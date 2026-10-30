#!/usr/bin/env python3
"""Sequential, process-isolated TTS qualification; stdlib controller.

No models, packages, or native libraries are downloaded by this program. The
worker uses the pinned source's real TTSBackend interface, not the README's
TTSEngine illustration; the explicit CPU reference adapts sherpa's reviewed
GenerationConfig API. Run only after independently reviewing model receipts.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import importlib
import importlib.metadata
import io
import json
import logging
import math
import os
from pathlib import Path
import platform
import re
import signal
import struct
import subprocess
import sys
import threading
import time
import traceback
import wave


HERE = Path(__file__).resolve().parent
SAMPLES = HERE.parent / "samples"
BACKENDS = {"matcha_rknn", "kokoro_convonly", "sherpa_matcha_cpu"}
NPU_IMPORT_PREFIXES = ("rknnlite", "rknn", "rkvoice_stream")
ENV_NAME = re.compile(r"(?:TTS_[A-Z0-9_]+|MATCHA_[A-Z0-9_]+|VOCOS_[A-Z0-9_]+|"
                      r"KOKORO_[A-Z0-9_]+|RK_PLATFORM|CSTOPS_LIB|MODEL_DIR|"
                      r"OMP_NUM_THREADS|OPENBLAS_NUM_THREADS|MKL_NUM_THREADS)")


def save_json(path: Path, value) -> None:
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False,
                     default=lambda x: x.item() if hasattr(x, "item") else str(x)) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(raw, encoding="utf-8")
    temporary.replace(path)


def validate_wav(payload: bytes) -> dict:
    """Reject streaming sentinels, truncation, non-PCM16, and digital silence.

    This validates a measurement artifact, not pronunciation or speech quality.
    The returned duration comes from PCM frame count, never backend metadata.
    """
    if not isinstance(payload, bytes) or not 44 <= len(payload) <= 64 * 1024 * 1024:
        raise ValueError("WAV must be bounded, complete bytes")
    if payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        raise ValueError("Expected a RIFF WAVE file")
    if struct.unpack_from("<I", payload, 4)[0] + 8 != len(payload):
        raise ValueError("WAV RIFF length is incomplete or uses a streaming sentinel")
    with wave.open(io.BytesIO(payload), "rb") as source:
        rate, channels = source.getframerate(), source.getnchannels()
        frames, width = source.getnframes(), source.getsampwidth()
        if source.getcomptype() != "NONE" or width != 2 or channels not in (1, 2):
            raise ValueError("Expected uncompressed PCM16 mono/stereo")
        if not 8000 <= rate <= 96000 or not 0 < frames <= rate * 600:
            raise ValueError("WAV rate or frame count is outside measurement limits")
        pcm = source.readframes(frames + 1)
    if len(pcm) != frames * channels * width:
        raise ValueError("WAV data chunk is truncated")
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max(abs(sample) for sample in samples)
    if not peak:
        raise ValueError("Digital silence is not a successful synthesis")
    return {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
            "format": "PCM_16", "sample_rate": rate, "channels": channels,
            "frames": frames, "duration_s": frames / rate,
            "peak": peak / 32768,
            "rms": math.sqrt(sum((x / 32768) ** 2 for x in samples) / len(samples)),
            "clipped_sample_fraction": sum(abs(x) >= 32767 for x in samples) / len(samples)}


def load_candidate(path: Path) -> dict:
    candidate = json.loads(path.read_text(encoding="utf-8"))
    allowed = {"name", "backend", "env", "source_revision", "speaker_id", "speed",
               "synthesis_kwargs", "expected_matcha_backend", "artifact_receipt", "cpu_config"}
    if not isinstance(candidate, dict) or set(candidate) - allowed:
        raise ValueError("Unexpected candidate fields")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", candidate.get("name", "")):
        raise ValueError("Candidate name must be a short lowercase identifier")
    if candidate.get("backend") not in BACKENDS:
        raise ValueError("Unsupported TTS backend")
    env = candidate.get("env", {})
    if not isinstance(env, dict) or any(not ENV_NAME.fullmatch(k) or not isinstance(v, str)
                                        or "\x00" in v for k, v in env.items()):
        raise ValueError("Candidate env must contain only explicit backend settings")
    speed = candidate.get("speed", 1.0)
    if isinstance(speed, bool) or not isinstance(speed, (float, int)) or not 0.25 <= speed <= 4:
        raise ValueError("Invalid synthesis speed")
    if not isinstance(candidate.get("synthesis_kwargs", {}), dict):
        raise ValueError("synthesis_kwargs must be an object")
    if set(candidate.get("synthesis_kwargs", {})) - {"language", "voice", "noise_scale"}:
        raise ValueError("Only language, voice and noise_scale synthesis kwargs are supported")
    if candidate.get("expected_matcha_backend") not in (None, "rknn", "rknn_split", "ort"):
        raise ValueError("Expected Matcha acoustic backend must be rknn, rknn_split or explicitly ort")
    if candidate["backend"] == "sherpa_matcha_cpu":
        validate_cpu_config(candidate.get("cpu_config"))
        if candidate.get("expected_matcha_backend") is not None or candidate.get("synthesis_kwargs"):
            raise ValueError("CPU reference uses cpu_config, not NPU settings or synthesis kwargs")
    elif "cpu_config" in candidate:
        raise ValueError("cpu_config is only valid for sherpa_matcha_cpu")
    return candidate


def validate_cpu_config(config):
    required = {"acoustic", "vocoder", "tokens", "lexicons", "rule_fsts", "num_threads", "noise_scale"}
    if not isinstance(config, dict) or set(config) != required:
        raise ValueError("CPU reference requires explicit acoustic/vocoder/tokens/lexicons/rule_fsts/num_threads/noise_scale")
    if (not isinstance(config["lexicons"], list) or not config["lexicons"]
            or not isinstance(config["rule_fsts"], list)):
        raise ValueError("CPU lexicons must be a nonempty list; rule_fsts must be an explicit list")
    paths = [config["acoustic"], config["vocoder"], config["tokens"],
             *config["lexicons"], *config["rule_fsts"]]
    if any(not isinstance(value, str) or not value or len(value) > 4096
           or "," in value or "\x00" in value for value in paths):
        raise ValueError("CPU artifact paths must be nonempty strings without commas or NULs")
    threads, noise = config["num_threads"], config["noise_scale"]
    if isinstance(threads, bool) or not isinstance(threads, int) or not 1 <= threads <= 32:
        raise ValueError("CPU num_threads must be 1..32")
    if isinstance(noise, bool) or not isinstance(noise, (float, int)) or not 0 <= noise <= 4:
        raise ValueError("CPU noise_scale must be finite and 0..4")


class NoNPUImports:
    """CPU-worker Python import guard, not a system-wide hardware assertion."""
    def __init__(self):
        self.attempts = []

    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == prefix or fullname.startswith(prefix + ".") for prefix in NPU_IMPORT_PREFIXES):
            self.attempts.append(fullname)
            raise ImportError("CPU reference forbids NPU/backend import: " + fullname)
        return None

    def evidence(self):
        return {"npu_python_import_guard": "blocked",
                "npu_import_attempts": list(self.attempts),
                "npu_modules_loaded": sorted(name for name in list(sys.modules)
                    if any(name == prefix or name.startswith(prefix + ".") for prefix in NPU_IMPORT_PREFIXES))}


class SherpaMatchaCPUBackend:
    """Reviewed sherpa-onnx 2.0.1 API; CPU acoustic + original CPU Vocos.

    This is a complete CPU reference with sherpa's native FST frontend, which
    differs from rkvoice-stream's frontend. It is not a same-frontend NPU A/B.
    """
    name = "sherpa_matcha_cpu"

    def __init__(self, config, module, import_guard):
        validate_cpu_config(config)
        self.config, self.module, self.import_guard = config, module, import_guard
        self.tts = None

    def preload(self):
        config = self.config
        for value in [config["acoustic"], config["vocoder"], config["tokens"],
                      *config["lexicons"], *config["rule_fsts"]]:
            if not Path(value).is_file():
                raise FileNotFoundError("CPU reference artifact is missing: " + value)
        module = self.module
        model = module.OfflineTtsMatchaModelConfig(
            acoustic_model=config["acoustic"], vocoder=config["vocoder"],
            tokens=config["tokens"], lexicon=",".join(config["lexicons"]),
            noise_scale=config["noise_scale"], length_scale=1.0)
        options = module.OfflineTtsConfig(
            model=module.OfflineTtsModelConfig(matcha=model, num_threads=config["num_threads"],
                                             provider="cpu", debug=False),
            rule_fsts=",".join(config["rule_fsts"]))
        if hasattr(options, "validate") and not options.validate():
            raise RuntimeError("sherpa rejected CPU Matcha/Vocos configuration")
        if not hasattr(module, "GenerationConfig"):
            raise RuntimeError("CPU reference requires the reviewed sherpa GenerationConfig API")
        self.tts = module.OfflineTts(options)

    def is_ready(self):
        return self.tts is not None

    def runtime_info(self):
        return {"provider": "cpu", "acoustic_engine": "cpu", "vocoder_engine": "cpu",
                "frontend": "sherpa native lexicon/FST; differs from rkvoice frontend",
                "comparison_class": "complete_cpu_reference_different_frontend",
                "generation_api": "GenerationConfig", "config": self.config,
                **self.import_guard.evidence()}

    def get_sample_rate(self):
        # Reviewed Matcha-Icefall-ZH-EN + original Vocos artifact contract.
        return 16000

    def synthesize(self, text, speaker_id=0, speed=1.0, **kwargs):
        import numpy as np
        if not self.is_ready() or kwargs:
            raise ValueError("CPU reference must be preloaded and has no freeform synthesis kwargs")
        generation = self.module.GenerationConfig()
        generation.sid, generation.speed = speaker_id, speed
        begin = time.perf_counter()
        result = self.tts.generate(text, generation)
        inference_s = time.perf_counter() - begin
        values = np.asarray(result.samples, dtype=np.float32)
        if values.ndim != 1 or not 0 < len(values) <= 16000 * 600 or not np.isfinite(values).all():
            raise ValueError("CPU reference returned empty, invalid or nonfinite samples")
        if int(result.sample_rate) != self.get_sample_rate():
            raise ValueError("CPU reference output differs from reviewed 16 kHz artifact contract")
        # Same fixed conversion as the standalone CPU runner; no gain change.
        pcm = np.rint(np.clip(values, -1.0, 1.0) * 32767.0).astype("<i2")
        output = io.BytesIO()
        with wave.open(output, "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(self.get_sample_rate())
            stream.writeframes(pcm.tobytes())
        return output.getvalue(), {"engine": "cpu", "provider": "cpu", "fallback": False,
            "acoustic_engine": "cpu", "vocoder_engine": "cpu", "inference_s": inference_s,
            "frontend": "sherpa native lexicon/FST; differs from rkvoice frontend",
            "comparison_class": "complete_cpu_reference_different_frontend",
            "clipped_sample_fraction_before_pcm": float(np.mean(np.abs(values) > 1.0))}

    def cleanup(self):
        self.tts = None


class InferenceTrace:
    """Count successful runtime calls, including Kokoro's native C-API path.

    A preload/init call never contributes to a synthesis's counters. Wrappers
    delegate exactly once; no input/output replacement, fallback, or retries.
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.counts = {}
        self.models = {}

    def install(self, cls, name):
        original = cls.inference
        if hasattr(cls, "load_rknn"):
            load = cls.load_rknn

            def observed_load(instance, path, *args, **kwargs):
                result = load(instance, path, *args, **kwargs)
                if result == 0:
                    with self.lock:
                        self.models[id(instance)] = str(path)
                return result

            cls.load_rknn = observed_load
        else:
            initialize = cls.__init__

            def observed_init(instance, model_path, *args, **kwargs):
                initialize(instance, model_path, *args, **kwargs)
                with self.lock:
                    self.models[id(instance)] = str(model_path)

            cls.__init__ = observed_init

        def observed(instance, *args, **kwargs):
            with self.lock:
                key = name + " | " + self.models.get(id(instance), "unidentified-model")
                count = self.counts.setdefault(key, {"calls": 0, "successful_returns": 0, "failed_calls": 0})
                count["calls"] += 1
            try:
                result = original(instance, *args, **kwargs)
            except BaseException:
                with self.lock:
                    count["failed_calls"] += 1
                raise
            with self.lock:
                outcome = "successful_returns" if result is not None else "failed_calls"
                count[outcome] += 1
            return result

        cls.inference = observed

    def snapshot(self):
        with self.lock:
            return {k: dict(v) for k, v in self.counts.items()}


