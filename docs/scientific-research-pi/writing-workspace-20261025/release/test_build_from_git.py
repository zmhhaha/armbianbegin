"""Offline release source/probe control-flow checks; never runs Docker or SSH."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / 'panghu_agent'
spec = importlib.util.spec_from_file_location('scientific_writing_builder',HERE / 'build_from_git.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class BuildSourceTests(unittest.TestCase):
    def test_image_worker_probe_actual_http_factory_and_fixed_input_flow(self):
        code = '''import importlib.util,os,sys
from pathlib import Path
source=Path(sys.argv[1]); sys.path.insert(0,str(source))
for key in ('SCIENTIFIC_PI_MODEL_API_KEY','LLM_SERVICE_TOKEN','SMTP_PASSWORD'):
    os.environ.pop(key,None)
for key in ('SCIENTIFIC_PI_CAPABILITY_VERIFIED','SCIENTIFIC_PI_MODEL_VERIFIED','SCIENTIFIC_PI_ISOLATION_VERIFIED'):
    os.environ[key]='0'
spec=importlib.util.spec_from_file_location('worker_probe',source/'tests/scientific_pi/deployment/worker_image_probe.py')
probe=importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
probe.verify_installation=lambda:([],{},'local dependency gate skipped','local dependency gate skipped')
probe.main(source,Path(sys.argv[2]))
'''
        with tempfile.TemporaryDirectory(dir=ROOT / '.research-temp') as directory:
            result = subprocess.run([sys.executable,'-B','-c',code,str(SOURCE),directory],
                capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt['status'],'passed')
        self.assertFalse(receipt['real_model_executed'])
        self.assertFalse(receipt['production_readiness_verified'])
        self.assertIn('synthetic_fixed_input_http_admission_idempotency_cancel_and_terminal_replay',receipt['checks'])

    def test_image_api_probe_complete_loopback_revision_and_adoption_flow(self):
        # Exact dependency installation can only be checked in the built image.
        # Keep that gate separate while exercising the entire installed-source
        # HTTP fixture here in a fresh process with the existing local deps.
        code = '''import importlib.util,sys
from pathlib import Path
from types import SimpleNamespace
source=Path(sys.argv[1]); sys.path.insert(0,str(source))
spec=importlib.util.spec_from_file_location('image_probe',source/'tests/scientific_pi/deployment/api_image_probe.py')
probe=importlib.util.module_from_spec(spec); spec.loader.exec_module(probe)
probe.verify_installation=lambda:({},SimpleNamespace(stdout='local gate skipped; image required'))
probe.main()
'''
        result = subprocess.run([sys.executable,'-B','-c',code,str(SOURCE)],capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt['status'],'passed')
        self.assertTrue(receipt['explicit_adoption_verified'])
        self.assertTrue(receipt['revision_dispatch_performed'])
        self.assertFalse(receipt['real_model_executed'])
        self.assertIn('candidate_diff_explicit_adoption_idempotent_replay_conflict_and_exact_original_downloads',receipt['checks'])

    def test_contexts_cover_docker_copy_inputs_without_unrelated_services(self):
        for names,dockerfile in ((builder.FILES,'Dockerfile.scientific-pi-api'),
                                  (builder.WORKER_FILES,'Dockerfile.scientific-pi')):
            self.assertEqual(len(names),len(set(names)))
            self.assertFalse(any(any(part in name.lower() for part in ('secret','.env','ppt_service','crewai')) for name in names))
            self.assertTrue(all((SOURCE / name).is_file() for name in names))
            text = (SOURCE / dockerfile).read_text().replace('\\\n',' ')
            for line in text.splitlines():
                parts = shlex.split(line)
                if not parts or parts[0] != 'COPY' or any(part.startswith('--from=') for part in parts):
                    continue
                for name in parts[1:-1]:
                    name = name.rstrip('/')
                    self.assertTrue(name in names or any(path.startswith(name+'/') for path in names),name)
                    if (SOURCE / name).is_dir():
                        tracked = subprocess.check_output(['git','ls-files','--',name],cwd=SOURCE,text=True).splitlines()
                        self.assertTrue(set(tracked) <= set(names),(dockerfile,set(tracked)-set(names)))

    def test_real_git_blobs_ignore_changed_worktree_and_untracked_secret(self):
        with tempfile.TemporaryDirectory(prefix='.build-from-git-',dir=ROOT / '.research-temp') as directory:
            repo = Path(directory)
            names = set(builder.FILES) | set(builder.WORKER_FILES) | {
                'app/ui/scientific_agent.py','tests/scientific_pi/deployment/api_image_probe.py',
                'tests/scientific_pi/deployment/worker_image_probe.py'}
            original = {}
            for number,name in enumerate(sorted(names)):
                raw = ('committed fixture '+str(number)+'\n科研\n').encode('utf-8')
                path = repo / name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(raw)
                original[name] = raw
            subprocess.run(['git','init','-q',str(repo)],check=True,capture_output=True)
            subprocess.run(['git','-C',str(repo),'add','--all'],check=True,capture_output=True)
            subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                            'commit','-qm','Synthetic release inputs'],check=True,capture_output=True)
            commit = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
            (repo / 'app/ui/scientific_agent.py').write_bytes(b'uncommitted changed source')
            (repo / 'pi_worker/private.env').write_bytes(b'synthetic-never-in-build')
            def git(*args): return subprocess.check_output(['git','-C',str(repo),*args])
            payload = builder.source_payload(git,commit)
            self.assertEqual(payload['ui-source.py'],original['app/ui/scientific_agent.py'])
            self.assertEqual(payload['worker-context/pi_worker/app.py'],original['pi_worker/app.py'])
            self.assertFalse(any('private.env' in name for name in payload))
            out = repo / 'output'
            out.mkdir()
            manifest = builder.write_payload(out,payload,commit)
            for row in manifest['files']:
                self.assertEqual(hashlib.sha256((out / row['path']).read_bytes()).hexdigest(),row['sha256'])
            self.assertEqual(manifest['commit'],commit)
            self.assertEqual(json.loads((out/'source-manifest.json').read_text()),manifest)

    def test_worker_probe_has_no_network_caps_or_production_mounts(self):
        command = builder.probe_command(Path('/isolated/output'),'fixture:local','worker')
        self.assertIn('65532:65532',command)
        self.assertEqual(command[command.index('--network')+1],'none')
        self.assertEqual(command[command.index('--cap-drop')+1],'ALL')
        self.assertIn('--read-only',command)
        self.assertIn('--tmpfs',command)
        self.assertFalse(any('secret' in value.lower() or 'docker.sock' in value or '/tmp:' in value for value in command))
        self.assertTrue(command[command.index('-v')+1].endswith(':/app/worker_image_probe.py:ro'))

    def test_api_probe_keeps_image_dependency_lock_unmasked(self):
        command = builder.probe_command(Path('/isolated/output'),'fixture:local','api')
        self.assertNotIn('--tmpfs',command)
        self.assertEqual(command[-1],'/app/api_image_probe.py')

    def test_failed_probe_removes_container_and_never_pushes_image(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.research-temp') as directory:
            out = Path(directory)
            actions = []
            def run(command,logfile,timeout=1800): actions.append(command)
            def docker_run(command,**kwargs):
                if command[:3] == ['docker','start','-a']:
                    raise subprocess.CalledProcessError(1,command)
                return subprocess.CompletedProcess(command,0)
            with patch.object(builder.subprocess,'check_output',return_value='synthetic-container'), \
                 patch.object(builder.subprocess,'run',side_effect=docker_run) as invoked:
                with self.assertRaises(subprocess.CalledProcessError):
                    builder.build_image(out,'a'*40,dict(source_digest='b'*64),'worker',run)
            self.assertEqual(len(actions),1)
            self.assertEqual(actions[0][:2],['docker','build'])
            self.assertTrue(any(call.args[0] == ['docker','rm','-f','synthetic-container'] for call in invoked.call_args_list))
            self.assertFalse((out/'worker-build-receipt.json').exists())


if __name__ == '__main__':
    unittest.main()
