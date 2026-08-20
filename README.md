# PolyDub —— AI 多说话人视频翻译与配音系统

一个**本地运行**的视频翻译 + 多说话人自动配音系统。上传一个视频，自动完成：

> 视频 → 提取音频 → 人声/背景分离 → 说话人识别（含重叠）→ 逐人转写 → 大模型翻译 → 逐人配音（保留情感）→ 时长对齐 → 混音 → 字幕烧录 → 输出配音视频

典型场景：把一部**多人对话**的影视/游戏/访谈视频，自动翻译并配音成目标语言，同时**保留背景音乐、环境音，并让每个角色用不同的声音**。

---

## 🎬 效果预览

[preview/preview.mp4](preview/preview.mp4)

（示例：一个 5 分钟的 3 人中文对话视频 → 英文配音 + 英文字幕，音色按说话人区分）

---

## 🚀 快速开始（小白版，3 步）

1. **一键安装**：双击运行 `setup.bat`，脚本会自动创建 Python 环境、安装全部依赖、配置 IndexTTS 2.5、下载全部 AI 模型。只需按提示输入 HuggingFace Token。
2. **填写配置**：用记事本打开 `.env`，填入翻译用的 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`（可先留空，用本地离线翻译）。
3. **启动使用**：运行 `python webui.py`，浏览器打开 http://127.0.0.1:7860，上传视频或粘贴视频链接，选目标语言，点「一键全流程」。

> 手动安装方式见下方「安装」章节；下载视频遇到 cookie 问题见「下载 Cookie 配置」章节。

---

## ✨ 核心特性

- **多说话人识别**（pyannote.audio 3.1）：自动判断「谁在何时说话」，人数可手动指定或自动检测
- **重叠语音分离**（SepFormer）：两人/三人同时说话时，把混合音频分离成各自独立的纯净人声
- **逐人配音**：
  - **IndexTTS 2.5**（本地 GPU）：克隆原声、保留每句话的语气/情感
  - **edge-tts**（免费）：微软免费接口，无需 GPU，内置中/英/日/韩/西/阿全部音色，多说话人自动按性别分配不同音色
- **背景音乐保留**（Demucs）：人声与背景音乐/环境音分离，配音后背景完整保留
- **字幕烧录**：翻译字幕直接烧进画面，多人重叠说话时**上下分行、不同颜色**同屏显示（ASS）
- **断点续跑**：每个阶段中间结果落盘，失败/中断后可从断点继续，不重复计算
- **Web UI**（Gradio）：上传视频 / 粘贴 URL 下载 → 选语言 → 一键全流程或分阶段
- **视频下载**（yt-dlp）：支持 YouTube / TikTok 等，可在设置里配置 cookie

---

## 🧠 技术栈

| 模块 | 技术 | 说明 |
|---|---|---|
| 音视频处理 | FFmpeg | 音频提取、混音、封装、字幕烧录 |
| 人声/背景分离 | Demucs (htdemucs) | 分离人声轨与背景轨 |
| 说话人识别 | pyannote.audio 3.1 | 谁在何时说话（含重叠） |
| 重叠语音分离 | SpeechBrain SepFormer | 2 人 / 3 人同时说话分离 |
| 语音转文字 | faster-whisper (large-v3) | 本地多语言 ASR |
| 翻译 | OpenAI 兼容 API（可换任意大模型）+ 本地 opus-mt 兜底 | 上下文翻译，失败自动降级 |
| 配音 TTS | IndexTTS 2.5 / edge-tts | 语音克隆 / 免费合成 |
| 说话人匹配 | wespeaker 嵌入 | 分离出的音频流匹配回说话人 |
| Web UI | Gradio | 可视化操作 |

---

## 🔄 处理流程

```
Video ──FFmpeg──▶ Audio
                   │
        ┌──────────┴──────────┐
   人声轨(vocals)        背景轨(background)  ← Demucs
        │
   说话人识别(diarization)  ← pyannote（谁在何时说话）
        │
   逐人转写  ← 非重叠:切该段人声；重叠:SepFormer分离后再分别转写
        │
   翻译  ← 大模型 API（失败降级本地）
        │
   逐人配音  ← IndexTTS（克隆该人音色 + 该句情绪）/ edge-tts
        │
   时长对齐  ← 每句配音对齐到原时间槽（保留重叠）
        │
   混音  ← 背景轨 + 各人配音（重叠处叠加）
        │
   字幕烧录 + 封装  ← FFmpeg（h264 + 烧录翻译字幕）
        │
   Final Video
