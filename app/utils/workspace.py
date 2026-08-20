"""工作区管理：outputs/<video_name>/ 下保存所有中间结果，支持断点续跑。"""
from pathlib import Path


class Workspace:
    def __init__(self, input_path, root: str = "outputs"):
        self.input_path = Path(input_path)
        self.name = self.input_path.stem
        self.dir = Path(root) / self.name
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, *parts) -> Path:
        return self.dir.joinpath(*parts)

    def exists(self, *parts) -> bool:
        return self.path(*parts).exists()

    def __repr__(self) -> str:
        return f"Workspace({self.dir})"
