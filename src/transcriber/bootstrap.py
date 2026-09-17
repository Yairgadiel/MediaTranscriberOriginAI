from redis import Redis
from transcriber.config import Settings
from transcriber.infrastructure.repositories.redis_job_repository import RedisJobRepository
from transcriber.infrastructure.redis_coordination import RedisAdmissionControl, RedisWorkerHeartbeat
from transcriber.infrastructure.local_storage import LocalMediaStorage
from transcriber.application.transcription_service import TranscriptionService

class Container:
    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.redis = Redis.from_url(self.settings.redis_url, decode_responses=True,
                                   socket_connect_timeout=2, socket_timeout=2)
        self.repository = RedisJobRepository(self.redis, self.settings.result_ttl)
        self.storage = LocalMediaStorage(self.settings.work_dir)
        self.admission = RedisAdmissionControl(self.redis, self.settings)
        self.heartbeat = RedisWorkerHeartbeat(self.redis, self.settings.heartbeat_ttl)
        from transcriber.infrastructure.celery_dispatcher import CeleryTaskDispatcher
        self.service = TranscriptionService(self.repository, self.storage, CeleryTaskDispatcher(),
                                            self.admission, self.heartbeat, self.settings)

    def load_engine(self):
        from transcriber.infrastructure.whisper_engine import FasterWhisperEngine
        from transcriber.infrastructure.ffmpeg_processor import FFmpegMediaProcessor
        return FFmpegMediaProcessor(self.settings), FasterWhisperEngine(self.settings)