```

---

## 🚀 安装

> **推荐：直接双击 `setup.bat` 一键安装**（自动完成下方全部步骤，小白友好）。
> 以下为手动方式：

### 硬件要求
- NVIDIA GPU（推荐 ≥ 8GB 显存，16GB 更佳；纯 edge-tts 方案可不需 GPU）
- Python 3.10–3.11
- FFmpeg（已在 PATH）
- git、conda（setup.bat 会检查）

### 步骤（手动）

```bash
# 1. 创建环境
conda create -n transvideo python=3.11 -y
conda activate transvideo

# 2. 安装依赖
pip install -r requirements.txt
# PyTorch（CUDA 版，示例 cu124）
pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124

# 3. 安装 pyannote + demucs（说话人识别 + 人声分离）
pip install pyannote.audio==3.1.1 demucs "numpy<2"
# transformers 需降到 4.49（torch 2.5 兼容）
pip install "transformers==4.49.0"

# 4. 配置 .env（复制并填写）
#    - HF_TOKEN：HuggingFace token（下载 pyannote 需先接受其 gated 许可）
#    - OPENAI_API_KEY / OPENAI_BASE_URL：翻译用的大模型 API
```

> 完整依赖与配置见 `.env` 与 `config/config.yaml`。

---

## 📖 使用

### 命令行

```bash
# 一键全流程：中文视频 → 英文配音（自动检测说话人数）
python main.py --input 视频.mp4 --target-lang en --num-speakers auto

# 指定说话人数（重要：自动检测不准时手动指定效果更好）
python main.py --input 视频.mp4 --target-lang en --num-speakers 3

# 从 URL 下载后处理
python main.py --input "https://www.youtube.com/watch?v=xxx" --target-lang zh

# 分阶段调试（中间结果落盘，可断点续跑）
python main.py --input 视频.mp4 --stage transcribe
python main.py --input 视频.mp4 --stage diarize
python main.py --input 视频.mp4 --stage separate
python main.py --input 视频.mp4 --stage translate
python main.py --input 视频.mp4 --stage tts
python main.py --input 视频.mp4 --stage align
python main.py --input 视频.mp4 --stage mix
python main.py --input 视频.mp4 --stage mux
```

### Web UI

```bash
python webui.py   # 打开 http://127.0.0.1:7860
```

- **🎬 处理**：上传视频 / 粘贴 URL 下载 → 选原/目标语言、说话人数 → 一键全流程或分阶段
- **⚙️ 设置**：所有配置可视化编辑，鼠标悬停有说明，保存后同步到 `.env`

---

## 🍪 下载 Cookie 配置（YouTube / TikTok）

部分视频下载会失败，提示「需要登录 / 被风控 / 会员专享 / 年龄限制」。解决方法是给项目配置对应网站的登录 Cookie（很简单，两步）。

### 第 1 步：用浏览器插件导出 Cookie

1. 在 Chrome / Edge 安装扩展 **Cookie-Editor**（扩展商店搜索 "Cookie-Editor" 即可）。
2. 打开 **YouTube**（或 **TikTok**），**确保你已经登录**。
3. 点击浏览器右上角的 Cookie-Editor 图标 → 点右下角 **Export**（导出）→ 复制弹出的 JSON 内容（一段方括号开头的文本）。

### 第 2 步：粘贴到项目设置页

1. 启动 Web UI：`python webui.py` → 打开 http://127.0.0.1:7860
2. 进「⚙️ 设置」页 → 找到 **「下载 Cookie（YouTube / TikTok）」** 分区。
3. 把复制的 JSON 整段粘贴到对应输入框（YouTube 的贴 YouTube 框，TikTok 的贴 TikTok 框）。
4. 点 **「💾 保存所有设置」**。系统会自动把 Cookie 存到 `config/cookies/` 目录。

### 第 3 步：重新下载

回到「🎬 处理」页，重新粘贴视频链接下载即可。

### 常见问题（FAQ）

- **保存后下载还是失败？** 确认 Cookie 是从「已登录」的浏览器导出的；YouTube 建议用可正常观看该视频的账号（如美区/港区账号）。
- **TikTok 不想粘贴 JSON？** 可在设置页填 `TIKTOK_COOKIES_BROWSER=edge`（换成你用的浏览器名），自动读取浏览器已登录的 Cookie。
- **Cookie 会过期**，一般几周到几个月，失效后重新导出粘贴一次即可。
- **下载失败的提示里包含「需要登录 Cookie」**，说明本项目识别到需要登录，按上面的步骤配置即可。
- **手动方式**：也可直接把 Cookie-Editor 导出的内容保存为文件，并在 `.env` 里填 `YOUTUBE_COOKIES_FILE=你的文件路径`。

---

## ⚙️ 配置说明

### `.env`（运行时配置，可在 Web UI 设置页直接改）

| 分组 | 关键项 | 说明 |
|---|---|---|
| 引擎选择 | `ASR_ENGINE` / `TRANSLATE_ENGINE` / `TTS_ENGINE` | 选本地/云端/免费引擎 |
| OpenAI | `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `TRANSLATE_MODEL` | 翻译大模型配置，支持备选模型链降级 |
| TTS 音色 | `TTS_VOICE_<语言>_MALE/FEMALE` | edge-tts 音色池（已内置中/英/日/韩/西/阿全部音色） |
| IndexTTS | `INDEX_TTS_REPO_DIR` 等 | 本地 IndexTTS 目录与开关 |
| 网络 | `HTTP_PROXY` / `HTTPS_PROXY` | 访问 HuggingFace/YouTube 等的代理 |
| 下载 Cookie | `YOUTUBE_COOKIES_JSON` / `TIKTOK_COOKIES_JSON` | 粘贴 Cookie-Editor 导出的 JSON（保存后自动写入 `config/cookies/`） |
| 下载 Cookie | `YOUTUBE_COOKIES_FILE` / `TIKTOK_COOKIES_FILE` / `TIKTOK_COOKIES_BROWSER` | Cookie 文件路径 / TikTok 浏览器读取（高级） |
| HuggingFace | `HF_TOKEN` | 下载 pyannote 等 gated 模型必需 |

