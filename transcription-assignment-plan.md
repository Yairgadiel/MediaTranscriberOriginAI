# Media transcription assignment — implementation handoff

## 1. Context and objective

Build a service that accepts a media upload and returns a transcription. The employer requires an open-source model available on Hugging Face, production-minded code, explicit assumptions/trade-offs, and clear local build/run/test instructions. Docker delivery was explicitly mentioned.

Confirmed with the candidate:

- English speech; audio and video uploads.
- Recordings up to one hour.
- CPU only; no GPU requirement or dependency.
- Development machine: Apple M1 Pro, 32 GB RAM.
- Must be portable to other machines, including Intel Macs.
- Agreed direction: FastAPI, separate worker, asynchronous jobs, Docker Compose.
- Initial delivery does not require permanent storage, accounts, history, or restart recovery. A later production phase adds a relational database and explicit recovery semantics.
- Use the repository pattern, with interfaces and implementations clearly reflected in filenames and subdirectories.
- Frontend must use React and TypeScript, as explicitly requested by the candidate.
- Initialize a Git repository in the implementation workspace and make incremental, coherent commits throughout implementation.
- Separation of concerns is a core requirement: model/runtime, persistence, media storage, and task transport must be replaceable through explicit contracts without rewriting application business logic.
- This document is a plan; no implementation or benchmarks have been performed.

### Employer and role context (self-contained)

Both roles are at OriginAI in Ramat Gan. The postings describe an AI research organization working across computer vision, speech, and natural language processing. One describes national-scale research and access to advanced computing resources. That context makes model-to-service integration relevant, but does not override the confirmed CPU-only execution requirement.

The following details come from the postings reviewed during planning. They are context, not an employer-provided grading rubric. No role links are needed to use this handoff.

**Backend Developer (Python): customer-site integration and operations**

- An ownership-heavy position working at a strategic customer site, bridging internal engineering, customer development teams, and DevOps.
- Responsibilities include scalable backend microservices, investigating cross-service production issues, customer/external API integration, deployments and CI/CD, and contributing to unfamiliar codebases.
- Requests four or more years of Python experience, with FastAPI, Pydantic, and asynchronous programming.
- Names MongoDB/MongoEngine and query optimization; RabbitMQ/Celery and message-driven architecture; REST design and integration.
- Names Docker, Kubernetes/OpenShift, Helm charts, container debugging, Git workflows, and CI/CD.
- Asks for the ability to read and contribute to TypeScript/React codebases. React and TypeScript are also an explicit candidate requirement for this submission.
- Explicitly mentions responsible use of modern AI coding tools with full ownership of the resulting code.
- Nice-to-haves include FFmpeg/media processing, ML/AI pipelines, PyTorch, Triton, embeddings, LLM/NLP or agentic systems, Elasticsearch or Vespa, Jenkins, and customer-site experience.
- Emphasizes self-management, initiative, debugging/investigation, clear communication across teams, customer-facing technical discussions, and thinking beyond an individual component.
- Lists a computer science degree or military technology-unit background.

**Backend Software Developer: productionizing AI and inference workflows**

- A software-team role turning research capabilities into production deliverables, emphasizing architecture, efficiency, and maintainability.
- Responsibilities include distributed/event-driven backend services, APIs through deployment, asynchronous pipelines with queues/workers/object storage, and optimizing high-throughput data and inference flows.
- Also includes AI-agent orchestration, tool/function calling, memory, and integrating LLMs or other models into reliable workflows.
- Requests four to five years of backend experience and strong Python with FastAPI, Flask, or Django, including asyncio.
- Explicitly names PostgreSQL/SQLAlchemy, pytest, Docker, and microservices.
- Agent frameworks, tool/function calling, RAG, and LLM-powered applications are advantages.
- Includes proofs of concept, technology benchmarking, documentation, peer design/code reviews, and close collaboration with Product, Research, and engineering teams.
- Mentions participation in Scrum and lists a computer science degree or military technology-unit background.

**How this context should influence the submission**

