"""Explicit experimental RK3588 Chinese backend; no downloads or CPU fallback.

The small subclass is tied to the reviewed source hash. It refuses an upstream
CPU profile before rendering, rather than generating fallback audio and hiding
that fact from the caller. CPU text preparation and hybrid arithmetic remain.
"""
from __future__ import annotations

import hashlib
import importlib
import os
from pathlib import Path
from typing import Mapping

MANIFEST_SHA256 = "83733c717e0ce5b76ac1295e4827cf3ad2e111955259e9d670897e100fabeb6e"
BACKEND_SHA256 = "5f9f0fa036ceb358b3ba793b6084c352d2a25f9f9f46db3f736a06007e712873"
VOICE = "zf_xiaobei"
MALE_VOICES = {"zm_yunxi", "zm_yunjian"}


def require_npu_metadata(metadata: dict, text: str) -> None:
    """Check complete source coverage and every segment's declared execution."""
    if not isinstance(metadata, dict) or metadata.get("engine") != "npu" or metadata.get("fallback") is not False:
        raise RuntimeError("speech execution did not satisfy the configured NPU route")
    segments = metadata.get("segments")
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("speech source coverage is unavailable")
    end = 0
    for item in segments:
        if (not isinstance(item, dict) or item.get("engine") != "npu" or item.get("fallback") is not False
                or item.get("finite") is not True or item.get("cancelled") is not False
                or type(item.get("source_start")) is not int or item["source_start"] != end
                or type(item.get("source_end")) is not int or not end < item["source_end"] <= len(text)
                or item.get("sentence_text") != text[end:item["source_end"]]):
            raise RuntimeError("speech segment execution or source coverage is invalid")
        end = item["source_end"]
    if end != len(text) or metadata.get("source_start") != 0 or metadata.get("source_end") != end:
        raise RuntimeError("speech source coverage is incomplete")


