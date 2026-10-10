"""Offline Tencent job/evidence contracts; no credentials, DB or paid HTTP."""
import json
import io
from copy import deepcopy
from PIL import Image
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from integrations.ai.tencent_homework_provider import TencentSubmissionUnknown, TencentQueryError, TencentConfigurationError, TencentKnownError
from services.homework_service import canonical, digest, POLICY
from services.homework_tencent_normalizer import normalize_question_page, normalize_essay_page, grading_reference, question_source_hierarchy
from services.homework_tencent_grading import HomeworkTencentGrading, NORMALIZED_SCHEMA
from tests import test_homework_analysis as fixtures


def marks(*, correct=False, answer='4', right='5', angle=0, prompt='3 + 2 ='):
    return {'Response': {'RequestId': 'request-offline', 'JobStatus': 'DONE', 'Angle': angle,
        'MarkInfos': [{'MarkItemTitle': prompt, 'QuestionType': '计算题',
            'QuestionPositions': [80, 100, 720, 100, 720, 300, 80, 300],
            'AnswerInfos': [{'HandwriteInfo': answer, 'IsCorrect': correct, 'RightAnswer': right,
                'AnswerAnalysis': '先计算两个数相加。', 'KnowledgePoints': ['20以内加法'],
                'HandwriteInfoPositions': [400, 110, 500, 110, 500, 180, 400, 180]}]}]}}


def essay():
    return {'Response': {'RequestId': 'essay-offline', 'JobStatus': 'DONE', 'Angle': 0,
        'SentenceSuggests': [{'ID': 1, 'Type': '表达', 'SubType': '用词', 'Origin': '风很大很大',
            'Replace': '风呼呼地吹', 'Message': '试着写出风的声音。',
            'Positions': [{'Position': [80, 100, 720, 100, 720, 300, 80, 300]}]}]}}


def source(prompt='3 + 2 ='):
    return {'Response': {'JobId': 'job-offline', 'RequestId': 'submit-offline', 'QuestionInfo': [{
        'Angle': 0, 'Width': 800, 'Height': 1000, 'OrgWidth': 800, 'OrgHeight': 1000,
        'ResultList': [{'Question': [{'Text': prompt, 'PageIndex': 1}],
            'Coord': [{'LeftTop': {'X': 80, 'Y': 100}, 'RightTop': {'X': 720, 'Y': 100},
                'RightBottom': {'X': 720, 'Y': 300}, 'LeftBottom': {'X': 80, 'Y': 300}}],
            'CoordPageIndex': [1]}]}]}}


def grouped_marks(count=44):
    """Anonymous paper shape: one heading, many unaligned answer entries."""
    raw = marks(correct=True, answer='5')
    mark = raw['Response']['MarkInfos'][0]
    mark['MarkItemTitle'] = '一、口算'
    mark['AnswerInfos'] = [deepcopy(mark['AnswerInfos'][0]) for _ in range(count)]
    return raw


