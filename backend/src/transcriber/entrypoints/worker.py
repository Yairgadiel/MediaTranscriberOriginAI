"""Celery worker entrypoint: loads the model after forking and runs queued job IDs."""

import logging
import threading
import time

from celery.signals import worker_process_init, worker_process_shutdown
from transcriber.dependencies import create_transcription_service, load_worker_engine
from transcriber.adapters.celery_dispatcher import celery_app
from transcriber.adapters.whisper_engine import is_transient_model_error
from transcriber.services.retry_policy import retry_transient

service = None
processor = engine = None
ready = threading.Event()


def wait_for_worker_ready(wait, timeout, attempts, delay, max_delay, sleep=time.sleep):
    for attempt in range(1, attempts + 1):
        if wait(timeout):
            return True
        if attempt < attempts:
            sleep(min(delay * (2 ** (attempt - 1)), max_delay))
    return False


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
            processor, engine = retry_transient(
                lambda: load_worker_engine(service.settings), retryable=is_transient_model_error,
                job_id=None, event='model_readiness', max_attempts=service.settings.retry_max_attempts,
                delay=service.settings.retry_delay_seconds, max_delay=service.settings.retry_max_delay_seconds,
            )
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
    settings = service.settings
    if not wait_for_worker_ready(ready.wait, settings.model_load_timeout,
                                 settings.retry_max_attempts, settings.retry_delay_seconds,
                                 settings.retry_max_delay_seconds):
        # It is still queued, so this conditional transition cannot affect duplicate work.
        service.fail_unclaimed_job(job_id, 'worker_unavailable',
                                    'The worker could not start. Please upload again.')
        return
    service.heartbeat.current_job = job_id
    try:
        service.transcribe_queued_job(job_id, processor, engine)
    finally:
        service.heartbeat.current_job = None
