"""生成多说话人测试视频（离线，供 Phase 2 Diarization 验证）。

Speaker A = Microsoft Huihui 女声（原声）；Speaker B = 同声音降调 ~40%（男声感），
保证两个说话人在声学上（F0 ~200Hz vs ~120Hz）清晰可分。
背景音 = 低音量正弦波。纯 CPU（SAPI + FFmpeg），不占显卡。
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.video.extractor import run_ffmpeg

PS_SCRIPT = r"""
param([string]$TextFile, [string]$Out, [string]$Voice)
Add-Type -AssemblyName System.Speech
$text = [System.IO.File]::ReadAllText($TextFile, [System.Text.Encoding]::UTF8)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice($Voice)
$s.SetOutputToWaveFile($Out)
$s.Speak($text)
$s.Dispose()
"""

# (voice, text, start_seconds, pitch_factor)  pitch_factor=None 表示不变调
# 含重叠：B 的第二句在 A 第一句尚未结束时开始说话（2.3s 起，A 到 2.9s 才结束）
SCRIPT = [
    ("Microsoft Huihui Desktop", "你吃饭了吗？", 1.0, None),          # A 女声 ~1.0-2.9s
    ("Microsoft Huihui Desktop", "我吃了，我们去看电影吧。", 2.3, 0.6),  # B 男声 ~2.3-5.4s（与 A 重叠）
    ("Microsoft Huihui Desktop", "好啊，我们七点出发。", 6.0, None),    # A 女声 ~6.0-8.0s
]


def sapi_speak(text, out_wav, voice="Microsoft Huihui Desktop"):
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
        text_file = f.name
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as f:
        f.write(PS_SCRIPT)
        script = f.name
    try:
        cmd = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", script, "-TextFile", text_file, "-Out", str(out_wav), "-Voice", voice,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"SAPI failed: {proc.stderr.strip() or proc.stdout.strip()}")
    finally:
        Path(script).unlink(missing_ok=True)
        Path(text_file).unlink(missing_ok=True)
    return out_wav


def pitch_shift(in_wav, out_wav, factor=0.6):
    """降低音高 factor（0.6 ≈ 降 40%），保持时长：asetrate 降采样率 + aresample 还原。"""
    sr = 44100
    new_sr = int(sr * factor)
    run_ffmpeg(
        ["-i", str(in_wav),
         "-af", f"aresample={sr},asetrate={new_sr},aresample={sr}",
         "-c:a", "pcm_s16le", str(out_wav)],
        tag="[gen]",
    )
    return out_wav


def make_test_video(out_mp4, workdir, duration=26):
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    out_mp4 = Path(out_mp4)

    print("[gen] synthesizing speech ...")
    audio_files = []
    for i, (voice, text, start, pitch) in enumerate(SCRIPT):
        raw = workdir / f"spk_{i:02d}_raw.wav"
        sapi_speak(text, raw, voice=voice)
        out = workdir / f"spk_{i:02d}.wav"
        if pitch is not None:
            pitch_shift(raw, out, factor=pitch)
        else:
            out = raw
        audio_files.append((out, start))

    print("[gen] generating background tone ...")
    bg = workdir / "bg.wav"
    run_ffmpeg(
        ["-f", "lavfi", "-i", f"sine=frequency=220:duration={duration}",
         "-af", "volume=0.06", "-c:a", "pcm_s16le", str(bg)],
        tag="[gen]",
    )

    print("[gen] mixing timeline ...")
    inputs, fc, labels = [], [], []
    for i, (f, start) in enumerate(audio_files):
        inputs += ["-i", str(f)]
        fc.append(f"[{i}:a]adelay={int(start * 1000)}:all=1[s{i}]")
        labels.append(f"[s{i}]")
    inputs += ["-i", str(bg)]
    n_bg = len(audio_files)
    fc.append(
        f"{''.join(labels)}[{n_bg}:a]amix=inputs={len(audio_files) + 1}:duration=longest,"
        f"atrim=0:{duration},asetpts=N/SR/TB,volume=2.0[m]"
    )
    mix = workdir / "mixed.wav"
    run_ffmpeg(
        inputs + ["-filter_complex", ";".join(fc), "-map", "[m]",
                  "-c:a", "pcm_s16le", str(mix)],
        tag="[gen]",
    )

    print("[gen] muxing mp4 ...")
    run_ffmpeg(
        ["-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=30:duration={duration}",
         "-i", str(mix), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(out_mp4)],
        tag="[gen]",
    )
    print(f"[gen] wrote {out_mp4}")
    return out_mp4


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="生成多说话人测试视频")
    p.add_argument("--out", default="test_video.mp4")
    p.add_argument("--workdir", default="test_assets")
    p.add_argument("--duration", type=int, default=26)
    args = p.parse_args()
    make_test_video(args.out, args.workdir, duration=args.duration)
