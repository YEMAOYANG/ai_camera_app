import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from core.course_storage_config import CourseStorageConfig
from repositories.course_storage_repository import storage_identity
from scripts import complete_course_storage_registry as supplement


class Registry:
    def __init__(self):
        self.entries, self.registered, self.scopes, self.activations = {}, [], [], []
        self.head_conflict = False

    def resolve(self, source, *, storage_id, expected_sha=None):
        entry = self.entries.get(source)
        return entry if entry and (expected_sha is None or entry['sha256'] == expected_sha) else None

    def find_scopes(self, **filters):
        return self.scopes

    def head_scope(self, source, storage_id):
        return {'scopeKey': '9' * 64} if source in self.entries else None

    def register_scope(self, metadata, files, storage_id, *, activate):
        self.registered.append((metadata, files, storage_id, activate))
        return {'scopeKey': metadata['scopeKey']}

    def activate_heads_if_unchanged(self, scope_key, storage_id, expected_heads):
        if self.head_conflict:
            raise ValueError('course_storage_head_conflict')
        self.activations.append((scope_key, storage_id, expected_heads))
        return {'scopeKey': scope_key, 'activated': len(expected_heads)}


class RemoteReader:
    def __init__(self, raw):
        self.raw = raw

    def read_bytes(self, *args, **kwargs):
        return self.raw


class Node:
    def __init__(self, root, config):
        self.root, self.config, self.calls, self.objects = root, config, [], {}
        self.after_upload = None
        self.bad_receipt = False

    def upload(self, index_path):
        self.calls.append(index_path)
        raw = Path(index_path).read_bytes()
        index = json.loads(raw)
        objects = []
        for item in index['generatedPublicFiles']:
            self.objects[item['relativePath']] = Path(item['localPath']).read_bytes()
            objects.append({'objectKey': item['relativePath'], 'sha256': item['sha256'],
                            'byteSize': item['byteSize'], 'etag': 'fixture-etag'})
        receipt = {'schemaVersion': 'mira.course-archive.verification.v1', 'complete': True,
                   'archiveId': index['archiveId'], 'indexSha256': supplement.sha(raw),
                   'storage': storage_identity(self.config.endpoint, self.config.bucket, self.config.region),
                   'courseId': index['courseId'], 'courseVersion': index['courseVersion'],
                   'sourceDigest': index['sourceDigest'], 'objects': objects}
        if self.bad_receipt:
            receipt['sourceDigest'] = '0' * 64
        if self.after_upload:
            self.after_upload()
        return receipt


