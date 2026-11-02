"""Reviewed mathematics scope and protected zero-quiz adoption; no provider calls."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from content.textbook_catalog import validate_manifest
from content.textbook_preview import blueprint_question_count, lesson_blueprint, operator_preview_input
from core.errors import ApiError


class CompareOrdinalScopeTests(unittest.TestCase):
    def setUp(self):
        content = Path(__file__).parents[1] / 'content/textbooks'
        self.manifest = validate_manifest(json.loads((content / 'official-directories-v1' /
            'pep-math-g1-upper-2022-standard.directory-ede7a8c63c337cf95a03fe79.json').read_text()))
        self.nodes = ('32aff930-d2cb-475f-8263-acf853fd4edf',
                      '803c9ac0-d35c-47a6-9a86-019581b8f4f7')
        self.author = dict(mode='openmaic_pro_workbench', sessionId='fixture-session',
                           stageId='fixture-stage', skillIds=['fixture'], request='制作已审范围。',
                           imageProvenance='synthetic fixture; no provider calls or generated media')
        self.classroom = {'id': 'fixture-stage', 'stage': {'id': 'fixture-stage'}, 'scenes': [
            {'id': 'opening', 'type': 'slide'}, {'id': 'practice', 'type': 'interactive'},
            {'id': 'closing', 'type': 'slide'}]}
        self.candidate = dict(schemaVersion='mira.textbook.authoring-candidate.v1',
            verification='frozen_identity_and_artifact_integrity_only', sceneCount=3, assetCount=0,
            interactionPolicyVersion=3, sha256='1' * 64, contractSha256='2' * 64,
            interactionPolicySha256='3' * 64)

    def test_exact_edition_and_distinct_lesson_scope_without_invented_questions(self):
        for node, title, pages in zip(self.nodes, ('比大小', '第几'), ([17, 18], [19])):
            with self.subTest(node=node):
                blueprint = lesson_blueprint(self.manifest, node)
                self.assertEqual(blueprint['title'], title)
                self.assertEqual(blueprint['status'], 'scope_verified_preview_only')
                self.assertEqual(blueprint['scopePages'], pages)
                self.assertEqual(blueprint['knowledgeBrief']['assessmentMode'], 'observed')
                self.assertNotIn('assessmentMapping', blueprint)
                self.assertEqual(blueprint_question_count(blueprint), len(blueprint['targets']))
                self.assertFalse(blueprint['generationReady'])
                source = next(record for record in blueprint['sourceScope']['reviewEvidence']
                              if record['nodeId'] == node)
                query = parse_qs(urlsplit(source['officialCourseUrl']).query)
                self.assertEqual(query['chapterId'], [node])
                self.assertEqual(query['classHourId'], ['lesson_1'])
                self.assertEqual(source['teachingRevision'], '1')
        wrong_revision = {**self.manifest, 'revisionId': 'other-revision'}
        self.assertIsNone(lesson_blueprint(wrong_revision, self.nodes[0]))

    def test_verified_empty_locks_preserve_targets_and_freeze_no_native_quiz(self):
        for node in self.nodes:
            with self.subTest(node=node):
                blueprint = lesson_blueprint(self.manifest, node)
                result = operator_preview_input(self.manifest, node, self.classroom, {}, self.author,
                    authoring_candidate=self.candidate, verified_locked_assessments=[])
                self.assertEqual(result['previewPrompt']['targets'], blueprint['targets'])
                self.assertEqual(result['previewPrompt']['expectedQuestionCount'], 0)
                self.assertEqual(result['previewPrompt']['requiredSceneTypes'], ['slide', 'interactive'])
                self.assertEqual(result['previewPrompt']['expectedSceneCount'], 3)
                self.assertFalse(result['publicationAllowed'])

    def test_empty_locks_require_a_verified_candidate_and_never_fix_bad_mapping(self):
        for node in self.nodes:
            with self.subTest(node=node):
                with self.assertRaises(ApiError) as caught:
                    operator_preview_input(self.manifest, node, self.classroom, {}, self.author,
                                           verified_locked_assessments=[])
                self.assertEqual(caught.exception.code, 'textbook_preview_candidate_invalid')
                malformed = deepcopy(lesson_blueprint(self.manifest, node))
                malformed['assessmentMapping'] = []
                with patch('content.textbook_preview.lesson_blueprint', return_value=malformed):
                    with self.assertRaises(ApiError) as caught:
                        operator_preview_input(self.manifest, node, self.classroom, {}, self.author,
                            authoring_candidate=self.candidate, verified_locked_assessments=[])
                self.assertEqual(caught.exception.code, 'textbook_preview_scope_unsupported')


if __name__ == '__main__':
    unittest.main()