| Role signal | Concrete implication for this assignment |
|---|---|
| Python APIs, Pydantic, asyncio | Typed HTTP contracts and validation; keep blocking decoding/inference off the API event loop. An async endpoint alone does not make CPU work nonblocking. |
| Queues, workers, inference pipelines | Demonstrate an actual worker boundary, bounded concurrency, understandable job states, and explicit delivery/failure semantics. |
| Object storage | Explain the shared-volume substitute, reference-only queue messages, and the later direct-to-blob upload design. |
| Relational databases and query optimization | Use an explicit repository contract and document the later PostgreSQL implementation, atomic state transitions, migrations, and necessary indexes. Do not add both MongoDB and PostgreSQL to match both postings. |
| Docker, deployments, customer integration | Make a clean checkout runnable, expose useful health checks, document configuration and portability, and provide actionable startup errors. |
| FFmpeg/media processing | Validate actual media, handle missing audio tracks, control subprocess/resource use, and clean temporary files. |
| Production troubleshooting | Correlate logs by job ID, distinguish decode/inference/infrastructure failures, and test interrupted work. Avoid logging full transcripts or media content. |
| Benchmarking and research integration | Record real quality/performance observations and distinguish verified results from assumptions. Encapsulate model inference behind a small adapter. |
| pytest and maintainability | Use focused service/repository tests plus real boundary tests; separate HTTP schemas, domain objects, persistence, and inference. |
| TypeScript/React familiarity | Deliver a focused React/TypeScript interface with typed API access and clear loading/error states; the framework does not replace backend consistency handling. |
| AI coding tools with ownership | Review generated code, understand its dependencies and failure modes, and be able to explain every architectural decision. |
| Communication and cross-team work | Write a README a reviewer can run without assistance, with clear limits, trade-offs, and troubleshooting guidance. |

Do not infer a requirement to deploy on AWS, use Kubernetes, add agents/RAG, or build a search system. An AWS production design is one illustrative deployment path; the customer-site role may involve other infrastructure. The initial delivery should demonstrate relevant engineering judgment without implementing every technology named in either posting.

## 2. Product scope and acceptance criteria

A user opens a simple page, selects an audio or video file, uploads it, sees an understandable processing state, and receives copyable English text. Failures must produce useful messages. Refreshing the page should allow resuming polling using a stored job ID while the service remains running.

Required submission:

- Real Hugging Face model inference, with CPU execution.
- Audio and video with an audio track; explicitly tested format list.
- One-hour recordings supported within a documented upload-size limit.
- Background worker; API remains responsive during inference.
- Temporary job status and transcript retrieval.
- Bounded upload size, duration, active jobs, inference concurrency, and processing time.
- Cleanup on ordinary success/failure and eventual cleanup of abandoned files.
- Unit/integration tests, a real-model smoke test, and a measured one-hour run.
- Reproducible Docker Compose startup and a README with measured limitations.

Out of scope: authentication, cloud deployment, Kubernetes, durable history, guaranteed job recovery, speaker diarization, word alignment, translation, streaming/live transcription, editing transcripts, arbitrary remote URL ingestion, and exactly-once processing.

Do not add those features simply because the job descriptions mention related technologies.

## 3. Architecture

```text
Browser -- upload / poll --> FastAPI -- task message --> Redis --> Celery worker
                              |                          |             |
                              +-- temporary job state --+-------------+
                              |                                        |
                              +------ shared temporary media ----------+
                                                                       |
                                                    FFmpeg + local ASR model
```

Three long-running Compose services: API, worker, Redis. One repository and preferably one application image, with different API/worker commands. Build the React/TypeScript frontend in a Node build stage and serve its compiled static assets from FastAPI. The supported Docker workflow needs neither host Node nor a separate frontend runtime service. Keep frontend source in its own `frontend/` directory.

Keep one public upload-and-submit endpoint in the initial delivery. The API stores the upload through `MediaStorage`, creates the job through `JobRepository`, and dispatches only the job ID. The worker resolves a trusted media reference; file bytes never travel through the broker. These are separate internal responsibilities, not separate browser-orchestrated API calls. Do not add public upload/finalize/create-job endpoints for this submission.

Production AWS mapping and the corresponding local substitutions must be explained explicitly in the README:

| Production design | Initial local substitute | Deliberate trade-off |
|---|---|---|
| S3/blob storage | Shared Docker volume behind `MediaStorage` | Simple single-host access; does not support workers on independent hosts |
| Direct client upload using a presigned URL | Multipart upload through the API | Simpler client workflow; API handles upload bandwidth, connections, and temporary disk use |
| SQS processing queue | Redis as Celery broker | Easy local startup; this configuration has no durable broker/recovery guarantee |
| PostgreSQL job repository | Temporary Redis job repository | No database setup initially; job history/results can be lost on restart |
| Transactional outbox and recovery workflow | Initial best-effort publication with explicit failure handling | No atomic guarantee across storing a job and publishing its task |

Direct-to-blob upload is a later production option, not a requirement imposed on the initial browser. It would require an upload-session/finalization protocol, reference validation, and abandoned-upload cleanup. The API can coordinate job creation after finalization; the browser need not manage queue or job-state internals. An S3-compatible local service is also deferred: it adds setup without being necessary to demonstrate this assignment's core flow.

Redis serves two distinct purposes: Celery message transport and short-lived application job records. Use an explicit job record so an unknown ID can be distinguished from a queued job. For the initial implementation, disable Celery result storage and make the application record the sole public status/result authority. Do not implement two competing state stores.

The initial phase uses a Redis implementation of the job repository, with no durable business-state guarantee. Disable Redis AOF/RDB persistence explicitly. A shared Docker volume is temporary working storage for the two containers, not a transcript archive. Model weights may be cached separately to avoid repeated downloads; this cache is an optimization, not user-data persistence. A later production phase replaces the job repository implementation with PostgreSQL; Redis remains the task broker and may retain ephemeral admission/heartbeat data.

Restart contract: pending jobs/results may be lost or interrupted; users may need to upload again. An API-only restart need not erase healthy worker state. Do not clear Redis or shared files indiscriminately at API startup.

## 4. First milestone: prove inference in Docker

Candidate: `Systran/faster-whisper-base.en`, using faster-whisper/CTranslate2 on CPU with INT8. Treat it as a benchmark candidate, not a settled quality/performance promise. Compare with `small.en` only if the first result warrants it and time permits.

Official runtime documentation shows CPU INT8 usage. CTranslate2 publishes platform support information, but dependency availability must be checked for the exact pinned Python/library versions on Linux ARM64 and AMD64. Do not force AMD64 emulation as the default on an M1 Mac.

Tasks:

1. Build a minimal native ARM64 image, initially using Python 3.11 slim and FFmpeg/ffprobe; adjust based on actual wheel support.
2. Verify model license and upstream provenance; record the Hugging Face repo and immutable revision. Do not assume all Hugging Face models are open source.
3. Download the pinned model into a cache, load on CPU, and fully consume the segment iterator on a real English recording.
4. Measure cold start separately from warm inference: download, load, elapsed transcription time, peak container memory, Docker CPU allocation, model configuration.
5. Evaluate basic readability on a short recording with known content; do not report word-error-rate without a reference transcript and calculation.
6. Run a representative full-hour recording early enough to change the design. Repeating a short fixture is useful for a resource test but is not a representative accuracy benchmark; label it accordingly.

Start with one model instance and four inference threads. Avoid batching initially. Load in the worker child process, not in the API or before a prefork. Reuse between tasks. Confirm the selected worker pool supports the timeout behavior we rely on.

Gate: no substantial UI or queue polish before a real containerized transcription works. If INT8 is unsupported on a target CPU, investigate supported compute types and document an explicit fallback. Do not silently introduce GPU or emulation dependencies.

References:
- https://github.com/SYSTRAN/faster-whisper
- https://huggingface.co/Systran/faster-whisper-base.en
- https://opennmt.net/CTranslate2/installation.html

## 5. Media pipeline and resource budget

Provisional configurable defaults (confirm by testing; these are design choices):

| Setting | Initial value | Purpose |
|---|---:|---|
| Maximum media duration | 3,600 seconds | Confirmed requirement |
| Maximum upload | 4 GiB, configurable | Agreed default supporting substantial compressed video; not every video bitrate |
| Outstanding admission slots | 3 | Includes uploading, queued, and processing work |
| Worker concurrency | 1 | One expensive inference at a time |
| CPU threads | 4 | Avoid saturating all host cores |
| Completed/failed result TTL | 24 hours | Temporary retrieval window |
| Browser polling | 2 seconds, backing off to 5 | Simple status updates |
| Upload deadline | 15 minutes | Release abandoned upload reservations |
| Processing deadline | Initially 2 hours | Revise from measured one-hour performance |

