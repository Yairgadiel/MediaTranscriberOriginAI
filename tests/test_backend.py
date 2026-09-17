import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError

from transcriber.domain.job import Job, JobError
from transcriber.entrypoints.api import create_app
from transcriber.infrastructure.redis_coordination import RedisWorkerHeartbeat


def submitted(c):
    job_id = uuid4().hex
    c.service.reserve(job_id)
    job = c.service.submit(job_id, io.BytesIO(b'audio'))
    c.service.uploading.discard(job_id)
    return job


def test_repository_atomic_claim_and_terminal_protection(context):
    c = context
    job = Job.new(uuid4().hex)
    c.repository.create(job)
    assert c.redis.ttl('job:' + job.id) == -1
    with ThreadPoolExecutor(8) as pool:
        assert sum(pool.map(c.repository.claim, [job.id] * 20)) == 1
    assert c.repository.complete(job.id, 'text', 1)
    assert not c.repository.fail(job.id, 'bad', 'bad', 'processing')
    assert not c.repository.claim(job.id)
    result = c.repository.get(job.id)
    assert result.text == 'text' and result.expires_at > result.finished_at
    assert 0 < c.redis.ttl('job:' + job.id) <= 30
    assert c.repository.active() == []


def test_admission_atomic_capacity_disk_and_release(context):
    c = context
    ids = [uuid4().hex for _ in range(20)]
    with ThreadPoolExecutor(8) as pool:
        assert sum(pool.map(lambda i: c.admission.reserve(i, 10**12), ids)) == 3
    for job_id in ids:
        c.admission.release(job_id)
        c.admission.release(job_id)
    assert not c.admission.reserve(uuid4().hex, c.settings.reservation_bytes - 1)
    assert c.admission.reserve(uuid4().hex, c.settings.reservation_bytes)


@pytest.mark.parametrize('failure', [False, True])
def test_processing_cleanup_and_duplicate(context, failure):
    c = context
    job = submitted(c)
    calls = []
    def transcribe(path):
        calls.append(path)
        if failure:
            raise RuntimeError('private details')
        return ''  # Silence is valid completed output.
    engine = SimpleNamespace(transcribe=transcribe)
    processor = SimpleNamespace(normalize=lambda source, destination: 1.0)
    c.service.process(job.id, processor, engine)
    c.service.process(job.id, processor, engine)
    result = c.repository.get(job.id)
    assert result.status == ('failed' if failure else 'completed')
    assert len(calls) == 1
    assert not c.storage.directory(job.id).exists()
    assert c.redis.zcard('admission:leases') == 0
    assert 'private' not in json.dumps(result.as_dict())


@pytest.mark.parametrize('claimed', [False, True])
def test_ambiguous_publication_preserves_worker_files(context, claimed):
    c = context
    job_id = uuid4().hex
    c.service.reserve(job_id)
    def dispatch(job_id):
        if claimed:
            c.repository.claim(job_id)
        raise RuntimeError('publish failed')
    c.service.dispatcher = SimpleNamespace(dispatch=dispatch)
    with pytest.raises(RuntimeError):
        c.service.submit(job_id, io.BytesIO(b'audio'))
    c.service.abandon(job_id)
    assert c.storage.directory(job_id).exists() == claimed
    assert c.repository.get(job_id).status == ('processing' if claimed else 'failed')


def test_redis_outage_during_compensation_is_conservative(context, monkeypatch):
    c = context
    job = submitted(c)
    def unavailable(*args):
        raise ConnectionError('offline')
    monkeypatch.setattr(c.repository, 'get', unavailable)
    c.service.abandon(job.id)
    assert c.storage.directory(job.id).exists()
    assert c.redis.zcard('admission:leases') == 1


def test_reconcile_waits_for_deadline_and_heartbeat(context):
    c = context
    job = submitted(c)
    c.repository.claim(job.id)
    c.service.reconcile()  # No heartbeat alone is not evidence of safe deletion.
    assert c.storage.directory(job.id).exists()
    raw = c.repository.get(job.id).as_dict()
    raw['started_at'] = time.time() - 20
    c.redis.set('job:' + job.id, json.dumps(raw))
    c.redis.set('worker:job:' + job.id, '1')
    c.service.reconcile()
    assert c.storage.directory(job.id).exists()
    c.redis.delete('worker:job:' + job.id)
    c.service.reconcile()
    assert c.repository.get(job.id).error['code'] == 'interrupted'
    assert not c.storage.directory(job.id).exists()


