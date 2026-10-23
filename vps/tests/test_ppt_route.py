"""Offline entrypoint contracts; does not contact nginx, Cloudflare or K8s.

These checks cover protected asset caching, preserved nginx runtime variables,
and the effective union of frpc egress rules. Real nginx/CNI/OAuth acceptance is
separate and must be performed by the deploying administrator.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
import unittest

import yaml


VPS = Path(__file__).resolve().parents[1]
REPOSITORY = VPS.parent


def labels_match(selector, labels):
    if any(labels.get(k) != v for k, v in selector.get('matchLabels', {}).items()):
        return False
    for expression in selector.get('matchExpressions', []):
        key, operator = expression['key'], expression['operator']
        if operator != 'NotIn':
            raise AssertionError('unexpected expression in this scoped fixture')
        if labels.get(key) in expression['values']:
            return False
    return True


class PptEntryContracts(unittest.TestCase):
    def test_exact_server_disables_all_cache_and_public_static_locations(self):
        source = (VPS / 'nginx/ppt-service.conf.template').read_text(encoding='utf-8')
        body = re.sub(r'#[^\n]*', '', source)
        self.assertIn('server_name ppt.${BASE_DOMAIN};', body)
        self.assertNotIn('default_server', body)
        self.assertIn('access_log off;', body)
        self.assertEqual(re.findall(r'\blocation\s+([^\{]+)\{', body), ['/ '])
        for directive in ('proxy_cache off;', 'proxy_cache_bypass 1;',
                          'proxy_no_cache 1;', 'add_header Cache-Control "no-store" always;'):
            self.assertIn(directive, body)
        self.assertNotIn('proxy_ignore_headers', body)
        self.assertNotIn('sub_filter', body)
        self.assertNotIn('beian-footer.conf', body)
        self.assertIn('proxy_pass http://127.0.0.1:8080;', body)
        self.assertNotIn('127.0.0.1:8000', body)

    def test_real_envsubst_preserves_runtime_auth_cookie_and_host(self):
        executable = shutil.which('envsubst')
        git_envsubst = Path('C:/Program Files/Git/usr/bin/envsubst.exe')
        if executable is None and git_envsubst.is_file():
            executable = str(git_envsubst)
        if executable is None:
            self.skipTest('envsubst unavailable; install gettext for rendering verification')
        source = (VPS / 'nginx/ppt-service.conf.template').read_bytes()
        # Deliberately set the names nginx uses: restricted substitution must
        # keep them literal even when the invoking environment has values.
        env = os.environ | {'BASE_DOMAIN': 'panghuer.top', 'HTTPS_PORT': '443',
                            'host': 'attacker.invalid', 'http_authorization': 'SHOULD_NOT_RENDER',
                            'http_cookie': 'SHOULD_NOT_RENDER'}
        result = subprocess.run([executable, '${BASE_DOMAIN} ${HTTPS_PORT}'],
                                input=source, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env, check=True)
        rendered = result.stdout.decode('utf-8')
        self.assertNotIn('${BASE_DOMAIN}', rendered)
        self.assertNotIn('${HTTPS_PORT}', rendered)
        self.assertNotIn('SHOULD_NOT_RENDER', rendered)
        self.assertNotIn('attacker.invalid', rendered)
        for directive in ('listen 443 ssl http2;', 'server_name ppt.panghuer.top;',
                          'proxy_set_header Host $host;',
                          'proxy_set_header Authorization $http_authorization;',
                          'proxy_set_header Cookie $http_cookie;',
                          'proxy_set_header X-Forwarded-Proto https;',
                          'proxy_set_header Connection $connection_upgrade;'):
            self.assertIn(directive, rendered)

    def test_upload_stream_and_cookie_size_contract(self):
        source = (VPS / 'nginx/ppt-service.conf.template').read_text(encoding='utf-8')
        for directive in ('client_max_body_size 26m;', 'large_client_header_buffers 8 32k;',
                          'proxy_request_buffering off;', 'proxy_buffering off;',
                          'proxy_intercept_errors off;', 'proxy_read_timeout 3600s;'):
            self.assertIn(directive, source)

    def test_frpc_effective_union_only_allows_ppt_website_4180(self):
        documents = list(yaml.safe_load_all((VPS / 'k8s/frpc.yaml').read_text(encoding='utf-8')))
        documents.append(yaml.safe_load((VPS / 'k8s/ppt-service-egress.yaml').read_text(encoding='utf-8')))
        policies = [d['spec'] for d in documents if d and d['kind'] == 'NetworkPolicy'
                    and labels_match(d['spec']['podSelector'], {'app': 'frpc'})]

        def allowed(namespace, pod, port):
            for policy in policies:
                for rule in policy.get('egress', []):
                    if not any(p['protocol'] == 'TCP' and p['port'] == port for p in rule['ports']):
                        continue
                    for peer in rule['to']:
                        if 'ipBlock' in peer:
                            continue  # fixed public VPS /32 cannot match Pod fixtures
                        if (labels_match(peer.get('namespaceSelector', {}),
                                         {'kubernetes.io/metadata.name': namespace})
                                and labels_match(peer.get('podSelector', {}), pod)):
                            return True
            return False

        site = {'app.kubernetes.io/name': 'ppt-site'}
        self.assertTrue(allowed('ppt-service-test', site, 4180))
        for pod, port in ((site, 8000), (site, 5432), ({'app': 'other'}, 4180)):
            self.assertFalse(allowed('ppt-service-test', pod, port))
        # The added exception must not change existing non-PPT web permissions.
        for namespace in ('hermes', 'dsh', 'default', 'scientific-agent'):
            for port in (80, 3000, 4173, 4180, 7860, 8000, 8080, 8090):
                self.assertTrue(allowed(namespace, {'app': 'existing'}, port))

    def test_frpc_fragment_contains_only_public_route(self):
        fragment = (VPS / 'k8s/routes/ppt-service.toml').read_text(encoding='utf-8')
        data = tomllib.loads(fragment)
        self.assertEqual(set(data), {'proxies'})
        self.assertEqual(data['proxies'], [{
            'name': 'ppt-service-test', 'type': 'http', 'customDomains': ['ppt.panghuer.top'],
            'localIP': 'ppt-site.ppt-service-test.svc.cluster.local', 'localPort': 4180}])
        self.assertTrue(fragment.isascii())

    def test_tunnel_fragment_targets_oauth_and_egress_requires_identity(self):
        public = json.loads((REPOSITORY / 'cloudflare-tunnel/ppt/public-hostname.json').read_text(encoding='utf-8'))
        self.assertEqual(public, {
            'hostname': 'ppt.panghuer.top',
            'service': 'http://ppt-site.ppt-service-test.svc.cluster.local:4180',
            'originRequest': {'httpHostHeader': 'ppt.panghuer.top'}})
        template = yaml.safe_load((REPOSITORY / 'cloudflare-tunnel/ppt/connector-egress.yaml.template')
                                  .read_text(encoding='utf-8'))
        self.assertEqual(template['metadata']['namespace'], 'REQUIRED_CONNECTOR_NAMESPACE')
        self.assertIn('REQUIRED_CONNECTOR_LABEL_KEY', template['spec']['podSelector']['matchLabels'])
        rule = template['spec']['egress'][0]
        self.assertEqual(rule['ports'], [{'protocol': 'TCP', 'port': 4180}])
        self.assertEqual(rule['to'], [{
            'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'ppt-service-test'}},
            'podSelector': {'matchLabels': {'app.kubernetes.io/name': 'ppt-site'}}}])
        ingress = yaml.safe_load((REPOSITORY / 'cloudflare-tunnel/ppt/site-ingress.yaml.template')
                                 .read_text(encoding='utf-8'))
        self.assertEqual(ingress['metadata']['namespace'], 'ppt-service-test')
        self.assertEqual(ingress['spec']['policyTypes'], ['Ingress'])
        self.assertEqual(ingress['spec']['podSelector'], rule['to'][0]['podSelector'])
        reciprocal = ingress['spec']['ingress'][0]
        self.assertEqual(reciprocal['ports'], rule['ports'])
        self.assertEqual(reciprocal['from'], [{
            'namespaceSelector': {'matchLabels': {
                'kubernetes.io/metadata.name': template['metadata']['namespace']}},
            'podSelector': template['spec']['podSelector']}])

    def test_optional_vps_is_not_installed_without_explicit_flag(self):
        source = (VPS / 'install.sh').read_text(encoding='utf-8')
        start = source.index('if [[ "${PPT_VPS_ENABLED:-0}" == 1 ]]; then')
        end = source.index('\n  fi', start)
        block = source[start:end]
        self.assertIn("envsubst '${BASE_DOMAIN} ${HTTPS_PORT}'", block)
        self.assertIn('nginx/ppt-service.conf.template', block)
        self.assertIn('/etc/nginx/sites-available/ppt-service.conf', block)
        self.assertNotIn('systemctl', block)
        self.assertIn('nginx -t || die', source[end:])


if __name__ == '__main__':
    unittest.main()