Do not confuse recording duration with processing duration. A 60-minute recording is not promised to finish in 60 minutes. Set queue deadlines to allow earlier admitted jobs to finish; a short fixed queue timeout must not reject legitimate wait time.

Upload handling:

- Acquire a bounded admission slot before accepting the body. One Uvicorn process is the baseline; use a Redis atomic reservation for slots and lease expiry rather than a racy read/increment pair.
- Enforce actual received bytes before multipart parsing can spool an unbounded file. Content-Length is an early check, not the sole enforcement. Use a tested ASGI body limiter or equivalent bounded parser path; return 413 and clean partial files.
- Limit multipart file/field counts. Account for parser spool space as well as the application's copied file; streaming application reads alone do not bound earlier parser spooling.
- Generate a server-side job ID and path. Never use the submitted filename as a filesystem path. Write `.part`, then atomically rename on successful upload.
- Do not trust extensions or MIME headers as evidence of valid media.

Worker validation and conversion:

- Probe with ffprobe under a timeout; require an audio track and an allowed media container/codec combination. Start by testing WAV, MP3, M4A, MP4, and WebM; advertise only tested formats.
- Select the first audio track and document that choice.
- Invoke FFmpeg with argument arrays, never shell interpolation. Restrict protocols to local inputs needed for supported files; reject playlists/remote references.
- Normalize to mono 16 kHz PCM on disk. Disable unnecessary video processing. Bound decoder execution and output duration; decode up to the maximum plus a small detection margin and reject overlong inputs rather than silently truncate.
- Verify decoded duration; metadata alone is insufficient. Handle missing or misleading duration metadata explicitly.
- One hour at 16 kHz mono float32 is about 220 MiB for the waveform alone. Model state, copies, features, decoder buffers, and the runtime add memory. Chunked inference does not prove bounded total memory.
- Prefer the library's supported long-form path if measurements fit the budget. Avoid custom overlapping chunk/stitch logic unless measurements show it is necessary.
- Treat silence/no detected speech as a completed result with an explanatory empty-text message, not a server exception.

Set container CPU/memory limits only after measuring headroom. Document a tested Docker Desktop allocation (initial experiment: 4 CPUs and 8 GiB available to the stack), not an unverified minimum. Check available disk before admission and bound total admitted media. Return a useful capacity error when resources are insufficient.

The 4 GiB file limit is an engineering default, not a measured requirement. Three admitted maximum-size files alone can occupy 12 GiB; account separately for multipart spooling, temporary copies, extracted audio, model cache, and a free-space margin. Reserve disk capacity atomically alongside admission slots so concurrent uploads cannot all rely on the same free-space check. Document how to configure the limit and explain that some high-bitrate videos need compression or audio extraction. Test the configured byte boundary without requiring a committed multi-gigabyte fixture.

## 6. API contract

| Endpoint | Behavior |
|---|---|
| `GET /` | Upload/status/result page |
| `POST /api/transcriptions` | Multipart upload; returns 202 with job ID and status URL after file storage and task publication |
| `GET /api/transcriptions/{id}` | Status, stage, timestamps, and transcript on success or safe error on failure |
| `GET /health` | Single service-health endpoint: 200 when Redis, working storage, and a ready worker/model are available; otherwise 503 |

Keep one public health endpoint; do not add separate liveness/readiness routes. Use bounded dependency checks and a fresh worker heartbeat/model-ready flag; never run inference or require an idle worker to answer health checks. A busy healthy worker remains healthy. Return a small status response without secrets or filesystem paths. Compose can use this endpoint; dependency failures should not trigger blind restart loops.

State sequence: `queued -> processing -> completed | failed`. Processing may expose stages `validating`, `decoding`, and `transcribing`. The browser has its own uploading state before it receives a job ID.

