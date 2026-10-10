"""Seed helper uses caller-owned transactions and production answer semantics."""
import unittest
import json
from unittest.mock import patch

from scripts.dev_review_sample import create_review_samples
import test_learning_reviews as fixtures


class DemoReviewSeedTest(unittest.TestCase):
    setUp=fixtures.ReviewsTest.setUp

    def test_three_demo_states_are_graded_idempotent_and_keep_actual_timestamps(self):
        pool=[fixtures.question(f'skill{s}',i,'real-shared-course') for s in range(6) for i in range(9)]
        course={'id':'real-shared-course','version':'1'}
        with patch('scripts.dev_review_sample._published_pool',return_value=pool),self.db.transaction():
            first=create_review_samples(self.db,child=self.child,course=course,now=self.now,seed_namespace='test_review_demo')
            second=create_review_samples(self.db,child=self.child,course=course,now=self.now+1000,seed_namespace='test_review_demo')
        self.assertEqual(first,second)
        by_case={r['scenario']:r for r in first['reviews']}
        self.assertEqual((by_case['ready']['status'],by_case['ready']['totalQuestions'],by_case['ready']['answeredCount']),('scheduled',10,0))
        self.assertEqual((by_case['paused']['status'],by_case['paused']['answeredCount']),('paused',2))
        self.assertEqual((by_case['completed']['status'],by_case['completed']['answeredCount'],by_case['completed']['correctCount']),('completed',6,4))
        rows=self.db.execute('SELECT * FROM learning_review_runs').fetchall()
        self.assertEqual(len(rows),3)
        self.assertTrue(all(r['created_at']==self.now for r in rows))
        self.assertEqual({r['week_start'] for r in rows},{'2026-09-14','2026-09-21','2026-09-28'})
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM learning_answer_events').fetchone()['n'],0)
        self.assertTrue(all(json.loads(r['coverage_json'])['syntheticFixture'] is True for r in rows))
        self.assertTrue(all('测试体验' in row['title'] for row in self.db.execute('SELECT title FROM tasks').fetchall()))
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM learning_sessions').fetchone()['n'],0)

    def test_conflicting_demo_namespace_never_overwrites_existing_results(self):
        pool=[fixtures.question(f'skill{s}',i,'real-shared-course') for s in range(6) for i in range(9)]
        with patch('scripts.dev_review_sample._published_pool',return_value=pool):
            with self.db.transaction():
                create_review_samples(self.db,child=self.child,course={'id':'real-shared-course','version':'1'},now=self.now,seed_namespace='one_demo')
            with self.assertRaises(ValueError),self.db.transaction():
                create_review_samples(self.db,child=self.child,course={'id':'real-shared-course','version':'1'},now=self.now,seed_namespace='another_demo')
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM learning_review_runs').fetchone()['n'],3)


if __name__=='__main__':
    unittest.main()
