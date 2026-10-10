"""Isolated execution for review-owned tasks; never blocks the care scheduler."""
import os
import threading
import time


class LearningReviewSchedulerRunner:
    def __init__(self):
        self._thread=None
        self._stop=threading.Event()
        self._lock=threading.Lock()
        self._state={'running':False,'lastTickAt':None,'nextTickAt':None,'tickCount':0,
                     'lastError':None,'lastResult':None}

    def start(self,app):
        if (app.config.get('TESTING') or not app.config.get('LEARNING_REVIEW_ENABLED')
                or not app.config.get('TASK_SCHEDULER_ENABLED')
                or os.getenv('MIRA_PROCESS_ROLE','all') not in {'all','api'}):
            return
        if self._thread and self._thread.is_alive():
            return
        if app.config.get('DEBUG') and os.getenv('WERKZEUG_RUN_MAIN')=='false':
            return
        interval=max(1,int(app.config.get('TASK_SCHEDULER_INTERVAL_SECONDS',15)))
        self._stop.clear()
        self._thread=threading.Thread(target=self._run,args=(app,interval),name='learning-review-scheduler',daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def status(self):
        with self._lock:
            return dict(self._state)

    def _run(self,app,interval):
        with self._lock:
            self._state['running']=True
        try:
            while not self._stop.is_set():
                tick_start=int(time.time()*1000)
                error,result=None,None
                try:
                    with app.app_context():
                        from services.service_factory import learning_review_service
                        result=learning_review_service().tick(now=tick_start)
                except Exception:
                    # Failure belongs only to this runner. Do not expose source
                    # questions/credentials in operational status or retry speech.
                    error='learning_review_scheduler_failed'
                with self._lock:
                    self._state.update(lastTickAt=tick_start,nextTickAt=int((time.time()+interval)*1000),
                        tickCount=self._state['tickCount']+1,lastError=error,lastResult=result)
                self._stop.wait(interval)
        finally:
            with self._lock:
                self._state['running']=False


learning_review_scheduler_runner=LearningReviewSchedulerRunner()


def start_learning_review_scheduler(app):
    learning_review_scheduler_runner.start(app)


def learning_review_scheduler_status():
    return learning_review_scheduler_runner.status()
