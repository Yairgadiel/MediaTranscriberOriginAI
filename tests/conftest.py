import os
import threading
from types import SimpleNamespace

import pytest
from redis import Redis

from transcriber.application.transcription_service import TranscriptionService
from transcriber.config import Settings
from transcriber.infrastructure.local_storage import LocalMediaStorage
from transcriber.infrastructure.redis_coordination import RedisAdmissionControl, RedisWorkerHeartbeat
from transcriber.infrastructure.repositories.redis_job_repository import RedisJobRepository


@pytest.fixture
def client():
    # Dedicated disposable test database; never use application database zero.
    redis = Redis.from_url(os.environ.get('TEST_REDIS_URL', 'redis://redis:6379/15'), decode_responses=True)
    assert redis.connection_pool.connection_kwargs['db'] == 15
    redis.flushdb()
    yield redis
    redis.flushdb()
    redis.close()


@pytest.fixture
def context(client, tmp_path):
    settings = Settings(work_dir=tmp_path, max_upload_bytes=1024, disk_margin_bytes=0,
                        processing_timeout=5, cleanup_grace=5)
    repository = RedisJobRepository(client, ttl=30)
    storage = LocalMediaStorage(tmp_path)
    admission = RedisAdmissionControl(client, settings)
    heartbeat = RedisWorkerHeartbeat(client)
    client.set('worker:ready', '1')
    dispatched = []
    dispatcher = SimpleNamespace(dispatch=dispatched.append)
    service = TranscriptionService(repository, storage, dispatcher, admission, heartbeat, settings)
    return SimpleNamespace(settings=settings, redis=client, repository=repository, storage=storage,
                           admission=admission, heartbeat=heartbeat, service=service, dispatched=dispatched)
