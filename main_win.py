"""
火山引擎豆包语音识别 - Windows 快捷输入脚本
用法: pythonw main_win.py       （后台无窗口）
      python  main_win.py       （前台带控制台，方便调试）
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


# ── Windows 无窗口（pythonw）下的 stdout/stderr 重定向 ────────────────
# pythonw.exe 没有控制台，sys.stdout/stderr 为 None，print 会抛异常。
# 统一把输出导到日志文件，让 ./doubaoctl.ps1 logs 能实时看见。

_LOG_FILE = Path(__file__).resolve().parent / "doubao_voice_input.log"

def _redirect_std_to_log_if_needed() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        try:
            sys.stdout.write("")
            sys.stderr.write("")
            return
        except Exception:
            pass
    log = open(_LOG_FILE, "a", encoding="utf-8", buffering=1)
    sys.stdout = log
    sys.stderr = log

_redirect_std_to_log_if_needed()


def _load_dotenv() -> None:
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
CHUNK_MS    = 100
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
    r = obj.get("result", "")
    if isinstance(r, dict): return (r.get("text") or "").strip()
    if isinstance(r, list): return "".join(i.get("text","") for i in r if isinstance(i,dict)).strip()
    if isinstance(r, str):  return r.strip()
    return ""

# ── 热键录音 ────────────────────────────────────────────────────────

BLOCK_SIZE = SAMPLE_RATE * CHUNK_MS // 1000

recording = False
processing = False
stream: sd.InputStream | None = None
state_lock = threading.Lock()
stop_event: threading.Event | None = None

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

    loop_ready.wait(timeout=2)
    stream.start()
    print("🔴 录音中...", flush=True)


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
    print("⏹  收尾中...", flush=True)


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
        # Windows 控制台 \r 刷新效果不稳定，且 pythonw 下无意义，直接换行
        print(line + (" " * pad), flush=True)
        preview_len = len(line)

    async def _run() -> str:
        global _active_loop, _active_queue
        q: asyncio.Queue[bytes] = asyncio.Queue()
        _active_loop = asyncio.get_running_loop()
        _active_queue = q
        loop_ready.set()
        return await asyncio.wait_for(
            recognize_streaming(q, session_stop_event, show_partial),
            timeout=30.0,
        )

    try:
        text = asyncio.run(_run())
        if text:
            paste(text)
        else:
            print("⚠️  未识别到内容", flush=True)
    except asyncio.TimeoutError:
        print("❌ 识别超时（30s），已放弃本次会话", flush=True)
    except Exception as e:
        print(f"❌ 识别失败: {e}", flush=True)
        traceback.print_exc()
    finally:
        loop_ready.set()
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
        await ws.send(encode_full_client({
            "user":    {"uid": "win_voice_input"},
            "audio":   {"format": "pcm", "codec": "raw", "rate": SAMPLE_RATE,
                        "bits": 16, "channel": CHANNELS, "language": "zh-CN"},
            "request": {"model_name": "bigmodel", "enable_punc": True, "result_type": "single"},
        }))

        raw = await ws.recv()
        kind, payload = parse_frame(raw)
        if kind == "error":
            raise RuntimeError(f"建联失败 [{payload['code']}]: {payload['message']}")

        async def sender():
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
                        await ws.close()
                    return

        async def receiver():
            nonlocal result_text
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=8.0)
                except asyncio.TimeoutError:
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
                        result_text = t
                        on_partial(t)
                    if payload.get("flags", 0) & 0x2:
                        break

        await asyncio.gather(sender(), receiver())

    if not sent_any:
        return ""
    return result_text.strip()

# ── 粘贴（Windows：Ctrl+V）─────────────────────────────────────────

def paste(text: str):
    pyperclip.copy(text)
    with _kbd_ctrl.pressed(keyboard.Key.ctrl):
        _kbd_ctrl.press('v')
        _kbd_ctrl.release('v')
    print(f"✅ 已粘贴：{text}", flush=True)

# ── 系统唤醒监听（Windows: WM_POWERBROADCAST）───────────────────────
# 创建一个 message-only 窗口，订阅电源事件，收到"恢复"事件时触发重建 Listener

def _wake_watcher(wake_event: threading.Event):
    import ctypes
    from ctypes import wintypes

    user32   = ctypes.WinDLL("user32",   use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    WM_POWERBROADCAST       = 0x0218
    PBT_APMRESUMESUSPEND    = 0x0007
    PBT_APMRESUMEAUTOMATIC  = 0x0012
    PBT_APMRESUMECRITICAL   = 0x0006
    HWND_MESSAGE            = wintypes.HWND(-3)

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )

    class WNDCLASS(ctypes.Structure):
        _fields_ = [
            ("style",         wintypes.UINT),
            ("lpfnWndProc",   WNDPROC),
            ("cbClsExtra",    ctypes.c_int),
            ("cbWndExtra",    ctypes.c_int),
            ("hInstance",     wintypes.HINSTANCE),
            ("hIcon",         wintypes.HICON),
            ("hCursor",       wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName",  wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    def wnd_proc(hwnd, msg, wparam, lparam):
        if msg == WM_POWERBROADCAST and wparam in (
            PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC, PBT_APMRESUMECRITICAL
        ):
            print("💤 系统唤醒，重建键盘监听", flush=True)
            wake_event.set()
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wndproc_c = WNDPROC(wnd_proc)

    user32.DefWindowProcW.restype       = ctypes.c_ssize_t
    user32.DefWindowProcW.argtypes      = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.RegisterClassW.restype       = wintypes.ATOM
    user32.RegisterClassW.argtypes      = [ctypes.POINTER(WNDCLASS)]
    user32.CreateWindowExW.restype      = wintypes.HWND
    user32.CreateWindowExW.argtypes     = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.GetMessageW.restype          = ctypes.c_int
    user32.GetMessageW.argtypes         = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.TranslateMessage.argtypes    = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes    = [ctypes.POINTER(wintypes.MSG)]

    hinst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASS()
    wc.lpfnWndProc   = wndproc_c
    wc.hInstance     = hinst
    wc.lpszClassName = "HoldSayWakeWatcher"

    atom = user32.RegisterClassW(ctypes.byref(wc))
    if not atom:
        # 可能已注册过，忽略
        pass

    hwnd = user32.CreateWindowExW(
        0, "HoldSayWakeWatcher", "HoldSay", 0,
        0, 0, 0, 0, HWND_MESSAGE, None, hinst, None,
    )
    if not hwnd:
        print("⚠️  创建 WakeWatcher 窗口失败，合盖唤醒自愈功能不可用", flush=True)
        return

    # 保持 wndproc_c 不被 GC
    _keepalive.append(wndproc_c)
    _keepalive.append(wc)

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


_keepalive: list = []


# ── 入口 ────────────────────────────────────────────────────────────

def main():
    import time

    print("=" * 40, flush=True)
    print("  豆包语音输入 for Windows", flush=True)
    print("=" * 40, flush=True)
    print("✅ 已就绪，按住 F5 说话，松开后自动识别并粘贴", flush=True)

    wake_event = threading.Event()
    threading.Thread(target=_wake_watcher, args=(wake_event,), daemon=True).start()

    while True:
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
        wake_event.wait()
        wake_event.clear()

        try:
            stop_and_recognize()
        except Exception:
            pass

        listener.stop()
        time.sleep(0.5)
        print("🔁 键盘监听已重建", flush=True)


if __name__ == "__main__":
    main()
