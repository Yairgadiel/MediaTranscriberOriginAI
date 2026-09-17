# Phase 1: native CPU inference gate

Runtime-verified pins (native ARM64, user-provided five-minute MP3): Python 3.11.13, faster-whisper 1.2.1,
CTranslate2 4.6.0, huggingface-hub 0.34.4. The resolved dependency lock captures the installed benchmark environment. The
Dockerfile was then changed to use that lock, and the final Compose checkpoint completed a fresh locked image build.

Model: `Systran/faster-whisper-base.en`, revision
`3d3d5dee26484f91867d81cb899cfcf72b96be6c`. Its
[model card](https://huggingface.co/Systran/faster-whisper-base.en)
identifies an MIT-licensed CTranslate2 conversion of
[OpenAI Whisper base.en](https://huggingface.co/openai/whisper-base.en).
The conversion stores FP16 weights; the benchmark explicitly loads CPU INT8.
No GPU libraries or architecture emulation are requested.

PyPI metadata confirms CPython 3.11 manylinux wheels for CTranslate2 4.6.0 on
AArch64 and x86-64. Native ARM64 inference subsequently passed. Wheel availability does **not**
verify AMD64 builds, runtime compatibility, or Intel performance.

Use a user-provided local English speech recording. Media and generated
transcripts are ignored by Git. No recording is fetched by the benchmark.

```sh
mkdir -p benchmarks/local
docker build -f benchmarks/Dockerfile -t transcriber-benchmark .
docker run --rm --cpus 4 --memory 6g \
  -v transcriber-model-cache:/models \
  -v "$PWD/benchmarks/local:/results" \
  -v "$PWD/sample-speech-5m.mp3:/input/sample.mp3:ro" \
  transcriber-benchmark /input/sample.mp3 --output /results/short.json
```

The 6 GiB benchmark ceiling is an experimental safety cap, not a measured
application requirement. The VM has 4 CPUs and 8 GiB. Run index 0 includes the
first inference after load; index 1 reuses the model. `download_or_cache_lookup`
includes an actual download only when the named volume has no cached snapshot.
Container cgroup peak and process RSS are distinct measurements. Fully consuming
the segment iterator is required for elapsed inference timing.

A repeated short clip may be used as a one-hour resource stress test but must
never be described as a representative accuracy benchmark. Representative
long-form evidence and final resource/time-limit decisions remain pending.

Actual metric reports: `results/sample-short-arm64.json` and
`results/runtime-versions-arm64.txt`. Full execution history and outstanding
verification are in `../docs/implementation-status.md`. No one-hour run or
manual transcript quality assessment has been performed. The measured ARM64 results must not be generalized to Intel/AMD64 compatibility or performance.
