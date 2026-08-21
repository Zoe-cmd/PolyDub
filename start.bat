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

REM ---------- 查找 Python 环境 ----------
set "PYTHON="

REM 1) 读取 setup.bat 保存的路径
if exist ".pyenv.txt" set /p PYTHON=<.pyenv.txt
if not "!PYTHON!"=="" goto :py_check

REM 2) 项目内 .venv
if exist ".venv\Scripts\python.exe" set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not "!PYTHON!"=="" goto :py_check

REM 3) 自动探测 conda 环境（常见安装位置 + transvideo/vt/soulx）
set "CONDA_BASE="
for %%d in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3" "C:\anaconda3" "C:\miniconda3") do (
  if not defined CONDA_BASE if exist "%%~d\envs\transvideo\python.exe" set "CONDA_BASE=%%~d"
  if not defined CONDA_BASE if exist "%%~d\envs\vt\python.exe" set "CONDA_BASE=%%~d"
  if not defined CONDA_BASE if exist "%%~d\envs\soulx\python.exe" set "CONDA_BASE=%%~d"
)
if defined CONDA_BASE if exist "!CONDA_BASE!\envs\transvideo\python.exe" set "PYTHON=!CONDA_BASE!\envs\transvideo\python.exe"
if not defined PYTHON if defined CONDA_BASE if exist "!CONDA_BASE!\envs\vt\python.exe" set "PYTHON=!CONDA_BASE!\envs\vt\python.exe"
if not defined PYTHON if defined CONDA_BASE if exist "!CONDA_BASE!\envs\soulx\python.exe" set "PYTHON=!CONDA_BASE!\envs\soulx\python.exe"
if defined PYTHON goto :py_check

:py_sys
set "PYTHON=python"

:py_check
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
