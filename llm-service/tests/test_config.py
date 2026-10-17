import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
from config import ConfigError, load_config
from upstream import _payload


class RoutingConfigTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((Path(__file__).parents[1] / 'config.example.json').read_text())

    def load(self, data=None, **env):
        values = {'LLM_ALIASES': json.dumps(self.data if data is None else data),
                  'CUSTOM_API_KEY': 'test', 'DEEPSEEK_API_KEY': 'test', 'LLM_GUARD': '', **env}
        with patch.dict(os.environ, values):
            return load_config()[0]

    def test_switch_changes_stable_routes_not_fixed_routes(self):
        before = self.load()
        self.data['active_upstream'] = 'deepseek'
        after = self.load()
        for tier in ('guarded', 'trusted'):
            a, b = before['llm-'+tier], after['llm-'+tier]
            self.assertEqual((a.upstream, b.upstream), ('custom', 'deepseek'))
            self.assertEqual((a.tier, b.tier), (tier, tier))
            self.assertNotEqual(a.revision, b.revision)
            self.assertEqual(before['custom-'+tier], after['custom-'+tier])
            self.assertEqual(_payload(a, [], {})['model'], 'gpt-6')

    def test_rejects_old_missing_unknown_version_and_unknown_reference(self):
        cases = [{'aliases': {}}, {**self.data, 'version': 1}, {**self.data, 'version': 3},
                 {k:v for k,v in self.data.items() if k != 'version'},
                 {**self.data, 'aliases': {}}, {**self.data, 'active_upstream': 'absent'}]
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ConfigError): self.load(data)
        self.data['routes']['llm-guarded']['upstream'] = 'missing'
        with self.assertRaises(ConfigError): self.load()

    def test_active_credentials_required_reserved_credentials_optional(self):
        self.load(OPENAI_API_KEY='')
        with self.assertRaises(ConfigError): self.load(CUSTOM_API_KEY='')

    def test_snapshot_and_nested_defaults_are_immutable(self):
        self.data['routes']['llm-trusted']['defaults'] = {'response_format': {'type': 'json_object'}}
        routes = self.load()
        with self.assertRaises(TypeError): routes['x'] = routes['llm-trusted']
        with self.assertRaises(TypeError): routes['llm-trusted'].defaults['response_format']['type'] = 'text'
        body = _payload(routes['llm-trusted'], [], {})
        body['response_format']['type'] = 'text'
        self.assertEqual(routes['llm-trusted'].defaults['response_format']['type'], 'json_object')

    def test_defaults_cannot_escape_tier_or_redirect_upstream(self):
        for defaults in ({'tools': [{}]}, {'max_tokens': 2049}, {'temperature': -1}, {'api_key': 'bad'}):
            self.data['routes']['llm-guarded']['defaults'] = defaults
            with self.subTest(defaults=defaults), self.assertRaises(ConfigError): self.load()

    def test_revision_tracks_guard_but_not_secret_rotation(self):
        before = self.load()['llm-guarded'].revision
        self.assertEqual(before, self.load(CUSTOM_API_KEY='rotated')['llm-guarded'].revision)
        self.assertNotEqual(before, self.load(LLM_GUARD='{"detection":"reject"}')['llm-guarded'].revision)

    def test_malformed_and_duplicate_json(self):
        for raw in ('{', '{"version":2,"version":2}', '[]'):
            with patch.dict(os.environ, {'LLM_ALIASES': raw}), self.assertRaises(ConfigError): load_config()

    def test_unknown_fields_bad_numbers_and_tier(self):
        for field, value in [('tier', 'admin'), ('timeout_seconds', -1), ('headers', {})]:
            data = copy.deepcopy(self.data)
            data['routes']['llm-guarded'][field] = value
            with self.subTest(field=field), self.assertRaises(ConfigError): self.load(data)