def trace_delta(before, after):
    return {name: {key: values[key] - before.get(name, {}).get(key, 0) for key in values}
            for name, values in after.items()}


def backend_snapshot(backend) -> dict:
    snapshot = {"name": backend.name, "class": type(backend).__module__ + "." + type(backend).__name__,
                "ready": bool(backend.is_ready())}
    hook = getattr(backend, "runtime_info", None)
    if hook:
        snapshot["runtime_info"] = hook()
    engine = getattr(backend, "_engine", None)
    if engine is not None and hasattr(engine, "_matcha_backend"):
        snapshot["matcha_acoustic_backend"] = engine._matcha_backend
        snapshot["vocos_runtime_class"] = type(engine._vocos).__module__ + "." + type(engine._vocos).__name__
    return snapshot


def assess_execution(candidate, snapshot, metadata, calls) -> dict:
    """Keep hardware-call observations distinct from backend self reports."""
    successful = sum(x["successful_returns"] for x in calls.values())
    failed = sum(x["failed_calls"] for x in calls.values())
    attempted = sum(x["calls"] for x in calls.values())
    if candidate["backend"] == "sherpa_matcha_cpu":
        runtime = snapshot.get("runtime_info", {})
        cpu_state = (runtime.get("provider") == "cpu" and runtime.get("acoustic_engine") == "cpu"
                     and runtime.get("vocoder_engine") == "cpu")
        imports_clear = (runtime.get("npu_python_import_guard") == "blocked"
                         and runtime.get("npu_import_attempts") == [] and runtime.get("npu_modules_loaded") == [])
        known = (cpu_state and metadata.get("engine") == "cpu" and metadata.get("provider") == "cpu"
                 and metadata.get("acoustic_engine") == "cpu" and metadata.get("vocoder_engine") == "cpu"
                 and metadata.get("fallback") is False)
        return {"qualification_passed": (snapshot["name"] == candidate["backend"] and snapshot["ready"]
                    and known and imports_clear and attempted == 0),
                "execution_class": "cpu_reference", "npu_runtime_calls_observed": successful > 0,
                "npu_runtime_call_attempts": attempted, "runtime_calls": calls,
                "no_npu_python_imports": imports_clear, "selected_backend_known": known,
                "fallback_detected": metadata.get("fallback") is True,
                "backend_report": {"provider": runtime.get("provider"),
                    "frontend": runtime.get("frontend"),
                    "comparison_class": "complete_cpu_reference_different_frontend"},
                "scope": "Explicit CPU provider + no NPU Python imports/calls; not a system-wide no-NPU assertion"}
    if candidate["backend"] == "matcha_rknn":
        selected = snapshot.get("matcha_acoustic_backend")
        expected = candidate.get("expected_matcha_backend")
        fallback = selected == "ort" and expected != "ort"
        known = selected in ("rknn", "rknn_split", "ort") and (
            selected == expected if expected else selected in ("rknn", "rknn_split"))
        report = {"matcha_acoustic_backend": selected,
                  "intentional_cpu_acoustic": selected == "ort" and expected == "ort",
                  "cpu_work_remains": "text frontend, ODE in split mode, ISTFT and WAV encoding"}
    else:
        segments = metadata.get("segments", [metadata])
        fallback = any(m.get("fallback") is True or m.get("engine") in ("cpu", "mixed") for m in segments)
        known = bool(segments) and all(m.get("engine") == "npu" and m.get("fallback") is False for m in segments)
        report = {"reported_engine": metadata.get("engine"),
                  "reported_fallback": metadata.get("fallback"),
                  "cpu_work_remains": "language frontend and hybrid non-convolution arithmetic/ISTFT"}
    passed = (snapshot["name"] == candidate["backend"] and snapshot["ready"]
              and known and not fallback and successful > 0 and failed == 0)
    return {"qualification_passed": passed, "execution_class": "npu_submodule",
            "npu_runtime_calls_observed": successful > 0, "npu_runtime_call_attempts": attempted,
            "runtime_calls": calls, "backend_report": report,
            "fallback_detected": fallback, "selected_backend_known": known,
            "scope": "Observed inference API calls plus backend state; not a full-model NPU claim"}


