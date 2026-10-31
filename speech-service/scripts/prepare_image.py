"""Stage only verified non-model image inputs from the prepared speech lab.

Does not download, install, execute vendor code, or copy credentials/evidence.
The container places the private runtime in its own /usr/lib; host libraries
and the original prepared source remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path, PurePosixPath
import platform
import re

from prepare_source import ARCHIVE_SHA256, REVISION, verify_source
from download_runtime import SHA256 as RUNTIME_SHA256, SIZE as RUNTIME_SIZE

ENGLISH_WHEEL = "en_core_web_sm-3.8.0-py3-none-any.whl"
ENGLISH_SHA256 = "1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85"
ENGLISH_BYTES = 12806118
MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024
MAX_PACKAGE_FILE_BYTES = 128 * 1024 * 1024
MAX_PACKAGE_FILES = 100000
# coloredlogs' optional interpreter-startup auto_install hook is unused by this
# service. Omit only the exact reviewed file; keep the package itself importable.
OMITTED_PACKAGE_HOOKS = {
    ("coloredlogs", "coloredlogs.pth"): {
        "bytes": 147,
        "sha256": "dda83a855986efa5cd87f0248b0199c0086eb0e8e7fece7d6741959c5ce39536",
    }
}


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


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def package_inventory(root: Path) -> tuple[Path, dict, dict, list]:
    """Select installed data without importing packages or trusting path hooks.

    Host executables, virtualenv links, editable installs, bytecode, and installer
    RECORD/direct_url files are never image inputs. Two distributions may share
    an installed namespace file; the snapshot records its actual bytes once.
    """
    if platform.system() != "Linux" or platform.machine() not in {"aarch64", "arm64"}:
        raise RuntimeError("package snapshot requires the verified Linux ARM64 worker")
    site = root / ".venv/lib/python3.11/site-packages"
    safe(site)
    if not site.is_dir():
        raise RuntimeError("the verified CPython 3.11 environment is required")
    requirements = root / "requirements-container.txt"
    safe(requirements)
    pinned = {}
    for line in requirements.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9.+!-]*)", line)
        if match is None or canonical(match[1]) in pinned:
            raise RuntimeError("container requirements must contain unique exact versions")
        pinned[canonical(match[1])] = match[2]
    if not pinned or any(name in pinned for name in {"pip", "setuptools", "rkvoice-stream", "en-core-web-sm"}):
        raise RuntimeError("snapshot packages must be the reviewed dependency closure")
    installed = {}
    for dist in metadata.distributions(path=[str(site)]):
        name = canonical(dist.metadata.get("Name", ""))
        if name not in pinned:
            continue
        if name in installed:
            raise RuntimeError("duplicate installed distribution metadata: " + name)
        if dist.version != pinned[name]:
            raise RuntimeError("installed version differs from the pinned requirement: " + name)
        direct = dist.read_text("direct_url.json")
        if direct and json.loads(direct).get("dir_info", {}).get("editable"):
            raise RuntimeError("editable distributions cannot become container inputs")
        installed[name] = dist
    if set(installed) != set(pinned):
        raise RuntimeError("a pinned container dependency is not installed")
    files = {}
    omissions = []
    total = 0
    for name in sorted(installed):
        rows = installed[name].files
        if rows is None:
            raise RuntimeError("installed distribution has no file inventory: " + name)
        copied = 0
        for row in rows:
            relative = row.as_posix()
            parts = PurePosixPath(relative).parts
            if (not parts or "\\" in relative or "\0" in relative
                    or PurePosixPath(relative).is_absolute()):
                raise RuntimeError("unsafe installed distribution path")
            # Installer-generated command entry points are outside site-packages.
            if ".." in parts:
                if parts[:4] == ("..", "..", "..", "bin") and len(parts) == 5:
                    continue
                if name == "sympy" and relative == "../../../share/man/man1/isympy.1":
                    continue  # Reviewed optional CLI manpage, not runtime data.
                raise RuntimeError("unexpected distribution path outside site-packages: " + name + ":" + relative)
            if PurePosixPath(relative).as_posix() != relative or any(p in {"", "."} for p in relative.split("/")):
                raise RuntimeError("noncanonical installed distribution path")
            if ("__pycache__" in parts or parts[-1].endswith((".pyc", ".pyo"))
                    or len(parts) >= 2 and parts[-2].endswith(".dist-info")
                    and parts[-1] in {"RECORD", "direct_url.json"}):
                continue
            if parts[-1].endswith((".pth", ".egg-link")) or any(p.startswith("__editable__") for p in parts):
                omitted = OMITTED_PACKAGE_HOOKS.get((name, relative))
                if omitted is not None:
                    checked(site / relative, sha256=omitted["sha256"], size=omitted["bytes"])
                    omissions.append({"distribution": name, "path": relative, **omitted,
                                      "reason": "unused optional coloredlogs auto-install hook"})
                    continue
                raise RuntimeError("installed Python path hooks cannot become container inputs: " + name + ":" + relative)
            target = site.joinpath(*parts)
            safe(target)
            if not target.is_file():
                raise RuntimeError("installed package file is missing or special: " + relative)
            size = target.stat().st_size
            if not 0 <= size <= MAX_PACKAGE_FILE_BYTES:
                raise RuntimeError("installed package file exceeds snapshot budget")
            if relative not in files:
                files[relative] = {"bytes": size, "owners": []}
                total += size
                if total > MAX_PACKAGE_BYTES or len(files) > MAX_PACKAGE_FILES:
                    raise RuntimeError("installed package closure exceeds snapshot budget")
            files[relative]["owners"].append(name)
            copied += 1
        if not copied:
            raise RuntimeError("installed distribution has no usable files: " + name)
    return site, pinned, files, omissions


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
    site, versions, package_files, package_omissions = package_inventory(root)

    staged = root / ".image"
    safe(staged)
    expected = {"receipt.json", "python-packages.json", "runtime/librknnrt.so", "frontend/" + ENGLISH_WHEEL}
    expected.update("source/" + name for name in inventory)
    expected.update("site-packages/" + name for name in package_files)
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
    for name, row in package_files.items():
        source_file = site / name
        safe(source_file)
        payload = source_file.read_bytes()
        if len(payload) != row["bytes"]:
            raise RuntimeError("installed package changed while snapshotting")
        row["sha256"] = hashlib.sha256(payload).hexdigest()
        write(staged / "site-packages" / name, payload)
    package_receipt = {
        "schema_version": 1,
        "platform": "linux-aarch64",
        "python_abi": "cp311",
        "versions": versions,
        "files": package_files,
        "reviewed_omissions": package_omissions,
    }
    package_json = (json.dumps(package_receipt, indent=2) + "\n").encode("utf-8")
    write(staged / "python-packages.json", package_json)
    receipt = {
        "schema_version": 2,
        "source_revision": REVISION,
        "source_archive_sha256": ARCHIVE_SHA256,
        "source_inventory": inventory,
        "runtime": {"sha256": RUNTIME_SHA256, "bytes": len(runtime)},
        "english_frontend": {"sha256": ENGLISH_SHA256, "bytes": len(english)},
        "python_packages": {"sha256": hashlib.sha256(package_json).hexdigest(),
                            "distributions": len(versions), "files": len(package_files),
                            "bytes": sum(row["bytes"] for row in package_files.values())},
        "models_included": False,
    }
    write(staged / "receipt.json", (json.dumps(receipt, indent=2) + "\n").encode("utf-8"))
    return {"ready": True, "source_files": len(inventory),
            "source_bytes": sum(row["bytes"] for row in inventory.values()),
            "runtime_bytes": len(runtime), "frontend_bytes": len(english),
            "package_files": len(package_files), "distributions": len(versions),
            "package_bytes": sum(row["bytes"] for row in package_files.values()),
            "models_included": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root)), flush=True)


if __name__ == "__main__":
    main()
