from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptDefinition:
    prompt_id: str
    version: str
    scenario: str
    status: str
    path: str
    body: str

    def to_public_dict(self) -> dict:
        return {
            "id": self.prompt_id,
            "version": self.version,
            "scenario": self.scenario,
            "status": self.status,
        }
