# Implementation checklist and conversation handoff

Last updated: 2026-09-17. This file is the ongoing execution log; the authoritative
requirements remain in `../transcription-assignment-plan.md`.

## How to use this log

- [x] Use `[x]` only for an action actually completed, with its evidence or limitation.
- [ ] In each future conversation, read this file and the relevant plan sections first.
- [ ] Update this checklist as work happens: changed files, commands/checks, actual outcomes,
      decisions, limitations, and the next concrete task. Do not mark authored code as tested.
- [ ] Keep work divided into phases and milestone commits; no effort estimates.
- [x] Stop implementation at the user's request. This conversation's final scope is to
      record evidence and checkpoint existing work; remaining implementation belongs to
      separate conversations.
- [x] Record user steering: keep token use and tool output concise; do not independently
      search for or download audio. Use user-provided recordings. Make routine decisions
      autonomously; tool-enforced sandbox approvals may still be necessary.

## Current state — read before resuming

- [x] A standalone native Docker inference benchmark **has run successfully** using a
      real Hugging Face model and the user's `sample-speech-5m.mp3`.
- [x] Backend source **has been written**, after the first successful benchmark run.
      It is an incomplete, untested scaffold, not a working vertical slice.
- [x] Only Python syntax compilation was run on that scaffold. No application imports,
      unit tests, Redis integration, Celery integration, HTTP flow, or frontend tests ran.
- [ ] Deliver a usable application: there is currently **no API, frontend, root Dockerfile,
      Compose file, maintenance loop, test suite, or root README**.
- [ ] Finish the root dependency lock. `pyproject.toml` references `requirements.lock`,
      which does not yet exist. `requirements.in` is only an uninstalled candidate list.
- [x] Preserve media/transcripts locally and exclude them from Git and Docker build context.

## Phase 0 — workspace, tools, and Git

- [x] Read the full handoff plan, including sections initially truncated in tool output.
- [x] Inspect workspace: initially only `transcription-assignment-plan.md`; no Git repository.
- [x] Initialize Git on branch `main`.
- [x] Add `.gitignore` for secrets, media, transcripts/local benchmark output, model caches,
      Python environments, build output, and Node/test caches.
- [x] Add `.dockerignore`; later extend it to keep supplied media out of build contexts.
- [x] Commit `bc4aa9d`: plan, ignore rules, initial evidence log.
- [x] Commit `a8cbebf`: benchmark harness checkpoint, explicitly runtime validation pending.
- [x] Inspect host: Apple M1 Pro, ARM64, 10 CPU cores, 32 GiB RAM. About 36 GiB host disk
      space was free at setup time; that is a snapshot, not a guaranteed current value.
- [x] Find no installed Docker runtime. Install through Homebrew, with tool approvals:
      Colima 0.10.3, Docker CLI 29.8.1, Docker Compose 5.5.1, Buildx 0.37.1;
      Lima 2.2.0 installed as a dependency. Homebrew also auto-updated its metadata/runtime.
- [x] Start Colima using `colima start --cpu 4 --memory 8 --disk 60 --arch aarch64 --vm-type vz`.
      The virtual disk setting is 60 GiB, not a reservation of that much free host space.
- [x] Verify Docker server 29.5.2 reports `aarch64`, 4 CPUs, and 8,307,105,792 memory bytes.
      Docker context is now `colima`. This is native ARM64 execution, not AMD64 emulation.
- [x] Record departure: Colima replaces the plan's provisional Docker Desktop environment.
- [ ] Verify `docker compose` / `docker buildx` plugin discovery. Homebrew installed them,
      but its suggested `cliPluginsExtraDirs` configuration was not applied. The benchmark
      used Docker's legacy builder successfully; no Compose command has run.
- [x] Inspect running containers at handoff: none. The benchmark container is retained in
      exited state. Colima VM remains running; it was not stopped or deleted.

## Phase 1 — real CPU inference proof

### Model, dependencies, and harness

- [x] Read official faster-whisper, Hugging Face model-card, and CTranslate2 installation
      documentation. Sources:
      <https://github.com/SYSTRAN/faster-whisper>,
      <https://huggingface.co/Systran/faster-whisper-base.en>,
      <https://opennmt.net/CTranslate2/installation.html>.
