"""No models required: reject fallback and incomplete segment bindings."""
from pathlib import Path
import hashlib
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speech_service.rkvoice_backend import RkvoiceKokoroBackend, require_npu_metadata
from speech_service import voice_assets


def segment(start, end, text):
    return {"engine": "npu", "fallback": False, "finite": True, "cancelled": False,
            "source_start": start, "source_end": end, "sentence_text": text}


class BindingTests(unittest.TestCase):
    def test_failed_male_voice_preload_cannot_render_default_female_style(self):
        events = []

        class Upstream:
            def __init__(self, config):
                self.frontend = SimpleNamespace(_official_g2p=lambda route: lambda text: text)

            def preload(self):
                events.append("base_ready")

            def is_ready(self):
                return True

            def cleanup(self):
                events.append("cleanup")

            def synthesize(self, *args, **kwargs):
                events.append("wrong_female_render")

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "upstream.py"
            source.write_bytes(b"reviewed fixture source")
            module = SimpleNamespace(__file__=str(source), KokoroConvOnlyBackend=Upstream,
                                     KokoroConvOnlyConfig=lambda *args, **kwargs: args)
            backend = RkvoiceKokoroBackend(Path(directory), voice="zm_yunjian", voice_directory=Path(directory))
            with patch("speech_service.rkvoice_backend.BACKEND_SHA256", hashlib.sha256(source.read_bytes()).hexdigest()), \
                    patch("speech_service.rkvoice_backend.importlib.import_module", return_value=module), \
                    patch.object(voice_assets, "load_verified_voice", side_effect=ValueError("invalid male asset")):
                with self.assertRaises(ValueError):
                    backend.preload()
            with self.assertRaises(RuntimeError):
                backend.synthesize("测试", voice="zm_yunjian", speed=1.0)
            self.assertEqual(events, ["base_ready", "cleanup"])
            self.assertIsNone(backend._backend)

    def test_operator_configuration_requires_a_supported_male_voice(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {"SPEECH_BACKEND": "kokoro_convonly", "SPEECH_VOICE": "zm_yunxi",
                   "KOKORO_CONVONLY_ROOT": directory, "SPEECH_VOICE_ROOT": directory}
            self.assertEqual(RkvoiceKokoroBackend.from_env(env)._voice, "zm_yunxi")
            for changes in ({"SPEECH_VOICE": "zf_xiaobei"}, {"SPEECH_VOICE": "unknown"},
                            {"SPEECH_VOICE_ROOT": "relative"}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    RkvoiceKokoroBackend.from_env({**env, **changes})

    def test_cpu_profile_is_refused_before_parent_renderer_is_called(self):
        rendered = []

        class Upstream:
            def __init__(self, config):
                self.frontend = SimpleNamespace(_official_g2p=lambda route: lambda text: text)

            def preload(self):
                pass

            def is_ready(self):
                return True

            def _render_segment(self, prepared, profile, *args, **kwargs):
                rendered.append(profile)
                return b"npu-output"

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "upstream.py"
            source.write_bytes(b"reviewed fixture source")
            module = SimpleNamespace(__file__=str(source), KokoroConvOnlyBackend=Upstream,
                                     KokoroConvOnlyConfig=lambda *args, **kwargs: args)
            with patch("speech_service.rkvoice_backend.BACKEND_SHA256", hashlib.sha256(source.read_bytes()).hexdigest()), \
                    patch("speech_service.rkvoice_backend.importlib.import_module", return_value=module):
                backend = RkvoiceKokoroBackend(Path(directory))
                backend.preload()
            with self.assertRaises(RuntimeError):
                backend._backend._render_segment(None, {"fallback": True})
            self.assertEqual(rendered, [])
            self.assertEqual(backend._backend._render_segment(None, {"fallback": False}), b"npu-output")
            self.assertEqual(rendered, [{"fallback": False}])

    def test_complete_multi_segment_source(self):
        require_npu_metadata({"engine": "npu", "fallback": False, "source_start": 0, "source_end": 4,
                              "segments": [segment(0, 2, "测试"), segment(2, 4, "旁白")]}, "测试旁白")

    def test_reject_cpu_fallback_or_unknown_metadata(self):
        for metadata in ({}, {"engine": "cpu", "fallback": True},
                         {"engine": "mixed", "fallback": False},
                         {"engine": "npu", "fallback": False, "segments": []}):
            with self.subTest(metadata=metadata), self.assertRaises(RuntimeError):
                require_npu_metadata(metadata, "测试")

    def test_reject_missing_overlap_wrong_text_and_untrusted_segment(self):
        for changes in ({"source_start": 1}, {"source_end": 1}, {"sentence_text": "其他"},
                        {"engine": "cpu"}, {"fallback": True}, {"cancelled": True},
                        {"finite": False}, {"source_start": False}):
            item = {**segment(0, 2, "测试"), **changes}
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                require_npu_metadata({"engine": "npu", "fallback": False, "source_start": 0,
                                      "source_end": 2, "segments": [item]}, "测试")


if __name__ == "__main__":
    unittest.main()
