# AI 视频翻译与多说话人配音系统 —— 项目计划 (PROJECT_PLAN)

> 目标机器：RTX 4060 Ti 16GB / i9-14900KF / 48GB RAM / Windows 11 (+ WSL2 Ubuntu)
> 原则：本地运行、不依赖付费 API、按阶段加载/释放 GPU、断点续跑、先 MVP 后增强。

---

## 0. 环境扫描结果（实测，2026-08-19）

| 项目 | 实测值 | 结论 |
|---|---|---|
| GPU | NVIDIA RTX 4060 Ti, **16380 MiB**, driver 610.47 (CUDA UMD 13.3) | ✅ 满足 16GB |
| CUDA 编译工具 | nvcc **12.4** (V12.4.99) | ✅ 有 toolkit |
| Python | base = **3.13.9** (anaconda)；conda envs 均为 **3.11.15** | ⚠️ 3.13 生态兼容性差，**用 3.11** |
| PyTorch | `pytorch`/`qwen` = 2.13.0+cu126；`soulx` = 2.5.1+cu124；`torch28` = 2.8.0+cu126；**全部 `cuda_available=True`** | ✅ |
| base 环境 torch | import 时 **OMP Error #15**（libiomp5md.dll 重复加载） | ⚠️ 不要用 base 跑 ML |
| FFmpeg | **4.3.1**（2020，偏旧） | ⚠️ 可用但旧，建议后续升级 |
| WSL | WSL2 `ubuntu` 运行中，kali/arch 停止 | ✅ 可选 Linux 路径 |
| 磁盘 | C: 1393 GB 空闲 / D: 984 GB 空闲 | ✅ 充足 |
| **GPU 当前占用** | **15282 / 16380 MiB 已用，仅剩 828 MiB** | 🔴 **必须处理，见 §9** |

### 0.1 GPU 占用根因（已定位）
- 进程 PID 41920 = `python.exe tts_server.py`，父进程 39336 为 `index-tts\.venv\Scripts\python.exe tts_server.py`。
- 脚本位于 `C:\Users\12439\agent project\kimi work\Soux-Duplug\webapp\tts_server.py`，监听 `127.0.0.1:8002`。
- 即：**你在跑的 IndexTTS TTS 服务器（SoulX-Duplug webapp）长期占用了几乎全部显存**。运行本项目前必须把它停掉。

### 0.2 已下载的可用模型（免重复下载，优先复用）
HF 缓存 `C:\Users\12439\.cache\huggingface\hub` 已存在：
- **faster-whisper**：`Systran/faster-whisper-{base,small,medium,large-v3}` ✅
- **翻译**：`Helsinki-NLP/opus-mt-{en-zh,zh-en}` ✅
- **SoulX**：`Soul-AILab/SoulX-Duplug-0.6B`、`SoulX-Podcast-1.7B` ✅
- **IndexTTS**：`IndexTeam/IndexTTS-2`、`IndexTeam/IndexTTS-2.5`（且 `checkpoints_25/` 全量权重已就位，`.venv` 已可用）✅
- 其它：`THUDM/glm-4-voice-tokenizer`、若干 bert 模型。

---

## 1. 技术栈最终推荐（一句话）

> **FFmpeg**（音视频 I/O）→ **faster-whisper large-v3**（ASR）→ **pyannote.audio 3.1**（说话人）→ **Demucs htdemucs**（人声/背景分离）→ **翻译**（第三方 API LLM 上下文翻译为主，opus-mt/NLLB 离线兜底）→ **IndexTTS 2.5**（多说话人配音）→ **自研 Aligner**（时长对齐）→ **FFmpeg**（混音 + 封装）。

全部模块化、可独立运行、按阶段加载释放显存。**不采用 SoulX-Transcriber 全家桶**（其整合度高但依赖重、不便单阶段调试，且你的 SoulX 环境里连 pyannote/demucs 都没有，只装了 faster-whisper + onnxruntime；改为自建轻量管道，按需借用其 Duplug 模型）。

---

## 2. 各模块模型选型对比

