from celery import Celery
from transcriber.config import Settings
s = Settings()
celery_app = Celery('transcriber', broker=s.redis_url, include=['transcriber.entrypoints.worker.tasks'])
celery_app.conf.update(task_ignore_result=True, result_backend=None, task_serializer='json',
    accept_content=['json'], worker_concurrency=1, worker_prefetch_multiplier=1,
    task_acks_late=False, task_reject_on_worker_lost=False, task_publish_retry=False,
    broker_connection_timeout=3, broker_connection_retry_on_startup=True,
    broker_transport_options={'socket_timeout': 3, 'socket_connect_timeout': 3},
    task_soft_time_limit=s.processing_timeout - 2, task_time_limit=s.processing_timeout,
    worker_hijack_root_logger=False)
