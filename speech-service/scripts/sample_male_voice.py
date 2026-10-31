"""One explicit male-voice sample with observed NPU calls; no implicit retries."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from speech_service.rkvoice_backend import MALE_VOICES, RkvoiceKokoroBackend
from speech_service.pronunciation import POLICY_ID


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--voices", type=Path, required=True)
    parser.add_argument("--voice", choices=sorted(MALE_VOICES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location("speech_measurement", ROOT / "benchmarks/benchmark.py")
    measurement = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(measurement)
    trace = measurement.InferenceTrace()
    from rknnlite.api import RKNNLite
    from rkvoice_stream.backends.tts.kokoro_convonly_capi import RK3588CapiRuntime
    trace.install(RKNNLite, "rknnlite.api.RKNNLite.inference")
    trace.install(RK3588CapiRuntime, "RK3588CapiRuntime.inference")
    text = "欢迎来到视频工作台。今天，我们用一段清楚、自然的中文讲解，看看本地男声是否适合日常制作。"
    backend = RkvoiceKokoroBackend(args.bundle, voice=args.voice, voice_directory=args.voices)
    report = {"status": "running", "voice": args.voice, "text": text,
              "frontend_policy": POLICY_ID, "automatic_retries": 0, "quality_accepted": False}
    try:
        start = time.perf_counter()
        backend.preload()
        report["preload_s"] = time.perf_counter() - start
        before = trace.snapshot()
        start = time.perf_counter()
        payload = backend.synthesize(text, voice=args.voice, speed=1.0)
        report["synthesis_s"] = time.perf_counter() - start
        report["wav"] = measurement.validate_wav(payload)
        (args.output / "sample.wav").write_bytes(payload)
        report["voice_receipt"] = backend.voice_receipt
        report["metadata"] = backend.last_metadata
        report["execution"] = measurement.assess_execution(
            {"backend": "kokoro_convonly"}, measurement.backend_snapshot(backend._backend),
            backend.last_metadata, measurement.trace_delta(before, trace.snapshot()))
        if not report["execution"]["qualification_passed"]:
            raise RuntimeError("male sample NPU evidence failed")
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__, error=str(exc))
    finally:
        backend.cleanup()
        measurement.save_json(args.output / "report.json", report)
    print(json.dumps({key: report.get(key) for key in ("status", "voice", "synthesis_s", "wav", "error")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