def source_info(module):
    path = Path(module.__file__).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def worker(candidate_path: Path, folder: Path, smoke: Path, paragraph: Path) -> int:
    import resource
    started = time.perf_counter()
    report = {"status": "running", "requests": [], "automatic_retries": 0,
              "cold_scope": "Fresh process; OS file caches are not flushed. preload may warm up internally."}
    backend = None
    cpu_guard = None

    def phase(name):
        save_json(folder / "phase.json", {"phase": name, "monotonic_s": time.monotonic()})

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", force=True)
    try:
        candidate = load_candidate(candidate_path)
        os.environ.update(candidate.get("env", {}))
        # Prevent implicit model downloads; all artifacts are staged separately.
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        phase("import")
        trace = InferenceTrace()
        if candidate["backend"] == "sherpa_matcha_cpu":
            cpu_guard = NoNPUImports()
            sys.meta_path.insert(0, cpu_guard)
            module = importlib.import_module("sherpa_onnx")
            importlib.import_module("numpy")
            package, report_prefix = "sherpa-onnx", "sherpa"
        else:
            module = importlib.import_module("rkvoice_stream.engine.tts")
            from rknnlite.api import RKNNLite
            trace.install(RKNNLite, "rknnlite.api.RKNNLite.inference")
            if candidate["backend"] == "kokoro_convonly":
                from rkvoice_stream.backends.tts.kokoro_convonly_capi import RK3588CapiRuntime
                trace.install(RK3588CapiRuntime, "RK3588CapiRuntime.inference")
            package, report_prefix = "rkvoice-stream", "rkvoice"
        report["import_s"] = time.perf_counter() - started
        report["python"] = sys.version
        report[report_prefix + "_engine_source"] = source_info(module)
        try:
            report[report_prefix + "_package_version"] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            report[report_prefix + "_package_version"] = None
        phase("create")
        begin = time.perf_counter()
        if candidate["backend"] == "sherpa_matcha_cpu":
            backend = SherpaMatchaCPUBackend(candidate["cpu_config"], module, cpu_guard)
        else:
            backend = module.create_backend(candidate["backend"])
        report["create_s"] = time.perf_counter() - begin
        report["backend_source"] = source_info(importlib.import_module(type(backend).__module__))
        phase("preload")
        begin = time.perf_counter()
        backend.preload()
        report["preload_s"] = time.perf_counter() - begin
        report["cold_startup_s"] = time.perf_counter() - started
        report["preload_runtime_calls"] = trace.snapshot()
        report["loaded_backend"] = backend_snapshot(backend)
        if not report["loaded_backend"]["ready"]:
            raise RuntimeError("Backend is not ready after preload")
        if cpu_guard:
            cpu_state = cpu_guard.evidence()
            if cpu_state["npu_import_attempts"] or cpu_state["npu_modules_loaded"]:
                raise RuntimeError("CPU reference attempted or loaded an NPU Python backend")
        if (candidate["backend"] == "matcha_rknn"
                and report["loaded_backend"].get("matcha_acoustic_backend") == "ort"
                and candidate.get("expected_matcha_backend") != "ort"):
            raise RuntimeError("Matcha selected CPU acoustic fallback; stop before synthesis")
        for name, text_path in (("smoke", smoke), ("paragraph", paragraph)):
            text = text_path.read_text(encoding="utf-8").strip()
            if not 1 <= len(text) <= 4000:
                raise ValueError("Sample text length is outside bounds")
            phase(name)
            before = trace.snapshot()
            begin = time.perf_counter()
            payload, metadata = backend.synthesize(text, speaker_id=candidate.get("speaker_id", 0),
                                                    speed=candidate.get("speed", 1.0),
                                                    **candidate.get("synthesis_kwargs", {}))
            elapsed = time.perf_counter() - begin
            if name == "smoke":
                report["cold_start_to_first_complete_audio_s"] = time.perf_counter() - started
            calls = trace_delta(before, trace.snapshot())
            media = validate_wav(payload)
            if media["sample_rate"] != backend.get_sample_rate():
                raise ValueError("Actual WAV sample rate differs from backend contract")
            (folder / (name + ".wav")).write_bytes(payload)
            execution = assess_execution(candidate, backend_snapshot(backend), metadata, calls)
            report["requests"].append({"name": name, "text": text,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "synthesis_s": elapsed,
                "rtf": elapsed / media["duration_s"], "wav": media,
                "execution": execution, "backend_metadata": metadata})
            save_json(folder / "worker.json", report)
            if not execution["qualification_passed"]:
                raise RuntimeError("Inference evidence failed; do not advance or retry")
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        traceback.print_exc()
    finally:
        phase("cleanup")
        if backend is not None:
            cleanup = getattr(backend, "cleanup", None) or getattr(backend, "close", None)
            if cleanup:
                try:
                    cleanup()
                except BaseException as error:
                    report["status"] = "failed"
                    report["cleanup_error"] = {"type": type(error).__name__, "message": str(error)}
                    traceback.print_exc()
        report["worker_wall_s"] = time.perf_counter() - started
        report["peak_self_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        report["peak_self_rss_source"] = "Linux getrusage(RUSAGE_SELF).ru_maxrss; includes imports/preload"
        if cpu_guard:
            report["cpu_no_npu_python_imports"] = cpu_guard.evidence()
            sys.meta_path.remove(cpu_guard)
        save_json(folder / "worker.json", report)
        phase("finished")
    return 0 if report["status"] == "passed" else 1


def read_bounded(path: Path, size=4096):
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            return {"text": stream.read(size)}
    except OSError as error:
        return {"error": error.__class__.__name__}


def process_sample(pid: int) -> list[dict]:
    """Linux process tree snapshot. RSS sums may double-count shared pages."""
    pending, seen, rows = [pid], set(), []
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            base = Path("/proc") / str(current)
            raw = (base / "stat").read_text()
            fields = raw[raw.rfind(")") + 2:].split()
            rows.append({"pid": current, "start_ticks": int(fields[19]),
                         "cpu_ticks": int(fields[11]) + int(fields[12]),
                         "rss_bytes": int(fields[21]) * os.sysconf("SC_PAGE_SIZE")})
            for task in (base / "task").iterdir():
                children = (task / "children").read_text().split()
                pending.extend(int(child) for child in children)
        except (OSError, ValueError, IndexError):
            continue
    return rows


def stop_process(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.wait(timeout=5)
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def run_candidate(candidate, folder, args):
    save_json(folder / "candidate.json", candidate)
    state = {"name": candidate["name"], "status": "running", "automatic_retries": 0,
             "hardware": {"machine": platform.machine(), "kernel": platform.release(),
                          "cpu_count": os.cpu_count()}, "peak_sampled_tree_rss_bytes": 0,
             "sampling_scope": "Process-tree RSS/CPU plus shared system NPU load; NPU load is not per-process proof"}
    if candidate.get("artifact_receipt"):
        receipt = Path(candidate["artifact_receipt"])
        state["artifact_receipt"] = {"path": str(receipt),
                                     "sha256": hashlib.sha256(receipt.read_bytes()).hexdigest()}
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", str(folder / "candidate.json"),
               "--output", str(folder), "--smoke-text", str(args.smoke_text),
               "--paragraph-text", str(args.paragraph_text)]
    started = time.monotonic()
    previous, previous_time = {}, None
    process = None
    try:
        with (folder / "backend.log").open("wb") as log, (folder / "samples.jsonl").open("w", encoding="utf-8") as samples:
            # A previous shell's candidate settings must not change this run.
            child_env = {k: v for k, v in os.environ.items() if not ENV_NAME.fullmatch(k)}
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True, env=child_env)
            state["pid"] = process.pid
            while True:
                now = time.monotonic()
                rows = process_sample(process.pid)
                current = {(r["pid"], r["start_ticks"]): r["cpu_ticks"] for r in rows}
                delta = sum(max(0, ticks - previous.get(key, ticks)) for key, ticks in current.items())
                cpu = None if previous_time is None else delta / os.sysconf("SC_CLK_TCK") / (now - previous_time) * 100
                rss = sum(row["rss_bytes"] for row in rows)
                state["peak_sampled_tree_rss_bytes"] = max(state["peak_sampled_tree_rss_bytes"], rss)
                try:
                    phase = json.loads((folder / "phase.json").read_text())["phase"]
                except (OSError, ValueError, KeyError):
                    phase = "starting"
                sample = {"elapsed_s": now - started, "phase": phase, "processes": rows,
                          "cpu_percent_one_core_100": cpu, "tree_rss_bytes": rss,
                          "npu": {str(path): read_bounded(path) for path in args.npu_load}}
                samples.write(json.dumps(sample, ensure_ascii=False) + "\n")
                samples.flush()
                previous, previous_time = current, now
                if now - started > args.timeout:
                    raise TimeoutError("Candidate exceeded wall deadline; no retry")
                if (folder / "backend.log").stat().st_size > 32 * 1024 * 1024:
                    raise RuntimeError("Backend log exceeded 32 MiB")
                if process.poll() is not None:
                    break
                time.sleep(args.interval)
        state["exit_code"] = process.returncode
        report = json.loads((folder / "worker.json").read_text(encoding="utf-8"))
        state["status"] = "passed" if process.returncode == 0 and report["status"] == "passed" else "failed"
    except BaseException as error:
        state["status"] = "failed"
        state["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if process:
            try:
                stop_process(process)
            except BaseException as error:
                state["status"] = "failed"
                state["stop_error"] = {"type": type(error).__name__, "message": str(error)}
            state["exit_code"] = process.returncode
        state["wall_s"] = time.monotonic() - started
        save_json(folder / "controller.json", state)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True, help="New output directory; never overwrite a previous run")
    parser.add_argument("--smoke-text", type=Path, default=SAMPLES / "smoke-zh.txt")
    parser.add_argument("--paragraph-text", type=Path, default=SAMPLES / "benchmark-zh.txt")
    parser.add_argument("--timeout", type=float, default=300, help="Wall seconds per candidate, including preload")
    parser.add_argument("--interval", type=float, default=0.25)
    parser.add_argument("--npu-load", type=Path, action="append", help="Read-only load file; repeat if needed")
    parser.add_argument("--lock-file", type=Path, default=Path("/tmp/speech-service-benchmark.lock"))
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("Model measurements require Linux /proc and getrusage semantics")
    if args.worker:
        return worker(args.worker, args.output, args.smoke_text, args.paragraph_text)
    if not args.candidate or not 0.05 <= args.interval <= 5 or not 1 <= args.timeout <= 3600:
        parser.error("Specify candidates, interval 0.05..5, and timeout 1..3600")
    import fcntl
    lock = os.open(args.lock_file, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("Another benchmark owns the single-concurrency lock")
    args.npu_load = args.npu_load or [Path("/sys/kernel/debug/rknpu/load")]
    candidates = [(path.resolve(), load_candidate(path)) for path in args.candidate]
    if len({candidate["name"] for _, candidate in candidates}) != len(candidates):
        parser.error("Candidate names must be unique")
    args.output = args.output.resolve()
    args.smoke_text, args.paragraph_text = args.smoke_text.resolve(), args.paragraph_text.resolve()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    results = []
    for path, candidate in candidates:
        folder = args.output / candidate["name"]
        folder.mkdir(mode=0o700)
        result = run_candidate(candidate, folder, args)
        results.append(result)
        save_json(args.output / "run.json", {"results": results, "stopped_on_first_failure": True})
        print(json.dumps({"name": candidate["name"], "status": result["status"], "output": str(folder)}), flush=True)
        if result["status"] != "passed":
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
