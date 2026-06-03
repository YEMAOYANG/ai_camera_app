from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from schemas.ai import ai_config_payload, eval_case_payloads, model_payloads
from services.prompt_registry import PromptRegistry


ai_bp = Blueprint("ai", __name__)


def _prompt_registry() -> PromptRegistry:
    return PromptRegistry(current_app.config["PROMPT_ROOT"])


@ai_bp.get("/config")
def ai_config():
    return jsonify(ai_config_payload())


@ai_bp.get("/prompts")
def prompts():
    return jsonify(
        {
            "ok": True,
            "prompts": [prompt.to_public_dict() for prompt in _prompt_registry().list_prompts()],
        }
    )


@ai_bp.get("/models")
def models():
    return jsonify({"ok": True, "models": model_payloads()})


@ai_bp.get("/eval-cases")
def eval_cases():
    return jsonify({"ok": True, "evalCases": eval_case_payloads()})
