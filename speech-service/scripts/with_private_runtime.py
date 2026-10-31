"""Run a lab command with Lite2's required library path in a private mount namespace.

No host library is installed or replaced. The temporary overlay and all mounts
belong to the child namespace and disappear when its processes exit. Linux/root
and the already verified official runtime are required; nothing is downloaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

RUNTIME_SHA256 = "d31fc19c85b85f6091b2bd0f6af9d962d5264a4e410bfb536402ec92bac738e8"
HOST_LIBRARY = Path("/usr/lib/librknnrt.so")


def identity(path: Path):
    if not path.exists() and not path.is_symlink():
        return None
    stat = path.lstat()
    return {"device": stat.st_dev, "inode": stat.st_ino, "mode": stat.st_mode,
            "size": stat.st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def inside(view: Path, command: list[str]) -> None:
    # unshare has made mount propagation private before this function runs.
    options = f"lowerdir=/usr/lib,upperdir={view / 'upper'},workdir={view / 'work'}"
    subprocess.run(["mount", "-t", "overlay", "overlay", "-o", options, "/usr/lib"], check=True)
    if hashlib.sha256(HOST_LIBRARY.read_bytes()).hexdigest() != RUNTIME_SHA256:
        raise RuntimeError("private runtime view checksum mismatch")
    print(json.dumps({"private_runtime": str(HOST_LIBRARY), "sha256": RUNTIME_SHA256,
                      "mount_namespace": os.readlink("/proc/self/ns/mnt")}), flush=True)
    os.execvpe(command[0], command, os.environ)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--inside", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if sys.platform != "linux" or os.geteuid() != 0:
        parser.error("this isolated lab launcher requires Linux and root")
    if not command:
        parser.error("supply a lab command after --")
    if args.inside:
        inside(args.inside, command)
        return 1  # exec never returns on success
    if not args.root or not args.root.is_absolute():
        parser.error("--root must be the absolute speech-service lab directory")
    root = args.root.resolve()
    if any(char in str(root) for char in (",", ":", "\n", "\\")):
        parser.error("root contains an unsupported mount-option character")
    runtime = root / "lib/librknnrt.so"
    if not runtime.is_file() or hashlib.sha256(runtime.read_bytes()).hexdigest() != RUNTIME_SHA256:
        parser.error("stage and verify the pinned official runtime before launching")
    before = identity(HOST_LIBRARY)
    cache = root / ".cache"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="runtime-view-", dir=cache) as directory:
        view = Path(directory)
        (view / "upper").mkdir()
        (view / "work").mkdir()
        shutil.copyfile(runtime, view / "upper/librknnrt.so")
        child = ["unshare", "--mount", "--propagation", "private", "--", sys.executable,
                 str(Path(__file__).resolve()), "--inside", str(view), "--", *command]
        result = subprocess.run(child, check=False)
    after = identity(HOST_LIBRARY)
    print(json.dumps({"host_library_unchanged": before == after,
                      "host_library_exists": after is not None,
                      "command_returncode": result.returncode}), flush=True)
    if before != after:
        raise RuntimeError("host runtime library identity unexpectedly changed")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
