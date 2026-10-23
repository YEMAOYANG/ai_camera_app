"""Exact representation counterexamples; registered policy only, no provider calls."""
from copy import deepcopy
import unittest
from content.textbook_pinyin_carrier_equivalence import exact_representation, validate_evidence
from content.textbook_pinyin_pronunciation import registered_policy
from core.errors import ApiError


class ExactCarrierTests(unittest.TestCase):
    def setUp(self):
        self.policy=registered_policy('mira.textbook.pinyin-zhchshr-ssml.v1')

    def match(self,source,transcript):
        return exact_representation(source,transcript,self.policy)

    def test_contiguous_literals_and_carriers_in_full_sentence(self):
        for token,carrier in [('zhuǎ','爪'),('chuō','戳'),('chi','吃'),('chī','吃'),('shuō','说'),('zhí','直')]:
            for transcript in (f'请听整卡：{token}。',f'请听整卡：{carrier}。'):
                with self.subTest(token=token,transcript=transcript):
                    result=self.match(f'请听整卡：{token}。',transcript)
                    self.assertTrue(result['contextCharactersIdentical'])
                    self.assertEqual(result['targets'][0]['symbol'],token)

    def test_each_repeated_target_is_independently_matched(self):
        value=self.match('先听：chi，再听：chī，最后再听：chi。','先听吃，再听chī，最后再听吃。')
        self.assertEqual([x['representation'] for x in value['targets']],['carrier','literal','carrier'])
        for text in ('先听吃，再听吃。','先听吃，再听吃，最后再听迟。'):
            with self.subTest(text=text),self.assertRaises(ApiError):
                self.match('先听：chi，再听：chī，最后再听：chi。',text)

    def test_chinese_context_cannot_be_added_removed_or_substituted(self):
        for text in ('请听正卡吃','请听卡吃','请听整卡吃再来一次','听请整卡吃'):
            with self.subTest(text=text),self.assertRaises(ApiError):self.match('请听整卡：chi。',text)

    def test_homophones_and_tone_stripping_are_not_equivalence(self):
        for source,text in [('zhí','迟'),('shà','下'),('chī','chi'),('rǔ','rú'),('shī','sh'),('ri','rì'),('è','é')]:
            with self.subTest(source=source,text=text),self.assertRaises(ApiError):self.match('请听：'+source+'。','请听：'+text+'。')

    def test_punctuation_cannot_split_or_merge_latin_targets(self):
        for text in ('c h i','c,h,i','CHi','CHI','chí','chiX','Xchi'):
            with self.subTest(text=text),self.assertRaises(ApiError):self.match('请听：chi。','请听：'+text+'。')
        with self.assertRaises(ApiError):self.match('请听：chi，shi。','请听：chishi。')

    def test_context_spacing_and_punctuation_only_is_explicit(self):
        self.assertTrue(self.match('请听：chi。','请 听， 吃！')['orthographicEquivalent'])
        with self.assertRaises(ApiError):self.match('请听：chī。','请听：chi\u0304。')

    def test_no_chinese_override_or_non_pinyin_target_can_enter(self):
        policy=deepcopy(self.policy);policy['words']={'桌子':{'ph':'zhuo1 zi5','carrier':'桌子'}}
        with self.assertRaises(ApiError):exact_representation('请听chi','请听吃',policy)
        for source in ('请听老师读。','请听hello。'):
            with self.subTest(source=source),self.assertRaises(ApiError):self.match(source,source)

    def test_invalid_text_and_manifest_shapes_fail_closed(self):
        for text in ('','请听：吃。\x00','请听：吃。\u200b'):
            with self.subTest(text=text),self.assertRaises(ApiError):self.match('请听：chi。',text)
        for value in (None,{}, {'segments':[None]}, {'segments':['wrong']}):
            with self.subTest(value=value),self.assertRaises(ApiError):validate_evidence(value,now_ms=1)
