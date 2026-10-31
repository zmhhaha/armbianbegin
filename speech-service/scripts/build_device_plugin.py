"""Build fixed upstream device-plugin source with a private verified Go SDK.

Linux ARM64 only. The operator must run this under a bounded systemd unit.
No host SDK, Python packages, drivers, or runtime libraries are installed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import urllib.request


REVISION = "7626d567413ce3831e5ec99471dcdd3a9250cf81"
SOURCE_URL = f"https://codeload.github.com/squat/generic-device-plugin/tar.gz/{REVISION}"
SOURCE_SHA256 = "61448ba86305887e7651abf5be7ff4fab2a28639a9f2396f8dc98d3f70a54a1e"
SOURCE_BYTES = 4222286
SDK_VERSION = "go1.26.0"
SDK_NAME = SDK_VERSION + ".linux-arm64.tar.gz"
SDK_SHA256 = "bd03b743eb6eb4193ea3c3fd3956546bf0e3ca5b7076c8226334afe6b75704cd"
SDK_BYTES = 63655921
SDK_URL = "https://golang.google.cn/dl/" + SDK_NAME
SDK_METADATA_URL = "https://golang.google.cn/dl/?mode=json&include=all"
IMAGE = "arm-cluster-master:5000/rknpu-device-plugin:latest"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def download(url, target, maximum, expected=None):
    if target.is_file() and expected and digest(target) == expected:
        return
    temporary = target.with_suffix(target.suffix + ".partial")
    req = urllib.request.Request(url, headers={"User-Agent": "speech-service-device-plugin-build"})
    size = 0
    with urllib.request.urlopen(req, timeout=25) as response, temporary.open("wb") as stream:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > maximum:
                raise RuntimeError("download byte limit exceeded")
            stream.write(chunk)
    if expected and digest(temporary) != expected:
        raise RuntimeError("download checksum mismatch")
    temporary.replace(target)


def extract(archive, destination, prefix, maximum):
    destination.mkdir(parents=True, exist_ok=True)
    total = 0
    with tarfile.open(archive, "r:gz") as source:
        for item in source:
            if item.name.rstrip("/") == prefix.rstrip("/") and item.isdir():
                continue
            if not item.name.startswith(prefix):
                raise RuntimeError("unexpected archive root")
            relative = item.name[len(prefix):]
            parts = PurePosixPath(relative).parts
            if not parts or relative.startswith("/") or "\\" in relative or any(p in {"", ".", ".."} for p in parts):
                raise RuntimeError("unsafe archive path")
            path = destination.joinpath(*parts)
            if any(p.is_symlink() for p in (path, *path.parents)):
                raise RuntimeError("linked extraction path")
            if item.isdir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            if not item.isfile():
                raise RuntimeError("special archive entry")
            total += item.size
            if total > maximum:
                raise RuntimeError("extracted byte limit exceeded")
            path.parent.mkdir(parents=True, exist_ok=True)
            with source.extractfile(item) as reader, path.open("wb") as writer:
                shutil.copyfileobj(reader, writer)
            path.chmod(0o755 if item.mode & 0o111 else 0o644)


def run(args, *, cwd=None, env=None, timeout=450):
    print(json.dumps({"command": args}), flush=True)
    subprocess.run(args, cwd=cwd, env=env, timeout=timeout, check=True)


def build(root):
    if os.uname().machine != "aarch64" or not root.is_absolute():
        raise RuntimeError("absolute private root on Linux ARM64 required")
    root = root.resolve()
    cache = root / ".cache/device-plugin"
    cache.mkdir(parents=True, exist_ok=True)
    tools = root / ".cache/tools"
    tools.mkdir(parents=True, exist_ok=True)
    sdk_archive = cache / SDK_NAME
    metadata = cache / "go-official-metadata.json"
    download(SDK_METADATA_URL, metadata, 4 * 1024 * 1024)
    versions = json.loads(metadata.read_text())
    published = next(x for row in versions if row["version"] == SDK_VERSION for x in row["files"] if x["filename"] == SDK_NAME)
    if published["sha256"] != SDK_SHA256 or published["size"] != SDK_BYTES:
        raise RuntimeError("official Go identity changed")
    print("Downloading the official private Go SDK", flush=True)
    download(SDK_URL, sdk_archive, SDK_BYTES, SDK_SHA256)
    extract(sdk_archive, tools / "go", "go/", 400 * 1024 * 1024)
    source_archive = cache / ("source-" + REVISION + ".tar.gz")
    download(SOURCE_URL, source_archive, SOURCE_BYTES, SOURCE_SHA256)
    source = cache / ("source-" + REVISION)
    extract(source_archive, source, f"generic-device-plugin-{REVISION}/", 48 * 1024 * 1024)
    go = str(tools / "go/bin/go")
    env = dict(os.environ, GOROOT=str(tools / "go"), GOCACHE=str(cache / "gocache"),
               GOMODCACHE=str(cache / "gomodcache"), GOPATH=str(cache / "gopath"),
               GOPROXY="https://goproxy.cn", GOTOOLCHAIN="local", CGO_ENABLED="0",
               GOOS="linux", GOARCH="arm64", GOMAXPROCS="2", GOFLAGS="-p=2")
    package = "./cmd/generic-device-plugin" if (source / "cmd/generic-device-plugin/main.go").exists() else "."
    context = cache / "image"
    context.mkdir(exist_ok=True)
    binary = context / "generic-device-plugin"
    run([go, "version"], env=env, timeout=10)
    run([go, "build", "-mod=readonly", "-trimpath", "-buildvcs=false", "-ldflags=-s -w", "-o", str(binary), package], cwd=source, env=env)
    module_info = subprocess.check_output([go, "version", "-m", str(binary)], env=env, text=True, timeout=10)
    (cache / "binary-modules.txt").write_text(module_info)
    run([str(binary), "--version"], timeout=10)
    shutil.copyfile(root / "device-plugin/Dockerfile", context / "Dockerfile")
    shutil.copyfile(source / "LICENSE", context / "LICENSE")
    created = datetime.now(timezone.utc).isoformat()
    docker_env = dict(os.environ, DOCKER_BUILDKIT="0")
    run(["docker", "build", "--platform", "linux/arm64", "--memory", "256m", "--cpu-period", "100000", "--cpu-quota", "100000", "--build-arg", "SOURCE_REVISION=" + REVISION, "--build-arg", "BUILD_CREATED=" + created, "-t", IMAGE, str(context)], env=docker_env, timeout=60)
    run(["docker", "push", IMAGE], timeout=60)
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", IMAGE], text=True, timeout=10))[0]
    receipt = {"source_revision": REVISION, "source_url": SOURCE_URL,
               "source_archive_sha256": digest(source_archive), "source_archive_bytes": source_archive.stat().st_size,
               "sdk_url": SDK_URL, "sdk_bytes": SDK_BYTES,
               "sdk_metadata_url": SDK_METADATA_URL, "sdk_sha256": SDK_SHA256,
               "binary_sha256": digest(binary), "binary_bytes": binary.stat().st_size,
               "module_info": module_info, "created": created, "image": IMAGE,
               "image_id": image["Id"], "repo_digests": image["RepoDigests"],
               "image_architecture": image["Architecture"], "image_bytes": image["Size"]}
    destination = root / ".state/rknpu-device-plugin-build.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    build(parser.parse_args().root)
