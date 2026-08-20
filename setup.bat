@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title PolyDub 一键安装
color 0A

echo ============================================================
echo   PolyDub - AI 多说话人视频翻译与配音系统  一键安装
echo ============================================================
echo   本脚本将自动完成：
echo   1. 创建 Python 环境并安装全部依赖
echo   2. 配置 IndexTTS 2.5（本地语音克隆）
echo   3. 下载 AI 模型（ASR / 说话人识别 / 重叠分离 / 翻译）
echo   4. 生成 .env 配置文件
echo.
echo   全程需要联网，预计 20~60 分钟（取决于网速）。
echo.

REM ========== 1. 检查基础工具 ==========
echo [1/6] 检查基础工具 ...
set MISSING=0

where git >nul 2>nul
if errorlevel 1 (
  echo   [错误] 未安装 git。请先安装：https://git-scm.com/download/win （安装时一路下一步即可）
  set MISSING=1
) else (
  echo   [OK] git
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo   [警告] 未检测到 ffmpeg。最终合成视频需要它，请安装：
  echo           https://www.gyan.dev/ffmpeg/builds/ （下载 release 版，解压后把 bin 目录加进 PATH）
) else (
  echo   [OK] ffmpeg
)

where conda >nul 2>nul
if errorlevel 1 (
  echo   [错误] 未安装 conda。请先安装 Miniconda：https://docs.conda.io/en/latest/miniconda.html
  set MISSING=1
) else (
  echo   [OK] conda
)

if "%MISSING%"=="1" (
  echo.
  echo 请先安装缺失的工具，再运行本脚本。
  goto :end
)

REM ========== 2. 创建环境 ==========
echo.
echo [2/6] 创建 Python 3.11 环境 transvideo ...
call conda create -n transvideo python=3.11 -y
if errorlevel 1 (
  echo   [错误] 创建 conda 环境失败。
  goto :end
)
call conda activate transvideo
echo   [OK] 环境 transvideo 已激活

REM ========== 3. 安装主依赖 ==========
echo.
echo [3/6] 安装 PyTorch + 项目依赖（需几分钟，请耐心等待）...
echo   正在安装 PyTorch（CUDA 12.4，约 2.5GB）...
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 goto :end
echo   正在安装项目依赖...
pip install -r requirements.txt
if errorlevel 1 goto :end
pip install pyannote.audio==3.1.1 demucs "numpy<2"
if errorlevel 1 goto :end
pip install "transformers==4.49.0"
if errorlevel 1 goto :end
echo   [OK] 主依赖安装完成

REM ========== 4. 配置 IndexTTS 2.5 ==========
echo.
echo [4/6] 配置 IndexTTS 2.5（本地语音克隆，使用独立环境）...
if not exist "index-tts" (
  echo   正在克隆 IndexTTS 仓库...
  git clone https://github.com/index-tts/index-tts.git
  if errorlevel 1 (
    echo   [错误] 克隆 IndexTTS 失败（国内网络可能需要代理）。
    echo   可手动执行：git clone https://github.com/index-tts/index-tts.git
    goto :end
  )
)
cd index-tts
if not exist ".venv" (
  python -m venv .venv
)
call .venv\Scripts\activate
echo   正在安装 IndexTTS 依赖（PyTorch 2.8 CUDA 12.8）...
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 (
  echo   [警告] 指定版本安装失败，尝试默认版本...
  pip install torch torchaudio
)
pip install -r requirements.txt
cd ..
echo   [OK] IndexTTS 环境就绪（权重在下一步下载）

REM ========== 5. 下载模型 ==========
echo.
echo [5/6] 下载 AI 模型 ...
echo   注意：pyannote 说话人识别模型需要在 HuggingFace 网页先接受许可
echo   （打开 https://huggingface.co/pyannote/speaker-diarization-3.1 页面点 Accept，
echo    同理还有 segmentation-3.0、wespeaker-voxceleb-resnet34-LM）
echo.
set /p HF_TOKEN=请输入 HuggingFace Token（https://huggingface.co/settings/tokens 创建）：
set HF_TOKEN=%HF_TOKEN%
python scripts/download_models.py
if errorlevel 1 (
  echo   [警告] 模型下载有失败项，请查看上方提示（gated 模型需先接受许可 / 代理问题）。
)

REM ========== 6. 生成 .env ==========
echo.
echo [6/6] 生成配置文件 ...
if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo   已生成 .env（下一步需要用记事本打开填写）
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
echo      - HTTP_PROXY / HTTPS_PROXY：国内访问 HuggingFace/YouTube 的代理（可选）
echo   2. 启动 Web UI：
echo      conda activate transvideo
echo      python webui.py
echo      浏览器打开 http://127.0.0.1:7860
echo   3. 上传视频 / 粘贴 URL，选语言，一键处理
echo.
echo   详细说明见 README.md
echo ============================================================
pause

:end
endlocal
