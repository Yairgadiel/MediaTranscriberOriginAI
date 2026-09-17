FROM python:3.11.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY benchmarks/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY scripts/benchmark.py /app/benchmark.py
ENTRYPOINT ["python", "-u", "/app/benchmark.py"]
