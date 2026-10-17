"""Render a versioned ConfigMap and matching Deployment without YAML dependencies."""
import argparse
import hashlib
import os
import re
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--image', required=True)
parser.add_argument('--upstream', choices=('custom', 'deepseek'), default=os.getenv('UPSTREAM') or None)
args = parser.parse_args()
if any(c.isspace() for c in args.image) or not args.image:
    parser.error('image must be a nonempty container image reference')
source = (Path(__file__).parent / 'k8s.yaml').read_text(encoding='utf-8')
if args.upstream:
    source, count = re.subn(r'("active_upstream"\s*:\s*)"[^"]+"', lambda m: m[1] + '"' + args.upstream + '"', source)
    if count != 1:
        parser.error('expected exactly one active_upstream')
config = source.split('kind: ConfigMap\n', 1)[1].split('\n---', 1)[0]
name = 'llm-service-config-' + hashlib.sha256(config.encode()).hexdigest()[:12]
print(source.replace('llm-service-config-v2', name).replace('arm-cluster-master:5000/llm-service:latest', args.image))
