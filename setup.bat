@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

title HoldSay - 一键安装

echo.
echo ========================================================
echo   HoldSay  .  豆包语音输入 for Windows
echo   按住 F2 说话 , 松开自动粘贴
echo ========================================================
echo.
echo 本脚本将自动完成:
echo   [1/5] 检查/安装 uv (Python 包管理器)
echo   [2/5] 同步 Python 依赖
echo   [3/5] 配置豆包凭证 (向导式填入 .env)
echo   [4/5] 注册开机自启 (启动文件夹快捷方式)
echo   [5/5] 启动后台服务
echo.
pause

rem ============================================================
rem [1/5] 检查/安装 uv
rem ============================================================
echo.
echo ----------------------------------------
echo [1/5] 检查 uv ...
echo ----------------------------------------
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo uv 未安装 , 正在从官方源下载...
    powershell -ExecutionPolicy Bypass -NoProfile -Command "irm https://astral.sh/uv/install.ps1 | iex"
    rem 把 uv 默认安装路径加入当前 cmd 的 PATH
    set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
    where uv >nul 2>&1
    if !errorlevel! neq 0 (
        echo.
        echo [X] uv 自动安装失败 . 请手动安装后重新运行本脚本:
        echo     powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
        echo.
        pause
        exit /b 1
    )
    echo [OK] uv 已安装
) else (
    echo [OK] uv 已就绪
)

rem ============================================================
rem [2/5] 同步 Python 依赖
rem ============================================================
echo.
echo ----------------------------------------
echo [2/5] 同步 Python 依赖 (首次会比较慢)...
echo ----------------------------------------
call uv sync
if %errorlevel% neq 0 (
    echo.
    echo [X] uv sync 失败 . 请检查网络或手动运行 "uv sync" 查看错误
    pause
    exit /b 1
)
echo [OK] 依赖同步完成

rem ============================================================
rem [3/5] 配置 .env
rem ============================================================
echo.
echo ----------------------------------------
echo [3/5] 配置豆包凭证
echo ----------------------------------------
if exist ".env" (
    echo [OK] 已存在 .env , 跳过凭证配置
    echo      如需修改 , 请用记事本编辑 .env
) else (
    echo.
    echo 如何获取凭证 (新用户有免费额度):
    echo   1. 注册火山引擎: https://www.volcengine.com/
    echo   2. 开通"语音识别大模型"服务
    echo   3. 创建应用 , 勾选"流式语音识别(大模型)"
    echo   4. 在应用详情页复制 App ID 和 Access Token
    echo.
    set /p "APPID=请输入 DOUBAO_APP_ID (纯数字): "
    set /p "TOKEN=请输入 DOUBAO_ACCESS_TOKEN: "
    if "!APPID!"=="" (
        echo [X] APP_ID 不能为空
        pause
        exit /b 1
    )
    if "!TOKEN!"=="" (
        echo [X] TOKEN 不能为空
        pause
        exit /b 1
    )
    > .env (
        echo DOUBAO_APP_ID=!APPID!
        echo DOUBAO_ACCESS_TOKEN=!TOKEN!
    )
    echo [OK] .env 已生成
)

rem ============================================================
rem [4/5] 注册开机自启
rem ============================================================
echo.
echo ----------------------------------------
echo [4/5] 注册开机自启...
echo ----------------------------------------
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0doubaoctl.ps1" install
if %errorlevel% neq 0 (
    echo [!] 注册开机自启失败 , 但不影响立即启动
)

rem ============================================================
rem [5/5] 启动后台服务
rem ============================================================
echo.
echo ----------------------------------------
echo [5/5] 启动后台服务...
echo ----------------------------------------
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0doubaoctl.ps1" start
if %errorlevel% neq 0 (
    echo [X] 启动失败 , 请查看日志: doubao_voice_input.log
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   全部完成 !
echo.
echo   使用方法:
echo     [*] 按住 F2 说话 , 松开后文字自动出现在光标位置
echo.
echo   日常控制:
echo     [*] 双击 control.bat 打开控制面板 (启停/查日志/卸载)
echo.
echo   首次录音时 Windows 可能会弹窗请求麦克风权限 , 请允许 .
echo ========================================================
echo.
pause
endlocal
