"""A missing/ambiguous paid receipt must never produce a duplicate charge."""
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from scripts import prepare_textbook_journey_audio as audio


class JourneyAudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.teacher = get_formal_subject_qwen_voice_identity('chinese')
        self.text = '抬头看看天。'
        self.frozen = {'texts': [self.text], 'teacher': self.teacher.to_target_payload()}
        self.identity = audio.request_id(self.frozen, self.text)
        self.runtime = Mock()
        self.runtime.get_formal_audio_tts.side_effect = OpenMaicFullRuntimeError('missing', 'missing', status_code=404)

    def create(self):
        return audio.synthesize_one(self.runtime, self.work, self.frozen, self.teacher, self.text)

    def test_lost_receipt_cannot_redispatch_after_timeout(self):
        self.runtime.start_formal_audio_tts.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError): self.create()
        with self.assertRaisesRegex(RuntimeError, 'Uncertain prior dispatch'): self.create()
        self.runtime.start_formal_audio_tts.assert_called_once()

    def test_ambiguous_receipt_does_not_replace_active_pack(self):
        self.runtime.start_formal_audio_tts.return_value = {'status': 'ambiguous', 'requestId': self.identity}
        with self.assertRaisesRegex(RuntimeError, 'no retry dispatched'): self.create()
        folder = self.work / 'active'
        folder.mkdir()
        audio.save(folder / 'manifest.json', {'original': 'preserved'})
        with self.assertRaises(ValueError): audio.compile_pack(self.work, self.frozen, folder)
        self.assertEqual(json.loads((folder / 'manifest.json').read_text()), {'original': 'preserved'})

    def test_verified_success_is_reused_and_installed_with_teacher_identity(self):
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
            wav.writeframes(b'\x01\x00' * 24000)
        data = output.getvalue()
        receipt = {'status': 'succeeded', 'requestId': self.identity,
            'audioSha256': audio.hashlib.sha256(data).hexdigest()}
        self.runtime.start_formal_audio_tts.return_value = receipt
        self.runtime.download_formal_audio_tts.return_value = data
        self.create(); self.create()
        self.runtime.start_formal_audio_tts.assert_called_once()
        self.runtime.download_formal_audio_tts.assert_called_once()
        folder = self.work / 'active'
        self.assertEqual(audio.compile_pack(self.work, self.frozen, folder), 1)
        entry = next(iter(json.loads((folder / 'manifest.json').read_text()).values()))
        self.assertEqual(entry['voice'], 'Serena')
        self.assertEqual(entry['modelId'], 'qwen3-tts-flash')
        self.assertFalse(entry['fallbackUsed'])
        self.assertEqual((folder / entry['file']).read_bytes(), data)

    def test_only_proven_rejection_allows_one_explicit_repair(self):
        evidence = {'requestId': self.identity, 'state': 'ambiguous', 'safeErrorCode': 'provider_rejected',
            'textSha256': audio.hashlib.sha256(self.text.encode()).hexdigest(),
            'classroomContentSha256': audio.digest(self.frozen)}
        self.runtime._request_formal_audio_json.return_value = evidence
        with self.assertRaises(ValueError):
            audio.prepare_failed_repair(self.runtime, self.work, self.frozen, self.identity)
        self.assertEqual(audio.active_request_id(self.work, self.frozen, self.text), self.identity)
        evidence['state'] = 'failed'
        audio.prepare_failed_repair(self.runtime, self.work, self.frozen, self.identity)
        self.assertEqual(audio.active_request_id(self.work, self.frozen, self.text), self.identity + '_repair1')
        self.runtime.start_formal_audio_tts.assert_not_called()


if __name__ == '__main__': unittest.main()
