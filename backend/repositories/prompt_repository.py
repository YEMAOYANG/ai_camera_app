from __future__ import annotations

from pathlib import Path


class PromptRepository:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def prompt_files(self) -> list[Path]:
        if not self.root.exists():
            return []
        return [
            path
            for path in sorted(self.root.rglob("*.md"))
            if path.name.upper() != "README.MD"
        ]

    def read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def relative_path(self, path: Path) -> str:
        return str(path.relative_to(self.root))