Do not fabricate a completion percentage or ETA. A processed-audio timestamp is optional and must be labelled as such, not wall-clock progress.

Status response fields: `id`, `status`, optional `stage`, `created_at`, `started_at`, `finished_at`, `expires_at`, `duration_seconds`, `text`, and an error object with a stable code and user-facing message. Use UTC timestamps. Do not expose local paths or tracebacks.

HTTP errors: malformed request 400/422, too large 413, capacity reached 429 with Retry-After, unavailable dependency/worker 503, unknown or expired ID 404. Media decoding/validation discovered after 202 becomes a failed job rather than an HTTP upload error. Explain this distinction in tests and docs.

If queue publication fails, release the slot and remove the upload; do not return 202. Broker acceptance and metadata updates are not a cross-system transaction. Document ambiguous publication failures and guard worker claims so a missing/failed job is not processed accidentally.

## 7. Temporary state, worker failures, and cleanup

Use Celery with concurrency one, prefetch multiplier one, JSON serialization, and explicit acknowledgement behavior. Prefer early acknowledgement for this submission and no automatic inference retries: a worker crash may lose a job, which fits the declared restart contract. Explain this trade-off. Do not imply durable or exactly-once processing.

Atomically claim `queued -> processing` in Redis; duplicate task delivery must not start the same job twice. Publish only a job ID; derive trusted paths on the worker. Heartbeat the worker and current job independently of blocking inference. Treat model-loading as not ready.

Maintain a small API lifecycle reconciliation loop (single API process baseline):

- Detect expired upload reservations and stale jobs using leases/heartbeats and configured deadlines.
- Mark interrupted jobs failed, making uncertainty explicit. A stale heartbeat alone must not delete files underneath an active process; coordinate cleanup with process termination or a conservative deadline/grace period.
- Release admission slots exactly once using atomic state transitions.
- Remove old `.part` files and orphan job directories after a conservative age threshold.
- Use only the dedicated work directory and generated IDs as deletion targets.

Ordinary worker success/failure uses `finally` cleanup for media and normalized files. Hard kills bypass `finally`; reconciliation is the fallback. Ensure soft/hard Celery time limits work with the pinned pool/version and terminate FFmpeg subprocesses; test rather than assume Python exception handling catches blocked native inference.

If Redis disappears, stop admitting uploads, show service unavailable, and let interrupted state expire/fail according to the restart contract. Do not continue expensive new jobs without state tracking.

Retain nonterminal records long enough for the full allowed queue/processing window. Apply the 24-hour result TTL after terminal completion. Never expire an active job merely because its creation-time result TTL elapsed.

Celery references:
- https://docs.celeryq.dev/en/stable/userguide/tasks.html
- https://docs.celeryq.dev/en/latest/getting-started/backends-and-brokers/redis.html

## 8. User interface

Plain accessible page: file picker, supported formats and limits, upload button, status text, elapsed waiting time, transcript area, and copy/download text controls. Show the one-hour and upload-size limits before submission.

Implement the UI in React and TypeScript with a lightweight build setup such as Vite. The client makes one multipart upload-and-submit request, receives a job ID, then polls. Backend application services coordinate storage, job creation, dispatch, and compensation on failure. Do not require the browser to chain a separate upload endpoint and transcription-creation endpoint.

Separate typed API access, polling/lifecycle logic, and presentation components. Use a small hook for submission/status state; cancel outstanding requests and polling timers on unmount or job change, prevent overlapping polls, and stop polling on terminal states. Keep state local; no global state library is required. Type API responses consistently with the backend schemas and check error responses explicitly. Use same-origin `/api` calls in Docker; an optional frontend development server may proxy those calls to FastAPI.

Verify the TypeScript check and production build. Add focused component/hook tests for submission, terminal-state polling cessation, and recoverable polling errors using mocked HTTP responses; backend tests cover actual job processing. Pin frontend dependencies in a lockfile.

Prevent duplicate submission while uploading. Store the active job ID in browser localStorage; offer a clear reset/new-upload action. On polling errors distinguish a temporary network problem from a failed transcription. On 404 explain that the result may have expired or the service restarted. Render filenames and transcript as text, never raw HTML.

