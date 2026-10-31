"""Download two pinned official Kokoro voices without importing PyTorch.

Neither inspection nor conversion executes pickle. Conversion accepts only
the exact reviewed descriptor; the original strict RKNN bundle is unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pickletools
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speech_service.voice_assets import ASSETS, REVISION, REPOSITORY, archive_members, stage_voice

ALLOWED_GLOBALS = {"torch._utils _rebuild_tensor_v2", "torch FloatStorage", "collections OrderedDict"}
MAX_PICKLE_BYTES = 65536


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_asset(destination: Path, voice_id: str, endpoint: str) -> Path:
    if voice_id not in ASSETS:
        raise ValueError("unsupported voice asset")
    row = ASSETS[voice_id]
    target = destination / (voice_id + ".pt")
    if any(p.is_symlink() for p in (destination, *destination.parents, target)):
        raise ValueError("voice destination must not use symlinks")
    if target.exists():
        if not target.is_file() or target.stat().st_size != row["bytes"] or sha256(target.read_bytes()) != row["sha256"]:
            raise ValueError("existing voice differs from the fixed asset: " + voice_id)
        return target
    temporary = target.with_suffix(".pt.part")
    if temporary.is_symlink():
        raise ValueError("partial voice destination must not be a symlink")
    url = f"{endpoint}/{REPOSITORY}/resolve/{REVISION}/voices/{voice_id}.pt"
    request = urllib.request.Request(url, headers={"User-Agent": "speech-service-voice-lab"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(row["bytes"] + 1)
    if len(data) != row["bytes"] or sha256(data) != row["sha256"]:
        raise ValueError("download differs from the fixed official asset: " + voice_id)
    destination.mkdir(parents=True, exist_ok=True)
    with temporary.open("wb") as output:
        output.write(data)
    os.replace(temporary, target)
    return target


def inspect_archive(data: bytes) -> dict:
    archive, members = archive_members(data)
    with archive:
        if "data.pkl" not in members or members["data.pkl"].file_size > MAX_PICKLE_BYTES:
            raise ValueError("voice archive lacks a bounded tensor pickle")
        serialized = archive.read(members["data.pkl"])
        instructions = []
        for opcode, argument, offset in pickletools.genops(serialized):
            if len(instructions) >= 256:
                raise ValueError("voice pickle has too many instructions")
            if opcode.name == "GLOBAL" and argument not in ALLOWED_GLOBALS:
                raise ValueError("voice pickle names a forbidden global")
            if opcode.name == "STACK_GLOBAL":
                raise ValueError("stack globals require explicit format review")
            instructions.append({"offset": offset, "opcode": opcode.name, "argument": argument})
        return {"members": [{"path": name, "bytes": info.file_size} for name, info in members.items()],
                "pickle_sha256": sha256(serialized), "instructions": instructions,
                "pickle_executed": False, "converted": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--endpoint", choices=("https://huggingface.co", "https://hf-mirror.com"), default="https://huggingface.co")
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    if not args.destination.is_absolute() or ".." in args.destination.parts:
        parser.error("destination must be an absolute dedicated voice directory")
    for voice_id, expected in ASSETS.items():
        path = fetch_asset(args.destination, voice_id, args.endpoint)
        if args.inspect:
            result = {"voice_id": voice_id, "repository": REPOSITORY, "revision": REVISION,
                      "pt_sha256": expected["sha256"], "pt_bytes": expected["bytes"],
                      "inspection": inspect_archive(path.read_bytes())}
        else:
            result = stage_voice(args.destination, voice_id)
        print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
