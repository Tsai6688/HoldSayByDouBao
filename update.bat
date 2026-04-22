@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

title HoldSay - 更新到最新版本

echo.
echo ========================================================
echo   HoldSay  .  更新到最新版本
echo ========================================================
echo.

rem ── 基础检查 ────────────────────────────────────────────
if not exist ".git" (
    echo [X] 当前目录不是 Git 仓库 , 无法自动更新 .
    echo.
    echo 两种方案任选其一:
    echo   A) 删除整个目录 , 在其它位置重新 git clone:
    echo      git clone git@github.com:Tsai6688/HoldSayByDouBao.git
    echo.
    echo   B) 去 GitHub 网页下载最新 zip , 解压覆盖本目录
    echo      (.env 不会被覆盖 , 请自己确认新版 .env.example 是否多了字段)
    echo.
    pause
    exit /b 1
)

where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] 未检测到 git , 请先安装 Git for Windows:
    echo     https://git-scm.com/download/win
    echo.
    pause
    exit /b 1
)

rem ── 1. 拉最新代码 ──────────────────────────────────────
echo [1/3] 从 GitHub 拉取最新代码...
git pull --rebase --autostash origin main
if %errorlevel% neq 0 (
    echo.
    echo [X] 拉取失败 , 常见原因:
    echo     - 本地改过代码且产生冲突
    echo     - 网络问题 (SSH / 代理)
    echo.
    echo 请手动处理:
    echo     git status           查看本地改动
    echo     git stash            临时保存本地改动
    echo     git pull --rebase    再拉一次
    echo     git stash pop        恢复本地改动 (如有冲突自己解决)
    echo.
    pause
    exit /b 1
)
echo.

rem ── 2. 同步依赖 (如有变化) ─────────────────────────────
echo [2/3] 同步 Python 依赖 (如果 pyproject 没变 , 会秒过)...
call uv sync
if %errorlevel% neq 0 (
    echo.
    echo [!] uv sync 失败 . 服务暂不重启 , 请手动排查 .
    echo.
    pause
    exit /b 1
)
echo.

rem ── 3. 重启服务生效 ────────────────────────────────────
echo [3/3] 重启后台服务以加载新版本...
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0doubaoctl.ps1" restart

echo.
echo ========================================================
echo   更新完成 !  按住 F2 说话 , 松开自动粘贴 .
echo ========================================================
echo.
pause
endlocal
