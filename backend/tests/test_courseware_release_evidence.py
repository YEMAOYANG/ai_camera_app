"""Regression coverage for binding teaching and random-play evidence into a light release."""
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from content.courseware_release import LIGHT_SCHEMA, build_release
from services.courseware_publish_service import CoursewarePublishService
from tests.test_courseware_publish_service import write_lesson
from tests.test_courseware_release import sample_inputs
from content.textbook_catalog import digest


class CoursewareReleaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.inputs = sample_inputs()

    def rejected(self, code):
        with self.assertRaisesRegex(ValueError, '^' + code + '$'):
            build_release(self.inputs)

    def test_random_play_receipt_is_required_current_successful_and_frozen(self):
        prepared = build_release(self.inputs)
        evidence = prepared['frozen']['coursewareLight']['evidence']
        self.assertEqual(prepared['frozen']['coursewareLight']['schemaVersion'], LIGHT_SCHEMA)
        self.assertEqual(evidence['playReceiptSha256'], digest(self.inputs['playReceipt']))
        for receipt in (None,
                        {**self.inputs['playReceipt'], 'bodySha256': '0' * 64},
                        {**self.inputs['playReceipt'], 'ok': False},
                        {**self.inputs['playReceipt'], 'pages': [{'scene': 1, 'ok': True, 'finished': True,
                                                                  'errors': [], 'stuck': None}]}):
            with self.subTest(receipt=receipt):
                self.inputs = sample_inputs()
                self.inputs['playReceipt'] = receipt
                self.rejected('play_receipt_invalid')

    def test_verification_is_bound_to_current_notes_and_every_teaching_goal(self):
        self.inputs['verification']['notesSha256'] = '0' * 64
        self.rejected('verification_invalid')
        self.inputs = sample_inputs()
        self.inputs['notes']['keyPoint'] = 'Compare only after counting both sides.'
        self.inputs['verification']['notesSha256'] = digest(self.inputs['notes'])
        self.rejected('verification_invalid')

    def test_publish_checker_receives_teaching_and_random_play_contract(self):
        checker = Mock(return_value=[])
        with tempfile.TemporaryDirectory() as directory:
            lesson = Path(directory) / 'lesson'
            write_lesson(lesson, self.inputs)
            service = CoursewarePublishService(None, classroom_directory=Path(directory) / 'classrooms',
                                               manifest=deepcopy(self.inputs['manifest']), checker=checker)
            result = service.check(lesson)
        self.assertTrue(result['ok'], result)
        kwargs = checker.call_args.kwargs
        self.assertTrue(kwargs['teaching'])
        self.assertTrue(kwargs['require_play'])
        self.assertEqual(kwargs['play_receipt'], self.inputs['playReceipt'])


if __name__ == '__main__':
    unittest.main()
