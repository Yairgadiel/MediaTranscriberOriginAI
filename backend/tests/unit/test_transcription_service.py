import io
import unittest
from types import SimpleNamespace

from transcriber.services.transcription_service import TranscriptionService
from transcriber.domain.models.job import Job


class FakeRepository:
    def __init__(self):
        self.jobs = {}

    def create(self, job):
        self.jobs[job.id] = job

    def get(self, job_id):
        return self.jobs.get(job_id)

    def claim(self, job_id):
        job = self.jobs.get(job_id)
        if job is None or job.status != 'queued':
            return False
        job.status, job.stage = 'processing', 'validating'
        return True

    def stage(self, job_id, stage):
        self.jobs[job_id].stage = stage

    def complete(self, job_id, text, duration):
        job = self.jobs[job_id]
        if job.status != 'processing':
            return False
        job.status, job.text, job.duration_seconds = 'completed', text, duration
        return True

    def fail(self, job_id, code, message, expected):
        job = self.jobs.get(job_id)
        if job is None or job.status != expected:
            return False
        job.status, job.error = 'failed', {'code': code, 'message': message}
        return True

    def active(self):
        return [job for job in self.jobs.values() if job.status in ('queued', 'processing')]


class FakeStorage:
    def __init__(self):
        self.files = set()
        self.deleted = []

    def save(self, job_id, source, max_bytes):
        self.files.add(job_id)

    def delete(self, job_id):
        self.files.discard(job_id)
        self.deleted.append(job_id)

    def free_bytes(self):
        return 10**12

    def old_directories(self, before):
        return []


class FakeAdmission:
    def __init__(self):
        self.reserved, self.released = set(), []

    def reserve(self, job_id, free_bytes):
        self.reserved.add(job_id)
        return True

    def renew(self, job_id, seconds):
        return job_id in self.reserved

    def release(self, job_id):
        self.reserved.discard(job_id)
        self.released.append(job_id)

    def expired(self):
        return []


class TranscriptionServiceTest(unittest.TestCase):
    def setUp(self):
        self.repository = FakeRepository()
        self.storage = FakeStorage()
        self.admission = FakeAdmission()
        self.dispatched = []
        self.dispatcher = SimpleNamespace(dispatch=self.dispatched.append)
        self.service = TranscriptionService(
            self.repository, self.storage, self.dispatcher, self.admission,
            SimpleNamespace(ready=lambda: True, job_alive=lambda job_id: False),
            SimpleNamespace(max_upload_bytes=1024, queue_timeout=10, cleanup_grace=1,
                            processing_timeout=10, upload_timeout=10),
        )

    def submit(self, job_id='job'):
        self.service.reserve_upload_capacity(job_id)
        job = self.service.store_and_enqueue(job_id, io.BytesIO(b'audio'))
        self.service.uploading.discard(job_id)
        return job

    def test_processing_failure_is_sanitized_cleaned_up_and_not_retried(self):
        job = self.submit()
        engine = SimpleNamespace(transcribe=lambda audio: (_ for _ in ()).throw(RuntimeError('private detail')))
        processor = SimpleNamespace(normalize=lambda source, destination: 1.0)

        self.service.transcribe_queued_job(job.id, processor, engine)
        self.service.transcribe_queued_job(job.id, processor, engine)

        result = self.repository.get(job.id)
        self.assertEqual(result.status, 'failed')
        self.assertEqual(result.error['code'], 'processing_failed')
        self.assertNotIn('private detail', result.error['message'])
        self.assertNotIn(job.id, self.storage.files)
        self.assertEqual(self.storage.deleted, [job.id])
        self.assertEqual(self.admission.released, [job.id])

    def test_publication_failure_marks_queued_job_failed_and_compensates(self):
        self.dispatcher.dispatch = lambda job_id: (_ for _ in ()).throw(RuntimeError('broker down'))
        self.service.reserve_upload_capacity('job')

        with self.assertRaisesRegex(RuntimeError, 'broker down'):
            self.service.store_and_enqueue('job', io.BytesIO(b'audio'))
        self.service.compensate_failed_submission('job')

        result = self.repository.get('job')
        self.assertEqual(result.status, 'failed')
        self.assertEqual(result.error['code'], 'submission_failed')
        self.assertNotIn('job', self.storage.files)
        self.assertEqual(self.admission.released, ['job'])

    def test_reconcile_fails_only_stale_processing_job_and_does_not_retry(self):
        stale = self.submit('stale')
        live = self.submit('live')
        self.repository.claim(stale.id)
        self.repository.claim(live.id)
        stale.started_at = -100
        self.service.heartbeat = SimpleNamespace(
            job_alive=lambda job_id: job_id == live.id,
        )

        self.service.reconcile_expired_work()

        result = self.repository.get(stale.id)
        self.assertEqual(result.status, 'failed')
        self.assertEqual(result.error, {
            'code': 'interrupted',
            'message': 'The job expired or was interrupted. Please upload again.',
        })
        self.assertNotIn(stale.id, self.storage.files)
        self.assertEqual(self.admission.released, [stale.id])
        self.assertEqual(self.dispatched, [stale.id, live.id])

        self.assertEqual(self.repository.get(live.id).status, 'processing')
        self.assertIn(live.id, self.storage.files)
        self.assertIn(live.id, self.admission.reserved)

        calls = []
        self.service.transcribe_queued_job(
            stale.id,
            SimpleNamespace(normalize=lambda source, destination: 1.0),
            SimpleNamespace(transcribe=lambda audio: calls.append(audio)),
        )
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
