import logging
import threading
from celery.signals import worker_process_init, worker_process_shutdown
from transcriber.bootstrap import Container

container = None
ready = threading.Event()

@worker_process_init.connect
def initialize(**kwargs):
    global container
    container = Container()
    # Celery child-init callbacks must return promptly; loading stays in child.
    def load():
        try:
            container.load_engine()
            container.heartbeat.model_ready = True
            ready.set()
            container.heartbeat.run()
        except Exception:
            logging.getLogger(__name__).error('Model initialization failed; worker remains unavailable')
    threading.Thread(target=load, daemon=True).start()

@worker_process_shutdown.connect
def shutdown(**kwargs):
    if container:
        container.heartbeat.stop.set()
