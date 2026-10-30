"""Stage the official RKNN 2.3.2 runtime locally, without changing system libraries."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

COMMIT = '42aa1d426c0a9e0869b6374edba009f7208a1926'
GIT_BLOB = 'e53a2b6ec332f2863df5c70cd9f6ebec9dbef397'
SIZE = 7726232
SHA256 = 'd31fc19c85b85f6091b2bd0f6af9d962d5264a4e410bfb536402ec92bac738e8'
URL = f'https://raw.githubusercontent.com/airockchip/rknn-toolkit2/{COMMIT}/rknpu2/runtime/Linux/librknn_api/aarch64/librknnrt.so'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    args = ap.parse_args()
    root = args.root.absolute()
    if any(p.is_symlink() for p in (root, *root.parents)):
        ap.error('root must not use symlink ancestors')
    target = root / 'lib/librknnrt.so'
    if target.is_symlink() or target.parent.is_symlink():
        ap.error('runtime destination must not be a symlink')
    if target.exists():
        data = target.read_bytes()
    else:
        request = urllib.request.Request(URL, headers={'User-Agent': 'speech-service-lab'})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(SIZE + 1)
    blob = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
    if len(data) != SIZE or blob != GIT_BLOB or hashlib.sha256(data).hexdigest() != SHA256:
        raise RuntimeError('runtime does not match the pinned official Git object')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    receipt = {'commit': COMMIT, 'url': URL, 'git_blob': blob,
               'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'path': str(target)}
    (root / '.state').mkdir(exist_ok=True)
    (root / '.state/runtime.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
