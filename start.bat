@echo off
echo Starting Trading WebApp...

:: 设置窗口标题
title Trading WebApp Launcher

:: 使用 %~dp0 变量来获取脚本所在的目录（即项目根目录）
set "PROJECT_ROOT=%~dp0"

:: 检查后端 run.py 文件是否存在
IF NOT EXIST "%PROJECT_ROOT%backend\run.py" (
    echo ERROR: Backend start script not found at '%PROJECT_ROOT%backend\run.py'
    pause
    exit /b
)

:: 直接启动后端服务器，不激活任何虚拟环境
echo Starting Backend Server...
start "Backend Server" cmd /k "cd /d "%PROJECT_ROOT%backend" && python run.py"

echo.
echo Please wait a moment for the server to start...
timeout /t 5 /nobreak > nul

:: 打开浏览器访问应用
echo Opening application in your default browser...
start http://127.0.0.1:8000

echo.
echo Application is running. You can close this launcher window.