def test_expired_upload_cleanup(context):
    c = context
    job_id = uuid4().hex
    c.admission.reserve(job_id, 10**12)
    c.storage.save(job_id, io.BytesIO(b'audio'), 1024)
    c.redis.zadd('admission:leases', {job_id: 0})
    c.service.reconcile()
    assert not c.storage.directory(job_id).exists()
    assert c.redis.zcard('admission:leases') == 0


def test_http_upload_status_validation_and_capacity(context):
    c = context
    with TestClient(create_app(c)) as api:
        assert api.get('/health').status_code == 200
        assert api.get('/api/transcriptions/missing').status_code == 404
        response = api.post('/api/transcriptions', files={'file': ('../../evil', b'a' * 1024)})
        assert response.status_code == 202
        job = response.json()
        assert job['status'] == 'queued' and job['created_at'].endswith('Z')
        assert api.get(job['status_url']).status_code == 200
        assert c.storage.input_path(job['id']).read_bytes() == b'a' * 1024
        assert c.dispatched == [job['id']]
        for files, expected in [({'file': ('x', b'')}, 400),
                                ({'file': ('x', b'a' * 1025)}, 413),
                                ({'wrong': ('x', b'a')}, 400),
                                ([('file', ('a', b'a')), ('file', ('b', b'b'))], 400)]:
            assert api.post('/api/transcriptions', files=files).status_code == expected
        assert c.redis.zcard('admission:leases') == 1
        assert api.post('/api/transcriptions', files={'file': ('x', b'a')}).status_code == 202
        assert api.post('/api/transcriptions', files={'file': ('x', b'a')}).status_code == 202
        response = api.post('/api/transcriptions', files={'file': ('x', b'a')})
        assert response.status_code == 429 and response.headers['retry-after'] == '5'


def test_http_actual_body_limit_without_content_length(context):
    c = context
    with TestClient(create_app(c)) as api:
        body = b'--bound\r\nContent-Disposition: form-data; name="file"; filename="x"\r\n\r\n' + b'x' * 70000
        response = api.post('/api/transcriptions', content=iter([body]),
                            headers={'content-type': 'multipart/form-data; boundary=bound'})
        assert response.status_code == 413
        assert c.redis.zcard('admission:leases') == 0
        assert list(c.settings.work_dir.iterdir()) == []


def test_http_worker_unavailable_and_publication_failure(context):
    c = context
    with TestClient(create_app(c)) as api:
        c.redis.delete('worker:ready')
        assert api.get('/health').status_code == 503
        assert api.post('/api/transcriptions', files={'file': ('x', b'a')}).status_code == 503
        c.redis.set('worker:ready', '1')
        def fail(*args):
            raise RuntimeError('private broker details')
        c.service.dispatcher = SimpleNamespace(dispatch=fail)
        response = api.post('/api/transcriptions', files={'file': ('x', b'a')})
        assert response.status_code == 503 and 'private' not in response.text
        assert c.redis.zcard('admission:leases') == 0
        assert list(c.settings.work_dir.iterdir()) == []


def test_worker_replacement_withholds_and_preserves_readiness(context):
    """A recycled child must not admit uploads until its own model has loaded."""
    c = context
    predecessor = RedisWorkerHeartbeat(c.redis, ttl=20)
    predecessor.start()
    for _ in range(20):
        if predecessor.ready():
            break
        time.sleep(0.01)
    assert predecessor.ready()

    predecessor.shutdown()
    assert not predecessor.ready()

    replacement = RedisWorkerHeartbeat(c.redis, ttl=20)
    replacement.mark_not_ready()
    assert not replacement.ready()
    replacement.start()
    for _ in range(20):
        if replacement.ready():
            break
        time.sleep(0.01)
    assert replacement.ready()

    predecessor.shutdown()  # A delayed predecessor shutdown cannot remove replacement readiness.
    assert replacement.ready()
    replacement.shutdown()
    assert not replacement.ready()