Keep model configuration, broker details, and container internals in documentation rather than the normal user flow. Use simple CSS and accessible controls; no elaborate design system is required.

## 9. Repository pattern and project structure

```text
README.md
Dockerfile
compose.yaml
.env.example
.dockerignore
pyproject.toml
<dependency lockfile>
frontend/
  package.json
  <frontend lockfile>
  tsconfig.json
  vite.config.ts
  index.html
  src/
    main.tsx
    App.tsx
    api/
      transcriptions.ts
      types.ts
    hooks/
      useTranscription.ts
    components/
      UploadForm.tsx
      JobStatus.tsx
      TranscriptResult.tsx
    styles.css
  tests/
    useTranscription.test.tsx
src/transcriber/
  config.py
  bootstrap.py                 # dependency construction / composition root
  domain/
    models/
      transcription_job.py     # job entity, status enum, domain errors
    repositories/
      job_repository.py        # JobRepository protocol
    ports/
      media_storage.py         # file access contract
      transcription_engine.py  # inference contract
      task_dispatcher.py       # dispatch-by-job-ID contract
  application/
    services/
      transcription_service.py # submit, retrieve, process use cases
      maintenance_service.py   # reconciliation and cleanup orchestration
  infrastructure/
    repositories/
      redis_job_repository.py  # initial JobRepository implementation
    coordination/
      redis_admission_control.py
      redis_worker_heartbeat.py
    storage/
      local_media_storage.py
    media/
      ffmpeg_media_processor.py
    inference/
      faster_whisper_engine.py
    messaging/
      celery_app.py
      celery_task_dispatcher.py
  entrypoints/
    api/
      app.py
      dependencies.py
      routes/
        transcriptions.py
        health.py
      schemas/
        transcription.py        # HTTP request/response models
      middleware/
        upload_limit.py
      static/                   # compiled frontend assets copied during image build
    worker/
      tasks.py                  # thin Celery task entrypoints
      lifecycle.py              # model initialization and heartbeat
    maintenance/
      runner.py                 # API lifecycle hook for maintenance service
tests/
  unit/
  integration/
    repositories/
      test_job_repository_contract.py
      test_redis_job_repository.py
  fakes/
    in_memory_job_repository.py
  fixtures/           # tiny synthetic/permitted media only
scripts/
  benchmark.py
```

Dependency direction: entrypoints call application services; services depend on domain models and contracts; infrastructure implements those contracts. Wire concrete implementations in bootstrap/dependency factories. API routes and Celery tasks must not execute Redis commands or contain persistence logic. Keep ML imports/model loading out of API startup.

Define `TranscriptionEngine`, `JobRepository`, `MediaStorage`, and `TaskDispatcher` contracts explicitly. Keep model-specific options/results, Redis representations, ORM entities, Celery task objects, and storage-provider SDK objects inside their adapters. Application services consume domain-level inputs/results and errors. Model/runtime replacement should require a new adapter and configuration, not edits to job orchestration. Persistence replacement should preserve the repository's atomic-transition contract. Test substitutability using contract tests and fakes where useful.

Do not equate adapter replacement with identical capabilities or automatic migration. Model language/format capabilities must be explicit; database migration and recovery semantics need deliberate implementation; direct-to-blob uploads change the public upload protocol. Keep these concerns visible while preventing infrastructure details from spreading into business logic. Avoid speculative frameworks or a generic lowest-common-denominator API.

`JobRepository` exposes business operations such as create, get, claim queued work, complete, fail, and find stale jobs. Specify expected-state checks and atomic transitions in the contract; a generic CRUD interface would hide the concurrency requirements. Return domain objects, not Redis hashes or future ORM entities. Keep capacity reservations and worker heartbeats in dedicated coordination components rather than disguising them as job persistence.

Use an in-memory fake for service tests and a shared repository contract suite for real implementations. The fake does not establish Redis concurrency correctness; integration tests must cover that. Do not introduce a generic base repository, speculative transaction framework, or unused implementation. Add package initializers as required by the selected packaging setup.

### Later production phase: durable job storage

Add PostgreSQL through SQLAlchemy and Alembic when implementing durable history and recovery. Planned additions:

