"""Offline artifact/manifest/cleanup checks; never claim real Pi acceptance."""
import ast
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location('real_revision_launcher',HERE/'run_real_revision.py')
launcher=importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)
# Load only the public serialization helpers. No fake Scheduler, model, runtime
# or executable probe is used in these control-flow tests.
tree=ast.parse((HERE/'real_revision_probe.py').read_text(encoding='utf-8'))
helpers={"base64":base64,"hashlib":hashlib}
exec(compile(ast.Module(body=[node for node in tree.body if isinstance(node,ast.FunctionDef)
     and node.name in ('sha','review_artifacts')],type_ignores=[]),'<export helpers>','exec'),helpers)


def fixture():
    data={name:('record '+name+'\n') for name in launcher.MATERIALS}
    files={prefix+name:data[name].encode() for prefix in ('base-','candidate-') for name in launcher.MATERIALS}
    files['candidate-report.md']=b'connected revised paragraphs\n'
    files['revision-output.json']=b'{"claims":[]}'
    files['validation.json']=b'{"valid":true}'
    files['public-provenance.json']=b'{"retrieval_performed":false,"full_text_restored":false}'
    record=helpers['review_artifacts']('synthetic-task',files)
    receipt=dict(status='passed',task_id='synthetic-task',
        base_sha256=hashlib.sha256(files['base-report.md']).hexdigest(),
        candidate_sha256=hashlib.sha256(files['candidate-report.md']).hexdigest())
    return data,files,record,receipt


def worker_fixture():
    worker={'spec':{'selector':{'matchLabels':{'app':'scientific-pi-worker'}},'template':{
        'metadata':{'labels':{'app':'scientific-pi-worker'}},'spec':{
            'containers':[{'name':'worker','image':'old','env':[{'name':'SCIENTIFIC_PI_IMAGE_DIGEST','value':'old'}],
                'volumeMounts':[{'name':'data','mountPath':'/data'}],'readinessProbe':{'httpGet':{'path':'/ready'}}}],
            'volumes':[{'name':'data','persistentVolumeClaim':{'claimName':'production'}}]}}}}
    policies=[{'spec':{'podSelector':{'matchLabels':{'app':'scientific-pi-worker'}},'policyTypes':['Ingress','Egress'],
                'ingress':[],'egress':[{'to':[{'ipBlock':{'cidr':'192.0.2.0/24'}}]}]}}]
    return worker,policies