### 2.1 ASR（语音转文字）
| 项目 | faster-whisper large-v3 ✅首选 | FunASR Paraformer-zh / SenseVoice |
|---|---|---|
| 用途 | 多语言 ASR + 词级时间戳 | 中文为主的 ASR |
| 参数量 | ~1.5B（CT2 格式） | ~220M / ~230M |
| 预计显存 | fp16 ~3.2GB / int8 ~2.0GB | ~1-2GB |
| 推理速度 | 快（CTranslate2 + CUDA，RTX 4060 Ti 上 large-v3 约 0.1-0.2×实时） | 极快 |
| 优点 | 多语言（en/zh/ja/ko 等）、时间戳准、**权重已下载**、生态成熟 | 中文标点/口语化强 |
| 缺点 | 中文极长音频略弱于 Paraformer；幻觉少见 | 多语言能力弱，时间戳需额外处理 |
| 许可证 | 代码 MIT / 权重 MIT | Apache-2.0 |
| 是否适合 4060 Ti 16GB | ✅ 完全适合 | ✅ |

**结论**：影视多语言场景选 `faster-whisper large-v3`（已下载、通用、时间戳好）。中文为主的可选换 Paraformer/SenseVoice。

### 2.2 说话人识别（Diarization）
| 项目 | pyannote.audio 3.1 ✅首选 | SoulX-Duplug-0.6B（备选） |
|---|---|---|
| 用途 | 谁在何时说话（speaker-diarization-3.1 + segmentation-3.0） | 说话人分离/日志 |
| 参数量 | ~（pipeline） | 0.6B |
| 预计显存 | **~2-3GB（3.x 版）；⚠️ 4.x 版实测峰值 >9.5GB，必须锁 3.x** | ~2GB |
| 优点 | 行业标准、精度高、与 whisper 结合成熟 | **免 HF token（无 gating）**、你已下载 |
| 缺点 | 模型 gated，**需 HF token 并同意条款** | 精度/生态略弱于 pyannote |
| 许可证 | 代码 MIT / 权重 gated | 需查 SoulX 仓库 |
| 是否适合 | ✅（锁 `pyannote.audio==3.1.*`） | ✅ |

**结论**：首选 `pyannote.audio 3.1`；若无 HF token，用 SoulX-Duplug-0.6B 兜底。**务必锁 3.x，勿升 4.x（显存 6 倍回归）。**

### 2.3 人声 / 背景分离（Vocal Separation）
| 项目 | Demucs htdemucs ✅首选 | BS-RoFormer / MelBand-RoFormer（高质可选） | UVR/MDX-Net |
|---|---|---|---|
| 用途 | 人声 vs 伴奏/环境音 | 更高 SDR 的人声分离 | 多种 MDX 模型 |
| 参数量 | ~80M | 数十~上百 M | 视模型 |
| 预计显存 | ~2GB | ~2-4GB | ~1-3GB（ONNX） |
| 优点 | 成熟、MIT、稳定、长音频可切段 | 分离质量更高 | onnxruntime-gpu 你已装 |
| 缺点 | 音质略逊于 RoFormer 系 | 依赖稍多 | 结果碎片化、需自己拼 |
| 许可证 | MIT | MIT（AEmotionStudio/mdx23c 等） | 视模型 |
| 是否适合 | ✅ | ✅（空闲时可用） | ✅ |

**结论**：默认 `Demucs htdemucs`（稳、快、够用）；追求更高保真再切 BS-RoFormer。二者都轻松放进 16GB。

### 2.4 重叠语音分离（Speech Separation，高级）
| 项目 | SpeechBrain SepFormer ✅（触发式） | asteroid Conv-TasNet |
|---|---|---|
| 用途 | 多人同时说话 → 多路独立语音 | 同左 |
| 参数量 | ~26M（sepformer-libri2mix） | ~5M |
| 预计显存 | <1GB | <1GB |
| 优点 | 时域 SOTA 之一、预训练可直接用 | 轻量 |
| 缺点 | 只适合语音混合、对真实影视泛化有限 | 精度略低 |
| 许可证 | Apache-2.0 | MIT |
| 是否适合 | ✅ | ✅ |

