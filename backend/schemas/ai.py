from __future__ import annotations


def ai_config_payload(
    *,
    provider: str,
    model: str,
    credentials_configured: bool,
    eval_enabled: bool,
    dev_adapters_enabled: bool,
) -> dict:
    provider_configured = bool(provider)
    provider_name = provider if provider_configured else "unconfigured"
    return {
        "ok": True,
        "providers": [provider_name],
        "providerConfigured": provider_configured,
        "credentialsConfigured": credentials_configured,
        "defaultModelPolicy": "configured" if provider_configured and credentials_configured else "unconfigured",
        "defaultModel": model or None,
        "promptRegistry": "file",
        "evalEnabled": eval_enabled,
        "devAdaptersEnabled": dev_adapters_enabled,
    }


def model_payloads(*, provider: str, model: str, dev_adapters_enabled: bool) -> list[dict]:
    if provider and model:
        return [
            {
                "id": model,
                "provider": provider,
                "capabilities": ["text", "vision-summary", "task-summary", "task-reminder"],
                "status": "configured",
            }
        ]
    if dev_adapters_enabled:
        return [
            {
                "id": "development.guardian-v1",
                "provider": "development",
                "capabilities": ["text", "vision-summary", "task-summary", "task-reminder"],
                "status": "development",
            }
        ]
    return [
        {
            "id": "unconfigured",
            "provider": "unconfigured",
            "capabilities": [],
            "status": "unconfigured",
        }
    ]


def eval_case_payloads(*, eval_enabled: bool) -> list[dict]:
    if not eval_enabled:
        return []
    return [
        {
            "id": "task-observation-summary-basic",
            "promptId": "task.observation.summary",
            "promptVersion": "v1",
            "scenario": "task",
            "status": "draft",
        }
    ]
