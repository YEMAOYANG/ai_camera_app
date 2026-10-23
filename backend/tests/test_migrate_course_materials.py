"""Current fixed-material migration stays read-only until remote verification."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from PIL import Image

from core.course_storage_config import CourseStorageConfig
from scripts import migrate_course_materials as materials
from services import course_file_store
from services.course_archive_exporter import CourseArchiveError
from services.course_file_store import CourseFileStore


class MemoryRegistry:
    def __init__(self, events):
        self.events, self.entries, self.scopes = events, {}, {}
        self.registered, self.activations = [], []
        self.before_activate = None

    def resolve(self, source, storage_id, expected_sha=None):
        entry = self.entries.get(source)
        return deepcopy(entry) if entry and (expected_sha is None or entry['sha256'] == expected_sha) else None

    def register_scope(self, metadata, files, storage_id, *, activate):
        if activate:
            raise AssertionError('a supplement must register inactive')
        self.events.append('register')
        self.registered.append((deepcopy(metadata), deepcopy(files), storage_id))
        self.scopes[metadata['scopeKey']] = deepcopy(files)

    def activate_missing_heads(self, scope_key, storage_id):
        files = self.scopes[scope_key]
        if self.before_activate:
            self.before_activate(files)
        count = 0
        for item in files:
            if item['sourcePath'] not in self.entries:
                self.entries[item['sourcePath']] = deepcopy(item)
                count += 1
        self.events.append('activate')
        self.activations.append((scope_key, count))
        return {'activated': count}


class MemoryNode:
    def __init__(self, config, events):
        self.config, self.events, self.objects, self.calls = config, events, {}, []
        self.after_upload = None
        self.receipt_change = None

    def upload(self, path):
        self.calls.append(path)
        self.events.append('upload')
        raw = Path(path).read_bytes()
        index = json.loads(raw)
        objects = []
        for item in index['generatedPublicFiles']:
            data = Path(item['localPath']).read_bytes()
            self.objects[item['relativePath']] = data
            objects.append({'objectKey': item['relativePath'], 'sha256': materials.sha(data),
                'byteSize': len(data), 'etag': hashlib.md5(data).hexdigest()})
        receipt = {'complete': True, 'indexSha256': materials.sha(raw), 'storage': {
            'endpoint': self.config.endpoint.rstrip('/'), 'bucket': self.config.bucket,
            'region': self.config.region}, 'objects': objects}
        if self.receipt_change:
            self.receipt_change(receipt)
        if self.after_upload:
            self.after_upload()
        return receipt


class MigrateCourseMaterialsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('MIRA_TASK_TMPDIR'))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / 'backend/data/course-storage'
        self.state.mkdir(parents=True, mode=0o700)
        self.events = []
        self.registry = MemoryRegistry(self.events)
        self.config = CourseStorageConfig(mode='registry', endpoint='http://storage.invalid:9000', bucket='study')
        self.node = MemoryNode(self.config, self.events)
        self.binding = {'courseId': 'current-course', 'courseVersion': 'v1', 'contentKey': 'a' * 64,
            'classroomId': 'tbpub_current', 'sourceDigest': 'b' * 64,
            'sessionId': 'producer-one', 'stageId': 'stage-one', 'sourceKind': 'textbook_release',
            'storageDirectory': '语文/统编版/一年级上册/2026-10-24/图片课',
            'parentArchiveId': 'parent-one', 'parentIndexSha256': 'c' * 64}
        picture = io.BytesIO()
        Image.new('RGB', (2, 3), 'red').save(picture, 'PNG')
        self.picture = picture.getvalue()
        self.picture_source = materials.MATERIAL_ROOT + 'owner-one/mat_picture'
        self.text_source = materials.MATERIAL_ROOT + 'producer-one/mat_text/text.md'
        self.put(self.picture_source, self.picture)
        self.put(self.text_source, '课文材料'.encode())
        self.items = [self.item(self.picture_source, self.picture, 'image/png'),
            self.item(self.text_source, '课文材料'.encode(), 'text/markdown')]
        self.exporter = Mock()
        self.exporter._material_inventory.side_effect = lambda _: self.material_inventory()
        self.store = CourseFileStore(config=self.config, project_root=self.root, repository=self.registry)
        self.root_patch = patch.object(materials, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.memory_patch = patch.object(materials, '_RemoteObject', side_effect=self.remote)
        self.memory_patch.start()
        self.addCleanup(self.memory_patch.stop)
        self.reader_patch = patch.object(course_file_store, '_RemoteObject', side_effect=self.remote)
        self.reader_patch.start()
        self.addCleanup(self.reader_patch.stop)
        self.space_patch = patch.object(materials, '_require_private_space')
        self.space_patch.start()
        self.addCleanup(self.space_patch.stop)

    def put(self, relative, raw):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return path

    @staticmethod
    def item(source, raw, mime):
        return {'sourcePath': source, 'mimeType': mime, 'displayName': '课文原稿',
            'byteSize': len(raw), 'sha256': materials.sha(raw)}

    def material_inventory(self):
        return {'schemaVersion': 'mira.course-material-inventory.v1', 'materials': deepcopy(self.items),
            'dependencySha256': materials.sha(materials.json_bytes(self.items))}

    def remote(self, config, locator, size):
        raw = self.node.objects[locator['objectKey']]
        if len(raw) != size:
            raise ValueError('fixture_remote_size_changed')
        outer = self

        class Range:
            def __init__(self):
                self.size = size
                self.etag = locator['etag']
                self.url = 'memory://' + str(outer.root) + '/' + locator['objectKey'] + '/' + materials.sha(raw)

            def get(self, start=0, end=None, *, whole=False):
                outer.events.append('remote-read')
                return raw[start:len(raw) if end is None else end]

        return Range()

    def inventory(self):
        return materials.inventory(self.exporter, deepcopy(self.binding), self.store)

    def apply(self, plan=None, raws=None, bindings=None):
        if plan is None:
            plan, raws = self.inventory()
        with patch.object(materials, 'selected_bindings', return_value=bindings or [self.binding]):
            return materials.apply(plan, raws, database=object(), config=self.config,
                registry=self.registry, exporter=self.exporter, store=self.store, client=self.node,
                state_root=self.state)

    def parent_job(self, name='parent', *, binding=None, priority=0, status='complete'):
        binding = binding or self.binding
        directory = self.state / 'parent-evidence' / name
        directory.mkdir(parents=True)
        index = {k: binding[k] for k in ('courseId', 'courseVersion', 'classroomId', 'sourceDigest')}
        index.update(complete=True, objectDirectory=binding['storageDirectory'], archiveId=name)
        index_raw = materials.json_bytes(index)
        index_path = directory / 'index.json'
        index_path.write_bytes(index_raw)
        receipt = {'complete': True, 'indexSha256': materials.sha(index_raw)}
        receipt_raw = materials.json_bytes(receipt)
        receipt_path = directory / 'receipt.json'
        receipt_path.write_bytes(receipt_raw)
        job = {'priority': priority, 'status': status,
            'identity': {k: binding[k] for k in ('courseId', 'courseVersion', 'sourceDigest', 'sourceKind')},
            'export': {'indexPath': str(index_path), 'indexSha256': materials.sha(index_raw)},
            'receiptPath': str(receipt_path), 'receiptSha256': materials.sha(receipt_raw)}
        path = self.put('backend/data/course-storage/archive-queue/items/' + name + '.json', materials.json_bytes(job))
        return path, job

    def selection(self, current=None):
        basic = {k: v for k, v in self.binding.items() if k not in {'storageDirectory', 'parentArchiveId', 'parentIndexSha256'}}
        with patch.object(materials, 'current_courses', return_value=current or {('current-course', 'v1'): basic}):
            return materials.selected_bindings(object(), self.state)

    def test_current_frozen_parent_only_excludes_history_and_unfinished_jobs(self):
        self.parent_job()
        old = {**self.binding, 'courseVersion': 'old', 'sourceDigest': 'd' * 64}
        self.parent_job('historical', binding=old)
        self.parent_job('history-priority', priority=2)
        self.parent_job('not-finished', status='pending')
        result = self.selection()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['parentArchiveId'], 'parent')
        self.assertEqual(result[0]['sessionId'], 'producer-one')
        self.assertEqual(result[0]['stageId'], 'stage-one')

    def test_inventory_cli_constructs_real_transport_without_connecting_or_uploading(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        transport_type = materials.NodeArchiveClient
        with patch.object(materials.sys, 'argv', ['migrate_course_materials.py']), \
                patch.object(materials.AppConfig, 'from_env', return_value=Mock(DATABASE_URL='fixture-only')), \
                patch.object(materials.CourseStorageConfig, 'from_env', return_value=self.config), \
                patch.object(materials, 'Database', return_value=object()), \
                patch.object(materials, 'CourseStorageRepository', return_value=self.registry), \
                patch.object(materials, 'CourseFileStore', return_value=self.store), \
                patch.object(materials, 'CourseArchiveExporter', return_value=self.exporter), \
                patch.object(materials, 'selected_bindings', return_value=[]), \
                patch.object(materials, 'NodeArchiveClient', wraps=transport_type) as constructor, \
                patch.object(transport_type, '_run', side_effect=AssertionError('inventory must not start Node')), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            code = materials.main()
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertEqual(stderr.getvalue(), '')
        self.assertEqual(json.loads(stdout.getvalue()), {'ok': True, 'applied': False,
            'selectedArchives': 0, 'uniqueMaterialFiles': 0})
        constructor.assert_called_once_with(project_root=self.root,
            node=os.environ.get('COURSE_ARCHIVE_NODE', 'node'))
        self.assertEqual(self.node.calls, [])
        self.assertEqual(self.registry.registered, [])

    def test_published_parent_missing_duplicate_or_source_changed_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'published_parent_archive_missing'):
            self.selection()
        path, job = self.parent_job()
        job['identity']['sourceDigest'] = 'd' * 64
        path.write_bytes(materials.json_bytes(job))
        with self.assertRaisesRegex(ValueError, 'current_source_changed'):
            self.selection()
        path.unlink()
        self.parent_job('one')
        self.parent_job('two')
        with self.assertRaisesRegex(ValueError, 'current_archive_ambiguous'):
            self.selection()

    def test_parent_index_and_receipt_tampering_are_rejected(self):
        path, job = self.parent_job()
        index = Path(job['export']['indexPath'])
        raw = index.read_bytes()
        index.write_bytes(raw + b' ')
        with self.assertRaisesRegex(ValueError, 'parent_index_changed'):
            self.selection()
        index.write_bytes(raw)
        Path(job['receiptPath']).write_bytes(b'{"complete":false}')
        with self.assertRaisesRegex(ValueError, 'parent_receipt_changed'):
            self.selection()

    def test_inventory_passes_only_the_frozen_producer_and_exact_material_paths(self):
        self.put('openmaic-runtime/.runtime/OpenMAIC/data/usage/do-not-archive.json', b'{}')
        self.put(materials.MATERIAL_ROOT + 'unrelated/source', b'not selected')
        plan, raws = self.inventory()
        self.assertEqual(self.exporter._material_inventory.call_args.args[0], {
            'sessionId': 'producer-one', 'stageId': 'stage-one', 'bindingKind': 'frozen_authoring'})
        self.assertEqual(set(raws), {self.picture_source, self.text_source})
        self.assertEqual({r['sourcePath'] for r in plan['files']}, set(raws))

    def test_source_metadata_format_and_png_corruption_are_rejected(self):
        original = deepcopy(self.items)
        for field, value, reason in [('sha256', '0' * 64, 'source_digest_mismatch'),
                ('byteSize', len(self.picture) + 1, 'source_length_mismatch'),
                ('mimeType', 'application/pdf', 'course_material_pdf_invalid')]:
            with self.subTest(field=field):
                self.items = deepcopy(original)
                self.items[0][field] = value
                with self.assertRaisesRegex((ValueError, CourseArchiveError), reason):
                    self.inventory()
        self.items = deepcopy(original)
        self.put(self.picture_source, b'\x89PNG\r\n\x1a\nnot-a-real-picture')
        with self.assertRaises(CourseArchiveError):
            self.inventory()
        self.assertEqual(self.node.calls, [])

    def test_missing_source_root_escape_links_and_duplicate_members_are_rejected(self):
        original = deepcopy(self.items)
        self.items = [{**original[0], 'sourcePath': 'output/unrelated'}]
        with self.assertRaisesRegex(ValueError, 'outside_library'):
            self.inventory()
        self.items = original + [deepcopy(original[0])]
        with self.assertRaisesRegex(ValueError, 'inventory_duplicate'):
            self.inventory()
        self.items = original
        source = self.root / self.picture_source
        saved = source.with_name('saved-original')
        source.rename(saved)
        with self.assertRaises(FileNotFoundError):
            self.inventory()
        source.symlink_to(saved)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.inventory()

    def test_prepare_keeps_originals_and_writes_exact_private_repeatable_zip(self):
        plan, raws = self.inventory()
        before = {p: (self.root / p).read_bytes() for p in raws}
        path, index, manifest, raw = materials.prepare(plan, raws, self.state)
        self.assertEqual(materials.prepare(plan, raws, self.state)[1], index)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        with zipfile.ZipFile(index['zip']['path']) as archive:
            self.assertEqual(set(archive.namelist()), {'manifest.json'} | {'原稿/' + p for p in raws})
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read('manifest.json'), raw)
            for p, content in before.items():
                self.assertEqual(archive.read('原稿/' + p), content)
                self.assertEqual((self.root / p).read_bytes(), content)
        self.assertEqual(manifest['sourceKind'], materials.SOURCE_KIND)
        self.assertTrue(all('/制作材料-' in item['relativePath'] for item in index['generatedPublicFiles']))

    def test_zip_extra_entry_duplicate_changed_manifest_and_symlink_are_rejected(self):
        plan, raws = self.inventory()
        _, index, manifest, raw = materials.prepare(plan, raws, self.state)
        original = Path(index['zip']['path']).read_bytes()
        for variant in ('extra', 'duplicate', 'manifest', 'source', 'symlink'):
            with self.subTest(variant=variant):
                output = io.BytesIO()
                with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(output, 'w') as target:
                    for info in source.infolist():
                        content = source.read(info)
                        if variant == 'manifest' and info.filename == 'manifest.json':
                            content += b' '
                        elif variant == 'source' and info.filename != 'manifest.json':
                            content = b'x' * len(content)
                        if variant == 'symlink' and info.filename != 'manifest.json':
                            info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        target.writestr(info, content)
                    if variant == 'extra':
                        target.writestr('../unrelated', b'not a course source')
                    if variant == 'duplicate':
                        with self.assertWarns(UserWarning):
                            target.writestr('manifest.json', raw)
                with self.assertRaisesRegex(ValueError, 'materials_zip_'):
                    materials.verify_zip(zipfile.ZipFile(io.BytesIO(output.getvalue())), manifest, raw)

    def test_success_reads_remote_zip_before_inactive_registration_then_reads_every_head(self):
        before = {p: (self.root / p).read_bytes() for p in (self.picture_source, self.text_source)}
        result = self.apply()
        self.assertTrue(result['complete'])
        self.assertEqual(result['newHeads'], 2)
        self.assertLess(self.events.index('upload'), self.events.index('remote-read'))
        self.assertLess(self.events.index('remote-read'), self.events.index('register'))
        self.assertLess(self.events.index('register'), self.events.index('activate'))
        metadata, files, _ = self.registry.registered[0]
        self.assertEqual(metadata['parentArchiveId'], 'parent-one')
        self.assertEqual({f['sourcePath'] for f in files}, set(before))
        for source, raw in before.items():
            self.assertEqual((self.root / source).read_bytes(), raw)
            self.assertEqual(self.store.read_bytes(self.root / source), raw)
        self.assertTrue(list((self.state / 'archives').glob('*/registered.json')))

    def test_bad_upload_receipt_never_registers(self):
        for name, change in [('complete', lambda r: r.update(complete=False)),
                ('index', lambda r: r.update(indexSha256='0' * 64)),
                ('storage', lambda r: r['storage'].update(bucket='different')),
                ('zip-sha', lambda r: r['objects'][0].update(sha256='0' * 64))]:
            with self.subTest(field=name):
                self.node.receipt_change = change
                with self.assertRaisesRegex(ValueError, 'upload_not_verified|remote_zip_unverified'):
                    self.apply()
                self.assertEqual(self.registry.registered, [])

    def test_remote_member_corruption_never_registers(self):
        def corrupt():
            key = next(k for k in self.node.objects if k.endswith('.zip'))
            output = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(self.node.objects[key])) as source, zipfile.ZipFile(output, 'w',
                    compression=zipfile.ZIP_DEFLATED) as target:
                for info in source.infolist():
                    raw = source.read(info)
                    target.writestr(info, raw if info.filename == 'manifest.json' else b'x' * len(raw))
            self.node.objects[key] = output.getvalue()
        self.node.after_upload = corrupt
        with self.assertRaises((ValueError, zipfile.BadZipFile)):
            self.apply()
        self.assertEqual(self.registry.registered, [])

    def test_binding_dependency_and_source_changes_after_upload_block_registration(self):
        for variant in ('binding', 'dependency', 'source'):
            with self.subTest(variant=variant):
                plan, raws = self.inventory()
                if variant == 'binding':
                    responses = [[self.binding], []]
                    with patch.object(materials, 'selected_bindings', side_effect=responses), \
                            self.assertRaisesRegex(ValueError, 'current_binding_changed'):
                        materials.apply(plan, raws, database=object(), config=self.config,
                            registry=self.registry, exporter=self.exporter, store=self.store,
                            client=self.node, state_root=self.state)
                elif variant == 'dependency':
                    self.node.after_upload = lambda: self.items.append(self.item(
                        materials.MATERIAL_ROOT + 'producer-one/new-source', b'new', 'text/plain'))
                    with self.assertRaisesRegex(ValueError, 'current_dependencies_changed'):
                        self.apply(plan, raws)
                    self.items.pop()
                else:
                    source = self.root / self.text_source
                    original = source.read_bytes()
                    self.node.after_upload = lambda: source.write_bytes(b'changed')
                    with self.assertRaisesRegex(ValueError, 'source_changed'):
                        self.apply(plan, raws)
                    source.write_bytes(original)
                self.node.after_upload = None
                self.assertEqual(self.registry.registered, [])

    def test_existing_same_sha_reuses_verified_remote_locator_without_rezipping(self):
        self.apply()
        old_locator = deepcopy(self.registry.entries[self.picture_source]['locator'])
        (self.root / self.picture_source).unlink()
        (self.root / self.text_source).unlink()
        plan, raws = self.inventory()
        self.assertEqual(raws, {})
        self.assertTrue(all(f['disposition'] == 'registered' for f in plan['files']))
        _, index, _, _ = materials.prepare(plan, raws, self.state)
        with zipfile.ZipFile(index['zip']['path']) as archive:
            self.assertEqual(archive.namelist(), ['manifest.json'])
        result = self.apply(plan, raws)
        self.assertEqual(result['newHeads'], 0)
        self.assertEqual(self.registry.entries[self.picture_source]['locator'], old_locator)
        self.assertFalse((self.root / self.picture_source).exists())

    def test_same_plan_retry_is_idempotent_and_preserves_original_heads(self):
        plan, raws = self.inventory()
        self.assertEqual(self.apply(plan, raws)['newHeads'], 2)
        heads = deepcopy(self.registry.entries)
        receipt_path = next((self.state / 'archives').glob('*/registered.json'))
        receipt = receipt_path.read_bytes()
        self.assertEqual(self.apply(plan, raws)['newHeads'], 0)
        self.assertEqual(self.registry.entries, heads)
        self.assertEqual(receipt_path.read_bytes(), receipt)
        self.assertEqual(json.loads(receipt)['newHeads'], 2)

    def test_concurrent_different_head_is_never_overwritten(self):
        def concurrent(files):
            self.registry.entries[self.picture_source] = {**deepcopy(next(
                f for f in files if f['sourcePath'] == self.picture_source)), 'sha256': 'f' * 64}
        self.registry.before_activate = concurrent
        with self.assertRaisesRegex(ValueError, 'current_head_changed'):
            self.apply()
        self.assertEqual(self.registry.entries[self.picture_source]['sha256'], 'f' * 64)
        self.assertFalse(list((self.state / 'archives').glob('*/registered.json')))
        self.assertEqual((self.root / self.picture_source).read_bytes(), self.picture)

    def test_concurrent_same_sha_is_idempotent(self):
        self.registry.before_activate = lambda files: self.registry.entries.update({
            f['sourcePath']: deepcopy(f) for f in files})
        result = self.apply()
        self.assertTrue(result['complete'])
        self.assertEqual(result['newHeads'], 0)

    def test_current_courses_sql_filters_retired_unreleased_and_noncurrent_previews(self):
        connection = sqlite3.connect(':memory:')
        self.addCleanup(connection.close)
        connection.row_factory = sqlite3.Row
        connection.create_function('JSON_UNQUOTE', 1, lambda value: value)
        connection.executescript('''
            CREATE TABLE learning_courses(id,version,status,quality_status,retired_at);
            CREATE TABLE learning_textbook_revisions(edition_id,revision_id,retired_at);
            CREATE TABLE learning_textbook_course_builds(content_key,course_id,course_version,
                edition_id,revision_id,status,input_json,review_json);
            CREATE TABLE learning_textbook_course_previews(preview_key,classroom_id,classroom_sha256,
                edition_id,revision_id,status,input_json);
        ''')
        for suffix, course_retired, revision_retired, quality, build_status in [
                ('live', None, None, 'released', 'published'), ('retired', 1, None, 'released', 'published'),
                ('old-revision', None, 1, 'released', 'published'), ('unreleased', None, None, 'pending', 'published'),
                ('draft', None, None, 'released', 'draft')]:
            connection.execute('INSERT INTO learning_courses VALUES(?,?,?,?,?)',
                (suffix, 'v1', 'published', quality, course_retired))
            connection.execute('INSERT INTO learning_textbook_revisions VALUES(?,?,?)',
                (suffix, 'r1', revision_retired))
            connection.execute('INSERT INTO learning_textbook_course_builds VALUES(?,?,?,?,?,?,?,?)',
                (suffix * 8, suffix, 'v1', suffix, 'r1', build_status,
                 json.dumps({'previewKey': suffix}), json.dumps({'release': {'sha256': 'b' * 64}})))
            connection.execute('INSERT INTO learning_textbook_course_previews VALUES(?,?,?,?,?,?,?)',
                (suffix, 'author-' + suffix, 'c' * 64, suffix, 'r1', 'complete',
                 json.dumps({'authoring': {'sessionId': 'producer-' + suffix, 'stageId': 'stage-' + suffix}})))
        for name, state, revision in [('saved', 'preview_ready', 'live'), ('review', 'review_required', 'live'),
                ('dead', 'preview_ready', 'old-revision'), ('closed', 'archived', 'live')]:
            connection.execute('INSERT INTO learning_textbook_course_previews VALUES(?,?,?,?,?,?,?)',
                (name, 'preview-' + name, 'd' * 64, revision, 'r1', state, '{}'))

        @contextmanager
        def reader(_):
            yield connection

        with patch.object(materials, 'read_only_connection', reader), \
                patch.object(materials, '_other_published_courses', return_value=[]):
            result = materials.current_courses(object())
        self.assertEqual(set(result), {('live', 'v1'), ('textbook-preview:saved', 'saved-' + 'd' * 16),
            ('textbook-preview:review', 'saved-' + 'd' * 16)})
        self.assertEqual(result[('live', 'v1')]['sessionId'], 'producer-live')
        self.assertEqual(result[('live', 'v1')]['stageId'], 'stage-live')


if __name__ == '__main__':
    unittest.main()
