"""HTTP boundary: bounded multipart parsing, schemas, and lifecycle wiring."""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from transcriber.bootstrap import Container
from transcriber.domain.job import Job, JobError

log = logging.getLogger(__name__)


class JobResponse(BaseModel):
    id: str
    status: str
    stage: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    expires_at: datetime | None
    duration_seconds: float | None
    text: str | None
    error: dict[str, str] | None
    status_url: str

    @classmethod
    def from_job(cls, job: Job):
        return cls(**job.as_dict(), status_url=f'/api/transcriptions/{job.id}')


def create_app(container=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.container = container or Container()

        async def maintain():
            while True:
                try:
                    await run_in_threadpool(app.state.container.service.reconcile)
                except Exception:
                    log.warning('event=maintenance_unavailable')
                await asyncio.sleep(5)

        task = asyncio.create_task(maintain())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            if container is None:
                app.state.container.redis.close()

    app = FastAPI(title='Media transcription', lifespan=lifespan)

    @app.exception_handler(RedisError)
    async def unavailable(request, exc):
        return JSONResponse({'detail': 'Job storage is unavailable. Please try again.'}, status_code=503)

    @app.get('/health')
    async def health(request: Request):
        c = request.app.state.container
        def check():
            try:
                return c.redis.ping() and c.storage.healthy() and c.heartbeat.ready()
            except Exception:
                return False
        healthy = await run_in_threadpool(check)
        return JSONResponse({'status': 'ready' if healthy else 'unavailable'}, status_code=200 if healthy else 503)

    @app.get('/api/transcriptions/{job_id}', response_model=JobResponse)
    async def get_job(job_id: str, request: Request):
        if len(job_id) != 32 or any(ch not in '0123456789abcdef' for ch in job_id):
            raise HTTPException(404, 'Unknown or expired job.')
        job = await run_in_threadpool(request.app.state.container.service.get, job_id)
        if job is None:
            raise HTTPException(404, 'Unknown or expired job.')
        return JobResponse.from_job(job)

    @app.post('/api/transcriptions', status_code=202, response_model=JobResponse)
    async def upload(request: Request):
        c = request.app.state.container
        service, s = c.service, c.settings
        job_id, accepted, reserved = uuid4().hex, False, False
        failure_status = 400
        form = parser = None
        try:
            # Admission happens before reading any body or creating parser spools.
            await run_in_threadpool(service.reserve, job_id)
            reserved = True
            if not request.headers.get('content-type', '').lower().startswith('multipart/form-data'):
                raise HTTPException(400, 'Send one multipart file field named file.')
            body_limit = s.max_upload_bytes + 65536  # Bounded multipart framing.
            length = request.headers.get('content-length')
            if length is not None:
                try:
                    declared = int(length)
                except ValueError:
                    raise HTTPException(400, 'Invalid Content-Length.')
                if declared < 0:
                    raise HTTPException(400, 'Invalid Content-Length.')
                if declared > body_limit:
                    raise HTTPException(413, 'The upload exceeds the size limit.')
            deadline, received = time.monotonic() + s.upload_timeout, 0

            async def bounded_stream():
                nonlocal failure_status, received
                while True:
                    try:
                        message = await asyncio.wait_for(request.receive(), max(0, deadline - time.monotonic()))
                    except TimeoutError:
                        failure_status = 408
                        raise MultiPartException('The upload timed out.')
                    if message['type'] == 'http.disconnect':
                        raise MultiPartException('Upload disconnected.')
                    chunk = message.get('body', b'')
                    received += len(chunk)
                    if received > body_limit:
                        failure_status = 413
                        # This exception makes Starlette close all partial spools.
                        raise MultiPartException('The upload exceeds the size limit.')
                    yield chunk
                    if not message.get('more_body', False):
                        break
                yield b''

            parser = MultiPartParser(request.headers, bounded_stream(), max_files=1, max_fields=0, max_part_size=65536)
            form = await parser.parse()
            file = form.get('file')
            if len(form) != 1 or not isinstance(file, UploadFile):
                raise HTTPException(400, 'Send exactly one file field named file.')
            if file.size is None or file.size > s.max_upload_bytes:
                raise HTTPException(413, 'The file exceeds the size limit.')
            job = await run_in_threadpool(service.submit, job_id, file.file)
            accepted = True
            return JobResponse.from_job(job)
        except MultiPartException as exc:
            raise HTTPException(failure_status, exc.message)
        except JobError as exc:
            status = {'capacity': 429, 'unavailable': 503, 'upload_too_large': 413,
                      'empty_upload': 400, 'upload_expired': 408}.get(exc.code, 503)
            raise HTTPException(status, {'code': exc.code, 'message': exc.message},
                                headers={'Retry-After': '5'} if status in (429, 503) else None)
        except HTTPException:
            raise
        except Exception:
            log.warning('job=%s event=submission_failed', job_id)
            raise HTTPException(503, 'The upload could not be submitted. Please try again.')
        finally:
            if form is not None:
                await form.close()
            elif parser is not None:
                # Starlette closes these on MultiPartException; also cover malformed
                # parser errors and cancellation. Kept here against our pinned version.
                for spool in parser._files_to_close_on_error:
                    spool.close()
            if reserved:
                if not accepted:
                    await run_in_threadpool(service.abandon, job_id)
                service.uploading.discard(job_id)

    # Docker copies the compiled React application here. API routes are registered
    # first so the catch-all static mount cannot shadow them during development.
    app.mount('/', StaticFiles(directory='backend/src/transcriber/entrypoints/static', html=True,
                               check_dir=False), name='web')
    return app


app = create_app()
