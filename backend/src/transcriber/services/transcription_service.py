import logging
import time
from typing import TYPE_CHECKING, BinaryIO

from transcriber.domain.models.job import Job, JobError
from transcriber.domain.contracts import (
    AdmissionControl, MediaProcessor, MediaStorage, TaskDispatcher,
    TranscriptionEngine, WorkerHeartbeat,
)
from transcriber.domain.repositories.job_repository import JobRepository
from transcriber.adapters.celery_dispatcher import TransientPublicationError
from transcriber.adapters.ffmpeg_processor import TransientDecoderStartError
from transcriber.services.retry_policy import retry_transient

if TYPE_CHECKING:
    from transcriber.config import Settings

log = logging.getLogger(__name__)


class TranscriptionService:
    def __init__(self, repository: JobRepository, storage: MediaStorage,
                 dispatcher: TaskDispatcher, admission: AdmissionControl,
                 heartbeat: WorkerHeartbeat, settings: "Settings",
                 uploading: set[str] | None = None):
        self.repository, self.storage, self.dispatcher = repository, storage, dispatcher
        self.admission, self.heartbeat, self.settings = admission, heartbeat, settings
        self.uploading = uploading if uploading is not None else set()  # Single API process; protects active copies.

    def reserve_upload_capacity(self, job_id: str) -> None:
        if not self.heartbeat.ready():
            raise JobError('unavailable', 'The worker is not ready. Please try again shortly.')
        if not self.admission.reserve(job_id, self.storage.free_bytes()):
            raise JobError('capacity', 'Upload capacity is full. Please try again later.')
        self.uploading.add(job_id)

    def cleanup_job_resources(self, job_id: str) -> None:
        # Keep capacity charged if deleting files fails; maintenance retries.
        self.storage.delete(job_id)
        self.admission.release(job_id)

    def compensate_failed_submission(self, job_id: str) -> None:
        """Compensate only when a worker cannot own these files.

        A failed publication may have reached the broker. If Redis is unavailable,
        keep files/reservation for reconciliation instead of guessing ownership.
        """
        try:
            job = self.repository.get(job_id)
            if job is None or job.status in ('completed', 'failed'):
                self.cleanup_job_resources(job_id)
            elif self.repository.fail(job_id, 'submission_failed',
                                      'The job could not be submitted. Please upload again.', 'queued'):
                self.cleanup_job_resources(job_id)
        except Exception:
            log.warning('job=%s event=cleanup_deferred', job_id)

    def fail_unclaimed_job(self, job_id: str, code: str, message: str) -> None:
        """Fail and clean only a still-queued job; a duplicate may already own it."""
        try:
            if self.repository.fail(job_id, code, message, 'queued'):
                self.cleanup_job_resources(job_id)
        except Exception:
            log.warning('job=%s event=cleanup_deferred', job_id)

    def store_and_enqueue(self, job_id: str, source: BinaryIO) -> Job:
        self.storage.save(job_id, source, self.settings.max_upload_bytes)
        if not self.admission.renew(job_id, self.settings.queue_timeout + self.settings.cleanup_grace):
            raise JobError('upload_expired', 'The upload expired. Please upload again.')
        job = Job.new(job_id)
        self.repository.create(job)
        retry_transient(
            lambda: self.dispatcher.dispatch(job_id), retryable=lambda exc: isinstance(exc, TransientPublicationError),
            job_id=job_id, event='task_publication', max_attempts=self.settings.retry_max_attempts,
            delay=self.settings.retry_delay_seconds, max_delay=self.settings.retry_max_delay_seconds,
        )
        return job

    def find_job(self, job_id: str) -> Job | None:
        return self.repository.get(job_id)

    def transcribe_queued_job(self, job_id: str, processor: MediaProcessor, engine: TranscriptionEngine) -> None:
        if not self.repository.claim(job_id):
            return
        log.info('job=%s event=claimed', job_id)
        try:
            if not self.admission.renew(job_id, self.settings.processing_timeout + self.settings.cleanup_grace):
                raise JobError('reservation_lost', 'Processing was interrupted. Please upload again.')
            self.repository.stage(job_id, 'decoding')
            # Only launch/resource failures retry, and never more than once. Validation,
            # decoding timeouts, and all inference failures stay terminal on first failure.
            duration = retry_transient(
                lambda: processor.normalize(self.storage.input_path(job_id), self.storage.audio_path(job_id)),
                retryable=lambda exc: isinstance(exc, TransientDecoderStartError), job_id=job_id,
                event='decoder_start', max_attempts=min(2, self.settings.retry_max_attempts),
                delay=self.settings.retry_delay_seconds, max_delay=self.settings.retry_max_delay_seconds,
            )
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
                self.cleanup_job_resources(job_id)
            except Exception:
                log.warning('job=%s event=cleanup_deferred', job_id)

    def reconcile_expired_work(self) -> None:
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
                self.cleanup_job_resources(job.id)
        for job_id in self.admission.expired():
            if job_id in self.uploading:
                continue
            job = self.repository.get(job_id)
            if job is None or job.status in ('completed', 'failed'):
                self.cleanup_job_resources(job_id)
        # Also recover directories after Redis loss, conservatively after every
        # possible upload/queue/processing window; never delete a known active job.
        before = now - s.upload_timeout - s.queue_timeout - s.processing_timeout - s.cleanup_grace
        for job_id in self.storage.old_directories(before):
            if job_id not in self.uploading and not self.heartbeat.job_alive(job_id):
                job = self.repository.get(job_id)
                if job is None or job.status in ('completed', 'failed'):
                    self.cleanup_job_resources(job_id)