**策略（不无脑全量跑）**：用 pyannote 的 **overlap 区域**判断重叠；仅对重叠片段触发 SepFormer 分离，再分别 ASR。普通片段走 Diarization + ASR。

### 2.5 翻译（Translation）
> 支持两种后端：**离线本地模型** + **第三方 API（OpenAI 兼容）**，由配置切换。

| 项目 | 第三方 API LLM ✅上下文翻译首选 | Helsinki opus-mt en↔zh（离线） | NLLB-200-600M（离线多语） | Qwen2.5-7B-4bit（本地 LLM，可选） |
|---|---|---|---|---|
| 用途 | 上下文/语气/专名/角色一致的影视对白翻译 | en↔zh 字幕翻译（离线） | ja/ko/es/ar→zh 等（离线） | 本地上下文翻译 |
| 参数量 | 远端，不占本地 | ~74M/对 | 600M | 7B（4bit ~5-6GB） |
| 预计显存 | **0** | ~0.3GB（可 CPU） | ~1.5GB | ~5-6GB |
| 优点 | 质量最高、上下文窗口、**显存 0 占用**、OpenAI 兼容 | **已下载**、快、MIT、免费离线 | 覆盖 200 语言 | 数据不出本机 |
| 缺点 | 需 API key、按量计费、数据出网 | 逐句、无上下文 | **权重 CC-BY-NC-4.0（禁商用）** | 慢、占显存 |
| 许可证 | 由服务商定义 | 代码/权重 MIT | CC-BY-NC-4.0 ⚠️ | Apache-2.0（权重另有条款） |
| 是否适合 | ✅ 最省显存 | ✅ | ✅ | ✅（单独加载） |

**结论**：
- **默认推荐：第三方 API（OpenAI 兼容，如 DeepSeek/OpenAI/通义等）** —— 上下文翻译质量最好，且完全不占本地显存，最契合 16GB 机器。
- 离线兜底：opus-mt（en↔zh 已就绪）+ NLLB-600M 补多语。
- `translator.py` 做成可插拔后端：`api`（OpenAI 兼容，`base_url/api_key/model` 走 `config`）+ `local`（opus-mt/NLLB）+ `llm_local`（Qwen，可选）。

### 2.6 TTS 配音
| 项目 | IndexTTS 2.5 ✅首选 | CosyVoice2 / F5-TTS（备选） |
|---|---|---|
| 用途 | 零样本克隆 + 多说话人配音 | 补充韩语等 IndexTTS 不支持的语言 |
| 参数量 | ~0.8B（GPT backbone） | 视模型 |
| 预计显存 | **~6GB**（README 官方） | ~4-6GB |
| 优点 | **已完整就绪（权重+venv 可用）**、zh/en/ja/es/ar、**`duration_factor` 0.5–2.0× 语速控制（对齐关键）**、克隆只需一句参考 | 开源生态广 |
| 缺点 | **不支持韩语**；bilibili 自定义许可证（见下） | 需重新下载/配置 |
| 许可证 | **bilibili Model Use License**（>1 亿 MAU 或年收入 >10 亿 RMB 需单独授权；不得用输出训练其它模型）| 各自条款 |
| 是否适合 | ✅（约 6GB，完美） | ✅ |

**结论**：TTS 用 **IndexTTS 2.5**（复用你的现成环境）。目标语言含韩语时，该句改用 CosyVoice2/F5-TTS。**注意许可证与克隆同意的合规**。

---

## 3. 显存预算（按阶段加载/释放，永不并发大模型）

