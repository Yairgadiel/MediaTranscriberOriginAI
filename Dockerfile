FROM node:22.15.0-bookworm-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.11.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/backend/src \
    TMPDIR=/work OMP_NUM_THREADS=4
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.lock requirements.lock
RUN pip install --no-cache-dir -r requirements.lock && pip check
RUN useradd --uid 10001 --create-home app && mkdir /work /models \
    && chown app:app /work /models
COPY backend/src backend/src
COPY backend/tests backend/tests
COPY --from=frontend-build /frontend/dist backend/src/transcriber/entrypoints/static
USER app
CMD ["uvicorn", "transcriber.entrypoints.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
