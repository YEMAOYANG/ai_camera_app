from __future__ import annotations

from dataclasses import dataclass
import base64
import io
import json
import logging
import urllib.error
import urllib.request
from typing import Protocol

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None  # type: ignore


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AiVisionResponse:
    text: str
    provider: str
    model: str


class AiVisionProvider(Protocol):
    provider_name: str
    model_name: str

    def analyze_image(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        content_type: str,
        max_tokens: int = 360,
        temperature: float = 0.6,
    ) -> AiVisionResponse | None:
        ...


class OpenAICompatibleVisionProvider:
    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 20.0,
        max_bytes: int = 524288,
        disable_thinking: bool = False,
    ):
        self.provider_name = provider_name.strip().lower() or "openai_compatible"
        self.api_key = api_key.strip()
        self.base_url = base_url.strip().rstrip("/")
        self.model_name = model_name.strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.max_bytes = max(8192, int(max_bytes))
        self.disable_thinking = disable_thinking

    def analyze_image(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        image_bytes: bytes,
        content_type: str,
        max_tokens: int = 360,
        temperature: float = 0.6,
    ) -> AiVisionResponse | None:
        if not self.api_key or not self.base_url or not self.model_name:
            return None
        if not image_bytes:
            return None
        encoded = _encode_image(image_bytes, content_type, self.max_bytes)
        if encoded is None:
            return None
        payload: dict = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": encoded}},
                    ],
                },
            ],
            "temperature": float(temperature),
            "max_tokens": max(64, int(max_tokens)),
        }
        if self.disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8", "ignore") or "{}")
        except urllib.error.HTTPError as exc:
            log.warning("vision provider HTTP error: %s", exc)
            return None
        except Exception as exc:
            log.warning("vision provider request failed: %s", exc)
            return None
        text = _extract_completion_text(body)
        if not text:
            return None
        return AiVisionResponse(text=text, provider=self.provider_name, model=self.model_name)


def _encode_image(image_bytes: bytes, content_type: str, max_bytes: int) -> str | None:
    body = image_bytes[:max_bytes]
    mime = str(content_type or "image/jpeg").split(";", 1)[0].strip() or "image/jpeg"
    if Image is not None:
        try:
            with Image.open(io.BytesIO(body)) as image:
                image = image.convert("RGB")
                image.thumbnail((512, 512))
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=45, optimize=True)
                body = buffer.getvalue()
                mime = "image/jpeg"
        except Exception:
            pass
    encoded = base64.b64encode(body).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _extract_completion_text(body: dict) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts).strip()
    return ""
