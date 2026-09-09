from __future__ import annotations

import copy
import hashlib
import io
import math
import struct
import tempfile
import unittest
import wave

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from services.learning_media_materialization_service import (
    LearningMediaMaterializationError,
    asr_similarity_bps,
    build_formal_speech_manifest,
    normalize_asr_text,
    prepare_formal_asr_comparison_text,
    prepare_formal_speech_text,
    validate_formal_wav,
)
from services.learning_media_asset_store import FilesystemLearningMediaAssetStore


def _wav(*, sample_rate: int = 16_000, duration_ms: int = 400,
         channels: int = 1, sample_width: int = 2, amplitude: float = 0.2) -> bytes:
    frame_count = sample_rate * duration_ms // 1000
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            sample = int(amplitude * 32767 * math.sin(2 * math.pi * 440 * index / sample_rate))
            encoded = struct.pack("<h", sample) if sample_width == 2 else bytes([(sample >> 8) + 128])
            frames.extend(encoded * channels)
        wav_file.writeframes(bytes(frames))
    return output.getvalue()


def _classroom() -> dict:
    return {
        "stage": {"id": "stage-1"},
        "scenes": [
            {
                "id": f"scene-{index}",
                "order": index,
                "actions": [
                    {"id": f"speech-{index}", "type": "speech", "text": f"第{index + 1}段讲解"},
                    {"id": f"other-{index}", "type": "spotlight"},
                ],
            }
            for index in range(10)
        ],
    }


