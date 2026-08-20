"""设置页面的配置项 Schema 与值转换。

每个配置项：(key, label, type, choices, desc)
  type: text | password | choice | checkbox | number
  desc: 小白友好的悬停说明
"""

# (key, label, type, choices, desc)
SETTINGS_SECTIONS = [
    ("引擎选择", [
        ("ASR_ENGINE", "语音识别引擎（ASR）", "choice",
         ["faster-whisper", "whisper-api"],
         "识别视频里说了什么。faster-whisper=本地免费（首次会自动下载模型）；whisper-api=云端接口（需 OpenAI Key）。推荐本地。"),
        ("TRANSLATE_ENGINE", "翻译引擎", "choice",
         ["openai", "local", "ollama", "google", "mymemory"],
         "把字幕翻译成目标语言。openai=调用大模型 API（质量最好，需 Key）；local=本地离线翻译（免费）；ollama=本地 Ollama 大模型；google/mymemory=免费在线接口。"),
        ("TTS_ENGINE", "配音引擎（TTS）", "choice",
         ["index", "edge", "azure"],
         "把翻译后的文字合成语音。index=本地 IndexTTS（克隆原声、保留情感，需 GPU）；edge=微软免费接口（无需 Key，最省事）；azure=微软云 TTS（需 Key，质量更好）。"),
    ]),
    ("路径", [
        ("FFMPEG_PATH", "FFmpeg 路径", "text", None,
         "ffmpeg 可执行文件路径，用于音视频处理。"),
        ("FFPROBE_PATH", "FFprobe 路径", "text", None,
         "ffprobe 可执行文件路径，用于读取视频信息。"),
        ("OUTPUT_DIR", "输出目录", "text", None,
         "最终成品的保存目录。"),
        ("WORK_DIR", "工作目录", "text", None,
         "处理过程中的中间文件目录（可随时删除）。"),
    ]),
    ("OpenAI 配置", [
        ("OPENAI_API_KEY", "API Key", "password", None,
         "OpenAI 兼容接口的密钥。填了之后翻译用大模型 API；留空则自动降级到本地/免费方案。"),
        ("OPENAI_BASE_URL", "接口地址（Base URL）", "text", None,
         "OpenAI 兼容服务地址，可填 DeepSeek、通义等任意兼容服务。"),
        ("WHISPER_MODEL", "云端转写模型", "text", None,
         "ASR 引擎选 whisper-api 时使用的云端模型名（如 whisper-1）。"),
        ("TRANSLATE_MODEL", "翻译模型", "text", None,
         "翻译使用的大模型名称（翻译引擎选 openai 时生效）。"),
        ("TRANSLATE_MODEL_FALLBACKS", "备选模型链", "text", None,
         "逗号分隔的备用模型，主模型调用失败时按顺序自动重试。"),
        ("FASTER_WHISPER_MODEL", "本地转写模型", "choice",
         ["tiny", "base", "small", "medium", "large-v3"],
         "本地 faster-whisper 模型大小。越大越准但越慢、越占显存；4060Ti 16GB 推荐 large-v3。"),
    ]),
    ("Azure TTS", [
        ("AZURE_SPEECH_KEY", "Azure 语音 Key", "password", None,
         "微软 Azure 语音服务密钥（配音引擎选 azure 时必需）。"),
        ("AZURE_SPEECH_REGION", "Azure 区域", "text", None,
         "Azure 服务区域，如 eastasia（东亚）。"),
    ]),
    ("Ollama 本地模型", [
        ("OLLAMA_URL", "Ollama 地址", "text", None,
         "本地 Ollama 服务地址（翻译引擎选 ollama 时生效）。"),
        ("OLLAMA_MODEL", "Ollama 模型", "text", None,
         "Ollama 模型名，如 qwen2.5:7b。"),
        ("OLLAMA_BATCH_SIZE", "批大小", "number", None,
         "Ollama 每次批量翻译的句子数量，越大越快但越占内存。"),
        ("OLLAMA_TIMEOUT", "超时（秒）", "number", None,
         "Ollama 单次请求超时时间。"),
    ]),
    ("TTS 配音音色", [
        ("TTS_VOICE_ZH", "中文默认音色", "text", None,
         "中文的默认音色（视频只有一位说话人时使用）。"),
        ("TTS_VOICE_EN", "英文默认音色", "text", None,
         "英文的默认音色（视频只有一位说话人时使用）。"),
        ("TTS_VOICE_JA", "日文默认音色", "text", None,
         "日文的默认音色（视频只有一位说话人时使用）。"),
        ("TTS_VOICE_KO", "韩文默认音色", "text", None,
         "韩文的默认音色（视频只有一位说话人时使用）。"),
        ("TTS_RATE", "语速", "text", None,
         "配音语速，如 +10% 加快、-5% 减慢。"),
        ("TTS_VOLUME", "音量", "text", None,
         "配音音量，如 +0%、-10%。"),
        ("EDGE_TTS_AUTO_VOICE", "edge-tts 多说话人自动分配音色", "checkbox", None,
         "使用 edge-tts 且视频有多位说话人时：开启=按性别从下方男/女音色池给每人分配不同音色；关闭=所有人用同一个默认音色。（仅 TTS_ENGINE=edge 时生效）"),
        ("TTS_VOICE_ZH_MALE", "中文男声音色池", "text", None,
         "edge-tts 多说话人时男声使用，逗号分隔多个音色，按说话人顺序依次分配（如 zh-CN-YunxiNeural,zh-CN-YunjianNeural）。"),
        ("TTS_VOICE_ZH_FEMALE", "中文女声音色池", "text", None,
         "edge-tts 多说话人时女声使用，逗号分隔多个音色（如 zh-CN-XiaoxiaoNeural,zh-CN-XiaoyiNeural）。"),
        ("TTS_VOICE_EN_MALE", "英文男声音色池", "text", None,
         "edge-tts 多说话人时英文男声使用，逗号分隔（如 en-US-GuyNeural,en-US-ChristopherNeural）。"),
        ("TTS_VOICE_EN_FEMALE", "英文女声音色池", "text", None,
         "edge-tts 多说话人时英文女声使用，逗号分隔（如 en-US-JennyNeural,en-US-AriaNeural）。"),
        ("TTS_VOICE_JA_MALE", "日文男声音色池", "text", None,
         "edge-tts 多说话人时日文男声使用，逗号分隔（如 ja-JP-KeitaNeural,ja-JP-DaichiNeural）。"),
        ("TTS_VOICE_JA_FEMALE", "日文女声音色池", "text", None,
         "edge-tts 多说话人时日文女声使用，逗号分隔（如 ja-JP-NanamiNeural,ja-JP-AyakaNeural）。"),
        ("TTS_VOICE_KO_MALE", "韩文男声音色池", "text", None,
         "edge-tts 多说话人时韩文男声使用，逗号分隔（如 ko-KR-InJoonNeural,ko-KR-HyunsuNeural）。"),
        ("TTS_VOICE_KO_FEMALE", "韩文女声音色池", "text", None,
         "edge-tts 多说话人时韩文女声使用，逗号分隔（如 ko-KR-SunHiNeural）。"),
        ("TTS_VOICE_ES_MALE", "西语男声音色池", "text", None,
         "edge-tts 多说话人时西班牙语男声使用，逗号分隔（已内置全部可用音色）。"),
        ("TTS_VOICE_ES_FEMALE", "西语女声音色池", "text", None,
         "edge-tts 多说话人时西班牙语女声使用，逗号分隔（已内置全部可用音色）。"),
        ("TTS_VOICE_AR_MALE", "阿语男声音色池", "text", None,
         "edge-tts 多说话人时阿拉伯语男声使用，逗号分隔（已内置全部可用音色）。"),
        ("TTS_VOICE_AR_FEMALE", "阿语女声音色池", "text", None,
         "edge-tts 多说话人时阿拉伯语女声使用，逗号分隔（已内置全部可用音色）。"),
    ]),
    ("IndexTTS 2", [
        ("INDEX_TTS_REPO_DIR", "项目目录", "text", None,
         "IndexTTS 代码项目所在目录。"),
        ("INDEX_TTS_MODEL_DIR", "模型目录", "text", None,
         "IndexTTS 模型权重所在目录。"),
        ("INDEX_TTS_REF_AUDIO", "默认参考音频", "text", None,
         "默认参考音频路径；留空则自动从原视频里为每个说话人提取一段声音作参考（效果更好）。"),
        ("INDEX_TTS_USE_FP16", "FP16 半精度", "checkbox", None,
         "半精度推理，省一半显存、速度更快，推荐开启。"),
        ("INDEX_TTS_USE_DEEPSPEED", "DeepSpeed", "checkbox", None,
         "DeepSpeed 加速（Windows 安装较麻烦，能装上可加速）。"),
        ("INDEX_TTS_USE_ACCEL", "GPT 加速引擎", "checkbox", None,
         "GPT 部分加速（需要 flash-attn/triton，安装成功才有用）。"),
        ("INDEX_TTS_USE_TORCH_COMPILE", "torch.compile", "checkbox", None,
         "对语音解码部分做 torch.compile 编译加速。"),
        ("INDEX_TTS_USE_CUDA_KERNEL", "CUDA 内核", "checkbox", None,
         "使用自定义 CUDA 内核进一步加速（部分环境有效）。"),
    ]),
    ("字幕配置", [
        ("SUBTITLE_STYLE", "字幕样式", "choice", ["single", "double"],
         "single=单行字幕；double=双行字幕（YouTube 风格黑底白字）。"),
        ("SUBTITLE_FONT", "字体", "text", None,
         "字幕字体名称（如 Arial、Microsoft YaHei）。"),
        ("SUBTITLE_FONTSIZE", "字号", "number", None,
         "字幕字号，越大字越大。"),
        ("SUBTITLE_PRIMARY_COLOR", "主色", "text", None,
         "字幕文字颜色（ASS 格式 &HBBGGRR，如 &H00FFFFFF 白色）。"),
        ("SUBTITLE_OUTLINE_COLOR", "描边色", "text", None,
         "字幕描边/阴影颜色（如 &H00000000 黑色）。"),
        ("SUBTITLE_OUTLINE_WIDTH", "描边宽度", "number", None,
         "描边粗细，越大越明显。"),
        ("SUBTITLE_MARGIN_V", "垂直边距", "number", None,
         "字幕距离画面底部的距离。"),
        ("SUBTITLE_MAX_WIDTH_PERCENT", "最大宽度占比", "number", None,
         "单行字幕允许的最大宽度（0~1，超宽自动换行）。"),
        ("SUBTITLE_MAX_LINES", "最大行数", "number", None,
         "字幕最多显示几行。"),
        ("SUBTITLE_OVERFLOW_MODE", "超长字幕处理", "choice", ["split", "truncate"],
         "一句太长时怎么办：split=拆成多条依次显示（不丢字）；truncate=直接截断。"),
    ]),
    ("音频配置", [
        ("AUDIO_KEEP_ORIGINAL", "保留原声", "checkbox", None,
         "是否保留原视频的人声。关闭=尽量去掉原人声，只留新配音；开启=原声与配音叠加。"),
        ("AUDIO_ORIGINAL_VOLUME", "原声音量", "number", None,
         "保留原声时的音量比例（0~1，0.15 左右比较自然）。"),
        ("SEGMENT_SENTENCE_ALIGN", "句子对齐断句", "checkbox", None,
         "把结尾没说完的残句移入下一片段，让每段都是完整句子，翻译更连贯。"),
    ]),
    ("Google 翻译", [
        ("GOOGLE_TRANSLATE_URL", "接口地址", "text", None,
         "Google 免费翻译接口地址（翻译引擎选 google 时生效）。"),
    ]),
    ("网络配置", [
        ("HTTP_PROXY", "HTTP 代理", "text", None,
         "HTTP 代理地址。访问 HuggingFace、YouTube 等海外服务时使用（如 http://127.0.0.1:7897）。"),
        ("HTTPS_PROXY", "HTTPS 代理", "text", None,
         "HTTPS 代理地址，一般与 HTTP 代理相同。"),
        ("NETWORK_PROXY", "通用代理", "text", None,
         "通用代理地址（部分工具读取该变量）。"),
        ("NETWORK_TIMEOUT", "超时（秒）", "number", None,
         "网络请求超时时间。"),
        ("TIKTOK_COOKIES_BROWSER", "TikTok Cookie 浏览器", "text", None,
         "下载 TikTok 时从哪个浏览器读取登录 cookie（如 edge），避免被风控。"),
    ]),
    ("人声分离 & 其他", [
        ("SEPARATE_VOCALS", "人声分离", "checkbox", None,
         "是否把人声和背景音乐/环境音分开。分离后背景音乐可完整保留，原人声可被新配音替换。"),
        ("VOCAL_SEPARATION_MODEL", "分离模型", "text", None,
         "人声分离模型文件（如 UVR-MDX-NET-Voc_FT.onnx）。"),
        ("KEEP_NONSPEECH_ORIGINAL", "保留非语音原声", "checkbox", None,
         "保留笑声、咳嗽、音效等非语音原声。"),
        ("ACCOMPANIMENT_VOLUME", "伴奏音量", "number", None,
         "背景音乐/伴奏的音量比例（0~2，1 为原音量）。"),
        ("YOUTUBE_COOKIES_FILE", "YouTube Cookie 文件", "text", None,
         "YouTube 的 cookies.txt 文件路径（Netscape 格式，浏览器插件导出），下载受限/会员视频时使用。"),
    ]),
    ("HuggingFace", [
        ("HF_TOKEN", "HuggingFace Token", "password", None,
         "HuggingFace 访问令牌（设置页右上角头像→Settings→Access Tokens 创建）。下载 pyannote 说话人分离模型等 gated 模型时必需。"),
    ]),
]


def value_from_str(raw, typ):
    """把 .env 里的字符串转成对应类型的 UI 值。"""
    if raw is None:
        raw = ""
    raw = str(raw)
    if typ == "checkbox":
        return raw.strip().lower() in ("true", "1", "yes", "on")
    if typ == "number":
        try:
            return float(raw)
        except (ValueError, TypeError):
            return 0.0
    return raw


def value_to_str(v, typ):
    """把 UI 值转成写入 .env 的字符串。"""
    if v is None:
        return ""
    if typ == "checkbox":
        return "true" if v else "false"
    if typ == "number":
        try:
            f = float(v)
            return str(int(f)) if f.is_integer() else str(f)
        except (ValueError, TypeError):
            return str(v).strip()
    return str(v).strip()
