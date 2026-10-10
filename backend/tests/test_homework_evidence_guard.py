"""Owned source checks on real isolated SQLite rows; no provider or live DB."""
from copy import deepcopy
import json
from unittest import TestCase

from services.homework_answer_quality import reference_for_correction, attach_reference_answer_layout
from services.homework_correction import evidence_question
from services.homework_evidence_guard import current_homework_events, private_review_reference_current
from services.learning_evidence_service import canonical, record_answer, weaknesses
from services.homework_service import POLICY
from services.homework_math import check_item
from services.homework_tencent_normalizer import normalize_question_page
from tests.test_homework_tencent_grading import marks, source
from tests.test_textbook_learning import IsolatedDatabase


class HomeworkEvidenceGuardTest(TestCase):
    def setUp(self):
        self.db = IsolatedDatabase(('085_learning_reviews.sql','086_homework_analysis.sql'))
        self.addCleanup(self.db.raw.close)
        self.submission_id = 'hw_'+'a'*32
        self.page_id = 'hwp_'+'b'*32
        self.item_id = 'hwi_'+'c'*56
        for suffix in ('a','b'):
            self.db.execute('INSERT INTO children VALUES (?,?,?,?)',
                ('child-'+suffix,'family-'+suffix,'primary_1',1))
        self._insert('homework_submissions',{'id':self.submission_id,'family_id':'family-a','child_id':'child-a',
            'grade_code':'primary_1','subject':'math','title':'匿名原图练习','source':'parent_app',
            'idempotency_key':'isolated-upload','request_sha256':'0'*64,'revision':1,'status':'ready',
            'consent_at':1,'created_at':1,'updated_at':1})
        self._insert('homework_pages',{'id':self.page_id,'submission_id':self.submission_id,
            'upload_key':'isolated-photo','content_sha256':'1'*64,'storage_key':'private-test.png',
            'mime_type':'image/png','width':800,'height':1000,'page_order':0,'rotation':0,
            'crop_json':None,'status':'ready','created_at':1})
        prompt = '看图：一共有几个苹果？'
        self.result = normalize_question_page([marks(prompt=prompt,answer='4',right='5')],
            page_id=self.page_id,width=800,height=1000,grade='primary_1',subject='math',policy=POLICY,
            submit_receipts=[source(prompt)])['items'][0]
        self._insert('homework_items',{'id':self.item_id,'submission_id':self.submission_id,
            'page_id':self.page_id,'revision':1,'analysis_revision':1,'item_order':0,
            'result_json':canonical(self.result),'media_json':'{}','correction_json':'{}','updated_at':1})
        item = self.db.execute('SELECT * FROM homework_items WHERE id=?',(self.item_id,)).fetchone()
        self.result = attach_reference_answer_layout(self.db,{'id':self.submission_id},item,self.result)
        reference = reference_for_correction(self.result)
        self.assertIsNotNone(reference)
        self.original_question = evidence_question({'id':self.submission_id,'subject':'math','grade_code':'primary_1'},
            item,self.result,reference)
        self.original = record_answer(self.db,family_id='family-a',child_id='child-a',source_kind='homework',
            source_id=self.submission_id,event_key=self.item_id+':1',question=self.original_question,
            answer='4',correct=False,occurred_at=1,diagnosis={'referenceDigest':reference['digest']})
        self.question = {**self.original_question,'private':True,'renderer':'homework_original',
            'sourceSubmissionId':self.submission_id,'sourceItemId':self.item_id,'sourceRevision':1,
            'referenceDigest':reference['digest'],'sourceEventId':self.original['id']}
        self.db.raw.commit()

    def _insert(self,table,value):
        self.db.execute('INSERT INTO '+table+'('+','.join(value)+') VALUES ('+','.join('?' for _ in value)+')',tuple(value.values()))

    def review(self,*,question=None,answer='4',correct=False,family='a',key='one'):
        value = record_answer(self.db,family_id='family-'+family,child_id='child-'+family,
            source_kind='review',source_id='review-'+key,event_key='frozen-question',
            question=question or self.question,answer=answer,correct=correct,occurred_at=20,
            hint_used=False,adult_help=False,independent=False)
        self.db.raw.commit()
        return value

    def rows(self):
        return self.db.execute("SELECT * FROM learning_answer_events WHERE source_kind='review' AND revoked_at IS NULL").fetchall()

    def current(self,question=None,family='a'):
        return private_review_reference_current(self.db,family_id='family-'+family,child_id='child-'+family,
            question=self.question if question is None else question)

    def picture_question(self,result):
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(canonical(result),self.item_id))
        question={**self.question,'renderer':'quantity_arithmetic','prompt':result['prompt'],
            'visual':result['picture'],'options':[{'value':choice['id'],'label':str(choice['count']),
                'picture':{'count':choice['count']}} for choice in result['picture']['choices']],
            'correctAnswer':'n'+result['expectedAnswer']}
        question.pop('referenceDigest')
        return question

    def test_valid_review_only_weaknesses_remain_same_question_without_independent_credit(self):
        self.review()
        before = self.rows()
        self.assertTrue(self.current())
        self.assertEqual(current_homework_events(self.db,before),before)
        # The original paper predates this range: a review-only query must
        # still execute the guard, rather than depend on a homework sibling.
        view = weaknesses(self.db,family_id='family-a',child_id='child-a',since=10)
        self.assertEqual((view[0]['wrongCount'],view[0]['independentCount']),(1,0))
        self.assertEqual(self.rows(),before)

    def test_changed_reference_digest_filters_review_only_weakness_without_rewriting_receipt(self):
        self.review();before=self.rows()
        changed=deepcopy(self.result)
        changed['tencentRaw']['answer']['AnswerAnalysis']='按当前小题新的解析逐个数。'
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(canonical(changed),self.item_id))
        self.assertIsNotNone(reference_for_correction(changed))
        self.assertFalse(self.current())
        self.assertEqual(current_homework_events(self.db,before),[])
        self.assertEqual(weaknesses(self.db,family_id='family-a',child_id='child-a',since=10),[])
        self.assertEqual(self.rows(),before)

    def test_deleted_owned_photo_filters_derived_review(self):
        self.review();self.db.execute('UPDATE homework_submissions SET deleted_at=30 WHERE id=?',(self.submission_id,))
        self.assertFalse(self.current());self.assertEqual(current_homework_events(self.db,self.rows()),[])

    def test_revoked_original_event_filters_derived_review_even_while_photo_exists(self):
        self.review();self.db.execute('UPDATE learning_answer_events SET revoked_at=30 WHERE id=?',(self.original['id'],))
        self.assertFalse(self.current());self.assertEqual(current_homework_events(self.db,self.rows()),[])

    def test_current_item_revision_and_reference_answer_must_match_frozen_question(self):
        for patch in ({'sourceRevision':2},{'referenceDigest':'0'*64},{'referenceDigest':None},{'correctAnswer':'6'}):
            with self.subTest(patch=patch):
                question={**self.question,**patch}
                self.assertFalse(self.current(question))
                record=self.review(question=question,key=str(len(self.rows())))
                self.assertEqual(current_homework_events(self.db,[record]),[])

    def test_cross_family_reference_cannot_read_another_childs_result_or_weakness(self):
        record=self.review(family='b')
        statements=[];self.db.raw.set_trace_callback(statements.append)
        try:
            self.assertFalse(self.current(family='b'))
            self.assertEqual(current_homework_events(self.db,[record]),[])
            self.assertEqual(weaknesses(self.db,family_id='family-b',child_id='child-b'),[])
        finally:
            self.db.raw.set_trace_callback(None)
        source_reads=[sql for sql in statements if 'FROM homework_items i' in sql]
        self.assertTrue(source_reads)
        self.assertTrue(all("s.family_id='family-b'" in sql and "s.child_id='child-b'" in sql for sql in source_reads))
        self.assertFalse(any('SELECT * FROM homework_items WHERE submission_id' in sql for sql in statements))

    def test_old_wrong_and_correct_flags_must_agree_with_the_actual_saved_answer(self):
        wrong_flag=self.review(answer='五个',correct=False,key='wrong-flag')
        correct_flag=self.review(answer='4',correct=True,key='correct-flag')
        valid=self.review(answer='五个',correct=True,key='valid')
        self.assertEqual(current_homework_events(self.db,[wrong_flag,correct_flag,valid]),[valid])
        original_wrong={**self.original,'answer_json':json.dumps('五个'),'correct':0}
        self.assertEqual(current_homework_events(self.db,[original_wrong]),[])

    def test_old_scalar_picture_answers_compare_without_certifying_independence(self):
        record=self.review(answer=5,correct=True)
        self.assertEqual(current_homework_events(self.db,[record]),[record])

    def test_real_tencent_exact_quantity_review_resolves_the_frozen_picture_option(self):
        result=normalize_question_page([marks()],page_id=self.page_id,width=800,height=1000,
            grade='primary_1',subject='math',policy=POLICY,submit_receipts=[source()])['items'][0]
        self.assertEqual(reference_for_correction(result)['authority'],'exact')
        question=self.picture_question(result)
        correct=self.review(question=question,answer='n5',correct=True,key='exact-picture-correct')
        wrong=self.review(question=question,answer='n4',correct=False,key='exact-picture-wrong')
        invalid=self.review(question=question,answer='n999',correct=False,key='not-an-option')
        self.assertTrue(self.current(question))
        self.assertEqual(current_homework_events(self.db,[correct,wrong,invalid]),[correct,wrong])
        self.assertEqual((correct['independent'],wrong['independent']),(0,0))
        # A similarly named value is not an answer without its exact option;
        # nor may an old frozen option change what the current picture counts.
        missing=deepcopy(question);missing['options']=[option for option in missing['options'] if option['value']!='n5']
        altered=deepcopy(question)
        next(option for option in altered['options'] if option['value']=='n5')['picture']['count']=6
        self.assertFalse(self.current(missing));self.assertFalse(self.current(altered))

    def test_real_legacy_decimal_picture_review_requires_current_recomputed_source(self):
        result=check_item({'prompt':'3 + 2 =','studentAnswer':'4','type':'arithmetic',
            'confidence':.99,'annotationAmbiguous':False,'region':self.result['region']},
            grade='primary_1',subject='math',policy=POLICY)
        self.assertEqual(result['method'],'decimal_arithmetic.v1')
        self.assertIsNone(reference_for_correction(result))
        question=self.picture_question(result)
        record=self.review(question=question,answer='n5',correct=True,key='legacy-decimal-picture')
        self.assertNotIn('referenceDigest',question)
        self.assertTrue(self.current(question))
        self.assertEqual(current_homework_events(self.db,[record]),[record])
        self.assertEqual(record['independent'],0)
        for patch in ({'recognitionNeedsConfirmation':True},{'expectedAnswer':'6'},{'prompt':'3 + 3 ='}):
            with self.subTest(patch=patch):
                changed={**result,**patch}
                self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(canonical(changed),self.item_id))
                self.assertFalse(self.current(question))
                self.assertEqual(current_homework_events(self.db,[record]),[])
        self.db.execute('UPDATE homework_items SET result_json=?,revision=2 WHERE id=?',(canonical(result),self.item_id))
        self.assertFalse(self.current(question))

    def test_nonprivate_and_nonphoto_legacy_reviews_are_preserved_without_photo_queries(self):
        public={**self.question,'private':False,'sourceSubmissionId':'hw_'+'f'*32}
        legacy={**self.question,'sourceSubmissionId':'legacy-private-fixture'}
        a=self.review(question=public,key='public');b=self.review(question=legacy,key='legacy')
        statements=[];self.db.raw.set_trace_callback(statements.append)
        try:
            self.assertTrue(self.current(public));self.assertTrue(self.current(legacy))
            self.assertEqual(current_homework_events(self.db,[a,b]),[a,b])
        finally:
            self.db.raw.set_trace_callback(None)
        self.assertEqual(statements,[])

    def test_invalid_source_json_fails_closed_without_mutating_events(self):
        record=self.review();before=self.rows()
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',('{broken',self.item_id))
        self.assertFalse(self.current());self.assertEqual(current_homework_events(self.db,[record]),[])
        self.assertEqual(self.rows(),before)
