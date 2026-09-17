import logging
from transcriber.domain.models.transcription_job import Job, JobError

log = logging.getLogger(__name__)

class TranscriptionService:
    def __init__(self, repository, storage, dispatcher, admission, settings, processor=None, engine=None):
        self.repository, self.storage, self.dispatcher = repository, storage, dispatcher
        self.admission, self.settings = admission, settings
        self.processor, self.engine = processor, engine

    def submit(self, job_id, source):
        try:
            self.storage.save(job_id, source, self.settings.max_upload_bytes)
            if not self.admission.renew(job_id, self.settings.queue_timeout + self.settings.cleanup_grace):
                raise JobError('upload_expired', 'The upload reservation expired. Please upload again.')
            self.repository.create(Job.new(job_id))
            self.dispatcher.dispatch(job_id)
            return self.repository.get(job_id)
        except BaseException:
            # Publication may be ambiguous: CAS prevents an already-claimed job
            # being overwritten or its files deleted underneath its worker.
            job = self.repository.get(job_id)
            safe = job is None or self.repository.fail(job_id, 'publication_failed', 'The job could not be submitted. Please upload again.', 'queued')
            if safe:
                self.storage.delete(job_id)
                self.admission.release(job_id)
            raise

    def get(self, job_id):
        return self.repository.get(job_id)

    def process(self, job_id):
        if not self.repository.claim(job_id):
            return
        log.info('job=%s event=claimed', job_id)
        try:
            if not self.admission.renew(job_id, self.settings.processing_timeout + self.settings.cleanup_grace):
                raise JobError('reservation_lost', 'Processing was interrupted. Please upload again.')
            self.repository.stage(job_id, 'decoding')
            duration = self.processor.normalize(self.storage.input_path(job_id), self.storage.audio_path(job_id))
            self.repository.stage(job_id, 'transcribing')
            text = self.engine.transcribe(self.storage.audio_path(job_id))
            self.repository.complete(job_id, text, duration)
            log.info('job=%s event=completed', job_id)
        except JobError as exc:
            self.repository.fail(job_id, exc.code, exc.message, 'processing')
            log.info('job=%s event=failed code=%s', job_id, exc.code)
        except Exception:
            self.repository.fail(job_id, 'processing_failed', 'Processing failed or was interrupted. Please try again.', 'processing')
            log.error('job=%s event=processing_failed', job_id)
        finally:
            self.storage.delete(job_id)
            self.admission.release(job_id)
