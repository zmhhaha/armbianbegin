"""Download the fixed CPU reference and RK3588 vocoder; verify before staging."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import urllib.request

REVISION = "3f8d58c8446ec4b18891624ad4ae4ce75e0f3d3e"
ACOUSTIC_SHA256 = "524286bf6cf11be74329ae1c682ac69e34d6860c2ea9fd1290319d561540b16a"
ARTIFACTS = [
    ("matcha-icefall-zh-en.tar.bz2",
     "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/matcha-icefall-zh-en.tar.bz2",
     79033838, "271b804af570400d3bcdcb53bf6e53cc9f75180ee763b9f13eb5eaf2b0d086ef"),
    ("vocos-16khz-univ.onnx",
     "https://github.com/k2-fsa/sherpa-onnx/releases/download/vocoder-models/vocos-16khz-univ.onnx",
     53882848, "b599142a1fb8ff03de3e84ac35ff537c619e56f4267a6fe894851a42844acf9e"),
    ("vocos-16khz-600.rknn",
     f"https://hf-mirror.com/harvestsu/seeed-local-voice-rk-artifacts/resolve/{REVISION}/rk3588/opt/tts/models/vocos-16khz-600.rknn",
     27907697, "963e73f78bfee9f021850f5d2a6a712db691efbaa4b6c46ef460af1200f98ed4"),
]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def fetch(path: Path, url: str, size: int, sha256: str) -> None:
    if path.is_symlink():
        raise RuntimeError("artifact destination must not be a symlink: " + path.name)
    if path.exists():
        if not path.is_file() or path.stat().st_size != size or digest(path) != sha256:
            raise RuntimeError("existing artifact checksum/size mismatch; inspect before replacing: " + path.name)
        print(json.dumps({"verified_existing": path.name}), flush=True)
        return
    temp = path.with_name(path.name + ".part")
    if temp.is_symlink():
        raise RuntimeError("partial artifact destination must not be a symlink")
    h = hashlib.sha256()
    count = 0
    request = urllib.request.Request(url, headers={"User-Agent": "speech-service-lab"})
    with urllib.request.urlopen(request, timeout=30) as response, temp.open("wb") as output:
        while data := response.read(1024 * 1024):
            count += len(data)
            if count > size:
                raise RuntimeError("download exceeded declared size: " + path.name)
            h.update(data)
            output.write(data)
    if count != size or h.hexdigest() != sha256:
        raise RuntimeError("artifact checksum/size mismatch: " + path.name)
    os.replace(temp, path)
    print(json.dumps({"downloaded": path.name, "bytes": count, "sha256": sha256}), flush=True)


def extract_frontend(archive: Path, root: Path) -> None:
    root = root.absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise RuntimeError("frontend root and ancestors must not be symlinks")
    root = root.resolve()
    _, _, archive_size, archive_sha256 = ARTIFACTS[0]
    if (archive.is_symlink() or not archive.is_file() or archive.stat().st_size != archive_size
            or digest(archive) != archive_sha256):
        raise RuntimeError("frontend archive does not match the pinned size/SHA256")
    marker = root / ".frontend-verified.json"
    if marker.is_symlink():
        raise RuntimeError("frontend marker must not be a symlink")
    previous = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else None
    if previous is not None and previous.get("archive_sha256") != archive_sha256:
        raise RuntimeError("frontend marker does not match the pinned archive")
    inventory = {}
    total = 0
    with tarfile.open(archive, "r:bz2") as tar:
        for member in tar:
            name = member.name
            parts = PurePosixPath(name).parts
            if (not parts or parts[0] != "matcha-icefall-zh-en" or "\\" in name
                    or any(p in ("", ".", "..") for p in name.rstrip("/").split("/"))):
                raise RuntimeError("unexpected frontend archive path")
            if member.isdir():
                continue
            if not member.isfile():
                raise RuntimeError("frontend links/special files are unsupported")
            if name in inventory:
                raise RuntimeError("duplicate frontend archive path")
            total += member.size
            if total > 512 * 1024 * 1024:
                raise RuntimeError("frontend extraction exceeds budget")
            target = root.joinpath(*parts)
            if (any(p.is_symlink() for p in (target, *target.parents))
                    or not target.resolve().is_relative_to(root)):
                raise RuntimeError("unsafe frontend destination")
            if previous is not None and not target.is_file():
                raise RuntimeError("verified frontend file is missing: " + name)
            if target.exists() and not target.is_file():
                raise RuntimeError("frontend destination is not a regular file: " + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = tar.extractfile(member)
            if stream is None:
                raise RuntimeError("frontend member cannot be read")
            # Existing files are compared, never silently repaired. A legacy
            # marker authorizes no bytes: hashes come from the verified tar.
            output = None if target.exists() else target.open("xb")
            count, checksum = 0, hashlib.sha256()
            try:
                while data := stream.read(1024 * 1024):
                    count += len(data)
                    checksum.update(data)
                    if output is not None:
                        output.write(data)
            finally:
                if output is not None:
                    output.close()
            if count != member.size:
                raise RuntimeError("frontend archive member is truncated: " + name)
            row = {"bytes": count, "sha256": checksum.hexdigest()}
            if target.stat().st_size != count or digest(target) != row["sha256"]:
                raise RuntimeError("existing frontend checksum/size mismatch: " + name)
            inventory[name] = row
    acoustic = inventory.get("matcha-icefall-zh-en/model-steps-3.onnx", {})
    if acoustic.get("sha256") != ACOUSTIC_SHA256:
        raise RuntimeError("reference acoustic model differs from the RK artifact acoustic model")
    for target in (root / "matcha-icefall-zh-en").rglob("*"):
        if target.is_symlink() or (not target.is_dir() and target.relative_to(root).as_posix() not in inventory):
            raise RuntimeError("unexpected file in frontend closure: " + str(target))
    if previous is not None:
        if previous.get("bytes") != total:
            raise RuntimeError("frontend marker byte count differs from verified archive")
        if previous.get("inventory") is not None and previous["inventory"] != inventory:
            raise RuntimeError("frontend marker inventory differs from verified archive")
    data = {"schema_version": 2, "archive_sha256": archive_sha256, "bytes": total, "inventory": inventory}
    temporary = marker.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(marker)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--cpu-only", action="store_true", help="Stage the CPU baseline before the NPU vocoder")
    args = parser.parse_args()
    root = args.root.absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        parser.error("root and ancestors must not be symlinks")
    root.mkdir(parents=True, exist_ok=True)
    rows = ARTIFACTS[:2] if args.cpu_only else ARTIFACTS
    for name, url, size, sha256 in rows:
        fetch(root / name, url, size, sha256)
        if name.endswith(".tar.bz2"):
            extract_frontend(root / name, root)
    print(json.dumps({"ready": True, "mode": "cpu" if args.cpu_only else "hybrid", "root": str(root)}), flush=True)


if __name__ == "__main__":
    main()
