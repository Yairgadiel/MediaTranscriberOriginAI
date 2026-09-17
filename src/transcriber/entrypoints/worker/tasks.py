from transcriber.infrastructure.messaging.celery_app import celery_app
from transcriber.entrypoints.worker import lifecycle

@celery_app.task(name='transcriber.process')
def process(job_id):
    if not lifecycle.ready.wait(120):
        c = lifecycle.container
        c.repository.fail(job_id, 'worker_unavailable', 'The worker could not load its model. Please try again.', 'queued')
        c.storage.delete(job_id)
        c.admission.release(job_id)
        return
    c = lifecycle.container
    c.heartbeat.current_job = job_id
    try:
        c.service.process(job_id)
    finally:
        c.heartbeat.current_job = None
