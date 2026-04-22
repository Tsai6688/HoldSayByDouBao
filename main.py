"""
火山引擎豆包语音识别 - Mac 快捷输入脚本（优化版）
用法: python voice_input.py
"""

import asyncio
import gzip
import json
import os
import struct
import sys
import traceback
import uuid
import threading
from pathlib import Path

from pynput import keyboard
import sounddevice as sd
import websockets
import pyperclip


def _load_dotenv() -> None:
    """Load KEY=VALUE lines from a local .env file into os.environ (no-op if missing)."""
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()

APP_ID      = os.environ.get("DOUBAO_APP_ID", "").strip()
TOKEN       = os.environ.get("DOUBAO_ACCESS_TOKEN", "").strip()
RESOURCE_ID = os.environ.get("DOUBAO_RESOURCE_ID", "volc.bigasr.sauc.duration").strip()
WSS_URL     = os.environ.get(
    "DOUBAO_WSS_URL",
    "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
).strip()

if not APP_ID or not TOKEN:
    print(
        "❌ 未配置火山引擎凭证。\n"
        "   请在项目根目录创建 .env 文件（可参考 .env.example），填入：\n"
        "     DOUBAO_APP_ID=你的 App ID\n"
        "     DOUBAO_ACCESS_TOKEN=你的 Access Token\n",
        file=sys.stderr,
    )
    sys.exit(1)

SAMPLE_RATE = 16000
CHANNELS    = 1
CHUNK_MS    = 100   # 发送粒度，小一点让最后一包更快到
HOTKEY      = keyboard.Key.f5

# ── 二进制帧编解码 ──────────────────────────────────────────────────

_VER             = 0x1
_HDR_SIZE_NIBBLE = 0x1
_MSG_FULL_CLIENT = 0x1
_MSG_AUDIO_ONLY  = 0x2
_MSG_FULL_SERVER = 0x9
_MSG_ERROR       = 0xF
_SER_JSON        = 0x1
_SER_NONE        = 0x0
_CMP_GZIP        = 0x1
_CMP_NONE        = 0x0


def _hdr(msg_type, flags, ser, compression):
    return bytes([(_VER << 4) | _HDR_SIZE_NIBBLE, (msg_type << 4) | (flags & 0xF),
                  (ser << 4) | (compression & 0xF), 0])


def encode_full_client(payload: dict) -> bytes:
    body = gzip.compress(json.dumps(payload, ensure_ascii=False).encode())
    return _hdr(_MSG_FULL_CLIENT, 0, _SER_JSON, _CMP_GZIP) + struct.pack(">I", len(body)) + body


def encode_audio(pcm: bytes, is_last: bool) -> bytes:
    flags = 0x2 if is_last else 0x0
    body  = gzip.compress(pcm)
    return _hdr(_MSG_AUDIO_ONLY, flags, _SER_NONE, _CMP_GZIP) + struct.pack(">I", len(body)) + body


def parse_frame(data: bytes) -> tuple[str, dict]:
    if len(data) < 4:
        raise ValueError("响应帧过短")
    header_len = (data[0] & 0xF) * 4
    msg_type   = (data[1] >> 4) & 0xF
    flags      = data[1] & 0xF
    compress   = data[2] & 0xF
    pos        = header_len

    if msg_type == _MSG_ERROR:
        code = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        elen = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
        return "error", {"code": code, "message": data[pos:pos+elen].decode(errors="replace")}

    if msg_type != _MSG_FULL_SERVER:
        return "skip", {}

    seq  = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
    plen = struct.unpack(">I", data[pos:pos+4])[0]; pos += 4
    body = data[pos:pos+plen]
    if compress == _CMP_GZIP:
        body = gzip.decompress(body)
    elif compress != _CMP_NONE:
        raise ValueError(f"不支持的压缩: {compress}")
    obj = json.loads(body.decode("utf-8"))
    return "result", {"flags": flags, "seq": seq, "obj": obj}


def extract_text(obj: dict) -> str:
    """
    取完整累积文本。
    豆包流式 ASR 一旦检测到句子切分，result.text 只会回当前这一句，
    之前已经"定稿"的句子被塞到 result.utterances[] 里。
    这里优先把 utterances[] 顺序拼接得到累积全量，utterances 缺失时再回落到 text。
    """
    r = obj.get("result", "")
    if isinstance(r, dict):
        utterances = r.get("utterances")
        if isinstance(utterances, list) and utterances:
            full = "".join(
                (u.get("text") or "")
                for u in utterances
                if isinstance(u, dict)
            ).strip()
            if full:
                return full
        return (r.get("text") or "").strip()
    if isinstance(r, list):
        return "".join(i.get("text","") for i in r if isinstance(i,dict)).strip()
    if isinstance(r, str):  return r.strip()
    return ""