class NormalizerTest(unittest.TestCase):
    def normalize(self, raw, **kw):
        mark = raw['Response']['MarkInfos'][0]
        while mark.get('MarkInfos'):
            mark = mark['MarkInfos'][0]
        return normalize_question_page([raw], page_id='hwp_' + 'a' * 32, width=800, height=1000,
            grade='primary_1', subject=kw.get('subject', 'math'), policy=POLICY,
            submit_receipts=[source(mark.get('MarkItemTitle') or '3 + 2 =')])['items'][0]

    def test_actual_answer_reference_confidence_and_arithmetic(self):
        result = self.normalize(marks())
        self.assertEqual(result['studentAnswer'], '4')
        self.assertEqual(result['expectedAnswer'], '5')
        self.assertIsNone(result['confidence'])
        self.assertEqual(result['answerMode'],'picture_choice')
        self.assertEqual(result['status'], 'incorrect')
        self.assertFalse(result['recognitionConfirmed'])
        self.assertTrue(result['sourceValidation']['trusted'])
        self.assertEqual(result['region'], {'x': .1, 'y': .1, 'width': .8, 'height': .2})
        self.assertEqual(result['knowledgePoints'], ['20以内加法'])
        self.assertIn('mark', result['tencentRaw'])

    def test_strict_correctness_and_contradictions_are_pending(self):
        for value in (None, 'false', 0, 1):
            raw = marks(); raw['Response']['MarkInfos'][0]['AnswerInfos'][0]['IsCorrect'] = value
            with self.subTest(value=value):
                self.assertEqual(self.normalize(raw)['status'], 'pending')
        for raw in (marks(correct=True), marks(right='6')):
            result = self.normalize(raw)
            self.assertEqual(result['status'], 'pending')
            self.assertFalse(result['sourceValidation']['trusted'])
        raw = marks(); del raw['Response']['MarkInfos'][0]['AnswerInfos'][0]['HandwriteInfo']
        result = self.normalize(raw)
        self.assertEqual(result['studentAnswer'], '')
        self.assertEqual(result['answerState'], 'unclear')
        self.assertEqual(result['status'], 'pending')

    def test_angle_and_coordinates_never_guess_or_use_original_dimensions(self):
        for angle in (None, 90, '0', True):
            with self.subTest(angle=angle):
                result = self.normalize(marks(angle=angle))
                self.assertIsNone(result['region'])
                self.assertEqual(result['status'], 'pending')
        raw = marks(); raw['Response']['MarkInfos'][0]['QuestionPositions'][2] = 801
        self.assertIsNone(self.normalize(raw)['region'])
        raw = marks(); raw['Response']['MarkInfos'][0]['QuestionPositions'] = [80, 100, 720, 300]
        self.assertIsNone(self.normalize(raw)['region'])

    def test_language_and_word_problem_go_to_teacher_without_invented_picture(self):
        result = self.normalize(marks(prompt='猫的英文是什么？', answer='dog', right='cat'), subject='english')
        self.assertEqual(result['status'], 'incorrect')
        self.assertEqual(result['method'], 'tencent_question.v1')
        self.assertIsNone(result['picture'])
        self.assertIsNone(result['answerMode'])
        self.assertEqual(self.normalize(marks(prompt='植物需要什么？'), subject='science')['status'], 'pending')

    def test_nested_cut_question_keeps_hierarchy_and_missing_entries(self):
        raw = marks(); child = raw['Response']['MarkInfos'][0]
        raw['Response']['MarkInfos'] = [{'MarkItemTitle': '第一题', 'MarkInfos': [child]}]
        result = self.normalize(raw)
        self.assertEqual(result['prompt'], '3 + 2 =')
        self.assertEqual(result['ancestorContext'], ['第一题'])
        self.assertIsNone(result['sourceQuestionLabel'])
        child['AnswerInfos'] = []
        self.assertEqual(self.normalize(raw)['status'], 'pending')

    def test_essay_is_saved_advice_and_not_invented_transcript_or_score(self):
        result = normalize_essay_page([essay()], page_id='hwp_' + 'a' * 32, width=800, height=1000,
            grade='primary_1', subject='chinese', policy=POLICY)['items'][0]
        self.assertEqual(result['method'], 'tencent_essay.v1')
        self.assertEqual(result['studentAnswer'], '')
        self.assertIsNone(result['expectedAnswer'])
        self.assertEqual(result['status'], 'unsupported')
        self.assertFalse(result['countsForAbility'])
        self.assertEqual(result['essaySuggestions'][0]['origin'], '风很大很大')
        self.assertNotIn('score', result)

    def test_real_tencent_synthetic_math_shape_uses_leaf_not_heading(self):
        # Fields transcribed from the saved synthetic smoke, without its signed
        # OriginalImageUrl, request IDs, images or provider job identifiers.
        raw = {'Response': {'Angle': 0, 'MarkInfos': [{'MarkItemTitle': 'Synthetic arithmetic worksheet',
            'AnswerInfos': [], 'MarkInfos': [
                {'MarkItemTitle': '1 + 2 =', 'QuestionType': '算式题', 'QuestionPositions': [102,617,519,617,519,718,102,718],
                 'AnswerInfos': [{'HandwriteInfo': '4', 'IsCorrect': False, 'RightAnswer': '3', 'KnowledgePoints': ['10以内加法运算'],
                     'HandwriteInfoPositions': [456,624,517,624,517,715,456,715]}]},
                {'MarkItemTitle': '2 + 3 =', 'QuestionType': '算式题', 'QuestionPositions': [89,983,520,983,520,1089,89,1089],
                 'AnswerInfos': [{'HandwriteInfo': '5', 'IsCorrect': True, 'RightAnswer': '5', 'KnowledgePoints': ['10以内加法运算'],
                     'HandwriteInfoPositions': [458,994,518,994,518,1088,458,1088]}]}]}]}}
        submit = {'Response': {'QuestionInfo': [{'Angle': 0, 'Width':1400, 'Height':1800,
            'OrgWidth':1400, 'OrgHeight':1800, 'ResultList':[{'Question': [], 'Coord': []}]}]}}
        result = normalize_question_page([raw], submit_receipts=[submit], page_id='hwp_'+'a'*32,
            width=1400, height=1800, grade='primary_1', subject='math', policy=POLICY)['items']
        self.assertEqual([i['prompt'] for i in result], ['1 + 2 =', '2 + 3 ='])
        self.assertEqual([i['status'] for i in result], ['incorrect', 'correct'])
        self.assertTrue(all(i['sourceQuestionLabel'] is None for i in result))
        self.assertTrue(all(i['sourceValidation']['questionTextSource']=='mark_item_title' for i in result))
        self.assertTrue(all(i['confidence'] is None for i in result))

    def test_title_only_multiblank_and_ambiguous_source_are_pending(self):
        raw=marks(prompt='第1题')
        self.assertEqual(self.normalize(raw)['status'],'pending')
        self.assertIn('question_text_missing',self.normalize(raw)['sourceValidation']['issues'])
        raw=marks(); raw['Response']['MarkInfos'][0]['AnswerInfos']*=2
        self.assertIn('multiple_answer_alignment_unverified',self.normalize(raw)['sourceValidation']['issues'])
        submit=source(); submit['Response']['QuestionInfo'][0]['Width']=801
        result=normalize_question_page([marks()],submit_receipts=[submit],page_id='hwp_'+'a'*32,
            width=800,height=1000,grade='primary_1',subject='math',policy=POLICY)['items'][0]
        self.assertIsNone(result['region']);self.assertEqual(result['status'],'pending')

    def test_crop_encloses_both_question_and_saved_answer(self):
        raw=marks(); raw['Response']['MarkInfos'][0]['AnswerInfos'][0]['HandwriteInfoPositions']=[720,310,790,310,790,350,720,350]
        result=self.normalize(raw)
        self.assertEqual(result['region'],{'x':.1,'y':.1,'width':.8875,'height':.25})

    def test_nearly_rotated_essay_keeps_advice_without_false_crop_or_score(self):
        raw=essay();raw['Response']['Angle']=359.99
        result=normalize_essay_page([raw],page_id='hwp_'+'a'*32,width=800,height=1000,
            grade='primary_1',subject='chinese',policy=POLICY)['items'][0]
        self.assertNotIn('region',result['essaySuggestions'][0])
        self.assertEqual(result['essaySuggestions'][0]['origin'],'风很大很大')
        self.assertFalse(result['recognitionNeedsConfirmation'])

    def test_decimal_operand_is_not_question_number_and_explicit_number_keeps_body(self):
        decimal=self.normalize(marks(prompt='1.5 + 2 =',answer='3.5',right='3.5',correct=True))
        self.assertIsNone(decimal['sourceQuestionLabel']);self.assertEqual(decimal['status'],'correct')
        numbered=self.normalize(marks(prompt='1. 3 + 2 ='))
        self.assertEqual(numbered['sourceQuestionLabel'],'1.')
        self.assertEqual(numbered['prompt'],'3 + 2 =')
        self.assertEqual(numbered['status'],'incorrect')

    def test_tencent_44_grouped_answers_keep_provisional_assessment_not_fake_trust(self):
        raw = grouped_marks()
        submit = source(); submit['Response']['QuestionInfo'][0]['ResultList'] = []
        result = normalize_question_page([raw], submit_receipts=[submit], page_id='hwp_'+'a'*32,
            width=800, height=1000, grade='primary_1', subject='math', policy=POLICY)
        self.assertEqual(POLICY['maxItemsPerPage'], 40)
        self.assertEqual(len(result['items']), 44)
        for item in result['items']:
            self.assertEqual(item['status'], 'pending')
            self.assertEqual(item['sourceValidation']['issues'], ['question_text_missing', 'multiple_answer_alignment_unverified'])
            self.assertFalse(item['sourceValidation']['trusted'])
            self.assertTrue(item['providerAssessment']['provisional'])
            self.assertTrue(item['providerAssessment']['isCorrect'])
            self.assertFalse(item['providerAssessment']['countsForAbility'])
            self.assertEqual(item['providerAssessment']['answerRegion'], item['answerRegions'][0])
            self.assertNotIn('AnswerInfos', item['tencentRaw']['mark'])
        self.assertLess(len(canonical(result)), 150_000)

    def test_tencent_200_item_limit_is_independent_and_bounded(self):
        args = dict(submit_receipts=[source()], page_id='hwp_'+'a'*32, width=800, height=1000,
            grade='primary_1', subject='math', policy=POLICY)
        self.assertEqual(len(normalize_question_page([grouped_marks(200)], **args)['items']), 200)
        with self.assertRaises(fixtures.ApiError) as raised:
            normalize_question_page([grouped_marks(201)], **args)
        self.assertEqual(raised.exception.code, 'homework_recognition_over_limit')

    def test_multiblank_hierarchy_references_are_per_answer_without_fake_independent_score(self):
        child=marks(prompt='请填写两个空格：3+2=（ ），4+1=（ ）。')['Response']['MarkInfos'][0]
        child['AnswerInfos'].append(deepcopy(child['AnswerInfos'][0]))
        child['AnswerInfos'][1].update(HandwriteInfo='5',IsCorrect=True,AnswerAnalysis='第二个空格的解析。',
            HandwriteInfoPositions=[550,110,650,110,650,180,550,180])
        raw={'Response':{'Angle':0,'MarkInfos':[{'MarkItemTitle':'一、填空','MarkInfos':[child]}]}}
        value=normalize_question_page([raw],submit_receipts=[source()],page_id='hwp_'+'a'*32,
            width=800,height=1000,grade='primary_1',subject='math',policy=POLICY)['items']
        self.assertEqual([item['status'] for item in value],['pending','pending'])
        self.assertEqual([item['gradingReference']['status'] for item in value],['incorrect','correct'])
        for index,item in enumerate(value,1):
            hierarchy=item['sourceHierarchy']
            self.assertEqual(hierarchy['markPath'],[1,1])
            self.assertEqual(hierarchy['receiptIndex'],1)
            self.assertEqual(hierarchy['answerIndex'],index)
            self.assertEqual(hierarchy['answerCount'],2)
            self.assertEqual(hierarchy['sourcePath'],['一、填空',child['MarkItemTitle']])
            self.assertEqual(hierarchy['questionTextScope'],'shared_question')
            self.assertEqual(item['gradingReference']['referenceAnswer'],'5')
            self.assertEqual(item['gradingReference']['answerRegion'],item['answerRegions'][0])
            self.assertFalse(item['gradingReference']['countsForAbility'])
            self.assertNotIn('deterministicValidation',item)
        self.assertNotEqual(value[0]['gradingReference']['answerRegion'],value[1]['gradingReference']['answerRegion'])
        self.assertEqual(value[1]['gradingReference']['analysis'],'第二个空格的解析。')

    def test_saved_v2_projection_uses_original_provider_reference_and_known_hierarchy_only(self):
        item=self.normalize(marks())
        item.pop('sourceHierarchy');item.pop('gradingReference')
        item.update(expectedAnswer='replacement',explanation='a later local explanation',ancestorContext=['一、填空'],
            sourceTitle='请填写两个空格。',sourceAnswerOrdinal=2,sourceAnswerCount=2)
        reference=grading_reference(item)
        self.assertEqual(reference['referenceAnswer'],'5')
        self.assertEqual(reference['analysis'],'先计算两个数相加。')
        hierarchy=question_source_hierarchy(item)
        self.assertEqual(hierarchy['sourcePath'],['一、填空','请填写两个空格。'])
        self.assertEqual(hierarchy['answerIndex'],2)
        self.assertEqual(hierarchy['markPath'],[])
        self.assertIsNone(hierarchy['receiptIndex'])
        self.assertFalse(hierarchy['hierarchyVerified'])
        item['tencentRaw']['answer']['IsCorrect']=0
        self.assertEqual(grading_reference(item)['status'],'unknown')
        item['sourceValidation']['angleVerified']=False
        reference=grading_reference(item)
        self.assertFalse(reference['geometryVerified']);self.assertNotIn('answerRegion',reference)

    def test_multiple_calculations_never_apply_whole_stem_to_each_answer(self):
        raw=marks();raw['Response']['MarkInfos'][0]['AnswerInfos']*=2
        value=normalize_question_page([raw],submit_receipts=[source()],page_id='hwp_'+'a'*32,
            width=800,height=1000,grade='primary_1',subject='math',policy=POLICY)['items']
        self.assertTrue(all('deterministicValidation' not in item and item['answerMode'] is None for item in value))
        self.assertTrue(all(item['status']=='pending' for item in value))

    def test_blank_provider_verdict_is_preserved_without_claiming_a_completed_answer(self):
        for verdict in (True,False):
            item=self.normalize(marks(correct=verdict,answer=''))
            reference=grading_reference(item)
            self.assertEqual(reference['status'],'unknown')
            self.assertEqual(reference['answerState'],'blank')
            self.assertIs(reference['providerIsCorrect'],verdict)
            self.assertFalse(reference['countsForAbility'])


