import unittest

from courseware.tools import post_publish


class PostPublishBatchTest(unittest.TestCase):
    def setUp(self):
        self.identity = {'editionId': 'edition', 'revisionId': 'directory', 'nodeId': 'node'}
        self.new_assignment = {**self.identity, 'owner': '/root/author', 'sourceSlug': 'lesson-arcade'}
        self.previous_assignment = {**self.identity, 'owner': '/root/author', 'slug': 'lesson-older'}
        self.ledger = {
            'currentGoalBatch': {'active': {'author': self.previous_assignment}},
            'arcade': {'active': {'author': self.new_assignment}},
        }
        self.receipt = {
            'contentKey': 'k', 'classroomId': 'classroom', 'releaseSha256': 'sha256',
            'verifiedAt': 'timestamp', 'receiptPath': 'receipt.json', 'timingsSeconds': {'studentPlayback': 1},
        }

    def test_finishing_pilot_only_updates_the_selected_batch(self):
        post_publish.record_completion(self.ledger, 'author', self.identity, 'lesson-arcade',
                                       self.receipt, batch_key='arcade')
        self.assertEqual(self.new_assignment['postPublishReceipt'], 'receipt.json')
        self.assertNotIn('postPublishReceipt', self.previous_assignment)

    def test_missing_batch_or_mismatched_lesson_has_no_fallback(self):
        for batch_key, error in [('unknown', 'batch is missing'), ('currentGoalBatch', 'Ledger lesson mismatch')]:
            with self.subTest(batch=batch_key), self.assertRaisesRegex(ValueError, error):
                post_publish.record_completion(self.ledger, 'author', self.identity, 'lesson-arcade',
                                               self.receipt, batch_key=batch_key)