# ── 热键录音 ────────────────────────────────────────────────────────

BLOCK_SIZE = SAMPLE_RATE * CHUNK_MS // 1000  # 每次回调的采样点数

recording = False
processing = False
stream: sd.InputStream | None = None
state_lock = threading.Lock()
stop_event: threading.Event | None = None

# 录音回调 → asyncio 事件循环 的跨线程通道
_active_loop: asyncio.AbstractEventLoop | None = None
_active_queue: asyncio.Queue[bytes] | None = None

_kbd_ctrl = keyboard.Controller()


def _audio_callback(indata, *_):
    if not recording:
        return
    loop = _active_loop
    q = _active_queue
    if loop is None or q is None:
        return
    data = bytes(indata)
    try:
        loop.call_soon_threadsafe(q.put_nowait, data)
    except RuntimeError:
        pass


def start_recording():
    global recording, processing, stream, stop_event

    with state_lock:
        if recording or processing:
            return
        stop_event = threading.Event()
        loop_ready = threading.Event()
        current_stop_event = stop_event

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=BLOCK_SIZE,
            callback=_audio_callback,
        )
        recording = True
        processing = True

        threading.Thread(
            target=run_stream_session,
            args=(current_stop_event, loop_ready),
            daemon=True,
        ).start()

    # 等识别线程的 asyncio loop 就绪，再开启麦克风，防止早期音频丢失
    loop_ready.wait(timeout=2)
    stream.start()
    print("🔴 录音中...")


def stop_and_recognize():
    global recording, stream, stop_event

    with state_lock:
        if not recording or stream is None:
            return
        current_stream = stream
        stream = None
        recording = False
        current_stop_event = stop_event

    current_stream.stop()
    current_stream.close()
    if current_stop_event is not None:
        current_stop_event.set()
    print("⏹  收尾中...")


def run_stream_session(
    session_stop_event: threading.Event,
    loop_ready: threading.Event,
):
    global processing, stop_event, _active_loop, _active_queue

    preview_len = 0

    def show_partial(text: str):
        nonlocal preview_len
        line = f"📝 {text}"
        pad = max(0, preview_len - len(line))
        print("\r" + line + (" " * pad), end="", flush=True)
        preview_len = len(line)

    async def _run() -> str:
        global _active_loop, _active_queue
        q: asyncio.Queue[bytes] = asyncio.Queue()
        _active_loop = asyncio.get_running_loop()
        _active_queue = q
        loop_ready.set()
        # 整体硬超时：任何死锁都不会把状态锁死
        return await asyncio.wait_for(
            recognize_streaming(q, session_stop_event, show_partial),
            timeout=30.0,
        )

    try:
        text = asyncio.run(_run())
        if preview_len:
            print()
        if text:
            paste(text)
        else:
            print("⚠️  未识别到内容")
    except asyncio.TimeoutError:
        if preview_len:
            print()
        print("❌ 识别超时（30s），已放弃本次会话")
    except Exception as e:
        if preview_len:
            print()
        print(f"❌ 识别失败: {e}")
        traceback.print_exc()
    finally:
        loop_ready.set()  # 万一异常早退，避免主线程卡 wait
        with state_lock:
            processing = False
            _active_loop = None
            _active_queue = None
            if stop_event is session_stop_event:
                stop_event = None


def on_press(key):
    if key == HOTKEY:
        start_recording()


def on_release(key):
    if key == HOTKEY:
        stop_and_recognize()

# ── 核心识别：边录边发 + 实时接收 ───────────────────────────────────

