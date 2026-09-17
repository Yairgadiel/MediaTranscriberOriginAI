import logging
import threading

from celery.signals import worker_process_init, worker_process_shutdown
from transcriber.bootstrap import Container
from transcriber.infrastructure.celery_dispatcher import celery_app

container = None
processor = engine = None
ready = threading.Event()


@worker_process_init.connect
def initialize(**kwargs):
    global container
    ready.clear()
    container = Container()
    # A recycled child starts loading with no ready signal. Concurrency is fixed at one.
    container.heartbeat.mark_not_ready()

    # Child-init handlers must return promptly. Model is loaded only after fork.
    def load():
        global processor, engine
        try:
            processor, engine = container.load_engine()
            ready.set()
            container.heartbeat.start()
        except Exception:
            logging.getLogger(__name__).exception('Model initialization failed')
    threading.Thread(target=load, daemon=True).start()


@worker_process_shutdown.connect
def shutdown(**kwargs):
    if container:
        container.heartbeat.shutdown()


@celery_app.task(name='transcriber.process')
def process(job_id: str):
    if not ready.wait(container.settings.model_load_timeout):
        # CAS in abandon protects against duplicate delivery of already-owned work.
        container.service.abandon(job_id)
        return
    container.heartbeat.current_job = job_id
    try:
        container.service.process(job_id, processor, engine)
    finally:
        container.heartbeat.current_job = None
