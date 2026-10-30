"""Stage the reviewed RKVoice source into this service's private vendor folder.

This downloads source only. It never installs or imports upstream packages.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import urllib.request

REVISION = "f2c2d730403e1d4c732add799f0414da34695043"
URL = f"https://codeload.github.com/suharvest/rkvoice-stream/tar.gz/{REVISION}"
ARCHIVE_SHA256 = "52aee0cb7f1bf25a04ad01ee906f27b7b665df22b2d266cfea97a7e43460718c"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
PREFIXES = ("rkvoice_stream/", "native/", "tools/", "configs/")
ROOT_FILES = {"pyproject.toml", "README.md", "LICENSE"}


def selected_path(relative: str) -> bool:
    return relative in ROOT_FILES or relative.startswith(PREFIXES)


def download_archive() -> bytes:
    request = urllib.request.Request(URL, headers={"User-Agent": "speech-service-lab"})
    with urllib.request.urlopen(request, timeout=30) as response:
        archive = response.read(MAX_ARCHIVE_BYTES + 1)
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise RuntimeError("upstream archive exceeds source budget")
    if hashlib.sha256(archive).hexdigest() != ARCHIVE_SHA256:
        raise RuntimeError("source archive differs from the pinned SHA256")
    return archive


def archive_files(archive: bytes) -> dict[str, bytes]:
    expected_prefix = f"rkvoice-stream-{REVISION}/"
    selected = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar:
            if not member.name.startswith(expected_prefix):
                if member.isdir() and member.name.rstrip("/") == expected_prefix.rstrip("/"):
                    continue
                raise RuntimeError("unexpected source archive root")
            relative = member.name[len(expected_prefix):]
            if not relative or member.isdir():
                continue
            name = PurePosixPath(relative)
            if name.is_absolute() or any(p in ("", ".", "..") for p in relative.split("/")) or "\\" in relative:
                raise RuntimeError("unsafe source path")
            if not selected_path(relative):
                continue
            if not member.isfile():
                raise RuntimeError("links and special source members are unsupported")
            if relative in selected:
                raise RuntimeError("duplicate source archive path")
            total += member.size
            if total > MAX_SOURCE_BYTES:
                raise RuntimeError("selected source exceeds extracted byte budget")
            stream = tar.extractfile(member)
            if stream is None:
                raise RuntimeError("source file cannot be read")
            content = stream.read(member.size + 1)
            if len(content) != member.size:
                raise RuntimeError("source file size mismatch")
            selected[relative] = content
    if "pyproject.toml" not in selected:
        raise RuntimeError("upstream package metadata missing")
    return selected


def inventory_for(selected: dict[str, bytes]) -> dict:
    return {name: {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            for name, content in selected.items()}


def verify_source(source: Path, inventory: dict) -> None:
    if not isinstance(inventory, dict) or "pyproject.toml" not in inventory:
        raise RuntimeError("source inventory is missing package metadata")
    if any(p.is_symlink() for p in (source, *source.parents)):
        raise RuntimeError("source destination has a symlink ancestor")
    for name, row in inventory.items():
        parts = PurePosixPath(name).parts
        if (not selected_path(name) or not parts or "\\" in name
                or any(p in ("", ".", "..") for p in name.split("/"))
                or PurePosixPath(name).is_absolute()):
            raise RuntimeError("unsafe or unexpected source inventory path")
        target = source.joinpath(*parts)
        if any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file():
            raise RuntimeError("source inventory file missing or linked: " + name)
        if (target.stat().st_size != row["bytes"]
                or hashlib.sha256(target.read_bytes()).hexdigest() != row["sha256"]):
            raise RuntimeError("source inventory checksum/size mismatch: " + name)
    # setuptools build/ and *.egg-info at the source root are generated products,
    # outside the selected package/native/tools/configs closure. Python bytecode
    # caches inside that closure are also generated, never trusted source.
    for target in source.rglob("*"):
        relative = target.relative_to(source)
        name = relative.as_posix()
        if "__pycache__" in relative.parts or not selected_path(name):
            continue
        if target.is_symlink() or (not target.is_dir() and name not in inventory):
            raise RuntimeError("unexpected file in source closure: " + name)


def prepare(root: Path) -> dict:
    root = root.absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise RuntimeError("root and ancestors must not be symlinks")
    root = root.resolve()
    source = root / "vendor" / f"rkvoice-stream-{REVISION}"
    receipt = root / ".state" / "source.json"
    if any(p.is_symlink() for p in (source, source.parent, receipt, receipt.parent)):
        raise RuntimeError("source or receipt destination must not be a symlink")
    if receipt.exists():
        previous = json.loads(receipt.read_text(encoding="utf-8"))
        if (previous.get("revision") != REVISION or previous.get("archive_sha256") != ARCHIVE_SHA256
                or not source.is_dir()):
            raise RuntimeError("source receipt does not match the pinned directory/archive")
        inventory = previous.get("inventory")
        if inventory is None:
            # Legacy receipts contain counts only. Derive expected hashes from
            # the pinned remote archive, never from the possibly damaged tree.
            inventory = inventory_for(archive_files(download_archive()))
        verify_source(source, inventory)
        data = dict(previous)
    else:
        if source.exists():
            raise RuntimeError("unreceipted source destination exists; inspect before continuing")
        selected = archive_files(download_archive())
        inventory = inventory_for(selected)
        source.mkdir(parents=True)
        for name, content in selected.items():
            target = source.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        verify_source(source, inventory)
        data = {"revision": REVISION, "source": str(source), "url": URL, "archive_sha256": ARCHIVE_SHA256}
    data.update(schema_version=2, inventory=inventory,
                source_bytes=sum(row["bytes"] for row in inventory.values()), files=len(inventory))
    receipt.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(receipt)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root)), flush=True)


if __name__ == "__main__":
    main()
