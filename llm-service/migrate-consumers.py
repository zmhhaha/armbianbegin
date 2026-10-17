"""One-time stable-route migration. Run on the cluster host after gateway acceptance.

Saves Deployment/ConfigMap snapshots before changes. Does not touch Secrets.
Usage: python3 migrate-consumers.py --image-tag <tag> --backup-dir <new directory>
"""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--image-tag', required=True)
parser.add_argument('--backup-dir', type=Path, required=True)
parser.add_argument('--resume', action='store_true', help='resume using the original snapshots without overwriting them')
args = parser.parse_args()
args.backup_dir.mkdir(parents=True, exist_ok=args.resume)
K = ['kubectl', '--kubeconfig=/etc/kubernetes/super-admin.conf']
targets = [
    ('data', 'rag-service', 'trusted'), ('content-agents', 'content-llm-service', 'trusted'),
    ('research-agent', 'api', 'trusted'), ('scientific-agent', 'api', 'trusted'),
    ('game-review-agent', 'api', 'trusted'), ('literature-downloader', 'api', 'trusted'),
    ('baijiazhengming', 'baijiazhengming-api', 'guarded'), ('xuye', 'xuye-server', 'guarded'),
    ('tewu', 'tewu-server', 'guarded'), ('guanliao', 'guanliao-server', 'guarded'),
    ('qianfu', 'qianfu-server', 'guarded'), ('shapan', 'shapan-agent-worker', 'guarded'),
    ('school-of-one', 'duel-judge', 'guarded'), ('school-of-one', 'combo-judge', 'guarded'),
    ('school-of-one', 'training-ground', 'guarded'),
    ('school-of-one', 'server', None), ('school-of-one', 'frontend', None),
]
images = {('baijiazhengming', 'baijiazhengming-api'): 'baijiazhengming-api',
          ('literature-downloader', 'api'): 'literature-downloader-api',
          ('school-of-one', 'server'): 'school-server', ('school-of-one', 'frontend'): 'school-frontend'}

def get(ns, kind, name):
    return json.loads(subprocess.check_output(K + ['-n', ns, 'get', kind, name, '-o', 'json']))

def save(ns, kind, obj):
    path = args.backup_dir / f'{ns}-{kind}-{obj["metadata"]["name"]}.json'
    if not path.exists():
        path.write_text(json.dumps(obj, indent=2))

deployments = []
configs = {}
# Read and back up everything before the first write.
for ns, name, tier in targets:
    obj = get(ns, 'deployment', name)
    save(ns, 'deployment', obj)
    deployments.append((ns, name, tier, obj))
    if tier:
        for container in obj['spec']['template']['spec']['containers']:
            names = [ref.get('configMapRef', {}).get('name') for ref in container.get('envFrom', [])]
            names += [env.get('valueFrom', {}).get('configMapKeyRef', {}).get('name')
                      for env in container.get('env', []) if env['name'] == 'LLM_MODEL']
            for cm in names:
                if cm and (ns, cm) not in configs:
                    config = get(ns, 'configmap', cm)
                    if config.get('data', {}).get('LLM_MODEL'):
                        save(ns, 'configmap', config)
                        configs[ns, cm] = (config, tier)
for (ns, name), (obj, tier) in configs.items():
    if obj['data']['LLM_MODEL'] not in ('custom-'+tier, 'llm-'+tier):
        raise RuntimeError(f'unexpected model configuration in {ns}/{name}')
for (ns, name), (obj, tier) in configs.items():
    subprocess.run(K + ['-n', ns, 'patch', 'configmap', name, '--type=merge', '-p',
                       json.dumps({'data': {'LLM_MODEL': 'llm-'+tier}})], check=True)
for ns, name, tier, obj in deployments:
    containers = []
    for container in obj['spec']['template']['spec']['containers']:
        update = {'name': container['name']}
        if tier:
            update['env'] = [{'name': 'LLM_MODEL', 'value': 'llm-'+tier, 'valueFrom': None}]
        image = images.get((ns, name))
        if image and len(obj['spec']['template']['spec']['containers']) == 1:
            update['image'] = f'arm-cluster-master:5000/{image}:{args.image_tag}'
        containers.append(update)
    patch = {'spec': {'template': {'spec': {'containers': containers}}}}
    subprocess.run(K + ['-n', ns, 'patch', 'deployment', name, '--type=strategic', '-p', json.dumps(patch)], check=True)
for ns, name, tier, obj in deployments:
    subprocess.run(K + ['-n', ns, 'rollout', 'status', 'deployment/'+name, '--timeout=600s'], check=True)
print('Migration complete; backups:', args.backup_dir)
