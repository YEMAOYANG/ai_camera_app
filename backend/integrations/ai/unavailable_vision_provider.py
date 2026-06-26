from __future__ import annotations


class UnavailableVisionProvider:
    provider_name = "unconfigured"
    model_name = "unconfigured"

    def analyze_image(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        content_type: str,
        max_tokens: int = 360,
        temperature: float = 0.6,
    ):
        return None
