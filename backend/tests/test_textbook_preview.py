"""No network/provider/database configuration is loaded by these checks."""
import json
from copy import deepcopy
import hashlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import wave
from unittest.mock import Mock

from content.textbook_catalog import generation_brief
from content.textbook_preview import (THREE_IMPORT, blueprint_prompt, blueprint_question_count, lesson_blueprint,
    preview_checks, preview_input, preview_media, responsive_activity_marker, self_contained_classroom)
from core.errors import ApiError
from repositories.textbook_repository import TextbookRepository
from services.textbook_learning_service import TextbookLearningService
from services.textbook_preview_service import TextbookPreviewService
from services.textbook_preview_audio import narrate_preview
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError
from tests.test_textbook_learning import IsolatedDatabase


RESPONSIVE_HEAD = '<head><meta name="mira-responsive-activity" content="low-reading-v1"></head>'


def responsive_html(body):
    return '<html>' + RESPONSIVE_HEAD + '<body>' + body + '</body></html>'


def scene_content(kind):
    reference = preview_media()["assets"][0]["mediaPath"]
    if kind == "quiz":
        return {"questions": [{}] * 6}
    if kind == "interactive":
        return {"html": responsive_html(f'<img src="{reference}" />')}
    return {"canvas": {"elements": [{"type": "image", "src": reference}]}}


class ResponsiveActivityPreviewTest(unittest.TestCase):
    def test_marker_is_one_real_head_meta_not_an_inert_example(self):
        marker = '<meta name="mira-responsive-activity" content="low-reading-v1">'
        self.assertTrue(responsive_activity_marker(responsive_html('<button>试一试</button>')))
        self.assertTrue(responsive_activity_marker('<html><head><META NAME="MIRA-RESPONSIVE-ACTIVITY" CONTENT="low-reading-v1"></head></html>'))
        for head, body in [('', marker), ('<!--' + marker + '-->', ''),
                           ('<script>const example=' + json.dumps(marker) + '</script>', ''),
                           ('<template>' + marker + '</template>', ''),
                           ('<noscript>' + marker + '</noscript>', ''),
                           (marker + marker, ''), (marker.replace('low-reading-v1', 'other'), ''),
                           ('', '<head>' + marker + '</head>'), ('<script/>' + marker, '')]:
            with self.subTest(head=head, body=body):
                self.assertFalse(responsive_activity_marker('<html><head>' + head + '</head><body>' + body + '</body></html>'))

    def test_only_requested_low_grade_new_preview_checks_require_marker(self):
        room = {'scenes': [{'type': 'interactive', 'content': {'html': '<button>旧课</button>'}}]}
        for grade in ('primary_1', 'primary_2'):
            self.assertIn('responsive_activity_marker_missing', preview_checks(room, 1, grade_code=grade)['issues'])
        for grade in (None, 'primary_3', 'kindergarten'):
            self.assertNotIn('responsive_activity_marker_missing', preview_checks(room, 1, grade_code=grade)['issues'])
        room['scenes'][0]['content']['html'] = responsive_html('<button>新课</button>')
        self.assertNotIn('responsive_activity_marker_missing', preview_checks(room, 1, grade_code='primary_1')['issues'])

    def test_verified_partial_revision_checks_changed_pages_and_preserves_untouched_legacy_layout(self):
        room = {'scenes': [
            {'id': 'legacy', 'type': 'interactive', 'content': {'html': '<button>旧画布</button>'}},
            {'id': 'revised', 'type': 'interactive', 'content': {'html': responsive_html('<button>重新排版</button>')}}]}
        def issues(scope):
            return preview_checks(room, 2, grade_code='primary_1', responsive_scene_ids=scope)['issues']
        self.assertIn('responsive_activity_marker_missing', issues(None))
        self.assertNotIn('responsive_activity_marker_missing', issues({'revised'}))
        self.assertIn('responsive_activity_scope_invalid', issues({'not-a-scene'}))
        room['scenes'][1]['content']['html'] = '<button>修订页遗漏标记</button>'
        self.assertIn('responsive_activity_marker_missing', issues({'revised'}))


