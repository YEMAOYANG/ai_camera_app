from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Protocol


class TtsProviderError(RuntimeError):
    def __init__(self, code: str, safe_message: str):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


@dataclass(frozen=True)
class TtsSynthesisRequest:
    text: str
    language_code: str
    voice_prompt: str
    output_format: str = "wav"
    cfg_value: float = 2.0
    inference_timesteps: int = 10
    normalize: bool = False
    denoise: bool = False


@dataclass(frozen=True)
class TtsSynthesisResult:
    audio: bytes
    mime_type: str
    provider_id: str
    model: str
    duration_ms: int | None = None
    checksum_sha256: str | None = None

    def verified_checksum_sha256(self) -> str:
        """Return the payload checksum and reject a dishonest provider value."""

        actual = hashlib.sha256(self.audio).hexdigest()
        claimed = str(self.checksum_sha256 or "").strip().lower()
        if claimed and claimed != actual:
            raise TtsProviderError(
                "tts_checksum_mismatch",
                "TTS audio failed its checksum verification",
            )
        return actual


class TtsProvider(Protocol):
    provider_id: str
    model_name: str

    def synthesize(self, request: TtsSynthesisRequest) -> TtsSynthesisResult:
        """Synthesize server-owned prompt voice audio or raise TtsProviderError."""
