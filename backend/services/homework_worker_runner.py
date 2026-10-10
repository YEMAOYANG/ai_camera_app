"""Durable homework job poller. Queue and call receipts, not threads, own progress."""
import threading
import time

class HomeworkWorkerRunner:
    def __init__(self):
        self._thread=None
        self._stop=threading.Event()
        self._lock=threading.Lock()
        self._state={'running':False,'lastCheckedAt':None,'lastError':None}

    def start(self,app):
        if self._thread and self._thread.is_alive():
            return
        if (app.config.get('TESTING') or not app.config.get('HOMEWORK_ANALYSIS_ENABLED')
            or not app.config.get('HOMEWORK_WORKER_ENABLED') or app.config.get('RUNTIME_ROLE','all') not in {'all','api'}):
            return
        self._stop.clear()
        self._thread=threading.Thread(target=self._run,args=(app,),name='homework-analysis',daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def status(self):
        with self._lock:
            return dict(self._state)

    def _run(self,app):
        with self._lock:
            self._state['running']=True
        try:
            interval=max(1,int(app.config.get('HOMEWORK_WORKER_INTERVAL_SECONDS',10)))
            while not self._stop.is_set():
                error=None
                result=None
                try:
                    with app.app_context():
                        from services.service_factory import homework_service
                        result=homework_service().process_next()
                        error=result.get('error')
                except Exception:
                    # No provider response, source text or credentials in status/logs.
                    # A durable in-flight request becomes unknown on safe recovery.
                    error='homework_worker_unavailable'
                with self._lock:
                    self._state.update(lastCheckedAt=int(time.time()*1000),lastError=error)
                self._stop.wait(0.1 if result and result.get('processed') else interval)
        finally:
            with self._lock:
                self._state['running']=False

homework_worker_runner=HomeworkWorkerRunner()
def start_homework_worker(app):
    homework_worker_runner.start(app)
def homework_worker_status():
    return homework_worker_runner.status()
