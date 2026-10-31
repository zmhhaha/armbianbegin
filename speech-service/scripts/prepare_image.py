"""Stage only verified non-model image inputs from the prepared speech lab.

Does not download, install, execute vendor code, or copy credentials/evidence.
The container places the private runtime in its own /usr/lib; host libraries
and the original prepared source remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from prepare_source import ARCHIVE_SHA256, REVISION, verify_source
from download_runtime import SHA256 as RUNTIME_SHA256, SIZE as RUNTIME_SIZE

ENGLISH_WHEEL = "en_core_web_sm-3.8.0-py3-none-any.whl"
ENGLISH_SHA256 = "1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85"
ENGLISH_BYTES = 12806118


def safe(path: Path) -> None:
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise RuntimeError("image inputs and destinations must not use symlinks")


def checked(path: Path, *, sha256: str, size: int) -> bytes:
    safe(path)
    if not path.is_file() or path.stat().st_size != size:
        raise RuntimeError("required image input missing or wrong size: " + path.name)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise RuntimeError("required image input checksum mismatch: " + path.name)
    return data


def write(path: Path, data: bytes) -> None:
    safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o644)


def prepare(root: Path) -> dict:
    root = root.absolute()
    safe(root)
    source_receipt = root / ".state/source.json"
    safe(source_receipt)
    data = json.loads(source_receipt.read_text(encoding="utf-8"))
    if data.get("revision") != REVISION or data.get("archive_sha256") != ARCHIVE_SHA256:
        raise RuntimeError("prepared source differs from the fixed review")
    inventory = data.get("inventory")
    if not isinstance(inventory, dict):
        raise RuntimeError("prepared source needs the complete version-2 inventory")
    source = root / "vendor" / ("rkvoice-stream-" + REVISION)
    verify_source(source, inventory)
    runtime = checked(root / "lib/librknnrt.so", sha256=RUNTIME_SHA256, size=RUNTIME_SIZE)
    english = checked(root / ".cache" / ENGLISH_WHEEL,
                      sha256=ENGLISH_SHA256, size=ENGLISH_BYTES)

    staged = root / ".image"
    safe(staged)
    expected = {"receipt.json", "runtime/librknnrt.so", "frontend/" + ENGLISH_WHEEL}
    expected.update("source/" + name for name in inventory)
    if staged.exists():
        for path in staged.rglob("*"):
            safe(path)
            if not path.is_dir() and (not path.is_file() or path.relative_to(staged).as_posix() not in expected):
                raise RuntimeError("unexpected existing image input; inspect it before staging")
    for name, row in inventory.items():
        payload = checked(source / name, sha256=row["sha256"], size=row["bytes"])
        write(staged / "source" / name, payload)
    write(staged / "runtime/librknnrt.so", runtime)
    write(staged / "frontend" / ENGLISH_WHEEL, english)
    receipt = {
        "schema_version": 1,
        "source_revision": REVISION,
        "source_archive_sha256": ARCHIVE_SHA256,
        "source_inventory": inventory,
        "runtime": {"sha256": RUNTIME_SHA256, "bytes": len(runtime)},
        "english_frontend": {"sha256": ENGLISH_SHA256, "bytes": len(english)},
        "models_included": False,
    }
    write(staged / "receipt.json", (json.dumps(receipt, indent=2) + "\n").encode("utf-8"))
    return {"ready": True, "source_files": len(inventory),
            "source_bytes": sum(row["bytes"] for row in inventory.values()),
            "runtime_bytes": len(runtime), "frontend_bytes": len(english),
            "models_included": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root)), flush=True)


if __name__ == "__main__":
    main()
