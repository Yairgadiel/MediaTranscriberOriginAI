class CeleryTaskDispatcher:
    def __init__(self, app):
        self.app = app

    def dispatch(self, job_id):
        self.app.send_task('transcriber.process', args=[job_id], task_id=job_id)
