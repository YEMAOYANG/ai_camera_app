import base64
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path

from courseware.tools.voice import voice_lines


def wav_bytes(text):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(bytes([sum(text.encode()) % 256, 0]) * 8000)
    return stream.getvalue()


def response(text):
    encoded = base64.b64encode(wav_bytes(text)).decode()
    return json.dumps({'data': {'base64': encoded}}).encode()


class VoiceCheckpointTests(unittest.TestCase):
    def test_interrupt_keeps_completed_clip_and_resume_only_calls_missing_line(self):
        lines = [
            {'id': 'first', 'text': 'first line', 'voice': 'Ethan'},
            {'id': 'interrupt', 'text': 'second line', 'voice': 'Ethan'},
        ]
        with tempfile.TemporaryDirectory() as root:
            media = Path(root) / 'media'
            cache = Path(root) / 'voice-cache.json'

            def interrupted_post(url, payload):
                if payload['audioId'] == 'interrupt':
                    raise KeyboardInterrupt()
                return 200, response(payload['text'])

            with self.assertRaises(KeyboardInterrupt):
                voice_lines(lines, media, post=interrupted_post, cache_path=cache,
                            jobs=1, sleep=lambda _: None)

            saved = json.loads(cache.read_text(encoding='utf-8'))
            first_name = saved['first|Ethan|first line']
            self.assertTrue((media / first_name).is_file())

            called = []

            def resumed_post(url, payload):
                called.append(payload['audioId'])
                return 200, response(payload['text'])

            result = voice_lines(lines, media, post=resumed_post, cache_path=cache,
                                 jobs=1, sleep=lambda _: None)
            self.assertEqual(called, ['interrupt'])
            self.assertEqual((result['reused'], result['voiced']), (1, 1))


if __name__ == '__main__':
    unittest.main()
