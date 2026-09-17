from redis import Redis
from transcriber.config import Settings
from transcriber.infrastructure.repositories.redis_job_repository import RedisJobRepository
from transcriber.infrastructure.coordination.redis_admission_control import RedisAdmissionControl
from transcriber.infrastructure.coordination.redis_worker_heartbeat import RedisWorkerHeartbeat
from transcriber.infrastructure.storage.local_media_storage import LocalMediaStorage
from transcriber.application.services.transcription_service import TranscriptionService

class Container:
    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.redis = Redis.from_url(self.settings.redis_url, decode_responses=True,
                                   socket_connect_timeout=2, socket_timeout=2)
        self.repository = RedisJobRepository(self.redis, self.settings.result_ttl)
        self.storage = LocalMediaStorage(self.settings.work_dir)
        self.admission = RedisAdmissionControl(self.redis, self.settings)
        self.heartbeat = RedisWorkerHeartbeat(self.redis, self.settings.heartbeat_ttl)
        from transcriber.infrastructure.messaging.celery_app import celery_app
        from transcriber.infrastructure.messaging.celery_task_dispatcher import CeleryTaskDispatcher
        self.service = TranscriptionService(self.repository, self.storage, CeleryTaskDispatcher(celery_app),
                                            self.admission, self.settings)

    def load_engine(self):
        from transcriber.infrastructure.inference.faster_whisper_engine import FasterWhisperEngine
        from transcriber.infrastructure.media.ffmpeg_media_processor import FFmpegMediaProcessor
        self.service.engine = FasterWhisperEngine(self.settings)
        self.service.processor = FFmpegMediaProcessor(self.settings)
