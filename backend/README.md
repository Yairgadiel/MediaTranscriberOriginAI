# Backend

The backend is the Python project boundary. Run Python commands from this directory unless a
command says otherwise. The package is installed from `src/`, and the runtime imports it as
`transcriber`.

## Exact structure

```text
backend/
├── pyproject.toml                 # setuptools metadata and pytest configuration
├── requirements.lock              # pinned runtime and test dependencies
├── README.md                      # this guide
├── src/
│   └── transcriber/
│       ├── __init__.py
│       ├── config.py               # environment-backed application settings
│       ├── dependencies.py         # concrete dependency composition
│       ├── domain/
│       │   ├── models/job.py        # Pydantic job model, statuses, and domain errors
│       │   ├── contracts.py         # explicit storage, engine, dispatcher, and Redis-client interfaces
│       │   └── repositories/job_repository.py # JobRepository interface
│       ├── services/
│       │   ├── retry_policy.py           # bounded exponential retry helper
│       │   └── transcription_service.py  # named submission, retrieval, processing, cleanup use cases
│       ├── adapters/
│       │   ├── celery_dispatcher.py      # Celery task publication
│       │   ├── redis_client.py            # Redis admission and heartbeat adapters
│       │   ├── redis_job_repository.py    # Redis JobRepository implementation
│       │   ├── ffmpeg_processor.py       # media probing and WAV normalization
│       │   ├── local_storage.py           # shared temporary-file storage
│       │   ├── process_launcher.py        # bounded subprocess execution
│       │   └── whisper_engine.py          # faster-whisper CPU adapter
│       └── entrypoints/
│           ├── __init__.py
│           ├── api.py               # FastAPI HTTP app, Depends wiring, and public routes
│           ├── schemas.py           # Pydantic HTTP response schemas
│           └── worker.py            # Celery worker app and task entrypoint
└── tests/
    ├── conftest.py                 # Redis-backed test fixtures
    ├── test_backend.py             # API, repository, coordination, and lifecycle behavior
    ├── test_media.py               # media validation and normalization behavior
    └── unit/
        └── test_transcription_service.py # dependency-free service behavior tests
```

The dependency direction is `entrypoints → services → domain`; adapters explicitly implement
the domain interfaces and `dependencies.py` declares the concrete factories. `ports` was renamed
to `contracts`: these are simply interfaces describing what the service needs. FastAPI resolves
the graph as `settings → Redis client → repository/storage/dispatcher/admission/heartbeat →
TranscriptionService` through `Depends`. Routes do not construct or locate dependencies.

`JobRepository` is defined in `domain/repositories/job_repository.py`; its current dedicated
implementation is `adapters/redis_job_repository.py`. Redis is not a service
requirement: it is the selected implementation for temporary job records, admission leases, and
worker heartbeats. Celery also currently uses Redis as its broker. A different implementation can
replace those injected contracts without changing the transcription service.

`entrypoints/worker.py` is intentionally small: it is the Celery process entrypoint. It creates
the worker service after forking, loads FFmpeg/faster-whisper outside the API process, reports
model readiness, and passes each opaque job ID to `transcribe_queued_job`.

Retry behavior is deliberately narrow: broker publication and model-cache/readiness transport
failures may make at most three exponentially backed-off attempts, while decoder process-start
resource failures get one retry. Invalid media, decode timeouts, out-of-memory or deterministic
runtime failures, and anything after transcription starts fail immediately. Conditional Redis
state transitions keep ambiguous publication and duplicate delivery from deleting or processing
an already-claimed job.

From the repository root, run the focused backend tests with:

```sh
(cd backend && PYTHONPATH=src ../.venv/bin/python -m pytest tests/unit/test_transcription_service.py -q)
```
