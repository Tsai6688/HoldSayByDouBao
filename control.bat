@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

title HoldSay - 控制面板

:menu
cls
echo.
echo ========================================================
echo   HoldSay  .  控制面板
echo   按住 F2 说话 , 松开自动粘贴
echo ========================================================
echo.

rem 显示当前状态
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0doubaoctl.ps1" status

echo.
echo --------------------------------------------------------
echo   [1] 启动
echo   [2] 停止
echo   [3] 重启
echo   [4] 查看日志   (Ctrl+C 退出日志窗口 , 不会停止服务)
echo   [5] 重新向导式配置 (重写 .env)
echo   [6] 检查更新   (git pull + uv sync + 重启)
echo   [7] 卸载      (移除开机自启 , 不删除代码)
echo   [0] 退出
echo ========================================================
set "CHOICE="
set /p "CHOICE=请选择操作: "

if "!CHOICE!"=="1" goto do_start
if "!CHOICE!"=="2" goto do_stop
if "!CHOICE!"=="3" goto do_restart
if "!CHOICE!"=="4" goto do_logs
if "!CHOICE!"=="5" goto do_reconfig
if "!CHOICE!"=="6" goto do_update
if "!CHOICE!"=="7" goto do_uninstall
if "!CHOICE!"=="0" goto end
goto menu

:do_start
echo.
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0doubaoctl.ps1" start
echo.
pause
goto menu

:do_stop
echo.
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0doubaoctl.ps1" stop
echo.
pause
goto menu

:do_restart
echo.
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0doubaoctl.ps1" restart
echo.
pause
goto menu

:do_logs
echo.
echo (Ctrl+C 退出日志并返回菜单 , 服务继续运行)
echo.
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0doubaoctl.ps1" logs
goto menu

:do_reconfig
echo.
echo 重新配置豆包凭证 (会覆盖现有 .env)...
set /p "APPID=请输入 DOUBAO_APP_ID (纯数字): "
set /p "TOKEN=请输入 DOUBAO_ACCESS_TOKEN: "
if "!APPID!"=="" (
    echo [X] APP_ID 不能为空
    pause
    goto menu
)
if "!TOKEN!"=="" (
    echo [X] TOKEN 不能为空
    pause
    goto menu
)
> .env (
    echo DOUBAO_APP_ID=!APPID!
    echo DOUBAO_ACCESS_TOKEN=!TOKEN!
)
echo [OK] .env 已更新 , 正在重启服务以生效...
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0doubaoctl.ps1" restart
echo.
pause
goto menu

:do_update
echo.
call "%~dp0update.bat"
goto menu

:do_uninstall
echo.
set "CONFIRM="
set /p "CONFIRM=确定卸载? (会停止服务并移除开机自启) [y/N]: "
if /i not "!CONFIRM!"=="y" goto menu
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0doubaoctl.ps1" stop
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0doubaoctl.ps1" uninstall
echo.
pause
goto menu

:end
endlocal
exit /b 0
