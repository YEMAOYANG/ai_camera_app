import base64
import hashlib
import io
import json
import struct
import tempfile
import unittest
import wave
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from courseware.tools.voice import VoiceError, _validate_wav, main, voice_lines


def wav(text='x', duration=1):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(bytes([sum(text.encode()) % 256, 0]) * int(duration * 8000))
    return stream.getvalue()


def raw_wav(payload, *, tag=1, channels=1, rate=8000, bits=16, declared=None):
    fmt = struct.pack('<HHIIHH', tag, channels, rate, rate * channels * bits // 8,
                      channels * bits // 8, bits)
    size = len(payload) if declared is None else declared
    return (b'RIFF' + struct.pack('<I', 36 + size) + b'WAVEfmt '
            + struct.pack('<I', len(fmt)) + fmt + b'data' + struct.pack('<I', size) + payload)


def answer(data, nested=True):
    encoded = base64.b64encode(data).decode()
    return json.dumps({'data': {'base64': encoded}} if nested else {'base64': encoded}).encode()


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.media = self.root / 'media'
        self.cache = self.root / 'cache.json'
        self.lines = [{'id': 'a', 'text': 'hello', 'voice': 'Ethan'}]
        self.calls = []

    def post(self, url, payload):
        self.calls.append((url, payload.copy()))
        return 200, answer(wav(payload['text']))

    def run_lines(self, lines=None, **kwargs):
        return voice_lines(self.lines if lines is None else lines, self.media, post=kwargs.pop('post', self.post),
                           cache_path=self.cache, sleep=kwargs.pop('sleep', lambda _: None), **kwargs)

    def test_success_reuse_change_and_payload(self):
        result = self.run_lines()
        name = 'tts-a-' + hashlib.sha256(wav('hello')).hexdigest() + '.wav'
        self.assertEqual(result, {'voiced': 1, 'reused': 0, 'files': {'a': name}})
        self.assertEqual((self.media / name).read_bytes(), wav('hello'))
        self.assertEqual(self.calls, [('http://127.0.0.1:3100/api/generate/tts',
                         {'text': 'hello', 'audioId': 'a', 'ttsProviderId': 'qwen-tts',
                          'ttsModelId': 'qwen3-tts-flash', 'ttsVoice': 'Ethan'})])
        self.calls.clear()
        self.assertEqual(self.run_lines()['reused'], 1)
        self.assertEqual(self.calls, [])
        self.lines[0]['text'] = 'changed'
        self.assertEqual(self.run_lines()['voiced'], 1)
        self.assertFalse((self.media / name).exists())

    def test_missing_and_tampered_cache(self):
        name = self.run_lines()['files']['a']
        (self.media / name).unlink()
        self.assertEqual(self.run_lines()['voiced'], 1)
        (self.media / name).write_bytes(b'tampered')
        self.assertEqual(self.run_lines()['voiced'], 1)

    def test_response_shapes_and_retry(self):
        sleeps = []
        calls = []
        def post(url, payload):
            calls.append(1)
            return (503, b'') if len(calls) == 1 else (200, answer(wav(), nested=False))
        self.assertEqual(self.run_lines(post=post, sleep=sleeps.append)['voiced'], 1)
        self.assertEqual(sleeps, [1])
        self.assertEqual(len(calls), 2)

    def test_failure_keeps_successes_and_order(self):
        lines = [{'id': i, 'text': i, 'voice': 'Ethan'} for i in ('bad1', 'ok', 'bad2')]
        def post(url, payload):
            return (500, b'') if payload['audioId'].startswith('bad') else (200, answer(wav()))
        with self.assertRaises(VoiceError) as caught:
            self.run_lines(lines, post=post)
        self.assertEqual(caught.exception.args[0], 'tts_failed')
        self.assertLess(caught.exception.args[1].index('bad1'), caught.exception.args[1].index('bad2'))
        cache = json.loads(self.cache.read_text())
        self.assertTrue((self.media / cache['ok|Ethan|ok']).exists())

    def test_invalid_wavs(self):
        for data in (b'not RIFF', wav(duration=0.2), wav(duration=61)):
            with self.subTest(data=data[:10]):
                with self.assertRaises(VoiceError) as caught:
                    self.run_lines(post=lambda u, p: (200, answer(data)))
                self.assertEqual(caught.exception.args[0], 'tts_failed')
                self.assertIn('wav_invalid', caught.exception.args[1])

    def test_invalid_lines(self):
        for lines, code in [([{'id': 'a', 'text': 'x', 'voice': 'unknown'}], 'voice_unknown'),
                            ([self.lines[0], self.lines[0]], 'line_invalid'),
                            ([{'id': '../x', 'text': 'x', 'voice': 'Ethan'}], 'line_invalid'),
                            ([{'id': 'a', 'text': ' ', 'voice': 'Ethan'}], 'line_invalid')]:
            with self.subTest(lines=lines), self.assertRaises(VoiceError) as caught:
                self.run_lines(lines)
            self.assertEqual(caught.exception.args[0], code)

    def test_concurrency_and_prefix_ids(self):
        lines = [{'id': i, 'text': i, 'voice': 'Bella'} for i in ('a', 'a-b', 'c', 'd')]
        first = self.run_lines(lines, jobs=1)
        other_media, other_cache = self.root / 'other', self.root / 'other.json'
        second = voice_lines(lines, other_media, post=self.post, cache_path=other_cache, jobs=4)
        self.assertEqual(first, second)
        lines[0]['text'] = 'new'
        self.run_lines(lines)
        self.assertTrue((self.media / first['files']['a-b']).exists())

    def test_streaming_wav_is_stored_exactly(self):
        header = bytes.fromhex(
            '52494646bfffff7f57415645666d74201000000001000100'
            'c05d000080bb000002001000646174619bffff7f')
        data = header + b'\xfd\xff' * 86400
        result = self.run_lines(post=lambda u, p: (200, answer(data)))
        name = 'tts-a-' + hashlib.sha256(data).hexdigest() + '.wav'
        self.assertEqual(result['files']['a'], name)
        self.assertEqual((self.media / name).read_bytes(), data)

    def test_raw_wav_validation(self):
        good = raw_wav(b'\0' * 4800)
        _validate_wav(good)
        padded = good[:12] + b'JUNK' + struct.pack('<I', 1) + b'x\0' + good[12:]
        _validate_wav(padded)
        fmt = good[12:36]
        data = good[36:]
        invalid = [b'NOPE' + good[4:], good[:8] + b'NOPE' + good[12:],
                   good[:12] + data, good[:12] + fmt,
                   raw_wav(b'\0' * 4800, tag=3), raw_wav(b'\0' * 4800, bits=8),
                   raw_wav(b'\0' * 4800, rate=7999), raw_wav(b'\0' * 4800, rate=48001),
                   raw_wav(b'\0' * 4798), raw_wav(b'\0' * (61 * 8000 * 2)),
                   raw_wav(b'\0' * 4801)]
        for item in invalid:
            with self.subTest(header=item[:44]), self.assertRaises(VoiceError) as caught:
                _validate_wav(item)
            self.assertEqual(caught.exception.args[0], 'wav_invalid')

    def test_extensible_pcm(self):
        good = raw_wav(b'\0' * 4800)
        extension = struct.pack('<HHI', 22, 16, 0) + bytes.fromhex('0100000000001000800000aa00389b71')
        fmt = bytearray(good[20:36])
        struct.pack_into('<H', fmt, 0, 0xfffe)
        data = good[:12] + b'fmt ' + struct.pack('<I', 40) + fmt + extension + good[36:]
        _validate_wav(data)
        bad = data[:44] + bytes.fromhex('0300000000001000800000aa00389b71') + data[60:]
        with self.assertRaises(VoiceError):
            _validate_wav(bad)

    def test_main(self):
        source = self.root / 'lines.json'
        source.write_text(json.dumps(self.lines))
        args = ['--lines', str(source), '--media-dir', str(self.media), '--cache', str(self.cache)]
        out, err = io.StringIO(), io.StringIO()
        with patch('courseware.tools.voice.default_post', self.post), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(args), 0)
            source.write_text(json.dumps([{'id': 'a', 'text': 'x', 'voice': 'bad'}]))
            self.assertEqual(main(args), 1)
        self.assertIn('voiced 1, reused 0', out.getvalue())
        self.assertIn('voice_unknown:', err.getvalue())


if __name__ == '__main__':
    unittest.main()
