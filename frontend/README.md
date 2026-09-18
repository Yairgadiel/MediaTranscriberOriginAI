# Frontend

The frontend is an independent React/TypeScript package. It builds into static assets that the
backend image copies into `backend/src/transcriber/entrypoints/static`; FastAPI then serves those
assets alongside the `/api` routes.

## Exact structure

```text
frontend/
├── package.json          # scripts and pinned direct dependency declarations
├── package-lock.json     # npm dependency graph lockfile
├── tsconfig.json         # application TypeScript configuration
├── tsconfig.node.json    # TypeScript configuration for tooling
├── vite.config.ts        # Vite build, dev proxy, and Vitest configuration
├── index.html            # browser document shell
└── src/
    ├── main.tsx          # React entrypoint
    ├── App.tsx           # page composition and upload/status presentation
    ├── api.ts            # typed HTTP calls to the backend
    ├── useTranscription.ts # upload, localStorage resume, polling, and retry state
    ├── styles.css        # application styling and responsive states
    └── App.test.tsx      # focused UI and polling behavior tests
```

The browser sends one multipart request to `POST /api/transcriptions`, stores the active job ID
in `localStorage`, and polls `GET /api/transcriptions/{id}` until the job completes or fails.
The frontend renders filenames and transcript content as text and has no direct access to Redis,
Celery, temporary files, or model internals. Transient polling errors use a 2-second exponential
delay capped at 5 seconds and retry at most three times; after the third failure, polling stops,
the stored ID is cleared, and the UI tells the user to
start a new upload or refresh. A `404` remains an immediate terminal expired/restarted-job case.

From this directory:

```sh
npm ci
npx tsc -b
npm run build
NODE_OPTIONS=--no-experimental-webstorage npm test
```
