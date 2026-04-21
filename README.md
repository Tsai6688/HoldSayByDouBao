# 豆包语音输入 for Mac

> 按住 `F5` 说话，松开自动识别并粘贴到光标位置。  
> 基于火山引擎 / 豆包流式语音识别大模型，中文识别准确率和速度都非常能打。

![platform](https://img.shields.io/badge/platform-macOS%2011%2B-black)
![python](https://img.shields.io/badge/python-3.13%2B-blue)

---

## ✨ 特性

- **按住说话 / 松开即贴**：全局热键 `F5`，任何 App、任何输入框都能用
- **实时预览**：说话过程中识别结果实时滚动显示在日志里
- **后台常驻、无窗口**：用 macOS 原生 `launchd` 托管，没有终端黑窗口
- **一键启停**：`./doubaoctl start | stop | restart | status | logs`
- **睡眠自愈**：合盖/唤醒后自动重建键盘监听，不会失灵
- **兜底保护**：识别超时 / 服务异常 30 秒内自动恢复，不会把热键"卡死"
- **低延迟**：音频采样直接按 100ms 块发送，粘贴由 `pynput` 直接模拟 Cmd+V（比 osascript 快 100~300ms）

---

## 🧰 系统要求

- macOS 11 Big Sur 及以上（Apple Silicon / Intel 均可）
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) 包管理器（强烈推荐）  
  没装的话：`curl -LsSf https://astral.sh/uv/install.sh | sh`

---

## 🚀 快速开始（4 步）

### 1. 获取火山引擎 / 豆包凭证

1. 注册账号：<https://www.volcengine.com/>
2. 开通「语音识别大模型」服务：<https://www.volcengine.com/product/voice-tech>
3. 控制台 → **语音技术** → **应用管理** → **创建应用**，勾选「流式语音识别（大模型）」
4. 在应用详情页记下 **App ID** 和 **Access Token**

> 💡 火山引擎新用户有免费额度，日常个人使用基本用不完。

### 2. 填入凭证

```bash
cp .env.example .env
# 编辑 .env，填入刚拿到的 App ID 和 Token
```

`.env` 里应该是这样：

```env
DOUBAO_APP_ID=1234567890
DOUBAO_ACCESS_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. 安装依赖

```bash
uv sync
```

uv 会自动下载对应 Python 版本和所有依赖到 `.venv/` 里，**不污染系统环境**。

### 4. 安装并启动后台服务

```bash
chmod +x doubaoctl
./doubaoctl install   # 首次安装（生成 LaunchAgent 配置）
./doubaoctl grant     # 打开系统设置协助授权（见下一节）
./doubaoctl start     # 启动后台服务
```

---

## 🔐 授予权限（关键，必须做）

macOS 有一套叫 TCC 的权限系统，本工具需要三项权限：

| 权限 | 用途 | 如何授予 |
|------|------|----------|
| **辅助功能** (Accessibility) | 发送 `Cmd+V` 自动粘贴 | 系统设置 → 隐私与安全性 → 辅助功能 |
| **输入监控** (Input Monitoring) | 监听全局 `F5` 热键 | 系统设置 → 隐私与安全性 → 输入监控 |
| **麦克风** (Microphone) | 录音 | 第一次录音时系统会自动弹窗 |

### ⚠️ 踩坑提醒：必须加"真实路径"

`.venv/bin/python` 是一个符号链接，**macOS 认的是解析后的真实路径**。直接拖 `.venv/bin/python` 进去等于没授权。

执行 `./doubaoctl grant` 会自动打印出真实路径并打开对应面板，大致长这样：

```
/Users/你的用户名/.local/share/uv/python/cpython-3.13.xx-macos-xxxx-none/bin/python3.13
```

**操作步骤**：
1. 运行 `./doubaoctl grant`
2. Finder 会高亮一个 `python3.13` 文件
3. 在弹出的「**辅助功能**」面板点 `+`，把高亮的 `python3.13` 拖进去，开启
4. 切到「**输入监控**」面板，重复一次
5. 回终端：`./doubaoctl restart`

---

## 📖 日常使用

### 命令速查

```bash
./doubaoctl install    # 安装 LaunchAgent（首次）
./doubaoctl uninstall  # 卸载
./doubaoctl grant      # 协助授权（打开系统设置 + Finder 定位）
./doubaoctl start      # 启动
./doubaoctl stop       # 停止
./doubaoctl restart    # 重启（改完代码或权限后用）
./doubaoctl status     # 查看运行状态
./doubaoctl logs       # 实时查看日志（Ctrl+C 退出）
```

### 使用方式

1. 把光标焦点切到任意一个输入框（微信、Slack、ChatGPT、浏览器地址栏、VSCode……都可以）
2. **按住** `F5`
3. 看到终端提示「🔴 录音中...」后开始说话
4. 说完**松开** `F5`
5. 识别完成后，文字会自动粘贴到光标位置

识别过程中 `./doubaoctl logs` 里会实时滚动显示识别结果：

```
🔴 录音中...
📝 今天天气
📝 今天天气真不错
⏹  收尾中...
📝 今天天气真不错。
✅ 已粘贴：今天天气真不错。
```

---

## 🛠 故障排查

### F5 完全没反应

1. 检查服务是否在跑：`./doubaoctl status`，没跑就 `./doubaoctl start`
2. 检查日志：`./doubaoctl logs`，看到 `not trusted` 字样 → 缺"辅助功能"或"输入监控"权限
3. 授权后**必须** `./doubaoctl restart` 让进程重新加载权限

### 能录音、有识别结果，但不自动粘贴

典型表现：日志里有 `✅ 已粘贴：xxx`，但光标位置什么也没出现（手动 Cmd+V 能贴出来）。

**原因**：缺"辅助功能"权限（注意不是"输入监控"）。授权后 `./doubaoctl restart`。

### 合盖/唤醒后失灵（已自动修复）

本项目内置了 macOS 系统唤醒监听，唤醒时会自动重建键盘 Listener。如果仍然偶发失灵，手动 `./doubaoctl restart` 即可。

### 识别半天没反应

30 秒内会自动超时恢复，看日志：
- `❌ 识别超时` → 网络/服务端问题，重试
- `❌ 识别失败: xxx` → 看 traceback 定位

### 授权明明加了还是不行

多半是加了 `.venv/bin/python` 这个**符号链接**。TCC 需要的是**真实路径**：

```bash
./doubaoctl grant    # 会打印真实路径并定位
```

把列表里的旧条目删掉，用新定位到的 `python3.13` 重新加。

---

## 📂 项目结构

```
autosb/
├── main.py                    # 主程序（录音 / WebSocket / 热键 / 粘贴）
├── doubaoctl                  # launchd 控制脚本（启停/日志/授权）
├── pyproject.toml             # 依赖声明（uv 使用）
├── uv.lock                    # 依赖锁文件
├── .env.example               # 凭证模板
├── .env                       # 你的凭证（本地，git 忽略）
├── doubao_voice_input.log     # 运行日志（自动生成，git 忽略）
└── README.md
```

---

## ⚙️ 自定义配置

编辑 `main.py` 顶部常量：

| 常量 | 默认 | 说明 |
|------|------|------|
| `HOTKEY` | `F5` | 热键，改成其他 `keyboard.Key.xxx` 即可 |
| `SAMPLE_RATE` | 16000 | 采样率，豆包要求 16kHz |
| `CHUNK_MS` | 100 | 每次发送粒度（毫秒），越小越实时 |

改完记得 `./doubaoctl restart`。

---

## ❓ FAQ

**Q: 这个能完全离线用吗？**  
A: 不能，识别是调用火山引擎的云服务。如果你追求离线，需要换成 whisper.cpp 等本地方案。

**Q: 火山引擎要花钱吗？**  
A: 新用户有免费额度，日常个人使用（每天几十分钟）基本不会超。超了是按时长计费，价格见官网。

**Q: 可以改成其他热键吗？**  
A: 可以，改 `main.py` 的 `HOTKEY` 常量。如果要组合键（如 Option+Space）稍微麻烦点，需要改 `on_press/on_release` 逻辑。

**Q: 支持英文 / 其他语言吗？**  
A: 改 `main.py` 里 `"language": "zh-CN"` 为 `"en-US"` 等即可，支持列表查火山引擎文档。

**Q: 开机自启怎么搞？**  
A: 编辑 `doubaoctl` 里 `gen_plist()` 函数，把 `<key>RunAtLoad</key><false/>` 改成 `<true/>`，然后 `./doubaoctl install && ./doubaoctl restart`。

**Q: 不想要后台常驻，每次手动跑怎么办？**  
A: 直接 `uv run python main.py` 即可，这时候会有终端窗口输出日志，Ctrl+C 退出。

---

## 📝 License

MIT — 爱咋用咋用。
