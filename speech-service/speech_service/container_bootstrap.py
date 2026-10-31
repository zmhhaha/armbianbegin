"""Expose only RK3588 compatibility data, then discard every capability.

Run this file as ``python -I -S``: the short mount phase imports stdlib only and
does not execute application/site-package code. All mounts belong to the
container's private namespace; the SDK and host filesystem remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

BOARD_INPUT = Path("/run/rknpu/compatible")
BOARD_VISIBLE = Path("/proc/device-tree/compatible")
FIRMWARE = Path("/sys/firmware")
CAP_FIELDS = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb")
MOUNT_CAPS = (1 << 21) | (1 << 8)  # CAP_SYS_ADMIN and CAP_SETPCAP only.


class BootstrapFailed(RuntimeError):
    pass


def status() -> dict[str, int]:
    result = {}
    for line in Path("/proc/self/status").read_text(encoding="ascii").splitlines():
        key, _, value = line.partition(":")
        if key in CAP_FIELDS:
            result[key] = int(value.strip(), 16)
        elif key == "NoNewPrivs":
            result[key] = int(value.strip())
    if set(result) != {*CAP_FIELDS, "NoNewPrivs"}:
        raise BootstrapFailed("process capability state is unavailable")
    return result


def compatible(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise BootstrapFailed("board compatibility input is not a regular file")
            value = stream.read(4097)
    except OSError:
        raise BootstrapFailed("board compatibility input is unavailable") from None
    if (not 1 <= len(value) <= 4096 or not value.endswith(b"\0")
            or any(byte != 0 and not 32 <= byte <= 126 for byte in value)
            or b"rockchip,rk3588" not in value.split(b"\0")):
        raise BootstrapFailed("board compatibility input is not a bounded RK3588 identity")
    return value


def readonly(path: Path) -> bool:
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except OSError:
        return False


def container_guard() -> None:
    marker = Path("/.dockerenv")
    if (sys.platform != "linux" or os.geteuid() != 0 or marker.is_symlink()
            or not marker.is_file()):
        raise BootstrapFailed("bootstrap requires the dedicated root container")
    if FIRMWARE.is_symlink() or not FIRMWARE.is_dir():
        raise BootstrapFailed("container firmware mountpoint is unavailable")
    if not readonly(BOARD_INPUT):
        raise BootstrapFailed("board compatibility input must be mounted read-only")


def mount(*args: str | Path) -> None:
    try:
        subprocess.run(["/usr/bin/mount", *map(str, args)], check=True,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise BootstrapFailed("private container firmware mount failed") from None


def mount_firmware(value: bytes) -> None:
    # Prevent propagation before changing any mount, including volume mounts.
    mount("--make-rprivate", "/")
    staging = Path(tempfile.mkdtemp(prefix="speech-firmware-", dir="/tmp")) / "tree"
    board = staging / "devicetree/base/compatible"
    board.parent.mkdir(parents=True, mode=0o700)
    board.write_bytes(value)
    board.chmod(0o400)
    # Make the /tmp alias read-only too: otherwise root with no capabilities
    # could still modify the same inode through its writable source pathname.
    mount("--bind", staging, staging)
    mount("-o", "remount,bind,ro,nodev,nosuid,noexec", staging, staging)
    mount("--bind", staging, FIRMWARE)
    mount("-o", "remount,bind,ro,nodev,nosuid,noexec", staging, FIRMWARE)
    if not readonly(staging) or not readonly(FIRMWARE):
        raise BootstrapFailed("private firmware aliases did not become read-only")


def verify() -> dict[str, int]:
    container_guard()
    state = status()
    if any(state[key] for key in CAP_FIELDS) or state["NoNewPrivs"] != 1:
        raise BootstrapFailed("capabilities were not completely and permanently discarded")
    if (not readonly(FIRMWARE) or compatible(BOARD_VISIBLE) != compatible(BOARD_INPUT)):
        raise BootstrapFailed("visible board identity is not the read-only mounted input")
    # Require an actual mount at the one deliberately replaced mask, rather
    # than accepting some unrelated read-only parent filesystem.
    if not any(line.split()[4] == str(FIRMWARE)
               for line in Path("/proc/self/mountinfo").read_text().splitlines()):
        raise BootstrapFailed("private firmware mount could not be verified")
    return state


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    second_phase = bool(args and args[0] == "--verify-and-exec")
    if second_phase:
        args.pop(0)
    if args and args[0] == "--":
        args.pop(0)
    try:
        if not args or any(not value or "\0" in value for value in args):
            raise BootstrapFailed("an explicit application command is required")
        if second_phase:
            state = verify()
            print(json.dumps({"event": "speech_container_bootstrap_ready",
                              "compatible_sha256": hashlib.sha256(compatible(BOARD_INPUT)).hexdigest(),
                              "capabilities": {key: state[key] for key in CAP_FIELDS},
                              "no_new_privs": state["NoNewPrivs"], "firmware_readonly": True}), flush=True)
            os.execvp(args[0], args)
        container_guard()
        state = status()
        if (state["CapPrm"] != MOUNT_CAPS or state["CapEff"] != MOUNT_CAPS
                or state["CapBnd"] != MOUNT_CAPS or state["CapInh"] or state["CapAmb"]):
            raise BootstrapFailed("bootstrap requires only SYS_ADMIN and SETPCAP")
        if not Path("/usr/bin/setpriv").is_file() or not Path("/usr/bin/mount").is_file():
            raise BootstrapFailed("container mount and capability tools are unavailable")
        mount_firmware(compatible(BOARD_INPUT))
        command = ["/usr/bin/setpriv", "--bounding-set=-all", "--inh-caps=-all",
                   "--ambient-caps=-all", "--no-new-privs", sys.executable,
                   "-I", "-S", str(Path(__file__).resolve()), "--verify-and-exec", "--", *args]
        os.execv(command[0], command)
    except (BootstrapFailed, OSError) as exc:
        # No vendor imports, board payload, narration, or credential is logged.
        message = str(exc) if isinstance(exc, BootstrapFailed) else "container bootstrap execution failed"
        print(json.dumps({"event": "speech_container_bootstrap_failed", "reason": message}),
              file=sys.stderr, flush=True)
        return 78
    return 78


if __name__ == "__main__":
    raise SystemExit(main())