class TextbookPreviewTest(unittest.TestCase):
    def setUp(self):
        self.db = IsolatedDatabase(("082_fixed_textbook_learning.sql", "083_textbook_course_previews.sql", "087_learning_course_reuse.sql"))
        self.addCleanup(self.db.raw.close)
        self.repo = TextbookRepository(self.db)
        self.manifest = json.loads((Path(__file__).parents[1] / "content/textbooks/revisions/pep-chinese-g1-upper.preview.v2.json").read_text())
        TextbookLearningService(self.repo).import_manifest(self.manifest)
        self.runtime = Mock(base_url="http://127.0.0.1:3100")
        self.job = SimpleNamespace(job_id="job-a", status="running", step="generating_scenes", progress=40, scenes_count=2, classroom_id=None)
        self.runtime.start_generation.return_value = self.job
        self.runtime.get_generation_job.return_value = self.job
        self.service = TextbookPreviewService(self.repo, self.runtime)

    def prepare(self):
        return self.service.prepare(self.manifest["editionId"], self.manifest["revisionId"], "u1-l1")["previewKey"]

    def test_continuous_unit_has_distinct_scopes_and_stops_before_billing_without_art(self):
        manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text())
        for node, count in [('u1-l2', 7), ('u1-l3', 7), ('u1-l4', 8), ('u1-l5', 12)]:
            blueprint = lesson_blueprint(manifest, node)
            self.assertEqual(blueprint_prompt(blueprint)['expectedQuestionCount'], count)
            self.assertFalse(blueprint['generationReady'])
            with self.assertRaises(ApiError) as error:
                preview_input(manifest, node)
            self.assertEqual(error.exception.code, 'textbook_preview_media_required')
        self.runtime.start_generation.assert_not_called()
        self.assertIsNone(lesson_blueprint({**manifest, 'revisionId': 'another-version'}, 'u1-l2'))

    def test_lesson_plans_may_live_in_one_file_per_unit(self):
        edition = {'editionId': 'edition-a', 'revisionId': 'revision-1'}
        def unit(name, lessons, revision='revision-1'):
            (folder / name).write_text(json.dumps({**edition, 'revisionId': revision, 'source': {'url': name},
                'lessons': lessons}), encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            unit('unit-1.json', [{'nodeId': 'u1-l1', 'status': 'scope_verified_preview_only', 'targets': ['一']}])
            unit('unit-2.json', [{'nodeId': 'u2-l1', 'status': 'scope_verified_preview_only', 'targets': ['a', 'o']},
                                 {'nodeId': 'u2-l2', 'status': 'draft', 'targets': ['b']}])
            unit('older.json', [{'nodeId': 'u3-l1', 'status': 'scope_verified_preview_only', 'targets': ['c']}],
                 revision='revision-0')
            found = lesson_blueprint(edition, 'u2-l1', folder)
            self.assertEqual((found['targets'], found['sourceScope']), (['a', 'o'], {'url': 'unit-2.json'}))
            self.assertEqual(lesson_blueprint(edition, 'u1-l1', folder)['targets'], ['一'])
            self.assertIsNone(lesson_blueprint(edition, 'u2-l2', folder))
            self.assertIsNone(lesson_blueprint(edition, 'u3-l1', folder))
            self.assertIsNone(lesson_blueprint(edition, 'u9-l9', folder))

    def test_preview_uses_the_lesson_question_count(self):
        classroom = {'scenes': [{'type': 'quiz', 'content': {'questions': [{}] * 7}}]}
        self.assertNotIn('question_count_mismatch', preview_checks(classroom, 1, expected_question_count=7)['issues'])
        self.assertIn('question_count_mismatch', preview_checks(classroom, 1, expected_question_count=8)['issues'])

    def test_pinyin_scope_registers_four_targets_only_for_the_verified_node(self):
        manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text())
        blueprint = lesson_blueprint(manifest, 'u2-l1')
        self.assertEqual(blueprint['targets'], [
            '单韵母ɑ、o、e的音形', '四声符号与ɑ、o、e各四声', '四线三格与中格位置', 'ɑ、o、e的笔顺与书写尝试'])
        self.assertFalse(blueprint['generationReady'])
        self.assertEqual(blueprint['sourceScope']['sourcePeriods'], [1, 2])
        for other, node in [({**manifest, 'editionId': 'another-edition'}, 'u2-l1'),
                            ({**manifest, 'revisionId': 'another-revision'}, 'u2-l1'),
                            (manifest, 'u9-l9')]:
            with self.subTest(edition=other['editionId'], revision=other['revisionId'], node=node):
                self.assertIsNone(lesson_blueprint(other, node))
        # Registering scope must not make the ordinary generation path billable
        # before a verified static media manifest exists.
        with self.assertRaises(ApiError) as error:
            preview_input(manifest, 'u2-l1')
        self.assertEqual(error.exception.code, 'textbook_preview_media_required')
        self.runtime.start_generation.assert_not_called()

    def test_bpmf_scope_keeps_verified_table_and_stops_before_generation_without_art(self):
        manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text())
        original = deepcopy(manifest)
        blueprint = lesson_blueprint(manifest, 'u2-l3')
        self.assertEqual(blueprint_prompt(blueprint)['expectedQuestionCount'], 4)
        self.assertEqual([row['targetIndex'] for row in blueprint['assessmentMapping']], [0, 1, 2, 3])
        self.assertEqual(len({row['questionId'] for row in blueprint['assessmentMapping']}), 4)
        self.assertFalse(blueprint['generationReady'])
        source = blueprint['sourceScope']
        self.assertTrue(source['textbookBodyRead'])
        table = source['syllableScope']
        syllables = [item for group in table['textbookTableGroups'] for item in group['syllables']]
        self.assertEqual(len(syllables), table['textbookTableCount'])
        self.assertEqual(len(set(syllables)), 15)
        # The textbook's second tone must not be silently replaced by the
        # separate, unverified picture exercise in the teaching design.
        self.assertIn('bí', syllables)
        self.assertNotIn('bǐ', syllables)
        self.assertFalse(table['cartesianExpansionAllowed'])
        self.assertFalse(any(s.startswith('f') and 'ī' in s for s in syllables))
        for other in ({**manifest, 'editionId': 'another-edition'},
                      {**manifest, 'revisionId': 'another-revision'}):
            self.assertIsNone(lesson_blueprint(other, 'u2-l3'))
        with self.assertRaises(ApiError) as error:
            preview_input(manifest, 'u2-l3')
        self.assertEqual(error.exception.code, 'textbook_preview_media_required')
        self.assertEqual(manifest, original)
        self.runtime.start_generation.assert_not_called()
        self.runtime.start_formal_audio_tts.assert_not_called()

    def test_science_known_plants_scope_is_exact_and_operator_adoption_keeps_14_pages(self):
        manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/science-v1/smartedu-science-six-year-g1-upper-5082db8c.directory-85c5a7913d61bf6ad6fd9a50.json').read_text())
        original = deepcopy(manifest)
        node = '494da807-9085-427e-a1c4-bc7d3f4c826f'
        blueprint = lesson_blueprint(manifest, node)
        self.assertEqual(blueprint['scopePages'], [2, 3, 4])
        self.assertEqual(blueprint['sourceScope']['resourceId'], '5082db8c-82e3-4253-be5a-36a4cc7473a6')
        self.assertFalse(blueprint['sourceScope']['humanReviewed'])
        self.assertFalse(blueprint['generationReady'])
        mapping = blueprint['assessmentMapping']
        self.assertEqual([(q['targetIndex'], q['questionId'], q['page'], q['correctAnswer']) for q in mapping], [
            (0, 'plant-known-01', 5, 'B'), (1, 'plant-campus-02', 8, 'C'),
            (2, 'plant-transfer-03', 11, 'A'), (3, 'plant-evidence-04', 13, 'B')])
        for other, requested in [({**manifest, 'editionId': 'other-book'}, node),
                                 ({**manifest, 'revisionId': 'other-revision'}, node),
                                 (manifest, 'b26fdeb4-d30c-411c-9745-70f437fcc3fe')]:
            self.assertIsNone(lesson_blueprint(other, requested))
        with self.assertRaises(ApiError) as error:
            preview_input(manifest, node)
        self.assertEqual(error.exception.code, 'textbook_preview_media_required')
        TextbookLearningService(self.repo).import_manifest(manifest)
        cid = 'synthetic-science'
        picture = f'/api/classroom-media/{cid}/media/plant.png'
        room = {'id': cid, 'stage': {'id': cid, 'name': '植物观察'}, 'scenes': []}
        by_page = {q['page']: q for q in mapping}
        for page in range(1, 15):
            locked = by_page.get(page)
            kind = 'quiz' if locked else 'slide' if page == 1 else 'interactive'
            content = ({'questions': [{'id': locked['questionId'], 'type': 'single', 'question': locked['evidence'],
                'options': [{'value': value, 'label': value} for value in ('A', 'B', 'C')],
                'answer': [locked['correctAnswer']], 'analysis': '看图片中的不同。', 'points': 10}]} if locked else
                {'canvas': {'elements': [{'id': 'plant', 'type': 'image', 'src': picture}]}} if kind == 'slide' else
                {'html': responsive_html('<img src="' + picture + '">')})
            room['scenes'].append({'id': 'p' + str(page), 'order': page, 'type': kind, 'content': content,
                'actions': [{'id': 'speech' + str(page), 'type': 'speech', 'text': locked['evidence'] if locked else '看看植物。'}]})
        authoring = {'mode': 'openmaic_pro_workbench', 'sessionId': 'science-session', 'stageId': cid,
            'skillIds': ['mira-primary-courseware'], 'request': '本课14页原创教学预览。', 'imageProvenance': 'synthetic test only'}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / cid / 'media').mkdir(parents=True)
            (root / cid / 'media/plant.png').write_bytes(b'synthetic plant picture')
            self.runtime.get_classroom.return_value = room
            result = self.service.adopt(manifest['editionId'], manifest['revisionId'], node, cid, root, authoring)
            frozen = json.loads(self.service.get(result['previewKey'])['input_json'])
            self.assertEqual((frozen['previewPrompt']['expectedSceneCount'], frozen['previewPrompt']['expectedQuestionCount']), (14, 4))
            self.assertEqual(frozen['previewPrompt']['targets'], blueprint['targets'])
            self.assertEqual(frozen['sourceScope'], blueprint['sourceScope'])
            self.assertEqual(frozen['knowledgeBrief'], blueprint['knowledgeBrief'])
            self.assertEqual(result['status'], 'review_required')
            self.assertFalse(result['publicationAllowed'])
        self.assertEqual(manifest, original)
        self.runtime.start_generation.assert_not_called()
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.runtime.save_preview_classroom.assert_not_called()

    def test_fltrp_whats_your_name_scope_is_exact_and_operator_adoption_keeps_seven_pages(self):
        manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/fltrp-reviewed-v1/'
            'smartedu-english-six-year-g1-upper-sync-af05bc77.20260928-metadata-1.json').read_text())
        node = 'b1620924-bc84-3321-858f-386bd08786fd'
        blueprint = lesson_blueprint(manifest, node)
        self.assertEqual(blueprint['scopePages'], [8, 9, 10])
        self.assertFalse(blueprint['sourceScope']['humanReviewed'])
        self.assertFalse(blueprint['generationReady'])
        self.assertEqual(blueprint_question_count(blueprint), 2)
        self.assertEqual([(row['targetIndex'], row['questionId'], row['page'], row['correctAnswer'])
            for row in blueprint['assessmentMapping']], [
                (0, 'whatsname-identity-01', 3, 'B'),
                (1, 'whatsname-morning-02', 6, 'A')])
        for other, requested in [({**manifest, 'editionId': 'other-book'}, node),
                                 ({**manifest, 'revisionId': 'other-revision'}, node),
                                 (manifest, '00000000-0000-0000-0000-000000000000')]:
            self.assertIsNone(lesson_blueprint(other, requested))
        for invalid in [
                [{**blueprint['assessmentMapping'][0], 'targetIndex': 2}],
                [blueprint['assessmentMapping'][0],
                 {**blueprint['assessmentMapping'][1], 'questionId': 'whatsname-identity-01'}]]:
            with self.assertRaises(ApiError) as error:
                blueprint_question_count({**blueprint, 'assessmentMapping': invalid})
            self.assertEqual(error.exception.code, 'textbook_preview_scope_unsupported')

        TextbookLearningService(self.repo).import_manifest(manifest)
        cid = 'synthetic-english-whatsname'
        picture = f'/api/classroom-media/{cid}/media/picture.png'
        by_page = {row['page']: row for row in blueprint['assessmentMapping']}
        room = {'id': cid, 'stage': {'id': cid, 'name': "What's your name?"}, 'scenes': []}
        for page in range(1, 8):
            locked = by_page.get(page)
            kind = 'quiz' if locked else 'interactive' if page in (2, 5) else 'slide'
            if locked:
                content = {'questions': [{'id': locked['questionId'], 'type': 'single',
                    'question': locked['evidence'], 'options': [
                        {'value': 'A', 'label': '第一张图'}, {'value': 'B', 'label': '第二张图'}],
                    'answer': [locked['correctAnswer']], 'analysis': '看图片并听老师说。', 'points': 10}]}
            elif kind == 'interactive':
                content = {'html': responsive_html(f'<img src="{picture}"><button>试一试</button>')}
            else:
                content = {'canvas': {'elements': [{'id': f'image-{page}', 'type': 'image', 'src': picture}]}}
            room['scenes'].append({'id': f'page-{page}', 'order': page, 'type': kind, 'content': content,
                'actions': [{'id': f'speech-{page}', 'type': 'speech',
                    'text': locked['evidence'] if locked else '看图片，听一听。'}]})
        authoring = {'mode': 'openmaic_pro_workbench', 'sessionId': 'english-scope-test', 'stageId': cid,
            'skillIds': ['mira-primary-courseware'], 'request': '本课七页原创教学预览。',
            'imageProvenance': 'synthetic test only'}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / cid / 'media').mkdir(parents=True)
            (root / cid / 'media/picture.png').write_bytes(b'synthetic english picture')
            self.runtime.get_classroom.return_value = room
            service = TextbookPreviewService(self.repo, self.runtime,
                authoring_output_root=root / 'isolated-authoring-output')
            result = service.adopt(manifest['editionId'], manifest['revisionId'], node,
                                   cid, root, authoring)
            frozen = json.loads(service.get(result['previewKey'])['input_json'])
        self.assertEqual((frozen['previewPrompt']['expectedSceneCount'],
                          frozen['previewPrompt']['expectedQuestionCount']), (7, 2))
        self.assertEqual(frozen['previewPrompt']['targets'], blueprint['targets'])
        self.assertEqual(frozen['sourceScope'], blueprint['sourceScope'])
        self.assertEqual(result['status'], 'review_required')
        self.assertFalse(result['publicationAllowed'])
        self.runtime.start_generation.assert_not_called()
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.runtime.save_preview_classroom.assert_not_called()

    def test_pinyin_operator_adopt_keeps_18_pages_and_requires_four_questions(self):
        manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text())
        original_manifest = deepcopy(manifest)
        TextbookLearningService(self.repo).import_manifest(manifest)
        picture = '/api/classroom-media/class-pinyin/media/generated-one.png'
        quiz_pages = {6: 1, 11: 2, 14: 3, 18: 4}
        classroom = {'id': 'class-pinyin', 'stage': {'id': 'class-pinyin', 'name': 'ɑ o e'}, 'scenes': []}
        for page in range(1, 19):
            question = {'id': f'u2-l1-q{quiz_pages[page]}', 'type': 'single', 'question': '请听老师的提示，再选出相应的图片。',
                        'options': [{'value': value, 'label': value} for value in ('A', 'B', 'C')],
                        'answer': ['A'], 'analysis': '看一看图片中的不同。', 'points': 10} if page in quiz_pages else None
            kind = 'quiz' if question else 'slide' if page == 1 else 'interactive'
            content = ({'questions': [question]} if question else
                       {'canvas': {'elements': [{'id': 'picture', 'type': 'image', 'src': picture}]}} if page == 1 else
                       {'html': responsive_html(f'<img src="{picture}" />')})
            classroom['scenes'].append({'id': f'scene-p{page}', 'order': page, 'type': kind, 'content': content,
                'actions': [{'id': f'speech-p{page}', 'type': 'speech',
                             'text': question['question'] if question else '听老师说，再看图片试一试。'}]})
        authoring = {'mode': 'openmaic_pro_workbench', 'sessionId': 'pinyin-session', 'stageId': 'class-pinyin',
                     'skillIds': ['mira-primary-courseware'], 'request': '完整制作两个课时的原创拼音教学预览。',
                     'imageProvenance': 'isolated test illustration'}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'class-pinyin/media').mkdir(parents=True)
            (root / 'class-pinyin/media/generated-one.png').write_bytes(b'isolated pinyin picture')
            def adopt():
                return self.service.adopt(manifest['editionId'], manifest['revisionId'], 'u2-l1',
                                          'class-pinyin', root, authoring)
            for count in (3, 5):
                variant = deepcopy(classroom)
                if count == 3:
                    variant['scenes'][-1].update(type='interactive', content={'html': f'<img src="{picture}" />'})
                else:
                    variant['scenes'][5]['content']['questions'].append({**variant['scenes'][5]['content']['questions'][0], 'id': 'extra-question'})
                self.runtime.get_classroom.return_value = variant
                with self.subTest(question_count=count), self.assertRaises(ApiError) as error:
                    adopt()
                self.assertEqual(error.exception.code, 'textbook_preview_adoption_rejected')
                self.assertIn('question_count_mismatch', str(error.exception))
            self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM learning_textbook_course_previews').fetchone()['n'], 0)
            self.runtime.get_classroom.return_value = deepcopy(classroom)
            summary = adopt()
            frozen = json.loads(self.service.get(summary['previewKey'])['input_json'])
            blueprint = lesson_blueprint(manifest, 'u2-l1')
            self.assertEqual((frozen['previewPrompt']['expectedSceneCount'], frozen['previewPrompt']['expectedQuestionCount']), (18, 4))
            self.assertEqual(frozen['previewPrompt']['targets'], blueprint['targets'])
            self.assertEqual(frozen['knowledgeBrief'], blueprint['knowledgeBrief'])
            self.assertEqual(frozen['sourceScope'], blueprint['sourceScope'])
            self.assertEqual(frozen['originalMedia']['assets'][0]['sha256'], hashlib.sha256(b'isolated pinyin picture').hexdigest())
            self.assertEqual((summary['status'], summary['publicationAllowed']), ('review_required', False))
            self.assertEqual(manifest, original_manifest)
        self.runtime.start_generation.assert_not_called()
        self.runtime.start_formal_audio_tts.assert_not_called()
        self.runtime.save_preview_classroom.assert_not_called()

    def test_preview_does_not_approve_publication_or_dispatch_on_prepare(self):
        key = self.prepare()
        self.assertEqual(key, self.prepare())
        self.runtime.start_generation.assert_not_called()
        self.assertFalse(preview_input(self.manifest, "u1-l1")["publicationAllowed"])
        with self.assertRaises(ApiError):
            generation_brief(self.manifest, "u1-l1")
        self.assertEqual(self.db.execute("SELECT COUNT(*) AS n FROM learning_textbook_course_builds").fetchone()["n"], 0)
        with self.assertRaises(ApiError):
            preview_input(self.manifest, "u1-l2")

    def test_repeated_start_and_poll_never_create_a_second_job(self):
        key = self.prepare()
        for _ in range(3):
            self.service.start(key)
            self.service.poll(key)
        self.runtime.start_generation.assert_called_once()

    def test_freeze_keeps_audio_and_reuses_an_immutable_preview_url(self):
        key = self.prepare()
        self.service.start(key)
        self.job.status, self.job.classroom_id = "succeeded", "class-a"
        scenes = [{"id": f"scene-{i}", "type": t, "actions": [{"type": "speech", "text": "天", "audioId": str(i), "audioUrl": "/audio/a.wav"}],
                   "content": scene_content(t)}
                  for i, t in enumerate(["slide"] * 5 + ["interactive", "quiz", "slide"])]
        documents = {"class-a": {"id": "class-a", "stage": {"id": "class-a"}, "scenes": scenes}}
        def read(classroom_id):
            if classroom_id not in documents:
                raise OpenMaicFullRuntimeError("not_found", "Not found", status_code=404)
            return deepcopy(documents[classroom_id])
        self.runtime.get_classroom.side_effect = read
        self.runtime.save_preview_classroom.side_effect = lambda c: documents.update({c["id"]: deepcopy(c)})
        self.service.poll(key)
        frozen = self.service.freeze(key)
        self.assertIn("/classroom/tbprev_", frozen["previewUrl"])
        self.assertEqual(frozen, self.service.freeze(key))
        self.runtime.save_preview_classroom.assert_called_once()
        self.runtime.start_generation.assert_called_once()
        options = self.runtime.start_generation.call_args.kwargs
        self.assertFalse(options["enable_web_search"])
        self.assertFalse(options["enable_image_generation"])
        self.assertFalse(options["enable_video_generation"])
        self.assertFalse(options["enable_tts"])

    def test_unknown_dispatch_and_crashed_claim_never_retry(self):
        key = self.prepare()
        self.runtime.start_generation.side_effect = TimeoutError()
        with self.assertRaises(ApiError):
            self.service.start(key)
        self.assertEqual(self.service.start(key)["status"], "dispatch_unknown")
        self.runtime.start_generation.assert_called_once()
        self.db.execute("UPDATE learning_textbook_course_previews SET status='dispatching'")
        self.assertEqual(self.service.start(key)["status"], "dispatching")
        self.runtime.start_generation.assert_called_once()

    def test_failed_job_does_not_retry_and_incomplete_output_is_not_ready(self):
        key = self.prepare()
        self.service.start(key)
        self.job.status = "failed"
        self.assertEqual(self.service.poll(key)["status"], "failed")
        self.assertEqual(self.service.start(key)["status"], "failed")
        self.runtime.start_generation.assert_called_once()

    def test_success_snapshots_classroom_and_reuses_without_native_calls(self):
        key = self.prepare()
        self.service.start(key)
        self.job.status, self.job.classroom_id = "succeeded", "class-a"
        scenes = [{"type": t, "actions": [{"type": "speech", "text": "天", "audioId": str(i), "audioUrl": "/audio/a.wav"}],
                   "content": scene_content(t)}
                  for i, t in enumerate(["slide"] * 5 + ["interactive", "quiz", "slide"])]
        self.runtime.get_classroom.return_value = {"id": "class-a", "stage": {"id": "class-a"}, "scenes": scenes}
        ready = self.service.poll(key)
        self.assertEqual(ready["status"], "preview_ready")
        self.assertFalse(ready["publicationAllowed"])
        self.assertEqual(ready, self.service.poll(key))
        self.assertEqual(ready, self.service.start(key))
        self.runtime.get_classroom.assert_called_once()
        self.runtime.start_generation.assert_called_once()

    def test_new_generated_preview_without_responsive_marker_stays_in_review(self):
        key = self.prepare()
        self.service.start(key)
        self.job.status, self.job.classroom_id = 'succeeded', 'class-a'
        scenes = [{'type': kind, 'actions': [{'type': 'speech', 'text': '看看图片。', 'audioId': str(i), 'audioUrl': '/a.wav'}],
                   'content': scene_content(kind)} for i, kind in enumerate(['slide'] * 5 + ['interactive', 'quiz', 'slide'])]
        scenes[5]['content']['html'] = scenes[5]['content']['html'].replace(RESPONSIVE_HEAD, '<head></head>')
        self.runtime.get_classroom.return_value = {'id': 'class-a', 'stage': {'id': 'class-a'}, 'scenes': scenes}
        result = self.service.poll(key)
        self.assertEqual(result['status'], 'review_required')
        self.assertIn('responsive_activity_marker_missing', result['result']['issues'])
        self.runtime.start_generation.assert_called_once()

    def test_incomplete_output_and_changed_origin_are_rejected(self):
        key = self.prepare()
        self.service.start(key)
        self.job.status, self.job.classroom_id = "succeeded", "class-a"
        self.runtime.get_classroom.return_value = {"id": "class-a", "stage": {"id": "class-a"}, "scenes": []}
        self.assertEqual(self.service.poll(key)["status"], "review_required")
        self.runtime.base_url = "http://127.0.0.1:4100"
        with self.assertRaises(ApiError):
            self.service.start(key)

    def test_text_only_or_placeholder_images_cannot_pass_picture_lesson_review(self):
        scenes = [{"type": t, "actions": [{"type": "speech", "text": "天", "audioId": str(i), "audioUrl": "/audio/a.wav"}],
                   "content": scene_content(t)} for i, t in enumerate(["slide"] * 5 + ["interactive", "quiz", "slide"])]
        self.assertEqual(preview_checks({"scenes": scenes}, media_manifest=preview_media())["issues"], [])
        scenes[0]["content"]["canvas"]["elements"][0]["src"] = "generated_image_placeholder"
        scenes[5]["content"] = {"html": "<p>请看插画</p>"}
        issues = preview_checks({"scenes": scenes}, media_manifest=preview_media())["issues"]
        self.assertIn("original_teaching_image_missing", issues)
        self.assertIn("interactive_teaching_image_missing", issues)

    def test_durable_segment_audio_reuses_receipts_and_stops_ambiguous_attempt(self):
        key = self.prepare()
        self.service.start(key)
        self.job.status, self.job.classroom_id = "succeeded", "class-a"
        classroom = {"id": "class-a", "stage": {"id": "class-a"}, "scenes": [{"id": "scene-a", "order": 1, "type": "slide",
                     "actions": [{"id": "action-a", "type": "speech", "text": "天空的天。"}], "content": {}}]}
        self.runtime.get_classroom.side_effect = lambda _: deepcopy(classroom)
        self.runtime.save_preview_classroom.side_effect = lambda value: classroom.update(deepcopy(value))
        self.service.poll(key)
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
            wav.writeframes(b"\0\0" * 2400)
        bytes_ = audio.getvalue()
        receipts, outcome = {}, {"status": "succeeded"}
        def read(request_id):
            if request_id not in receipts:
                raise OpenMaicFullRuntimeError("not_found", "Not found", status_code=404)
            return receipts[request_id]
        def start(**kwargs):
            receipt = {"requestId": kwargs["request_id"], "status": outcome["status"], "audioSha256": hashlib.sha256(bytes_).hexdigest()}
            receipts[kwargs["request_id"]] = receipt
            return receipt
        self.runtime.get_formal_audio_tts.side_effect = read
        self.runtime.start_formal_audio_tts.side_effect = start
        self.runtime.download_formal_audio_tts.return_value = bytes_
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "class-a.json"
            source.write_text(json.dumps(classroom))
            result = narrate_preview(self.service, key, root)
            self.assertEqual(result["result"]["audioSeconds"], 0.1)
            source.write_text(json.dumps(classroom))
            narrate_preview(self.service, key, root)
            self.runtime.start_formal_audio_tts.assert_called_once()
            self.runtime.download_formal_audio_tts.assert_called_once()
            # A stalled or refused call is never re-sent under its own id; the
            # next attempt gets a new, recorded id.
            first = next(iter(receipts))
            receipts[first]["status"] = "ambiguous"
            result = narrate_preview(self.service, key, root)
            self.assertIsNone(result["result"]["audioStopCode"])
            self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 2)
            retry = self.runtime.start_formal_audio_tts.call_args.kwargs["request_id"]
            self.assertNotEqual(retry, first)
            self.assertEqual(result["result"]["audioReceiptCount"], 2)
            self.assertEqual(classroom["scenes"][0]["actions"][0]["audioId"], retry)
            # One run sends at most two calls for a line, then stops.
            receipts[retry]["status"] = "failed"
            outcome["status"] = "failed"
            result = narrate_preview(self.service, key, root)
            self.assertEqual(result["result"]["audioStopCode"], "textbook_preview_audio_failed")
            self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 4)
            # A later run (say after a lapsed provider account is topped up)
            # reads every earlier attempt back and tries again.
            outcome["status"] = "succeeded"
            result = narrate_preview(self.service, key, root)
            self.assertIsNone(result["result"]["audioStopCode"])
            self.assertEqual(self.runtime.start_formal_audio_tts.call_count, 5)
            self.assertEqual(result["result"]["audioReceiptCount"], 5)

    def test_operator_pages_become_self_contained_or_are_refused(self):
        katex = ('<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">\n'
                 '<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>\n')
        page = lambda html: {'scenes': [{'type': 'interactive', 'content': {'html': html}}]}
        module = (Path(__file__).parents[2] / 'openmaic-runtime/.runtime/OpenMAIC/public/vendor/three/0.160.0/three.module.js')
        source = page('<head>' + katex + '</head><svg xmlns="http://www.w3.org/2000/svg"></svg>'
                      '<script type="module">const THREE = ' + THREE_IMPORT + ';renderMathInElement(document.body);</script>')
        with self.assertRaises(ApiError):
            self_contained_classroom(source, lambda: b'another build')
        if module.is_file():
            html = self_contained_classroom(source, module.read_bytes)['scenes'][0]['content']['html']
            self.assertIn('window.renderMathInElement=function(){}', html)
            self.assertIn('await import("data:text/javascript;base64,', html)
            self.assertNotIn('jsdelivr', html)
            self.assertIn(THREE_IMPORT, source['scenes'][0]['content']['html'])
        for refused in ('<script src="https://unpkg.com/three@0.160.0/build/three.module.js"></script>',
                        '<img src="//cdn.example.com/a.png">', '<script>katex.render("x", el)</script>',
                        '<script>let best = localStorage.getItem("best") || 0;</script>'):
            with self.assertRaises(ApiError) as error:
                self_contained_classroom(page(refused), module.read_bytes)
            self.assertEqual(error.exception.code, 'textbook_preview_adoption_rejected')
        plain = page('<p>数一数</p><script>// a.b 不是地址\nconst half = 4 / 2;</script>')
        self.assertEqual(self_contained_classroom(plain, module.read_bytes), plain)

    def test_adopted_operator_classroom_never_dispatches_and_binds_audited_question_audio(self):
        manifest = json.loads((Path(__file__).parents[1] / 'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text())
        TextbookLearningService(self.repo).import_manifest(manifest)
        picture = '/api/classroom-media/class-op/media/generated-one.png'
        questions = [{'id': f'q{i}', 'type': 'single', 'question': f'第{i}题，听一听，选一选。', 'answer': ['A'], 'points': 10,
                      'analysis': '数一数就知道。', 'options': [{'label': '一个', 'value': 'A'}, {'label': '两个', 'value': 'B'}]}
                     for i in range(1, 8)]
        def speech(scene, index, text):
            return {'id': f'{scene}-speech-{index}', 'type': 'speech', 'text': text}
        def cues(items):
            return '<script id="mira-narration-cues" type="application/json">' + json.dumps({
                'schemaVersion': 'mira.interactive.narration-cues.v1',
                'cues': [{'id': cue, 'text': text} for cue, text in items]}, ensure_ascii=False) + '</script>'
        def page(html):
            return {'scenes': [classroom['scenes'][0], {**classroom['scenes'][1], 'content': {'html': html}}, classroom['scenes'][2]]}
        classroom = {'id': 'class-op', 'stage': {'id': 'class-op', 'name': '数一数'}, 'scenes': [
            {'id': 'scene-1', 'order': 1, 'type': 'slide', 'actions': [{'id': 'act-intro', 'type': 'speech', 'text': '看，这是野餐垫。'}],
             'content': {'canvas': {'elements': [{'type': 'image', 'src': picture}]}}},
            {'id': 'scene-2', 'order': 2, 'type': 'interactive',
             'actions': [{'id': 'act-intro', 'type': 'speech', 'text': '放一个苹果。'}, speech('scene-2', 2, '对了，真棒！')],
             'content': {'html': f'<html>{RESPONSIVE_HEAD}<body><img src="{picture}" />' + cues([('ask', '放一个苹果。'), ('right', '对了，真棒！')])
                         + '<button onclick="window.miraNarrate(\'ask\')"></button></body></html>'}},
            {'id': 'scene-3', 'order': 3, 'type': 'quiz', 'content': {'questions': questions},
             'actions': [speech('scene-3', 0, '我们来选一选。')] + [speech('scene-3', i, q['question']) for i, q in enumerate(questions, 1)]}]}
        authoring = {'mode': 'openmaic_pro_workbench', 'sessionId': 'session-1', 'stageId': 'stage-1',
                     'skillIds': ['mira-primary-courseware'], 'request': '做一节原创互动课。', 'imageProvenance': 'original illustration'}
        self.runtime.get_classroom.side_effect = lambda _: deepcopy(classroom)
        self.runtime.save_preview_classroom.side_effect = lambda value: classroom.update(deepcopy(value))
        audio = io.BytesIO()
        with wave.open(audio, 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
            wav.writeframes(b'\0\0' * 2400)
        receipts = {}
        def read(request_id):
            if request_id not in receipts:
                raise OpenMaicFullRuntimeError('not_found', 'Not found', status_code=404)
            return receipts[request_id]
        def start(**kwargs):
            receipts[kwargs['request_id']] = {'requestId': kwargs['request_id'], 'status': 'succeeded',
                                              'audioSha256': hashlib.sha256(audio.getvalue()).hexdigest()}
            return receipts[kwargs['request_id']]
        self.runtime.get_formal_audio_tts.side_effect = read
        self.runtime.start_formal_audio_tts.side_effect = start
        self.runtime.download_formal_audio_tts.return_value = audio.getvalue()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'class-op/media').mkdir(parents=True)
            (root / 'class-op/media/generated-one.png').write_bytes(b'original picture')
            adopt = lambda record=authoring, **options: self.service.adopt(
                manifest['editionId'], manifest['revisionId'], 'u1-l2', 'class-op', root, record, **options)
            for broken, code in [
                    ({'scenes': classroom['scenes'][:2] + [{**classroom['scenes'][2], 'content': {'questions': questions[:6]}}]}, 'textbook_preview_adoption_rejected'),
                    ({'scenes': [{**classroom['scenes'][0], 'content': {'canvas': {'elements': []}}}] + classroom['scenes'][1:]}, 'textbook_preview_adoption_rejected'),
                    ({'scenes': classroom['scenes'][:2] + [{**classroom['scenes'][2], 'content': {'questions': [{**questions[0], 'questionAudioUrl': '/a.wav'}] + questions[1:]}}]}, 'textbook_preview_adoption_rejected'),
                    ({'scenes': classroom['scenes'] + [{**classroom['scenes'][2], 'id': 'scene-4'}]}, 'textbook_preview_adoption_rejected'),
                    (page(f'<img src="{picture}" /><script>speechSynthesis.speak(new SpeechSynthesisUtterance("一"))</script>'), 'textbook_preview_adoption_rejected'),
                    (page(f'<img src="{picture}" />' + cues([('ask', '老师没有读过的话。')])), 'textbook_preview_adoption_rejected'),
                    (page(f'<img src="{picture}" />' + cues([('ask', '放一个苹果。')]) + '<script>window.miraNarrate=()=>{};</script>'), 'textbook_preview_adoption_rejected')]:
                variant = {**classroom, **broken}
                self.runtime.get_classroom.side_effect = lambda _, value=variant: deepcopy(value)
                self.runtime.save_preview_classroom.side_effect = lambda value, target=variant: target.update(deepcopy(value))
                with self.assertRaises(ApiError) as error:
                    adopt()
                self.assertEqual(error.exception.code, code)
            self.runtime.get_classroom.side_effect = lambda _: deepcopy(classroom)
            self.runtime.save_preview_classroom.side_effect = lambda value: classroom.update(deepcopy(value))
            with self.assertRaises(ApiError) as error:
                adopt(record={**authoring, 'mode': 'hand_written'})
            self.assertEqual(error.exception.code, 'textbook_preview_authoring_invalid')
            self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM learning_textbook_course_previews').fetchone()['n'], 0)

            summary = adopt()
            self.assertEqual((summary['status'], summary['runtimeJobId'], summary['publicationAllowed']),
                             ('review_required', 'agent-session:session-1:class-op', False))
            self.assertEqual(adopt()['previewKey'], summary['previewKey'])
            frozen = json.loads(self.service.get(summary['previewKey'])['input_json'])
            self.assertEqual((frozen['previewPrompt']['expectedSceneCount'], frozen['previewPrompt']['expectedQuestionCount']), (3, 7))
            self.assertEqual(frozen['originalMedia']['assets'][0]['sha256'], hashlib.sha256(b'original picture').hexdigest())
            self.runtime.start_generation.assert_not_called()

            revised = deepcopy(classroom)
            revised['stage'] = {**revised['stage'], 'name': '数一数 · 图片修订'}
            self.runtime.get_classroom.side_effect = lambda _: deepcopy(revised)
            revision_two = adopt(teaching_revision='2', regeneration={
                'reason': '同一终态会话的图片语义修订',
                'budgetReference': 'provider-free operator repair; no generation call',
            })
            self.assertNotEqual(revision_two['previewKey'], summary['previewKey'])
            self.assertEqual((revision_two['status'], revision_two['publicationAllowed']),
                             ('review_required', False))
            expected_job_id = self.service._operator_runtime_job_id(authoring, 'class-op', '2')
            self.assertEqual(revision_two['runtimeJobId'], expected_job_id)
            self.assertLessEqual(len(expected_job_id), 128)
            rows = self.db.execute(
                'SELECT preview_key,status,input_json FROM learning_textbook_course_previews ORDER BY created_at'
            ).fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual([json.loads(row['input_json']).get('teachingRevision', '1') for row in rows],
                             ['1', '2'])
            self.assertEqual([row['status'] for row in rows], ['review_required', 'review_required'])
            self.runtime.get_classroom.side_effect = lambda _: deepcopy(classroom)

            (root / 'class-op.json').write_text(json.dumps(classroom))
            result = narrate_preview(self.service, summary['previewKey'], root)
            self.assertEqual((result['status'], result['result']['issues']), ('preview_ready', []))
            saved = json.loads(self.service.get(summary['previewKey'])['classroom_json'])
            self.assertEqual([a['id'] for scene in saved['scenes'][:2] for a in scene['actions']],
                             ['scene-1-act-intro', 'scene-2-act-intro', 'scene-2-speech-2'])
            clips = {a['text']: a['audioUrl'] for a in saved['scenes'][2]['actions']}
            for question in saved['scenes'][2]['content']['questions']:
                self.assertEqual('http://127.0.0.1:3100' + question['questionAudioUrl'], clips[question['question']])
            page_clips = {a['text']: a['audioUrl'].removeprefix('http://127.0.0.1:3100') for a in saved['scenes'][1]['actions']}
            helper = saved['scenes'][1]['content']['html'].split('const clips=')[1].split(';let active')[0]
            self.assertEqual(json.loads(helper), {'ask': page_clips['放一个苹果。'], 'right': page_clips['对了，真棒！']})
            self.runtime.start_generation.assert_not_called()


class TextbookCitationResourceTest(unittest.TestCase):
    @staticmethod
    def classroom(html, **content):
        return {'scenes': [{'type': 'interactive', 'content': {'html': html, **content}}]}

    def check(self, html, **content):
        return self_contained_classroom(self.classroom(html, **content), lambda: b'')

    def assert_rejected(self, html, **content):
        with self.assertRaises(ApiError) as error:
            self.check(html, **content)
        self.assertEqual(error.exception.code, 'textbook_preview_adoption_rejected')

    def test_visible_citations_preserve_exact_html_without_network_attributes(self):
        html = ('<details><summary>家长参考</summary><p>来源：https://example.com/book?a=1&amp;b=2</p>'
                '<p>&#104;ttps://publisher.example.org/source.pdf</p>'
                '<code>&lt;a href="https://example.com/"&gt;示例文字&lt;/a&gt;</code></details>')
        source = self.classroom(html)
        self.assertEqual(self.check(html), source)
        self.assertEqual(source['scenes'][0]['content']['html'], html)

    def test_external_attribute_urls_remain_rejected(self):
        for html in ('<a href="https://example.com">来源</a>',
                     '<img src="//cdn.example.com/image.png">',
                     '<img srcset="/local.png 1x, https://cdn.example.com/image.png 2x">',
                     '<div style="background:url(https://cdn.example.com/image.png)"></div>',
                     '<p data-source="https://example.com/source">来源</p>',
                     '<iframe srcdoc="&lt;img src=&quot;https://example.com/a&quot;&gt;"></iframe>'):
            with self.subTest(html=html):
                self.assert_rejected(html)

    def test_entity_encoded_and_split_attribute_urls_cannot_bypass(self):
        for html in ('<a href="https:&#47;&#47;example.com/a">来源</a>',
                     '<img src="&sol;&sol;example&#46;com/a">',
                     '<img src="https://exa&#x09;mple.com/a">',
                     '<img src="&amp;#x2f;&amp;#x2f;example.com/a">',
                     '<div style="background:url(https&colon;&sol;&sol;example.com/a)"></div>'):
            with self.subTest(html=html):
                self.assert_rejected(html)

    def test_script_and_style_urls_remain_rejected_even_in_malformed_raw_text(self):
        for html in ('<script>const source="https://example.com/a";</script>',
                     '<script>const source="https:&#47;&#47;example.com/a";</script>',
                     '<style>body{background:url(https://example.com/a)}</style>',
                     '<style>@import "&sol;&sol;example.com/a.css";</style>',
                     '<script/>location="https://example.com/a"</script>',
                     '<script/><style></style>location="https://example.com/a"</script>',
                     '<script>location="https://example.com/a"',
                     '<style>body{background:url(https://example.com/a)}'):
            with self.subTest(html=html):
                self.assert_rejected(html)

    def test_existing_namespace_exception_and_content_url_gate_are_unchanged(self):
        html = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L1 1"/></svg>'
        self.assertEqual(self.check(html), self.classroom(html))
        for url in ('http://example.com/page', 'https://example.com/page', '//example.com/page'):
            with self.subTest(url=url):
                self.assert_rejected('<p>来源：https://example.com/page</p>', url=url)


if __name__ == "__main__":
    unittest.main()
