"""Run the committed real-Pi probe in an isolated candidate-image Pod.

Uses fixed Git blobs, reviewed existing model configuration and an empty data
volume. Public review artifacts are recovered from private logs before precise
UID-guarded cleanup of only the resources created by this invocation.
"""
import argparse
import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid


SOURCE='docs/scientific-research-pi/writing-workspace-20261025/release/'
MATERIALS=('report.md','papers.jsonl','evidence.jsonl','claims.jsonl','references.json')
REVIEW_FILES={'base-report.md','candidate-report.md','revision-output.json',
             'validation.json','public-provenance.json'} | {
    prefix+name for prefix in ('base-','candidate-') for name in MATERIALS if name!='report.md'}
RUN_ANNOTATION='openspec.panghuer.top/acceptance-run'
MAX_REVIEW_BYTES=4*1024*1024


def fixed_git_data(repo, commit):
    if not re.fullmatch('[0-9a-f]{40}',commit):
        raise ValueError('A full Git commit is required')
    def git(path):
        return subprocess.check_output(['git','-C',str(repo),'show',commit+':'+path]).decode('utf-8')
    data={'probe.py':git(SOURCE+'real_revision_probe.py')}
    data.update({name:git(SOURCE+'real-review-materials/'+name) for name in MATERIALS})
    return data


def isolated_manifest(worker, network_policies, name, image, data, run_token):
    pod_spec=copy.deepcopy(worker['spec']['template']['spec'])
    assert len(pod_spec['containers'])==1 and not pod_spec.get('initContainers')
    container=pod_spec['containers'][0]
    container['image']=image
    container['command']=['python','-B','/acceptance/probe.py','--materials-dir','/acceptance','--output-dir','/data/acceptance']
    container.pop('args',None)
    for key in ('ports','livenessProbe','readinessProbe','startupProbe'):
        container.pop(key,None)
    for item in container.get('env',[]):
        if item['name']=='SCIENTIFIC_PI_IMAGE_DIGEST':
            item.clear();item.update(name='SCIENTIFIC_PI_IMAGE_DIGEST',value=image.split('@')[1])
    assert any(x['name']=='SCIENTIFIC_PI_IMAGE_DIGEST' for x in container.get('env',[]))
    container['volumeMounts'].append(dict(name='acceptance-source',mountPath='/acceptance',readOnly=True))
    data_mount=next(x['name'] for x in container['volumeMounts'] if x['mountPath']=='/data')
    assert any(volume['name']==data_mount for volume in pod_spec['volumes'])
    for volume in pod_spec['volumes']:
        if volume['name']==data_mount:
            volume.clear();volume.update(name=data_mount,emptyDir={'sizeLimit':'512Mi'})
    assert not any('persistentVolumeClaim' in x or 'hostPath' in x for x in pod_spec['volumes'])
    pod_spec['volumes'].append(dict(name='acceptance-source',configMap={'name':name,'defaultMode':292}))
    pod_spec.update(restartPolicy='Never',automountServiceAccountToken=False,activeDeadlineSeconds=780)
    labels=copy.deepcopy(worker['spec']['template']['metadata'].get('labels',{}))
    labels.update(app='scientific-revision-acceptance',acceptance=name)
    selector=worker['spec']['selector']['matchLabels']
    assert selector and not all(labels.get(key)==value for key,value in selector.items())
    def metadata(resource_name):
        return dict(name=resource_name,namespace='scientific-agent',
                    labels={'acceptance':name},annotations={RUN_ANNOTATION:run_token})
    pod=dict(apiVersion='v1',kind='Pod',metadata=metadata(name),spec=pod_spec)
    pod['metadata']['labels']=labels
    cm=dict(apiVersion='v1',kind='ConfigMap',metadata=metadata(name),immutable=True,data=data)
    policies=[]
    for policy in network_policies:
        selector=policy['spec'].get('podSelector',{}).get('matchLabels',{})
        if selector.get('app')!='scientific-pi-worker': continue
        spec=copy.deepcopy(policy['spec'])
        assert not spec['podSelector'].get('matchExpressions')
        spec['podSelector']={'matchLabels':{'acceptance':name}}
        policies.append(dict(apiVersion='networking.k8s.io/v1',kind='NetworkPolicy',
            metadata=metadata(name+'-'+str(len(policies))),spec=spec))
    assert policies,'Expected an existing reviewed worker network policy'
    return dict(apiVersion='v1',kind='List',items=[cm,*policies,pod])


