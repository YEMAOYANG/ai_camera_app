from __future__ import annotations

from pathlib import Path

from models.prompt import PromptDefinition
from repositories.prompt_repository import PromptRepository


class PromptRegistry:
    def __init__(self, root: str | Path):
        self.repository = PromptRepository(root)

    def list_prompts(self) -> list[PromptDefinition]:
        prompts: list[PromptDefinition] = []
        for path in self.repository.prompt_files():
            prompts.append(self._read_prompt(path))
        return prompts

    def get_prompt(self, prompt_id: str, version: str) -> PromptDefinition | None:
        for prompt in self.list_prompts():
            if prompt.prompt_id == prompt_id and prompt.version == version:
                return prompt
        return None

    def _read_prompt(self, path: Path) -> PromptDefinition:
        text = self.repository.read_text(path)
        meta: dict[str, str] = {}
        body_lines: list[str] = []
        for line in text.splitlines():
            if line.startswith("# ") and ":" in line:
                key, value = line[2:].split(":", 1)
                meta[key.strip()] = value.strip()
                continue
            body_lines.append(line)

        return PromptDefinition(
            prompt_id=meta.get("prompt_id", path.stem),
            version=meta.get("version", "v1"),
            scenario=meta.get("scenario", path.parent.name),
            status=meta.get("status", "draft"),
            path=self.repository.relative_path(path),
            body="\n".join(body_lines).strip(),
        )
