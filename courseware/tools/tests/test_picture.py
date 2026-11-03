import base64
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from courseware.tools import picture


def image_bytes(size=(300, 300), format='PNG', mode='RGB'):
    output = io.BytesIO()
    Image.new(mode, size, 'red').save(output, format=format)
    return output.getvalue()


def answer(**result):
    return json.dumps({'success': True, 'result': result}).encode()


class PictureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / 'assets'
        self.cache = self.root / 'cache.json'
        self.requests = [{'key': 'one', 'prompt': 'A cat'}]
        self.data = image_bytes()
        self.calls = []
        self.sleeps = []

    def post(self, url, payload):
        self.calls.append((url, payload))
        return 200, answer(base64=base64.b64encode(self.data).decode())

    def fetch(self, url):
        self.calls.append(url)
        return 200, self.data

    def generate(self, requests=None, post=None, fetch=None, jobs=2):
        return picture.generate_pictures(self.requests if requests is None else requests,
                                         self.assets, post=post or self.post, fetch=fetch or self.fetch,
                                         cache_path=self.cache, jobs=jobs, sleep=self.sleeps.append)

    def test_url_payload_and_conversion(self):
        self.data = image_bytes((400, 300), 'JPEG')
        calls = []
        def post(url, payload):
            calls.append((url, payload))
            return 200, answer(url='https://example.test/image')
        result = self.generate([{'key': 'one', 'prompt': 'A cat', 'aspect': '4:3'}], post=post)
        style = (Path(picture.__file__).parent / 'prompts/picture_style.v1.md').read_text(encoding='utf-8').strip()
        self.assertEqual(calls[0], ('http://127.0.0.1:3100/api/generate/image',
                                    {'prompt': style + '\nA cat', 'aspectRatio': '4:3'}))
        self.assertEqual(self.calls, ['https://example.test/image'])
        self.assertEqual(result['aspects']['one'], 400 / 300)
        with Image.open(self.assets / 'one.png') as image:
            self.assertEqual((image.format, image.mode), ('PNG', 'RGB'))

    def test_base64_resize_and_alpha(self):
        self.data = image_bytes((2000, 1000), mode='RGBA')
        self.generate()
        with Image.open(self.assets / 'one.png') as image:
            self.assertEqual((image.size, image.mode), ((1280, 640), 'RGBA'))
        self.data = image_bytes((256, 300))
        self.generate([{'key': 'two', 'prompt': 'small'}])
        with Image.open(self.assets / 'two.png') as image:
            self.assertEqual(image.size, (256, 300))

    def test_invalid_image_and_url(self):
        for data in (image_bytes((255, 300)), b'not an image'):
            with self.subTest(data=len(data)):
                with self.assertRaises(picture.PictureError) as error:
                    picture._png(data)
                self.assertEqual(error.exception.args[0], 'image_invalid')
        with self.assertRaises(picture.PictureError) as error:
            picture._image_bytes(answer(url='file:///etc/passwd'), self.fetch)
        self.assertEqual(error.exception.args[0], 'image_invalid')

    def test_cache_reuse_and_regeneration(self):
        self.assertEqual(self.generate()['made'], 1)
        self.calls.clear()
        result = self.generate()
        self.assertEqual((result['made'], result['reused'], self.calls), (0, 1, []))
        self.requests[0]['prompt'] = 'A dog'
        self.assertEqual(self.generate()['made'], 1)
        (self.assets / 'one.png').unlink()
        self.assertEqual(self.generate()['made'], 1)
        (self.assets / 'one.png').write_bytes(b'tampered')
        self.assertEqual(self.generate()['made'], 1)

    def test_retry_and_safety(self):
        attempts = []
        def post(url, payload):
            attempts.append(1)
            return (503, b'') if len(attempts) == 1 else self.post(url, payload)
        self.generate(post=post)
        self.assertEqual((len(attempts), self.sleeps), (2, [1]))
        attempts.clear()
        def refusal(url, payload):
            attempts.append(1)
            return 200, json.dumps({'success': False, 'error': 'SensitiveContent'}).encode()
        with self.assertRaises(picture.PictureError) as error:
            self.generate([{'key': 'two', 'prompt': 'x'}], post=refusal)
        self.assertEqual(error.exception.args[0], 'image_failed')
        self.assertEqual(len(attempts), 1)

    def test_partial_failure_is_cached(self):
        def post(url, payload):
            if payload['prompt'].endswith('bad'):
                return 500, b''
            return self.post(url, payload)
        requests = [{'key': 'bad', 'prompt': 'bad'}, {'key': 'good', 'prompt': 'good'},
                    {'key': 'worse', 'prompt': 'bad'}]
        with self.assertRaises(picture.PictureError) as error:
            self.generate(requests, post=post)
        self.assertEqual(error.exception.args[0], 'image_failed')
        self.assertIn('bad:', error.exception.args[1])
        self.assertIn('worse:', error.exception.args[1])
        self.assertTrue((self.assets / 'good.png').exists())
        self.assertEqual(list(json.loads(self.cache.read_text())), ['good'])

    def test_invalid_requests(self):
        cases = [[{'key': 'Bad!', 'prompt': 'x'}], self.requests * 2,
                 [{'key': 'x', 'prompt': ' '}], [{'key': 'x', 'prompt': 'x', 'aspect': '2:1'}],
                 [{'key': 'x', 'prompt': 'x', 'extra': 1}], None]
        for requests in cases:
            with self.subTest(requests=requests), self.assertRaises(picture.PictureError) as error:
                picture.generate_pictures(requests, self.assets, post=self.post, fetch=self.fetch,
                                          cache_path=self.cache, sleep=self.sleeps.append)
            self.assertEqual(error.exception.args[0], 'request_invalid')

    def test_concurrent_results(self):
        requests = [{'key': str(i), 'prompt': str(i)} for i in range(5)]
        first = self.generate(requests, jobs=1)
        self.cache.unlink()
        second = self.generate(requests, jobs=4)
        self.assertEqual(first, second)

    def test_main(self):
        path = self.root / 'requests.json'
        path.write_text(json.dumps(self.requests))
        args = ['--requests', str(path), '--assets', str(self.assets), '--cache', str(self.cache)]
        with patch.object(picture, 'default_post', self.post), patch.object(picture, 'default_fetch', self.fetch):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(picture.main(args), 0)
            self.assertEqual(output.getvalue(), 'made 1, reused 0\n')
            path.write_text('invalid')
            with contextlib.redirect_stderr(io.StringIO()) as error:
                self.assertEqual(picture.main(args), 1)
            self.assertIn('request_invalid:', error.getvalue())


if __name__ == '__main__':
    unittest.main()
