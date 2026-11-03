import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from courseware.tools import prep


FIXTURES = Path(__file__).parent / 'fixtures'
LISTS = json.loads((FIXTURES / 'prep_public_lists.json').read_bytes())
SINGLE = (FIXTURES / 'prep_details_single_hour.json').read_bytes()
DOUBLE = (FIXTURES / 'prep_details_two_hours.json').read_bytes()
MATH = 'ba9d9c0b-2c1c-4bba-84d7-369fb405bb13'
CHINESE = 'b7062df1-f929-458e-964c-d778f89ca255'
ENGLISH = 'af05bc77-0902-9842-f1b5-37cdfad7c5c8'
CHAPTER = '5cd47ba3-5d21-48a1-9fc8-a41358ecc4bd'


def identity(material=MATH, subject='math', title='整理和复习'):
    return {'officialMaterialId': material, 'subject': subject, 'gradeCode': 'primary_1',
            'volume': 'upper', 'lessonTitle': title}


class FakeFetch:
    def __init__(self):
        self.calls = []
        self.counts = {}
        self.bad = set()
        self.suffix = b''
        self.entries = {key: list(value) for key, value in LISTS['activities'].items()}
        self.details = {json.loads(SINGLE)['id']: SINGLE, json.loads(DOUBLE)['id']: DOUBLE}
        self.details['d7643a2d-f204-5efb-0baf-0d203a35762d'] = SINGLE
        self.urls = {}
        for body in (SINGLE, DOUBLE):
            for resource in json.loads(body)['relations']['national_course_resource']:
                for item in resource.get('ti_items', []):
                    if item.get('ti_file_flag') == 'image' and item.get('ti_format') == 'folder':
                        base = item['ti_storages'][0].replace('r1-ndr-private.', 'r1-ndr.')
                        self.urls[base] = resource['id']

    def __call__(self, url):
        self.calls.append(url)
        def encoded(value):
            return 200, json.dumps(value, ensure_ascii=False).encode()
        if url == prep.MATERIALS_URL:
            return encoded({'urls': ['https://fake/materials']})
        if url == 'https://fake/materials':
            return encoded(LISTS['materials'])
        for material, entries in self.entries.items():
            if url == prep.MATERIAL_URL.format(material):
                return encoded([f'https://fake/{material}'] if entries else [])
            if url == f'https://fake/{material}':
                return encoded(entries)
        for activity, body in self.details.items():
            if url == prep.DETAILS_URL.format(activity):
                return 200, body
        for base, resource_id in self.urls.items():
            if url.startswith(base + '/'):
                number = int(url.rsplit('/', 1)[1][:-4])
                if number > self.counts.get(resource_id, 1):
                    return 404, b''
                if resource_id in self.bad:
                    return 200, b'not jpeg'
                return 200, b'\xff\xd8\xff\xe0' + bytes([number]) + self.suffix
        raise AssertionError(url)


class PrepTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / 'out'
        self.fetch = FakeFetch()
        self.math = identity()
        self.math['officialChapterId'] = CHAPTER

    def run_prep(self, identity_value=None, **kwargs):
        return prep.prep_lesson(identity_value or self.math, self.out, self.fetch, **kwargs)

    def assert_code(self, code, identity_value=None, **kwargs):
        with self.assertRaises(prep.PrepError) as caught:
            self.run_prep(identity_value, **kwargs)
        self.assertEqual(caught.exception.args[0], code)
        return caught.exception

    def test_single_hour_manifest_and_hashes(self):
        details = json.loads(SINGLE)
        course = next(r for r in details['relations']['national_course_resource'] if r['resource_type_code'] == 'coursewares')
        self.fetch.counts[course['id']] = 3
        now = datetime(2026, 1, 2, tzinfo=timezone.utc)
        result = self.run_prep(now=now)
        self.assertEqual(result['schemaVersion'], 'mira.courseware.official-sources.v1')
        self.assertEqual(result['fetchedAt'], now.isoformat())
        self.assertEqual(result['lesson']['detailsSha256'], hashlib.sha256(SINGLE).hexdigest())
        resources = result['classHours'][0]['resources']
        self.assertEqual(len(resources['courseware']['pages']), 3)
        self.assertEqual(resources['video']['status'], 'waived')
        self.assertEqual(len(resources), 5)
        for resource in resources.values():
            for page in resource.get('pages', []):
                path = Path(page['path'])
                self.assertFalse(path.is_absolute())
                body = (self.out / path).read_bytes()
                self.assertEqual(page['sha256'], hashlib.sha256(body).hexdigest())
                self.assertEqual(page['bytes'], len(body))
                self.assertIn('r1-ndr.ykt.cbern.com.cn', page['url'])
        self.assertEqual(json.loads((self.out / 'manifest.json').read_text()), result)
        self.assertFalse(any('.pdf' in url for url in self.fetch.calls))

    def test_two_hours_title_and_singing(self):
        chinese = identity(CHINESE, 'chinese', '2 江南')
        self.fetch.entries[CHINESE].append(dict(self.fetch.entries[CHINESE][1], id='song', resource_type_code='singing'))
        result = self.run_prep(chinese)
        hours = result['classHours']
        self.assertEqual([h['id'] for h in hours], ['lesson_1', 'lesson_2'])
        self.assertNotEqual(hours[0]['resources']['courseware']['resourceId'], hours[1]['resources']['courseware']['resourceId'])
        chinese['classHours'] = ['lesson_2']
        self.assertEqual([h['id'] for h in self.run_prep(chinese)['classHours']], ['lesson_2'])
        chinese['classHours'] = ['lesson_3']
        self.assert_code('class_hour_not_found', chinese)

    def test_ambiguous_and_chapter(self):
        error = self.assert_code('lesson_ambiguous', identity())
        self.assertEqual(len(error.args[1]), 2)
        self.assertEqual(self.run_prep()['lesson']['chapterIds'][-1], CHAPTER)
        missing = dict(self.math, officialChapterId='missing')
        self.assert_code('lesson_not_found', missing)

    def test_material_mismatch(self):
        for changes in ({'gradeCode': 'primary_2'}, {'volume': 'lower'}, {'officialMaterialId': 'unknown'}):
            self.assert_code('material_mismatch', dict(self.math, **changes))

    def test_empty_listing(self):
        result = self.run_prep(identity(ENGLISH, 'english', 'anything'))
        listing = prep.MATERIAL_URL.format(ENGLISH)
        self.assertEqual(result['status'], 'no_official_resources')
        self.assertEqual(result['evidence'], {'listingUrl': listing, 'listingSha256': hashlib.sha256(b'[]').hexdigest()})
        self.assertEqual(self.fetch.calls[-1], listing)
        self.assertEqual([p.name for p in self.out.iterdir()], ['manifest.json'])

    def test_idempotency_and_changed_page(self):
        result = self.run_prep()
        page = self.out / result['classHours'][0]['resources']['courseware']['pages'][0]['path']
        original = page.stat().st_mtime_ns
        self.run_prep()
        self.assertEqual(page.stat().st_mtime_ns, original)
        self.fetch.suffix = b'changed'
        self.assert_code('page_changed')
        self.run_prep(overwrite=True)
        self.assertTrue(page.read_bytes().endswith(b'changed'))

    def test_invalid_or_missing_page(self):
        resource = next(r for r in json.loads(SINGLE)['relations']['national_course_resource'] if r['resource_type_code'] == 'coursewares')
        self.fetch.bad.add(resource['id'])
        self.assert_code('page_not_jpeg')
        self.fetch.bad.clear()
        self.fetch.counts[resource['id']] = 0
        self.assert_code('page_missing')

    def test_absent_resource_and_unparseable_reference(self):
        details = json.loads(DOUBLE)
        details['resource_structure']['relations'][0]['res_ref'] = [
            '$.relations.national_course_resource[0,1]', 'invalid[2,3,4]']
        self.fetch.details[details['id']] = json.dumps(details).encode()
        result = self.run_prep(identity(CHINESE, 'chinese', '江南'))
        resources = result['classHours'][0]['resources']
        self.assertEqual(resources['teachingDesign']['status'], 'absent_in_listing')
        self.assertEqual(resources['video']['status'], 'waived')

    def test_fetch_failure(self):
        def failure(url):
            return 503, b''
        with self.assertRaises(prep.PrepError) as caught:
            prep.prep_lesson(self.math, self.out, failure)
        self.assertEqual(caught.exception.args[0], 'fetch_failed')

    def test_server_error_after_the_first_page_is_not_the_end(self):
        resource = next(r for r in json.loads(SINGLE)['relations']['national_course_resource'] if r['resource_type_code'] == 'coursewares')
        self.fetch.counts[resource['id']] = 5
        def flaky(url):
            return (500, b'') if url.endswith('/2.jpg') else self.fetch(url)
        with self.assertRaises(prep.PrepError) as caught:
            prep.prep_lesson(self.math, self.out, flaky)
        self.assertEqual(caught.exception.args[0], 'fetch_failed')
        self.assertIn('HTTP 500', caught.exception.args[1])
        self.fetch.counts[resource['id']] = 2
        forbidden = lambda url: (403, b'') if url.endswith('/3.jpg') else self.fetch(url)
        self.assertEqual(len(prep.prep_lesson(self.math, self.out, forbidden)['classHours'][0]['resources']['courseware']['pages']), 2)

    def test_main_exit_codes(self):
        path = Path(self.tmp.name) / 'identity.json'
        def run(value):
            path.write_text(json.dumps(value))
            with patch.object(prep, 'default_fetch', self.fetch), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                return prep.main(['--identity', str(path), '--out', str(self.out)])
        self.assertEqual(run(self.math), 0)
        self.assertEqual(run(identity(ENGLISH, 'english', 'anything')), 2)
        self.assertEqual(run(identity()), 1)


if __name__ == '__main__':
    unittest.main()
