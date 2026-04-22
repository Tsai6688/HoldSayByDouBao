# HoldSay · Windows 使用说明

> 按住 **F2** 说话，松开后文字自动粘贴到光标位置。
> 基于豆包（火山引擎）流式语音识别大模型。

---

## 一键安装（推荐）

### ✅ 只需两步

1. **下载/克隆本仓库到你自己的目录**（建议放 `D:\Tools\HoldSay` 之类的稳定路径，不要放桌面）。
2. **双击 `setup.bat`**，按提示走完即可。

`setup.bat` 会自动帮你做完：

| 步骤 | 做什么 |
|---|---|
| 1 | 检查 `uv`，如未安装会自动从官方源下载 |
| 2 | 运行 `uv sync` 安装 Python 依赖 |
| 3 | 向导式让你填入豆包 `APP_ID` / `ACCESS_TOKEN`，写入 `.env` |
| 4 | 在"启动"文件夹创建快捷方式，开机自动运行 |
| 5 | 立即以 `pythonw.exe` 后台启动（无黑窗口） |

完成后：**按住 F2 说话，松开就行**。

> ⚠️ 不要直接双击 `doubaoctl.ps1`！Windows 会用记事本打开它。
> 入口永远是 **`setup.bat`**（首次）和 **`control.bat`**（日常）。

---

## 日常使用

### 控制面板

**双击 `control.bat`** 打开交互式菜单：

```
[1] 启动
[2] 停止
[3] 重启
[4] 查看日志    (Ctrl+C 退出日志窗口，不会停止服务)
[5] 重新向导式配置 (重写 .env)
[6] 卸载        (移除开机自启，不删除代码)
[0] 退出
```

### 快捷键

| 按键 | 动作 |
|---|---|
| 按住 **F2** | 开始录音 |
| 松开 **F2** | 停止录音 → 识别 → 自动粘贴（Ctrl+V）到光标位置 |

---

## 如何获取豆包凭证

新用户有免费额度，够日常用很久。

1. 注册 [火山引擎](https://www.volcengine.com/)
2. 开通 **"语音识别大模型"** 服务
3. 创建应用，勾选 **"流式语音识别（大模型）"**
4. 在应用详情页复制 **App ID** 和 **Access Token**

`setup.bat` 会在第一次运行时向导式询问这两个值。如果以后要换，双击 `control.bat` → `[5] 重新向导式配置`。

---

## 系统要求

- **Windows 10 / 11**
- **Python 3.11+**（如无，`uv` 会自动下载）
- 麦克风
- 联网（使用时需要访问豆包 WebSocket API）

> 如果你没有 `uv`，`setup.bat` 会自动装。手动安装命令：
> ```powershell
> powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
> ```

---

## 高级：命令行用法

如果你更喜欢命令行，可以直接调用 `doubaoctl.ps1`：

```powershell
# 首次使用前需要允许本地脚本执行（只需做一次）
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# 然后就能直接用
.\doubaoctl.ps1 install     # 注册开机自启
.\doubaoctl.ps1 start       # 启动
.\doubaoctl.ps1 stop        # 停止
.\doubaoctl.ps1 restart     # 重启
.\doubaoctl.ps1 status      # 查状态
.\doubaoctl.ps1 logs        # 实时日志
.\doubaoctl.ps1 uninstall   # 移除开机自启
```

---

## 工作原理

- **后台无窗口**：用 `pythonw.exe` 启动，不产生黑色命令行窗口。
- **开机自启**：在 Windows "启动"文件夹 (`shell:startup`) 创建快捷方式。
- **日志**：所有输出重定向到 `doubao_voice_input.log`，`control.bat → [4]` 可实时查看。
- **休眠恢复**：用 `WM_POWERBROADCAST` 监听 Windows 电源事件，从休眠/睡眠恢复后自动重建热键监听，保证 F2 永远可用。
- **凭证**：从 `.env` 读取，不会硬编码进代码，也不会被提交到 Git。

---

## 常见问题

**Q: 双击 `.ps1` 被记事本打开了？**
A: 这是 Windows 默认行为，**请不要双击 `.ps1` 文件**。统一使用 `setup.bat` 和 `control.bat`（双击即可运行）。

**Q: 为什么按 F2 没反应？**
A:
1. 确认 `control.bat` 里状态是 `● 运行中`
2. 看日志（`control.bat → [4]`）里有没有 `✅ 已就绪，按住 F2 说话`
3. 某些游戏、全屏应用或以管理员权限运行的窗口会吞掉全局键盘事件，试试其它应用（记事本、浏览器）里测。
4. 极少数笔记本 F2 被 BIOS/厂商热键软件占用，关掉 Fn 锁定或关掉 OEM 热键工具。

**Q: 识别出来是空的？**
A: 多半是麦克风没录到声音。Windows 设置 → 隐私和安全性 → 麦克风，允许应用访问。说话时观察日志里是否有 `🎤 采集`。

**Q: 怎么换热键？**
A: 编辑 `main_win.py` 顶部：
```python
HOTKEY = keyboard.Key.f2    # 改成 f3 / f4 / f6 ...
```
然后双击 `control.bat → [3] 重启`。

**Q: 要把它完全卸载？**
A: 双击 `control.bat → [6] 卸载`，会停止服务并移除开机自启；然后直接删掉整个目录即可。

---

## 问题反馈

在 GitHub 提 Issue，或带上日志：

```
doubao_voice_input.log
```
