from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import urllib.error
import urllib.request
from typing import Protocol


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AiTextResponse:
    text: str
    provider: str
    model: str


class AiTextProvider(Protocol):
    provider_name: str
    model_name: str

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 96,
        temperature: float = 0.4,
    ) -> AiTextResponse | None:
        """Generate a short text completion. Returns None when unavailable."""


class UnavailableAiTextProvider:
    provider_name = "unconfigured"
    model_name = "unconfigured"

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 96,
        temperature: float = 0.4,
    ) -> AiTextResponse | None:
        return None


class OpenAICompatibleTextProvider:
    def __init__(
        self,
        *,
        provider_name: str,
        api_key: str,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 8.0,
        disable_thinking: bool = False,
    ):
        self.provider_name = provider_name.strip().lower() or "openai_compatible"
        self.api_key = api_key.strip()
        self.base_url = base_url.strip().rstrip("/")
        self.model_name = model_name.strip()
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.disable_thinking = disable_thinking

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 96,
        temperature: float = 0.4,
    ) -> AiTextResponse | None:
        if not self.api_key or not self.base_url or not self.model_name:
            return None
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": user_prompt.strip()},
            ],
            "temperature": max(0.0, min(float(temperature), 1.0)),
            "max_tokens": max(16, int(max_tokens)),
        }
        if self.disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        request = urllib.request.Request(
            self._chat_completions_url(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:240]
            log.warning("%s AI text completion failed: HTTP %s %s", self.provider_name, exc.code, detail)
            return None
        except Exception as exc:  # pragma: no cover - network failure shape varies by host.
            log.warning("%s AI text completion failed: %s", self.provider_name, exc)
            return None

        try:
            text = str(body["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError):
            log.warning("%s AI text completion returned unexpected payload", self.provider_name)
            return None
        if not text:
            return None
        return AiTextResponse(text=text, provider=self.provider_name, model=self.model_name)

    def _chat_completions_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"