- [x] Query Hugging Face metadata: `Systran/faster-whisper-base.en`, immutable revision
      `3d3d5dee26484f91867d81cb899cfcf72b96be6c`, declared license MIT. The model card
      identifies it as a CTranslate2 conversion of `openai/whisper-base.en`.
- [x] Verify PyPI lists CPython 3.11 manylinux ARM64 and AMD64 wheels for CTranslate2 4.6.0.
      This is wheel availability evidence only, not AMD64 build/runtime evidence.
- [x] Write `scripts/benchmark.py`: download/cache pinned model, load CPU INT8 with four
      threads, consume all segments, run twice in one process, record time/memory/version
      JSON and write transcript text only to ignored local output.
- [x] Write `benchmarks/Dockerfile`, candidate `benchmarks/requirements.in`, and benchmark README.
- [x] Build `transcriber-benchmark` from `python:3.11.13-slim-bookworm` with system FFmpeg.
      Tested image ID: `sha256:a058b2cc5a4b01c77b07e80f1b7a77a1e5c860ade2e2900c6d00074d806a2c4c`.
      Python base manifest digest reported by pull:
      `sha256:86adf8dbadc3d6e82ee5dd2c74bec2e1c2467cdad47886280501df722372d2e1`.
- [x] Verify installed benchmark dependencies with `pip check`: no broken requirements.
- [x] Capture exact installed packages in `benchmarks/requirements.lock` and
      `benchmarks/results/runtime-versions-arm64.txt`. Key tested versions:
      Python 3.11.13, faster-whisper 1.2.1, CTranslate2 4.6.0,
      huggingface-hub 0.34.4, PyAV 18.1.0, ONNX Runtime 1.30.0, NumPy 2.4.6,
      system FFmpeg 5.1.9-0+deb12u1.
- [x] Change benchmark Dockerfile to install the captured lock instead of the candidate input.
- [ ] Rebuild from that lock and rerun. The successful image was built **before** this
      Dockerfile edit; the lock captures its installed versions but the edited build
      recipe has not itself been exercised.

### Audio provenance and completed run

- [x] Before the user's restriction, download OpenAI Whisper's short JFK fixture to ignored
      `benchmarks/local/jfk.flac`. It was **not** used for any inference run.
- [x] Before that restriction, search for long-form audio and fetch Internet Archive metadata
      to `/tmp/transcriber-long-source.json`. No long-form audio was downloaded.
- [x] Stop scouting/downloading audio after the user instructed this. Update benchmark
      instructions to use a supplied file rather than fetch a recording.
- [x] Receive user-provided `sample-speech-5m.mp3` in repository root; mount it read-only.
- [x] Run the following command (absolute workspace path expanded when executed):

  ```sh
  docker run --name transcriber-benchmark-short --cpus 4 --memory 6g \
    -v transcriber-model-cache:/models \
    -v "$PWD/benchmarks/local:/results" \
    -v "$PWD/sample-speech-5m.mp3:/input/sample.mp3:ro" \
    transcriber-benchmark /input/sample.mp3 --output /results/sample-short.json
  ```

- [x] Verify exit code 0 and `OOMKilled=false`; both inference runs completed.
- [x] Preserve metric-only evidence in `benchmarks/results/sample-short-arm64.json`.
      Raw reports/transcripts remain in ignored `benchmarks/local/sample-short*`.
- [x] Record actual results:

  | Measurement | Actual result |
  |---|---:|
  | Audio duration reported by model runtime | 300.0185 s |
  | Initial model download/cache operation | 43.0954 s |
  | Model load | 0.1823 s |
  | First inference after load | 14.8165 s |
  | Warm inference, same model instance | 14.3079 s |
  | First / warm real-time factor | 0.04939 / 0.04769 |
  | First / cumulative warm process peak RSS | 756,072 / 829,232 KiB |
  | Container cgroup peak memory, whole run | 940,720,128 bytes (~897.1 MiB) |
  | Transcript length, each run | 4,762 characters |

- [x] Record settings: CPU INT8, four threads, beam size 5, English forced,
      VAD enabled, `condition_on_previous_text=False`, no batching.
      Runtime reports CPU support for `float32`, `int8`, and `int8_float32`.
- [x] Record measurement limits: elapsed inference includes PyAV decoding/VAD and full
      segment consumption, but **not** application FFmpeg normalization or queue/upload
      overhead. Process RSS is a cumulative high-water mark. Container peak includes
      download/cache activity. The 6 GiB limit was an experimental ceiling, not a measured
      minimum. Docker stats once showed ~386% CPU; this is a snapshot, not average usage.