def recover_artifacts(logs, receipt, data, output_dir):
    """Validate the entire explicit allowlist before writing any review bytes."""
    if len(logs)>16*1024*1024:
        raise ValueError('Probe logs exceed the recovery bound')
    records=[]
    for line in logs.decode('utf-8',errors='replace').splitlines():
        try: value=json.loads(line)
        except ValueError: continue
        if isinstance(value,dict) and value.get('type')=='review_artifacts': records.append(value)
    if len(records)!=1 or not receipt or receipt.get('status')!='passed':
        raise ValueError('Exactly one public artifact record and a passed receipt are required')
    record=records[0]
    if record.get('schema_version')!='1' or record.get('task_id')!=receipt.get('task_id'):
        raise ValueError('Review artifact task identity mismatch')
    rows=record.get('artifacts')
    if not isinstance(rows,list) or len(rows)!=len(REVIEW_FILES):
        raise ValueError('Incomplete public review artifacts')
    files={}
    total=0
    for row in rows:
        name=row.get('name')
        size=row.get('size_bytes')
        if name not in REVIEW_FILES or name in files or row.get('encoding')!='base64':
            raise ValueError('Unexpected or duplicate public artifact')
        if type(size) is not int or size<0 or size>MAX_REVIEW_BYTES or not isinstance(row.get('data'),str):
            raise ValueError('Invalid artifact size or encoding')
        if len(row['data'])>4*((size+2)//3):
            raise ValueError('Encoded artifact exceeds declared size')
        raw=base64.b64decode(row['data'],validate=True)
        total+=len(raw)
        if len(raw)!=size or total>MAX_REVIEW_BYTES or hashlib.sha256(raw).hexdigest()!=row.get('sha256'):
            raise ValueError('Public review artifact checksum mismatch')
        files[name]=raw
    if set(files)!=REVIEW_FILES:
        raise ValueError('Missing public review artifact')
    for name in MATERIALS:
        if files['base-'+name]!=data[name].encode('utf-8'):
            raise ValueError('Original public materials differ from fixed Git inputs')
    for name in ('papers.jsonl','evidence.jsonl','references.json'):
        if files['candidate-'+name]!=files['base-'+name]:
            raise ValueError('Fixed evidence changed')
    for key,name in (('base_sha256','base-report.md'),('candidate_sha256','candidate-report.md')):
        if hashlib.sha256(files[name]).hexdigest()!=receipt.get(key):
            raise ValueError('Public report does not match the probe receipt')
    if json.loads(files['validation.json']).get('valid') is not True:
        raise ValueError('Candidate validation did not pass')
    provenance=json.loads(files['public-provenance.json'])
    if provenance.get('retrieval_performed') is not False or provenance.get('full_text_restored') is not False:
        raise ValueError('Candidate exceeded the recorded-evidence boundary')
    review_dir=output_dir/'review-artifacts'
    review_dir.mkdir(exist_ok=False)
    manifest=[]
    for name,raw in sorted(files.items()):
        (review_dir/name).write_bytes(raw)
        manifest.append(dict(name=name,size_bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    (review_dir/'manifest.json').write_text(json.dumps(dict(task_id=record['task_id'],files=manifest),indent=2)+'\n')
    return dict(path=str(review_dir),file_count=len(files),total_bytes=total)


def cleanup_resources(k, attempted, output_dir, run_token):
    """Delete with API UID preconditions, never a selector or deployment name."""
    results=[]
    plurals={'Pod':('v1','pods'),'ConfigMap':('v1','configmaps'),
             'NetworkPolicy':('networking.k8s.io/v1','networkpolicies')}
    for number,item in enumerate(reversed(attempted)):
        kind,name=item['kind'],item['name']
        row=dict(kind=kind,name=name)
        try:
            current=subprocess.run(k+['get',kind+'/'+name,'--ignore-not-found','-o','json'],capture_output=True,check=True).stdout
            if not current.strip():
                row['status']='absent';results.append(row);continue
            metadata=json.loads(current)['metadata']
            if metadata.get('annotations',{}).get(RUN_ANNOTATION)!=run_token:
                row['status']='ownership_changed';results.append(row);continue
            if item.get('uid') and metadata['uid']!=item['uid']:
                row['status']='uid_changed';results.append(row);continue
            uid=metadata['uid']
            body=output_dir/('cleanup-'+str(number)+'.json')
            body.write_text(json.dumps(dict(apiVersion='v1',kind='DeleteOptions',
                preconditions={'uid':uid},propagationPolicy='Background',gracePeriodSeconds=0)))
            api,plural=plurals[kind]
            prefix='/api/' if api=='v1' else '/apis/'
            url=prefix+api+'/namespaces/scientific-agent/'+plural+'/'+name
            subprocess.run(k+['delete','--raw='+url,'-f',str(body)],capture_output=True,check=True)
            row.update(status='deleted',uid=uid)
        except (subprocess.SubprocessError,ValueError,KeyError,OSError) as exc:
            row.update(status='cleanup_failed',error_type=type(exc).__name__)
        results.append(row)
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-repo',type=Path,required=True)
    parser.add_argument('--root-commit',required=True)
    parser.add_argument('--worker-image',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--kubeconfig',default='/etc/kubernetes/super-admin.conf')
    args=parser.parse_args()
    assert re.fullmatch('[0-9a-f]{40}',args.root_commit)
    assert re.fullmatch(r'arm-cluster-master:5000/scientific-pi-worker@sha256:[0-9a-f]{64}',args.worker_image)
    os.umask(0o077)
    args.output_dir.mkdir(parents=True,exist_ok=False)
    k=['kubectl','--kubeconfig='+args.kubeconfig,'-n','scientific-agent']
    def call(*values): return subprocess.check_output(k+list(values),stderr=subprocess.PIPE)
    def obj(*values): return json.loads(call(*values))
    assert subprocess.check_output(['git','-C',str(args.root_repo),'rev-parse','HEAD'],text=True).strip()==args.root_commit
    data=fixed_git_data(args.root_repo,args.root_commit)
    source_sha=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    run_token=uuid.uuid4().hex
    suffix=args.root_commit[:10]+'-'+datetime.now(timezone.utc).strftime('%H%M%S')+'-'+run_token[:6]
    name='scientific-revision-acceptance-'+suffix
    worker=obj('get','deployment/scientific-pi-worker','-o','json')
    manifest=isolated_manifest(worker,obj('get','networkpolicies','-o','json')['items'],name,args.worker_image,data,run_token)
    manifest_path=args.output_dir/'isolated-manifest.json'
    manifest_path.write_text(json.dumps(manifest,indent=2))
    result=dict(status='failed',observed_at=datetime.now(timezone.utc).isoformat(),pod=name,
        root_commit=args.root_commit,source_sha256=source_sha,worker_image=args.worker_image,
        isolated_data_volume=True,production_service_selected=False,production_database_accessed=False,
        private_output=str(args.output_dir))
    attempted=[]
    try:
        subprocess.run(k+['create','--dry-run=server','-f',str(manifest_path)],check=True,capture_output=True)
        # Keep a ledger even if create succeeds server-side but its response is
        # interrupted: the unique ownership marker then permits safe recovery.
        for number,resource in enumerate(manifest['items']):
            resource_path=args.output_dir/('create-'+str(number)+'.json')
            resource_path.write_text(json.dumps(resource))
            entry=dict(kind=resource['kind'],name=resource['metadata']['name'])
            attempted.append(entry)
            created=json.loads(subprocess.check_output(k+['create','-f',str(resource_path),'-o','json'],stderr=subprocess.PIPE))
            entry['uid']=created['metadata']['uid']
        print(json.dumps(dict(stage='isolated_real_pi_probe_created',pod=name,worker_image=args.worker_image)),flush=True)
        deadline=time.monotonic()+790
        last=None
        status={}
        phase=None
        while time.monotonic()<deadline:
            status=obj('get','pod/'+name,'-o','json')
            phase=status.get('status',{}).get('phase')
            if phase!=last:
                print(json.dumps(dict(stage='probe_pod',phase=phase)),flush=True);last=phase
            if phase in ('Succeeded','Failed'): break
            time.sleep(2)
        (args.output_dir/'pod-after.json').write_text(json.dumps(status,indent=2))
        logs=call('logs',name,'-c',manifest['items'][-1]['spec']['containers'][0]['name'])
        (args.output_dir/'probe.log').write_bytes(logs)
        summaries=[]
        for line in logs.decode('utf-8',errors='replace').splitlines():
            try: value=json.loads(line)
            except ValueError: continue
            if isinstance(value,dict) and value.get('status')=='passed': summaries.append(value)
        receipt=summaries[-1] if summaries else None
        if phase!='Succeeded' or not receipt:
            raise ValueError('Real Pi Pod or its receipt did not pass')
        if receipt.get('actual_pi_called') is not True or receipt.get('actual_model_called') is not True or receipt.get('fixture_runtime') is not False:
            raise ValueError('A real Pi/model execution is required')
        if receipt.get('image_digest')!=args.worker_image.split('@')[1]:
            raise ValueError('Real Pi receipt came from a different image')
        result['review_artifacts']=recover_artifacts(logs,receipt,data,args.output_dir)
        result.update(status='passed',probe=receipt)
    except Exception as exc:
        # Never relay model logs, full artifact records, env or raw subprocess
        # diagnostics to stdout; private files carry the detailed evidence.
        result['error_type']=type(exc).__name__
        diagnostic=dict(error_type=type(exc).__name__,message=str(exc))
        stderr=getattr(exc,'stderr',None)
        if stderr:
            diagnostic['stderr']=stderr.decode('utf-8',errors='replace') if isinstance(stderr,bytes) else str(stderr)
        (args.output_dir/'launcher-error.json').write_text(json.dumps(diagnostic,ensure_ascii=False,indent=2)+'\n')
    finally:
        result['cleanup']=cleanup_resources(k,attempted,args.output_dir,run_token)
        if any(item['status']=='cleanup_failed' for item in result['cleanup']):
            result['status']='failed'
        (args.output_dir/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False),flush=True)
    if result['status']!='passed': raise SystemExit(1)


if __name__=='__main__':main()
