"""字幕输出：SRT / JSON / ASS。"""
import json
from pathlib import Path

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,80,80,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def format_timestamp(seconds: float) -> str:
    """秒 -> SRT 时间戳 HH:MM:SS,mmm。"""
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ass_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h}:{m:02d}:{s:02d}.{ms:03d}"


def write_srt(segments, out_path) -> None:
    lines = []
    for i, seg in enumerate(segments, 1):
        speaker = seg.get("speaker")
        prefix = f"[{speaker}] " if speaker else ""
        lines.append(str(i))
        lines.append(f"{format_timestamp(seg['start'])} --> {format_timestamp(seg['end'])}")
        lines.append(f"{prefix}{seg['text'].strip()}")
        lines.append("")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


def write_json(payload, out_path) -> None:
    Path(out_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


_SPEAKER_COLORS = {
    "SPEAKER_00": "&H00FFFFFF",  # 白
    "SPEAKER_01": "&H0000FFFF",  # 黄
    "SPEAKER_02": "&H00FF00FF",  # 品红
    "SPEAKER_03": "&H0000FF00",  # 绿
    "SPEAKER_04": "&H00FFFF00",  # 青
    "SPEAKER_05": "&H000000FF",  # 红
}


def write_ass(segments, out_path) -> None:
    """ASS 字幕：重叠说话人自动分到不同垂直行，同屏显示（带说话人标签 + 颜色）。"""
    segs = sorted(segments, key=lambda s: s["start"])
    # 分配垂直轨道：时间重叠的片段占不同 track（同一时刻多人说话则上下分行）
    active = []  # [(end, track)]
    track_of = []
    for seg in segs:
        active = [(e, tr) for (e, tr) in active if e > seg["start"] + 0.05]
        used = {tr for (_e, tr) in active}
        tr = 0
        while tr in used:
            tr += 1
        active.append((seg["end"], tr))
        track_of.append(tr)

    margin_base = 30
    margin_step = 60
    out = [ASS_HEADER]
    for seg, tr in zip(segs, track_of):
        speaker = seg.get("speaker", "")
        prefix = f"[{speaker}] " if speaker else ""
        color = _SPEAKER_COLORS.get(speaker, "&H00FFFFFF")
        text = seg["text"].strip().replace("\n", " ")
        margin_v = margin_base + tr * margin_step
        out.append(
            f"Dialogue: 0,{_ass_time(seg['start'])},{_ass_time(seg['end'])},"
            f"Default,,0,0,{margin_v},,{{\\1c&H{color[4:]}&}}{prefix}{text}"
        )
    Path(out_path).write_text("\n".join(out), encoding="utf-8")
