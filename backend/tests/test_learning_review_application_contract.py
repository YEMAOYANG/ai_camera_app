"""Application/factory construction without a database, network or environment file."""
import os
import tempfile
import unittest
from unittest.mock import patch


class LearningReviewApplicationContractTest(unittest.TestCase):
    def test_disabled_and_enabled_application_factories_are_lazy(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            'APP_ENV':'test','MIRA_PROCESS_ROLE':'api-passive','APP_AI_PROVIDER':'disabled',
            'APP_TEST_DATABASE_URL':'postgresql://contract:contract@127.0.0.1:1/contract_only',
        }, clear=True), patch('dotenv.load_dotenv',return_value=False), \
             patch('core.database.Database.connect',side_effect=AssertionError('Construction must not connect')) as connect, \
             patch('socket.socket.connect',side_effect=AssertionError('Construction must not use a network')) as network:
            from app import create_app
            from services.service_factory import learning_review_service,homework_service
            from services.task_scheduler_runner import task_scheduler_status
            from services.learning_review_scheduler_runner import learning_review_scheduler_status
            from services.homework_worker_runner import homework_worker_status
            for enabled in (False,True):
                app=create_app({'TESTING':True,'LEARNING_REVIEW_ENABLED':enabled,
                    'HOMEWORK_ANALYSIS_ENABLED':enabled,'HOMEWORK_AUDIO_ENABLED':enabled,
                    'HOMEWORK_WORKER_ENABLED':enabled,'TASK_SCHEDULER_ENABLED':enabled,
                    'HOMEWORK_ASSET_ROOT':directory+'/private-assets'})
                paths={str(rule) for rule in app.url_map.iter_rules()}
                self.assertIn('/api/v2/student/learning/reviews/<run_id>/answers',paths)
                self.assertIn('/api/children/<child_id>/review-preferences',paths)
                self.assertIn('/api/reports/learning/weaknesses',paths)
                with app.app_context():
                    review=learning_review_service()
                    homework=homework_service()
                    self.assertEqual(homework.enabled,enabled)
                    self.assertEqual(homework.evidence_enabled,enabled)
                    self.assertEqual(callable(review.private_question_pool),enabled)
                    self.assertTrue(callable(review.reminder_sender))
                self.assertFalse(task_scheduler_status()['running'])
                self.assertFalse(learning_review_scheduler_status()['running'])
                self.assertFalse(homework_worker_status()['running'])
            connect.assert_not_called()
            network.assert_not_called()


if __name__=='__main__':
    unittest.main()
