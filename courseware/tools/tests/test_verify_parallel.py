from threading import Barrier, Event
import unittest

from courseware.tools import verify


class ParallelVerificationTest(unittest.TestCase):
    def setUp(self):
        self.requests = [
            {'kind': 'speech', 'prompt': word, 'images': [word + '.png'], 'items': [{'id': word}]}
            for word in ('first', 'second')
        ]

    def test_concurrent_requests_keep_independent_model_and_receipt_order(self):
        started = Barrier(2)
        second_finished = Event()

        def runner(prompt, schema, model, effort, images):
            self.assertEqual((model, effort), ('gpt-6.1-terra', 'low'))
            self.assertEqual(schema, verify._schema('speech'))
            self.assertEqual(images, [prompt + '.png'])
            started.wait(timeout=3)
            if prompt == 'first':
                self.assertTrue(second_finished.wait(timeout=3))
            else:
                second_finished.set()
            return {'verdicts': [{'id': prompt, 'ok': True, 'issue': None}]}

        verdicts = verify.run_requests(self.requests, runner, jobs=2)
        self.assertEqual([item['id'] for item in verdicts], ['first', 'second'])

    def test_invalid_batch_fails_entire_verification(self):
        def runner(prompt, *_args):
            return {'verdicts': [{'id': 'wrong' if prompt == 'second' else prompt, 'ok': True, 'issue': None}]}
        with self.assertRaisesRegex(ValueError, 'Extra or duplicate verdict'):
            verify.run_requests(self.requests, runner, jobs=2)