class FormalQwenAudioValidationTest(unittest.TestCase):
    def test_final_storage_readback_returns_exact_written_wav(self) -> None:
        audio = _wav()
        digest = hashlib.sha256(audio).hexdigest()
        with tempfile.TemporaryDirectory() as root:
            store = FilesystemLearningMediaAssetStore(root)
            stored = store.put_audio(
                job_id="formal-job-1",
                segment_id="segment-0",
                content_hash=digest,
                mime_type="audio/wav",
                audio=audio,
            )
            self.assertEqual(store.read_audio(stored.storage_key), audio)
            with self.assertRaises(ValueError):
                store.read_audio("../outside.wav")

    def test_valid_wav_proves_full_hash_pcm_duration_and_non_silence(self) -> None:
        audio = _wav()
        digest = hashlib.sha256(audio).hexdigest()
        evidence = validate_formal_wav(
            audio,
            mime_type="audio/wav",
            runtime_sha256=digest,
            download_sha256=digest,
            streamed_sha256=digest,
        )
        self.assertEqual(evidence.readback_sha256, digest)
        self.assertEqual(evidence.sample_rate_hz, 16_000)
        self.assertEqual(evidence.channel_count, 1)
        self.assertEqual(evidence.bits_per_sample, 16)
        self.assertEqual(evidence.duration_ms, 400)
        self.assertGreaterEqual(evidence.normalized_peak_bps, 100)
        self.assertGreaterEqual(evidence.overall_rms_bps, 30)
        self.assertGreaterEqual(evidence.active_window_bps, 500)

    def test_wav_rejects_format_duration_hash_and_silence_mutations(self) -> None:
        valid = _wav()
        digest = hashlib.sha256(valid).hexdigest()
        cases = {
            "mime": (valid, "audio/x-wav", digest),
            "hash": (valid, "audio/wav", "0" * 64),
            "sample-rate": (_wav(sample_rate=8_000), "audio/wav", None),
            "stereo": (_wav(channels=2), "audio/wav", None),
            "eight-bit": (_wav(sample_width=1), "audio/wav", None),
            "short": (_wav(duration_ms=299), "audio/wav", None),
            "silence": (_wav(amplitude=0), "audio/wav", None),
        }
        for label, (audio, mime, forced_hash) in cases.items():
            actual = hashlib.sha256(audio).hexdigest()
            with self.subTest(label=label), self.assertRaises(LearningMediaMaterializationError):
                validate_formal_wav(
                    audio,
                    mime_type=mime,
                    runtime_sha256=forced_hash or actual,
                    download_sha256=actual,
                    streamed_sha256=actual,
                )

    def test_manifest_flattens_multiple_speeches_without_mutating_classroom(self) -> None:
        classroom = _classroom()
        classroom["scenes"][4]["actions"].append(
            {"id": "speech-extra", "type": "speech", "text": "补充讲解"}
        )
        original = copy.deepcopy(classroom)
        manifest = build_formal_speech_manifest(
            classroom,
            build_item_id="build-item-1",
            voice=get_formal_subject_qwen_voice_identity("math"),
        )
        self.assertEqual(classroom, original)
        self.assertEqual(manifest["schemaVersion"], "mira.learning.formal-qwen-audio-sidecar.v1")
        self.assertEqual(manifest["classroomContentSha256"], hashlib.sha256(
            __import__("json").dumps(
                {"stage": classroom["stage"], "scenes": classroom["scenes"]},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest())
        self.assertEqual(len(manifest["segments"]), 11)
        self.assertEqual([item["sceneOrder"] for item in manifest["segments"]], list(range(11)))
        self.assertEqual(
            [item["sceneId"] for item in manifest["segments"]].count("scene-4"),
            2,
        )
        self.assertEqual({item["voiceId"] for item in manifest["segments"]}, {"Ethan"})
        changed = _classroom()
        changed["scenes"][4]["actions"] = [
            action
            for action in changed["scenes"][4]["actions"]
            if action["type"] != "speech"
        ]
        with self.assertRaises(LearningMediaMaterializationError):
            build_formal_speech_manifest(
                changed,
                build_item_id="build-item-1",
                voice=get_formal_subject_qwen_voice_identity("math"),
            )

    def test_asr_normalization_and_similarity_use_nfkc_casefold_letters_and_numbers(self) -> None:
        self.assertEqual(normalize_asr_text("Ａ-b C１！"), "abc1")
        self.assertEqual(normalize_asr_text("你好，同学 2！"), "你好同学2")
        self.assertEqual(asr_similarity_bps("abcdefghij", "abcdefghij"), 10_000)
        self.assertEqual(asr_similarity_bps("abcdefghijklmnopqrst", "abcXefghYjklmnZpqrst"), 8_500)
        self.assertGreaterEqual(asr_similarity_bps("你好，同学！", "你好同学"), 8_500)
        self.assertEqual(asr_similarity_bps("", ""), 0)

    def test_chinese_formal_speech_uses_spoken_pinyin_without_changing_other_subjects(self) -> None:
        source = "声母 ch 和韵母 e 拼成音节 che，再读 a、o、u。"
        self.assertEqual(
            prepare_formal_speech_text(source, subject="chinese"),
            "声母 吃 和韵母 鹅 拼成音节 车，再读 啊、喔、乌。",
        )
        self.assertEqual(
            prepare_formal_speech_text(source, subject="math"),
            source,
        )
        spoken = prepare_formal_speech_text(source, subject="chinese")
        transcribed_with_symbols = "声母 ch 和韵母 e 拼成音节 che，再读 a、o、u。"
        self.assertEqual(
            asr_similarity_bps(
                spoken,
                prepare_formal_speech_text(
                    transcribed_with_symbols, subject="chinese"
                ),
            ),
            10_000,
        )

        classroom = _classroom()
        classroom["scenes"][2]["actions"][0]["text"] = source
        manifest = build_formal_speech_manifest(
            classroom,
            build_item_id="build-item-pinyin",
            voice=get_formal_subject_qwen_voice_identity("chinese"),
        )
        segment = manifest["segments"][2]
        self.assertEqual(
            segment["text"],
            "声母 吃 和韵母 鹅 拼成音节 车，再读 啊、喔、乌。",
        )
        self.assertEqual(
            segment["sourceTextSha256"],
            hashlib.sha256(source.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            segment["speechTextPolicyVersion"],
            "mira.learning.formal-speech-text.v2",
        )

    def test_formal_asr_comparison_keeps_threshold_after_number_canonicalization(self) -> None:
        expected = "比较14和0，再算5+3=8。"
        transcript = "比较十四和零，再算五加三等于八。"
        self.assertEqual(
            prepare_formal_asr_comparison_text(expected, subject="math"),
            prepare_formal_asr_comparison_text(transcript, subject="math"),
        )
        self.assertEqual(
            asr_similarity_bps(
                prepare_formal_asr_comparison_text(expected, subject="math"),
                prepare_formal_asr_comparison_text(transcript, subject="math"),
            ),
            10_000,
        )
        self.assertEqual(
            prepare_formal_asr_comparison_text("14", subject="english"),
            "14",
        )


if __name__ == "__main__":
    unittest.main()
