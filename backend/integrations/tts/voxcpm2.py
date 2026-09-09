from __future__ import annotations

from dataclasses import dataclass
import io
import json
import secrets
from typing import Mapping, Protocol
from urllib.parse import urlparse
import urllib.error
import urllib.request
import wave

from services.tts_provider import (
    TtsProviderError,
    TtsSynthesisRequest,
    TtsSynthesisResult,
)


VOXCPM_BACKENDS = frozenset({"vllm-omni", "python-api"})
_MAX_AUDIO_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class TtsHttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class TtsHttpTransport(Protocol):
    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> TtsHttpResponse: ...


class UrllibTtsHttpTransport:
    def post(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> TtsHttpResponse:
        request = urllib.request.Request(
            url,
            data=body,
            headers=dict(headers),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read(_MAX_AUDIO_BYTES + 1)
                if len(payload) > _MAX_AUDIO_BYTES:
                    raise TtsProviderError("tts_response_too_large", "TTS audio exceeded the size limit")
                return TtsHttpResponse(
                    status=int(response.status),
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=payload,
                )
        except urllib.error.HTTPError as exc:
            exc.read(512)
            raise TtsProviderError(
                "tts_upstream_http_error",
                f"VoxCPM2 rejected the synthesis request (HTTP {exc.code})",
            ) from exc
        except TtsProviderError:
            raise
        except Exception as exc:
            raise TtsProviderError(
                "tts_upstream_unavailable",
                "VoxCPM2 is temporarily unavailable",
            ) from exc


class VoxCpm2HttpProvider:
    """Server-only VoxCPM2 adapter for the two official HTTP protocols.

    It accepts neither API keys nor reference audio.  Voice design is a fixed
    registry prompt embedded into target text, matching OpenMAIC's prompt mode
    while intentionally excluding clone mode and browser-owned credentials.
    """

    provider_id = "voxcpm2"

    def __init__(
        self,
        *,
        base_url: str,
        backend: str = "vllm-omni",
        model_name: str = "openbmb/VoxCPM2",
        timeout_seconds: float = 30.0,
        transport: TtsHttpTransport | None = None,
    ):
        self.base_url = self._validate_base_url(base_url)
        self.backend = str(backend or "").strip().lower()
        if self.backend not in VOXCPM_BACKENDS:
            raise ValueError("VoxCPM2 backend must be vllm-omni or python-api")
        self.model_name = str(model_name or "").strip()
        if not self.model_name:
            raise ValueError("VoxCPM2 model name is required")
        self.timeout_seconds = max(1.0, min(float(timeout_seconds), 120.0))
        self.transport = transport or UrllibTtsHttpTransport()

    def synthesize(self, request: TtsSynthesisRequest) -> TtsSynthesisResult:
        text = self._clean_text(request.text, field="text", maximum=2000)
        voice_prompt = self._clean_text(
            request.voice_prompt,
            field="voice prompt",
            maximum=300,
        )
        if request.output_format.lower() != "wav":
            raise TtsProviderError("unsupported_audio_format", "VoxCPM2 output must be WAV")
        target_text = f"({self._strip_parentheses(voice_prompt)}){text}"
        if self.backend == "vllm-omni":
            response = self._post_vllm_omni(target_text)
        else:
            response = self._post_python_api(target_text, request)
        if response.status < 200 or response.status >= 300:
            raise TtsProviderError(
                "tts_upstream_http_error",
                f"VoxCPM2 returned HTTP {response.status}",
            )
        mime_type = self._normalize_audio_mime(response.headers)
        if not response.body:
            raise TtsProviderError("tts_empty_audio", "VoxCPM2 returned empty audio")
        if len(response.body) > _MAX_AUDIO_BYTES:
            raise TtsProviderError("tts_response_too_large", "TTS audio exceeded the size limit")
        return TtsSynthesisResult(
            audio=bytes(response.body),
            mime_type=mime_type,
            provider_id=self.provider_id,
            model=self.model_name,
            duration_ms=self._wav_duration_ms(response.body) if mime_type == "audio/wav" else None,
        )

    def _post_vllm_omni(self, target_text: str) -> TtsHttpResponse:
        payload = {
            "model": self.model_name,
            "input": target_text,
            "voice": "default",
            "response_format": "wav",
            "stream": False,
        }
        return self.transport.post(
            url=self._vllm_url(),
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            timeout_seconds=self.timeout_seconds,
        )

    def _post_python_api(
        self,
        target_text: str,
        request: TtsSynthesisRequest,
    ) -> TtsHttpResponse:
        fields = {
            "text": target_text,
            "cfg_value": str(float(request.cfg_value)),
            "inference_timesteps": str(max(1, int(request.inference_timesteps))),
            "normalize": str(bool(request.normalize)).lower(),
            "denoise": str(bool(request.denoise)).lower(),
        }
        boundary = f"mira-{secrets.token_hex(16)}"
        body = self._encode_multipart(fields, boundary=boundary)
        return self.transport.post(
            url=f"{self.base_url}/tts/upload",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            body=body,
            timeout_seconds=self.timeout_seconds,
        )

    def _vllm_url(self) -> str:
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/audio/speech"
        return f"{self.base_url}/v1/audio/speech"

    @staticmethod
    def _encode_multipart(fields: Mapping[str, str], *, boundary: str) -> bytes:
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("ascii"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode("ascii"))
        return b"".join(chunks)

    @staticmethod
    def _validate_base_url(value: str) -> str:
        normalized = str(value or "").strip().rstrip("/")
        parsed = urlparse(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("VoxCPM2 base URL must be a server-owned HTTP(S) origin or path")
        return normalized

    @staticmethod
    def _clean_text(value: str, *, field: str, maximum: int) -> str:
        normalized = " ".join(str(value or "").replace("\x00", " ").split()).strip()
        if not normalized:
            raise TtsProviderError("invalid_tts_request", f"TTS {field} is required")
        if len(normalized) > maximum:
            raise TtsProviderError("invalid_tts_request", f"TTS {field} is too long")
        return normalized

    @staticmethod
    def _strip_parentheses(value: str) -> str:
        return value.replace("(", "").replace(")", "").replace("（", "").replace("）", "")

    @staticmethod
    def _normalize_audio_mime(headers: Mapping[str, str]) -> str:
        content_type = str(
            headers.get("content-type") or headers.get("Content-Type") or ""
        ).split(";", 1)[0].strip().lower()
        aliases = {"audio/x-wav": "audio/wav", "audio/mp3": "audio/mpeg"}
        content_type = aliases.get(content_type, content_type)
        if content_type not in {
            "audio/wav",
            "audio/mpeg",
            "audio/flac",
            "audio/ogg",
            "audio/webm",
        }:
            raise TtsProviderError(
                "tts_invalid_content_type",
                "VoxCPM2 did not return a supported audio response",
            )
        return content_type

    @staticmethod
    def _wav_duration_ms(audio: bytes) -> int | None:
        try:
            with wave.open(io.BytesIO(audio), "rb") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                if rate <= 0:
                    return None
                return int(round(frames * 1000 / rate))
        except (wave.Error, EOFError):
            return None