class RkvoiceKokoroBackend:
    def __init__(self, bundle: Path, *, frontend_threads: int = 2, voice: str = VOICE,
                 voice_directory: Path | None = None):
        if (not bundle.is_absolute() or ".." in bundle.parts or not bundle.is_dir()
                or any(p.is_symlink() for p in (bundle, *bundle.parents))):
            raise ValueError("a staged absolute Kokoro bundle directory is required")
        if type(frontend_threads) is not int or not 1 <= frontend_threads <= 4:
            raise ValueError("frontend threads must be between one and four")
        if voice not in {VOICE, *MALE_VOICES} or voice in MALE_VOICES and voice_directory is None:
            raise ValueError("a supported fixed voice and staged voice assets are required")
        self._bundle = bundle
        self._threads = frontend_threads
        self._voice = voice
        self._voice_directory = voice_directory
        self.voice_receipt = None
        self.last_metadata = None
        self._backend = None
        self._initialized = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None):
        env = os.environ if env is None else env
        if env.get("SPEECH_BACKEND") != "kokoro_convonly" or env.get("SPEECH_VOICE") not in MALE_VOICES:
            raise ValueError("explicit supported speech backend and Chinese voice are required")
        voice_directory = Path(env.get("SPEECH_VOICE_ROOT", ""))
        if not voice_directory.is_absolute():
            raise ValueError("a staged absolute male voice directory is required")
        return cls(Path(env.get("KOKORO_CONVONLY_ROOT", "")), voice=env["SPEECH_VOICE"],
                   voice_directory=voice_directory)

    def preload(self) -> None:
        if self._backend is not None:
            raise RuntimeError("speech backend is already initialized")
        # Stage all packages/models separately; startup must remain offline.
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        module = importlib.import_module("rkvoice_stream.backends.tts.kokoro_convonly")
        if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != BACKEND_SHA256:
            raise RuntimeError("speech backend source differs from the pinned review")

        voice_id = self._voice

        class NpuOnlyBackend(module.KokoroConvOnlyBackend):
            def _iter_planned_segments(self, text, language, speed, cancel):
                from .npu_planner import PlanLimits, plan_npu_segments
                # Complete the batch request's CPU plan before yielding its
                # first segment to the inherited renderer. A rejected short
                # segment can then move a parent boundary without NPU work.
                plan = plan_npu_segments(
                    text,
                    lambda fragment: self._prepare_candidate(fragment, language, speed, cancel),
                    length_error=module.PhonemeLengthError,
                    cancel_check=lambda: self._cancel(cancel, 'planning'),
                    max_natural_d=max(module.PLATFORM_TS[self.config.platform]) // 2,
                    limits=PlanLimits(max_segments=module.MAX_SEGMENTS),
                )
                for segment in plan:
                    self._cancel(cancel, 'planning')
                    yield segment

            @staticmethod
            def _request(text, speaker_id, speed, pitch_shift, kwargs):
                if kwargs.get("voice") != voice_id or kwargs.get("speaker") not in (None, voice_id):
                    raise ValueError("request voice differs from the fixed backend voice")
                options = dict(kwargs, voice=VOICE)
                if options.get("speaker") is not None:
                    options["speaker"] = VOICE
                language, route, _, rate, cancel = module.KokoroConvOnlyBackend._request(
                    text, speaker_id, speed, pitch_shift, options)
                if route != "z":
                    raise ValueError("this backend supports only Chinese narration")
                # Validation of language/rate/speaker/cancellation is retained;
                # rendering and metadata carry the actually selected voice.
                return language, route, voice_id, rate, cancel

            def _render_segment(self, prepared, profile, *args, **kwargs):
                if profile.get("fallback") is not False:
                    raise RuntimeError("input requires a disabled CPU generator profile")
                return super()._render_segment(prepared, profile, *args, **kwargs)

        config = module.KokoroConvOnlyConfig("rk3588", self._bundle, MANIFEST_SHA256,
                                            intra=self._threads, inter=1)
        self._backend = NpuOnlyBackend(config)
        try:
            self._configure_frontend()
        except Exception:
            self.cleanup()
            raise
        self._initialized = True

    def _configure_frontend(self) -> None:
        self._backend.preload()
        if not self._backend.is_ready():
            raise RuntimeError("speech backend is not ready")
        from .pronunciation import make_mixed_chinese_g2p_factory
        self._backend.frontend.g2p_factory = make_mixed_chinese_g2p_factory(
            self._backend.frontend._official_g2p)
        if self._voice in MALE_VOICES:
            from .voice_assets import load_verified_voice
            raw, self.voice_receipt = load_verified_voice(self._voice_directory, self._voice)
            import numpy as np
            # Immutable bytes back the table: no vendor file, base receipt or
            # global VOICES map is changed. Style is selected before duration
            # prediction and all downstream frontend tensors are constructed.
            table = np.frombuffer(raw, dtype="<f4").reshape(510, 1, 256)

            def male_style(route, n):
                if route != "z" or type(n) is not int or not 0 <= n < 510:
                    raise ValueError("male voice route or style index is invalid")
                return table[n]

            self._backend.frontend._voice = male_style

    def synthesize(self, text: str, *, voice: str, speed: float) -> bytes:
        self.last_metadata = None
        if not self._initialized or self._backend is None or voice != self._voice:
            raise RuntimeError("speech backend is unavailable for this voice")
        payload, metadata = self._backend.synthesize(text, language="zh", voice=voice, speed=speed)
        require_npu_metadata(metadata, text)
        if metadata.get("voice") != self._voice or any(
                item.get("voice") != self._voice for item in metadata["segments"]):
            raise RuntimeError("speech output voice binding is inconsistent")
        self.last_metadata = metadata
        return payload

    def cleanup(self) -> None:
        self._initialized = False
        if self._backend is not None:
            try:
                self._backend.cleanup()
            finally:
                self._backend = None