- [ ] Listen/read against source and assess readability. No manual transcript quality
      review, reference-transcript comparison, or WER calculation has been performed.
- [ ] Verify application inference adapter separately; the successful run used the standalone harness.
- [ ] Obtain user-provided full-hour speech for representative long-form measurement.
      Do not source/download it independently. Do not extrapolate the five-minute result
      into verified one-hour support. A repeated sample may only be labelled a resource test.
- [ ] Benchmark silence, speech video, and full-hour input; record cold/warm context,
      CPU allocation, peak memory, decoder time, inference time, and quality limitations.
- [ ] Choose final model, worker memory limit, and processing timeout from these measurements.
      `base.en` remains the candidate; no `small.en` comparison has run.
- [ ] Verify AMD64 build/runtime where available. No Intel compatibility or performance verified.

## Phase 2 — backend vertical slice (authored, not operational)

- [x] Write `pyproject.toml` and root `requirements.in`. Candidate API/worker/test versions
      are listed, but have not been installed or compatibility tested.
- [x] Write `config.py` and `bootstrap.py` composition root.
- [x] Write domain `Job`, statuses/errors, `JobRepository` protocol, and ports for storage,
      inference, dispatch, media processing, admission, and heartbeat.
- [x] Write Redis repository adapter with Lua expected-state transitions and terminal TTL.
- [x] Write Redis admission and worker heartbeat adapters.
- [x] Write generated-ID local storage adapter and temporary-file save/rename path.
- [x] Write FFmpeg normalization adapter and Linux parent-death subprocess launcher.
- [x] Write faster-whisper application adapter with lazy worker-only imports.
- [x] Write submission/processing application service and Celery dispatch adapter.
- [x] Write Celery configuration and thin worker lifecycle/task entrypoints; intended
      concurrency one, early acknowledgement, no results backend or inference retries.
- [x] Add Python package initializers.
- [x] Run `python3 -m compileall -q src` successfully on host Python 3.14.4.
      This checks syntax only; target runtime is Python 3.11, and no imports were exercised.
- [ ] Review and correct scaffold before building on it. Particularly review:
      application constructor contract typing; Redis-outage compensation/cleanup paths;
      reservation release ordering; stale worker-ready keys across child replacement;
      model-load/claim timing versus Celery limits; bounded ffprobe output; safe filename/path
      handling; subprocess cancellation; codec/container policy. These are review targets,
      not claimed verified defects or guarantees.
- [ ] Resolve and lock application dependencies on target Python 3.11/Linux; run `pip check`.
- [ ] Implement API schemas/routes/dependencies and single `/health` endpoint, with bounded
      Redis/storage/ready-worker checks. Keep ML imports out of API startup.
- [ ] Implement admission before body parsing, actual byte limiter, multipart file/field bounds,
      upload timeout, safe status/error mapping, and unknown-ID 404.
- [ ] Demonstrate real upload -> stored file -> queued Redis record -> Celery worker ->
      completed transcript, with fake-engine tests and an opt-in real-model smoke run.
- [ ] Verify API responsiveness during inference and publication failure compensation.

## Phase 3 — reliability and resource bounds

- [ ] Test atomic slot/disk reservations and idempotent release under concurrent requests.
- [ ] Enforce upload limit without trusting Content-Length; account for parser spooling,
      saved upload, decoded audio, model cache, and free disk margin.
- [ ] Test actual media/container/codec validation, first-audio-track choice, local protocols,
      corrupt input, no audio, decode timeout, and misleading duration metadata.
- [ ] Accept exactly one hour; reject over-limit decoded audio without silent truncation.
- [ ] Implement maintenance service and API lifecycle runner: expired uploads, queue deadlines,
      interrupted processing, stale records, conservative cleanup, and orphan directories.
- [ ] Never delete live-job files or release their capacity merely because a heartbeat is stale.
- [ ] Verify heartbeat behavior during blocked inference and Redis outages.
- [ ] Test Celery prefork soft/hard limits, native inference interruption, worker termination,
      decoder child termination, eventual visible failure, and cleanup.
- [ ] Verify duplicate delivery, terminal-state protection, result TTL only after completion,
      restart semantics, and no indiscriminate startup deletion.
- [ ] Replace provisional limits only when justified; document retained assumptions explicitly.

