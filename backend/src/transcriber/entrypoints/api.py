"""HTTP boundary: bounded multipart parsing, schemas, and lifecycle wiring."""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from transcriber.dependencies import create_transcription_service, get_transcription_service
from transcriber.domain.models.job import JobError

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name('static')


from transcriber.entrypoints.schemas import JobResponse


def create_app(service=None):
    @asynccontextmanager
    async def lifespan(app):
        runtime_service = service or create_transcription_service()
        app.state.service = runtime_service

        async def maintain():
            while True:
                try:
                    await run_in_threadpool(runtime_service.reconcile_expired_work)
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
            if service is None:
                runtime_service.repository.client.close()

    app = FastAPI(title='Media transcription', lifespan=lifespan)
    if service is not None:  # Explicit test seam; production uses the providers above.
        app.dependency_overrides[get_transcription_service] = lambda: service

    @app.exception_handler(RedisError)
    async def unavailable(request, exc):
        return JSONResponse({'detail': 'Job storage is unavailable. Please try again.'}, status_code=503)

    @app.get('/health')
    async def health(request: Request):
        def check():
            try:
                service = request.app.state.service
                return (service.repository.client.ping() and service.storage.healthy()
                        and service.heartbeat.ready())
            except Exception:
                return False
        healthy = await run_in_threadpool(check)
        return JSONResponse({'status': 'ready' if healthy else 'unavailable'}, status_code=200 if healthy else 503)

    @app.get('/api/transcriptions/{job_id}', response_model=JobResponse)
    async def get_job(job_id: str, service = Depends(get_transcription_service)):
        if len(job_id) != 32 or any(ch not in '0123456789abcdef' for ch in job_id):
            raise HTTPException(404, 'Unknown or expired job.')
        job = await run_in_threadpool(service.find_job, job_id)
        if job is None:
            raise HTTPException(404, 'Unknown or expired job.')
        return JobResponse.from_job(job)

    @app.post('/api/transcriptions', status_code=202, response_model=JobResponse)
    async def upload(request: Request, service = Depends(get_transcription_service)):
        s = service.settings
        job_id, accepted, reserved = uuid4().hex, False, False
        failure_status = 400
        form = parser = None
        try:
            # Admission happens before reading any body or creating parser spools.
            await run_in_threadpool(service.reserve_upload_capacity, job_id)
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
            # The bounded request stream and LocalMediaStorage enforce the actual
            # byte limit. Starlette may not know a part's size on every parser path.
            if file.size is not None and file.size > s.max_upload_bytes:
                raise HTTPException(413, 'The file exceeds the size limit.')
            job = await run_in_threadpool(service.store_and_enqueue, job_id, file.file)
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
                    await run_in_threadpool(service.compensate_failed_submission, job_id)
                service.uploading.discard(job_id)

    # Docker copies the compiled React application here. API routes are registered
    # first so the catch-all static mount cannot shadow them during development.
    app.mount('/', StaticFiles(directory=STATIC_DIR, html=True,
                               check_dir=False), name='web')
    return app


app = create_app()
