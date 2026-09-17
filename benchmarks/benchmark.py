"""Opt-in real inference benchmark; JSON report, transcript kept only locally."""
import argparse
import importlib.metadata
import json
import os
import platform
import resource
import time
from pathlib import Path

import ctranslate2
from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download

MODEL = "Systran/faster-whisper-base.en"
REVISION = "3d3d5dee26484f91867d81cb899cfcf72b96be6c"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--output", default="/results/benchmark.json")
    parser.add_argument("--runs", type=int, default=2)
    args = parser.parse_args()
    started = time.monotonic()
    model_path = snapshot_download(MODEL, revision=REVISION, cache_dir="/models",
                                   allow_patterns=["*.json", "*.bin", "*.txt"])
    downloaded = time.monotonic()
    model = WhisperModel(model_path, device="cpu", compute_type="int8", cpu_threads=4)
    loaded = time.monotonic()
    report = {
        "model": MODEL, "revision": REVISION, "architecture": platform.machine(),
        "python": platform.python_version(), "cpu_threads": 4, "compute_type": "int8",
        "supported_compute_types": sorted(ctranslate2.get_supported_compute_types("cpu")),
        "versions": {p: importlib.metadata.version(p) for p in
                     ["faster-whisper", "ctranslate2", "av", "huggingface-hub", "onnxruntime", "numpy"]},
        "download_or_cache_lookup_seconds": downloaded - started,
        "load_seconds": loaded - downloaded, "runs": [],
    }
    for index in range(args.runs):
        start = time.monotonic()
        segments, info = model.transcribe(args.audio, language="en", beam_size=5,
                                          vad_filter=True, condition_on_previous_text=False)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        elapsed = time.monotonic() - start
        run = {"index": index, "seconds": elapsed, "duration_seconds": info.duration,
               "real_time_factor": elapsed / info.duration, "characters": len(text),
               "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        report["runs"].append(run)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).with_suffix(f".run{index}.txt").write_text(text)
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(run), flush=True)
    try:
        report["container_memory_peak_bytes"] = int(Path("/sys/fs/cgroup/memory.peak").read_text())
    except (OSError, ValueError):
        report["container_memory_peak_bytes"] = None
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
