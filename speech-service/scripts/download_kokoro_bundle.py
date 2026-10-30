"""Download only the pinned RK3588 ConvOnly bundle and verify every byte.

Run on the worker after reviewing the destination. No pip/model code is run.
Temporary download files live beside the bundle, outside its strict inventory.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request

REVISION = '3f8d58c8446ec4b18891624ad4ae4ce75e0f3d3e'
MANIFEST_SHA256 = '83733c717e0ce5b76ac1295e4827cf3ad2e111955259e9d670897e100fabeb6e'
REPO = 'harvestsu/seeed-local-voice-rk-artifacts'
PREFIX = 'rk3588/kokoro-convonly-v1_0'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_metadata(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'rk3588-tts-smoke'}), timeout=30) as r:
        data = r.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError('manifest too large')
    if hashlib.sha256(data).hexdigest() != MANIFEST_SHA256:
        raise ValueError('manifest SHA256 does not match the pinned upstream receipt')
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('destination', type=Path)
    ap.add_argument('--endpoint', choices=['https://huggingface.co', 'https://hf-mirror.com'], default='https://hf-mirror.com')
    ap.add_argument('--jobs', type=int, choices=range(1, 5), default=2)
    ap.add_argument('--interval', type=float, default=0.5, help='Delay before each file request; use --jobs 1 for serial pacing')
    ap.add_argument('--plan', action='store_true', help='Fetch metadata and print download size without downloading bundle files')
    args = ap.parse_args()
    if not 0 <= args.interval <= 10:
        ap.error('interval must be between 0 and 10 seconds')
    root = args.destination
    if not root.is_absolute() or '..' in root.parts:
        ap.error('destination must be an absolute path without traversal')
    if any(p.is_symlink() for p in (root, *root.parents)):
        ap.error('destination and ancestors must not be symlinks')
    base = args.endpoint + '/' + REPO + '/resolve/' + REVISION + '/' + PREFIX + '/'
    raw = read_metadata(base + 'convonly.manifest.json')
    manifest = json.loads(raw)
    if (manifest.get('schema'), manifest.get('platform')) != ('kokoro.convonly.bundle.v1', 'rk3588'):
        raise ValueError('unexpected manifest identity')
    rows = manifest['files']
    expected = {'convonly.manifest.json'}
    for row in rows:
        name = row['path']
        p = PurePosixPath(name)
        if p.is_absolute() or p.as_posix() != name or any(s in ('.', '..', '') for s in name.split('/')) or '\\' in name:
            raise ValueError('unsafe file inventory path')
        if name in expected or not isinstance(row['size'], int) or not 0 < row['size'] < 1024 ** 3:
            raise ValueError('invalid or duplicate file inventory row')
        expected.add(name)
    total = len(raw) + sum(row['size'] for row in rows)
    print(json.dumps({'revision': REVISION, 'manifest_sha256': MANIFEST_SHA256, 'files': len(rows) + 1, 'bytes': total, 'destination': str(root), 'endpoint': args.endpoint}), flush=True)
    if args.plan:
        return
    if root.exists():
        for p in root.rglob('*'):
            if p.is_symlink():
                raise ValueError('symlink found in destination bundle')
            if p.is_file() and p.relative_to(root).as_posix() not in expected:
                raise ValueError('destination contains a file outside the pinned inventory: ' + str(p))
    root.mkdir(parents=True, exist_ok=True)
    staging = root.parent / ('.' + root.name + '-downloads')
    if staging.is_symlink():
        raise ValueError('download staging must not be a symlink')
    staging.mkdir(exist_ok=True)
    (root / 'convonly.manifest.json').write_bytes(raw)

    def download(row):
        target = root.joinpath(*PurePosixPath(row['path']).parts)
        if target.is_file() and target.stat().st_size == row['size'] and digest(target) == row['sha256']:
            return 'verified-existing'
        target.parent.mkdir(parents=True, exist_ok=True)
        # Equal-content inventory paths can download concurrently.
        temp = staging / (hashlib.sha256(row['path'].encode('utf-8')).hexdigest() + '.part')
        h = hashlib.sha256()
        count = 0
        req = urllib.request.Request(base + urllib.parse.quote(row['path'], safe='/'), headers={'User-Agent': 'rk3588-tts-smoke'})
        if args.interval:
            time.sleep(args.interval)
        with urllib.request.urlopen(req, timeout=30) as r, temp.open('wb') as out:
            while chunk := r.read(1024 * 1024):
                count += len(chunk)
                if count > row['size']:
                    raise ValueError('file exceeded declared size: ' + row['path'])
                h.update(chunk)
                out.write(chunk)
        if count != row['size'] or h.hexdigest() != row['sha256']:
            raise ValueError('file SHA/size mismatch: ' + row['path'])
        os.replace(temp, target)
        return 'downloaded'

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(download, row) for row in rows]
        done = 0
        try:
            for future in as_completed(futures):
                future.result()
                done += 1
                if done % 10 == 0 or done == len(rows):
                    print(f'verified {done}/{len(rows)}', flush=True)
        except BaseException:
            for future in futures:
                future.cancel()
            raise
    print('Bundle downloaded and all inventory SHA256 values verified.', flush=True)


if __name__ == '__main__':
    main()
