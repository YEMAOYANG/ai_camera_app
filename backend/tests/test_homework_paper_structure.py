"""Private receipt -> original-paper DTO, isolated DB/files and no HTTP."""
from copy import deepcopy
import hashlib
import json
import unittest
from unittest.mock import patch

from services.homework_paper_structure import paper_structure, selected_item_context
from services.homework_tencent_grading import canonical, digest
from tests.test_homework_tencent_grading import TencentPipelineTest, marks, source


def polygon(x, y, width, height):
    return [x, y, x+width, y, x+width, y+height, x, y+height]


class PaperStructureTest(unittest.TestCase):
    setUp = TencentPipelineTest.setUp
    create = TencentPipelineTest.create
    upload = TencentPipelineTest.upload
    queued = TencentPipelineTest.queued
    due = TencentPipelineTest.due
    two_pages = TencentPipelineTest.two_pages

    def complete(self, *, submit=None, result=None):
        submit = deepcopy(submit or source())
        result = deepcopy(result or marks())
        def post(path, *, receipt_callback, **kw):
            receipt_callback('SubmitQuestionMarkAgentJob', canonical(submit).encode(), {})
            return {'jobIds': ['job-offline'], 'rawReceipt': submit}
        def get(identity, *, receipt_callback):
            receipt_callback('DescribeQuestionMarkAgentJob', canonical(result).encode(), {})
            return {'status': 'DONE', 'rawReceipt': result}
        self.tencent.submit_question.side_effect = post
        self.tencent.describe_question.side_effect = get
        submission = self.queued()
        self.service.process_next(); self.due(); self.service.process_next()
        self.tencent.submit_question.reset_mock(); self.tencent.describe_question.reset_mock()
        self.identity = submission['id']
        return self.service.get('parent-a', self.identity)['submission']

    def detail(self):
        return self.service.student_detail('student-a', self.identity)['submission']

    def context(self, item=None):
        with self.service.repository.transaction() as conn:
            row = self.service.repository.submission(conn, 'family-a', self.identity)
            item = item or self.service.repository.items(conn, self.identity)[0]
            return selected_item_context(self.service, conn, row, item)

    def call(self):
        return self.db.execute('SELECT * FROM homework_provider_calls WHERE submission_id=?', (self.identity,)).fetchone()

    def mutate_receipt(self, fn):
        call = self.call(); receipt = json.loads(call['receipt_json'])
        fn(receipt)
        self.db.execute('UPDATE homework_provider_calls SET receipt_json=? WHERE id=?', (canonical(receipt), call['id']))
        self.db.raw.commit()

    def rewrite_journal(self, *, submit=False, mutate):
        """Replace only the anonymous fixture's bytes and rebind its digests."""
        call = self.call(); receipt = json.loads(call['receipt_json'])
        ref = receipt['submitResponse'] if submit else receipt['completedJobs']['job-offline']
        path = self.store._path(ref['storageKey'])
        envelope = json.loads(path.read_bytes())
        import base64
        raw = json.loads(base64.b64decode(envelope['rawBase64']))
        mutate(envelope, raw)
        data = canonical(raw).encode()
        envelope['rawBase64'] = base64.b64encode(data).decode()
        saved = canonical(envelope).encode(); path.write_bytes(saved)
        ref.update(sha256=hashlib.sha256(saved).hexdigest(), rawSha256=hashlib.sha256(data).hexdigest())
        self.db.execute('UPDATE homework_provider_calls SET receipt_json=? WHERE id=?', (canonical(receipt), call['id']))
        self.db.raw.commit()

    def test_details_only_read_no_provider_score_or_raw_projection(self):
        detail = self.complete()
        before = self.db.execute('SELECT result_json FROM homework_items WHERE submission_id=?', (self.identity,)).fetchall()
        projection = detail['paperStructure']
        self.assertEqual(projection['coverage'], {'status': 'ready', 'issues': [], 'linkedAnswers': 1, 'totalAnswers': 1})
        question = projection['pages'][0]['questions'][0]
        self.assertEqual(question['answers'][0]['itemId'], detail['originalPaperItems'][0]['id'])
        self.assertEqual(question['prompt'], '3 + 2 =')
        self.assertEqual(self.detail()['paperStructure'], projection)
        self.assertEqual(self.context()['answerTarget']['itemId'], question['answers'][0]['itemId'])
        for value in ('rawBase64', 'storageKey', 'JobId', 'RequestId', 'RightAnswer', 'AnswerAnalysis', 'https://'):
            self.assertNotIn(value, canonical(projection))
        with patch('services.homework_paper_structure.paper_structure', side_effect=AssertionError('lists must not load receipts')):
            self.assertNotIn('paperStructure', self.service.list_parent('parent-a', 'child-a')['submissions'][0])
            self.assertNotIn('paperStructure', self.service.list_student('student-a')['submissions'][0])
        self.tencent.submit_question.assert_not_called(); self.tencent.describe_question.assert_not_called()
        self.assertEqual(before, self.db.execute('SELECT result_json FROM homework_items WHERE submission_id=?', (self.identity,)).fetchall())

    def test_tree_shared_stem_multi_blank_illustration_and_precise_existing_ids(self):
        raw = marks(); leaf = raw['Response']['MarkInfos'][0]
        leaf['MarkItemTitle'] = '1. 请数出图中的数量，填入两个空。'
        second = deepcopy(leaf['AnswerInfos'][0]); second['HandwriteInfoPositions'] = polygon(600, 110, 50, 70)
        leaf['AnswerInfos'].append(second)
        raw['Response']['MarkInfos'] = [{'MarkItemTitle': '第一题：看图填空',
            'QuestionPositions': polygon(80, 50, 640, 400),
            'QuestionImagePositions': [{'Position': polygon(90, 320, 180, 120)}], 'MarkInfos': [leaf]}]
        detail = self.complete(result=raw)
        page = detail['paperStructure']['pages'][0]; parent = page['questions'][0]; node = parent['children'][0]
        self.assertEqual(parent['prompt'], '第一题：看图填空')
        self.assertEqual([answer['index'] for answer in node['answers']], [1, 2])
        self.assertEqual([answer['count'] for answer in node['answers']], [2, 2])
        self.assertEqual({answer['itemId'] for answer in node['answers']}, {item['id'] for item in detail['originalPaperItems']})
        self.assertTrue(parent['illustrations'][0]['geometryVerified'])
        context = self.context()
        self.assertEqual(len(context['questionPath']), 2)
        self.assertEqual(len(context['illustrations']), 1)
        self.assertTrue(context['geometryVerified'])
        self.assertGreaterEqual(context['region']['y'] + context['region']['height'], .44)
        self.assertTrue(all(item['status']=='incorrect' for item in detail['items']))
        for item in detail['items']:
            self.assertEqual(item['reviewContext']['grading']['referenceGate']['status'],'provider_consistent')
            self.assertEqual(item['reviewContext']['grading']['studentQuality']['status'],'needs_review')

    def test_question_info_figures_options_tables_only_unique_spatial_join(self):
        submit = source(); entry = submit['Response']['QuestionInfo'][0]['ResultList'][0]
        entry['Question'][0]['Text'] = '请观察图表并选择正确的选项。'
        entry['Figure'] = [{'Text': 'https://private.example/signed?token=secret', 'Coord': polygon(100, 190, 120, 90), 'PageIndex': 1}]
        entry['Option'] = [{'Text': 'A. 三只', 'Index': 1, 'CoordPolygon': polygon(240, 190, 100, 60)},
            {'Text': 'B. 五只', 'Index': 2, 'Coord': polygon(350, 190, 100, 60)}]
        entry['Table'] = [{'Text': '红色 3\n蓝色 5', 'Coord': polygon(500, 190, 170, 90)}]
        detail = self.complete(submit=submit)
        node = detail['paperStructure']['pages'][0]['questions'][0]
        self.assertEqual(node['prompt'], entry['Question'][0]['Text'])
        self.assertEqual(len(node['options']), 2); self.assertEqual(len(node['tables']), 1)
        self.assertEqual(node['illustrations'][0]['region']['x'], .125)
        self.assertNotIn('private.example', canonical(detail['paperStructure']))
        context = self.context(); self.assertTrue(context['geometryVerified'])
        self.assertEqual(len(context['options']), 2)
        # A second possible owner with the same region invalidates the join;
        # never pick the first result/nearest region/array index.
        self.rewrite_journal(submit=True, mutate=lambda envelope, raw: raw['Response']['QuestionInfo'][0]['ResultList'].append(deepcopy(entry)))
        ambiguous = self.detail()['paperStructure']['pages'][0]['questions'][0]
        self.assertEqual(ambiguous['prompt'], '3 + 2 =')
        self.assertEqual(ambiguous['options'], []); self.assertEqual(ambiguous['tables'], [])
        self.assertIn('question_info_owner_unverified', self.detail()['paperStructure']['coverage']['issues'])

    def test_nonzero_or_unknown_angle_never_positions_original_page(self):
        self.complete()
        for angle in (90, None, '0', True):
            self.rewrite_journal(mutate=lambda envelope, raw: raw['Response'].update(Angle=angle))
            projection = self.detail()['paperStructure']; page = projection['pages'][0]; node = page['questions'][0]
            self.assertFalse(page['geometryVerified']); self.assertIsNone(node['region'])
            self.assertIsNone(node['answers'][0]['region']); self.assertIsNone(self.context()['region'])
        # Even a zero query angle cannot overrule an unverified submit frame.
        self.rewrite_journal(mutate=lambda envelope, raw: raw['Response'].update(Angle=0))
        self.rewrite_journal(submit=True, mutate=lambda envelope, raw: raw['Response']['QuestionInfo'][0].update(OrgWidth=801))
        self.assertFalse(self.detail()['paperStructure']['pages'][0]['geometryVerified'])

    def test_out_of_page_diagram_is_preserved_unpositioned_and_full_page_fallback(self):
        raw = marks(); raw['Response']['MarkInfos'][0]['QuestionImagePositions'] = [{'Position': polygon(700, 400, 110, 100)}]
        detail = self.complete(result=raw)
        picture = detail['paperStructure']['pages'][0]['questions'][0]['illustrations'][0]
        self.assertIsNone(picture['region']); self.assertFalse(picture['geometryVerified'])
        self.assertIn('illustration_region_unverified', detail['paperStructure']['coverage']['issues'])
        self.assertIsNone(self.context()['region'])

    def test_sha_tamper_private_journal_and_original_photo_fall_back(self):
        self.complete(); call = self.call(); receipt = json.loads(call['receipt_json'])
        query_path = self.store._path(receipt['completedJobs']['job-offline']['storageKey'])
        original = query_path.read_bytes(); query_path.write_bytes(original+b' ')
        projection = self.detail()['paperStructure']
        self.assertEqual(projection['coverage']['status'], 'unavailable')
        self.assertEqual(projection['pages'][0]['questions'], [])
        query_path.write_bytes(original)
        page = self.db.execute('SELECT * FROM homework_pages WHERE submission_id=?', (self.identity,)).fetchone()
        self.store._path(page['storage_key']).write_bytes(b'not the uploaded photo')
        self.assertIn('source_asset_changed', self.detail()['paperStructure']['coverage']['issues'])
        self.tencent.submit_question.assert_not_called(); self.tencent.describe_question.assert_not_called()

    def test_exact_child_submission_revision_and_job_identity_bound(self):
        self.complete()
        self.rewrite_journal(mutate=lambda envelope, raw: envelope.update(childId='child-b'))
        self.assertEqual(self.detail()['paperStructure']['coverage']['status'], 'unavailable')
        self.rewrite_journal(mutate=lambda envelope, raw: envelope.update(childId='child-a', analysisRevision=99))
        self.assertEqual(self.detail()['paperStructure']['coverage']['status'], 'unavailable')
        self.rewrite_journal(mutate=lambda envelope, raw: envelope.update(analysisRevision=2))
        self.rewrite_journal(submit=True, mutate=lambda envelope, raw: raw['Response'].update(JobId='foreign-job'))
        self.assertIn('receipt_job_identity_changed', self.detail()['paperStructure']['coverage']['issues'])

    def test_existing_v2_rows_project_without_rescore_and_mismatched_link_is_unassigned(self):
        self.complete()
        item = self.db.execute('SELECT * FROM homework_items WHERE submission_id=?', (self.identity,)).fetchone()
        old = json.loads(item['result_json']); old.pop('sourceHierarchy', None); old.pop('gradingReference', None)
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?', (canonical(old), item['id'])); self.db.raw.commit()
        projection = self.detail()['paperStructure']
        self.assertEqual(projection['coverage']['linkedAnswers'], 1)
        self.assertEqual(json.loads(self.db.execute('SELECT result_json FROM homework_items WHERE id=?', (item['id'],)).fetchone()['result_json']), old)
        old['sourceAnswerOrdinal'] = 2
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?', (canonical(old), item['id'])); self.db.raw.commit()
        projection = self.detail()['paperStructure']
        self.assertEqual(projection['coverage']['linkedAnswers'], 0)
        self.assertEqual(projection['pages'][0]['unassignedItemIds'], [item['id']])
        self.assertEqual(self.context()['questionPath'], [])

    def test_no_answer_leaf_retains_unknown_item_null_index_and_zero_count(self):
        raw = marks(); raw['Response']['MarkInfos'][0]['AnswerInfos'] = []
        detail = self.complete(result=raw)
        target = detail['paperStructure']['pages'][0]['questions'][0]['answers'][0]
        self.assertIsNone(target['index']); self.assertEqual(target['count'], 0)
        self.assertEqual(target['itemId'], detail['originalPaperItems'][0]['id'])
        self.assertFalse(target['geometryVerified'])

    def test_same_child_live_cache_reuse_binds_original_receipts_and_new_item_ids(self):
        first = self.complete()
        second = self.queued('cache-repeat')
        self.service.process_next()
        self.identity = second['id']; detail = self.detail()
        self.assertEqual(detail['paperStructure']['coverage']['linkedAnswers'], 1)
        answer = detail['paperStructure']['pages'][0]['questions'][0]['answers'][0]
        self.assertEqual(answer['itemId'], detail['originalPaperItems'][0]['id'])
        self.assertNotEqual(answer['itemId'], first['originalPaperItems'][0]['id'])
        self.tencent.submit_question.assert_not_called(); self.tencent.describe_question.assert_not_called()
        # A deleted owner may not donate retained private receipts to a copy.
        self.db.execute('UPDATE homework_submissions SET deleted_at=? WHERE id=?', (1, first['id'])); self.db.raw.commit()
        self.assertEqual(self.detail()['paperStructure']['coverage']['status'], 'unavailable')

    def test_digest_changes_with_projection_version_and_saved_metadata(self):
        self.complete(); before = self.detail()['paperStructure']['sourceDigest']
        with patch('services.homework_paper_structure.PROJECTION_VERSION', 'mira.homework-paper-structure-projection.future'):
            self.assertNotEqual(before, self.detail()['paperStructure']['sourceDigest'])
        self.mutate_receipt(lambda value: value.update(submittedGeometry={'submittedWidth': 799}))
        self.assertNotEqual(before, self.detail()['paperStructure']['sourceDigest'])
        self.assertFalse(self.detail()['paperStructure']['pages'][0]['geometryVerified'])

    def test_missing_second_page_journal_preserves_first_page_tree(self):
        submission = self.two_pages('partial-two-page')
        for _ in range(3):
            self.service.process_next(); self.due()
        self.identity = submission['id']
        before = self.detail()['paperStructure']
        self.assertEqual(before['coverage']['linkedAnswers'], 2)
        calls = self.db.execute('SELECT * FROM homework_provider_calls WHERE submission_id=? ORDER BY page_id', (self.identity,)).fetchall()
        receipt = json.loads(calls[1]['receipt_json'])
        self.store.delete(receipt['completedJobs']['job-offline']['storageKey'])
        projection = self.detail()['paperStructure']
        self.assertEqual(projection['coverage']['status'], 'partial')
        self.assertEqual(projection['coverage']['linkedAnswers'], 1)
        self.assertEqual(sum(bool(page['questions']) for page in projection['pages']), 1)
        self.assertEqual(sum(len(page['unassignedItemIds']) for page in projection['pages']), 1)


if __name__ == '__main__':
    unittest.main()