| 阶段 | 模型 | 峰值显存 | 备注 |
|---|---|---|---|
| 音频提取 | FFmpeg | 0 | CPU |
| 人声分离 | Demucs htdemucs | ~2GB | 用后 `del + empty_cache` |
| Diarization | pyannote 3.1 | ~3GB | 用后释放 |
| ASR | faster-whisper large-v3 | ~3.2GB | 用后释放 |
| 翻译 | 第三方 API（0 显存）或 opus-mt / NLLB-600M | 0（API）/ ≤1.5GB（本地） | API 首选 |
| TTS | IndexTTS 2.5 | ~6GB | **单次峰值最大项** |
| 对齐/混音 | 无（纯 DSP） | 0 | librosa/soxr |

- **任意时刻只有一个大模型驻留**，峰值 ~6GB < 16GB，留足余量。
- GPU 管理统一封装 `app/utils/gpu.py`：`load(model)->cuda` / `release(model)` + `torch.cuda.empty_cache()`。
- 必要时：FP16 默认、INT8 备选（仅 ASR）、4-bit（仅可选 Qwen 翻译）、chunk 推理（长音频）。

---

## 4. 系统架构

```
Video ──FFmpeg──▶ Audio(WAV 16k/44.1k)
                    │
        ┌───────────┴───────────┐
   Vocal Track            Background Track (Demucs)
        │                       │
   [overlap?] ──否──▶ Diarization(pyannote)
        │是                    │
   SpeechSep(SepFormer)        │
        │                       │
   ASR(faster-whisper) ────────▶ 带时间戳+speaker 的字幕(JSON/SRT/ASS)
        │                       │
   Translation(opus-mt/NLLB/Qwen)
        │
   每说话人固定 Voice ← 参考音频(IndexTTS 克隆)
        │
   TTS(IndexTTS 2.5, duration_factor)
        │
   Alignment(语速+静音+time-stretch+字幕微调, 不覆盖下一句)
        │
        └───────────────┬───────┘
                  Audio Mixing(原人声降低 + Background + 新配音)
                        │
                    FFmpeg 封装 ──▶ Final Video(不重编码视频)
```

### 目录结构（工作目录即项目根 `...\deepseek\translate`）
```
translate/
├── app/
│   ├── video/        extractor.py, muxer.py
│   ├── separation/   vocal_separator.py, speech_separator.py
│   ├── diarization/  speaker_diarization.py
│   ├── asr/          transcriber.py
│   ├── translation/  translator.py
│   ├── tts/          synthesizer.py
│   ├── alignment/    aligner.py
│   ├── mixing/       audio_mixer.py
│   ├── pipeline/     pipeline.py
│   └── utils/        gpu.py, audio.py, workspace.py, logging.py
├── models/           (缓存/符号链接)
├── config/           config.yaml, speakers.yaml
├── scripts/          gen_test_video.py, download_models.py
├── tests/
├── outputs/
├── main.py
├── webui.py          (Gradio，可选)
├── requirements.txt
├── PROJECT_PLAN.md
└── README.md
```

**运行环境隔离（关键）**：
- **主管道 env**：新建 conda `vt`（Python 3.11）+ `requirements.txt`（faster-whisper、pyannote 3.1、demucs、librosa、transformers、gradio…）。
- **IndexTTS**：**复用你现成的 `index-tts\.venv`**（Python 3.11.13 / torch 2.8.0+cu128），通过子进程调用其 `infer_v2_5.py`，避免与主管道依赖冲突。

---

## 5. 安装步骤（概要，Phase 1 时细化）

1. **释放 GPU**：停止 `tts_server.py`（:8002）。
2. 主环境：`conda create -n vt python=3.11` → `pip install -r requirements.txt`（torch 选 cu124/cu126）。
3. 复用已下载模型：设 `HF_HOME` 指向现有缓存，或软链到 `models/`。
4. IndexTTS：直接复用 `C:\Users\12439\agent project\public\index-tts`（`checkpoints_25/` + `.venv`）。
5. pyannote：`HF_TOKEN` 配置（Phase 2 需要）。

---

## 6. 开发阶段（严格顺序，每阶段实测后进入下一阶段）