async def recognize_streaming(
    session_audio_queue: asyncio.Queue[bytes],
    session_stop_event: threading.Event,
    on_partial,
) -> str:
    headers = {
        "X-Api-App-Key":     APP_ID,
        "X-Api-Access-Key":  TOKEN,
        "X-Api-Resource-Id": RESOURCE_ID,
        "X-Api-Connect-Id":  str(uuid.uuid4()),
    }

    result_text = ""
    sent_any = False

    async with websockets.connect(WSS_URL, additional_headers=headers, proxy=None) as ws:

        # ── 建联 ──
        await ws.send(encode_full_client({
            "user":    {"uid": "mac_voice_input"},
            "audio":   {"format": "pcm", "codec": "raw", "rate": SAMPLE_RATE,
                        "bits": 16, "channel": CHANNELS, "language": "zh-CN"},
            "request": {"model_name": "bigmodel", "enable_punc": True, "result_type": "single"},
        }))

        raw = await ws.recv()
        kind, payload = parse_frame(raw)
        if kind == "error":
            raise RuntimeError(f"建联失败 [{payload['code']}]: {payload['message']}")

        # ── 并发：发送 + 接收同时跑，不互相等待 ──

        async def sender():
            """把录音回调产出的 PCM 连续发给服务端。"""
            nonlocal sent_any
            prev: bytes | None = None

            while True:
                try:
                    pcm = await asyncio.wait_for(
                        session_audio_queue.get(),
                        timeout=CHUNK_MS / 1000,
                    )
                except asyncio.TimeoutError:
                    pcm = None

                if pcm is not None:
                    if prev is not None:
                        await ws.send(encode_audio(prev, is_last=False))
                        sent_any = True
                    prev = pcm

                if session_stop_event.is_set():
                    while not session_audio_queue.empty():
                        if prev is not None:
                            await ws.send(encode_audio(prev, is_last=False))
                            sent_any = True
                        prev = session_audio_queue.get_nowait()

                    if prev is not None:
                        await ws.send(encode_audio(prev, is_last=True))
                        sent_any = True
                    else:
                        # 一个音频包都没收到（按键过短或麦克风异常），
                        # 主动关掉 ws，让 receiver 从 async for 里退出
                        await ws.close()
                    return

        async def receiver():
            """持续收服务端的中间结果和最终结果。"""
            nonlocal result_text
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=8.0)
                except asyncio.TimeoutError:
                    # 兜底：8 秒没有任何服务端推送，放弃，避免死锁
                    break
                except websockets.ConnectionClosed:
                    break

                if isinstance(raw, str):
                    continue
                kind, payload = parse_frame(raw)
                if kind == "error":
                    raise RuntimeError(f"识别出错 [{payload['code']}]: {payload['message']}")
                if kind == "result":
                    t = extract_text(payload.get("obj", {}))
                    if t:
                        # 累积文本只允许增长 / 改写，不允许变短
                        # （防止服务端切句后的某一帧只回当前句导致历史丢失）
                        if len(t) >= len(result_text):
                            result_text = t
                            on_partial(result_text)
                    # flags 含 bit1（0x2）时一般为最后一包识别结果（文档 0b0011）
                    if payload.get("flags", 0) & 0x2:
                        break

        await asyncio.gather(sender(), receiver())

    if not sent_any:
        return ""
    return result_text.strip()

# ── 粘贴 ────────────────────────────────────────────────────────────

def paste(text: str):
    pyperclip.copy(text)
    with _kbd_ctrl.pressed(keyboard.Key.cmd):
        _kbd_ctrl.press('v')
        _kbd_ctrl.release('v')
    print(f"✅ 已粘贴：{text}")

# ── 系统唤醒监听 ────────────────────────────────────────────────────
# macOS 休眠/唤醒后 CGEventTap 会被系统静默关闭，pynput Listener 仍活着
# 但再也收不到按键。这里监听 NSWorkspaceDidWakeNotification，唤醒时重建。

def _wake_watcher(wake_event: threading.Event):
    from AppKit import NSWorkspace
    from Foundation import NSObject, NSRunLoop

    class _Observer(NSObject):
        def handleWake_(self, _notification):
            print("💤 系统唤醒，重建键盘监听", flush=True)
            wake_event.set()

    observer = _Observer.alloc().init()
    nc = NSWorkspace.sharedWorkspace().notificationCenter()
    nc.addObserver_selector_name_object_(
        observer,
        b"handleWake:",
        "NSWorkspaceDidWakeNotification",
        None,
    )
    NSRunLoop.currentRunLoop().run()


# ── 入口 ────────────────────────────────────────────────────────────

def main():
    import time

    print("=" * 40)
    print("  豆包语音输入 for Mac")
    print("=" * 40)
    print("✅ 已就绪，按住 F5 说话，松开后自动识别并粘贴")
    print("按 Ctrl+C 退出")

    wake_event = threading.Event()
    threading.Thread(target=_wake_watcher, args=(wake_event,), daemon=True).start()

    while True:
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        wake_event.wait()  # 阻塞直到唤醒
        wake_event.clear()

        # 若唤醒时正好在录音，先把它收尾，避免悬挂状态
        try:
            stop_and_recognize()
        except Exception:
            pass

        listener.stop()
        time.sleep(0.5)  # 让系统完成唤醒流程再重建监听
        print("🔁 键盘监听已重建", flush=True)


if __name__ == "__main__":
    main()