### `config/config.yaml`（管道参数）

- `diarization.num_speakers`：说话人数（`null`=自动，或指定数字）
- `separation`：人声分离模型、重叠分离模型
- `mixing.burn_subtitles`：是否烧录字幕
- `alignment.max_stretch`：对齐最大压缩比

---

## 📁 目录结构

```
transvideo/
├── app/
│   ├── video/        extractor / downloader / muxer（FFmpeg 封装、yt-dlp 下载）
│   ├── separation/   vocal_separator（Demucs）/ speech_separator（SepFormer）
│   ├── diarization/  speaker_diarization（pyannote）
│   ├── asr/          transcriber（faster-whisper）
│   ├── translation/  translator（API + 本地降级链）
│   ├── tts/          synthesizer（IndexTTS）/ edge_synthesizer（edge-tts）
│   ├── alignment/    aligner（时长对齐，允许重叠）
│   ├── mixing/       audio_mixer（混音）
│   ├── pipeline/     pipeline（编排）/ utterances（逐人转写+重叠分离）
│   └── utils/        env / gpu / subtitles / audio / workspace
├── config/           config.yaml / speakers.yaml / cookies/（粘贴的 cookie 文件）
├── scripts/          gen_test_video.py / download_models.py（一键下载模型）
├── preview/          预览视频
├── setup.bat         一键安装脚本（小白推荐）
├── main.py           命令行入口
├── webui.py          Web UI
└── outputs/          中间结果与成品（按视频名分目录）
```

---

## ⚠️ 注意事项 / 限制

1. **说话人数**：自动检测有时会把声线相近的两个人合并；若发现人数不对，用 `--num-speakers` 手动指定。
2. **重叠分离**：SepFormer 目前支持 2 人、3 人同时说话；4 人以上同瞬间重叠会退化为整体转写（现实中极少见）。
3. **对齐**：目标语言比原语言长时（如中文→英文），极短句可能轻微溢出；系统会用语速加速尽量收紧。
4. **模型许可证**：IndexTTS 使用 bilibili Model License（个人/小规模使用通常没问题，商用请自行评估）；NLLB 权重为非商用（CC-BY-NC）。使用时请遵守各模型许可。
5. **语音克隆合规**：使用 IndexTTS 克隆他人声音时，请确保已获得相关授权。

---

## 📄 许可证

本项目代码仅供学习交流。各内置模型（faster-whisper、pyannote、Demucs、SepFormer、IndexTTS、edge-tts 等）的许可证归其原作者所有，请分别遵守。
