import logging
import time
from typing import TYPE_CHECKING, BinaryIO

from transcriber.domain.job import Job, JobError
from transcriber.domain.ports import (
    AdmissionControl, MediaProcessor, MediaStorage, TaskDispatcher,
    TranscriptionEngine, WorkerHeartbeat,
)
from transcriber.domain.repositories.job_repository import JobRepository

if TYPE_CHECKING:
    from transcriber.config import Settings

log = logging.getLogger(__name__)


class TranscriptionService:
    def __init__(self, repository: JobRepository, storage: MediaStorage,
                 dispatcher: TaskDispatcher, admission: AdmissionControl,
                 heartbeat: WorkerHeartbeat, settings: "Settings"):
        self.repository, self.storage, self.dispatcher = repository, storage, dispatcher
        self.admission, self.heartbeat, self.settings = admission, heartbeat, settings
        self.uploading: set[str] = set()  # Single API process; protects active copies.

    def reserve(self, job_id: str) -> None:
        if not self.heartbeat.ready():
            raise JobError('unavailable', 'The worker is not ready. Please try again shortly.')
        if not self.admission.reserve(job_id, self.storage.free_bytes()):
            raise JobError('capacity', 'Upload capacity is full. Please try again later.')
        self.uploading.add(job_id)

    def cleanup(self, job_id: str) -> None:
        # Keep capacity charged if deleting files fails; maintenance retries.
        self.storage.delete(job_id)
        self.admission.release(job_id)

    def abandon(self, job_id: str) -> None:
        """Compensate only when a worker cannot own these files.

        A failed publication may have reached the broker. If Redis is unavailable,
        keep files/reservation for reconciliation instead of guessing ownership.
        """
        try:
            job = self.repository.get(job_id)
            if job is None or job.status in ('completed', 'failed'):
                self.cleanup(job_id)
            elif self.repository.fail(job_id, 'submission_failed',
                                      'The job could not be submitted. Please upload again.', 'queued'):
                self.cleanup(job_id)
        except Exception:
            log.warning('job=%s event=cleanup_deferred', job_id)

    def submit(self, job_id: str, source: BinaryIO) -> Job:
        self.storage.save(job_id, source, self.settings.max_upload_bytes)
        if not self.admission.renew(job_id, self.settings.queue_timeout + self.settings.cleanup_grace):
            raise JobError('upload_expired', 'The upload expired. Please upload again.')
        job = Job.new(job_id)
        self.repository.create(job)
        self.dispatcher.dispatch(job_id)
        return job

    def get(self, job_id: str) -> Job | None:
        return self.repository.get(job_id)

    def process(self, job_id: str, processor: MediaProcessor, engine: TranscriptionEngine) -> None:
        if not self.repository.claim(job_id):
            return
        log.info('job=%s event=claimed', job_id)
        try:
            if not self.admission.renew(job_id, self.settings.processing_timeout + self.settings.cleanup_grace):
                raise JobError('reservation_lost', 'Processing was interrupted. Please upload again.')
            self.repository.stage(job_id, 'decoding')
            duration = processor.normalize(self.storage.input_path(job_id), self.storage.audio_path(job_id))
            self.repository.stage(job_id, 'transcribing')
            text = engine.transcribe(self.storage.audio_path(job_id))
            self.repository.complete(job_id, text, duration)
            log.info('job=%s event=completed', job_id)
        except Exception as exc:
            error = exc if isinstance(exc, JobError) else JobError(
                'processing_failed', 'Processing failed or was interrupted. Please try again.')
            self.repository.fail(job_id, error.code, error.message, 'processing')
            log.warning('job=%s event=failed code=%s', job_id, error.code)
        finally:
            try:
                self.cleanup(job_id)
            except Exception:
                log.warning('job=%s event=cleanup_deferred', job_id)

    def reconcile(self) -> None:
        """Deadlines include hard task limit + grace; stale heartbeat alone is insufficient."""
        now, s = time.time(), self.settings
        for job in self.repository.active():
            if job.status == 'queued':
                expired = now > job.created_at + s.queue_timeout
            else:
                expired = (now > (job.started_at or now) + s.processing_timeout + s.cleanup_grace
                           and not self.heartbeat.job_alive(job.id))
            if expired and self.repository.fail(job.id, 'interrupted',
                                                'The job expired or was interrupted. Please upload again.', job.status):
                self.cleanup(job.id)
        for job_id in self.admission.expired():
            if job_id in self.uploading:
                continue
            job = self.repository.get(job_id)
            if job is None or job.status in ('completed', 'failed'):
                self.cleanup(job_id)
        # Also recover directories after Redis loss, conservatively after every
        # possible upload/queue/processing window; never delete a known active job.
        before = now - s.upload_timeout - s.queue_timeout - s.processing_timeout - s.cleanup_grace
        for job_id in self.storage.old_directories(before):
            if job_id not in self.uploading and not self.heartbeat.job_alive(job_id):
                job = self.repository.get(job_id)
                if job is None or job.status in ('completed', 'failed'):
                    self.cleanup(job_id)
