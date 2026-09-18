from celery import Celery
from kombu.exceptions import OperationalError
from transcriber.config import Settings
from transcriber.domain.contracts import TaskDispatcher
s = Settings()
celery_app = Celery('transcriber', broker=s.redis_url, include=['transcriber.entrypoints.worker'])
celery_app.conf.update(task_ignore_result=True, result_backend=None, task_serializer='json',
    accept_content=['json'], worker_concurrency=1, worker_prefetch_multiplier=1,
    task_acks_late=False, task_reject_on_worker_lost=False, task_publish_retry=False,
    broker_connection_timeout=3, broker_connection_retry_on_startup=True,
    broker_transport_options={'socket_timeout': 3, 'socket_connect_timeout': 3},
    task_soft_time_limit=s.processing_timeout - 2, task_time_limit=s.processing_timeout,
    worker_max_tasks_per_child=s.worker_max_tasks_per_child,
    worker_hijack_root_logger=False)


class CeleryTaskDispatcher(TaskDispatcher):
    def dispatch(self, job_id: str) -> None:
        try:
            celery_app.send_task('transcriber.process', args=[job_id], task_id=job_id)
        except OperationalError as exc:
            # The service retries only broker-connectivity/publication failures.
            raise TransientPublicationError() from exc


class TransientPublicationError(RuntimeError):
    """A broker result is unknown, so publication compensation remains conservative."""