## Phase 4 — React and TypeScript UI

- [ ] Create frontend with pinned packages and lockfile; separate typed API, lifecycle hook,
      and presentation components.
- [ ] Add accessible upload/status/transcript page with limits, copy/download, empty-speech
      explanation, elapsed waiting time, and useful errors.
- [ ] Use one multipart submission endpoint; prevent duplicate submit, preserve active ID
      in localStorage, resume polling after refresh, and offer reset/new upload.
- [ ] Cancel requests/timers, avoid overlapping polls, stop on terminal states, distinguish
      transient polling failures from transcription failures and expired/unknown IDs.
- [ ] Render filenames/transcripts as text, not HTML.
- [ ] Run TypeScript check, production build, and focused hook/component tests.

## Phase 5 — focused verification

- [ ] Add in-memory repository fake and shared repository contract tests.
- [ ] Test Redis atomic transitions and concurrent admission against real Redis.
- [ ] Test service cleanup on success, inference failure, and publication failure.
- [ ] Add HTTP size/validation/status/capacity/dependency tests, including untrusted or absent
      Content-Length and malicious filenames.
- [ ] Add real Celery/FFmpeg integration and crash/time-limit checks.
- [ ] Test WAV, MP3, M4A, MP4, and WebM variants; advertise only successfully tested formats.
- [ ] Run real-model audio/video/silence/full-hour checks and retain metrics, not user text.
- [ ] Run browser walkthrough, refresh/poll-error tests, health under load, and log review
      for accidental transcript/media/secrets leakage.

## Phase 6 — Docker submission and documentation

- [ ] Create root multistage Dockerfile: pinned Node build, compiled static frontend,
      Python runtime, non-root user, owned work/cache volumes, no GPU dependency.
- [ ] Create Compose API/worker/Redis services, localhost-only public port, no public Redis,
      explicit Redis AOF/RDB disabled, health checks, ordering, and stop grace periods.
- [ ] Add nonsecret `.env.example` and measured/configurable resource limits.
- [ ] Verify `docker compose up --build` without host Python/Node/FFmpeg or an HF token.
- [ ] Verify a fresh build/startup and lockfile reproducibility, not only cached image execution.
- [ ] Write README in the plan's requested order: product/limits, prerequisites/startup,
      walkthrough/curl, exact test commands, architecture/lifecycle, model/license/metrics,
      storage/retention/restarts/cleanup, trade-offs/limitations, future production phase.
- [ ] Include required AWS-to-local substitution table: blob storage/shared volume,
      presigned/API uploads, SQS/Redis broker, PostgreSQL/Redis records, outbox/best effort.
- [ ] Explain single submission endpoint, early ack/no durable recovery, publication gap,
      single-host storage, high-bitrate video limit, and local-only/no-account deployment.
- [ ] Document user-media versus model-cache cleanup commands; do not delete either implicitly.
- [ ] Inspect final staged diff, commit coherent milestones, check clean Git state, and report
      exact verified scope and limitations. Do not begin phase 7 as a prerequisite.

## Phase 7 — explicitly deferred production extension

- [ ] Add PostgreSQL repository through SQLAlchemy/Alembic and contract parity/migration tests.
- [ ] Design durable media, ownership/leases, retries, idempotent completion, transactional
      outbox/publication recovery, interrupted-job recovery, and retention together.
- [ ] Keep authentication and worker scaling separate optional work. An adapter swap alone
      does not establish durability, direct uploads, or reliable recovery.

## Local artifacts and checkpoint notes

- [x] Retained ignored user file: `sample-speech-5m.mp3`.
- [x] Retained ignored benchmark outputs: `benchmarks/local/sample-short.json`,
      `sample-short.run0.txt`, `sample-short.run1.txt`, and `runtime-versions.txt`.
- [x] Retained Docker image `transcriber-benchmark`, exited container
      `transcriber-benchmark-short`, and named model volume `transcriber-model-cache`.
- [x] Auxiliary `/tmp` files were used for downloaded model/package metadata and scaffold
      generation. They are not required to resume; repository sources are authoritative.
- [x] No remote repository created, no push, no publishing, no user-media deletion.
- [ ] **Next conversation:** review this checklist and scaffold, finish the benchmark
      reproducibility/quality gaps that can use the supplied file, then complete phase 2.
      Request a user-provided full-hour recording only when needed; do not fetch one.
