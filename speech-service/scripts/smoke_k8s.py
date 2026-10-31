"""One real in-cluster request using the externally mounted video SpeechClient.

Run in a temporary Pod with speech-client=true, a projected TOKEN_FILE, and the
original client source mounted at /client. No Kubernetes API calls, retries,
source copies, model downloads or provider switching are performed here.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import sys
from time import monotonic
import wave


CLIENT_SHA256 = "4ce02745006f5109d5975716b451718dc07a7465c18c496791152e66cb499ccd"
CONTRACTS_SHA256 = "122d2496d87cc2c2a52f8172992b6d14dc16110cf97a36507b27bc99d3b04afd"


class SmokeFailed(Exception):
    def __init__(self, code: str):
        self.code = code


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_client(root: Path):
    client_path = root / "video_workbench/speech.py"
    contracts_path = root / "agent_service/contracts.py"
    if (_sha(client_path) != CLIENT_SHA256
            or _sha(contracts_path) != CONTRACTS_SHA256):
        raise SmokeFailed("original_client_source_mismatch")
    sys.path.insert(0, str(root))
    client = importlib.import_module("video_workbench.speech")
    contracts = importlib.import_module("agent_service.contracts")
    if (Path(client.__file__).resolve() != client_path.resolve()
            or Path(contracts.__file__).resolve() != contracts_path.resolve()):
        raise SmokeFailed("original_client_import_mismatch")
    return client


def _token(path: Path) -> str:
    if not path.is_absolute() or not path.is_file():
        raise SmokeFailed("credential_unavailable")
    with path.open("rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise SmokeFailed("credential_unavailable")
    value = raw.decode("ascii").strip()
    if not value or any(not 33 <= ord(c) <= 126 for c in value):
        raise SmokeFailed("credential_unavailable")
    return value


def _run(args) -> dict:
    module = _load_client(args.client_root.resolve())
    # Configuration is operator supplied; request bodies never select an origin.
    settings = module.SpeechSettings(
        base_url=os.environ.get("BASE_URL", ""),
        model=os.environ.get("SPEECH_MODEL", "kokoro-rk3588"),
        voice=os.environ.get("SPEECH_VOICE", "zm_yunjian"),
        token=_token(Path(os.environ.get("TOKEN_FILE", ""))),
        connect_timeout=5.0, read_timeout=120.0, total_timeout=120.0,
    )
    if not settings.base_url.endswith("/v1"):
        raise SmokeFailed("api_prefix_invalid")
    with args.text_file.open("rb") as stream:
        raw = stream.read(16 * 1024 + 1)
    if len(raw) > 16 * 1024:
        raise SmokeFailed("text_invalid")
    text = raw.decode("utf-8").strip()
    if not 1 <= len(text) <= 2000:
        raise SmokeFailed("text_invalid")

    # Claim the attempt before any HTTP request; rerunning an ambiguous smoke
    # cannot issue another synthesis using an existing evidence directory.
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "attempt.json").open("x", encoding="utf-8") as stream:
        json.dump({"text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                   "client_source_sha256": CLIENT_SHA256}, stream)

    import httpx

    payload = dict(model=settings.model, input=text, voice=settings.voice,
                   speed=1.0, response_format="wav")
    endpoint = settings.base_url + "/audio/speech"
    # Reject checks run first. Unexpected acceptance aborts the entire smoke;
    # no successful synthesis request is then issued automatically.
    with httpx.Client(transport=httpx.HTTPTransport(retries=0),
                      trust_env=False, follow_redirects=False, timeout=5.0) as raw_client:
        response = raw_client.post(endpoint, json=payload)
        unauthorized = response.status_code
        response.close()
        if unauthorized != 401:
            raise SmokeFailed("unauthenticated_request_not_rejected")
        bad_model = "__smoke_invalid_model__"
        if bad_model == settings.model:
            bad_model = "__other_invalid_model__"
        response = raw_client.post(
            endpoint, json=dict(payload, model=bad_model),
            headers={"Authorization": "Bearer " + settings.token},
        )
        rejected_model = response.status_code
        response.close()
        if rejected_model != 422:
            raise SmokeFailed("wrong_model_not_rejected")

    started = monotonic()
    # This is the original application class, not a substitute HTTP adapter.
    with module.SpeechClient(settings) as client:
        audio = client.synthesize(text, speed=1.0)
    elapsed = monotonic() - started
    # The original client validates every PCM frame and all RIFF boundaries.
    # Tighten the smoke to the actual configured backend's PCM16 mono format,
    # and independently reject all-zero decoded frames.
    with wave.open(io.BytesIO(audio.data), "rb") as wav:
        frames = wav.readframes(wav.getnframes())
        if (wav.getsampwidth() != 2 or wav.getnchannels() != 1
                or wav.getframerate() != 24000 or not any(frames)):
            raise SmokeFailed("unexpected_backend_audio")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / "sample.wav"
    # A new output path prevents a failed/repeated Pod run from masquerading as
    # the current run by overwriting or accidentally retaining an older sample.
    with target.open("xb") as stream:
        stream.write(audio.data)
    return {
        "status": "passed",
        "voice": settings.voice,
        "model": settings.model,
        "client_source_sha256": CLIENT_SHA256,
        "contracts_source_sha256": CONTRACTS_SHA256,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text_characters": len(text),
        "input_sha256": audio.input_sha256,
        "synthesis_requests": 1,
        "automatic_retries": 0,
        "without_token_status": unauthorized,
        "wrong_model_status": rejected_model,
        "elapsed_seconds": elapsed,
        "audio_seconds": audio.duration_seconds,
        "sample_rate": audio.sample_rate,
        "channels": audio.channels,
        "sample_width": audio.sample_width,
        "frame_count": audio.frame_count,
        "audio_bytes": len(audio.data),
        "audio_sha256": audio.sha256,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-root", type=Path, default=Path("/client"))
    parser.add_argument("--text-file", type=Path, default=Path("/client/benchmark-zh.txt"))
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/evidence"))
    args = parser.parse_args()
    try:
        report = _run(args)
    except SmokeFailed as exc:
        report = {"status": "failed", "code": exc.code}
    except Exception:
        # Never expose request text, origins, credentials, response bodies,
        # exception strings or projected Secret paths in Pod logs.
        report = {"status": "failed", "code": "smoke_execution_failed"}
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False)
    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        with (args.output_dir / "report.json").open("x", encoding="utf-8") as stream:
            stream.write(rendered + "\n")
    except OSError:
        print(json.dumps({"status": "failed", "code": "evidence_write_failed"}))
        return 1
    print(rendered, flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
