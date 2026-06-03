from __future__ import annotations


def ai_config_payload() -> dict:
    return {
        "ok": True,
        "providers": ["mock"],
        "defaultModelPolicy": "development",
        "promptRegistry": "file",
    }


def model_payloads() -> list[dict]:
    return [
        {
            "id": "mock.guardian-v1",
            "provider": "mock",
            "capabilities": ["text", "vision-summary", "task-summary"],
            "status": "development",
        }
    ]


def eval_case_payloads() -> list[dict]:
    return [
        {
            "id": "task-observation-summary-basic",
            "promptId": "task.observation.summary",
            "promptVersion": "v1",
            "scenario": "task",
            "status": "draft",
        }
    ]
