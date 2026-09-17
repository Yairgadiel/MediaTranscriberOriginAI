# Media Transcriber

An asynchronous, CPU-only English transcription service. Upload one audio or video file to receive a short-lived transcript. The API is public under `/api`; the in-progress Docker image is intended to serve the compiled browser UI from the same FastAPI process.

## Quick start

Docker Desktop or another Compose-compatible Docker engine is required. Allocate the stack the environment used for the benchmark: four CPUs and about 8 GiB of VM memory. That allocation is tested evidence for the benchmark environment, not a minimum system requirement.

```sh
docker compose up --build
```

Open <http://localhost:8000>. The worker downloads the public model to the `model-cache` volume on first use, so the first transcription takes longer. The service binds only to localhost and Redis is not published. A fresh final Compose build/startup smoke check is still pending; see [Known limitations](#known-limitations-and-future-work).

Copy `.env.example` to `.env` only to override limits. The supported Compose flow needs no host Python, Node, FFmpeg, GPU, Hugging Face token, or media download.

The optional frontend development server is configured to proxy `/api` to a backend at `127.0.0.1:8000`. Its dependency installation, typecheck, build, and tests remain unverified while the frontend work is reviewed.

## Use the API

The UI submits the same single public request. Submit a multipart file and retain the returned job ID or `status_url`:

```sh
curl -F 'file=@my-recording.mp3' http://localhost:8000/api/transcriptions
curl http://localhost:8000/api/transcriptions/JOB_ID
```

`POST /api/transcriptions` returns `202` with status `queued`. Poll `GET /api/transcriptions/{id}` until `completed` (with `text` and `duration_seconds`) or `failed` (with a safe error). An unknown or expired ID returns `404`; capacity returns `429`; an unavailable worker or state store returns `503`. `GET /health` is ready only when Redis, temporary storage, and a model-ready worker are available.

The in-progress React/TypeScript UI is designed to prevent duplicate uploads, retain a nonterminal job ID in browser localStorage, distinguish a temporary polling error from a failed transcription, explain a `404` as expiration/restart, and offer copy and text download after completion. Those browser behaviors have not yet been verified.

## Limits and configuration

Defaults are deliberately bounded:

| Limit or Compose override | Default | Meaning |
| --- | ---: | --- |
| `TRANSCRIBER_MAX_UPLOAD_BYTES` | 4 GiB | Maximum file bytes; the request allows a small multipart framing allowance |
| maximum duration | 3,600 seconds | Audio longer than one hour is rejected after media inspection |
| active jobs | 3 | Atomic Redis admission reservations, including disk margin |
| `TRANSCRIBER_PROCESSING_TIMEOUT` | 7,200 seconds | Per-job worker processing allowance |
| result TTL | 24 hours | Redis result retrieval window |
| `TRANSCRIBER_CLEANUP_GRACE` | 60 seconds | Extra time retained for cleanup/reconciliation deadlines |
| `TRANSCRIBER_WORKER_MAX_TASKS_PER_CHILD` | 5 jobs | Worker-child recycling threshold |

Compose reads these four optional overrides from `.env`; copy `.env.example` to `.env` to change them. Other `TRANSCRIBER_` settings in `src/transcriber/config.py` are runtime settings, but Compose does not pass them through as `.env` overrides. The API reserves capacity before parsing an upload, bounds both declared and streamed bodies, and validates/normalizes media with FFmpeg. It accepts WAV, MP3, M4A, MP4, and WebM only when the first audio stream uses a supported codec. Large high-bitrate video can exceed the byte limit even when shorter than an hour; extract or compress audio first.

## Architecture and lifecycle

The entrypoint layer contains FastAPI routes and thin Celery tasks. The application service coordinates business flow through domain contracts; infrastructure provides Redis repositories/admission/heartbeat, local shared-volume storage, Celery dispatch, FFmpeg processing, and faster-whisper inference. API startup does not import or load the model.

`upload → reserve capacity → temporary file → queued Redis record → Celery job ID → claim → FFmpeg WAV → transcription → completed/failed record → cleanup`

Only job IDs pass through Celery; media bytes stay in the shared `work` volume. The UI makes one upload-and-submit request rather than coordinating separate browser-side storage and job APIs.

| Production direction | Initial delivery | Cost of the local choice |
| --- | --- | --- |
| Blob storage | Shared Docker `work` volume behind `MediaStorage` | Workers must share one host volume |
| Direct client uploads | Multipart through the API | The API carries upload bandwidth, connections, and temporary disk use |
| Durable queue/recovery | Redis Celery broker, best-effort publication | No durable broker/recovery guarantee and no atomic job-record/task-publication guarantee |
| PostgreSQL job records | Temporary Redis records | Restart can lose job state and results |
| Transactional outbox | Explicit compensation after publication failure | An ambiguous publication can still require reconciliation |

## Model and measured evidence

- Model: `Systran/faster-whisper-base.en`, revision `3d3d5dee26484f91867d81cb899cfcf72b96be6c`, declared MIT license.
- Runtime measured: Python 3.11.13, faster-whisper 1.2.1, CTranslate2 4.6.0; native Linux ARM64 (Colima), four CPUs, approximately 8 GiB VM memory.
- Settings: CPU INT8, four threads, beam size 5, English, VAD enabled, and `condition_on_previous_text=False`.
- Supplied five-minute MP3 (model duration 300.0185 seconds): standalone first run 14.8165 s, warm run 14.3079 s; peak cgroup memory 940,720,128 bytes (about 897 MiB). Three warm application jobs were observed around 15.6 s; one first application job was about 101.9 s. These observations are not a performance guarantee.

## Temporary data and restarts

`work` contains upload and normalized-audio directories only while needed; ordinary success/failure cleanup removes them and releases admission capacity. `model-cache` retains downloaded weights as an optimization. Docker named volumes can outlive containers, but neither is durable user history. Do not delete volumes unless you intend to remove temporary media (`work`) or model cache (`model-cache`).

Redis persistence is explicitly disabled. Pending jobs and results can be lost or interrupted when Redis or the worker stack restarts; users may need to upload again. Celery acknowledges tasks early and does not automatically retry inference, so a worker crash can lose in-flight work. An API-only restart does not intentionally clear healthy worker state or shared files.

## Verification

Local backend verification used Python 3.11.15 provisioned by `uv`: locked imports for FastAPI, Celery, Redis, PyAV, faster-whisper, and the API entrypoint passed; the focused suite passed **17 tests** against a temporary no-persistence local Redis 8.10.1 instance and host FFmpeg (one upstream AnyIO deprecation warning). The frontend typecheck/build/tests and the final Docker checkpoint have not been run.

## Known limitations and future work

One-hour input support has **not** been verified with a user-provided one-hour recording. Intel/AMD64 behavior, accuracy/WER, silence/video/additional-format behavior beyond focused checks, native subprocess interruption, and worker memory/recycling under repeated jobs are unverified. The English base model, VAD, and disabled previous-text conditioning do not guarantee accurate or hallucination-free output. The Docker image's new frontend build path also awaits its first build/startup check.

The planned production phase adds PostgreSQL migrations, durable media, leases/retries/idempotent completion, recovery, and a transactional outbox. Authentication, cloud deployment, scaling, diarization, alignment, streaming, translation, and editing are intentionally out of scope.
