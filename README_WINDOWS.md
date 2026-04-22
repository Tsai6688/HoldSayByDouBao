# HoldSay for Windows

> Mac 版用户请看 [`README.md`](./README.md)。
> Windows 版通过另一套入口文件 `main_win.py` 和 PowerShell 控制脚本 `doubaoctl.ps1` 实现，**与 Mac 版共享 `.env` 配置，互不干扰**。

---

## 🧰 系统要求

- Windows 10 / 11（64 位）
- Python 3.13+
- [uv](https://docs.astral.sh/uv/) 包管理器

  PowerShell 一行装：

  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

---

## 🚀 快速开始

### 1. 获取豆包凭证

注册火山引擎 → 开通语音识别大模型 → 记下 `App ID` 和 `Access Token`。详见 [`README.md`](./README.md) 的"获取火山引擎凭证"一节。

### 2. 克隆仓库 + 配置凭证

```powershell
git clone https://github.com/Tsai6688/HoldSayByDouBao.git
cd HoldSayByDouBao
copy .env.example .env
notepad .env   # 填入 DOUBAO_APP_ID / DOUBAO_ACCESS_TOKEN
```

### 3. 装依赖

```powershell
uv sync
```

> `uv` 会在 `.venv\` 里创建独立 Python 环境，不污染系统。

### 4. 允许 PowerShell 执行脚本（只需一次）

默认 Windows 可能禁止运行本地 `.ps1`。用**管理员 PowerShell** 执行一次：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

（或者 `-Scope Process` 只对当前窗口生效，更保守）

### 5. 安装 + 启动

```powershell
.\doubaoctl.ps1 install   # 注册开机自启（在"启动"文件夹放快捷方式）
.\doubaoctl.ps1 start     # 立即启动后台服务（pythonw.exe，无窗口）
.\doubaoctl.ps1 logs      # 实时查看日志（Ctrl+C 退出日志不会停止服务）
```

---

## 🎤 使用

1. 光标焦点切到任意输入框（微信、浏览器、VSCode、记事本……）
2. **按住** `F5`
3. 看日志出现 `🔴 录音中...` 后说话
4. 说完**松开** `F5`
5. 文字自动粘贴到光标位置（Ctrl+V 由脚本模拟触发）

---

## 🛠 命令速查

| 命令 | 作用 |
|------|------|
| `.\doubaoctl.ps1 install` | 注册开机自启（启动文件夹放 `HoldSay.lnk`） |
| `.\doubaoctl.ps1 uninstall` | 移除开机自启 |
| `.\doubaoctl.ps1 start` | 立即启动后台服务 |
| `.\doubaoctl.ps1 stop` | 停止后台服务 |
| `.\doubaoctl.ps1 restart` | 重启 |
| `.\doubaoctl.ps1 status` | 查看状态（PID / 内存 / CPU / 是否自启） |
| `.\doubaoctl.ps1 logs` | 实时跟随日志 |

---

## 🔐 权限

Windows 上**不需要** macOS 那一套 TCC 授权流程，但第一次录音时：

- **麦克风弹窗**：同意即可（之后系统自动记住）
- **Windows 11 的"麦克风访问"开关**：如果没弹窗且日志报麦克风错误，去 `系统设置 → 隐私和安全性 → 麦克风` 确认已开启"允许应用访问麦克风"以及"允许桌面应用访问麦克风"

如果需要监听 **以管理员权限运行的程序**（比如某些 IDE 以管理员启动）的按键，HoldSay 自己也要以管理员运行。一般场景用不着。

---

## 🛠 故障排查

### 按 F5 完全没反应

1. 查状态：`.\doubaoctl.ps1 status`，如果"未运行"就 `start`
2. 查日志：`.\doubaoctl.ps1 logs`，看有没有报错堆栈

### 能录音、识别成功，但没粘贴出来

- 多半是目标 App 拦截了模拟按键（少见，比如 VMware 全屏、某些安全软件）。手动 Ctrl+V 能贴就证明识别正常。

### `Start-Process` 报错 / 无法执行 .ps1

- 执行策略问题。参见上面第 4 步：`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

### 合盖/唤醒后失灵

已内置 `WM_POWERBROADCAST` 监听，唤醒会自动重建键盘监听。如果偶发仍失灵：`.\doubaoctl.ps1 restart`。

### 想改 F5 为别的热键

编辑 `main_win.py` 顶部 `HOTKEY = keyboard.Key.f5`，然后 `.\doubaoctl.ps1 restart`。

### pythonw 没输出日志

`main_win.py` 启动时会自动把 stdout/stderr 重定向到 `doubao_voice_input.log`。如果还是没日志，可能是 venv 里的 `pythonw.exe` 路径不对，执行 `.\doubaoctl.ps1 status` 检查。

---

## 📂 与 Mac 版的关系

| 文件 | 平台 |
|------|------|
| `main.py` | macOS 专用 |
| `main_win.py` | Windows 专用 |
| `doubaoctl`（bash） | macOS |
| `doubaoctl.ps1`（PowerShell） | Windows |
| `.env` / `.env.example` / `pyproject.toml` / `uv.lock` | **共享** |

两套代码目前平行演进，没有共享的 module。如果想 Mac / Windows 一键切换，可以在同一台开发机上切换 venv 后用对应的入口脚本。

---

## 📝 License

MIT — 同 Mac 版。
