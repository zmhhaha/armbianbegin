"""Offline control-flow simulation of the versioned rollout; no subprocess I/O."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest


SCRIPT = Path(__file__).with_name('rollout.py')
spec = importlib.util.spec_from_file_location('writing_rollout_under_test', SCRIPT)
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)


def obj(kind, name, value):
    return dict(kind=kind, metadata=dict(name=name, namespace='scientific-agent', uid='fixture-' + name,
                                        resourceVersion='1', generation=1), spec=copy.deepcopy(value))


def pointer(value, path):
    for key in path.strip('/').split('/'):
        key = key.replace('~1', '/').replace('~0', '~')
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def replace(value, path, replacement):
    parts = path.strip('/').split('/')
    current = value
    for key in parts[:-1]:
        key = key.replace('~1', '/').replace('~0', '~')
        current = current[int(key)] if isinstance(current, list) else current[key]
    key = parts[-1].replace('~1', '/').replace('~0', '~')
    current[int(key) if isinstance(current, list) else key] = copy.deepcopy(replacement)


class MemoryRelease(rollout.Release):
    def __init__(self, api='baseline', ui='zero', service='maintenance', worker='baseline'):
        api_before = dict(replicas=1, template=dict(spec=dict(containers=[dict(name='api', image='fixture:old')]),
                                                  metadata=dict(labels={'app': 'research-api'})))
        ui_before = dict(replicas=1, selector=dict(matchLabels={'app': 'ui'}),
                         template=dict(metadata=dict(labels={'app': 'ui'}),
                                       spec=dict(containers=[dict(name='ui', image='fixture:unchanged')],
                                                 volumes=[dict(name='source', configMap=dict(name='fixture-old-cm'))])))
        worker_before = dict(replicas=1, template=dict(spec=dict(containers=[dict(name='worker', image='fixture:protected')],
                                                               volumes=[dict(name='data', persistentVolumeClaim={'claimName': 'protected'})])))
        self.snapshots = {'api': obj('Deployment', 'api', api_before),
                          'ui': obj('Deployment', 'ui', ui_before),
                          'scientific-pi-worker': obj('Deployment', 'scientific-pi-worker', worker_before)}
        self.service = obj('Service', 'ui', dict(type='ClusterIP', selector={'app': 'ui'},
                                                ports=[dict(port=80, targetPort=7860)]))
        self.maintenance_spec = copy.deepcopy(self.service['spec'])
        self.maintenance_spec['selector']['scientific-writing-maintenance'] = 'fixture-run'
        self.zero_spec = copy.deepcopy(ui_before)
        self.zero_spec['replicas'] = 0
        self.api_zero_spec = copy.deepcopy(api_before)
        self.api_zero_spec['replicas'] = 0
        self.api_spec = copy.deepcopy(api_before)
        self.api_spec['template']['spec']['containers'][0]['image'] = 'fixture:candidate'
        self.ui_spec = copy.deepcopy(ui_before)
        self.ui_spec['template']['spec']['volumes'][0]['configMap']['name'] = 'fixture-candidate-cm'
        self.worker_spec = copy.deepcopy(worker_before)
        self.worker_spec['template']['spec']['containers'][0]['image'] = 'fixture:new-worker'
        api_spec = {'baseline': api_before, 'zero': self.api_zero_spec, 'candidate': self.api_spec}[api]
        ui_spec = {'baseline': ui_before, 'zero': self.zero_spec, 'candidate': self.ui_spec}[ui]
        self.objects = {('deployment', name): copy.deepcopy(value) for name, value in self.snapshots.items()}
        self.objects['deployment', 'api']['spec'] = copy.deepcopy(api_spec)
        self.objects['deployment', 'ui']['spec'] = copy.deepcopy(ui_spec)
        self.objects['deployment', 'scientific-pi-worker']['spec'] = copy.deepcopy(worker_before if worker == 'baseline' else self.worker_spec)
        self.objects['service', 'ui'] = copy.deepcopy(self.service)
        self.objects['service', 'ui']['spec'] = copy.deepcopy(self.service['spec'] if service == 'baseline' else self.maintenance_spec)
        self.receipt = dict(events=[])
        self.out = Path('/synthetic/private')
        self.sequence, self.saved, self.events, self.patches = 0, {}, [], []
        self.maintenance_attempted = True
        self.ready = {'api': False, 'ui': False, 'scientific-pi-worker':worker == 'baseline'}
        self.before_patch = None
        self.api_index = self.worker_index = 0
        self.source_reference = '/spec/template/spec/volumes/0/configMap/name'
        self.cm_name = 'fixture-candidate-cm'
        self.cm = dict(immutable=True, data={'agent.py':'fixture-ui'})
        self.objects['configmap', self.cm_name] = copy.deepcopy(self.cm)
        self.args = SimpleNamespace(api_image='fixture:candidate', worker_image='fixture:new-worker')
        self.probe_failure = None
        self.queue_counts = [{'succeeded':1}, {'succeeded':1}]

    def get(self, kind, name, optional=False):
        return copy.deepcopy(self.objects.get((kind, name))) if optional else copy.deepcopy(self.objects[kind, name])

    def save(self, name, value):
        self.saved[name] = copy.deepcopy(value)

    def stage(self, name, **safe_details):
        self.events.append(name)

    def command(self, args, timeout=25, allow_failure=False):
        # Execute the real guarded() generated JSON Patch against an in-memory
        # object, including every UID/resourceVersion/spec test.
        self.sequence += 1
        assert 'patch' in args, 'No real kubectl or process invocation is allowed'
        index = args.index('patch')
        kind, name = args[index + 1:index + 3]
        patch = self.saved[Path(args[args.index('--patch-file') + 1]).name]
        assert [item['path'] for item in patch[:3]] == ['/metadata/uid', '/metadata/resourceVersion', '/spec']
        assert all(item['op'] == 'test' for item in patch[:3])
        current = self.objects[kind, name]
        if self.before_patch:
            self.before_patch(kind, name, current)
        for item in patch:
            if item['op'] == 'test':
                if pointer(current, item['path']) != item['value']:
                    raise rollout.ReleaseError('simulated_json_patch_precondition_failed')
            else:
                assert item['op'] == 'replace'
        updated = copy.deepcopy(current)
        for item in patch:
            if item['op'] == 'replace':
                replace(updated, item['path'], item['value'])
        if kind == 'deployment':
            assert name in ('api', 'ui', 'scientific-pi-worker')
            assert self.objects['service', 'ui']['spec'] == self.maintenance_spec, 'Deployment recovery while entry is open'
            self.ready[name] = False
        if kind == 'service' and updated['spec'] == self.service['spec']:
            assert all(self.ready.values()), 'Entry reopened before both baseline deployments were ready'
        updated['metadata']['resourceVersion'] = str(int(current['metadata']['resourceVersion']) + 1)
        if kind == 'deployment':
            updated['metadata']['generation'] += 1
        self.objects[kind, name] = updated
        self.patches.append((kind, name, copy.deepcopy(updated['spec'])))
        self.events.append('patch:' + kind + ':' + name)
        return SimpleNamespace(stdout=json.dumps(updated), returncode=0)

    def wait_endpoints(self, available):
        expected = self.service['spec'] if available else self.maintenance_spec
        assert self.objects['service', 'ui']['spec'] == expected
        self.events.append('endpoints:' + str(available))

    def wait_ui_stopped(self, expected_spec):
        self.check('deployment', 'ui', self.snapshots['ui'], expected_spec)
        assert expected_spec['replicas'] == 0
        self.events.append('ui_stopped')

    def wait_stopped(self, name, expected_spec):
        self.check('deployment', name, self.snapshots[name], expected_spec)
        assert expected_spec['replicas'] == 0
        self.events.append(name + '_stopped')

    def worker_counts(self):
        return self.queue_counts.pop(0)

    def exec_python(self, name, container, code):
        assert name == 'api' and container == 'api'
        return {'active':0}

    def probe_worker(self):
        assert self.objects['deployment', 'api']['spec'] == self.api_zero_spec
        self.events.append('worker_capability_probe')
        if self.probe_failure == 'worker':
            raise rollout.ReleaseError('worker_runtime_probe_failed')

    def probe(self):
        self.events.append('candidate_api_ui_probe')
        if self.probe_failure == 'api':
            raise rollout.ReleaseError('api_runtime_probe_failed')

    def wait_rollout(self, name, expected_spec, phase):
        current = self.check('deployment', name, self.snapshots[name], expected_spec)
        assert expected_spec['replicas'] == 1
        self.ready[name] = True
        self.events.append('ready:' + name)
        return current


class RecoveryTests(unittest.TestCase):
    def restore(self, release):
        release.recover()
        self.assertEqual(release.receipt['rollback'], 'baseline_worker_api_ui_and_readiness_verified')
        self.assertEqual(release.objects['service', 'ui']['spec'], release.maintenance_spec)
        self.assertLess(release.events.index('endpoints:False'), release.events.index('ready:api'))
        for name in ('api', 'ui'):
            self.assertEqual(release.objects['deployment', name]['spec'], release.snapshots[name]['spec'])
        release.reopen(release.snapshots['api']['spec'], release.snapshots['ui']['spec'])
        self.assertTrue(release.receipt['entry_restored'])
        self.assertEqual(release.objects['service', 'ui']['spec'], release.service['spec'])
        self.assertEqual(release.objects['deployment', 'scientific-pi-worker']['spec'], release.snapshots['scientific-pi-worker']['spec'])

    def test_service_already_reopened_is_closed_before_recovery(self):
        release = MemoryRelease(api='baseline', ui='baseline', service='baseline')
        self.restore(release)
        self.assertEqual(release.events[0], 'patch:service:ui')
        self.assertEqual([item[:2] for item in release.patches], [('service', 'ui'), ('service', 'ui')])

    def test_scale_zero_only_restores_ui_after_api_ready(self):
        release = MemoryRelease()
        self.restore(release)
        self.assertNotIn('patch:deployment:api', release.events)
        self.assertLess(release.events.index('ready:api'), release.events.index('patch:deployment:ui'))

    def test_api_candidate_and_scale_zero_pair_roll_back(self):
        release = MemoryRelease(api='candidate')
        self.restore(release)
        self.assertLess(release.events.index('ready:api'), release.events.index('patch:deployment:ui'))

    def test_both_candidates_and_reopened_entry_roll_back_closed(self):
        release = MemoryRelease(api='candidate', ui='candidate', service='baseline')
        self.restore(release)
        self.assertEqual([item[:2] for item in release.patches],
                         [('service', 'ui'), ('deployment', 'ui'), ('deployment', 'api'), ('deployment', 'api'),
                          ('deployment', 'ui'), ('service', 'ui')])
        self.assertLess(release.events.index('ui_stopped'), release.events.index('patch:deployment:api'))

    def test_foreign_ui_spec_is_preserved_and_api_is_not_patched(self):
        release = MemoryRelease(api='candidate', ui='candidate', service='baseline')
        release.objects['deployment', 'ui']['spec']['third_party'] = True
        foreign = copy.deepcopy(release.objects['deployment', 'ui'])
        with self.assertRaisesRegex(rollout.ReleaseError, 'foreign_ui_spec_recovery_refused'):
            release.recover()
        self.assertEqual(release.objects['deployment', 'ui'], foreign)
        self.assertEqual(release.objects['deployment', 'api']['spec'], release.api_spec)
        self.assertEqual(release.objects['service', 'ui']['spec'], release.maintenance_spec)

    def test_foreign_api_spec_is_preserved_and_entry_stays_closed(self):
        release = MemoryRelease(api='candidate')
        release.objects['deployment', 'api']['spec']['third_party'] = True
        foreign = copy.deepcopy(release.objects['deployment', 'api'])
        with self.assertRaisesRegex(rollout.ReleaseError, 'foreign_api_spec_recovery_refused'):
            release.recover()
        self.assertEqual(release.objects['deployment', 'api'], foreign)
        self.assertEqual(release.objects['deployment', 'ui']['spec'], release.zero_spec)
        self.assertEqual(release.patches, [])

    def test_recreated_ui_uid_is_preserved(self):
        release = MemoryRelease(api='candidate', ui='candidate')
        release.objects['deployment', 'ui']['metadata']['uid'] = 'foreign-new-uid'
        before = copy.deepcopy(release.objects)
        with self.assertRaisesRegex(rollout.ReleaseError, 'foreign_ui_spec_recovery_refused'):
            release.recover()
        self.assertEqual(release.objects, before)

    def test_foreign_service_selector_prevents_any_recovery_patch(self):
        release = MemoryRelease(api='candidate', ui='candidate')
        release.objects['service', 'ui']['spec']['selector'] = {'app': 'another-ui'}
        before = copy.deepcopy(release.objects)
        with self.assertRaisesRegex(rollout.ReleaseError, 'foreign_service_spec_recovery_refused'):
            release.recover()
        self.assertEqual(release.objects, before)
        self.assertEqual(release.patches, [])

    def test_foreign_worker_spec_is_never_changed_or_reopened(self):
        release = MemoryRelease(api='candidate', ui='candidate')
        release.objects['deployment', 'scientific-pi-worker']['spec']['third_party'] = True
        foreign = copy.deepcopy(release.objects['deployment', 'scientific-pi-worker'])
        with self.assertRaisesRegex(rollout.ReleaseError, 'foreign_worker_spec_recovery_refused'):
            release.recover()
        self.assertEqual(release.objects['deployment', 'scientific-pi-worker'], foreign)
        self.assertEqual(release.objects['service', 'ui']['spec'], release.maintenance_spec)
        self.assertFalse(release.receipt['entry_restored'])

    def test_fresh_resource_version_race_rejects_guarded_ui_patch(self):
        release = MemoryRelease(api='candidate', ui='candidate')

        def race(kind, name, current):
            if kind == 'deployment' and name == 'ui':
                current['metadata']['resourceVersion'] = str(int(current['metadata']['resourceVersion']) + 1)

        release.before_patch = race
        with self.assertRaisesRegex(rollout.ReleaseError, 'simulated_json_patch_precondition_failed'):
            release.recover()
        self.assertEqual(release.objects['deployment', 'ui']['spec'], release.ui_spec)
        self.assertEqual(release.objects['deployment', 'api']['spec'], release.api_spec)
        self.assertEqual(release.objects['service', 'ui']['spec'], release.maintenance_spec)
        self.assertEqual(release.patches, [])

    def test_worker_candidate_rolled_back_before_api_and_ui_restore(self):
        release = MemoryRelease(api='candidate', ui='candidate', worker='candidate')
        self.restore(release)
        self.assertLess(release.events.index('api_stopped'), release.events.index('patch:deployment:scientific-pi-worker'))
        self.assertLess(release.events.index('ready:scientific-pi-worker'), release.events.index('ready:api'))
        self.assertLess(release.events.index('ready:api'), release.events.index('ready:ui'))

    def test_worker_patch_response_lost_and_api_still_zero_recovers(self):
        release = MemoryRelease(api='zero', worker='candidate')
        self.restore(release)
        self.assertEqual([name for kind,name,_ in release.patches if kind == 'deployment'],
                         ['scientific-pi-worker','api','ui'])

    def test_active_task_after_reopen_retains_candidate_worker_api_and_closes_entry(self):
        release = MemoryRelease(api='candidate', ui='candidate', service='baseline', worker='candidate')
        release.queue_counts = [{'running':1}]
        with self.assertRaisesRegex(rollout.ReleaseError, 'rollback_deferred_active_research_candidate_backends_retained'):
            release.recover()
        self.assertEqual(release.objects['service','ui']['spec'], release.maintenance_spec)
        self.assertEqual(release.objects['deployment','scientific-pi-worker']['spec'],release.worker_spec)
        self.assertEqual(release.objects['deployment','api']['spec'],release.api_spec)
        self.assertNotIn('patch:deployment:scientific-pi-worker',release.events)


class CoordinatedReleaseTests(unittest.TestCase):
    def test_apply_starts_worker_capability_before_api_before_ui_and_reopens_all_ready(self):
        release = MemoryRelease(api='zero')
        release.apply()
        release.reopen(release.api_spec,release.ui_spec,release.worker_spec)
        self.assertLess(release.events.index('ready:scientific-pi-worker'),release.events.index('worker_capability_probe'))
        self.assertLess(release.events.index('worker_capability_probe'),release.events.index('patch:deployment:api'))
        self.assertLess(release.events.index('ready:api'),release.events.index('patch:deployment:ui'))
        self.assertLess(release.events.index('candidate_api_ui_probe'),release.events.index('endpoints:True'))
        self.assertEqual(release.objects['deployment','scientific-pi-worker']['spec']['template']['spec']['volumes'],
                         release.snapshots['scientific-pi-worker']['spec']['template']['spec']['volumes'])

    def test_worker_probe_failure_does_not_start_api_or_ui_and_recovery_restores_baseline(self):
        release = MemoryRelease(api='zero')
        release.probe_failure='worker'
        with self.assertRaisesRegex(rollout.ReleaseError,'worker_runtime_probe_failed'):
            release.apply()
        self.assertNotIn('patch:deployment:api',release.events)
        self.assertNotIn('patch:deployment:ui',release.events)
        release.recover()
        self.assertEqual(release.objects['deployment','scientific-pi-worker']['spec'],
                         release.snapshots['scientific-pi-worker']['spec'])

    def test_candidate_api_ui_probe_failure_recovers_all_backends(self):
        release=MemoryRelease(api='zero')
        release.probe_failure='api'
        with self.assertRaisesRegex(rollout.ReleaseError,'api_runtime_probe_failed'):
            release.apply()
        release.recover()
        for name in ('api','ui','scientific-pi-worker'):
            self.assertEqual(release.objects['deployment',name]['spec'],release.snapshots[name]['spec'])

    def test_drain_stops_api_then_observes_empty_queue_before_changing_worker(self):
        release=MemoryRelease(api='baseline',ui='baseline',service='baseline')
        release.drain()
        self.assertEqual(release.receipt['drain']['worker_active_after_api_stop'],0)
        self.assertEqual(release.objects['deployment','api']['spec'],release.api_zero_spec)
        self.assertEqual(release.objects['deployment','scientific-pi-worker']['spec'],
                         release.snapshots['scientific-pi-worker']['spec'])
        self.assertLess(release.events.index('api_stopped'),release.events.index('api_stopped_drain_observed'))

    def test_late_enqueue_after_first_drain_defers_worker_change_and_recovers_running_api(self):
        release=MemoryRelease(api='baseline',ui='baseline',service='baseline')
        release.queue_counts=[{}, {'queued':1}]
        with self.assertRaisesRegex(rollout.ReleaseError,'active_research_release_deferred'):
            release.drain()
        release.recover()
        self.assertEqual(release.objects['deployment','api']['spec'],release.snapshots['api']['spec'])
        self.assertNotIn('patch:deployment:scientific-pi-worker',release.events)

    def test_first_drain_active_task_does_not_stop_api_or_worker(self):
        release=MemoryRelease(api='baseline',ui='baseline',service='baseline')
        release.queue_counts=[{'running':1}]
        with self.assertRaisesRegex(rollout.ReleaseError,'active_research_release_deferred'):
            release.drain()
        self.assertEqual(release.objects['deployment','api']['spec'],release.snapshots['api']['spec'])
        self.assertNotIn('patch:deployment:scientific-pi-worker',release.events)
        release.recover()
        release.reopen(release.snapshots['api']['spec'],release.snapshots['ui']['spec'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
