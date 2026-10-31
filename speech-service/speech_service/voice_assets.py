"""Pinned Kokoro male voice tensors, decoded without executing any pickle.

The two reviewed files share one exact 165-byte descriptor. Its digest binds
FloatStorage/CPU/key0, offset0, shape(510,1,256), stride(256,256,1), no grad and
empty hooks. Only the corresponding little-endian storage bytes are copied.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import stat
import struct
import zipfile

REVISION = "f3ff3571791e39611d31c381e3a41a3af07b4987"
REPOSITORY = "hexgrad/Kokoro-82M"
ASSETS = {
    "zm_yunxi": {"bytes": 523425, "sha256": "dbe6e1ce7c3dbaf2f5667432947b638b1c6831ccbe154c4610dbcc44f431e27b"},
    "zm_yunjian": {"bytes": 523435, "sha256": "76cbf8bad35901d011d9628a2fdceb7b4f1f127e7a3269cb393b3941eb7fc417"},
}
DESCRIPTOR_SHA256 = "645dea33b46e50fdda6c8a43b39ec4b7adcf28e4643408c02d74fef10ff9d712"
SHAPE = (510, 1, 256)
RAW_BYTES = 522240
MAX_PT_BYTES = 1024 * 1024
MEMBERS = {"data.pkl": 165, "byteorder": 6, "data/0": RAW_BYTES,
           "version": 2, ".data/serialization_id": 40}
CONVERSION_METHOD = "descriptor-hash-checked-no-pickle"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive_members(data: bytes) -> tuple[zipfile.ZipFile, dict]:
    if type(data) is not bytes or not 0 < len(data) <= MAX_PT_BYTES:
        raise ValueError("voice archive exceeds the byte budget")
    archive = zipfile.ZipFile(io.BytesIO(data), "r")
    try:
        infos = archive.infolist()
        if not 1 <= len(infos) <= 16 or sum(info.file_size for info in infos) > MAX_PT_BYTES:
            raise ValueError("voice archive inventory exceeds the budget")
        roots, entries = set(), {}
        for info in infos:
            name = info.filename
            parts = PurePosixPath(name).parts
            if (not parts or len(parts) < 2 or PurePosixPath(name).is_absolute() or "\\" in name
                    or any(p in ("", ".", "..") for p in name.split("/"))
                    or info.is_dir() or stat.S_ISLNK(info.external_attr >> 16)
                    or info.flag_bits & 1 or info.compress_type != zipfile.ZIP_STORED
                    or name in entries):
                raise ValueError("unsupported or unsafe voice archive member")
            roots.add(parts[0])
            entries[name] = info
        if len(roots) != 1:
            raise ValueError("voice archive must have exactly one root")
        prefix = next(iter(roots)) + "/"
        return archive, {name[len(prefix):]: info for name, info in entries.items()}
    except BaseException:
        archive.close()
        raise


def decode_voice_archive(data: bytes) -> bytes:
    """Accept only the actual reviewed tensor descriptor; never unpickle it."""
    archive, members = archive_members(data)
    with archive:
        if set(members) != set(MEMBERS) or any(members[name].file_size != size for name, size in MEMBERS.items()):
            raise ValueError("voice archive differs from the reviewed member closure")
        descriptor = archive.read(members["data.pkl"])
        if sha256(descriptor) != DESCRIPTOR_SHA256:
            raise ValueError("voice tensor descriptor, globals or shape differ from the review")
        if archive.read(members["byteorder"]) != b"little":
            raise ValueError("voice storage must be explicitly little-endian")
        raw = archive.read(members["data/0"])
        if len(raw) != RAW_BYTES or not all(math.isfinite(value[0]) for value in struct.iter_unpack("<f", raw)):
            raise ValueError("voice storage is truncated or contains non-finite floats")
        return raw


def verified_pt(data: bytes, voice_id: str) -> bytes:
    if voice_id not in ASSETS:
        raise ValueError("unsupported voice asset")
    expected = ASSETS[voice_id]
    if len(data) != expected["bytes"] or sha256(data) != expected["sha256"]:
        raise ValueError("voice differs from the fixed official asset")
    return decode_voice_archive(data)


def receipt_for(voice_id: str, raw: bytes) -> dict:
    expected = ASSETS[voice_id]
    return {"schema": "speech-service.kokoro-voice.v1", "voice_id": voice_id,
            "repository": REPOSITORY, "revision": REVISION,
            "source_path": "voices/" + voice_id + ".pt", "pt_bytes": expected["bytes"],
            "pt_sha256": expected["sha256"], "descriptor_sha256": DESCRIPTOR_SHA256,
            "shape": list(SHAPE), "dtype": "float32", "byteorder": "little",
            "raw_bytes": len(raw), "raw_sha256": sha256(raw),
            "conversion_method": CONVERSION_METHOD, "pickle_executed": False}


def _safe_directory(directory: Path) -> Path:
    if (not directory.is_absolute() or ".." in directory.parts
            or any(path.is_symlink() for path in (directory, *directory.parents))):
        raise ValueError("voice directory must be absolute and must not use symlinks")
    return directory


def _bounded_file(path: Path, maximum: int) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("voice asset file is missing, linked or oversized")
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError("voice asset file exceeds its byte budget")
    return data


def stage_voice(directory: Path, voice_id: str) -> dict:
    """Create derived files only after re-verifying the fixed official .pt."""
    directory = _safe_directory(directory)
    if voice_id not in ASSETS:
        raise ValueError("unsupported voice asset")
    raw = verified_pt(_bounded_file(directory / (voice_id + ".pt"), MAX_PT_BYTES), voice_id)
    receipt = receipt_for(voice_id, raw)
    payloads = {voice_id + ".bin": raw,
                voice_id + ".receipt.json": (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode("utf-8")}
    for name, data in payloads.items():
        target = directory / name
        if target.is_symlink():
            raise ValueError("derived voice asset must not be a symlink")
        if target.exists():
            if _bounded_file(target, len(data)) != data:
                raise ValueError("existing derived voice asset differs; inspect before replacing")
            continue
        temporary = target.with_suffix(target.suffix + ".part")
        if temporary.is_symlink():
            raise ValueError("partial derived voice asset must not be a symlink")
        # A .part is never trusted; explicit reruns replace its incomplete bytes.
        with temporary.open("wb") as output:
            output.write(data)
        temporary.replace(target)
    return receipt


def load_verified_voice(directory: Path, voice_id: str) -> tuple[bytes, dict]:
    """Re-derive from pinned .pt, then compare stored raw bytes and receipt."""
    directory = _safe_directory(directory)
    if voice_id not in ASSETS:
        raise ValueError("unsupported voice asset")
    raw = verified_pt(_bounded_file(directory / (voice_id + ".pt"), MAX_PT_BYTES), voice_id)
    expected = receipt_for(voice_id, raw)
    stored = _bounded_file(directory / (voice_id + ".bin"), RAW_BYTES)
    if stored != raw:
        raise ValueError("derived voice bytes differ from the fixed official tensor")
    receipt = _bounded_file(directory / (voice_id + ".receipt.json"), 8192)
    if receipt != (json.dumps(expected, sort_keys=True, indent=2) + "\n").encode("utf-8"):
        raise ValueError("voice receipt differs from the verified conversion")
    return raw, expected
