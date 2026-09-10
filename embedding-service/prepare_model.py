"""从国内可达的镜像下载 bge-small-zh-v1.5 模型文件。

默认源 hf-mirror.com（国内可达），可用 --base-url 或 MODEL_BASE_URL 覆盖。
下载 model_optimized.onnx 与 tokenizer.json 到 --destination。
--sha256 / --tokenizer-sha256 可选，给出时做固定校验。
"""
import argparse
import hashlib
import os
import sys
import time
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://hf-mirror.com/Qdrant/bge-small-zh-v1.5/resolve/main"
FILES = {
    "model_optimized.onnx": "sha256",
    "tokenizer.json": "tokenizer_sha256",
}


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, target, attempts=4, timeout=180):
    partial = Path(str(target) + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response, open(partial, "wb") as sink:
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    sink.write(chunk)
            os.replace(partial, target)
            return
        except Exception as error:  # 网络抖动一律重试
            partial.unlink(missing_ok=True)
            if attempt == attempts:
                raise
            print(f"  重试 {attempt}/{attempts - 1}: {error}", file=sys.stderr)
            time.sleep(3)


def prepare(destination, base_url, pins):
    destination.mkdir(parents=True, exist_ok=True)
    for name, key in FILES.items():
        target = destination / name
        if not (target.is_file() and target.stat().st_size > 0):
            print(f"  下载: {base_url}/{name}")
            download(f"{base_url}/{name}", target)
        actual = sha256_of(target)
        expected = (pins.get(key) or "").strip().lower()
        if expected and actual != expected:
            raise SystemExit(f"校验失败 {name}: {actual} != {expected}")
        print(f"  ok {name}: {actual}")
    (destination / "SHA256SUMS").write_text(
        "".join(f"{sha256_of(destination / name)}  {name}\n" for name in FILES), encoding="ascii"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="下载 bge-small-zh-v1.5（国内镜像）")
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--base-url", default=os.getenv("MODEL_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--sha256", default=os.getenv("MODEL_SHA256", ""))
    parser.add_argument("--tokenizer-sha256", default=os.getenv("TOKENIZER_SHA256", ""))
    args = parser.parse_args()
    prepare(args.destination, args.base_url, {"sha256": args.sha256, "tokenizer_sha256": args.tokenizer_sha256})