| Phase | 内容 | 代码 | 验证标准 |
|---|---|---|---|
| **1** | 视频→音频→ASR→时间戳字幕 | ✅ | 30s 测试视频字幕准确、时间戳正确 |
| **2** | Speaker Diarization | ✅ | 多人对话 speaker 正确 |
| **3** | Vocal Separation | ✅ | 背景音乐/环境音可保留 |
| **4** | Translation | ✅（API + local） | 英→中字幕质量 |
| **5** | TTS | ✅（IndexTTS 批量） | 每 speaker 固定 Voice |
| **6** | Alignment | ✅ | 不覆盖下一句、时长匹配 |
| **7** | Mixing | ✅ | Background + 新配音融合 |
| **8** | 最终封装 | ✅ | 输出完整配音视频、不重编码视频 |

> ✅ **全流程（Phase 1–8）已端到端实测通过**（30s 双说话人测试视频，中文→英文配音）：
> 转写逐字正确 → pyannote 分出 2 说话人 → Demucs 分离人声/背景 → opus-mt 翻译 → IndexTTS 逐说话人合成英文 → 对齐到原时间槽 → 混音 → 封装（视频流 copy 不重编码）。
> 最终产物：`outputs/test_video/test_video_dubbed.mp4`。
> 关键修复：① 禁用 torch cuDNN（规避 faster-whisper/CT2 与 torch 同进程冲突）；② transformers 降到 4.49（torch 2.5 兼容 `.bin` 加载）。

---

## 7. 测试方案

1. **30s 合成测试视频**（`scripts/gen_test_video.py` 自动生成）：Speaker A 独白 / Speaker B 独白 / A-B 对话 / A-B 短暂重叠 / 背景音乐 / 环境音。
2. 逐阶段跑该视频，检查 JSON/SRT/ASS、时长、说话人、混音效果。
3. 通过后 → 5 分钟视频 → 30 分钟+ 长视频（验证 chunk/断点续跑/显存稳定）。
4. 阶段产物持久化到 `outputs/<video_name>/`，支持 `--stage` 单阶段重跑。

---

## 8. 风险与应对

| 风险 | 应对 |
|---|---|
| GPU 被 `tts_server.py` 占满 | 停掉该进程；本项目进程化串行加载模型 |
| pyannote gated 需 token | 用 SoulX-Duplug-0.6B 兜底；或引导配置 HF_TOKEN |
| 中文 TTS 语速导致时长错位 | IndexTTS `duration_factor` + 静音填充 + soxr time-stretch + 字幕微调 |
| 长视频内存/显存 | chunk 处理 + 中间结果落盘 + 断点续跑 |
| numpy/依赖冲突 | 主环境锁 numpy<2；IndexTTS 独立 venv |
| FFmpeg 4.3.1 过旧 | MVP 先用；必要时下载静态新版 FFmpeg |
| 韩语等 IndexTTS 不支持 | 该语言句切 CosyVoice2/F5-TTS |
| 许可证（IndexTTS/NLLB） | 记录并遵守；商用前需单独评估 |

---

## 9. 当前状态 & 待办

1. ✅ GPU 已释放（`tts_server.py` 已停，空闲 ~13.7GB）。
2. ✅ 主环境 `vt`（克隆自 `soulx`）+ 测试视频 `test_video.mp4` 已就绪。
3. ⏸️ **Phase 1 实测暂停**：GPU 正在打游戏占用，等空闲后再跑。
4. 🟡 **pyannote HF token**：Phase 2 需要，届时请提供或选 SoulX 兜底。
5. 🟡 **翻译 API key**：Phase 4 需要（`VT_TRANSLATE_API_KEY` 环境变量），或改 `translation.backend=local`。

---

## 10. 替代方案（Plan B）

- 若 faster-whisper large-v3 在长片过慢 → 换 medium（~1.5GB，更快）。
- 若 Demucs 保真不足 → BS-RoFormer/MelBand-RoFormer。
- 若 pyannote 无 token → SoulX-Duplug-0.6B。
- 若需韩语 → CosyVoice2 / F5-TTS。
- 若想整体更省心 → 直接跑 WSL2 Ubuntu（Linux 生态更顺，但 IndexTTS 已在 Windows 配好，暂不迁移）。
