"""Meaningful offline media/evidence checks; never imports a TTS runtime."""
import io
from pathlib import Path
import struct
import sys
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent))
from benchmark import (InferenceTrace, NoNPUImports, assess_execution, trace_delta,
                       validate_cpu_config, validate_wav)


def audio(samples=(1000, -1000) * 8000):
    output = io.BytesIO()
    with wave.open(output, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    return output.getvalue()


class MediaAndEvidence(unittest.TestCase):
    def cpu_evidence(self, *, calls=None, runtime_changes=None, metadata_changes=None):
        runtime = {"provider": "cpu", "acoustic_engine": "cpu", "vocoder_engine": "cpu",
                   "frontend": "sherpa native lexicon/FST; differs from rkvoice frontend",
                   "npu_python_import_guard": "blocked", "npu_import_attempts": [], "npu_modules_loaded": []}
        runtime.update(runtime_changes or {})
        metadata = {"engine": "cpu", "provider": "cpu", "fallback": False,
                    "acoustic_engine": "cpu", "vocoder_engine": "cpu"}
        metadata.update(metadata_changes or {})
        return assess_execution({"backend": "sherpa_matcha_cpu"},
            {"name": "sherpa_matcha_cpu", "ready": True, "runtime_info": runtime}, metadata, calls or {})

    def test_cpu_reference_passes_without_npu_and_keeps_frontend_difference(self):
        evidence = self.cpu_evidence()
        self.assertTrue(evidence["qualification_passed"])
        self.assertEqual(evidence["execution_class"], "cpu_reference")
        self.assertFalse(evidence["npu_runtime_calls_observed"])
        self.assertEqual(evidence["npu_runtime_call_attempts"], 0)
        self.assertEqual(evidence["backend_report"]["comparison_class"],
                         "complete_cpu_reference_different_frontend")

    def test_cpu_reference_rejects_successful_or_failed_npu_call(self):
        for successes, failures in ((1, 0), (0, 1)):
            with self.subTest(successes=successes):
                evidence = self.cpu_evidence(calls={"rknn": {
                    "calls": 1, "successful_returns": successes, "failed_calls": failures}})
                self.assertFalse(evidence["qualification_passed"])

    def test_cpu_reference_rejects_wrong_provider_imports_or_fallback(self):
        for changes in ({"metadata_changes": {"provider": "rknn"}},
                        {"metadata_changes": {"fallback": True}},
                        {"runtime_changes": {"npu_import_attempts": ["rknnlite.api"]}},
                        {"runtime_changes": {"npu_modules_loaded": ["rknnlite.api"]}},
                        {"runtime_changes": {"provider": "cuda"}}):
            with self.subTest(changes=changes):
                self.assertFalse(self.cpu_evidence(**changes)["qualification_passed"])

    def test_cpu_config_cannot_override_provider(self):
        config = {"acoustic": "/models/acoustic.onnx", "vocoder": "/models/vocos.onnx",
                  "tokens": "/models/tokens.txt", "lexicons": ["/models/lexicon.txt"],
                  "rule_fsts": ["/models/number-zh.fst"], "num_threads": 4, "noise_scale": 0.667}
        validate_cpu_config(config)
        with self.assertRaises(ValueError):
            validate_cpu_config({**config, "provider": "rknn"})

    def test_cpu_import_guard_blocks_npu_and_leaves_normal_imports_available(self):
        guard = NoNPUImports()
        self.assertIsNone(guard.find_spec("numpy"))
        with self.assertRaisesRegex(ImportError, "forbids NPU"):
            guard.find_spec("rknnlite.api")
        self.assertEqual(guard.evidence()["npu_import_attempts"], ["rknnlite.api"])

    def test_runtime_observer_delegates_once_and_keeps_model_identity(self):
        class Runtime:
            def __init__(self):
                self.attempts = 0

            def load_rknn(self, path):
                return 0

            def inference(self, result):
                self.attempts += 1
                if isinstance(result, Exception):
                    raise result
                return result

        trace = InferenceTrace()
        trace.install(Runtime, "test-runtime")
        runtime = Runtime()
        runtime.load_rknn("/models/vocos.rknn")
        sentinel = object()
        self.assertIs(runtime.inference(sentinel), sentinel)
        with self.assertRaisesRegex(ValueError, "failed inference"):
            runtime.inference(ValueError("failed inference"))
        self.assertIsNone(runtime.inference(None))
        self.assertEqual(runtime.attempts, 3)
        self.assertEqual(trace.snapshot(), {"test-runtime | /models/vocos.rknn": {
            "calls": 3, "successful_returns": 1, "failed_calls": 2}})

    def test_capi_observer_maps_constructor_model_without_loading_native_library(self):
        class NativeRuntime:
            def __init__(self, model_path, core_mask=0):
                self.model_path = model_path
                self.core_mask = core_mask

            def inference(self, inputs):
                return inputs

        trace = InferenceTrace()
        trace.install(NativeRuntime, "native-runtime")
        runtime = NativeRuntime("/models/kokoro.rknn", core_mask=3)
        inputs = [object()]
        self.assertIs(runtime.inference(inputs), inputs)
        self.assertEqual(runtime.core_mask, 3)
        self.assertEqual(trace.snapshot(), {"native-runtime | /models/kokoro.rknn": {
            "calls": 1, "successful_returns": 1, "failed_calls": 0}})

    def test_duration_is_real_pcm_frames(self):
        info = validate_wav(audio())
        self.assertEqual(info["duration_s"], 1)
        self.assertEqual(info["frames"], 16000)
        self.assertEqual(len(info["sha256"]), 64)

    def test_streaming_length_is_rejected(self):
        data = bytearray(audio())
        struct.pack_into("<I", data, 4, 0xFFFFFFFF)
        with self.assertRaises(ValueError):
            validate_wav(bytes(data))

    def test_truncated_pcm_and_silence_are_rejected(self):
        data = bytearray(audio()[:-2])
        struct.pack_into("<I", data, 4, len(data) - 8)
        for payload in (bytes(data), audio((0,) * 16000)):
            with self.subTest(length=len(payload)), self.assertRaises(ValueError):
                validate_wav(payload)

    def test_readiness_without_inference_is_not_npu_success(self):
        evidence = assess_execution({"backend": "matcha_rknn"},
            {"name": "matcha_rknn", "ready": True, "matcha_acoustic_backend": "rknn"}, {}, {})
        self.assertFalse(evidence["qualification_passed"])

    def test_vocoder_calls_do_not_hide_acoustic_cpu_fallback(self):
        calls = {"rknn": {"calls": 1, "successful_returns": 1, "failed_calls": 0}}
        evidence = assess_execution({"backend": "matcha_rknn"},
            {"name": "matcha_rknn", "ready": True, "matcha_acoustic_backend": "ort"}, {}, calls)
        self.assertTrue(evidence["fallback_detected"])
        self.assertFalse(evidence["qualification_passed"])

    def test_kokoro_mixed_segments_are_not_all_npu(self):
        calls = {"rknn": {"calls": 3, "successful_returns": 3, "failed_calls": 0}}
        evidence = assess_execution({"backend": "kokoro_convonly"},
            {"name": "kokoro_convonly", "ready": True},
            {"engine": "mixed", "fallback": True, "segments": [
                {"engine": "npu", "fallback": False}, {"engine": "cpu", "fallback": True}]}, calls)
        self.assertTrue(evidence["fallback_detected"])
        self.assertFalse(evidence["qualification_passed"])

    def test_explicit_cpu_acoustic_npu_vocoder_is_labeled_hybrid(self):
        calls = {"vocos.rknn": {"calls": 1, "successful_returns": 1, "failed_calls": 0}}
        evidence = assess_execution({"backend": "matcha_rknn", "expected_matcha_backend": "ort"},
            {"name": "matcha_rknn", "ready": True, "matcha_acoustic_backend": "ort"}, {}, calls)
        self.assertTrue(evidence["qualification_passed"])
        self.assertTrue(evidence["backend_report"]["intentional_cpu_acoustic"])
        self.assertFalse(evidence["fallback_detected"])

    def test_preload_calls_are_not_credited_to_synthesis(self):
        previous = {"rknn": {"calls": 4, "successful_returns": 4, "failed_calls": 0}}
        current = {"rknn": {"calls": 5, "successful_returns": 5, "failed_calls": 0}}
        delta = trace_delta(previous, current)
        self.assertEqual(delta["rknn"]["successful_returns"], 1)
        evidence = assess_execution({"backend": "matcha_rknn", "expected_matcha_backend": "rknn"},
            {"name": "matcha_rknn", "ready": True, "matcha_acoustic_backend": "rknn"}, {}, delta)
        self.assertTrue(evidence["qualification_passed"])


if __name__ == "__main__":
    unittest.main()
