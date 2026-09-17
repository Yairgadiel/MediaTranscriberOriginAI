# Phase 1: native CPU inference gate

Candidate pins (not yet runtime verified): Python 3.11.13, faster-whisper 1.2.1,
CTranslate2 4.6.0, huggingface-hub 0.34.4. A complete resolved dependency lock
will replace the candidate input once the container has run successfully.

Model: `Systran/faster-whisper-base.en`, revision
`3d3d5dee26484f91867d81cb899cfcf72b96be6c`. Its
[model card](https://huggingface.co/Systran/faster-whisper-base.en)
identifies an MIT-licensed CTranslate2 conversion of
[OpenAI Whisper base.en](https://huggingface.co/openai/whisper-base.en).
The conversion stores FP16 weights; the benchmark explicitly loads CPU INT8.
No GPU libraries or architecture emulation are requested.

PyPI metadata confirms CPython 3.11 manylinux wheels for CTranslate2 4.6.0 on
AArch64 and x86-64. This alone does **not** verify either runtime, all transitive
dependencies, or Intel performance.

The short fixture is the public JFK speech recording in the
[OpenAI Whisper test suite](https://github.com/openai/whisper/blob/main/tests/jfk.flac).
Expected content: “And so, my fellow Americans, ask not what your country can do
for you; ask what you can do for your country.” Downloaded media and generated
transcripts stay in ignored `benchmarks/local/`.

```sh
mkdir -p benchmarks/local
curl -fL https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac \
  -o benchmarks/local/jfk.flac
docker build -f benchmarks/Dockerfile -t transcriber-benchmark .
docker run --rm --cpus 4 --memory 6g \
  -v transcriber-model-cache:/models \
  -v "$PWD/benchmarks/local:/results" \
  transcriber-benchmark /results/jfk.flac --output /results/short.json
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
