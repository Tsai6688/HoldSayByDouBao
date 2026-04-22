# HoldSay · Windows 控制脚本
# 用法: .\doubaoctl.ps1 <install|uninstall|start|stop|restart|status|logs>

$ErrorActionPreference = "Stop"

# ── 路径 ──────────────────────────────────────────────────────────────
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogPath   = Join-Path $ScriptDir "doubao_voice_input.log"
$PidFile   = Join-Path $ScriptDir ".doubao.pid"
$MainPy    = Join-Path $ScriptDir "main_win.py"
$Venv      = Join-Path $ScriptDir ".venv"
$PythonW   = Join-Path $Venv     "Scripts\pythonw.exe"
$Python    = Join-Path $Venv     "Scripts\python.exe"
$StartupDir = [Environment]::GetFolderPath("Startup")
$LinkPath  = Join-Path $StartupDir "HoldSay.lnk"

# ── 辅助函数 ──────────────────────────────────────────────────────────
function Test-Running {
    if (-not (Test-Path $PidFile)) { return $false }
    $pidNum = Get-Content $PidFile -ErrorAction SilentlyContinue
    if (-not $pidNum) { return $false }
    try {
        $p = Get-Process -Id $pidNum -ErrorAction Stop
        if ($p.ProcessName -match "python") { return $true }
    } catch {}
    return $false
}

function Ensure-Venv {
    if (-not (Test-Path $PythonW)) {
        Write-Host "❌ 找不到 $PythonW" -ForegroundColor Red
        Write-Host "   请先运行: uv sync" -ForegroundColor Yellow
        exit 1
    }
    if (-not (Test-Path $MainPy)) {
        Write-Host "❌ 找不到 $MainPy" -ForegroundColor Red
        exit 1
    }
}

# ── 命令实现 ──────────────────────────────────────────────────────────
function Cmd-Install {
    Ensure-Venv

    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($LinkPath)
    $Shortcut.TargetPath       = $PythonW
    $Shortcut.Arguments        = "`"$MainPy`""
    $Shortcut.WorkingDirectory = $ScriptDir
    $Shortcut.Description      = "HoldSay - 豆包语音输入（按住 F5 说话）"
    $Shortcut.Save()

    Write-Host "✅ 已创建开机启动快捷方式:" -ForegroundColor Green
    Write-Host "   $LinkPath"
    Write-Host ""
    Write-Host "说明："
    Write-Host "  · 下次开机会自动启动（pythonw.exe 无窗口）"
    Write-Host "  · 现在手动启动请执行: .\doubaoctl.ps1 start"
    Write-Host ""
    Write-Host "日志文件: $LogPath"
}

function Cmd-Uninstall {
    if (Test-Path $LinkPath) {
        Remove-Item $LinkPath -Force
        Write-Host "✅ 已移除开机启动快捷方式" -ForegroundColor Green
    } else {
        Write-Host "ℹ️  未找到开机启动快捷方式"
    }
}

function Cmd-Start {
    Ensure-Venv

    if (Test-Running) {
        $pidNum = Get-Content $PidFile
        Write-Host "⚠️  已经在运行 (PID=$pidNum)，要重启请用 restart" -ForegroundColor Yellow
        return
    }

    # 清空日志（保留最近一次的上下文更清爽）
    "" | Set-Content -Path $LogPath -Encoding UTF8

    # pythonw.exe 启动即无窗口，stdout 在 main_win.py 里重定向到 $LogPath
    $proc = Start-Process -FilePath $PythonW `
                          -ArgumentList "`"$MainPy`"" `
                          -WorkingDirectory $ScriptDir `
                          -WindowStyle Hidden `
                          -PassThru

    $proc.Id | Set-Content -Path $PidFile -Encoding ASCII

    Start-Sleep -Milliseconds 700
    if (Test-Running) {
        Write-Host "✅ 已启动 (PID=$($proc.Id))" -ForegroundColor Green
        Write-Host "日志: $LogPath"
    } else {
        Write-Host "⚠️  启动似乎失败，最近日志：" -ForegroundColor Yellow
        if (Test-Path $LogPath) { Get-Content $LogPath -Tail 30 }
        exit 1
    }
}

function Cmd-Stop {
    if (-not (Test-Running)) {
        Write-Host "ℹ️  未在运行"
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        return
    }
    $pidNum = Get-Content $PidFile
    try {
        Stop-Process -Id $pidNum -Force -ErrorAction Stop
        Write-Host "✅ 已停止 (PID=$pidNum)" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  进程无法停止: $_" -ForegroundColor Yellow
    }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
}

function Cmd-Restart {
    Cmd-Stop
    Start-Sleep -Milliseconds 400
    Cmd-Start
}

function Cmd-Status {
    if (Test-Running) {
        $pidNum = Get-Content $PidFile
        $p = Get-Process -Id $pidNum
        $mem = [math]::Round($p.WorkingSet64 / 1MB, 1)
        $cpu = [math]::Round($p.CPU, 2)
        Write-Host "● 运行中" -ForegroundColor Green
        Write-Host "  PID:       $pidNum"
        try { Write-Host "  启动时间:  $($p.StartTime)" } catch {}
        Write-Host "  CPU 时间:  ${cpu}s"
        Write-Host "  内存占用:  ${mem} MB"
        Write-Host "  日志文件:  $LogPath"

        $autoRun = Test-Path $LinkPath
        Write-Host "  开机自启:  $(if ($autoRun) { '是' } else { '否' })"
    } else {
        Write-Host "○ 未运行"
        $autoRun = Test-Path $LinkPath
        Write-Host "  开机自启:  $(if ($autoRun) { '是 (下次开机会自动启动)' } else { '否' })"
    }
}

function Cmd-Logs {
    if (-not (Test-Path $LogPath)) {
        "" | Set-Content $LogPath
    }
    Write-Host "实时日志 (Ctrl+C 退出)：$LogPath" -ForegroundColor Cyan
    Write-Host "─────────────────────────────────────────────"
    Get-Content -Path $LogPath -Wait -Tail 100
}

function Show-Usage {
@"
用法: .\doubaoctl.ps1 <command>

命令:
  install    创建开机自启动快捷方式（放到"启动"文件夹）
  uninstall  移除开机自启动快捷方式
  start      立即启动后台服务 (pythonw.exe，无窗口)
  stop       停止后台服务
  restart    重启
  status     查看运行状态
  logs       实时跟随日志

日志文件: $LogPath

首次使用：
  1. uv sync                      # 装依赖（需要先装 uv）
  2. copy .env.example .env       # 然后编辑 .env 填凭证
  3. .\doubaoctl.ps1 install      # 创建开机自启
  4. .\doubaoctl.ps1 start        # 立即启动
"@
}

# ── 分发 ──────────────────────────────────────────────────────────────
switch ($args[0]) {
    "install"   { Cmd-Install }
    "uninstall" { Cmd-Uninstall }
    "start"     { Cmd-Start }
    "stop"      { Cmd-Stop }
    "restart"   { Cmd-Restart }
    "status"    { Cmd-Status }
    "logs"      { Cmd-Logs }
    default     { Show-Usage }
}