class TencentPipelineTest(unittest.TestCase):
    create = fixtures.HomeworkTest.create
    upload = fixtures.HomeworkTest.upload
    error = fixtures.HomeworkTest.error
    events = fixtures.HomeworkTest.events

    def setUp(self):
        fixtures.HomeworkTest.setUp(self)
        self.tick = [self.clock()]
        self.service.clock = lambda: self.tick[0]
        def submit(path, *, receipt_callback, **kwargs):
            raw = source()
            receipt_callback('SubmitQuestionMarkAgentJob', canonical(raw).encode(), {'httpStatus': 200})
            return {'jobId': 'job-offline', 'jobIds': ['job-offline'], 'rawReceipt': raw, 'submitted': True}
        def query(job_id, *, receipt_callback):
            raw = marks()
            receipt_callback('DescribeQuestionMarkAgentJob', canonical(raw).encode(), {'httpStatus': 200})
            return {'status': 'DONE', 'rawReceipt': raw}
        def submit_essay(path, *, receipt_callback, **kwargs):
            raw = {'Response': {'JobIds': ['job-offline'], 'RequestId': 'essay-submit-offline'}}
            receipt_callback('SubmitMarkEssayAgentJob', canonical(raw).encode(), {'httpStatus': 200})
            return {'jobIds': ['job-offline'], 'rawReceipt': raw, 'submitted': True}
        self.tencent = SimpleNamespace(is_tencent_grading=True, provider_name='tencent', model_name='tencent-questions',
            submit_question=Mock(side_effect=submit), describe_question=Mock(side_effect=query),
            submit_essay=Mock(side_effect=submit_essay), describe_essay=Mock(side_effect=query))
        self.service.provider = self.tencent
        self.service.grading_provider = self.tencent
        self.service.tutor.process_next = Mock(return_value={'ok': True, 'processed': False})

    def queued(self, key='q', *, subject='math', kind='questions'):
        s = self.service.create('parent-a', 'child-a', {'subject': subject, 'analysisKind': kind,
            'analysisConsent': True, 'idempotencyKey': key})['submission']
        s = self.upload(s)
        self.service.analyze('parent-a', s['id'], {'revision': s['revision']})
        return s

    def due(self):
        self.tick[0] += 60_000

    def two_pages(self, key='two-pages'):
        s = self.upload(self.create(key))
        # Distinct bytes, identical dimensions, no private source photos.
        image = Image.open(io.BytesIO(fixtures.picture())).convert('RGB')
        image.putpixel((799, 999), (30, 30, 30))
        second = io.BytesIO(); image.save(second, format='PNG')
        s = self.upload(s, key='page2', body=second.getvalue())
        self.service.analyze('parent-a', s['id'], {'revision': s['revision']})
        return s

    def test_two_page_submit_and_poll_receipt_keys_are_unique_under_real_constraint(self):
        s = self.two_pages()
        for _ in range(3):
            self.service.process_next(); self.due()
        self.assertEqual(self.tencent.submit_question.call_count, 2)
        self.assertEqual(self.tencent.describe_question.call_count, 2)
        self.assertEqual(self.service.get('parent-a', s['id'])['submission']['status'], 'ready')
        receipts = self.db.execute('SELECT * FROM homework_actions WHERE item_id=?', ('__tencent_receipt__',)).fetchall()
        self.assertEqual(len(receipts), 4)
        self.assertEqual(len({r['idempotency_key'] for r in receipts}), 4)

    def test_saved_two_page_old_limit_and_orphan_submit_recover_without_paid_replay(self):
        s = self.two_pages('old-multpage-recovery')
        submissions = []
        def submit(path, *, receipt_callback, **kw):
            index = len(submissions); submissions.append(index)
            raw = source(); raw['Response']['JobId'] = f'page-{index}'
            if index == 0:
                raw['Response']['QuestionInfo'][0]['ResultList'] = []
            receipt_callback('SubmitQuestionMarkAgentJob', canonical(raw).encode(), {})
            if index == 1:
                # Raw reached its immutable address, but the old UNIQUE-key
                # failure prevented the downstream JobId linkage.
                raise TencentSubmissionUnknown('ReceiptPersistenceFailed')
            return {'jobIds': [f'page-{index}'], 'rawReceipt': raw}
        def query(job_id, *, receipt_callback):
            raw = grouped_marks() if job_id == 'page-0' else marks(correct=True, answer='5')
            receipt_callback('DescribeQuestionMarkAgentJob', canonical(raw).encode(), {})
            return {'status': 'DONE', 'rawReceipt': raw}
        self.tencent.submit_question.side_effect = submit
        self.tencent.describe_question.side_effect = query
        # The request fingerprint still uses the original generic policy (40).
        # Simulate the old Tencent parser limit without changing that identity.
        with patch.dict('services.homework_tencent_grading.POLICY', {'maxItemsPerPage': 40}):
            self.service.process_next(); self.due()
            self.assertEqual(self.service.process_next()['error'], 'homework_recognition_over_limit')
        before = self.db.execute('SELECT * FROM homework_provider_calls ORDER BY created_at,id').fetchall()
        original_ids = {c['id']: c['request_sha256'] for c in before}
        for call in before:
            receipt = json.loads(call['receipt_json'])
            if receipt['jobIds']:
                receipt['completedJobs'] = {'page-0': grouped_marks()}
            else:
                receipt.pop('receivedResponse', None); receipt.pop('submitResponse', None)
                self.db.execute('DELETE FROM homework_actions WHERE id=?', ('hwtr_'+digest([call['id'], 'submit'])[:56],))
            self.db.execute('UPDATE homework_provider_calls SET receipt_json=? WHERE id=?', (canonical(receipt), call['id']))
        self.db.raw.commit()
        row = self.db.execute('SELECT * FROM homework_submissions WHERE id=?', (s['id'],)).fetchone()
        repair = HomeworkTencentGrading(self.service)
        with self.db.transaction() as conn:
            preview = repair.resume_saved_results(conn, row)
        self.assertTrue(preview['resumable']); self.assertFalse(preview['resumed'])
        self.assertEqual(preview['completedJobCount'], 1)
        self.assertEqual(self.db.execute('SELECT status FROM homework_jobs').fetchone()['status'], 'failed')
        with self.db.transaction() as conn:
            restored = repair.resume_saved_results(conn, row, execute=True)
        self.assertTrue(restored['resumed']); self.assertTrue(restored['queryOnly'])
        self.assertEqual(self.service.process_next()['status'], 'needs_confirmation')
        self.assertEqual(self.tencent.submit_question.call_count, 2)
        self.assertEqual(self.tencent.describe_question.call_count, 2)
        after = self.db.execute('SELECT * FROM homework_provider_calls').fetchall()
        self.assertEqual({c['id']: c['request_sha256'] for c in after}, original_ids)
        self.assertEqual(NORMALIZED_SCHEMA, 'mira.homework-tencent-normalized.v1')
        parent = self.service.get('parent-a', s['id'])['submission']
        self.assertEqual(len(parent['items']), 45)
        self.assertEqual(sum(i['status'] == 'pending' for i in parent['items']), 44)
        for call in after:
            receipt = json.loads(call['receipt_json'])
            self.assertLess(len(call['receipt_json']), 6000)
            self.assertTrue(all('storageKey' in v and 'Response' not in v for v in receipt['completedJobs'].values()))
        with self.db.transaction() as conn:
            self.assertTrue(repair.resume_saved_results(conn, row, execute=True)['alreadyResumed'])
        self.assertEqual(self.db.execute('SELECT status FROM homework_jobs').fetchone()['status'], 'succeeded')
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM homework_actions WHERE item_id=?', ('__tencent_local_repair__',)).fetchone()['n'], 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM homework_actions WHERE item_id=?', ('__tencent_receipt__',)).fetchone()['n'], 4)
        self.service.delete('parent-a', s['id'], {'revision': s['revision']})
        self.assertEqual(list(self.store.root.rglob('*.json')), [])

    def test_local_repair_requires_every_page_original_reservation_and_saved_submit(self):
        s = self.two_pages('missing-page-recovery'); self.service.process_next()
        row = self.db.execute('SELECT * FROM homework_submissions WHERE id=?', (s['id'],)).fetchone()
        with self.db.transaction() as conn:
            value = HomeworkTencentGrading(self.service).resume_saved_results(conn, row, execute=True)
        self.assertFalse(value['resumable']); self.assertFalse(value['resumed'])
        self.assertEqual(self.tencent.submit_question.call_count, 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM homework_actions WHERE item_id=?', ('__tencent_local_repair__',)).fetchone()['n'], 0)

    def test_local_repair_rejects_changed_revision_missing_journal_and_semantic_tampering(self):
        s = self.queued('guarded-local-repair'); self.service.process_next()
        row = self.db.execute('SELECT * FROM homework_submissions WHERE id=?', (s['id'],)).fetchone()
        call = self.db.execute('SELECT * FROM homework_provider_calls').fetchone()
        original = json.loads(call['receipt_json'])
        repair = HomeworkTencentGrading(self.service)
        for mutation in ('revision', 'grade', 'subject', 'request_hash', 'config'):
            receipt = deepcopy(original)
            if mutation == 'revision': receipt['analysisRevision'] += 1
            elif mutation == 'grade': receipt['semanticContext']['gradeCode'] = 'primary_2'
            elif mutation == 'subject': receipt['semanticContext']['subject'] = 'english'
            elif mutation == 'request_hash': receipt['semanticContext']['policySha256'] = 'b'*64
            else: receipt['semanticContext']['providerConfig'] = {}
            self.db.execute('UPDATE homework_provider_calls SET receipt_json=? WHERE id=?', (canonical(receipt), call['id'])); self.db.raw.commit()
            with self.db.transaction() as conn:
                self.assertFalse(repair.resume_saved_results(conn, row, execute=True)['resumable'])
        self.db.execute('UPDATE homework_provider_calls SET receipt_json=? WHERE id=?', (canonical(original), call['id'])); self.db.raw.commit()
        self.store.delete(original['requestJournalKey'])
        with self.db.transaction() as conn:
            self.assertFalse(repair.resume_saved_results(conn, row, execute=True)['resumable'])
        self.assertEqual(self.tencent.submit_question.call_count, 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM homework_actions WHERE item_id=?', ('__tencent_local_repair__',)).fetchone()['n'], 0)

    def test_local_repair_never_creates_paid_reservation_after_config_changes(self):
        s = self.queued('query-only-repair'); self.service.process_next()
        row = self.db.execute('SELECT * FROM homework_submissions WHERE id=?', (s['id'],)).fetchone()
        with self.db.transaction() as conn:
            self.assertTrue(HomeworkTencentGrading(self.service).resume_saved_results(conn, row, execute=True)['resumed'])
        with patch.dict('integrations.ai.tencent_homework_provider.QUESTION_CONFIG', {'TrueAnswer': False}):
            self.assertEqual(self.service.process_next()['error'], 'homework_provider_unknown')
        self.assertEqual(self.tencent.submit_question.call_count, 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM homework_provider_calls').fetchone()['n'], 1)

    def test_local_repair_checks_current_original_bytes_and_transformed_source_hash(self):
        s = self.queued('source-bound-repair'); self.service.process_next()
        row = self.db.execute('SELECT * FROM homework_submissions WHERE id=?', (s['id'],)).fetchone()
        page = self.db.execute('SELECT * FROM homework_pages').fetchone()
        repair = HomeworkTencentGrading(self.service)
        original = self.store.read(page['storage_key'])
        with self.db.transaction() as conn:
            self.assertTrue(repair.resume_saved_results(conn, row)['resumable'])
        self.store._path(page['storage_key']).write_bytes(original+b'changed')
        with self.db.transaction() as conn:
            self.assertEqual(repair.resume_saved_results(conn, row, execute=True)['reason'], 'source_asset_changed')
        self.store._path(page['storage_key']).write_bytes(original)
        # A page transform changed without a revision increment still cannot
        # recover a paid receipt for the previous source coordinates.
        self.db.execute('UPDATE homework_pages SET rotation=? WHERE id=?', (90, page['id'])); self.db.raw.commit()
        with self.db.transaction() as conn:
            self.assertFalse(repair.resume_saved_results(conn, row, execute=True)['resumable'])
        self.assertEqual(self.tencent.submit_question.call_count, 1)

    def test_orphan_done_query_recovers_locally_and_is_included_in_private_delete(self):
        s = self.queued('query-journal-recovery', subject='chinese', kind='essay')
        def submit(path, *, receipt_callback, **kw):
            raw = {'Response': {'JobIds': ['essay-1', 'essay-2']}}
            receipt_callback('SubmitMarkEssayAgentJob', canonical(raw).encode(), {})
            return {'jobIds': ['essay-1', 'essay-2'], 'rawReceipt': raw}
        seen = []
        def query(job_id, *, receipt_callback):
            seen.append(job_id); raw = essay()
            receipt_callback('DescribeMarkEssayAgentJob', canonical(raw).encode(), {})
            if job_id == 'essay-1':
                call = self.db.execute('SELECT * FROM homework_provider_calls').fetchone()
                receipt = json.loads(call['receipt_json']); reference = receipt.pop('receivedResponse')
                self.db.execute('DELETE FROM homework_actions WHERE id=?', ('hwtr_'+digest([call['id'], reference['attempt']])[:56],))
                self.db.execute('UPDATE homework_provider_calls SET receipt_json=? WHERE id=?', (canonical(receipt), call['id'])); self.db.raw.commit()
                raise TencentQueryError('ReceiptPersistenceFailed')
            return {'status': 'DONE', 'rawReceipt': raw}
        self.tencent.submit_essay.side_effect = submit; self.tencent.describe_essay.side_effect = query
        self.service.process_next(); self.due()
        self.assertEqual(self.service.process_next()['status'], 'queued'); self.due()
        self.assertEqual(self.service.process_next()['status'], 'ready')
        self.assertEqual(seen, ['essay-1', 'essay-2'])
        self.assertEqual(self.tencent.submit_essay.call_count, 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM homework_actions WHERE item_id=?', ('__tencent_receipt__',)).fetchone()['n'], 3)
        self.service.delete('parent-a', s['id'], {'revision': s['revision']})
        self.assertEqual(list(self.store.root.rglob('*.json')), [])

    def test_invalid_saved_query_payload_can_query_same_job_without_submit_replay(self):
        self.queued('malformed-query-receipt'); self.service.process_next(); self.due()
        original = self.tencent.describe_question.side_effect
        def malformed(job_id, *, receipt_callback):
            receipt_callback('DescribeQuestionMarkAgentJob', b'{"incomplete":', {})
            raise TencentQueryError('InvalidResponse')
        self.tencent.describe_question.side_effect = malformed
        self.assertEqual(self.service.process_next()['status'], 'queued'); self.due()
        self.tencent.describe_question.side_effect = original
        self.assertEqual(self.service.process_next()['status'], 'ready')
        self.assertEqual(self.tencent.submit_question.call_count, 1)
        self.assertEqual(self.tencent.describe_question.call_count, 2)

    def test_parser_upgrade_reparses_completed_cache_locally_and_keeps_old_call_identity(self):
        s = self.queued('cache-before-parser'); self.service.process_next(); self.due(); self.service.process_next()
        call = self.db.execute('SELECT * FROM homework_provider_calls').fetchone()
        result = json.loads(call['result_json']); result.pop('normalizerVersion'); result.pop('normalizationContextSha256')
        self.db.execute('UPDATE homework_provider_calls SET result_json=? WHERE id=?', (canonical(result), call['id'])); self.db.raw.commit()
        next_s = self.queued('cache-after-parser'); self.service.process_next()
        self.assertEqual(self.tencent.submit_question.call_count, 1)
        self.assertEqual(self.tencent.describe_question.call_count, 1)
        items = self.service.get('parent-a', next_s['id'])['submission']['items']
        self.assertEqual(items[0]['pageId'], next_s['pages'][0]['id'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM homework_provider_calls').fetchone()['n'], 1)

    def test_large_received_body_is_kept_private_and_sql_has_only_digests(self):
        self.queued('large-private-receipt'); self.service.process_next(); self.due()
        raw = marks(correct=True, answer='5')
        raw['Response']['UnconsumedProviderData'] = 'x' * (8 * 1024 * 1024 + 1)
        def query(job_id, *, receipt_callback):
            receipt_callback('DescribeQuestionMarkAgentJob', canonical(raw).encode(), {})
            return {'status': 'DONE', 'rawReceipt': raw}
        self.tencent.describe_question.side_effect = query
        self.assertEqual(self.service.process_next()['status'], 'ready')
        call = self.db.execute('SELECT * FROM homework_provider_calls').fetchone()
        receipt = json.loads(call['receipt_json'])
        self.assertLess(len(call['receipt_json']), 6000)
        self.assertLess(len(call['result_json']), 6000)
        completed = receipt['completedJobs']['job-offline']
        saved = json.loads(self.store.read(completed['storageKey']))
        self.assertGreater(len(saved['rawBase64']), 8 * 1024 * 1024)

    def test_submit_durable_job_and_due_poll_completes_unknown_help_evidence(self):
        s = self.queued()
        result = self.service.process_next()
        self.assertEqual(result['status'], 'queued')
        self.assertGreater(result['nextPollAt'], self.tick[0])
        self.assertEqual(self.tencent.submit_question.call_count, 1)
        self.assertEqual(self.tencent.describe_question.call_count, 0)
        call = self.db.execute('SELECT * FROM homework_provider_calls').fetchone()
        receipt = json.loads(call['receipt_json'])
        self.assertEqual(receipt['jobIds'], ['job-offline'])
        self.assertTrue(self.store.read(receipt['submitResponse']['storageKey']))
        self.assertFalse(self.service.process_next()['processed'])
        self.due(); result = self.service.process_next()
        self.assertTrue(result['ok']); self.assertEqual(result['status'], 'ready')
        self.assertEqual(self.tencent.submit_question.call_count, 1)
        self.assertEqual(self.tencent.describe_question.call_count, 1)
        item = self.service.get('parent-a', s['id'])['submission']['items'][0]
        self.assertIsNone(item['confidence'])
        student = self.service.student_detail('student-a', s['id'])['submission']
        self.assertEqual(student['items'][0]['reviewContext']['originalAnswer'], '4')
        self.assertNotIn('tencentRaw', student['items'][0])
        self.assertNotIn('deterministicValidation', student['items'][0])
        self.assertEqual(student['tutorItems'][0]['pageId'], s['pages'][0]['id'])
        self.assertEqual(len(self.events()), 1)
        self.assertIsNone(self.events()[0]['independent'])
        self.assertIsNone(self.events()[0]['confidence'])
        self.assertEqual(self.transport.call_count, 5)

    def test_wait_run_timeout_backoff_and_no_submit_replay(self):
        self.queued(); self.service.process_next()
        responses = ['WAIT', 'RUN', 'timeout']
        def query(job_id, *, receipt_callback):
            state = responses.pop(0)
            if state == 'timeout':
                raise TencentQueryError('Timeout')
            raw = {'Response': {'JobStatus': state}}
            receipt_callback('DescribeQuestionMarkAgentJob', canonical(raw).encode(), {})
            return {'status': state, 'rawReceipt': raw}
        self.tencent.describe_question.side_effect = query
        for _ in range(3):
            self.due(); result = self.service.process_next()
            self.assertEqual(result['status'], 'queued')
            self.assertGreater(result['nextPollAt'], self.tick[0])
            self.assertFalse(self.service.process_next()['processed'])
        self.assertEqual(self.tencent.submit_question.call_count, 1)
        self.assertEqual(self.tencent.describe_question.call_count, 3)

    def test_waiting_old_job_does_not_starve_another_submission(self):
        first = self.queued('first'); self.service.process_next()
        second = self.queued('second')
        # A distinct image is needed, since an identical in-flight paid request
        # must never be bypassed by making a second submission.
        page = second['pages'][0]
        self.service.update_pages('parent-a', second['id'], {'revision': second['revision'],
            'pages': [{'id': page['id'], 'rotation': 90}]})
        second = self.service.get('parent-a', second['id'])['submission']
        self.service.analyze('parent-a', second['id'], {'revision': second['revision']})
        result = self.service.process_next()
        self.assertEqual(result['submissionId'], second['id'])
        self.assertNotEqual(result['submissionId'], first['id'])
        self.assertEqual(self.tencent.submit_question.call_count, 2)

    def test_unknown_submit_no_job_id_never_replayed(self):
        s = self.queued()
        self.tencent.submit_question.side_effect = TencentSubmissionUnknown('Timeout')
        result = self.service.process_next()
        self.assertEqual(result['error'], 'homework_provider_unknown')
        self.due(); self.assertFalse(self.service.process_next()['processed'])
        self.service.analyze('parent-a', s['id'], {'revision': s['revision']})
        self.assertFalse(self.service.process_next()['processed'])
        self.assertEqual(self.tencent.submit_question.call_count, 1)

    def test_expired_lease_recovers_raw_submit_before_job_link_without_replay(self):
        self.queued()
        original = self.tencent.submit_question.side_effect
        def crash(path, *, receipt_callback, **kw):
            original(path, receipt_callback=receipt_callback)
            raise KeyboardInterrupt()
        self.tencent.submit_question.side_effect = crash
        with self.assertRaises(KeyboardInterrupt):
            self.service.process_next()
        self.tick[0] += POLICY['leaseMilliseconds'] + 1
        self.service.process_next()
        self.assertEqual(self.tencent.submit_question.call_count, 1)
        call = self.db.execute('SELECT * FROM homework_provider_calls').fetchone()
        self.assertEqual(json.loads(call['receipt_json'])['jobIds'], ['job-offline'])
        self.due(); self.assertEqual(self.service.process_next()['status'], 'ready')
        self.assertEqual(self.tencent.submit_question.call_count, 1)

    def test_delete_during_dispatch_cannot_publish_job_or_leave_private_receipt(self):
        s = self.queued()
        original = self.tencent.submit_question.side_effect
        def delete(path, *, receipt_callback, **kw):
            self.service.delete('parent-a', s['id'], {'revision': s['revision']})
            return original(path, receipt_callback=receipt_callback)
        self.tencent.submit_question.side_effect = delete
        self.assertEqual(self.service.process_next()['error'], 'homework_job_superseded')
        self.service.purge_files()
        self.assertEqual(list(self.store.root.rglob('*.json')), [])
        self.assertEqual(self.db.execute('SELECT status FROM homework_provider_calls').fetchone()['status'], 'deleted')

    def test_essay_metadata_survives_page_edit_and_is_not_an_assessment(self):
        s = self.queued(subject='chinese', kind='essay')
        s = self.service.update_pages('parent-a', s['id'], {'revision': s['revision'],
            'pages': [{'id': s['pages'][0]['id'], 'rotation': 0}]})['submission']
        self.assertEqual(s['analysisKind'], 'essay')
        self.service.analyze('parent-a', s['id'], {'revision': s['revision']})
        def query(job_id, *, receipt_callback):
            raw = essay(); receipt_callback('DescribeMarkEssayAgentJob', canonical(raw).encode(), {})
            return {'status': 'DONE', 'rawReceipt': raw}
        self.tencent.describe_essay.side_effect = query
        self.service.process_next(); self.due(); self.service.process_next()
        parent = self.service.get('parent-a', s['id'])['submission']
        self.assertEqual(parent['originalSummary']['total'], 0)
        self.assertEqual(parent['summary']['total'], 0)
        self.assertEqual(parent['essayReview']['status'], 'ready')
        self.assertFalse(parent['essayReview']['countsForAbility'])
        self.assertEqual(parent['essayReview']['suggestions'][0]['pageId'], s['pages'][0]['id'])
        student = self.service.student_detail('student-a', s['id'])['submission']
        self.assertEqual(student['tutorItems'][0]['assessmentMethod'], 'tencent_essay.v1')
        self.assertEqual(student['tutorItems'][0]['pageId'], s['pages'][0]['id'])
        self.assertEqual(self.events(), [])

    def test_create_kind_has_validation_and_idempotency(self):
        for kind, subject, code in (('essay', 'math', 'homework_essay_subject_unsupported'),
                ('guessed', 'chinese', 'homework_analysis_kind_invalid')):
            self.error(code, lambda: self.service.create('parent-a', 'child-a', {'subject': subject,
                'analysisKind': kind, 'analysisConsent': True, 'idempotencyKey': 'bad'}))
        payload = {'subject': 'chinese', 'analysisConsent': True, 'analysisKind': 'essay', 'idempotencyKey': 'same'}
        first = self.service.create('parent-a', 'child-a', payload)
        self.assertEqual(self.service.create('parent-a', 'child-a', payload), first)
        self.error('homework_idempotency_conflict', lambda: self.service.create('parent-a', 'child-a', {**payload, 'analysisKind': 'questions'}))

    def test_successful_delete_removes_all_private_poll_receipts(self):
        s = self.queued(); self.service.process_next(); self.due(); self.service.process_next()
        self.assertGreater(len(list(self.store.root.rglob('*.json'))), 1)
        self.service.delete('parent-a', s['id'], {'revision': s['revision']})
        self.assertEqual(list(self.store.root.rglob('*.json')), [])

    def test_multijob_essay_waits_for_every_job_and_does_not_requery_done(self):
        self.queued(subject='chinese',kind='essay')
        def submit(path,*,receipt_callback,**kw):
            raw={'Response':{'JobIds':['essay-1','essay-2']}}
            receipt_callback('SubmitMarkEssayAgentJob',canonical(raw).encode(),{})
            return {'jobIds':['essay-1','essay-2'],'rawReceipt':raw}
        self.tencent.submit_essay.side_effect=submit
        seen=[]
        def query(job_id,*,receipt_callback):
            seen.append(job_id)
            status='RUN' if job_id=='essay-2' and seen.count(job_id)==1 else 'DONE'
            raw=essay() if status=='DONE' else {'Response':{'JobStatus':status}}
            receipt_callback('DescribeMarkEssayAgentJob',canonical(raw).encode(),{})
            return {'status':status,'rawReceipt':raw}
        self.tencent.describe_essay.side_effect=query
        self.service.process_next();self.due()
        self.assertEqual(self.service.process_next()['status'],'queued')
        self.due();self.assertEqual(self.service.process_next()['status'],'ready')
        self.assertEqual(seen,['essay-1','essay-2','essay-2'])
        self.assertEqual(self.tencent.submit_essay.call_count,1)

    def test_multijob_failure_waits_for_other_accepted_jobs_to_terminate(self):
        self.queued(subject='chinese',kind='essay')
        def submit(path,*,receipt_callback,**kw):
            raw={'Response':{'JobIds':['fail-1','essay-2']}}
            receipt_callback('SubmitMarkEssayAgentJob',canonical(raw).encode(),{})
            return {'jobIds':['fail-1','essay-2'],'rawReceipt':raw}
        self.tencent.submit_essay.side_effect=submit
        seen=[]
        def query(job_id,*,receipt_callback):
            seen.append(job_id)
            status='FAIL' if job_id=='fail-1' else 'RUN' if seen.count(job_id)==1 else 'DONE'
            raw=essay() if status=='DONE' else {'Response':{'JobStatus':status}}
            receipt_callback('DescribeMarkEssayAgentJob',canonical(raw).encode(),{})
            return {'status':status,'rawReceipt':raw}
        self.tencent.describe_essay.side_effect=query
        self.service.process_next();self.due()
        self.assertEqual(self.service.process_next()['status'],'queued')
        self.due();self.assertEqual(self.service.process_next()['error'],'homework_tencent_failed')
        self.assertEqual(seen,['fail-1','essay-2','essay-2'])
        self.assertEqual(self.tencent.submit_essay.call_count,1)

    def test_revision_change_during_submit_never_attaches_stale_job_id(self):
        s=self.queued();original=self.tencent.submit_question.side_effect
        def change(path,*,receipt_callback,**kw):
            self.service.update_pages('parent-a',s['id'],{'revision':s['revision'],
                'pages':[{'id':s['pages'][0]['id'],'rotation':90}]})
            return original(path,receipt_callback=receipt_callback,**kw)
        self.tencent.submit_question.side_effect=change
        self.assertEqual(self.service.process_next()['error'],'homework_job_superseded')
        call=self.db.execute('SELECT receipt_json FROM homework_provider_calls').fetchone()
        self.assertEqual(json.loads(call['receipt_json'])['jobIds'],[])
        receipt=json.loads(call['receipt_json'])
        # Keep the private raw submit under the old reservation for audit, not
        # as a result of the new revision; deletion later purges it.
        self.assertTrue(self.store.read(receipt['requestJournalKey']))
        revised=self.service.get('parent-a',s['id'])['submission']
        self.service.delete('parent-a',s['id'],{'revision':revised['revision']})
        self.assertEqual(list(self.store.root.rglob('*.json')),[])

    def test_legacy_create_replay_preserves_questions_default_without_title_inference(self):
        s=self.service.create('parent-a','child-a',{'subject':'math','title':'英语作文','analysisConsent':True,'idempotencyKey':'legacy'})['submission']
        legacy=digest({'subject':'math','title':'英语作文','analysisConsent':True})
        self.db.execute('DELETE FROM homework_actions WHERE submission_id=? AND item_id=?',(s['id'],'__analysis_kind__'))
        self.db.execute('UPDATE homework_submissions SET request_sha256=? WHERE id=?',(legacy,s['id']));self.db.raw.commit()
        replay=self.service.create('parent-a','child-a',{'subject':'math','title':'英语作文','analysisConsent':True,'idempotencyKey':'legacy'})['submission']
        self.assertEqual(replay['id'],s['id']);self.assertEqual(replay['analysisKind'],'questions')

    def test_semantic_cache_includes_subject_grade_and_policy(self):
        first=self.queued('first');self.service.process_next();self.due();self.service.process_next()
        second=self.queued('same');self.service.process_next()
        self.assertEqual(self.tencent.submit_question.call_count,1)
        self.assertEqual(self.service.get('parent-a',second['id'])['submission']['items'][0]['pageId'],second['pages'][0]['id'])
        self.queued('other-subject',subject='english');self.service.process_next()
        self.assertEqual(self.tencent.submit_question.call_count,2)
        self.due();self.service.process_next()
        self.db.execute('UPDATE children SET grade_code=? WHERE id=?',('primary_2','child-a'));self.db.raw.commit()
        third=self.queued('other-grade');self.service.process_next()
        self.assertEqual(self.tencent.submit_question.call_count,3)
        self.assertEqual(self.service.get('parent-a',third['id'])['submission']['gradeCode'],'primary_2')

    def test_unknown_submit_cannot_be_bypassed_by_new_subject_or_grade(self):
        self.queued('unknown');self.tencent.submit_question.side_effect=TencentSubmissionUnknown('Timeout')
        self.service.process_next()
        self.queued('new-subject',subject='english');self.service.process_next()
        self.db.execute('UPDATE children SET grade_code=? WHERE id=?',('primary_2','child-a'));self.db.raw.commit()
        self.queued('new-grade');self.service.process_next()
        self.assertEqual(self.tencent.submit_question.call_count,1)

    def test_input_resize_mismatch_cannot_create_trusted_coordinates(self):
        self.queued()
        original=self.tencent.submit_question.side_effect
        def submit(path,*,receipt_callback,**kw):
            result=original(path,receipt_callback=receipt_callback,**kw)
            return {**result,'submittedWidth':400,'submittedHeight':500}
        self.tencent.submit_question.side_effect=submit
        self.service.process_next();self.due();self.service.process_next()
        result=json.loads(self.db.execute('SELECT result_json FROM homework_items').fetchone()['result_json'])
        self.assertIsNone(result['region']);self.assertEqual(result['status'],'pending')

    def test_pre_dispatch_configuration_failure_can_resume_without_new_paid_reservation(self):
        s=self.queued();original=self.tencent.submit_question.side_effect
        self.tencent.submit_question.side_effect=TencentConfigurationError('NotConfigured')
        self.assertEqual(self.service.process_next()['error'],'homework_provider_unconfigured')
        self.tencent.submit_question.side_effect=original
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        self.assertEqual(self.service.process_next()['status'],'queued')
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM homework_provider_calls').fetchone()['n'],1)

    def test_permanent_query_failure_stops_auto_poll_and_explicit_retry_queries_only(self):
        s=self.queued();self.service.process_next();self.due()
        original=self.tencent.describe_question.side_effect
        self.tencent.describe_question.side_effect=TencentKnownError('AuthFailure.SignatureFailure')
        result=self.service.process_next()
        self.assertEqual(result['error'],'homework_tencent_query_failed')
        parent=self.service.get('parent-a',s['id'])['submission'];self.assertTrue(parent['retryAllowed'])
        self.due();self.assertFalse(self.service.process_next()['processed'])
        self.assertEqual(self.tencent.describe_question.call_count,1)
        receipt=json.loads(self.db.execute('SELECT receipt_json FROM homework_provider_calls').fetchone()['receipt_json'])
        self.assertEqual(receipt['jobIds'],['job-offline'])
        self.assertEqual(receipt['queryErrorCode'],'AuthFailure.SignatureFailure')
        self.tencent.describe_question.side_effect=original
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        self.assertEqual(self.service.process_next()['status'],'ready')
        self.assertEqual(self.tencent.submit_question.call_count,1)
        self.assertEqual(self.tencent.describe_question.call_count,2)

    def test_resource_not_found_and_invalid_parameter_stop_auto_query(self):
        s=self.queued();self.service.process_next();self.due()
        for code in ('ResourceNotFound.JobNotFound','InvalidParameter.JobId'):
            with self.subTest(code=code):
                self.tencent.describe_question.side_effect=TencentKnownError(code)
                self.assertEqual(self.service.process_next()['error'],'homework_tencent_query_failed')
                self.due();self.assertFalse(self.service.process_next()['processed'])
                self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        self.assertEqual(self.tencent.submit_question.call_count,1)

    def test_poll_limits_stop_waiting_and_resume_only_saved_job(self):
        self.service.policy={**self.service.policy,'tencentPolling':{'maxQueriesPerPage':1}}
        s=self.queued();self.service.process_next();self.due()
        original=self.tencent.describe_question.side_effect
        def wait(job_id,*,receipt_callback):
            raw={'Response':{'JobStatus':'WAIT'}};receipt_callback('DescribeQuestionMarkAgentJob',canonical(raw).encode(),{})
            return {'status':'WAIT','rawReceipt':raw}
        self.tencent.describe_question.side_effect=wait
        self.assertEqual(self.service.process_next()['status'],'queued');self.due()
        self.assertEqual(self.service.process_next()['error'],'homework_tencent_query_limit')
        self.assertEqual(self.tencent.describe_question.call_count,1)
        self.tencent.describe_question.side_effect=original
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        self.assertEqual(self.service.process_next()['status'],'ready')
        self.assertEqual(self.tencent.submit_question.call_count,1)

    def test_new_upload_cannot_resubmit_a_paused_job_for_the_same_photo(self):
        self.queued();self.service.process_next();self.due()
        self.tencent.describe_question.side_effect=TencentKnownError('AuthFailure.SignatureFailure')
        self.assertEqual(self.service.process_next()['error'],'homework_tencent_query_failed')
        self.queued('same-photo-new-upload')
        self.assertEqual(self.service.process_next()['error'],'homework_provider_unknown')
        self.assertEqual(self.tencent.submit_question.call_count,1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) AS n FROM homework_provider_calls').fetchone()['n'],1)

    def test_poll_deadline_pauses_before_query_and_unknown_cannot_fake_query_retry(self):
        self.service.policy={**self.service.policy,'tencentPolling':{'maxPollingMilliseconds':1000}}
        s=self.queued();self.service.process_next();self.due()
        self.assertEqual(self.service.process_next()['error'],'homework_tencent_query_limit')
        self.assertEqual(self.tencent.describe_question.call_count,0)
        self.db.execute('UPDATE homework_provider_calls SET receipt_json=?',('{}',));self.db.raw.commit()
        parent=self.service.get('parent-a',s['id'])['submission'];self.assertFalse(parent['retryAllowed'])
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']})
        self.assertFalse(self.service.process_next()['processed'])
        self.assertEqual(self.tencent.submit_question.call_count,1)

    def test_trusted_arithmetic_is_ready_for_weekend_picture_review(self):
        s=self.queued();self.service.process_next();self.due();self.service.process_next()
        child=self.db.execute('SELECT * FROM children WHERE id=?',('child-a',)).fetchone()
        with self.db.transaction() as conn:
            pool,gaps=self.service.review_question_pool(conn,child)
        self.assertEqual(len(pool),1);self.assertEqual(gaps,[])
        self.assertEqual(pool[0]['visual']['kind'],'quantity_arithmetic')
        self.assertTrue(pool[0]['options'])
        fresh=self.service.student_detail('student-a',s['id'])['submission']['items'][0]
        self.assertNotIn('expectedAnswer',fresh);self.assertNotIn('referenceSteps',fresh)
        self.assertNotIn('deterministicValidation',fresh)

    def test_existing_pending_items_show_complete_provider_paper_without_score_or_paid_replay(self):
        s=self.queued('paper-provider-report');self.service.process_next();self.due()
        raw=grouped_marks(3)
        answers=raw['Response']['MarkInfos'][0]['AnswerInfos']
        answers[1].update(IsCorrect=False,HandwriteInfo='4')
        answers[2]['IsCorrect']='false'
        def query(job_id,*,receipt_callback):
            receipt_callback('DescribeQuestionMarkAgentJob',canonical(raw).encode(),{})
            return {'status':'DONE','rawReceipt':raw}
        self.tencent.describe_question.side_effect=query
        self.assertEqual(self.service.process_next()['status'],'needs_confirmation')
        # Existing v2 rows already preserve the actual AnswerInfo and titles.
        # Reading the new UI contract must neither rewrite them nor call AI.
        for item in self.db.execute('SELECT id,result_json FROM homework_items').fetchall():
            value=json.loads(item['result_json']);value.pop('sourceHierarchy');value.pop('gradingReference')
            self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(canonical(value),item['id']))
        self.db.raw.commit()
        before=[tuple(item) for item in self.db.execute('SELECT id,result_json,revision FROM homework_items ORDER BY id').fetchall()]
        parent=self.service.get('parent-a',s['id'])['submission']
        student=self.service.student_detail('student-a',s['id'])['submission']
        self.assertEqual(student['originalPaperSummary'],{'correct':0,'incorrect':0,'unknown':3,'blank':0,'total':3,'countsForAbility':False})
        self.assertEqual(parent['originalPaperSummary'],student['originalPaperSummary'])
        self.assertEqual(student['originalSummary']['pending'],3)
        self.assertEqual(student['items'],[])
        self.assertEqual(len(student['originalPaperItems']),3)
        for index,paper_item in enumerate(student['originalPaperItems'],1):
            context=paper_item['reviewContext']
            self.assertEqual(context['answerIndex'],index);self.assertEqual(context['answerCount'],3)
            self.assertEqual(context['sourcePath'],['一、口算'])
            self.assertNotIn('referenceAnswer',context['grading'])
            self.assertNotIn('analysis',context['grading'])
            self.assertEqual(context['grading']['status'],'unknown')
            self.assertTrue(context['grading']['geometryVerified'])
            self.assertEqual(context['grading']['studentQuality']['status'],'needs_review')
            self.assertNotIn('tencentRaw',paper_item)
            self.assertIn('gradingReference',parent['items'][index-1])
            self.assertFalse(parent['items'][index-1]['sourceHierarchy']['hierarchyVerified'])
        self.assertEqual(before,[tuple(item) for item in self.db.execute('SELECT id,result_json,revision FROM homework_items ORDER BY id').fetchall()])
        self.assertEqual(self.events(),[])
        self.assertEqual(self.tencent.submit_question.call_count,1)
        self.assertEqual(self.tencent.describe_question.call_count,1)


if __name__ == '__main__':
    unittest.main()