class RealRevisionReleaseTests(unittest.TestCase):
    def test_complete_export_recovers_exact_public_bytes(self):
        data,files,record,receipt=fixture()
        with tempfile.TemporaryDirectory(dir=ROOT/'.research-temp') as directory:
            path=Path(directory)
            result=launcher.recover_artifacts((json.dumps(record)+'\n').encode(),receipt,data,path)
            self.assertEqual(result['file_count'],len(launcher.REVIEW_FILES))
            for name,raw in files.items(): self.assertEqual((path/'review-artifacts'/name).read_bytes(),raw)
            self.assertFalse(any('runtime' in name or 'task.json' in name or '.env' in name for name in files))

    def test_tampering_unknown_paths_duplicate_encoding_and_limits_fail_before_writes(self):
        for mutation in ('checksum','path','duplicate','base64','oversize','original','receipt','missing'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(dir=ROOT/'.research-temp') as directory:
                data,files,record,receipt=fixture()
                row=record['artifacts'][0]
                if mutation=='checksum': row['sha256']='0'*64
                if mutation=='path': row['name']='../private.env'
                if mutation=='duplicate': record['artifacts'][-1]=copy.deepcopy(row)
                if mutation=='base64': row['data']='!!!!'
                if mutation=='oversize': row['size_bytes']=launcher.MAX_REVIEW_BYTES+1
                if mutation=='original': data['report.md']='different committed source'
                if mutation=='receipt': receipt['candidate_sha256']='0'*64
                if mutation=='missing': record['artifacts'].pop()
                path=Path(directory)
                with self.assertRaises(ValueError):
                    launcher.recover_artifacts(json.dumps(record).encode(),receipt,data,path)
                self.assertFalse((path/'review-artifacts').exists())

    def test_duplicate_export_records_and_missing_pass_receipt_are_rejected(self):
        data,_,record,receipt=fixture()
        with tempfile.TemporaryDirectory(dir=ROOT/'.research-temp') as directory:
            with self.assertRaises(ValueError):
                launcher.recover_artifacts((json.dumps(record)+'\n'+json.dumps(record)).encode(),receipt,data,Path(directory))
            with self.assertRaises(ValueError):
                launcher.recover_artifacts(json.dumps(record).encode(),None,data,Path(directory))

    def test_fixed_git_inputs_exclude_dirty_and_untracked_files(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.research-temp') as directory:
            repo=Path(directory)
            names=[launcher.SOURCE+'real_revision_probe.py']+[
                launcher.SOURCE+'real-review-materials/'+name for name in launcher.MATERIALS]
            for name in names:
                path=repo/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('committed '+name,encoding='utf-8')
            subprocess.run(['git','init','-q',str(repo)],check=True,capture_output=True)
            subprocess.run(['git','-C',str(repo),'add','--all'],check=True,capture_output=True)
            subprocess.run(['git','-C',str(repo),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                'commit','-qm','Synthetic committed materials'],check=True,capture_output=True)
            commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
            (repo/names[0]).write_text('uncommitted probe',encoding='utf-8')
            (repo/'private.env').write_text('not-an-input',encoding='utf-8')
            data=launcher.fixed_git_data(repo,commit)
            self.assertEqual(data['probe.py'],'committed '+names[0])
            self.assertEqual(set(data),{'probe.py',*launcher.MATERIALS})

    def test_manifest_replaces_production_pvc_and_distinguishes_all_selectors(self):
        worker,policies=worker_fixture()
        original=copy.deepcopy(worker)
        manifest=launcher.isolated_manifest(worker,policies,'own-probe','worker@sha256:'+'a'*64,{},'run')
        pod=manifest['items'][-1]
        self.assertEqual(worker,original)
        self.assertEqual(pod['metadata']['labels']['app'],'scientific-revision-acceptance')
        self.assertFalse(pod['spec']['automountServiceAccountToken'])
        self.assertEqual(pod['spec']['volumes'][0],{'name':'data','emptyDir':{'sizeLimit':'512Mi'}})
        self.assertFalse(any('persistentVolumeClaim' in value for value in pod['spec']['volumes']))
        self.assertEqual(manifest['items'][1]['spec']['podSelector'],{'matchLabels':{'acceptance':'own-probe'}})
        self.assertEqual(manifest['items'][1]['spec']['egress'],policies[0]['spec']['egress'])
        self.assertTrue(all(item['metadata']['annotations'][launcher.RUN_ANNOTATION]=='run' for item in manifest['items']))
        worker['spec']['template']['spec']['volumes'].append({'name':'other','persistentVolumeClaim':{'claimName':'production'}})
        with self.assertRaises(AssertionError):
            launcher.isolated_manifest(worker,policies,'own-probe','worker@sha256:'+'a'*64,{},'run')

    def test_cleanup_uses_uid_precondition_and_preserves_changed_ownership(self):
        attempted=[dict(kind='ConfigMap',name='own-cm',uid='cm-uid'),dict(kind='Pod',name='own-pod',uid='pod-uid'),
                   dict(kind='NetworkPolicy',name='replaced',uid='old-uid'),dict(kind='ConfigMap',name='foreign')]
        actions=[]
        def run(command,**kwargs):
            actions.append(command)
            if 'get' in command:
                name=command[command.index('get')+1].split('/')[1]
                uid={'own-cm':'cm-uid','own-pod':'pod-uid','replaced':'new-uid','foreign':'foreign-uid'}[name]
                marker='other' if name=='foreign' else 'run'
                return subprocess.CompletedProcess(command,0,json.dumps({'metadata':{
                    'uid':uid,'annotations':{launcher.RUN_ANNOTATION:marker}}}).encode())
            body=json.loads(Path(command[-1]).read_text())
            self.assertIn(body['preconditions']['uid'],('pod-uid','cm-uid'))
            self.assertNotIn('--selector',command)
            self.assertTrue(any(value.startswith('--raw=/api/v1/namespaces/scientific-agent/') for value in command))
            return subprocess.CompletedProcess(command,0,b'{}')
        with tempfile.TemporaryDirectory(dir=ROOT/'.research-temp') as directory, patch.object(launcher.subprocess,'run',side_effect=run):
            results=launcher.cleanup_resources(['kubectl'],attempted,Path(directory),'run')
        self.assertEqual([row['status'] for row in results],['ownership_changed','uid_changed','deleted','deleted'])
        self.assertEqual(len([action for action in actions if 'delete' in action]),2)

    def test_cleanup_recovers_own_resource_when_create_response_was_lost(self):
        def run(command,**kwargs):
            if 'get' in command:
                return subprocess.CompletedProcess(command,0,json.dumps({'metadata':{
                    'uid':'server-created-uid','annotations':{launcher.RUN_ANNOTATION:'run'}}}).encode())
            body=json.loads(Path(command[-1]).read_text())
            self.assertEqual(body['preconditions'],{'uid':'server-created-uid'})
            self.assertIn('--raw=/apis/networking.k8s.io/v1/namespaces/scientific-agent/networkpolicies/own-policy',command)
            return subprocess.CompletedProcess(command,0,b'{}')
        with tempfile.TemporaryDirectory(dir=ROOT/'.research-temp') as directory, patch.object(launcher.subprocess,'run',side_effect=run):
            results=launcher.cleanup_resources(['kubectl'],[dict(kind='NetworkPolicy',name='own-policy')],Path(directory),'run')
        self.assertEqual(results[0]['status'],'deleted')


if __name__=='__main__': unittest.main()
