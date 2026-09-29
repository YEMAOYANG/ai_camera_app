"""Run after preparing the sample bundle; binds an ephemeral loopback port."""
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from uuid import uuid4
import wave

from scripts.serve_textbook_sample import ROOT, make_server


@unittest.skipUnless((ROOT / 'output/tiandiren-play-v2/assets.json').exists(), 'Prepare local sample assets first')
class SampleHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.bundle = ROOT / 'output/tiandiren-play-v2'
        cls.server = make_server(cls.bundle, 0, Path(cls.temp.name) / 'http-test.sqlite3')
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.host = f'127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def call(self, path, body=None, cookie=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        request_headers = {'Origin': 'http://' + self.host, 'Content-Type': 'application/json'}
        if cookie:
            request_headers['Cookie'] = cookie
        request_headers.update(headers or {})
        conn.request('POST' if body is not None else 'GET', path,
                     json.dumps(body) if body is not None else None, request_headers)
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def session(self):
        status, headers, body = self.call('/api/session')
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie']
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)
        return cookie.split(';')[0], json.loads(body)

    def test_player_assets_and_private_file_boundary(self):
        for path, mime in [('/', 'text/html'), ('/lesson.js', 'text/javascript'), ('/lesson.css', 'text/css'), ('/assets/garden', 'image/webp')]:
            status, headers, body = self.call(path)
            self.assertEqual(status, 200)
            self.assertTrue(headers['Content-Type'].startswith(mime))
            self.assertGreater(len(body), 100)
            self.assertIn("frame-ancestors 'self'", headers['Content-Security-Policy'])
        for path in ['/lesson.json', '/assets/../lesson.json', '/api/answers', '/assets/unknown']:
            self.assertEqual(self.call(path)[0], 404)

    def test_host_origin_and_non_json_writes_rejected(self):
        cookie, state = self.session()
        request = {'action': 'start', 'choice': 'check', 'revision': state['revision'], 'requestId': str(uuid4())}
        self.assertEqual(self.call('/api/action', request, cookie, {'Origin': 'https://unrelated.example'})[0], 403)
        self.assertEqual(self.call('/api/session', headers={'Host': 'unrelated.example'})[0], 403)
        self.assertEqual(self.call('/api/action', request, cookie, {'Content-Type': 'text/plain'})[0], 400)
        self.assertEqual(json.loads(self.call('/api/session', cookie=cookie)[2])['phase'], 'welcome')

    def test_question_answers_private_until_submit_and_idempotent(self):
        cookie, state = self.session()
        start = {'action': 'start', 'choice': 'check', 'revision': state['revision'], 'requestId': str(uuid4())}
        first = self.call('/api/action', start, cookie)
        self.assertEqual(first[0], 200)
        question = json.loads(first[2])
        self.assertNotIn('answer', question)
        self.assertNotIn('answer', question['question'])
        self.assertEqual(self.call('/api/action', start, cookie)[2], first[2])
        submitted = {'action': 'choose', 'choice': 'B', 'revision': question['revision'], 'requestId': str(uuid4())}
        response = self.call('/api/action', submitted, cookie)
        self.assertFalse(json.loads(response[2])['correct'])
        self.assertEqual(json.loads(response[2])['answer'], 'A')
        self.assertEqual(self.call('/api/action', submitted, cookie)[2], response[2])
        self.assertEqual(self.call('/api/action', {**submitted, 'choice': 'A'}, cookie)[0], 409)

    def test_reports_are_session_scoped(self):
        one, state = self.session()
        two, _ = self.session()
        self.call('/api/action', {'action': 'start', 'choice': 'check', 'revision': 0, 'requestId': str(uuid4())}, one)
        self.call('/api/action', {'action': 'choose', 'choice': 'A', 'revision': 1, 'requestId': str(uuid4())}, one)
        self.assertEqual(json.loads(self.call('/api/report', cookie=one)[2])['check']['answered'], 1)
        self.assertEqual(json.loads(self.call('/api/report', cookie=two)[2])['check']['answered'], 0)

    def test_all_bundled_audio_is_nonempty_and_allowlisted_bytes_match(self):
        manifest = json.loads((self.bundle / 'assets.json').read_text())
        count = 0
        for key, item in manifest['assets'].items():
            status, _, data = self.call('/assets/' + key)
            self.assertEqual(status, 200, key)
            self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'], key)
            if item['mimeType'] == 'audio/wav':
                with wave.open(str(self.bundle / item['file'])) as audio:
                    self.assertGreater(audio.getnframes(), audio.getframerate() * .2, key)
                    frames = audio.readframes(audio.getnframes())
                    self.assertGreater(len(set(frames)), 20, key)
                count += 1
        self.assertEqual(count, 101)


if __name__ == '__main__':
    unittest.main()
