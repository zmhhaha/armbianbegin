"""Download a checksum-pinned model archive; never extract archive paths."""
import argparse
import hashlib
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

URL = "https://storage.googleapis.com/qdrant-fastembed/fast-bge-small-zh-v1.5.tar.gz"

def prepare(destination, expected):
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected.lower()):
        raise ValueError("A verified SHA256 is required")
    with tempfile.TemporaryDirectory() as directory:
        archive = Path(directory) / "model.tar.gz"
        urllib.request.urlretrieve(URL, archive)
        with archive.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected.lower():
            raise ValueError("Model archive checksum mismatch")
        with tarfile.open(archive) as tar:
            selected = {}
            for member in tar.getmembers():
                name = Path(member.name).name
                if name in ("model_optimized.onnx", "tokenizer.json") and member.isfile():
                    if name in selected:
                        raise ValueError("Duplicate model file")
                    selected[name] = member
            if len(selected) != 2:
                raise ValueError("Missing model or tokenizer")
            destination.mkdir(parents=True, exist_ok=True)
            for name, member in selected.items():
                with tar.extractfile(member) as src, (destination / name).open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        (destination / "archive.sha256").write_text(actual, encoding="ascii")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.destination, args.sha256)
