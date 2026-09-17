"""Celery worker entrypoint: loads the model after forking and runs queued job IDs."""

import logging
import threading

from celery.signals import worker_process_init, worker_process_shutdown
from transcriber.dependencies import create_transcription_service, load_worker_engine
from transcriber.adapters.celery_dispatcher import celery_app

service = None
processor = engine = None
ready = threading.Event()


@worker_process_init.connect
def initialize(**kwargs):
    global service
    ready.clear()
    service = create_transcription_service()
    # A recycled child starts loading with no ready signal. Concurrency is fixed at one.
    service.heartbeat.mark_not_ready()

    # Child-init handlers must return promptly. Model is loaded only after fork.
    def load():
        global processor, engine
        try:
            processor, engine = load_worker_engine(service.settings)
            ready.set()
            service.heartbeat.start()
        except Exception:
            logging.getLogger(__name__).exception('Model initialization failed')
    threading.Thread(target=load, daemon=True).start()


@worker_process_shutdown.connect
def shutdown(**kwargs):
    if service:
        service.heartbeat.shutdown()


@celery_app.task(name='transcriber.process')
def process(job_id: str):
    if not ready.wait(service.settings.model_load_timeout):
        # CAS in abandon protects against duplicate delivery of already-owned work.
        service.compensate_failed_submission(job_id)
        return
    service.heartbeat.current_job = job_id
    try:
        service.transcribe_queued_job(job_id, processor, engine)
    finally:
        service.heartbeat.current_job = None
