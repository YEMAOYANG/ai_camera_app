"""A blocked or broken review tick cannot suppress existing task care work."""
import os
import threading
import unittest
from unittest.mock import Mock,patch

from flask import Flask
from services.learning_review_scheduler_runner import LearningReviewSchedulerRunner
from services.task_scheduler_runner import TaskSchedulerRunner


class ReviewSchedulerTests(unittest.TestCase):
    def app(self):
        app=Flask(__name__)
        app.config.update(LEARNING_REVIEW_ENABLED=True,TASK_SCHEDULER_ENABLED=True,CARE_ROUTINE_REMINDER_ENABLED=True)
        return app

    def test_slow_then_failed_review_does_not_block_task_publish_or_routine(self):
        app=self.app();review=LearningReviewSchedulerRunner();care=TaskSchedulerRunner()
        entered,release=threading.Event(),threading.Event()
        def failing_review(**kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError('fixture timeout')
            raise RuntimeError('simulated unavailable review database')
        runtime=Mock();runtime.tick.return_value={'ok':True,'changedTasks':[{'id':'existing-task'}],'events':[]}
        routine=Mock();routine.tick.return_value={'ok':True}
        publish=Mock(side_effect=lambda result:care.stop())
        with patch('services.service_factory.learning_review_service',return_value=Mock(tick=failing_review)), \
             patch('services.service_factory.task_runtime_service',return_value=runtime), \
             patch('services.service_factory.routine_reminder_service',return_value=routine), \
             patch('services.task_event_stream.publish_task_runtime_result',publish):
            worker=threading.Thread(target=review._run,args=(app,1),daemon=True)
            worker.start()
            try:
                self.assertTrue(entered.wait(1),'review tick must actually be blocked')
                care._run(app,1)
                runtime.tick.assert_called_once()
                publish.assert_called_once()
                routine.tick.assert_called_once()
                self.assertEqual(care.status()['lastError'],'')
                self.assertTrue(worker.is_alive(),'care completed while review remained blocked')
            finally:
                review.stop();release.set();worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(review.status()['lastError'],'learning_review_scheduler_failed')
        self.assertEqual(review.status()['tickCount'],1)

    def test_testing_passive_disabled_and_non_api_roles_do_not_start_threads(self):
        app=self.app()
        for role,testing,enabled,scheduler in [('api',True,True,True),('api-passive',False,True,True),
                ('curriculum-worker',False,True,True),('api',False,False,True),('all',False,True,False)]:
            app.config.update(TESTING=testing,LEARNING_REVIEW_ENABLED=enabled,TASK_SCHEDULER_ENABLED=scheduler)
            with self.subTest(role=role,testing=testing,enabled=enabled),patch.dict(os.environ,{'MIRA_PROCESS_ROLE':role}), \
                    patch('services.learning_review_scheduler_runner.threading.Thread') as thread:
                LearningReviewSchedulerRunner().start(app)
                thread.assert_not_called()

    def test_enabled_api_and_all_start_one_dedicated_runner(self):
        for role in ('api','all'):
            with self.subTest(role=role),patch.dict(os.environ,{'MIRA_PROCESS_ROLE':role}), \
                    patch('services.learning_review_scheduler_runner.threading.Thread') as thread:
                thread.return_value.is_alive.return_value=True
                runner=LearningReviewSchedulerRunner();runner.start(self.app());runner.start(self.app())
                thread.assert_called_once()
                self.assertEqual(thread.call_args.kwargs['name'],'learning-review-scheduler')
                thread.return_value.start.assert_called_once()


if __name__=='__main__':
    unittest.main()
