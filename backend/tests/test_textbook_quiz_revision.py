"""Picture-quiz revisions use synthetic pixels and isolated SQLite only."""
from copy import deepcopy
import io
import json
import unittest

from PIL import Image

from content.textbook_catalog import canonical, digest
from content.textbook_operator_revision import (
    CROP_VERSION, QUIZ_PATCH_SCHEMA, revision_candidate, sha_text, validate_parent, validate_quiz_revision_binding,
)
from content.textbook_release import public_classroom, validate_release
from core.errors import ApiError
from core.security import now_ms
from services.textbook_operator_revision_service import derive_quiz_assets, prepare_revision, register_revision, load_prepared
from services.textbook_preview_audio import narrate_preview
from services.textbook_preview_visual_revision import sha_bytes
from services.textbook_publication_service import TextbookPublicationService
from tests import test_textbook_operator_revision_service as fixture_service
from tests.test_textbook_operator_revision import parent_fixture


class QuizRevisionTests(unittest.TestCase):
    parent_rows = fixture_service.OperatorRevisionServiceTests.parent_rows
    source_files = fixture_service.OperatorRevisionServiceTests.source_files
    configure_paid_mocks = fixture_service.OperatorRevisionServiceTests.configure_paid_mocks
    audit = fixture_service.OperatorRevisionServiceTests.audit

    def setUp(self):
        picture = Image.new('RGB', (128, 96))
        picture.putdata([(x * 2, y * 2, (x + y) % 256) for y in range(96) for x in range(128)])
        output = io.BytesIO(); picture.save(output, format='PNG')
        self.fixture_picture, self.quiz_intro = output.getvalue(), True
        fixture_service.OperatorRevisionServiceTests.setUp(self)
        room = self.docs[self.source_cid]
        scene = room['scenes'][-1]
        q = scene['content']['questions'][0]
        source_path = room['scenes'][0]['content']['canvas']['elements'][0]['src']
        self.patch = {'schemaVersion': QUIZ_PATCH_SCHEMA, 'parentContentKey': self.parent_key,
            'expectedSourceSha256': self.before_rows[1]['classroom_sha256'], 'teachingRevision': 'quiz-4',
            'reviewer': 'isolated test', 'basis': 'replace letter selection with spoken picture comprehension',
            'derivedImages': [{'id': name, 'sourcePath': source_path, 'sourceSha256': sha_bytes(self.picture),
                'sourceSize': [128, 96], 'rect': rect, 'transform': CROP_VERSION}
                for name, rect in [('left', [0, 0, 64, 96]), ('right', [64, 0, 64, 96])]],
            'changes': [{'kind': 'quiz_scene', 'sceneId': scene['id'],
                'beforeQuestionsSha256': digest(scene['content']['questions']), 'beforeActionsSha256': digest(scene['actions']),
                'intro': {'actionId': 'quiz-intro', 'beforeTextSha256': sha_text(scene['actions'][0]['text']),
                          'text': '听老师说，点一幅图。'},
                'questions': [{'questionId': q['id'], 'beforeQuestionSha256': digest(q),
                    'question': '哪幅图是河流？请点一点。', 'options': deepcopy(q['options']), 'answer': q['answer'],
                    'analysis': '这幅图是河流。', 'speechActionId': 'line-quiz',
                    'visual': {'kind': 'image', 'sourcePath': source_path, 'alt': '自然情境'},
                    'optionVisuals': {'A': {'kind': 'image', 'cropId': 'left', 'alt': '田地'},
                                      'B': {'kind': 'image', 'cropId': 'right', 'alt': '河流'}}}]}]}

    def prepare(self, patch=None):
        return prepare_revision(self.service, self.parent_key, self.root, patch or self.patch,
                                self.source_audit, self.output)

    def register(self):
        return register_revision(self.service, self.output, self.root, budget_reference='test-only fake audio')

    def publish_ready(self):
        prepared = self.prepare(); self.register(); self.configure_paid_mocks()
        narrate_preview(self.service, prepared['previewKey'], self.root)
        audit = self.audit(prepared['previewKey'])
        row = self.service.get(prepared['previewKey'])
        review = dict(alignmentConfirmed=True, originalExpressionConfirmed=True, sourceUsageConfirmed=True,
            publicationAuthorized=True, reviewer='isolated', basis='picture task checked',
            sourceSha256=row['classroom_sha256'], reviewedAt=now_ms() - 1)
        publisher = TextbookPublicationService(self.service)
        release = publisher.prepare(key=row['preview_key'], edition=row['edition_id'], revision=row['revision_id'],
            node=row['node_id'], teaching_revision='quiz-4', review=review, audio_audit=audit,
            classroom_directory=self.root)
        return prepared, publisher, release

    def test_exact_private_question_new_audio_and_crops_publish_without_touching_parent(self):
        prepared, publisher, release = self.publish_ready()
        self.assertEqual((prepared['changedSpeechCount'], prepared['inheritedSpeechCount']), (2, 2))
        self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)
        self.assertEqual(self.runtime.start_formal_audio_asr.call_count, 2)
        q = release['release']['classroom']['scenes'][-1]['content']['questions'][0]
        self.assertEqual(q['answer'], ['B'])
        self.assertEqual(q['question'], self.patch['changes'][0]['questions'][0]['question'])
        proof = release['frozen']['operatorParent']
        self.assertEqual(len(proof['derivedImages']), 2)
        for asset in proof['derivedImages']:
            raw = (self.output / 'derived' / (asset['sha256'] + '.png')).read_bytes()
            self.assertEqual(Image.open(io.BytesIO(raw)).size, (64, 96))
        receipt = publisher.publish(release)
        build = self.repo.get_build(self.db, receipt['contentKey'])
        course = self.db.execute('SELECT * FROM learning_courses WHERE id=? AND version=?',
            (receipt['courseId'], receipt['courseVersion'])).fetchone()
        validate_release(build, release['manifest'], course)
        public = public_classroom(release['release'])['scenes'][-1]['content']['questions'][0]
        self.assertNotIn('answer', public); self.assertNotIn('analysis', public)
        self.assertEqual(self.before_rows, self.parent_rows())
        self.assertEqual(self.before_files, self.source_files())

    def test_stale_hash_answer_url_pixels_and_answer_styling_refuse_before_save(self):
        mutations = [
            lambda p: p.update(expectedSourceSha256='0' * 64),
            lambda p: p['changes'][0].update(beforeActionsSha256='0' * 64),
            lambda p: p['changes'][0].update(beforeQuestionsSha256='0' * 64),
            lambda p: p['changes'][0]['questions'][0].update(answer=['A']),
            lambda p: p['changes'][0]['questions'][0].update(speechActionId='quiz-intro'),
            lambda p: p['derivedImages'][0].update(sourcePath='https://example.invalid/picture.png'),
            lambda p: p['derivedImages'][0].update(sourceSha256='0' * 64),
            lambda p: p['derivedImages'][0].update(sourceSize=[128, 95]),
            lambda p: p['derivedImages'][0].update(rect=[100, 0, 64, 96]),
            lambda p: p['changes'][0]['questions'][0]['optionVisuals']['B'].update(cue='speaking'),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                invalid = deepcopy(self.patch); mutation(invalid)
                with self.assertRaises(ApiError): self.prepare(invalid)
        self.runtime.save_preview_classroom.assert_not_called()
        self.assertEqual(self.before_rows, self.parent_rows())

    def test_rehashing_a_changed_crop_cannot_replace_derived_pixels(self):
        self.prepare()
        path = next((self.output / 'derived').glob('*.png'))
        path.write_bytes(path.read_bytes() + b'changed')
        intent_path = self.output / 'prepared.json'; intent = json.loads(intent_path.read_text())
        intent['files'][str(path.relative_to(self.output))] = sha_bytes(path.read_bytes())
        intent['sha256'] = digest({k: v for k, v in intent.items() if k != 'sha256'})
        intent_path.write_text(canonical(intent))
        with self.assertRaises(ApiError): load_prepared(self.output)
        with self.assertRaises(ApiError): self.register()
        self.runtime.save_preview_classroom.assert_not_called()

    def test_saved_question_or_course_answer_cannot_drift_from_reviewed_binding(self):
        _, _, release = self.publish_ready()
        proof, room = release['frozen']['operatorParent'], release['release']['classroom']
        changed = deepcopy(room)
        changed['scenes'][-1]['content']['questions'][0]['questionAudioUrl'] = '/api/classroom-media/another/audio/unreviewed.wav'
        with self.assertRaises(ApiError): validate_quiz_revision_binding(proof, changed, media=release['release']['media'])
        course = json.loads(release['course']['content_json'])['questions']
        course[0]['answer'] = 'A'
        with self.assertRaises(ApiError):
            validate_quiz_revision_binding(proof, room, media=release['release']['media'], course_questions=course)

    def test_unknown_save_with_new_crop_namespace_reconciles_without_resending(self):
        self.prepare()
        save = self.runtime.save_preview_classroom.side_effect
        def lost(room):
            save(room)
            raise TimeoutError('lost test response')
        self.runtime.save_preview_classroom.side_effect = lost
        with self.assertRaises(TimeoutError): self.register()
        self.register()
        self.runtime.save_preview_classroom.assert_called_once()
        self.assertEqual(self.before_files, self.source_files())

    def test_legacy_saved_preview_keeps_original_manifest_plan_and_exact_numbered_question_identity(self):
        parent = parent_fixture(saved_preview=True, quiz_intro=True, image_sha=sha_bytes(self.picture))
        before = deepcopy(parent)
        self.assertNotEqual(parent['plan']['classroomSha256'], parent['preview']['classroom_sha256'])
        self.assertNotEqual(parent['sourceManifest']['revisionId'], parent['manifest']['revisionId'])
        self.assertEqual(len(validate_parent(parent, allow_saved_preview=True)['segments']), 4)
        with self.assertRaises(ApiError): validate_parent(parent)
        patch = deepcopy(self.patch)
        patch.update(parentContentKey=parent['build']['content_key'],
                     expectedSourceSha256=parent['preview']['classroom_sha256'])
        scene = json.loads(parent['preview']['classroom_json'])['scenes'][-1]
        change, question = patch['changes'][0], scene['content']['questions'][0]
        change.update(beforeQuestionsSha256=digest(scene['content']['questions']),
                      beforeActionsSha256=digest(scene['actions']))
        edit = change['questions'][0]
        edit.update(beforeQuestionSha256=digest(question), options=deepcopy(question['options']),
                    speechActionId='review_question-1')
        extra = deepcopy(patch['derivedImages'][0]); extra.update(id='middle', rect=[32, 0, 32, 96])
        patch['derivedImages'].append(extra)
        edit['optionVisuals']['C'] = {'kind': 'image', 'cropId': 'middle', 'alt': '山地'}
        assets, _ = derive_quiz_assets(parent, patch, lambda _: self.picture)
        candidate = revision_candidate(parent, patch, derived_assets=assets)
        self.assertEqual(candidate['changedSegments'], [['quiz', 'quiz-intro'], ['quiz', 'review_question-1']])
        self.assertNotIn('questionAudioUrl', candidate['classroom']['scenes'][-1]['content']['questions'][0])
        for mutate in (lambda p: p['sourceManifest'].update(revisionId='other-original'),
                       lambda p: p['plan'].update(classroomSha256='0' * 64)):
            bad = deepcopy(parent); mutate(bad)
            with self.assertRaises(ApiError): validate_parent(bad, allow_saved_preview=True)
        wrong_slot = deepcopy(patch); wrong_slot['changes'][0]['questions'][0]['speechActionId'] = 'quiz-intro'
        assets, _ = derive_quiz_assets(parent, wrong_slot, lambda _: self.picture)
        with self.assertRaises(ApiError): revision_candidate(parent, wrong_slot, derived_assets=assets)
        self.assertEqual(parent, before)


if __name__ == '__main__': unittest.main()
