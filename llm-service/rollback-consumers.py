"""Validate/restore snapshots saved by migrate-consumers.py.

Defaults to server-side dry-run. --apply restores ConfigMaps then Deployments.
Replace whole resources rather than merging env value/valueFrom fields.
"""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--backup-dir', type=Path, required=True)
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
K = ['kubectl', '--kubeconfig=/etc/kubernetes/super-admin.conf']
snapshots = [json.loads(p.read_text()) for p in args.backup_dir.glob('*.json')]
if not snapshots:
    parser.error('no snapshots found')
for obj in snapshots:
    if obj.get('kind') not in ('ConfigMap', 'Deployment') or not obj.get('metadata', {}).get('namespace'):
        parser.error('only namespaced ConfigMap/Deployment snapshots are supported')
snapshots.sort(key=lambda obj: (obj['kind'] != 'ConfigMap', obj['metadata']['namespace'], obj['metadata']['name']))
for obj in snapshots:
    ns, name, kind = obj['metadata']['namespace'], obj['metadata']['name'], obj['kind']
    current = json.loads(subprocess.check_output(K + ['-n', ns, 'get', kind, name, '-o', 'json']))
    obj.pop('status', None)
    for field in ('uid', 'creationTimestamp', 'generation', 'managedFields'):
        obj['metadata'].pop(field, None)
    obj['metadata']['resourceVersion'] = current['metadata']['resourceVersion']
    command = K + ['replace', '-f', '-']
    if not args.apply:
        command.append('--dry-run=server')
    subprocess.run(command, input=json.dumps(obj), text=True, check=True)
print('Restored' if args.apply else 'Validated', len(snapshots), 'snapshots')
