from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class SpeechGateway:
    """ASR/TTS boundary. V1 defaults to text-in/text-out for worker mock mode."""

    def __init__(self, *, asr_provider: str = "disabled", tts_provider: str = "disabled"):
        self.asr_provider = str(asr_provider or "disabled").strip().lower()
        self.tts_provider = str(tts_provider or "disabled").strip().lower()

    def transcribe_text(self, text: str) -> dict:
        value = str(text or "").strip()
        return {"ok": bool(value), "text": value, "provider": self.asr_provider or "text"}

    def synthesize(self, text: str) -> dict:
        value = str(text or "").strip()
        return {"ok": bool(value), "text": value, "provider": self.tts_provider or "text"}
