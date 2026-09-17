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
│       ├── bootstrap.py            # concrete dependency composition
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── job.py              # job entity, statuses, and domain errors
│       │   └── ports.py            # storage, engine, and dispatcher contracts
│       ├── application/
│       │   ├── __init__.py
│       │   └── transcription_service.py  # submit, retrieve, process, cleanup use cases
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   ├── celery_dispatcher.py      # Celery task publication
│       │   ├── ffmpeg_processor.py       # media probing and WAV normalization
│       │   ├── local_storage.py           # shared temporary-file storage
│       │   ├── process_launcher.py        # bounded subprocess execution
│       │   ├── redis_coordination.py     # admission and worker-heartbeat coordination
│       │   ├── whisper_engine.py          # faster-whisper CPU adapter
│       │   └── repositories/
│       │       ├── __init__.py
│       │       └── redis_job_repository.py # Redis JobRepository implementation
│       └── entrypoints/
│           ├── __init__.py
│           ├── api.py               # FastAPI HTTP app and public routes
│           └── worker.py            # Celery worker app and task entrypoint
└── tests/
    ├── conftest.py                 # Redis-backed test fixtures
    ├── test_backend.py             # API, repository, coordination, and lifecycle behavior
    ├── test_media.py               # media validation and normalization behavior
    └── unit/
        └── test_transcription_service.py # dependency-free service behavior tests
```

The dependency direction is `entrypoints → application → domain`; infrastructure implements
the domain contracts and is assembled by `bootstrap.py`. API routes and Celery tasks do not own
Redis or persistence logic.

From the repository root, run the focused backend tests with:

```sh
(cd backend && PYTHONPATH=src ../.venv/bin/python -m pytest tests/unit/test_transcription_service.py -q)
```
