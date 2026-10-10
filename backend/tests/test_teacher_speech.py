"""Shared teacher speech formatting; no providers, database or credentials."""
import unittest

from services.teacher_speech import (MAX_SPEECH_CHARACTERS,
    SPEECH_POLICY_VERSION, normalize_teacher_speech)


class TeacherOrdinalSpeechTests(unittest.TestCase):
    def test_ordinals_use_er_and_leave_quantities_in_the_same_sentence(self):
        self.assertEqual(
            normalize_teacher_speech('第2棵、第12题、2个苹果、第20页、第101题；两棵树。'),
            '第二棵、第十二题、2个苹果、第二十页、第一百零一题；两棵树。')

    def test_decimal_places_and_internal_zero_are_correct(self):
        cases = {1:'一', 2:'二', 10:'十', 11:'十一', 12:'十二', 20:'二十',
            22:'二十二', 100:'一百', 101:'一百零一', 110:'一百一十',
            200:'二百', 1000:'一千', 1001:'一千零一', 1010:'一千零一十',
            1100:'一千一百', 1101:'一千一百零一', 9999:'九千九百九十九'}
        for number, spoken in cases.items():
            with self.subTest(number=number):
                self.assertEqual(normalize_teacher_speech(f'第{number}题'), f'第{spoken}题')

    def test_fullwidth_and_intervening_whitespace_are_local_to_ordinals(self):
        self.assertEqual(normalize_teacher_speech('第 ２ 棵，第\n１２题；２个；２＋３＝５'),
            '第二 棵，第十二题；２个；２＋３＝５')
        self.assertEqual(normalize_teacher_speech('第两棵、第兩棵、第 两 题，两个，兩棵'),
            '第二棵、第二棵、第二 题，两个，兩棵')

    def test_decimals_subsection_identifiers_fractions_and_expressions_stay_verbatim(self):
        for text in ('第2.1题', '第２．１题', '第12.34节', '第2 . 1题',
            '第2/3题', '第2+3题', '第2−3题', '第2-3题', '第2×3题',
            '第1,000页', '2+3=5，0.2，2个苹果，两棵树，Question 2, Page 20'):
            with self.subTest(text=text):
                self.assertEqual(normalize_teacher_speech(text), text)

    def test_unknown_zero_and_large_identifiers_are_not_partially_normalized(self):
        for text in ('第0题', '第０题', '第10000题', '第１２３４５题', '第999999999999999999题'):
            with self.subTest(text=text):
                self.assertEqual(normalize_teacher_speech(text), text)

    def test_chinese_explanations_are_normalized_across_subjects(self):
        for text, expected in (
            ('语文第2段，读第12个字。', '语文第二段，读第十二个字。'),
            ('数学从左数第22个，算2+3。', '数学从左数第二十二个，算2+3。'),
            ('英语第20页：Question 2 has 2 apples.', '英语第二十页：Question 2 has 2 apples.'),
        ):
            with self.subTest(text=text):
                self.assertEqual(normalize_teacher_speech(text), expected)

    def test_input_and_expanded_output_are_bounded_without_truncation(self):
        self.assertEqual(normalize_teacher_speech('第2棵', maximum_characters=3), '第二棵')
        for text, limit in (('长'*(MAX_SPEECH_CHARACTERS+1),MAX_SPEECH_CHARACTERS), ('第9999题',6)):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                normalize_teacher_speech(text, maximum_characters=limit)
        for limit in (0,-1,True,MAX_SPEECH_CHARACTERS+1):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                normalize_teacher_speech('第2棵', maximum_characters=limit)
        with self.assertRaises(TypeError):
            normalize_teacher_speech(None)

    def test_normalization_is_idempotent_and_policy_is_versioned(self):
        text='第 ２棵，第兩棵，2个，第101题，第2.1节。'
        once=normalize_teacher_speech(text)
        self.assertEqual(normalize_teacher_speech(once),once)
        self.assertEqual(SPEECH_POLICY_VERSION,'mira.teacher-speech-ordinals.v1')


if __name__ == '__main__':
    unittest.main()
