from copy import deepcopy
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave
import zipfile

from core.course_storage_config import CourseStorageConfig
from scripts import complete_course_storage_activities as activity
from tests.test_complete_course_storage_registry import Registry, Node


class CompleteCourseStorageActivitiesTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('MIRA_TASK_TMPDIR'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.registry = Registry()
        self.config = CourseStorageConfig(mode='registry', endpoint='http://storage.invalid:9000', bucket='study')
        self.remote = {}
        self.store = SimpleNamespace(config=self.config, read_bytes=Mock(side_effect=self.read_remote))
        self.identity = {'contentKey': 'a' * 64, 'courseId': 'textbook-fixture', 'courseVersion': 'saved-1',
            'classroomId': 'tbpub_fixture', 'originalSourceDigest': 'd' * 64,
            'frozenInputSha256': 'e' * 64, 'frozenReviewSha256': 'f' * 64}
        self.release = {'sha256': 'd' * 64}
        self.current = [self.identity]
        self.directory = '语文/统编版/一年级上册/2026-10-23/活动课'
        question = {'prompt': '请点天空', 'options': [{'value': 'A', 'label': '天空'}, {'value': 'B', 'label': '地面'}],
            'hints': ['向上看', '再看看', '点蓝天'], 'explanation': '上面是天空'}
        plan = {'id': 'activity-fixture', 'releaseSha256': self.release['sha256'],
            'skills': {'sky': {'word': '天', 'hints': question['hints'], 'explanation': question['explanation']}}}
        flow = {'bank': {'sky': [question]}, 'probes': {'sky': question}}
        self.spec = SimpleNamespace(plan=plan, flow=flow, renderer='tiandiren', audio_pack='audio-v2')
        self.put(activity.ACTIVITIES / 'tiandiren.v1.json', activity.json_bytes(plan))
        self.put(activity.ACTIVITIES / 'tiandiren.journey.v2.json', activity.json_bytes(flow))
        self.put(activity.ACTIVITIES / 'tiandiren.visuals.v1.json', b'{"pictures":"fixture"}')
        registry = {'definitions': [{'plan': {'file': 'tiandiren.v1.json', 'sha256': activity.sha(activity.json_bytes(plan))},
            'flow': {'file': 'tiandiren.journey.v2.json', 'sha256': activity.sha(activity.json_bytes(flow))}}]}
        self.put(activity.ACTIVITIES / 'registry.v1.json', activity.json_bytes(registry))
        nav = {'schemaVersion': 'navigation-fixture', 'cues': {'continue': '继续试试', 'done': '完成啦'}}
        self.put(activity.NAVIGATION_POLICY, activity.json_bytes(nav))
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as clip:
            clip.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            clip.writeframes(b'\0\0' * 100)
        self.wav = buffer.getvalue()
        self.manifests = {}
        for pack, texts in [('audio-v2', activity.allowed_texts(self.spec)), ('navigation-audio-v1', activity.navigation_texts(nav))]:
            manifest = {}
            for text in sorted(texts):
                asset = activity.journey.audio_id(text) + '.wav'
                self.put(activity.ACTIVITIES / pack / 'qwen-fixture' / asset, self.wav)
                manifest[asset] = {'text': text, 'file': 'qwen-fixture/' + asset, 'sha256': activity.sha(self.wav),
                    'bytes': len(self.wav), 'providerId': 'qwen-tts', 'fallbackUsed': False}
            unused = '0' * 24 + '.wav'
            manifest[unused] = {'text': '历史不用录音', 'file': 'unused/' + unused, 'sha256': activity.sha(b'old'),
                'bytes': 3, 'providerId': 'qwen-tts', 'fallbackUsed': False}
            self.put(activity.ACTIVITIES / pack / 'unused' / unused, b'old')
            self.put(activity.ACTIVITIES / pack / 'manifest.json', activity.json_bytes(manifest))
            self.manifests[pack] = manifest
        self.target = self.root / 'backend/data/course-storage/archives/activity-fixture'
        self.node = Node(self.root, self.config)
        self.plan = self.inventory()

    def put(self, relative, raw):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return target

    def read_remote(self, path, *, expected_sha256=None, expected_bytes=None):
        raw = self.remote.get(Path(path).relative_to(self.root).as_posix())
        if raw is not None:
            self.assertEqual(activity.sha(raw), expected_sha256)
            self.assertEqual(len(raw), expected_bytes)
        return raw

    def inventory(self):
        return activity.inventory_for_course(self.root, self.identity, self.release, self.directory, self.current,
            self.registry, self.store, spec=self.spec, all_specs=[self.spec])

    def prepare(self, plan=None):
        with patch.object(activity.os, 'statvfs', return_value=SimpleNamespace(f_bavail=2 ** 50, f_frsize=1)):
            return activity.prepare_supplement(plan or self.plan, self.root, self.target, registry=self.registry, store=self.store)

    def transfer(self, **kwargs):
        return activity.verify_and_register(self.target / 'index.json', binding_loader=lambda binding: self.plan['binding'],
            registry=self.registry, config=self.config, node_client=self.node, store=self.store,
            remote_object_read=lambda r: self.node.objects[r['objectKey']],
            remote_zip_factory=lambda r: io.BytesIO(self.node.objects[r['objectKey']]), **kwargs)

    def entry(self, record, source=None):
        return {'sourcePath': source or record['sourcePath'], **{k: record[k] for k in ('sha256', 'byteSize', 'mimeType')},
                'locator': {'kind': 'object', 'objectKey': 'verified/voice.wav', 'etag': 'fixture-etag'}}

    def test_only_compiler_selected_wavs_and_enumerated_small_rules_are_selected(self):
        paths = {r['sourcePath'] for r in self.plan['files']}
        self.assertFalse(any('/unused/' in p for p in paths))
        self.assertNotIn(activity.NAVIGATION_POLICY.as_posix(), paths)
        self.assertEqual(len(self.plan['binding']['ruleFiles']), 4)
        self.assertEqual({p['audioPack']: len(p['allowedAssets']) for p in self.plan['binding']['packs']},
                         {'audio-v2': len(activity.allowed_texts(self.spec)), 'navigation-audio-v1': 2})
        self.assertEqual(self.plan['binding']['currentPublishedSetSha256'], activity.digest(self.current))
        self.assertEqual(self.plan['blocked'], [])

    def test_original_manifests_are_unchanged_and_zip_has_exact_selected_members(self):
        original = (self.root / activity.ACTIVITIES / 'audio-v2/manifest.json').read_bytes()
        index = self.prepare()
        self.assertEqual(index, self.prepare())
        manifest = json.loads(Path(index['manifestPath']).read_bytes())
        with zipfile.ZipFile(index['zip']['path']) as archive:
            self.assertEqual(set(archive.namelist()), {'manifest.json'} | {r['archivePath'] for r in manifest['files']})
            self.assertEqual(archive.read('原稿/' + (activity.ACTIVITIES / 'audio-v2/manifest.json').as_posix()), original)
            self.assertFalse(any('/unused/' in p for p in archive.namelist()))
        self.assertNotEqual(index['sourceDigest'], self.release['sha256'])
        self.assertEqual(Path(index['indexPath']).stat().st_mode & 0o777, 0o600)
        self.assertTrue(all('/互动资源补充-' in e['relativePath'] for e in index['generatedPublicFiles']))

    def test_missing_required_audio_blocks_prepare_without_touching_originals(self):
        wav = next(r for r in self.plan['files'] if r['mimeType'] == 'audio/wav')
        path = self.root / wav['sourcePath']
        path.unlink()
        plan = self.inventory()
        self.assertEqual(len(plan['blocked']), 1)
        with self.assertRaisesRegex(activity.SupplementError, 'blocked'):
            self.prepare(plan)
        self.assertFalse(self.target.exists())

    def test_missing_allowed_manifest_entry_and_rule_path_escape_are_rejected(self):
        file = self.root / activity.ACTIVITIES / 'audio-v2/manifest.json'
        saved = file.read_bytes()
        value = json.loads(saved)
        value.pop(self.plan['binding']['packs'][0]['allowedAssets'][0])
        file.write_bytes(activity.json_bytes(value))
        with self.assertRaisesRegex(activity.SupplementError, 'manifest_missing'):
            self.inventory()
        file.write_bytes(saved)
        file = self.root / activity.ACTIVITIES / 'registry.v1.json'
        value = json.loads(file.read_bytes())
        value['definitions'][0]['plan']['file'] = '../outside.json'
        file.write_bytes(activity.json_bytes(value))
        with self.assertRaises(ValueError):
            self.inventory()

    def test_forged_extra_historical_wav_cannot_enter_a_valid_selected_binding(self):
        plan = deepcopy(self.plan)
        relative = (activity.ACTIVITIES / 'audio-v2/unused' / ('0' * 24 + '.wav')).as_posix()
        record, _, snapshot = activity._read_source(self.root, relative, self.registry, 'fixture', self.store)
        plan['files'].append(record)
        plan['sourceStats'][relative] = snapshot
        with self.assertRaisesRegex(activity.SupplementError, 'selected_source_set'):
            self.prepare(plan)
        self.assertFalse(self.target.exists())

    def test_secrets_inside_complete_manifest_are_not_hidden_by_unused_entries(self):
        path = self.root / activity.ACTIVITIES / 'audio-v2/manifest.json'
        value = json.loads(path.read_bytes())
        value['unused'] = {'password': 'fixture-private'}
        path.write_bytes(activity.json_bytes(value))
        with self.assertRaises(ValueError):
            self.inventory()
        self.assertEqual(json.loads(path.read_bytes())['unused']['password'], 'fixture-private')
        self.assertFalse(self.target.exists())

    def test_source_links_and_changes_are_rejected_before_upload(self):
        source = self.root / self.plan['files'][-1]['sourcePath']
        original = source.with_name('original-copy')
        source.rename(original)
        source.symlink_to(original)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.node.calls, [])

    def test_low_disk_reserve_refuses_before_writing_any_private_artifact(self):
        with patch.object(activity.os, 'statvfs', return_value=SimpleNamespace(f_bavail=activity.RESERVE_BYTES, f_frsize=1)), \
             self.assertRaisesRegex(activity.SupplementError, 'reserve_insufficient'):
            activity.prepare_supplement(self.plan, self.root, self.target, registry=self.registry, store=self.store)
        self.assertFalse(self.target.exists())

    def test_already_registered_exact_original_is_verified_and_not_zipped(self):
        record = self.plan['files'][0]
        self.registry.entries[record['sourcePath']] = self.entry(record)
        self.remote[record['sourcePath']] = (self.root / record['sourcePath']).read_bytes()
        plan = self.inventory()
        self.assertEqual(plan['files'][0]['disposition'], 'already_registered')
        index = self.prepare(plan)
        manifest = json.loads(Path(index['manifestPath']).read_bytes())
        self.assertEqual(manifest['alreadyRegistered'][0]['sourcePath'], record['sourcePath'])
        with zipfile.ZipFile(index['zip']['path']) as archive:
            self.assertNotIn(record['archivePath'], archive.namelist())
        self.remote[record['sourcePath']] = None
        with self.assertRaisesRegex(activity.SupplementError, 'remote_mismatch'):
            self.inventory()

    def test_existing_same_sha_audio_alias_is_verified_and_reused_without_duplication(self):
        record = next(r for r in self.plan['files'] if r['mimeType'] == 'audio/wav')
        source = 'openmaic-runtime/.runtime/OpenMAIC/data/formal-audio/assets/existing.wav'
        alias = self.entry(record, source)
        self.registry.entries[source] = alias
        self.registry.scopes = [{'bindings': [{'sourcePath': source, 'sha256': record['sha256']}]}]
        self.remote[source] = self.wav
        self.plan = self.inventory()
        self.assertTrue(any(r['disposition'] == 'reuse_registered' for r in self.plan['files']))
        index = self.prepare()
        with zipfile.ZipFile(index['zip']['path']) as archive:
            self.assertNotIn(record['archivePath'], archive.namelist())
        self.transfer()
        metadata, files, _, activate = self.registry.registered[0]
        self.assertFalse(activate)
        self.assertEqual(next(r for r in files if r['sourcePath'] == record['sourcePath'])['locator'], alias['locator'])

    def test_normal_transfer_verifies_two_objects_and_every_member_before_inactive_scope_then_cas(self):
        index = self.prepare()
        result = self.transfer()
        self.assertEqual(len(self.node.calls), 1)
        self.assertEqual(len(self.registry.registered), 1)
        metadata, files, _, activate = self.registry.registered[0]
        self.assertFalse(activate)
        self.assertEqual(metadata['sourceKind'], 'runtime_dependency_supplement')
        self.assertEqual(metadata['sourceDigest'], index['sourceDigest'])
        self.assertNotEqual(metadata['sourceDigest'], self.release['sha256'])
        self.assertEqual(metadata['originalSourceDigest'], self.release['sha256'])
        self.assertEqual(len(files), len(self.plan['files']))
        self.assertEqual(len(self.registry.activations), 1)
        self.assertTrue(all(v is None for v in self.registry.activations[0][2].values()))
        self.assertEqual(result['registeredFiles'], len(files))

    def test_bad_upload_receipt_never_registers(self):
        self.prepare()
        self.node.bad_receipt = True
        with self.assertRaisesRegex(activity.SupplementError, 'receipt_invalid'):
            self.transfer()
        self.assertEqual(self.registry.registered, [])

    def test_bad_remote_manifest_or_zip_never_registers(self):
        self.prepare()
        for kind in ('manifest', 'zip'):
            with self.subTest(kind=kind), self.assertRaises((ValueError, zipfile.BadZipFile)):
                activity.verify_and_register(self.target / 'index.json', binding_loader=lambda b: self.plan['binding'],
                    registry=self.registry, config=self.config, node_client=self.node, store=self.store,
                    remote_object_read=lambda r: b'wrong' if kind == 'manifest' else self.node.objects[r['objectKey']],
                    remote_zip_factory=lambda r: io.BytesIO(b'not ZIP' if kind == 'zip' else self.node.objects[r['objectKey']]))
            self.assertEqual(self.registry.registered, [])

    def test_current_release_set_change_is_rejected_before_upload(self):
        self.prepare()
        self.plan['binding']['currentPublishedSetSha256'] = '9' * 64
        with self.assertRaisesRegex(activity.SupplementError, 'current_binding_changed'):
            self.transfer()
        self.assertEqual(self.node.calls, [])
        self.assertEqual(self.registry.registered, [])

    def test_source_change_during_transfer_is_rejected_before_registration(self):
        self.prepare()
        source = self.root / self.plan['files'][0]['sourcePath']
        self.node.after_upload = lambda: source.write_bytes(source.read_bytes() + b' ')
        with self.assertRaisesRegex(activity.SupplementError, 'source_changed'):
            self.transfer()
        self.assertEqual(self.registry.registered, [])

    def test_cas_conflict_keeps_scope_inactive_and_does_not_activate_any_head(self):
        self.prepare()
        self.registry.head_conflict = True
        with self.assertRaisesRegex(ValueError, 'head_conflict'):
            self.transfer()
        self.assertFalse(self.registry.registered[0][3])
        self.assertEqual(self.registry.activations, [])

    def test_current_loader_freezes_every_current_release_but_validates_and_selects_only_supported(self):
        keys = ['a' * 64, 'b' * 64]
        builds, releases = {}, {}
        for key in keys:
            unsigned = {'contentKey': key, 'classroomId': 'tbpub_' + key[:24]}
            release = {**unsigned, 'sha256': activity.digest(unsigned)}
            releases[key] = release
            builds[key] = {'course_id': 'course-' + key[:1], 'course_version': 'v1',
                'input_json': '{"frozen":true}', 'review_json': json.dumps({'release': release})}
        conn = Mock()
        conn.execute.side_effect = lambda sql, params: SimpleNamespace(fetchone=lambda: builds[params[0]])
        @contextmanager
        def readonly(database):
            yield conn
        with patch.object(activity, 'read_only_connection', readonly), \
             patch.object(activity, '_current_keys', return_value=keys), \
             patch.object(activity.journey, 'supported', side_effect=lambda r: r['contentKey'] == keys[0]), \
             patch.object(activity.journey, 'definition', return_value=self.spec), \
             patch.object(activity, '_validated_release', return_value=(None, None, releases[keys[0]], None)) as validate, \
             patch.object(activity, 'original_directory', return_value=(self.directory, [])):
            current, active = activity.load_current(Mock(), self.registry, self.store)
        self.assertEqual((len(current), len(active)), (2, 1))
        self.assertEqual(current[0]['frozenReviewSha256'], activity.sha(builds[keys[0]]['review_json'].encode()))
        validate.assert_called_once_with(conn, keys[0])
        self.assertTrue(all(call.args[0].startswith('SELECT ') for call in conn.execute.call_args_list))

    def test_compiler_mismatch_and_source_release_mismatch_cannot_select_a_pack(self):
        bad = deepcopy(self.spec)
        bad.audio_pack = 'historical-unmapped-pack'
        with self.assertRaisesRegex(activity.SupplementError, 'compiler_not_registered'):
            activity.allowed_texts(bad)
        bad = deepcopy(self.spec)
        bad.plan['releaseSha256'] = '0' * 64
        with self.assertRaisesRegex(activity.SupplementError, 'definition_release_mismatch'):
            activity.inventory_for_course(self.root, self.identity, self.release, self.directory, self.current,
                self.registry, self.store, spec=bad, all_specs=[bad])


if __name__ == '__main__':
    unittest.main()
