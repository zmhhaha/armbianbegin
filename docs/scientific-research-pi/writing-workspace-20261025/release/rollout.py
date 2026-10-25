#!/usr/bin/env python3
"""Run an authorized, guarded worker/API/UI release on the cluster master.

Only worker/API images, the worker image digest metadata, and UI source change.
UI entry and UI/API replicas temporarily stop submissions and reconciliation.
All raw Kubernetes objects and command output remain in a fresh private folder.
No research is submitted/cancelled; no database rows or schema are edited here.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid


K = ['kubectl', '--kubeconfig=/etc/kubernetes/super-admin.conf', '-n', 'scientific-agent']
BASE = Path('/root/scientific-writing-releases')
NAMESPACE = 'scientific-agent'
PUBLIC_ROOT = 'https://scientific-agent.panghuer.top'
TERMINAL = {'succeeded', 'failed', 'cancelled', 'timed_out'}


class ReleaseError(Exception):
    pass


def require(condition, code):
    if not condition:
        raise ReleaseError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


class Release:
    def __init__(self, args):
        self.args, self.out = args, Path(args.output_dir)
        require(BASE.is_absolute() and not BASE.is_symlink(), 'invalid_release_base')
        BASE.mkdir(mode=0o700, exist_ok=True)
        require(BASE.resolve(strict=True) == BASE and stat.S_IMODE(BASE.stat().st_mode) & 0o077 == 0,
                'release_base_not_private')
        require(self.out.is_absolute() and self.out.parent == BASE
                and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,100}', self.out.name) is not None
                and self.out.name not in ('.', '..'), 'invalid_output_directory')
        require(not self.out.exists() and not self.out.is_symlink(), 'output_directory_exists_use_fresh_id')
        self.out.mkdir(mode=0o700)
        self.sequence = 0
        self.snapshots = {}
        self.service = None
        self.maintenance_spec = None
        self.zero_spec = None
        self.api_spec = None
        self.api_zero_spec = None
        self.worker_spec = None
        self.ui_spec = None
        self.maintenance_attempted = False
        self.mutation_attempted = False
        self.receipt = dict(status='preparing', started_at=now(), events=[],
                            api_image=args.api_image, api_source_sha256=args.api_source_sha256,
                            worker_image=args.worker_image,
                            ui_source_sha256=args.ui_source_sha256,
                            source_commit=args.source_commit, source_transport='server_git_checkout',
                            rollout_script_sha256=digest(Path(__file__).read_bytes()),
                            scope='Worker/API images and UI source; preserved data/config; no research dispatch',
                            private_directory=str(self.out), browser_acceptance='pending')

    def save(self, name, value):
        require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name) is not None, 'invalid_private_filename')
        target = self.out / name
        require(not target.is_symlink(), 'private_file_symlink')
        temporary = self.out / (name + '.tmp')
        require(not temporary.exists() and not temporary.is_symlink(), 'private_temporary_file_exists')
        with temporary.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        temporary.chmod(0o600)
        temporary.replace(target)

    def stage(self, name, **safe_details):
        event = dict(stage=name, at=now(), **safe_details)
        self.receipt['events'].append(event)
        self.save('receipt.json', self.receipt)
        print(json.dumps(event, ensure_ascii=True), flush=True)

    def command(self, args, timeout=25, allow_failure=False):
        self.sequence += 1
        try:
            result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', timeout=timeout)
            record = dict(argv=args, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired as exc:
            def decoded(value):
                return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value
            self.save('command-%04d.json' % self.sequence,
                      dict(argv=args, timeout=True, stdout=decoded(exc.stdout), stderr=decoded(exc.stderr)))
            if allow_failure:
                return None
            raise ReleaseError('kubernetes_operation_timeout') from None
        self.save('command-%04d.json' % self.sequence, record)
        if result.returncode and not allow_failure:
            raise ReleaseError('kubernetes_operation_failed')
        return result

    def get(self, kind, name, optional=False):
        args = K + ['get', kind, name, '-o', 'json']
        if optional:
            args.append('--ignore-not-found')
        value = self.command(args).stdout
        return json.loads(value) if value.strip() else None

    @staticmethod
    def same(current, baseline, spec):
        return (current is not None and current.get('metadata', {}).get('uid') == baseline['metadata']['uid']
                and current.get('spec') == spec)

    def check(self, kind, name, baseline, spec):
        current = self.get(kind, name)
        require(self.same(current, baseline, spec), 'concurrent_change_' + name)
        return current

    def guarded(self, kind, name, baseline, expected_spec, operations, dry=False):
        current = self.check(kind, name, baseline, expected_spec)
        value = [dict(op='test', path='/metadata/uid', value=baseline['metadata']['uid']),
                 dict(op='test', path='/metadata/resourceVersion', value=current['metadata']['resourceVersion']),
                 dict(op='test', path='/spec', value=expected_spec)] + operations
        filename = 'patch-%04d.json' % (self.sequence + 1)
        self.save(filename, value)
        args = K + ['patch', kind, name, '--type=json', '--patch-file', str(self.out / filename), '-o', 'json']
        if dry:
            args.append('--dry-run=server')
        return json.loads(self.command(args).stdout)

    def replace_spec(self, name, expected_spec, target_spec):
        value = self.guarded('deployment', name, self.snapshots[name], expected_spec,
                             [dict(op='replace', path='/spec', value=target_spec)])
        require(self.same(value, self.snapshots[name], target_spec), 'deployment_patch_readback_' + name)

    def preserved(self, api_spec, ui_spec, service_spec, worker_spec=None):
        self.check('deployment', 'api', self.snapshots['api'], api_spec)
        self.check('deployment', 'ui', self.snapshots['ui'], ui_spec)
        self.check('deployment', 'scientific-pi-worker', self.snapshots['scientific-pi-worker'],
                   self.snapshots['scientific-pi-worker']['spec'] if worker_spec is None else worker_spec)
        self.check('service', 'ui', self.service, service_spec)

    def wait_rollout(self, name, expected_spec, phase):
        for segment in range(1, 5):
            self.check('deployment', name, self.snapshots[name], expected_spec)
            self.stage(phase + '_waiting', deployment=name, segment=segment, segment_seconds=50)
            result = self.command(K + ['rollout', 'status', 'deployment/' + name, '--timeout=50s'],
                                  timeout=55, allow_failure=True)
            current = self.check('deployment', name, self.snapshots[name], expected_spec)
            status, desired = current.get('status', {}), expected_spec.get('replicas', 1)
            ready = (desired >= 1 and status.get('observedGeneration', 0) >= current['metadata']['generation']
                     and all(status.get(field, 0) == desired for field in
                             ('replicas', 'updatedReplicas', 'readyReplicas', 'availableReplicas'))
                     and status.get('unavailableReplicas', 0) == 0)
            self.stage(phase + '_segment_finished', deployment=name, segment=segment,
                       ready=ready, command_succeeded=result is not None and result.returncode == 0)
            if ready:
                return current
        raise ReleaseError('rollout_not_ready_' + name)

    def wait_ui_stopped(self, expected_spec):
        self.wait_stopped('ui', expected_spec)

    def wait_stopped(self, name, expected_spec):
        selector = self.snapshots[name]['spec']['selector']
        require(not selector.get('matchExpressions'), name + '_selector_expressions_unsupported')
        labels = ','.join(key + '=' + value for key, value in sorted(selector['matchLabels'].items()))
        for segment in range(1, 5):
            self.check('deployment', name, self.snapshots[name], expected_spec)
            pods = json.loads(self.command(K + ['get', 'pods', '-l', labels, '-o', 'json']).stdout)['items']
            if not pods:
                return
            self.stage(name + '_handlers_stopping', segment=segment, remaining_pods=len(pods), segment_seconds=50)
            self.command(K + ['wait', '--for=delete', 'pods', '-l', labels, '--timeout=50s'],
                         timeout=55, allow_failure=True)
        self.check('deployment', name, self.snapshots[name], expected_spec)
        pods = json.loads(self.command(K + ['get', 'pods', '-l', labels, '-o', 'json']).stdout)['items']
        require(not pods, 'old_' + name + '_handlers_not_stopped')

    def wait_endpoints(self, available):
        for attempt in range(15):
            obj = self.get('endpoints', 'ui', optional=True) or {}
            addresses = [address for subset in obj.get('subsets', []) for address in subset.get('addresses', [])]
            if bool(addresses) == available:
                return
            if attempt % 5 == 0:
                self.stage('ui_endpoints_waiting', expected_available=available, attempt=attempt + 1)
            time.sleep(1)
        raise ReleaseError('ui_endpoint_state_not_confirmed')

    def exec_python(self, name, container, code):
        return json.loads(self.command(K + ['exec', 'deployment/' + name, '-c', container,
                                            '--', 'python', '-c', code], timeout=40).stdout)

    def prepare(self):
        source_path = Path(self.args.ui_source)
        require(source_path.is_file() and not source_path.is_symlink(), 'ui_source_missing_or_symlink')
        # Sources come from the server's fixed Git checkout. No prepared source
        # bundle, uploaded archive or remote file-copy transport is accepted.
        source_path = source_path.resolve(strict=True)
        repository = self.command(['git', '-C', str(source_path.parent), 'rev-parse', '--show-toplevel']).stdout.strip()
        head = self.command(['git', '-C', repository, 'rev-parse', 'HEAD']).stdout.strip()
        require(head == self.args.source_commit, 'server_source_commit_mismatch')
        relative_source = source_path.relative_to(Path(repository).resolve(strict=True)).as_posix()
        require(relative_source == 'app/ui/scientific_agent.py', 'ui_source_not_panghu_agent_checkout')
        tracked_sources = [relative_source, 'app/api/scientific_agent.py',
                           'scientific_agent/pi_citations.py', 'scientific_agent/pi_sections.py',
                           'scientific_agent/pi_report_versions.py', 'scientific_agent/pi_revision_contracts.py',
                           'scientific_agent/pi_revision_validation.py', 'pi_worker/app.py']
        self.command(['git', '-C', repository, 'ls-files', '--error-unmatch', '--'] + tracked_sources)
        self.command(['git', '-C', repository, 'diff', '--exit-code', 'HEAD', '--'])
        self.receipt['source_repository'] = repository
        api_path = Path(repository) / 'app/api/scientific_agent.py'
        require(api_path.is_file() and not api_path.is_symlink()
                and digest(api_path.read_bytes()) == self.args.api_source_sha256, 'git_api_source_digest_mismatch')
        self.module_hashes = {}
        for name in ('pi_citations', 'pi_sections', 'pi_report_versions', 'pi_revision_contracts', 'pi_revision_validation'):
            module = Path(repository) / 'scientific_agent' / (name + '.py')
            require(module.is_file() and not module.is_symlink(), 'git_source_module_missing')
            self.module_hashes[name] = digest(module.read_bytes())
        self.receipt['new_module_sha256'] = self.module_hashes
        self.worker_source_sha256 = digest((Path(repository) / 'pi_worker/app.py').read_bytes())
        self.receipt['worker_source_sha256'] = self.worker_source_sha256
        raw = source_path.read_bytes()
        require(len(raw) <= 900 * 1024 and digest(raw) == self.args.ui_source_sha256, 'ui_source_digest_mismatch')
        source = raw.decode('utf-8')
        compile(source, '<reviewed-ui-source>', 'exec')
        for name in ('api', 'ui', 'scientific-pi-worker'):
            obj = self.get('deployment', name)
            require(obj['metadata']['namespace'] == NAMESPACE and obj['metadata']['name'] == name,
                    'deployment_identity_mismatch')
            self.snapshots[name] = obj
            self.save(name + '-before.json', obj)
            self.save(name + '-rollback.json', dict(
                schema_version='1', kind='GuardedRollbackPlan', resource_kind='Deployment', name=name,
                uid=obj['metadata']['uid'], baseline_spec=obj['spec'],
                automatic_mutation_allowed=True,
                required_guards=['uid', 'fresh_resourceVersion', 'exact_this_attempt_spec'],
                instruction='Use guarded recovery; this document is not an executable JSON Patch'))
            self.stage('deployment_snapshot_saved', deployment=name)
        self.service = self.get('service', 'ui')
        self.save('ui-service-before.json', self.service)
        self.save('ui-service-rollback.json', dict(
            schema_version='1', kind='GuardedRollbackPlan', resource_kind='Service', name='ui',
            uid=self.service['metadata']['uid'], baseline_spec=self.service['spec'],
            permitted_mutation='selector only after paired readiness is verified',
            required_guards=['uid', 'fresh_resourceVersion', 'exact_this_attempt_maintenance_spec'],
            instruction='Use guarded recovery; this document is not an executable JSON Patch'))
        ui, api = self.snapshots['ui'], self.snapshots['api']
        require(ui['spec'].get('replicas', 1) >= 1 and api['spec'].get('replicas', 1) >= 1, 'baseline_scaled_down')
        containers = api['spec']['template']['spec']['containers']
        indices = [i for i, item in enumerate(containers) if item['name'] == 'api']
        require(len(indices) == 1, 'api_container_not_unique')
        self.api_index = indices[0]
        api_container = containers[self.api_index]
        require('@sha256:' in api_container['image'], 'baseline_api_image_not_pinned')
        blocked = ('/app', '/app/scientific_agent', '/app/app', '/app/app/api', '/app/app/api/scientific_agent.py')
        require(not any(item['mountPath'].rstrip('/') in blocked for item in api_container.get('volumeMounts', [])),
                'baseline_api_source_overlay_present')
        worker = self.snapshots['scientific-pi-worker']
        require(worker['spec'].get('replicas', 1) == 1
                and worker['spec'].get('strategy', {}).get('type') == 'Recreate', 'worker_requires_single_recreate')
        workers = worker['spec']['template']['spec']['containers']
        indices = [i for i, item in enumerate(workers) if item['name'] == 'worker']
        require(len(indices) == 1, 'worker_container_not_unique')
        self.worker_index = indices[0]
        worker_container = workers[self.worker_index]
        require('@sha256:' in worker_container['image'], 'baseline_worker_image_not_pinned')
        blocked_worker = ('/app', '/app/pi_worker', '/app/scientific_agent', '/app/pi_worker/app.py')
        require(not any(item['mountPath'].rstrip('/') in blocked_worker for item in worker_container.get('volumeMounts', [])),
                'baseline_worker_source_overlay_present')
        worker_env = worker_container.get('env', [])
        positions = [i for i, item in enumerate(worker_env) if item['name'] == 'SCIENTIFIC_PI_IMAGE_DIGEST']
        require(len(positions) == 1 and worker_env[positions[0]].get('value') == worker_container['image'].rsplit('@', 1)[1],
                'baseline_worker_image_digest_metadata_mismatch')
        self.worker_digest_index = positions[0]
        self.worker_spec = copy.deepcopy(worker['spec'])
        next_worker = self.worker_spec['template']['spec']['containers'][self.worker_index]
        next_worker['image'] = self.args.worker_image
        next_worker['env'][self.worker_digest_index]['value'] = self.args.worker_image.rsplit('@', 1)[1]
        ui_containers = [item for item in ui['spec']['template']['spec']['containers'] if item['name'] == 'ui']
        require(len(ui_containers) == 1 and '@sha256:' in ui_containers[0]['image'], 'ui_container_not_pinned')
        mounts = [item for item in ui_containers[0].get('volumeMounts', []) if item['mountPath'] == '/app/app/ui/agent.py']
        require(len(mounts) == 1 and mounts[0].get('subPath'), 'ui_source_mount_not_unique')
        volumes = ui['spec']['template']['spec']['volumes']
        matches = [(i, item) for i, item in enumerate(volumes) if item['name'] == mounts[0]['name']]
        require(len(matches) == 1 and 'configMap' in matches[0][1], 'ui_source_volume_not_configmap')
        self.volume_index, volume = matches[0]
        old_name = volume['configMap']['name']
        items = volume['configMap'].get('items')
        key = mounts[0]['subPath'] if items is None else next(
            (item['key'] for item in items if item['path'] == mounts[0]['subPath']), None)
        old_cm = self.get('configmap', old_name)
        self.save('ui-source-configmap-before.json', old_cm)
        require(key is not None and set(old_cm.get('data', {})) == {key} and not old_cm.get('binaryData')
                and old_cm.get('immutable') is True, 'ui_source_configmap_not_immutable_single_file')
        roots = [item.get('value') for item in ui_containers[0].get('env', []) if item['name'] == 'GRADIO_ROOT_PATH']
        require(roots == [PUBLIC_ROOT], 'baseline_ui_https_root_mismatch')
        selector = self.service['spec'].get('selector')
        labels = ui['spec']['template']['metadata']['labels']
        require(selector and all(labels.get(key) == value for key, value in selector.items()), 'ui_service_selector_mismatch')
        marker = 'writing-' + uuid.uuid4().hex
        self.maintenance_spec = copy.deepcopy(self.service['spec'])
        self.maintenance_spec['selector'] = dict(selector, **{'scientific-writing-maintenance': marker})
        self.zero_spec = copy.deepcopy(ui['spec'])
        self.zero_spec['replicas'] = 0
        self.api_spec = copy.deepcopy(api['spec'])
        self.api_spec['template']['spec']['containers'][self.api_index]['image'] = self.args.api_image
        self.api_zero_spec = copy.deepcopy(api['spec'])
        self.api_zero_spec['replicas'] = 0
        self.cm_name = 'scientific-workbench-ui-' + self.args.ui_source_sha256[:12]
        self.ui_spec = copy.deepcopy(ui['spec'])
        self.ui_spec['template']['spec']['volumes'][self.volume_index]['configMap']['name'] = self.cm_name
        self.source_reference = '/spec/template/spec/volumes/%d/configMap/name' % self.volume_index
        self.cm = dict(apiVersion='v1', kind='ConfigMap', immutable=True,
                       metadata=dict(name=self.cm_name, namespace=NAMESPACE,
                                     annotations={'research.panghuer.top/ui-source-sha256': self.args.ui_source_sha256}),
                       data={key: source})
        self.save('ui-configmap.json', self.cm)
        self.save('api-expected-spec.json', self.api_spec)
        self.save('api-maintenance-spec.json', self.api_zero_spec)
        self.save('worker-expected-spec.json', self.worker_spec)
        self.save('ui-expected-spec.json', self.ui_spec)
        self.save('ui-maintenance-spec.json', self.zero_spec)
        self.receipt.update(configmap=self.cm_name, previous_configmap=old_name,
                            previous_ui_source_sha256=digest(old_cm['data'][key].encode('utf-8')))
        self.preserved(api['spec'], ui['spec'], self.service['spec'])
        self.guarded('deployment', 'scientific-pi-worker', worker, worker['spec'],
                     [dict(op='replace', path='/spec', value=self.worker_spec)], dry=True)
        self.stage('worker_server_dry_run_passed')
        self.guarded('deployment', 'api', api, api['spec'],
                     [dict(op='replace', path='/spec/template/spec/containers/%d/image' % self.api_index,
                           value=self.args.api_image)], dry=True)
        self.stage('api_server_dry_run_passed')
        self.guarded('deployment', 'ui', ui, ui['spec'],
                     [dict(op='replace', path=self.source_reference, value=self.cm_name)], dry=True)
        self.stage('ui_server_dry_run_passed')
        self.guarded('deployment', 'ui', ui, ui['spec'], [dict(op='replace', path='/spec/replicas', value=0)], dry=True)
        self.guarded('deployment', 'api', api, api['spec'], [dict(op='replace', path='/spec/replicas', value=0)], dry=True)
        self.guarded('service', 'ui', self.service, self.service['spec'],
                     [dict(op='replace', path='/spec/selector', value=self.maintenance_spec['selector'])], dry=True)
        existing = self.get('configmap', self.cm_name, optional=True)
        if existing:
            self.check_cm(existing)
        else:
            self.command(K + ['create', '--dry-run=server', '-f', str(self.out / 'ui-configmap.json'), '-o', 'json'])
        self.stage('fresh_snapshots_and_server_dry_runs_passed')

    def check_cm(self, value):
        require(value.get('immutable') is True and value.get('data') == self.cm['data']
                and not value.get('binaryData'), 'candidate_configmap_collision')

    def worker_counts(self):
        worker = self.exec_python('scientific-pi-worker', 'worker', '''import json,os,sqlite3
from pathlib import Path
p=(Path(os.getenv('SCIENTIFIC_PI_RUNTIME_DIR','/data'))/'control'/'queue.sqlite').resolve(strict=True)
c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
c.execute('PRAGMA query_only=ON')
print(json.dumps({'counts':dict(c.execute('SELECT state,COUNT(*) FROM tasks GROUP BY state'))}))
c.close()
''')
        require(isinstance(worker.get('counts'), dict)
                and all(type(value) is int and value >= 0 for value in worker['counts'].values()), 'invalid_drain_response')
        return worker['counts']

    def drain(self):
        self.preserved(self.snapshots['api']['spec'], self.snapshots['ui']['spec'], self.service['spec'])
        self.maintenance_attempted = True
        self.guarded('service', 'ui', self.service, self.service['spec'],
                     [dict(op='replace', path='/spec/selector', value=self.maintenance_spec['selector'])])
        self.wait_endpoints(False)
        self.stage('ui_entry_maintenance_enabled')
        self.mutation_attempted = True
        self.replace_spec('ui', self.snapshots['ui']['spec'], self.zero_spec)
        self.wait_ui_stopped(self.zero_spec)
        self.stage('old_ui_handlers_stopped')
        legacy = self.exec_python('api', 'api', '''import json
from tools import sqlite_client as db
print(json.dumps({'active':db._query("SELECT COUNT(*) AS n FROM scientific_tasks WHERE status IN ('pending','running')")[0]['n']}))
''')
        counts = self.worker_counts()
        require(type(legacy.get('active')) is int and legacy['active'] >= 0, 'invalid_drain_response')
        active = sum(value for state, value in counts.items() if state not in TERMINAL)
        self.receipt['drain'] = dict(legacy_active=legacy['active'], worker_counts=counts, worker_active=active)
        self.stage('drain_observed', legacy_active=legacy['active'], worker_active=active)
        require(legacy['active'] == 0 and active == 0, 'active_research_release_deferred')
        self.preserved(self.snapshots['api']['spec'], self.zero_spec, self.maintenance_spec)
        # Stop the old reconciler as well as UI handlers before replacing the
        # singleton worker. A late internal dispatch is caught by the second
        # read, and can be resumed by the restored old API without cancellation.
        self.replace_spec('api', self.snapshots['api']['spec'], self.api_zero_spec)
        self.wait_stopped('api', self.api_zero_spec)
        counts = self.worker_counts()
        active = sum(value for state, value in counts.items() if state not in TERMINAL)
        self.receipt['drain'].update(worker_counts_after_api_stop=counts, worker_active_after_api_stop=active)
        self.stage('api_stopped_drain_observed', worker_active=active)
        require(active == 0, 'active_research_release_deferred')
        self.preserved(self.api_zero_spec, self.zero_spec, self.maintenance_spec)

    def apply(self):
        existing = self.get('configmap', self.cm_name, optional=True)
        if existing:
            self.check_cm(existing)
        else:
            value = json.loads(self.command(K + ['create', '-f', str(self.out / 'ui-configmap.json'), '-o', 'json']).stdout)
            self.check_cm(value)
        self.preserved(self.api_zero_spec, self.zero_spec, self.maintenance_spec)
        self.replace_spec('scientific-pi-worker', self.snapshots['scientific-pi-worker']['spec'], self.worker_spec)
        self.stage('worker_image_patched')
        self.wait_rollout('scientific-pi-worker', self.worker_spec, 'worker_rollout')
        self.probe_worker()
        self.preserved(self.api_zero_spec, self.zero_spec, self.maintenance_spec, self.worker_spec)
        self.replace_spec('api', self.api_zero_spec, self.api_spec)
        self.stage('api_image_patched')
        self.wait_rollout('api', self.api_spec, 'api_rollout')
        self.preserved(self.api_spec, self.zero_spec, self.maintenance_spec, self.worker_spec)
        value = self.guarded('deployment', 'ui', self.snapshots['ui'], self.zero_spec,
                             [dict(op='replace', path=self.source_reference, value=self.cm_name),
                              dict(op='replace', path='/spec/replicas', value=self.ui_spec.get('replicas', 1))])
        require(self.same(value, self.snapshots['ui'], self.ui_spec), 'ui_candidate_readback_mismatch')
        self.stage('ui_source_patched')
        self.wait_rollout('ui', self.ui_spec, 'ui_rollout')
        self.probe()
        self.preserved(self.api_spec, self.ui_spec, self.maintenance_spec, self.worker_spec)
        self.receipt['status'] = 'deployed_runtime_checks_passed'
        self.stage('worker_api_ui_runtime_checks_passed')

    def probe_worker(self):
        value = self.exec_python('scientific-pi-worker', 'worker', '''import hashlib,json,os,urllib.request
from pathlib import Path
r=urllib.request.Request('http://127.0.0.1:8080/v1/health',headers={'Authorization':'Bearer '+os.environ['SCIENTIFIC_PI_WORKER_TOKEN']})
with urllib.request.urlopen(r,timeout=15) as response:h=json.load(response)
c=h.get('capabilities',{})
assert h.get('worker_ready') is True and '1' in c.get('revision_job_versions',[])
assert c.get('revision_input_scope')=='recorded_evidence_only'
assert c.get('max_revision_input_bytes')==16*1024*1024
print(json.dumps({'worker_ready':True,'revision_job_versions':c['revision_job_versions'],
 'revision_input_scope':c['revision_input_scope'],'max_revision_input_bytes':c['max_revision_input_bytes'],
 'source_sha256':hashlib.sha256(Path('/app/pi_worker/app.py').read_bytes()).hexdigest(),
 'image_digest_metadata':os.environ['SCIENTIFIC_PI_IMAGE_DIGEST']}))
''')
        require(value.get('worker_ready') is True and value.get('source_sha256') == self.worker_source_sha256
                and value.get('image_digest_metadata') == self.args.worker_image.rsplit('@', 1)[1], 'worker_runtime_probe_failed')
        self.receipt.setdefault('runtime_probes', {})['worker'] = value
        self.stage('worker_revision_capability_verified')

    def probe(self):
        api_probe = self.exec_python('api', 'api', '''import hashlib,importlib,importlib.util,json,urllib.request
from pathlib import Path
names=('pi_citations','pi_sections','pi_report_versions','pi_revision_contracts','pi_revision_validation')
hashes={}
for name in names:
 m=importlib.import_module('scientific_agent.'+name)
 assert Path(m.__file__).resolve()==Path('/app/scientific_agent/'+name+'.py')
 hashes[name]=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
with urllib.request.urlopen('http://127.0.0.1:8000/openapi.json',timeout=15) as r:schema=json.load(r)
paths=('/scientific-research/{task_id}/citations','/scientific-reports/{report_id}/sections',
 '/scientific-reports/{report_id}/versions','/scientific-reports/{report_id}/revision-previews',
 '/scientific-report-versions/{version_id}','/scientific-report-versions/{version_id}/sections',
 '/scientific-report-versions/{version_id}/download','/scientific-report-snapshots/{snapshot_id}',
 '/scientific-revision-previews/{intent_id}','/scientific-revision-previews/{intent_id}/start',
 '/scientific-reports/{report_id}/writing-state','/scientific-report-versions/{candidate_id}/comparison',
 '/scientific-report-versions/{candidate_id}/adopt')
assert all(path in schema['paths'] for path in paths)
assert 'post' in schema['paths']['/scientific-reports/{report_id}/revision-previews']
with urllib.request.urlopen('http://127.0.0.1:8000/scientific-health',timeout=15) as r:h=json.load(r)
assert h['backend']=='pi' and h['status']=='ok' and h['worker_ready'] is True
assert importlib.util.find_spec('crewai') is None
print(json.dumps({'source_sha256':hashlib.sha256(Path('/app/app/api/scientific_agent.py').read_bytes()).hexdigest(),
 'new_modules_imported':True,'module_sha256':hashes,'schema_routes_verified':len(paths),'worker_ready':True,'crewai_installed':False}))
''')
        require(api_probe.get('source_sha256') == self.args.api_source_sha256
                and api_probe.get('schema_routes_verified') == 13 and api_probe.get('worker_ready') is True
                and api_probe.get('new_modules_imported') is True
                and api_probe.get('module_sha256') == self.module_hashes, 'api_runtime_probe_failed')
        ui_probe = self.exec_python('ui', 'ui', '''import hashlib,json,urllib.request
from pathlib import Path
with urllib.request.urlopen('http://127.0.0.1:7860/config',timeout=15) as r:c=json.load(r)
assert c['root']=='https://scientific-agent.panghuer.top'
assert any('查看引用与证据' in str(x.get('props',{}).get('value','')) for x in c['components'] if x['type']=='button')
buttons=[str(x.get('props',{}).get('value','')) for x in c['components'] if x['type']=='button']
assert all(label in buttons for label in ('预览修改范围','确认并开始章节修订','取消修订','比较候选版本','采用为当前写作稿'))
print(json.dumps({'source_sha256':hashlib.sha256(Path('/app/app/ui/agent.py').read_bytes()).hexdigest(),
 'https_root_verified':True,'citation_button_present':True,'editor_buttons_present':True,'gradio_version':c['version']}))
''')
        require(ui_probe.get('source_sha256') == self.args.ui_source_sha256
                and ui_probe.get('https_root_verified') is True and ui_probe.get('citation_button_present') is True
                and ui_probe.get('editor_buttons_present') is True,
                'ui_runtime_probe_failed')
        self.receipt.setdefault('runtime_probes', {}).update(api=api_probe, ui=ui_probe)

    def recover(self):
        """Restore only specs this attempt may have written; retain foreign edits."""
        require(self.snapshots and self.service is not None, 'no_complete_snapshots_for_recovery')
        if not self.maintenance_attempted:
            return
        # Reopening can commit before its response/endpoints check fails. Close
        # our own original selector again before touching either deployment;
        # never roll a pair back while callbacks can reach a recovering UI.
        current_service = self.get('service', 'ui')
        if self.same(current_service, self.service, self.service['spec']):
            self.guarded('service', 'ui', self.service, self.service['spec'],
                         [dict(op='replace', path='/spec/selector', value=self.maintenance_spec['selector'])])
        else:
            require(self.same(current_service, self.service, self.maintenance_spec),
                    'foreign_service_spec_recovery_refused')
        self.receipt['entry_restored'] = False
        self.wait_endpoints(False)
        self.stage('recovery_entry_maintenance_confirmed')
        api_before, ui_before = self.snapshots['api']['spec'], self.snapshots['ui']['spec']
        worker_before = self.snapshots['scientific-pi-worker']['spec']
        current_worker = self.get('deployment', 'scientific-pi-worker')
        worker_is_candidate = self.same(current_worker, self.snapshots['scientific-pi-worker'], self.worker_spec)
        require(worker_is_candidate or self.same(current_worker, self.snapshots['scientific-pi-worker'], worker_before),
                'foreign_worker_spec_recovery_refused')
        current_ui = self.get('deployment', 'ui')
        if self.same(current_ui, self.snapshots['ui'], self.ui_spec):
            self.replace_spec('ui', self.ui_spec, self.zero_spec)
            self.wait_ui_stopped(self.zero_spec)
        elif self.same(current_ui, self.snapshots['ui'], self.zero_spec):
            self.wait_ui_stopped(self.zero_spec)
        else:
            require(self.same(current_ui, self.snapshots['ui'], ui_before), 'foreign_ui_spec_recovery_refused')
        current_api = self.get('deployment', 'api')
        api_is_candidate = self.same(current_api, self.snapshots['api'], self.api_spec)
        api_is_zero = self.same(current_api, self.snapshots['api'], self.api_zero_spec)
        require(api_is_candidate or api_is_zero or self.same(current_api, self.snapshots['api'], api_before),
                'foreign_api_spec_recovery_refused')
        # Do not stop a baseline API when an active-task drain deferred the
        # release before any backend change. Once either backend changed, fence
        # reconciliation until the old singleton worker is ready again.
        if api_is_candidate or api_is_zero or worker_is_candidate:
            if not api_is_zero:
                self.replace_spec('api', current_api['spec'], self.api_zero_spec)
            self.wait_stopped('api', self.api_zero_spec)
            if worker_is_candidate:
                counts = self.worker_counts()
                active = sum(value for state, value in counts.items() if state not in TERMINAL)
                self.receipt['rollback_drain'] = dict(worker_counts=counts, worker_active=active)
                if active:
                    # A reopened entry may accept work before a later check
                    # fails. Keep its new worker and restore the matching API
                    # so publication can finish; never run an old binary over
                    # active revision jobs. Entry remains closed for review.
                    self.replace_spec('api', self.api_zero_spec, self.api_spec)
                    self.wait_rollout('api', self.api_spec, 'candidate_api_retained_for_active_work')
                    raise ReleaseError('rollback_deferred_active_research_candidate_backends_retained')
                self.replace_spec('scientific-pi-worker', self.worker_spec, worker_before)
            self.wait_rollout('scientific-pi-worker', worker_before, 'worker_rollback')
            self.replace_spec('api', self.api_zero_spec, api_before)
        else:
            self.check('deployment', 'scientific-pi-worker', self.snapshots['scientific-pi-worker'], worker_before)
        self.wait_rollout('api', api_before, 'api_rollback')
        current_ui = self.get('deployment', 'ui')
        if self.same(current_ui, self.snapshots['ui'], self.zero_spec):
            self.replace_spec('ui', self.zero_spec, ui_before)
        else:
            require(self.same(current_ui, self.snapshots['ui'], ui_before), 'foreign_ui_spec_recovery_refused')
        self.wait_rollout('ui', ui_before, 'ui_rollback')
        self.check('deployment', 'scientific-pi-worker', self.snapshots['scientific-pi-worker'],
                   self.snapshots['scientific-pi-worker']['spec'])
        self.receipt['rollback'] = 'baseline_worker_api_ui_and_readiness_verified'
        self.stage('worker_api_ui_rollback_ready')

    def reopen(self, expected_api, expected_ui, expected_worker=None):
        self.check('deployment', 'api', self.snapshots['api'], expected_api)
        self.check('deployment', 'ui', self.snapshots['ui'], expected_ui)
        self.check('deployment', 'scientific-pi-worker', self.snapshots['scientific-pi-worker'],
                   self.snapshots['scientific-pi-worker']['spec'] if expected_worker is None else expected_worker)
        current = self.get('service', 'ui')
        if self.same(current, self.service, self.maintenance_spec):
            self.guarded('service', 'ui', self.service, self.maintenance_spec,
                         [dict(op='replace', path='/spec/selector', value=self.service['spec']['selector'])])
        else:
            require(self.same(current, self.service, self.service['spec']), 'foreign_service_spec_reopen_refused')
        self.wait_endpoints(True)
        self.preserved(expected_api, expected_ui, self.service['spec'], expected_worker)
        self.receipt['entry_restored'] = True
        self.stage('ui_entry_restored')

    def run(self):
        failed = False
        try:
            self.prepare()
            self.drain()
            self.apply()
            self.reopen(self.api_spec, self.ui_spec, self.worker_spec)
        except BaseException as exc:
            failed = True
            code = str(exc) if isinstance(exc, ReleaseError) else 'unexpected_release_response'
            self.receipt.update(status='failed_entry_may_remain_in_maintenance', error_code=code,
                                error_type=type(exc).__name__)
            self.stage('release_failed', error_code=code)
            try:
                if self.maintenance_attempted:
                    self.recover()
                    self.reopen(self.snapshots['api']['spec'], self.snapshots['ui']['spec'])
                    self.receipt['status'] = ('deferred_active_research_entry_restored'
                                              if code == 'active_research_release_deferred' else 'failed_worker_api_ui_rolled_back_entry_restored')
                else:
                    self.receipt['rollback'] = 'not_needed_no_entry_or_deployment_patch_attempted'
            except BaseException as rollback_exc:
                self.receipt['rollback'] = 'unconfirmed_manual_review_required_entry_not_reopened'
                self.receipt['rollback_error_code'] = (str(rollback_exc) if isinstance(rollback_exc, ReleaseError)
                                                       else 'unexpected_recovery_response')
                self.stage('recovery_unconfirmed', error_code=self.receipt['rollback_error_code'])
        finally:
            self.receipt['finished_at'] = now()
            self.save('receipt.json', self.receipt)
            print(json.dumps({key: self.receipt.get(key) for key in
                              ('status', 'worker_image', 'api_image', 'api_source_sha256', 'ui_source_sha256', 'configmap',
                               'source_commit', 'entry_restored', 'rollback', 'error_code', 'private_directory')}, ensure_ascii=True), flush=True)
        return 1 if failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-image', required=True)
    parser.add_argument('--api-image', required=True)
    parser.add_argument('--api-source-sha256', required=True)
    parser.add_argument('--ui-source', required=True)
    parser.add_argument('--ui-source-sha256', required=True)
    parser.add_argument('--source-commit', required=True, help='Exact panghu_agent commit checked out on this server')
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    for name in ('worker_image', 'api_image'):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]*@sha256:[0-9a-f]{64}', getattr(args, name)):
            parser.error('--' + name.replace('_', '-') + ' must be an immutable repository@sha256:digest')
    for name in ('api_source_sha256', 'ui_source_sha256'):
        if not re.fullmatch(r'[0-9a-f]{64}', getattr(args, name)):
            parser.error('--' + name.replace('_', '-') + ' must be 64 lowercase hexadecimal characters')
    if not re.fullmatch(r'[0-9a-f]{40}', args.source_commit):
        parser.error('--source-commit must be the full 40-character panghu_agent Git commit')
    os.umask(0o077)
    try:
        release = Release(args)
    except BaseException as exc:
        print(json.dumps(dict(status='preparation_refused', error_code=str(exc) if isinstance(exc, ReleaseError)
                              else 'private_directory_unavailable')), flush=True)
        return 1
    return release.run()


if __name__ == '__main__':
    sys.exit(main())
