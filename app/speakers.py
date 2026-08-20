"""说话人角色管理：SPEAKER_XX -> 角色名 / 固定 Voice 映射。

同一 Speaker 在整部视频中保持同一声音。
映射持久化到 config/speakers.yaml，可人工编辑。
"""
from pathlib import Path

import yaml

from .utils.logging import get_logger

log = get_logger(__name__)


class SpeakerManager:
    def __init__(self, mapping_file=None):
        self.mapping_file = Path(mapping_file) if mapping_file else None
        self.mapping = {}
        if self.mapping_file and self.mapping_file.exists():
            self.mapping = yaml.safe_load(self.mapping_file.read_text(encoding="utf-8")) or {}

    def role(self, speaker):
        return self.mapping.get(speaker, {}).get("role", speaker)

    def voice(self, speaker):
        return self.mapping.get(speaker, {}).get("voice")

    def set_role(self, speaker, role, voice=None):
        entry = self.mapping.setdefault(speaker, {})
        entry["role"] = role
        if voice is not None:
            entry["voice"] = voice

    def ensure_roles(self, speakers):
        """为未知 speaker 生成默认角色名并保存。"""
        changed = False
        for spk in speakers:
            if spk not in self.mapping:
                self.mapping[spk] = {"role": spk, "voice": None}
                changed = True
        if changed:
            self.save()
        return self.mapping

    def save(self):
        if not self.mapping_file:
            return
        self.mapping_file.parent.mkdir(parents=True, exist_ok=True)
        self.mapping_file.write_text(
            yaml.safe_dump(self.mapping, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        log.info("[Speakers] saved mapping to %s", self.mapping_file)
