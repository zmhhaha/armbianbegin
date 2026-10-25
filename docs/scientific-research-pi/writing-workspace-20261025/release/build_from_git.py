"""Build a scientific API candidate from a fixed server-side Git checkout.

Run after fetching/checking out the pushed root and panghu_agent commits.
No source archive or uploaded source file is accepted. Only committed Git blobs
enter the Docker context; unrelated services and ignored files are excluded.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

FILES = (
    'Dockerfile.scientific-pi-api', 'scientific_agent/requirements-api.lock',
    'app/__init__.py', 'app/api/__init__.py', 'app/api/scientific_agent.py',
    'scientific_agent/__init__.py', 'scientific_agent/pi_contracts.py',
    'scientific_agent/pi_client.py', 'scientific_agent/pi_projection.py',
    'scientific_agent/pi_citations.py', 'scientific_agent/pi_sections.py',
    'scientific_agent/pi_report_versions.py', 'tools/__init__.py',
    'tools/sqlite_client.py', 'tools/email_client.py',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    repo = args.repo.resolve(strict=True)
    assert re.fullmatch('[0-9a-f]{40}', args.commit), 'full Git commit required'

    def git(*values):
        return subprocess.check_output(['git', '-C', str(repo), *values])

    commit = git('rev-parse', 'HEAD').decode().strip()
    assert commit == args.commit, 'checkout differs from requested commit'
    assert not git('status', '--porcelain', '--untracked-files=no'), 'tracked checkout is dirty'
    out = args.output_dir.resolve()
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    payload = {'context/' + name: git('show', commit + ':' + name) for name in FILES}
    payload['ui-source.py'] = git('show', commit + ':app/ui/scientific_agent.py')
    payload['api_image_probe.py'] = git('show', commit + ':tests/scientific_pi/deployment/api_image_probe.py')
    entries = []
    for name, raw in sorted(payload.items()):
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        entries.append({'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    digest = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    manifest = {'commit': commit, 'source_digest': digest, 'files': entries,
                'source_format': 'server-side fetched Git blobs; normalized source line endings',
                'scope': 'scientific API/UI only; no worker, secrets or unrelated service source'}
    (out/'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    tag = 'arm-cluster-master:5000/scientific-pi-api:writing-' + commit[:12]

    def run(command, logfile, timeout=1800):
        with (out/logfile).open('wb') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=timeout)

    print(json.dumps({'stage': 'building_from_git', 'commit': commit, 'image_tag': tag}), flush=True)
    run(['docker', 'build', '--label', 'org.opencontainers.image.revision=' + commit,
         '--label', 'org.panghu.scientific.source=' + digest,
         '-f', str(out/'context/Dockerfile.scientific-pi-api'), '-t', tag, str(out/'context')], 'build.log')
    # The image keeps its installed dependency lock under /tmp. Do not mask it
    # with a tmpfs; the probe only uses in-memory SQLite and read-only files.
    cid = subprocess.check_output(['docker', 'create', '--network', 'none', '--read-only',
        '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges',
        '-v', str(out/'api_image_probe.py') + ':/app/api_image_probe.py:ro',
        tag, 'python', '-B', '/app/api_image_probe.py'], text=True).strip()
    try:
        print(json.dumps({'stage': 'isolated_image_probe'}), flush=True)
        with (out/'api-image-probe.json').open('wb') as output, (out/'probe.stderr.log').open('wb') as errors:
            subprocess.run(['docker', 'start', '-a', cid], stdout=output, stderr=errors, check=True, timeout=180)
        state = json.loads(subprocess.check_output(['docker', 'inspect', cid]))[0]
        assert state['State']['ExitCode'] == 0, 'image probe failed; see private logs'
        probe = json.loads((out/'api-image-probe.json').read_text())
        assert probe['status'] == 'passed'
    finally:
        subprocess.run(['docker', 'rm', '-f', cid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    print(json.dumps({'stage': 'pushing_image', 'checks': probe['checks']}), flush=True)
    run(['docker', 'push', tag], 'push.log', 300)
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag]))[0]
    digests = [value for value in image.get('RepoDigests', [])
               if value.startswith('arm-cluster-master:5000/scientific-pi-api@sha256:')]
    assert len(digests) == 1 and image['Architecture'] == 'arm64' and image['Os'] == 'linux'
    receipt = {'status': 'passed', 'observed_at': datetime.now(timezone.utc).isoformat(),
               'image_tag': tag, 'image_digest': digests[0], 'image_id': image['Id'],
               'architecture': image['Architecture'], 'source': manifest, 'probe': probe,
               'production_deployment_modified': False, 'production_database_contacted': False}
    (out/'api-build-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: receipt[key] for key in ('status', 'image_digest', 'architecture')}), flush=True)


if __name__ == '__main__':
    main()
