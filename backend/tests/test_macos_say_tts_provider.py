from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import platform
import subprocess
import unittest
import wave

from core.config import ConfigError, validate_flask_config
from integrations.tts.macos_say import (
    MacOsSayTtsProvider,
    SayCommandResult,
)
from services.tts_provider import TtsProviderError, TtsSynthesisRequest


def fixture_wav(*, frames: int = 2_205) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22_050)
        wav_file.writeframes(b"\x01\x00" * frames)
    return output.getvalue()


class WritingSayRunner:
    def __init__(self, *, audio: bytes | None = None, returncode: int = 0):
        self.audio = fixture_wav() if audio is None else audio
        self.returncode = returncode
        self.commands: list[tuple[str, ...]] = []

    def run(self, args, *, timeout_seconds):
        command = tuple(args)
        self.commands.append(command)
        if self.returncode == 0:
            output_path = Path(command[command.index("-o") + 1])
            output_path.write_bytes(self.audio)
        return SayCommandResult(returncode=self.returncode)


class TimeoutSayRunner:
    def run(self, args, *, timeout_seconds):
        raise subprocess.TimeoutExpired(args, timeout_seconds)


class MacOsSayTtsProviderTest(unittest.TestCase):
    def request(
        self,
        *,
        text: str = "先看十位，再看个位。",
        language_code: str = "zh-CN",
        voice_prompt: str = "Samantha --rate 999",
    ) -> TtsSynthesisRequest:
        return TtsSynthesisRequest(
            text=text,
            language_code=language_code,
            voice_prompt=voice_prompt,
        )

    def test_fixed_language_voice_produces_verified_wav(self):
        runner = WritingSayRunner()
        provider = MacOsSayTtsProvider(
            app_env="development",
            runner=runner,
        )
        result = provider.synthesize(self.request())

        self.assertEqual(result.provider_id, "macos-say")
        self.assertEqual(result.model, "apple/macos-system-speech")
        self.assertEqual(result.mime_type, "audio/wav")
        self.assertEqual(result.duration_ms, 100)
        self.assertEqual(result.checksum_sha256, hashlib.sha256(result.audio).hexdigest())
        command = runner.commands[0]
        self.assertEqual(command[0], "/usr/bin/say")
        self.assertEqual(command[command.index("-v") + 1], "Tingting")
        self.assertEqual(command[-2], "--")
        self.assertEqual(command[-1], "先看十位，再看个位。")
        self.assertNotIn("Samantha --rate 999", command)

        provider.synthesize(
            self.request(text="Listen and repeat.", language_code="en-US")
        )
        english_command = runner.commands[1]
        self.assertEqual(english_command[english_command.index("-v") + 1], "Samantha")

    def test_command_failure_is_safe_and_does_not_return_audio(self):
        provider = MacOsSayTtsProvider(
            app_env="development",
            runner=WritingSayRunner(returncode=7),
        )
        with self.assertRaises(TtsProviderError) as raised:
            provider.synthesize(self.request())
        self.assertEqual(raised.exception.code, "tts_upstream_command_failed")

    def test_timeout_is_mapped_to_provider_error(self):
        provider = MacOsSayTtsProvider(
            app_env="development",
            timeout_seconds=1,
            runner=TimeoutSayRunner(),
        )
        with self.assertRaises(TtsProviderError) as raised:
            provider.synthesize(self.request())
        self.assertEqual(raised.exception.code, "tts_upstream_timeout")

    def test_empty_wav_is_rejected(self):
        provider = MacOsSayTtsProvider(
            app_env="development",
            runner=WritingSayRunner(audio=fixture_wav(frames=0)),
        )
        with self.assertRaises(TtsProviderError) as raised:
            provider.synthesize(self.request())
        self.assertEqual(raised.exception.code, "tts_empty_audio")

    def test_provider_constructor_and_config_forbid_non_development(self):
        with self.assertRaises(ValueError):
            MacOsSayTtsProvider(
                app_env="production",
                runner=WritingSayRunner(),
            )
        with self.assertRaises(ConfigError) as raised:
            validate_flask_config(
                {
                    "APP_ENV": "production",
                    "DATABASE_URL": "mysql+pymysql://mira:mira@db/mira",
                    "LEARNING_TTS_PROVIDER": "macos-say",
                }
            )
        self.assertIn("only in development", str(raised.exception))

    @unittest.skipUnless(
        platform.system() == "Darwin"
        and Path("/usr/bin/say").is_file()
        and os.getenv("MIRA_RUN_MACOS_TTS_SMOKE") == "1",
        "set MIRA_RUN_MACOS_TTS_SMOKE=1 on macOS to run system speech",
    )
    def test_real_system_say_smoke(self):
        result = MacOsSayTtsProvider(
            app_env="development",
            timeout_seconds=30,
        ).synthesize(self.request(text="一加一等于二。"))
        self.assertGreater(len(result.audio), 44)
        self.assertGreater(result.duration_ms or 0, 0)
        self.assertEqual(result.verified_checksum_sha256(), result.checksum_sha256)


if __name__ == "__main__":
    unittest.main()
