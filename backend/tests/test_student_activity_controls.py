"""Compiler replay, G8 and the authenticated Classic controls descriptor."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from content.courseware_release import validate_light_release
from content.student_activity_controls import (
    FIELD, SCHEMA, SOURCE_PROOF_SCHEMA, compile_evidence, validate_release_controls,
)
from content.textbook_catalog import canonical, digest
from services.courseware_publish_service import CoursewarePublishService
from services.textbook_classroom_service import TextbookClassroomService
from tests.test_courseware_release import sample_inputs
from courseware.tools import build, package


ROOT = Path(__file__).resolve().parents[2] / 'courseware'
FIXTURE = ROOT / 'tools/tests/fixtures/build_lesson'


def write(path, data):
    path.write_text(canonical(data), encoding='utf-8')


class StudentActivityControlsTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.lesson = self.root / 'lessons' / 'stage-test'
        shutil.copytree(FIXTURE, self.lesson)
        (self.root / 'kit').symlink_to(ROOT / 'kit', target_is_directory=True)
        source = patch('content.student_activity_controls._ROOT', self.root)
        source.start()
        self.addCleanup(source.stop)

        self.fixture = sample_inputs()
        identity = self.fixture['identity']
        self.brief = {'schemaVersion': 'mira.courseware.brief.v1', 'goals': ['比较数量'],
            'binding': {key: identity[key] for key in ('editionId', 'revisionId', 'nodeId', 'teachingRevision')},
            'games': [{'page': 'play', 'template': 'sortingDepot', 'version': 1,
                       'entryPoint': 'K.gameTemplates.sortingDepot', 'ownerApprovedOn': '2026-11-09'}]}
        write(self.lesson / 'brief.json', self.brief)
        write(self.lesson / 'official-notes.json', self.fixture['notes'])
        (self.lesson / 'pages/play.js').write_text(
            "K.ready({title:'游戏',sub:'看图，听老师。'});\nK.game(K.gameTemplates.sortingDepot({}));\n",
            encoding='utf-8')
        self.work = self.root / 'work'
        draft = build.prepare(self.lesson, self.work, stage_id='stage-test', now_ms=123)
        audio_name, audio = next((name, data) for name, data in self.fixture['media'].items() if name.endswith('.wav'))
        (self.work / 'media' / audio_name).write_bytes(audio)
        self.body = build.finish(draft, self.work, {line['id']: audio_name for line in draft['lines']})
        self.receipts = {'audit-receipt.json': self.fixture['receipt'], 'play-receipt.json': self.fixture['playReceipt'],
                         'verification.json': self.fixture['verification']}
        self.receipts['play-receipt.json']['pages'] = [
            {'scene': 2, 'ok': True, 'finished': True, 'errors': [], 'stuck': None}]
        self.receipts['verification.json'].update(speechChecked=len(draft['lines']), questionsChecked=2)
        self.write_receipts(self.work, self.body)
        self.service = CoursewarePublishService(None, classroom_directory=self.root / 'classrooms',
            manifest=self.fixture['manifest'], checker=lambda *args, **kwargs: [])

    def write_receipts(self, directory, body):
        for name, value in self.receipts.items():
            write(directory / name, {**value, 'bodySha256': digest(body)})

    def package(self, *, opt_in=True):
        identity = self.fixture['identity']
        folder = self.root / ('opted' if opt_in else 'legacy')
        with patch.object(package.check, 'check_classroom', return_value=[]):
            package.package_lesson(self.lesson, self.work, folder, edition_id=identity['editionId'],
                revision_id=identity['revisionId'], node_id=identity['nodeId'], teacher_code=identity['teacherCode'],
                author_models=identity['authorModels'], confirmation=self.fixture['confirmation'],
                student_activity_controls=opt_in)
        return folder

    def use_older_source(self, *, stage_id='older-preview', template='platformHop'):
        self.brief = {'schemaVersion': 'mira.courseware.brief.v1', 'goals': self.brief['goals'],
            'binding': {key: self.brief['binding'][key] for key in ('editionId', 'revisionId', 'nodeId')},
            'pageSequence': [{'key': 'play', 'page': 2, 'game': {'template': template, 'version': 1}}]}
        write(self.lesson / 'brief.json', self.brief)
        (self.lesson / 'pages/play.js').write_text(
            f"K.ready({{title:'游戏',sub:'看图，听老师。'}});\nK.game(K.gameTemplates.{template}({{}}));\n",
            encoding='utf-8')
        draft = build.prepare(self.lesson, self.work, stage_id=stage_id, now_ms=123)
        audio = next(p.name for p in (self.work / 'media').glob('*.wav'))
        self.body = build.finish(draft, self.work, {line['id']: audio for line in draft['lines']})
        self.write_receipts(self.work, self.body)

    def compile_source_proof(self, *, body=None, media=None):
        identity = self.fixture['identity']
        binding = {key: identity[key] for key in ('editionId', 'nodeId', 'teachingRevision')}
        binding['alignmentRevisionId'] = identity['revisionId']
        if media is None:
            media = {path.name: path.read_bytes() for path in (self.work / 'media').iterdir()}
        return compile_evidence(True, self.brief, self.body if body is None else body, media, binding)

    def test_normal_package_changes_only_release_identity_and_verified_descriptors(self):
        legacy = self.service.check(self.package(opt_in=False))
        folder = self.package()
        result = self.service.check(folder)
        self.assertTrue(legacy['ok'], legacy['errors'])
        self.assertTrue(result['ok'], result['errors'])
        prepared, previous = result['prepared'], legacy['prepared']
        self.assertNotIn(FIELD, previous['frozen'])
        self.assertNotIn(FIELD, previous['release'])
        self.assertIs(json.loads((folder / 'identity.json').read_text())[FIELD], True)
        self.assertEqual(prepared['frozen']['coursewareLight'], previous['frozen']['coursewareLight'])
        self.assertNotEqual(prepared['frozen']['contentKey'], previous['frozen']['contentKey'])
        self.assertEqual((folder / 'body.json').read_bytes(), (self.work / 'body.json').read_bytes())
        self.assertFalse((self.root / 'classrooms').exists())
        release = prepared['release']
        self.assertEqual(prepared['frozen'][FIELD]['schemaVersion'], SCHEMA)
        html = release['classroom']['scenes'][1]['content']['html']
        self.assertIn(release['classroomId'], html)
        self.assertEqual(release[FIELD], {'schemaVersion': SCHEMA, 'scenes': [{'sceneId': 'scene-play',
            'template': 'sortingDepot', 'version': 1, 'contentSha256': hashlib.sha256(html.encode()).hexdigest()}]})
        validate_release_controls(prepared['frozen'], release)

    def test_older_source_proof_replays_alias_and_keeps_public_descriptor_v1(self):
        self.use_older_source()
        folder = self.package()
        result = self.service.check(folder)
        self.assertTrue(result['ok'], result['errors'])
        prepared = result['prepared']
        proof = prepared['frozen'][FIELD]
        self.assertEqual(proof['schemaVersion'], SOURCE_PROOF_SCHEMA)
        self.assertEqual(proof['sourceStageId'], 'older-preview')
        self.assertEqual(proof['bodySha256'], digest(self.body))
        self.assertEqual(proof['brief'], self.brief)
        self.assertEqual((folder / 'body.json').read_bytes(), (self.work / 'body.json').read_bytes())
        release = prepared['release']
        html = release['classroom']['scenes'][1]['content']['html']
        self.assertEqual(release[FIELD], {'schemaVersion': SCHEMA, 'scenes': [{'sceneId': 'scene-play',
            'template': 'platformHop', 'version': 1, 'contentSha256': hashlib.sha256(html.encode()).hexdigest()}]})
        with patch('content.student_activity_controls._ROOT', self.root / 'missing'):
            validate_release_controls(prepared['frozen'], release)
        for field, changed in [('scenes', []), ('mediaSha256', '0' * 64), ('sourceStageId', 'wrong-stage')]:
            with self.subTest(field=field):
                frozen = deepcopy(prepared['frozen'])
                frozen[FIELD][field] = changed
                with self.assertRaisesRegex(ValueError, 'student_activity_controls_invalid'):
                    validate_release_controls(frozen, release)

    def test_older_source_proof_rejects_conflicting_explicit_binding_and_game_fields(self):
        self.use_older_source()
        original = deepcopy(self.brief)
        for field, bad, error in (
                ('nodeId', 'a-different-node', 'student_activity_controls_invalid'),
                ('template', 'magnetMarbles@1', 'student_activity_controls_template_mismatch'),
                ('version', True, 'student_activity_controls_template_mismatch'),
                ('ownerApprovedOn', '2026-11-08', 'student_activity_controls_template_mismatch')):
            with self.subTest(field=field):
                self.brief = deepcopy(original)
                declaration = self.brief['binding'] if field == 'nodeId' else self.brief['pageSequence'][0]['game']
                declaration[field] = bad
                write(self.lesson / 'brief.json', self.brief)
                with self.assertRaisesRegex(ValueError, error):
                    self.compile_source_proof()

    def test_older_source_proof_rejects_ambiguous_source_and_multiple_mechanics(self):
        self.use_older_source()
        duplicate = self.lesson.parent / 'other-source'
        shutil.copytree(self.lesson, duplicate)
        with self.assertRaisesRegex(ValueError, 'student_activity_controls_source_unavailable'):
            self.compile_source_proof()
        shutil.rmtree(duplicate)
        with (self.lesson / 'pages/play.js').open('a', encoding='utf-8') as script:
            script.write('K.game(K.gameTemplates.magnetMarbles({}));')
        with self.assertRaisesRegex(ValueError, 'student_activity_controls_template_mismatch'):
            self.compile_source_proof()

    def test_older_source_proof_requires_exact_body_and_media(self):
        self.use_older_source()
        altered = deepcopy(self.body)
        altered['scenes'][1]['content']['html'] += '<!-- forged -->'
        with self.assertRaisesRegex(ValueError, 'student_activity_controls_body_changed'):
            self.compile_source_proof(body=altered)
        media = {path.name: path.read_bytes() for path in (self.work / 'media').iterdir()}
        name = next(name for name in media if name.endswith('.wav'))
        media[name] += b'changed'
        with self.assertRaisesRegex(ValueError, 'student_activity_controls_media_changed'):
            self.compile_source_proof(media=media)
        extra = b'extra media'
        media[name] = (self.work / 'media' / name).read_bytes()
        media['pic-' + hashlib.sha256(extra).hexdigest() + '.png'] = extra
        with self.assertRaisesRegex(ValueError, 'student_activity_controls_media_changed'):
            self.compile_source_proof(media=media)

    def test_packages_cannot_supply_sidecar_proof_or_change_the_trusted_brief(self):
        folder = self.package()
        identity_path = folder / 'identity.json'
        identity = json.loads(identity_path.read_text())
        write(identity_path, {**identity, FIELD: {'schemaVersion': SCHEMA, 'scenes': []}})
        self.assertEqual(self.service.check(folder)['errors'], ['student_activity_controls_invalid'])
        write(identity_path, identity)
        write(folder / 'brief.json', {**self.brief, 'goals': ['新目标']})
        self.assertEqual(self.service.check(folder)['errors'], ['student_activity_controls_brief_changed'])

    def test_source_template_version_and_page_must_match_compiler(self):
        folder = self.package()
        cases = [({'page': 'wrong-page'}, 'student_activity_controls_page_unmatched'),
                 ({'template': 'bubbleMaze', 'entryPoint': 'K.gameTemplates.bubbleMaze'},
                  'student_activity_controls_template_mismatch'),
                 ({'version': 2}, 'student_activity_controls_template_unapproved'),
                 ({'template': 'magnetMarbles'}, 'student_activity_controls_template_unapproved'),
                 ({'ownerApprovedOn': None}, 'student_activity_controls_invalid')]
        for change, error in cases:
            with self.subTest(change=change):
                updated = {**self.brief, 'games': [{**self.brief['games'][0], **change}]}
                write(self.lesson / 'brief.json', updated)
                write(folder / 'brief.json', updated)
                self.assertEqual(self.service.check(folder)['errors'], [error])

    def test_g8_rejects_modified_html_even_if_local_gate_receipts_repeat_its_sha(self):
        folder = self.package()
        altered = deepcopy(self.body)
        altered['scenes'][1]['content']['html'] += '<!-- modified -->'
        write(folder / 'body.json', altered)
        self.write_receipts(folder, altered)
        self.assertEqual(self.service.check(folder)['errors'], ['student_activity_controls_body_changed'])

    def test_saved_release_rejects_wrong_digest_and_missing_evidence(self):
        prepared = self.service.check(self.package())['prepared']
        release = prepared['release']
        release[FIELD]['scenes'][0]['contentSha256'] = '0' * 64
        release['sha256'] = digest({key: value for key, value in release.items() if key != 'sha256'})
        prepared['content_json']['releaseSha256'] = release['sha256']
        prepared['course']['content_json'] = canonical(prepared['content_json'])
        self.assertEqual(validate_light_release(prepared, self.fixture['manifest']), ['release_invalid'])
        with self.assertRaisesRegex(ValueError, 'student_activity_controls_invalid'):
            validate_release_controls({}, release)
        proof = deepcopy(prepared['frozen'])
        del proof[FIELD]['scenes'][0]['sourceContentSha256']
        with self.assertRaisesRegex(ValueError, 'student_activity_controls_invalid'):
            validate_release_controls(proof, release)

    def test_authenticated_validate_exposes_only_attested_rows(self):
        prepared = self.service.check(self.package())['prepared']
        build_row = {'input_json': canonical(prepared['frozen'])}
        release = prepared['release']
        service = object.__new__(TextbookClassroomService)
        service.repository = SimpleNamespace(parse=json.loads)
        session = {'id': 'fixed-session'}
        data = {'expiresAt': 10**14}
        authority = (data, None, build_row, release, None, session)
        with patch('services.textbook_classroom_service.activity_state.descriptors', return_value=[]):
            with patch.object(service, '_authority', return_value=authority):
                result = service.validate('verified-token')
            self.assertEqual(result[FIELD], release[FIELD])
            self.assertIsNot(result[FIELD], release[FIELD])
            legacy = {key: value for key, value in release.items() if key != FIELD}
            with patch.object(service, '_authority', return_value=(data, None, build_row, legacy, None, session)):
                self.assertNotIn(FIELD, service.validate('verified-token'))
            with patch.object(service, '_authority', return_value=(
                    {**data, 'entry': 'intro', 'key': 'content-key'}, *authority[1:])), \
                    patch('services.textbook_classroom_service.sections.plan_for', return_value={}), \
                    patch('services.textbook_classroom_service.sections.scene_groups',
                          return_value={'intro': [release['classroom']['scenes'][0]]}):
                self.assertNotIn(FIELD, service.validate('verified-token'))
