"""Build worker/API/UI candidates from a fixed server-side Git checkout.

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
    'scientific_agent/pi_revision_contracts.py', 'scientific_agent/pi_revision_validation.py',
    'tools/sqlite_client.py', 'tools/email_client.py',
)
WORKER_FILES = (
    'Dockerfile.scientific-pi',
    'scientific_agent/__init__.py', 'scientific_agent/pi_contracts.py',
    'scientific_agent/pi_runtime_config.py', 'scientific_agent/pi_healthcheck.py',
    'scientific_agent/pi_sections.py', 'scientific_agent/pi_citations.py',
    'scientific_agent/pi_revision_contracts.py', 'scientific_agent/pi_revision_validation.py',
    'pi_worker/__init__.py', 'pi_worker/app.py', 'pi_worker/artifacts.py',
    'pi_worker/store.py', 'pi_worker/scheduler.py',
    'pi_worker/node/package.json', 'pi_worker/node/package-lock.json',
    'pi_worker/requirements.lock', 'pi_worker/requirements.txt',
    'pi_worker/research_tools/__init__.py', 'pi_worker/research_tools/__main__.py',
    'pi_worker/research_tools/bridge.py', 'pi_worker/research_tools/prompt.py',
    'pi_worker/research_tools/schemas.py', 'pi_worker/research_tools/transport.py',
    'pi_worker/research_tools/validation.py',
    'pi_worker/runtime/__init__.py', 'pi_worker/runtime/adapter.py',
    'pi_worker/runtime/jsonl_compactor.mjs', 'pi_worker/runtime/launcher.py',
    'pi_worker/runtime/profiles.py', 'pi_worker/runtime/windows_job.py',
    'scientific_skills/LICENSE', 'scientific_skills/manifest.json',
    'scientific_skills/research-procedure/SKILL.md', 'scientific_skills/task-template.md',
    'tools/__init__.py', 'tools/academic/__init__.py', 'tools/academic/http_client.py',
    'tools/academic/models.py', 'tools/academic/providers.py', 'tools/academic/query.py',
    'tools/academic/search.py',
)


def source_payload(git, commit):
    """Read only allowlisted committed blobs; never copy the working directory."""
    payload = {'context/' + name: git('show', commit + ':' + name) for name in FILES}
    payload.update({'worker-context/' + name: git('show', commit + ':' + name) for name in WORKER_FILES})
    payload['ui-source.py'] = git('show', commit + ':app/ui/scientific_agent.py')
    for name in ('api_image_probe.py', 'worker_image_probe.py'):
        payload[name] = git('show', commit + ':tests/scientific_pi/deployment/' + name)
    return payload


def write_payload(out, payload, commit):
    entries = []
    for name, raw in sorted(payload.items()):
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        entries.append(dict(path=name, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    digest = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    manifest = dict(commit=commit, source_digest=digest, files=entries,
        source_format='server-side fetched Git blobs; committed source line endings',
        scope='scientific worker/API/UI only; explicit source allowlists; no credentials or unrelated services')
    (out / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def probe_command(out, tag, kind):
    command = ['docker', 'create', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges']
    if kind == 'worker':
        # Keep /tmp dependency locks readable. Only an empty /data is writable;
        # no production PVC, key, model endpoint or Docker socket is mounted.
        command += ['--user', '65532:65532', '--tmpfs',
                    '/data:rw,nosuid,nodev,noexec,mode=0700,uid=65532,gid=65532',
                    '--env', 'TMPDIR=/data']
    name = kind + '_image_probe.py'
    return command + ['-v', str(out / name) + ':/app/' + name + ':ro',
                      tag, 'python', '-B', '/app/' + name]


def build_image(out, commit, manifest, kind, run):
    repository = 'arm-cluster-master:5000/scientific-pi' + ('-api' if kind == 'api' else '-worker')
    tag = repository + ':writing-' + commit[:12]
    context = out / ('context' if kind == 'api' else 'worker-context')
    dockerfile = context / ('Dockerfile.scientific-pi-api' if kind == 'api' else 'Dockerfile.scientific-pi')
    print(json.dumps(dict(stage='building_from_git', kind=kind, commit=commit, image_tag=tag)), flush=True)
    run(['docker', 'build', '--label', 'org.opencontainers.image.revision=' + commit,
         '--label', 'org.panghu.scientific.source=' + manifest['source_digest'],
         '-f', str(dockerfile), '-t', tag, str(context)], kind + '-build.log')
    cid = subprocess.check_output(probe_command(out, tag, kind), text=True).strip()
    try:
        print(json.dumps(dict(stage='isolated_image_probe', kind=kind)), flush=True)
        with (out / (kind + '-image-probe.json')).open('wb') as output, (out / (kind + '-probe.stderr.log')).open('wb') as errors:
            subprocess.run(['docker', 'start', '-a', cid], stdout=output, stderr=errors, check=True, timeout=180)
        state = json.loads(subprocess.check_output(['docker', 'inspect', cid]))[0]
        assert state['State']['ExitCode'] == 0, 'image probe failed; see private logs'
        probe = json.loads((out / (kind + '-image-probe.json')).read_text())
        assert probe['status'] == 'passed'
    finally:
        subprocess.run(['docker', 'rm', '-f', cid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    print(json.dumps(dict(stage='pushing_image', kind=kind, checks=probe['checks'])), flush=True)
    run(['docker', 'push', tag], kind + '-push.log', 300)
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', tag]))[0]
    digests = [value for value in image.get('RepoDigests', []) if value.startswith(repository + '@sha256:')]
    assert len(digests) == 1 and image['Architecture'] == 'arm64' and image['Os'] == 'linux'
    receipt = dict(status='passed', observed_at=datetime.now(timezone.utc).isoformat(),
        image_tag=tag, image_digest=digests[0], image_id=image['Id'], architecture=image['Architecture'],
        source=manifest, probe=probe, production_deployment_modified=False, production_database_contacted=False)
    (out / (kind + '-build-receipt.json')).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(kind=kind, image_digest=digests[0], status='passed')), flush=True)
    return receipt


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
    manifest = write_payload(out, source_payload(git, commit), commit)

    def run(command, logfile, timeout=1800):
        with (out/logfile).open('wb') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=timeout)

    images = {kind: build_image(out, commit, manifest, kind, run) for kind in ('worker', 'api')}
    combined = dict(status='passed', source_commit=commit, source_digest=manifest['source_digest'],
                    worker=images['worker']['image_digest'], api=images['api']['image_digest'],
                    ui_source_sha256=next(row['sha256'] for row in manifest['files'] if row['path'] == 'ui-source.py'),
                    production_deployment_modified=False, real_model_acceptance=False)
    (out / 'build-receipt.json').write_text(json.dumps(combined, indent=2) + '\n')
    print(json.dumps(combined), flush=True)


if __name__ == '__main__':
    main()
