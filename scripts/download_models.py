"""一键下载 PolyDub 所需的全部模型（首次使用前运行，或由 setup.bat 调用）。

需要先设置 HF_TOKEN（环境变量或交互输入）。
pyannote 系列是 gated 模型，需先在 https://huggingface.co 登录并接受模型许可
（speaker-diarization-3.1、segmentation-3.0、wespeaker-voxceleb-resnet34-LM）。
"""
import os
import sys

# (HF repo id, 用途说明, 是否需要 gated 许可)
MODELS = [
    ("Systran/faster-whisper-large-v3", "语音转文字 ASR", False),
    ("pyannote/speaker-diarization-3.1", "说话人识别（gated，需接受许可）", True),
    ("pyannote/segmentation-3.0", "说话人识别辅助（gated）", True),
    ("pyannote/wespeaker-voxceleb-resnet34-LM", "说话人声音嵌入（gated）", True),
    ("speechbrain/sepformer-libri2mix", "2 人重叠语音分离", False),
    ("speechbrain/sepformer-libri3mix", "3 人重叠语音分离", False),
    ("Helsinki-NLP/opus-mt-en-zh", "离线翻译（英→中）兜底", False),
    ("Helsinki-NLP/opus-mt-zh-en", "离线翻译（中→英）兜底", False),
]

INDEX_TTS_CHECKPOINT = ("index-tts/index-tts-v2.5", "IndexTTS 2.5 语音克隆权重（放到 index-tts/checkpoints_25）")


def main():
    token = os.environ.get("HF_TOKEN") or input("请输入 HuggingFace Token（https://huggingface.co/settings/tokens 创建）：").strip()
    if not token:
        print("[错误] 未提供 HF_TOKEN，无法下载 gated 模型。")
        sys.exit(1)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[错误] 请先安装 huggingface_hub：pip install huggingface-hub")
        sys.exit(1)

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        print(f"[信息] 检测到代理：{proxy}（用于访问 HuggingFace）")

    ok, fail = 0, 0
    for repo, desc, gated in MODELS:
        print(f"\n>>> 下载 [{desc}] {repo} ...")
        if gated:
            print("    （gated 模型，请确认你已在 HuggingFace 网页接受该模型许可）")
        try:
            snapshot_download(repo_id=repo, token=token)
            print("    完成 ✓")
            ok += 1
        except Exception as e:
            print(f"    [失败] {e}")
            fail += 1

    # IndexTTS 2.5 权重（可选，若本地已有可跳过）
    print(f"\n>>> 下载 [{INDEX_TTS_CHECKPOINT[1]}] {INDEX_TTS_CHECKPOINT[0]} ...")
    try:
        snapshot_download(
            repo_id=INDEX_TTS_CHECKPOINT[0],
            local_dir=os.path.join("index-tts", "checkpoints_25"),
            token=token,
        )
        print("    完成 ✓")
        ok += 1
    except Exception as e:
        print(f"    [失败] {e}")
        print("    可手动下载：在浏览器打开 https://huggingface.co/index-tts/index-tts-v2.5")
        print("    下载全部文件放到 index-tts/checkpoints_25/ 目录下。")
        fail += 1

    print("\n======================================")
    print(f"下载完成：成功 {ok} 项，失败 {fail} 项。")
    if fail:
        print("失败的项请查看上方提示处理（gated 模型需先接受许可，代理失败请检查网络）。")
    else:
        print("全部模型就绪，可以开始使用了！")


if __name__ == "__main__":
    main()
