"""Concrete dependency factories and FastAPI providers."""
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from redis import Redis

from transcriber.adapters.celery_dispatcher import CeleryTaskDispatcher
from transcriber.adapters.local_storage import LocalMediaStorage
from transcriber.config import Settings
from transcriber.domain.contracts import AdmissionControl, MediaStorage, TaskDispatcher, WorkerHeartbeat
from transcriber.domain.repositories.job_repository import JobRepository
from transcriber.adapters.redis_client import RedisAdmissionControl, RedisWorkerHeartbeat
from transcriber.adapters.redis_job_repository import RedisJobRepository
from transcriber.services.transcription_service import TranscriptionService


def create_redis_client(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True,
                          socket_connect_timeout=2, socket_timeout=2)


def create_transcription_service(settings: Settings | None = None) -> TranscriptionService:
    """Compose the long-lived service used by maintenance and the worker."""
    settings = settings or Settings()
    redis = create_redis_client(settings)
    return TranscriptionService(
        RedisJobRepository(redis, settings.result_ttl),
        LocalMediaStorage(settings.work_dir),
        CeleryTaskDispatcher(),
        RedisAdmissionControl(redis, settings),
        RedisWorkerHeartbeat(redis, settings.heartbeat_ttl),
        settings,
    )


def load_worker_engine(settings: Settings):
    from transcriber.adapters.ffmpeg_processor import FFmpegMediaProcessor
    from transcriber.adapters.whisper_engine import FasterWhisperEngine
    return FFmpegMediaProcessor(settings), FasterWhisperEngine(settings)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_redis_client() -> Redis:
    return create_redis_client(get_settings())


def get_job_repository(
    redis: Annotated[Redis, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JobRepository:
    return RedisJobRepository(redis, settings.result_ttl)


def get_media_storage(settings: Annotated[Settings, Depends(get_settings)]) -> MediaStorage:
    return LocalMediaStorage(settings.work_dir)


def get_task_dispatcher() -> TaskDispatcher:
    return CeleryTaskDispatcher()


def get_admission_control(
    redis: Annotated[Redis, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AdmissionControl:
    return RedisAdmissionControl(redis, settings)


def get_worker_heartbeat(
    redis: Annotated[Redis, Depends(get_redis_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> WorkerHeartbeat:
    return RedisWorkerHeartbeat(redis, settings.heartbeat_ttl)


@lru_cache
def get_uploading_jobs() -> set[str]:
    return set()


def get_transcription_service(
    repository: Annotated[JobRepository, Depends(get_job_repository)],
    storage: Annotated[MediaStorage, Depends(get_media_storage)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_task_dispatcher)],
    admission: Annotated[AdmissionControl, Depends(get_admission_control)],
    heartbeat: Annotated[WorkerHeartbeat, Depends(get_worker_heartbeat)],
    settings: Annotated[Settings, Depends(get_settings)],
    uploading: Annotated[set[str], Depends(get_uploading_jobs)],
) -> TranscriptionService:
    return TranscriptionService(repository, storage, dispatcher, admission, heartbeat, settings, uploading)
