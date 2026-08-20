@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title PolyDub 启动器
color 0A

if not exist "webui.py" (
  echo [错误] 未找到 webui.py，请确认在项目根目录（与 webui.py 同目录）运行本脚本。
  pause
  exit /b 1
)

REM 读取 setup.bat 安装时保存的 Python 路径
set "PYTHON="
if exist ".pyenv.txt" set /p PYTHON=<.pyenv.txt

REM 没有配置则自动探测
if "!PYTHON!"=="" (
  if exist ".venv\Scripts\python.exe" set "PYTHON=%CD%\.venv\Scripts\python.exe"
)
if "!PYTHON!"=="" set "PYTHON=python"

REM 校验 Python 是否存在
if /i "!PYTHON!"=="python" (
  echo 使用系统 Python：python
) else (
  if exist "!PYTHON!" (
    echo 使用 Python：!PYTHON!
  ) else (
    echo [警告] 配置的 Python 不存在：!PYTHON!
    echo 将尝试使用系统 python 命令 ...
    set "PYTHON=python"
  )
)

echo.
echo 正在启动 PolyDub Web UI ...
echo 启动后请在浏览器打开：http://127.0.0.1:7860
echo 关闭本窗口即可停止服务。
echo.
"!PYTHON!" webui.py --host 127.0.0.1 --port 7860
if errorlevel 1 (
  echo.
  echo [提示] 启动失败。若提示缺少依赖/模块，请先双击 setup.bat 一键安装。
)
echo.
pause
endlocal
