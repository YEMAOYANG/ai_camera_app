"""A new publication must have a distinct, live, release-bound picture."""
from copy import deepcopy
import hashlib
import io
import json
import multiprocessing
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from core.errors import ApiError
from services.textbook_cover_guard import cover_bytes, verify_textbook_cover


def _register_cover_worker(root, key, raw):
    from scripts import textbook_lesson_cover as covers
    root = Path(root)
    covers.PICTURES = root / 'pictures'
    covers.LISTING = root / 'lesson-pictures.json'
    covers.LOCK = root / 'locks' / 'registration.lock'
    covers.register_cover(key, raw, '测试图片', {})


class _Response:
    def __init__(self, raw):
        self.raw = raw
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limit):
        return self.raw[:limit]


class TextbookCoverGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='textbook-cover-guard-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.student = self.root / 'student-web'
        self.media_root = self.root / 'classrooms'
        self.key = 'a' * 64
        self.release_sha = 'b' * 64
        self.cid = 'tbpub_' + self.key[:24]
        source = io.BytesIO()
        Image.new('RGB', (160, 90), (44, 118, 190)).save(source, 'PNG')
        self.source_raw = source.getvalue()
        self.source_sha = hashlib.sha256(self.source_raw).hexdigest()
        self.source_name = self.source_sha + '.png'
        self.source_path = f'/api/classroom-media/{self.cid}/media/{self.source_name}'
        path = self.media_root / self.cid / 'media' / self.source_name
        path.parent.mkdir(parents=True)
        path.write_bytes(self.source_raw)
        self.cover = cover_bytes(self.source_raw)
        self.cover_sha = hashlib.sha256(self.cover).hexdigest()
        self.src = '/textbooks/course-pictures-v1/' + self.key[:16] + '-' + self.cover_sha[:16] + '.webp'
        self.cover_path = self.student / 'public' / self.src.lstrip('/')
        self.cover_path.parent.mkdir(parents=True)
        self.cover_path.write_bytes(self.cover)
        self.listing = self.student / 'src/features/learning/lesson-pictures.json'
        self.listing.parent.mkdir(parents=True)
        self.item = {'src': self.src, 'alt': '两个不同的教学对象', 'width': 960, 'height': 540,
                     'releaseSha256': self.release_sha, 'sourceSha256': self.source_sha,
                     'sourceMediaPath': self.source_path, 'coverSha256': self.cover_sha}
        self.save({self.key: self.item})
        self.prepared = {'frozen': {'contentKey': self.key}, 'release': {
            'contentKey': self.key, 'sha256': self.release_sha, 'classroomId': self.cid,
            'classroom': {'scenes': [{'content': {'html': '<img src="' + self.source_path + '">'}}]},
            'media': [{'path': self.source_path, 'sha256': self.source_sha,
                       'byteSize': len(self.source_raw), 'mimeType': 'image/png'}]}}
        self.store = Mock()
        self.store.read.return_value = None
        self.chunk_url = '/_next/static/chunks/cover-test.js'
        self.chunk = json.dumps({self.key: {'src': self.src}}).encode()
        chunk_path = self.student / '.next/static/chunks/cover-test.js'
        chunk_path.parent.mkdir(parents=True)
        chunk_path.write_bytes(self.chunk)
        self.responses = {'/learning/textbooks': ('<script src="' + self.chunk_url + '"></script>').encode(),
                          self.chunk_url: self.chunk, self.src: self.cover}
        opener = Mock()
        opener.open.side_effect = lambda req, timeout: _Response(self.responses[url_path(req.full_url)])
        self.opener_patch = patch('services.textbook_cover_guard.build_opener', return_value=opener)
        self.opener_patch.start()
        self.addCleanup(self.opener_patch.stop)

    def save(self, listing):
        self.listing.write_text(json.dumps(listing), encoding='utf-8')

    def verify(self, prepared=None):
        verify_textbook_cover(prepared or self.prepared, media_root=self.media_root, media_store=self.store,
                              student_root=self.student, origin='http://127.0.0.1:3000')

    def test_own_registered_picture_must_be_present_in_the_live_bundle(self):
        self.verify()
        self.store.read.assert_called_once()

    def test_missing_or_unbound_cover_fails(self):
        self.save({})
        with self.assertRaises(ApiError):
            self.verify()
        for field in ('releaseSha256', 'sourceSha256', 'sourceMediaPath', 'coverSha256'):
            item = deepcopy(self.item)
            item.pop(field)
            self.save({self.key: item})
            with self.assertRaises(ApiError, msg=field):
                self.verify()

    def test_changed_release_original_or_cover_is_rejected(self):
        changed = deepcopy(self.prepared)
        changed['release']['sha256'] = 'c' * 64
        with self.assertRaises(ApiError):
            self.verify(changed)
        changed = deepcopy(self.prepared)
        changed['release']['classroom']['scenes'] = []
        with self.assertRaises(ApiError):
            self.verify(changed)
        self.cover_path.write_bytes(self.cover + b'changed')
        with self.assertRaises(ApiError):
            self.verify()

    def test_cover_shared_with_another_course_is_rejected(self):
        other = deepcopy(self.item)
        other['src'] = '/textbooks/course-pictures-v1/another.webp'
        (self.cover_path.parent / 'another.webp').write_bytes(self.cover)
        self.save({self.key: self.item, 'd' * 64: other})
        with self.assertRaises(ApiError):
            self.verify()

    def test_stale_served_bundle_or_changed_served_picture_is_rejected(self):
        self.responses[self.chunk_url] = b'old compiled bundle'
        with self.assertRaises(ApiError):
            self.verify()
        self.responses[self.chunk_url] = self.chunk
        self.responses[self.src] = b'wrong image'
        with self.assertRaises(ApiError):
            self.verify()

    def test_bundle_must_map_this_course_to_this_picture(self):
        unrelated = json.dumps({self.key: {'src': '/old.webp'}, 'other': {'src': self.src}}).encode()
        (self.student / '.next/static/chunks/cover-test.js').write_bytes(unrelated)
        self.responses[self.chunk_url] = unrelated
        with self.assertRaises(ApiError):
            self.verify()

    def test_parallel_cover_registration_keeps_both_entries(self):
        listing = self.root / 'lesson-pictures.json'
        listing.write_text('{}', encoding='utf-8')
        context = multiprocessing.get_context('spawn')
        processes = [context.Process(target=_register_cover_worker, args=(str(self.root), key, self.cover))
                     for key in ('1' * 64, '2' * 64)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(set(json.loads(listing.read_text())), {'1' * 64, '2' * 64})


def url_path(url):
    from urllib.parse import urlsplit
    return urlsplit(url).path


if __name__ == '__main__':
    unittest.main()
