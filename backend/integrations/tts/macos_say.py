from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import platform
import subprocess
import tempfile
from typing import Protocol, Sequence
import wave

from services.tts_provider import (
    TtsProviderError,
    TtsSynthesisRequest,
    TtsSynthesisResult,
)


_SAY_BINARY = "/usr/bin/say"
_MAX_TEXT_CHARACTERS = 2_000
_MAX_AUDIO_BYTES = 32 * 1024 * 1024
_MIN_TIMEOUT_SECONDS = 1.0
_MAX_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class SayCommandResult:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""


class SayCommandRunner(Protocol):
    def run(
        self,
        args: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> SayCommandResult: ...


class SubprocessSayCommandRunner:
    def run(
        self,
        args: Sequence[str],
        *,
        timeout_seconds: float,
    ) -> SayCommandResult:
        completed = subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
        )
        return SayCommandResult(
            returncode=int(completed.returncode),
            stdout=bytes(completed.stdout or b""),
            stderr=bytes(completed.stderr or b""),
        )


class MacOsSayTtsProvider:
    """Development-only adapter for macOS' local system speech synthesizer.

    The executable and voice mapping are code-owned. A request supplies only
    narration text and language; ``voice_prompt`` is deliberately ignored so
    no client or generated lesson can choose a system voice or inject command
    options. ``subprocess`` is invoked without a shell and ``--`` terminates
    option parsing before the narration text.
    """

    provider_id = "macos-say"
    model_name = "apple/macos-system-speech"
    voice_mapping = {
        "zh-cn": "Tingting",
        "en-us": "Samantha",
    }

    def __init__(
        self,
        *,
        app_env: str,
        timeout_seconds: float = 30.0,
        runner: SayCommandRunner | None = None,
    ):
        if str(app_env or "").strip().lower() != "development":
            raise ValueError("macos-say is available only in APP_ENV=development")
        timeout = float(timeout_seconds)
        if timeout < _MIN_TIMEOUT_SECONDS or timeout > _MAX_TIMEOUT_SECONDS:
            raise ValueError("macos-say timeout must be between 1 and 120 seconds")
        if runner is None:
            if platform.system() != "Darwin":
                raise ValueError("macos-say requires macOS")
            say_path = Path(_SAY_BINARY)
            if not say_path.is_file():
                raise ValueError("macos-say requires /usr/bin/say")
        self.timeout_seconds = timeout
        self.runner = runner or SubprocessSayCommandRunner()

    def synthesize(self, request: TtsSynthesisRequest) -> TtsSynthesisResult:
        if not isinstance(request, TtsSynthesisRequest):
            raise TtsProviderError(
                "invalid_tts_request",
                "macOS speech requires a TtsSynthesisRequest",
            )
        text = self._clean_text(request.text)
        language = self._normalize_language(request.language_code)
        if str(request.output_format or "").strip().lower() != "wav":
            raise TtsProviderError(
                "unsupported_audio_format",
                "macOS speech output must be WAV",
            )
        voice = self.voice_mapping.get(language)
        if voice is None:
            raise TtsProviderError(
                "unsupported_tts_language",
                "macOS speech supports only zh-CN and en-US",
            )

        with tempfile.TemporaryDirectory(prefix="mira-macos-say-") as temporary:
            output_path = Path(temporary) / "narration.wav"
            command = (
                _SAY_BINARY,
                "-v",
                voice,
                "--file-format=WAVE",
                "--data-format=LEI16@22050",
                "-o",
                str(output_path),
                "--",
                text,
            )
            try:
                completed = self.runner.run(
                    command,
                    timeout_seconds=self.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise TtsProviderError(
                    "tts_upstream_timeout",
                    "macOS speech synthesis timed out",
                ) from exc
            except (OSError, subprocess.SubprocessError) as exc:
                raise TtsProviderError(
                    "tts_upstream_unavailable",
                    "macOS speech synthesis is unavailable",
                ) from exc
            if completed.returncode != 0:
                raise TtsProviderError(
                    "tts_upstream_command_failed",
                    "macOS speech synthesis failed",
                )
            audio = self._read_audio(output_path)

        duration_ms = self._validate_wav(audio)
        checksum = hashlib.sha256(audio).hexdigest()
        return TtsSynthesisResult(
            audio=audio,
            mime_type="audio/wav",
            provider_id=self.provider_id,
            model=self.model_name,
            duration_ms=duration_ms,
            checksum_sha256=checksum,
        )

    @staticmethod
    def _clean_text(value: str) -> str:
        normalized = " ".join(str(value or "").replace("\x00", " ").split()).strip()
        if not normalized:
            raise TtsProviderError("invalid_tts_request", "TTS text is required")
        if len(normalized) > _MAX_TEXT_CHARACTERS:
            raise TtsProviderError("invalid_tts_request", "TTS text is too long")
        return normalized

    @staticmethod
    def _normalize_language(value: str) -> str:
        return str(value or "").strip().replace("_", "-").casefold()

    @staticmethod
    def _read_audio(output_path: Path) -> bytes:
        try:
            if not output_path.is_file() or output_path.is_symlink():
                raise TtsProviderError(
                    "tts_empty_audio",
                    "macOS speech returned no audio",
                )
            with output_path.open("rb") as handle:
                audio = handle.read(_MAX_AUDIO_BYTES + 1)
        except TtsProviderError:
            raise
        except OSError as exc:
            raise TtsProviderError(
                "tts_upstream_unavailable",
                "macOS speech audio could not be read",
            ) from exc
        if len(audio) > _MAX_AUDIO_BYTES:
            raise TtsProviderError(
                "tts_response_too_large",
                "TTS audio exceeded the size limit",
            )
        if not audio:
            raise TtsProviderError("tts_empty_audio", "macOS speech returned no audio")
        return audio

    @staticmethod
    def _validate_wav(audio: bytes) -> int:
        try:
            with wave.open(io.BytesIO(audio), "rb") as wav_file:
                frames = int(wav_file.getnframes())
                rate = int(wav_file.getframerate())
                channels = int(wav_file.getnchannels())
                sample_width = int(wav_file.getsampwidth())
        except (EOFError, wave.Error) as exc:
            raise TtsProviderError(
                "tts_invalid_audio",
                "macOS speech returned an invalid WAV file",
            ) from exc
        if frames <= 0 or rate <= 0 or channels <= 0 or sample_width <= 0:
            raise TtsProviderError(
                "tts_empty_audio",
                "macOS speech returned an empty WAV file",
            )
        return max(1, int(round(frames * 1000 / rate)))