class CompleteCourseStorageRegistryTests(unittest.TestCase):
    def setUp(self):
        parent = os.environ.get('MIRA_TASK_TMPDIR')
        self.tmp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.config = CourseStorageConfig(mode='registry', endpoint='https://MINIO.invalid:443/',
                                          bucket='courses', region='us-east-1')
        self.registry = Registry()
        self.identity = {'contentKey': 'a' * 64, 'courseId': 'textbook_fixture', 'courseVersion': '1',
                         'previewKey': 'b' * 64, 'classroomId': 'tbpub_fixture',
                         'originalInputSha256': 'c' * 64, 'originalSourceDigest': 'd' * 64}
        self.proof = {'revisionIds': ['e' * 64]}
        self.original = {'authoring': {'sessionId': 'fixture-session', 'stageId': 'stage-fixture'},
                         'sourceSha256': 'f' * 64,
                         'authoringCandidate': {'interactionPolicyVersion': 1,
                             'interactionPolicySha256': '1' * 64, 'sha256': '2' * 64,
                             'completeSceneReviewFollowup': self.proof}}
        self.source_root = self.root / supplement.REVIEW_ROOT / supplement.sha(b'fixture-session') / 'stage-fixture'
        self.source_root.mkdir(parents=True)
        self.source = self.source_root / ('e' * 64) / 'intent.json'
        self.source.parent.mkdir()
        self.source.write_bytes(b'{"review":true}\n')
        self.directory = '数学/人教版/一年级上册/2026-10-23/fixture'
        self.binding = self.bind()
        self.target = self.root / 'backend/data/course-storage/archives/fixture'
        self.node = Node(self.root, self.config)

    def bind(self, original=None, **kwargs):
        return supplement.binding_from_input(self.root, self.identity, original or self.original,
            self.directory, followup_reader=lambda *a, **k: self.proof, **kwargs)

    def relative(self, path):
        return path.relative_to(self.root).as_posix()

    def entry(self, path, raw=None):
        raw = path.read_bytes() if raw is None else raw
        return {'sourcePath': self.relative(path), 'sha256': supplement.sha(raw), 'byteSize': len(raw),
                'mimeType': 'image/png' if path.suffix == '.png' else 'application/json',
                'locator': {'kind': 'object', 'objectKey': 'fixture/object', 'etag': 'fixture-etag'}}

    def inventory(self, **kwargs):
        return supplement.inventory_sources(self.binding, self.root, self.registry, 'fixture-storage', **kwargs)

    def prepare(self, inventory=None):
        return supplement.prepare_supplement(self.binding, inventory or self.inventory(), self.root, self.target)

    def transfer(self, **kwargs):
        return supplement.verify_and_register(self.target / 'index.json', binding_loader=lambda b: self.binding,
            registry=self.registry, config=self.config, node_client=self.node,
            remote_object_read=lambda r: self.node.objects[r['objectKey']],
            remote_zip_factory=lambda r: io.BytesIO(self.node.objects[r['objectKey']]), **kwargs)

    def test_selects_only_frozen_current_session_stage(self):
        self.assertEqual(self.binding['sourceRoots'], [self.relative(self.source_root)])
        current = copy.deepcopy(self.original)
        current['authoringCandidate'].update(interactionPolicyVersion=2, completeSceneReviewFollowup=None)
        self.assertIsNone(self.bind(current))
        wrong = copy.deepcopy(self.original)
        wrong['authoringCandidate']['completeSceneReviewFollowup'] = {'revisionIds': ['3' * 64]}
        with self.assertRaisesRegex(supplement.SupplementError, 'differs_from_frozen'):
            self.bind(wrong)
        with self.assertRaisesRegex(supplement.SupplementError, 'unbound_source_roots'):
            self.bind(source_roots=['output/unrelated'])

    def test_complete_current_stage_root_is_retained(self):
        other = self.source_root / ('3' * 64) / 'prior-review.json'
        other.parent.mkdir()
        other.write_bytes(b'{"branch":"retained"}')
        unrelated = self.source_root.parent / 'stage-unrelated'
        unrelated.mkdir()
        (unrelated / 'do-not-read.json').write_text('{"password":"private"}')
        inventory = self.inventory()
        self.assertEqual({r['sourcePath'] for r in inventory['files']}, {self.relative(self.source), self.relative(other)})

    def test_private_controls_and_literal_secrets_block_public_package(self):
        for filename, raw in [('paid.claim', b'{"ownership":"private"}'),
                              ('secret.json', b'{"password":"private","password":""}')]:
            with self.subTest(filename=filename):
                path = self.source.parent / filename
                path.write_bytes(raw)
                inventory = self.inventory()
                self.assertEqual(len(inventory['blocked']), 1)
                with self.assertRaisesRegex(supplement.SupplementError, 'public_ineligible'):
                    self.prepare(inventory)
                self.assertEqual(path.read_bytes(), raw)
                path.unlink()

    def test_symlinks_are_rejected(self):
        (self.source_root / 'linked').symlink_to(self.source.parent, target_is_directory=True)
        with self.assertRaisesRegex(supplement.SupplementError, 'symlink'):
            self.inventory()

    def test_registered_original_is_excluded_and_conflicting_head_refused(self):
        self.registry.entries[self.relative(self.source)] = self.entry(self.source)
        inventory = self.inventory()
        self.assertEqual(inventory['files'][0]['disposition'], 'already_registered')
        with self.assertRaisesRegex(supplement.SupplementError, 'no_missing'):
            self.prepare(inventory)
        self.registry.entries[self.relative(self.source)]['sha256'] = '0' * 64
        with self.assertRaisesRegex(supplement.SupplementError, 'conflict'):
            self.inventory()

    def test_verified_registered_media_alias_is_not_rezipped(self):
        image = self.source.parent / 'picture.png'
        raw = b'fixture-png'
        image.write_bytes(raw)
        alias = self.entry(image)
        alias['sourcePath'] = 'openmaic-runtime/.runtime/OpenMAIC/data/classrooms/existing/picture.png'
        inventory = self.inventory(aliases={supplement.sha(raw): alias}, remote_reader=RemoteReader(raw))
        record = next(r for r in inventory['files'] if r['sourcePath'].endswith('.png'))
        self.assertEqual(record['disposition'], 'reuse_registered')
        index = self.prepare(inventory)
        with zipfile.ZipFile(index['zip']['path']) as archive:
            self.assertNotIn(record['archivePath'], archive.namelist())
        with self.assertRaisesRegex(supplement.SupplementError, 'remote_hash'):
            self.inventory(aliases={supplement.sha(raw): alias}, remote_reader=RemoteReader(b'bad'))

    def test_standard_zip_contains_only_missing_originals_and_is_repeatable(self):
        before = self.source.read_bytes()
        index = self.prepare()
        self.assertEqual(index, self.prepare())
        self.assertEqual(len(index['generatedPublicFiles']), 2)
        self.assertNotEqual(index['sourceDigest'], self.identity['originalSourceDigest'])
        with zipfile.ZipFile(index['zip']['path']) as archive:
            self.assertEqual(set(archive.namelist()), {'manifest.json', '原稿/' + self.relative(self.source)})
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read('原稿/' + self.relative(self.source)), before)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual((self.target.stat().st_mode & 0o777), 0o700)

    def test_private_workspace_and_source_stability(self):
        inventory = self.inventory()
        with self.assertRaisesRegex(supplement.SupplementError, 'private_workspace'):
            supplement.prepare_supplement(self.binding, inventory, self.root, Path('/unapproved-supplement-output'))
        self.source.write_bytes(b'{"changed":true}')
        with self.assertRaisesRegex(supplement.SupplementError, 'source_changed'):
            self.prepare(inventory)

    def test_extra_source_file_after_plan_fails_closed(self):
        inventory = self.inventory()
        (self.source.parent / 'extra.json').write_bytes(b'{}')
        with self.assertRaisesRegex(supplement.SupplementError, 'source_set_changed'):
            self.prepare(inventory)

    def test_success_verifies_remote_objects_before_register(self):
        index = self.prepare()
        result = self.transfer()
        self.assertEqual(result['registeredFiles'], 1)
        metadata, files, _, activate = self.registry.registered[0]
        self.assertFalse(activate)
        self.assertEqual(self.registry.activations[0][2], {self.relative(self.source): None})
        self.assertEqual(metadata['sourceKind'], supplement.SOURCE_KIND)
        self.assertEqual(metadata['sourceDigest'], index['sourceDigest'])
        self.assertEqual(metadata['originalSourceDigest'], self.identity['originalSourceDigest'])
        self.assertEqual(files[0]['locator']['kind'], 'zip_member')

    def test_bad_receipt_does_not_register(self):
        self.prepare()
        self.node.bad_receipt = True
        with self.assertRaisesRegex(supplement.SupplementError, 'receipt_mismatch'):
            self.transfer()
        self.assertFalse(self.registry.registered)

    def test_tampered_index_does_not_upload(self):
        index = self.prepare()
        index['generatedPublicFiles'][0]['sha256'] = '0' * 64
        (self.target / 'index.json').write_bytes(supplement.json_bytes(index))
        with self.assertRaisesRegex(supplement.SupplementError, 'artifact_changed'):
            self.transfer()
        self.assertFalse(self.node.calls)
        self.assertFalse(self.registry.registered)

    def test_frozen_binding_change_does_not_upload(self):
        self.prepare()
        with self.assertRaisesRegex(supplement.SupplementError, 'binding_changed'):
            supplement.verify_and_register(self.target / 'index.json', binding_loader=lambda b: {},
                registry=self.registry, config=self.config, node_client=self.node)
        self.assertFalse(self.node.calls)

    def test_source_change_after_upload_does_not_register(self):
        self.prepare()
        self.node.after_upload = lambda: self.source.write_bytes(b'{"changed":true}')
        with self.assertRaisesRegex(supplement.SupplementError, 'source_changed'):
            self.transfer()
        self.assertFalse(self.registry.registered)

    def test_remote_zip_member_corruption_does_not_register(self):
        self.prepare()
        def corrupt():
            key = next(k for k in self.node.objects if k.endswith('.zip'))
            source = zipfile.ZipFile(io.BytesIO(self.node.objects[key]))
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w') as target:
                for info in source.infolist():
                    target.writestr(info, b'corrupt' if info.filename != 'manifest.json' else source.read(info))
            source.close()
            self.node.objects[key] = output.getvalue()
        self.node.after_upload = corrupt
        with self.assertRaisesRegex(supplement.SupplementError, 'member_invalid|member_hash'):
            self.transfer()
        self.assertFalse(self.registry.registered)

    def test_manifest_and_source_plan_must_match(self):
        self.prepare()
        path = self.target / 'manifest.json'
        manifest = json.loads(path.read_bytes())
        manifest['files'][0]['mimeType'] = 'text/plain'
        path.write_bytes(supplement.json_bytes(manifest))
        with self.assertRaisesRegex(supplement.SupplementError, 'manifest_invalid'):
            self.transfer()
        self.assertFalse(self.node.calls)

    def test_duplicate_json_members_are_refused(self):
        with self.assertRaisesRegex(supplement.SupplementError, 'duplicate_json'):
            supplement.parse_json(b'{"complete":false,"complete":true}')

    def test_saved_mismatch_preserves_both_proofs_without_approval(self):
        self.identity['contentKey'] = None
        self.original['authoringCandidate']['completeSceneReviewFollowup'] = {'revisionIds': ['3' * 64]}
        binding = self.bind(proof_validator=lambda *a, **k: None)
        self.assertEqual(binding['reviewValidation'], 'frozen-proof-mismatch')
        self.assertEqual(binding['revisionIds'], ['3' * 64])
        self.assertEqual(binding['currentReviewRevisionIds'], ['e' * 64])
        self.assertNotEqual(binding['frozenReviewProofSha256'], binding['currentReviewProofSha256'])
        self.assertNotIn('approved', binding)

    def test_task_tmp_prefix_alias_is_canonicalized_without_following_children(self):
        task = Path(os.environ['MIRA_TASK_TMPDIR'])
        if task == task.resolve():
            self.skipTest('task path has no platform alias')
        destination = task / self.target.relative_to(task.resolve())
        self.assertEqual(supplement.private_workspace(self.root, destination), self.target)
        link = self.root / 'linked-output'
        link.symlink_to(self.target, target_is_directory=True)
        with self.assertRaisesRegex(supplement.SupplementError, 'symlink'):
            supplement.private_workspace(self.root, link)

    def test_head_conflict_leaves_verified_scope_inactive(self):
        self.prepare()
        self.registry.head_conflict = True
        with self.assertRaisesRegex(ValueError, 'head_conflict'):
            self.transfer()
        self.assertEqual(len(self.registry.registered), 1)
        self.assertFalse(self.registry.registered[0][3])
        self.assertFalse(self.registry.activations)

    def test_existing_publication_scope_must_match_original_release(self):
        self.registry.scopes = [{'metadata': {'registryVersion': 3, 'sourceKind': 'published',
            'sourceDigest': self.identity['originalSourceDigest'], 'storageDirectory': self.directory}}]
        self.assertEqual(supplement.original_directory(self.registry, 'fixture-storage', self.identity)[0], self.directory)
        self.registry.scopes[0]['metadata']['sourceDigest'] = '0' * 64
        with self.assertRaisesRegex(supplement.SupplementError, 'directory_ambiguous'):
            supplement.original_directory(self.registry, 'fixture-storage', self.identity)

    def test_identical_head_registered_by_shared_course_is_verified_and_cas_bound(self):
        self.prepare()
        self.registry.entries[self.relative(self.source)] = self.entry(self.source)
        self.transfer(alias_reader=RemoteReader(self.source.read_bytes()))
        self.assertEqual(self.registry.activations[0][2], {self.relative(self.source): {
            'sha256': supplement.sha(self.source.read_bytes()), 'scopeKey': '9' * 64}})

    def test_changed_existing_head_is_refused_before_upload(self):
        self.prepare()
        entry = self.entry(self.source)
        entry['sha256'] = '0' * 64
        self.registry.entries[self.relative(self.source)] = entry
        with self.assertRaisesRegex(supplement.SupplementError, 'source_head_changed'):
            self.transfer()
        self.assertFalse(self.node.calls)
        self.assertFalse(self.registry.registered)


if __name__ == '__main__':
    unittest.main()