```text
src/transcriber/infrastructure/
  repositories/
    postgres_job_repository.py
  database/
    session.py
    models/
      transcription_job.py
migrations/
tests/integration/repositories/
  test_postgres_job_repository.py
```

Store job lifecycle, timestamps, media references, transcript, and safe failure details in PostgreSQL. Keep media outside the database. Replace the injected repository without changing HTTP contracts or leaking SQLAlchemy into application services. Use conditional updates/transactions to preserve the repository's state-transition guarantees.

A database alone does not provide reliable job execution. This phase must also define durable media storage, worker ownership/leases, retry policy, idempotent completion, and recovery of interrupted jobs. Address the database-commit/task-publication gap with a transactional outbox and dispatcher, or another explicitly justified recovery mechanism. Revisit early acknowledgements deliberately; do not merely enable retries and claim recovery is solved.

Test migrations, repository contract parity, duplicate delivery, and crashes between commit/publication and processing/completion. Retention still applies: production durability does not mean keeping uploads and transcripts forever. This is a planned extension, not a prerequisite for the initial working submission.

## 10. Docker and reproducibility

- Compose must support `docker compose up --build` with no required secret or HF token for the selected public model.
- Build React/TypeScript using a pinned Node build stage and the frontend lockfile; copy only compiled assets into the application runtime image. Document optional frontend development commands separately from the Docker quick start.
- Pin application dependencies and model revision. Select versioned base/service images and document the tested versions.
- Download weights at first startup into a model cache, with visible logs and readiness reflecting loading. Keep downloads out of ordinary unit tests.
- Run application processes as non-root with correctly owned work/cache paths.
- Bind the web port to localhost by default; do not publish Redis externally.
- Support native `linux/arm64` and `linux/amd64`. Verify builds on both when possible and a real smoke test on available hardware. An emulated AMD64 build is not an Intel performance test.
- Include health checks, predictable startup ordering, explicit Redis no-persistence configuration, and reasonable stop grace periods.
- Document that shared work files/cache volumes can survive container removal even though jobs have no durability guarantee. Provide explicit cleanup commands and distinguish deleting cache from deleting temporary user media.
- Avoid CUDA, MPS, host Python, or host FFmpeg requirements in the supported Docker path.

## 11. Verification plan

Automated unit/API tests use a fake engine; integration tests exercise real Redis/Celery and FFmpeg without repeatedly downloading a model.

Priority cases:

1. Successful upload -> queued -> processing -> text; real worker boundary covered.
2. Unknown job returns 404 rather than indefinite queued status.
3. Oversized body rejected even without trustworthy Content-Length; partial files removed.
4. Three concurrent reservations accepted; additional admission rejected atomically; slots released after errors.
5. Corrupt media, video without audio, overlong media, and conversion timeout produce stable error codes.
6. Exactly one hour accepted; over-limit decoded audio rejected, including misleading metadata scenarios.
7. Engine exception and normal success both clean files and release capacity.
8. Duplicate task delivery cannot run a completed/already-claimed job again.
9. Queue publication failure does not leave an accepted-but-invisible upload.
10. Worker termination/time limit eventually becomes visible failure with reclaimed resources.
11. Result expiry, browser refresh, and Redis unavailability behave as documented.
12. Malicious filenames cannot escape storage; transcript markup renders as text.

Real-model checks: short English audio, video with speech, silence, and a full-hour workload. Confirm actual text manually; avoid brittle exact-output assertions for model inference.

Measure wall time, peak memory, CPU allocation, model/revision/compute type, media duration, and cold/warm status. Calculate real-time factor = processing seconds / audio seconds. Report actual results; do not extrapolate a short run as proof of full-hour support.

Final verification: fresh checkout/startup, documented test command, clean browser walkthrough, responsive health/status requests during inference, and review logs for accidental transcript/token leakage.

## 12. Delivery phases and scope control

| Phase | Outcome |
|---|---|
| 1. Inference proof | Native Docker inference spike, model/license/dependency choice; start long benchmark |
| 2. Vertical slice | Repository contract and Redis implementation; upload -> worker -> result |
| 3. Reliability | Resource bounds, media validation, temporary state/cleanup, failure behavior |
| 4. User experience | Minimal UI and user-facing errors |
| 5. Verification | Integration tests, crash/time-limit checks, full-length recording measurements |
| 6. Initial delivery | README, clean startup, cross-architecture build check where available, final review |
| 7. Production extension | PostgreSQL repository, migrations, durable media, publication/recovery semantics |

