@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title PolyDub 一键安装
color 0A

if not exist "main.py" (
  echo [错误] 未找到 main.py，请把 setup.bat 放在项目根目录（与 main.py 同目录）再运行。
  pause
  exit /b 1
)

echo ============================================================
echo   PolyDub - AI 多说话人视频翻译与配音系统  一键安装
echo ============================================================
echo.
echo 本脚本会引导你完成：
echo   1. 选择 Python 环境（conda / .venv / 系统 Python）
echo   2. 安装全部依赖（PyTorch CUDA、ASR、说话人识别等）
echo   3. 配置 IndexTTS 2.5（本地语音克隆）
echo   4. 下载 AI 模型
echo   5. 生成 .env 配置文件
echo.
echo 需要联网，预计 20~60 分钟（取决于网速）。
echo.

REM ========== 1. 检查基础工具 ==========
echo [1/7] 检查基础工具 ...
set "NEED=0"
where git >nul 2>nul
if errorlevel 1 (
  echo   [错误] 未安装 git。请先安装：https://git-scm.com/download/win
  set "NEED=1"
) else (
  echo   [OK] git
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo   [警告] 未检测到 ffmpeg。最终合成视频需要它：
  echo          https://www.gyan.dev/ffmpeg/builds/ （下载 release 版，解压后把 bin 目录加进 PATH）
) else (
  echo   [OK] ffmpeg
)
if "!NEED!"=="1" (
  echo.
  echo 请先安装缺失的工具再运行本脚本。
  goto :end
)

REM ========== 2. 选择 Python 环境 ==========
echo.
echo [2/7] 选择 Python 环境 ...
echo   当前电脑检测结果：
where conda >nul 2>nul && echo   - 已安装 conda（Miniconda/Anaconda）
where python >nul 2>nul && echo   - 已安装 Python（系统 PATH）
if exist ".venv\Scripts\python.exe" echo   - 已存在 .venv 虚拟环境
echo.
echo   请选择使用哪种方式安装（支持任意一种）：
echo     1) Conda 环境（推荐；自动创建 transvideo 环境并安装）
echo     2) 项目内 .venv 虚拟环境（自动创建，依赖系统 Python）
echo     3) 系统 Python（直接安装到当前 Python，需 Python 3.10+）
echo.
set /p ENVCHOICE=请输入 1、2 或 3 后回车 [默认 1]：
if "!ENVCHOICE!"=="" set "ENVCHOICE=1"
if "!ENVCHOICE!"=="2" goto :env_venv
if "!ENVCHOICE!"=="3" goto :env_sys
goto :env_conda

:env_conda
where conda >nul 2>nul
if errorlevel 1 (
  echo [错误] 未安装 conda，无法使用方案 1。请重跑脚本选择方案 2 或 3。
  goto :end
)
echo 创建并激活 conda 环境 transvideo ...
call conda create -n transvideo python=3.11 -y
if errorlevel 1 ( echo [错误] 创建 conda 环境失败 & goto :end )
call conda activate transvideo
if errorlevel 1 ( echo [错误] 激活 conda 环境失败 & goto :end )
set "PYTHON=%CONDA_PREFIX%\python.exe"
goto :env_done

:env_venv
where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 python，无法创建 .venv。请先安装 Python 3.10+：https://www.python.org/downloads/
  goto :end
)
echo 创建 .venv 虚拟环境 ...
python -m venv .venv
if errorlevel 1 ( echo [错误] 创建 .venv 失败 & goto :end )
set "PYTHON=%CD%\.venv\Scripts\python.exe"
goto :env_done

:env_sys
where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 python。请先安装 Python 3.10+：https://www.python.org/downloads/
  goto :end
)
set "PYTHON=python"
goto :env_done

:env_done
echo.
echo   已选定 Python：!PYTHON!
(echo !PYTHON!)> .pyenv.txt
echo   （已保存到 .pyenv.txt，之后双击 start.bat 会自动读取此路径启动）

REM ========== 3. 安装依赖 ==========
echo.
echo [3/7] 安装依赖（需要几分钟，请耐心等待）...
"!PYTHON!" -m pip install --upgrade pip
echo   正在安装 PyTorch（CUDA 12.4，约 2.5GB，需下载）...
"!PYTHON!" -m pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 ( echo [错误] PyTorch 安装失败，请检查网络或代理 & goto :end )
echo   正在安装项目依赖（ASR/说话人识别/分离/翻译/Web UI）...
"!PYTHON!" -m pip install -r requirements.txt
if errorlevel 1 ( echo [错误] 依赖安装失败 & goto :end )
echo   [OK] 依赖安装完成

REM ========== 4. 配置 IndexTTS 2.5 ==========
echo.
echo [4/7] 配置 IndexTTS 2.5（本地语音克隆，使用独立环境）...
if not exist "index-tts" (
  echo   正在克隆 IndexTTS 仓库 ...
  git clone https://github.com/index-tts/index-tts.git
  if errorlevel 1 ( echo [错误] 克隆失败（国内网络可能需要代理） & goto :end )
)
if not exist "index-tts\.venv" (
  echo   正在创建 IndexTTS 独立环境 ...
  "!PYTHON!" -m venv "index-tts\.venv"
)
echo   正在安装 IndexTTS 依赖（PyTorch 2.8 CUDA 12.8）...
"index-tts\.venv\Scripts\python.exe" -m pip install --upgrade pip
"index-tts\.venv\Scripts\python.exe" -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 (
  echo   [警告] 指定版本安装失败，尝试默认版本 ...
  "index-tts\.venv\Scripts\python.exe" -m pip install torch torchaudio
)
"index-tts\.venv\Scripts\python.exe" -m pip install -r "index-tts\requirements.txt"
echo   [OK] IndexTTS 环境就绪（权重在下一步下载）

REM ========== 5. 下载模型 ==========
echo.
echo [5/7] 下载 AI 模型 ...
echo   注意：pyannote 说话人识别模型需先在 HuggingFace 网页接受许可
echo   （打开 https://huggingface.co/pyannote/speaker-diarization-3.1 点 Accept，
echo    同理还有 segmentation-3.0、wespeaker-voxceleb-resnet34-LM）
echo.
set /p HF_TOKEN=请输入 HuggingFace Token（https://huggingface.co/settings/tokens 创建）：
set "HF_TOKEN=!HF_TOKEN!"
"!PYTHON!" scripts\download_models.py
if errorlevel 1 ( echo [警告] 模型下载有失败项，请看上方提示 & set "WARN=1" )

REM ========== 6. 生成 .env ==========
echo.
echo [6/7] 生成配置文件 ...
if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo   已生成 .env（下一步用记事本打开填写）
) else (
  echo   .env 已存在，跳过。
)

echo.
echo ============================================================
echo   安装完成！
echo ============================================================
echo   下一步：
echo   1. 用记事本打开 .env，填写：
echo      - OPENAI_API_KEY ：翻译用的大模型 API Key
echo      - OPENAI_BASE_URL：API 地址
echo      - TTS_ENGINE     ：edge=免费配音（无需GPU） / index=本地克隆（需GPU）
echo   2. 以后每次使用：双击 start.bat（自动读取 .pyenv.txt 找到 Python 并启动）
echo   3. 浏览器打开 http://127.0.0.1:7860
echo.
echo   详细说明见 README.md
echo ============================================================
pause
:end
endlocal