Complete phases in dependency order. If scope needs reducing, cut UI polish, optional progress, and model comparisons first. Preserve the working Docker path, full-length recording evidence, basic error handling, resource bounds, and honest documentation. Deliver the initial service before beginning the production extension; do not present the initial ephemeral design as a fully durable production system.

### Git workflow

Create the Git repository in the new implementation workspace before making application changes, unless that workspace already belongs to a repository. Inspect existing state first and preserve unrelated user changes. This planning workspace is not the target application repository.

Create `.gitignore` early. Exclude environment secrets, uploaded media, transcripts, model weights/cache, temporary files, local volumes, Python environments, node_modules, build output, and test caches. Commit source, dependency lockfiles, migrations when introduced, `.env.example` with nonsecret defaults, and small permitted test fixtures.

Commit periodically at coherent milestones rather than accumulating the entire project into one commit. Suggested boundaries: scaffold/tooling; verified inference adapter; repository and worker vertical slice; resource/error handling; React/TypeScript UI; tests and delivery documentation. Split or combine these according to actual implementation progress. Run the checks relevant to each change, inspect the staged diff, and use concise messages describing the result. Stage task-related files explicitly; do not blindly include unrelated changes or large generated assets.

Keep commits runnable where practical. If an intermediate checkpoint is incomplete, say so clearly in its commit message; never imply unrun checks passed. Continue normal implementation without requesting approval for each local commit. Do not create a remote repository, push, or publish unless separately requested. Finish by checking repository status and reporting the latest commit and any intentionally uncommitted changes.

## 13. README and interview preparation

README order:

1. What the product does and supported input limits.
2. Exact prerequisites, startup command, first-download expectations, URL.
3. User walkthrough and curl upload/poll examples.
4. Exact automated-test and opt-in real-model-test commands.
5. Compact architecture and job lifecycle.
6. Model/revision/license, configuration, measured performance and hardware.
7. Temporary storage, expiry, cleanup, and restart behavior.
8. Trade-offs and known limitations.
9. Short future-work section.

Key trade-offs to explain: asynchronous jobs for long CPU work; one worker to control resources; Redis instead of a relational database for ephemeral state; shared files for a single Docker host; English model selection; quality versus latency; early acknowledgement and explicit lack of durable recovery; size limits that exclude some high-bitrate video; local-only deployment without accounts.

The infrastructure substitution table in section 3 is required README content, adapted to what was actually implemented. Explain specifically why uploads pass through the local API instead of going directly to blob storage, why one public submission endpoint avoids extra client coordination, and how storage/queue interfaces preserve internal boundaries. Describe the costs honestly: API upload load, single-host storage, ephemeral state, and the publication consistency gap. These are central architectural trade-offs, not incidental setup notes. Do not imply that swapping an adapter alone delivers production durability, direct uploads, or recovery.

Future work should distinguish the explicitly planned PostgreSQL/recovery phase from optional authentication and worker scaling. Explain which guarantees the initial submission provides and which belong to the production extension.

## 14. Prompt for the implementation chat

Read this plan fully and implement the initial delivery phases in this workspace. Treat the confirmed requirements and agreed scope as authoritative. Initialize Git if needed and make coherent milestone commits throughout the work, following the Git workflow above. Start with the CPU-only native Docker inference benchmark, then implement a working vertical slice before adding polish. Use the repository pattern and the explicit domain/application/infrastructure/entrypoint structure. Verify exact dependency/model compatibility and pin the versions you actually test. Use the Redis job repository initially; preserve the documented PostgreSQL production phase without implementing it as a prerequisite for delivery. Use measured results to choose the model, memory limits, and timeouts. Make routine implementation decisions autonomously, documenting departures from provisional choices. Do not claim Intel compatibility, performance, or tests that were not actually verified. Finish with a usable Docker submission, focused tests, a thorough README, and explicit remaining limitations. Present work as phases without effort estimates or delivery-hour budgets.
