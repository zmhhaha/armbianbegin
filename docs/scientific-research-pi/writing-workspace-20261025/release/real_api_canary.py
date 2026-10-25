#!/usr/bin/env python3
"""D2 real deployed-API canary: fixed report/owner; no SQL, cancel or email.

Run inside the API container after the new worker and API are deployed. This
requests a real revision and explicitly adopts only this dedicated canary's
candidate. Resume with the same private output directory after interruptions.
Public API completion is not a substitute for independent worker provenance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request
import uuid


REPORT_ID='ad888da1-6d7d-561d-9eda-4a341efae099'
OWNER='scientific-workbench-production-canary-20261023'
BASE_URL='http://127.0.0.1:8000'
FIELDS=('expected_current_version_id','expected_selection_revision','base_sha256',
        'candidate_sha256','comparison_token')
MAX_RESPONSE=12*1024*1024
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))
INSTRUCTION=('仅使用已经固定的论文、证据和引用，将本节整理为两段连贯的学术综述，'
    '澄清摘要证据能够支持的判断以及不能支持的研究比较。保持原章节标题与现有引用编号，'
    '不得声称读取全文、完成新检索或验证未给出的细节，不新增量化性能、样本量、实验条件或文献。'
    '保留既有论断的证据不足或冲突判断：同一组或其子集证据不能把insufficient/conflicting升级为supported。'
    '拆分或新增论断时也遵守此限制；不能增加支持强度的综合或比较使用insufficient并说明原因。'
    '只改所选章节，明确哪些结论仍需全文或后续实证核验。')


class CanaryError(Exception):
    pass


class ApiError(CanaryError):
    def __init__(self,status,code='api_error',task_id=None):
        super().__init__(code)
        self.status,self.code,self.task_id=status,code,task_id


def require(value,code):
    if not value: raise CanaryError(code)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def identifier(value):
    require(isinstance(value,str) and str(uuid.UUID(value))==value,'invalid_public_identifier')
    return value


def guard(owner,report_id):
    require(owner==OWNER and report_id==REPORT_ID and 'canary' in owner,
            'dedicated_canary_owner_and_report_required')


def request(path,owner=OWNER,*,body=None,key=None):
    require(path.startswith('/') and not path.startswith('//'),'invalid_api_path')
    headers={'Content-Type':'application/json'}
    if owner is not None: headers['X-Forwarded-User']=owner
    if key is not None: headers['Idempotency-Key']=key
    req=urllib.request.Request(BASE_URL+path,headers=headers,
        data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8'),
        method='GET' if body is None else 'POST')
    try: response=OPENER.open(req,timeout=30)
    except urllib.error.HTTPError as exc: response=exc
    except (OSError,urllib.error.URLError): raise ApiError(503,'transport_unavailable') from None
    with response:
        raw=response.read(MAX_RESPONSE+1)
        require(len(raw)<=MAX_RESPONSE,'response_too_large')
        return response.code,raw,{key.casefold():value for key,value in response.headers.items()}


def api(path,owner=OWNER,*,body=None,key=None):
    status,raw,_=request(path,owner,body=body,key=key)
    try: value=json.loads(raw)
    except (ValueError,UnicodeError): raise ApiError(status,'invalid_api_json') from None
    require(isinstance(value,dict),'invalid_api_shape')
    if status!=200:
        detail=value.get('detail')
        detail=detail if isinstance(detail,dict) else {}
        code=detail.get('code','api_error')
        if not isinstance(code,str) or re.fullmatch('[a-z0-9_]{1,100}',code) is None: code='api_error'
        task_id=detail.get('task_id')
        if not isinstance(task_id,str) or re.fullmatch('[0-9a-f-]{36}',task_id) is None: task_id=None
        raise ApiError(status,code,task_id)
    return value


def retry_write(path,body,key=None,attempts=3):
    for attempt in range(attempts):
        try: return api(path,body=body,key=key)
        except ApiError as exc:
            if exc.status not in (502,503,504) or attempt==attempts-1: raise
            time.sleep(2)


def save_state(path,state):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(temp,path)


def select_leaf(index,raw):
    require(index.get('report_sha256')==sha(raw),'section_source_digest_mismatch')
    sections=index.get('sections')
    require(isinstance(sections,list),'sections_missing')
    candidates=[]
    for section in sections:
        if section.get('kind')!='section' or section.get('editable') is not True: continue
        title=section.get('title','')
        if re.search(r'参考|文献|目录|摘要|结论|总结|references|bibliograph|abstract|conclusion',title,re.I): continue
        start,end=section.get('start_byte'),section.get('end_byte')
        require(type(start) is int and type(end) is int and 0<=start<end<=len(raw),'invalid_section_range')
        if any(other.get('kind')=='section' and start<other.get('start_byte',-1)<end for other in sections): continue
        content=raw[start:end]
        require(section.get('sha256')==sha(content),'section_digest_mismatch')
        if not 60<=len(content)<=16000 or not re.search(rb'\[\d+\]',content): continue
        candidates.append(section)
    require(bool(candidates),'no_cited_content_leaf_available')
    return sorted(candidates,key=lambda item:(-item['level'],item['end_byte']-item['start_byte'],item['start_byte']))[0]


def exact_version(version_id,expected_sha=None):
    path='/scientific-report-versions/'+identifier(version_id)
    version=api(path)
    require(version.get('version_id')==version_id and isinstance(version.get('content'),str),'version_identity_mismatch')
    raw=version['content'].encode('utf-8')
    require(version.get('report_sha256')==sha(raw) and (expected_sha is None or sha(raw)==expected_sha),
            'version_digest_mismatch')
    status,download,headers=request(path+'/download')
    require(status==200 and download==raw and headers.get('x-content-type-options')=='nosniff','exact_version_download_mismatch')
    return version,raw


def check_isolation(paths,foreign):
    require(foreign!=OWNER,'foreign_identity_collision')
    for path in paths:
        require(request(path,None)[0]==401,'anonymous_read_not_rejected')
        require(request(path,foreign)[0]==404,'foreign_read_not_rejected')


def review_records(task_id,names,review_dir,prefix):
    path='/scientific-research/'+identifier(task_id)+'/artifacts'
    page=api(path)
    rows=page.get('items')
    require(isinstance(rows,list),'public_artifact_manifest_missing')
    items={row.get('artifact_id'):row for row in rows if isinstance(row,dict)}
    records={}
    for name in names:
        item=items.get(name)
        require(isinstance(item,dict) and type(item.get('size')) is int
                and 0<=item['size']<=4*1024*1024,'public_review_artifact_missing_or_oversize')
        status,raw,_=request(path+'/'+name)
        require(status==200 and len(raw)==item['size'] and sha(raw)==item.get('sha256'),
                'public_review_artifact_checksum_mismatch')
        extension='.json' if name in ('references','revision_output','validation') else '.jsonl'
        (review_dir/(prefix+name+extension)).write_bytes(raw)
        records[name]=raw
    return records


def recover_start(intent_path,state,state_path):
    """Retry only this intent; persist an ambiguous task identity before retry."""
    task_id=state.get('task_id')
    for attempt in range(4):
        restored=api(intent_path)
        if restored.get('task_id'):
            restored_id=identifier(restored['task_id'])
            require(task_id is None or task_id==restored_id,'restored_task_identity_changed')
            task_id=restored_id
        else:
            require(restored.get('start_url')==intent_path+'/start','preview_start_route_mismatch')
        try:
            started=api(intent_path+'/start',body={})
            started_id=identifier(started.get('id'))
            require(task_id is None or task_id==started_id,'start_replay_created_another_task')
            state['task_id']=started_id;save_state(state_path,state)
            return started
        except ApiError as exc:
            if exc.task_id:
                require(task_id is None or task_id==exc.task_id,'ambiguous_task_identity_changed')
                task_id=exc.task_id;state['task_id']=task_id;save_state(state_path,state)
            if exc.status not in (502,503,504) or attempt==3: raise
            if task_id:
                try:
                    observed=api('/scientific-research/'+identifier(task_id))
                    if observed.get('id')==task_id: return observed
                except ApiError as read_error:
                    if read_error.status not in (404,502,503,504): raise
            time.sleep(2)
    raise CanaryError('revision_start_not_recovered')


def run(args):
    # Exact owner and root are checked before any HTTP request or filesystem
    # output. There is no general user/report override in this release canary.
    guard(args.owner,args.report_id)
    require(re.fullmatch('[0-9a-f]{40}',args.source_commit) is not None,'full_source_commit_required')
    os.umask(0o077)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    state_path=args.output_dir/'resume-state.json'
    if state_path.exists():
        state=json.loads(state_path.read_text(encoding='utf-8'))
        require(all(state.get(key)==value for key,value in
            (('owner',OWNER),('report_id',REPORT_ID),('source_commit',args.source_commit))), 'resume_identity_mismatch')
    else:
        state=dict(owner=OWNER,report_id=REPORT_ID,source_commit=args.source_commit)
        save_state(state_path,state)
    receipt=dict(status='failed',scope='dedicated production canary; deployed API D2',
        source_commit=args.source_commit,owner=OWNER,root_report_id=REPORT_ID,
        direct_database_access=False,email_requested=False,cancel_requested=False,
        real_model_requested=False,actual_model_call_attestation='requires_independent_worker_provenance',
        independent_scientific_review='pending',private_output=str(args.output_dir))
    try:
        root='/scientific-reports/'+REPORT_ID
        source_task=api('/scientific-research/'+REPORT_ID)
        require(source_task.get('user_id')==OWNER and source_task.get('id')==REPORT_ID
                and source_task.get('engine')=='pi' and source_task.get('state')=='succeeded',
                'source_is_not_the_dedicated_completed_pi_canary')
        report=api(root)
        require(report.get('id')==REPORT_ID and isinstance(report.get('content'),str),'source_report_invalid')
        original=report['content'].encode('utf-8')
        status,download,_=request('/scientific-download/'+REPORT_ID)
        require(status==200 and download==original,'source_download_mismatch')
        before=api(root+'/writing-state')
        require(before.get('root_report_id')==REPORT_ID,'unexpected_canary_root')
        foreign='d2-negative-'+uuid.uuid4().hex
        check_isolation((root,root+'/writing-state',root+'/sections'),foreign)
        health=api('/scientific-health')
        capabilities=health.get('capabilities',{})
        require(health.get('worker_ready') is True and '1' in capabilities.get('revision_job_versions',[])
                and capabilities.get('revision_input_scope')=='recorded_evidence_only','revision_worker_not_ready')
        review=args.output_dir/'review-materials';review.mkdir(exist_ok=True)
        base_records=review_records(REPORT_ID,('papers','evidence','claims','references'),review,'base-')
        selected=select_leaf(api(root+'/sections'),original)
        key='real-api-d2-'+args.source_commit[:20]+'-'+REPORT_ID
        body=dict(base_sha256=sha(original),section_id=selected['section_id'],instruction=INSTRUCTION,timeout_seconds=600)
        if 'intent_id' not in state:
            preview=retry_write(root+'/revision-previews',body,key)
            require(preview.get('dispatch_available') is False and preview['intent'].get('status')=='prepared',
                    'preview_unexpected_dispatch')
            require(preview['parent'].get('report_sha256')==sha(original)
                    and preview['parent'].get('root_report_id')==REPORT_ID,'preview_parent_mismatch')
            require(preview.get('snapshot',{}).get('material_policy')=='recorded_evidence_only',
                    'preview_exceeded_recorded_evidence_boundary')
            state.update(intent_id=identifier(preview['intent']['intent_id']),
                         parent_version_id=identifier(preview['parent']['version_id']),
                         base_sha256=sha(original),section_id=selected['section_id'],prepare_key=key)
            save_state(state_path,state)
        require(state['base_sha256']==sha(original) and state['section_id']==selected['section_id'],
                'resume_source_or_selection_changed')
        intent_path='/scientific-revision-previews/'+identifier(state['intent_id'])
        current=api(root+'/writing-state')
        require(current.get('current_version_id') in (state['parent_version_id'],state.get('candidate_version_id')),
                'canary_current_head_is_not_this_probe_lineage')
        receipt['real_model_requested']=True
        task=recover_start(intent_path,state,state_path)
        task_id=identifier(task['id'])
        # A second explicit same-intent start is an idempotency check, never a
        # second independently prepared revision or a new model instruction.
        replayed=recover_start(intent_path,state,state_path)
        require(replayed.get('id')==task_id,'start_replay_identity_changed')
        receipt.update(task_id=task_id,intent_id=state['intent_id'],start_replay_same_task=True)
        deadline=time.monotonic()+720
        last=None
        while True:
            try: task=api('/scientific-research/'+task_id)
            except ApiError as exc:
                if exc.status not in (502,503,504) or time.monotonic()>=deadline: raise
                time.sleep(3);continue
            require(task.get('user_id')==OWNER and task.get('task_kind')=='revision'
                    and task.get('root_report_id')==REPORT_ID
                    and task.get('parent_version_id')==state['parent_version_id'],'revision_task_lineage_mismatch')
            stage=task.get('state')
            if stage!=last:
                print(json.dumps(dict(stage='dedicated_canary_revision',state=stage,task_id=task_id)),flush=True);last=stage
            if stage=='succeeded': break
            require(stage not in ('failed','cancelled','timed_out'),'revision_terminal_failure')
            require(time.monotonic()<deadline,'revision_wait_deadline_exceeded_task_not_cancelled')
            time.sleep(3)
        require(task.get('status')=='done' and task.get('report_id')==task_id,'candidate_report_not_published')
        require(isinstance(task.get('report_sha256'),str)
                and re.fullmatch('[0-9a-f]{64}',task['report_sha256']) is not None,'candidate_task_digest_missing')
        candidate_id=identifier(task.get('candidate_version_id'))
        if state.get('candidate_version_id'): require(state['candidate_version_id']==candidate_id,'resume_candidate_changed')
        state['candidate_version_id']=candidate_id;save_state(state_path,state)
        candidate_path='/scientific-report-versions/'+candidate_id
        comparison=api(candidate_path+'/comparison')
        parent,parent_raw=exact_version(state['parent_version_id'],sha(original))
        candidate,candidate_raw=exact_version(candidate_id,task.get('report_sha256'))
        require(parent_raw==original and candidate.get('parent_version_id')==parent['version_id']
                and candidate.get('root_report_id')==REPORT_ID,'candidate_lineage_or_original_changed')
        section=comparison['section'];adoption=comparison['adoption']
        start,end,new_end=section['start_byte'],section['end_byte'],section['candidate_end_byte']
        require(type(start) is int and type(end) is int and type(new_end) is int
                and 0<=start<=end<=len(original) and start<=new_end<=len(candidate_raw),
                'comparison_range_invalid')
        require(section.get('section_id')==state['section_id'] and start==selected['start_byte'] and end==selected['end_byte']
                and candidate_raw[:start]==original[:start] and candidate_raw[new_end:]==original[end:]
                and section['before'].encode('utf-8')==original[start:end]
                and section['after'].encode('utf-8')==candidate_raw[start:new_end], 'comparison_exact_range_mismatch')
        require(comparison['parent']['version_id']==parent['version_id']
                and comparison['candidate']['version_id']==candidate_id
                and adoption.get('base_sha256')==sha(original)
                and adoption.get('candidate_sha256')==sha(candidate_raw),'comparison_version_digest_mismatch')
        candidate_records=review_records(task_id,('papers','evidence','claims','references','revision_output'),review,'candidate-')
        require(all(candidate_records[name]==base_records[name] for name in ('papers','evidence','references')),
                'candidate_changed_fixed_evidence_records')
        for name,raw in {'original-report.md':original,'candidate-report.md':candidate_raw,
                'before-section.md':original[start:end],'candidate-section.md':candidate_raw[start:new_end]}.items():
            (review/name).write_bytes(raw)
        (review/'comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        check_isolation((candidate_path,candidate_path+'/comparison',candidate_path+'/download',
                         '/scientific-report-versions/'+parent['version_id']+'/download',
                         '/scientific-research/'+task_id),foreign)
        if 'adoption_body' not in state:
            require(adoption.get('can_adopt') is True
                    and adoption.get('expected_current_version_id')==parent['version_id'], 'candidate_cannot_be_adopted')
            state['adoption_body']={field:adoption[field] for field in FIELDS}
            state['adoption_key']='adopt-'+key
            save_state(state_path,state)
        # Reassert the exact identity immediately before the explicit canary
        # selection change. Persisted CAS body/key survive ambiguous responses.
        guard(args.owner,args.report_id)
        adopted=retry_write(candidate_path+'/adopt',state['adoption_body'],state['adoption_key'])
        replay=retry_write(candidate_path+'/adopt',state['adoption_body'],state['adoption_key'])
        require(adopted['adoption']['adoption_id']==replay['adoption']['adoption_id']
                and replay['adoption'].get('replayed') is True
                and replay.get('current_version_id')==candidate_id
                and replay.get('current_sha256')==sha(candidate_raw)
                and replay.get('selection_revision')==state['adoption_body']['expected_selection_revision']+1,
                'adoption_replay_or_selection_mismatch')
        final=api(root+'/writing-state')
        require(final.get('current_version_id')==candidate_id and final.get('current_sha256')==sha(candidate_raw)
                and final.get('selection_revision')==replay['selection_revision'],'writing_head_not_persisted')
        status,final_original,_=request('/scientific-download/'+REPORT_ID)
        require(status==200 and final_original==original and api(root).get('content')==report['content'],
                'published_original_changed_after_adoption')
        exact_version(parent['version_id'],sha(original));exact_version(candidate_id,sha(candidate_raw))
        receipt.update(status='passed',parent_version_id=parent['version_id'],candidate_version_id=candidate_id,
            original_sha256=sha(original),candidate_sha256=sha(candidate_raw),selected_title=selected['title'],
            candidate_section_sha256=sha(candidate_raw[start:new_end]),candidate_section_path=str(review/'candidate-section.md'),
            selection_revision=final['selection_revision'],adoption_id=replay['adoption']['adoption_id'],
            explicit_canary_adoption=True,adoption_replay_same_receipt=True,
            original_report_unchanged=True,exact_version_downloads=True,owner_isolation=True)
        state['completed']=True;save_state(state_path,state)
    except Exception as exc:
        # Public stdout contains stable codes only; reports, full API errors
        # and any private operational details stay in the protected directory.
        code=str(exc) if isinstance(exc,CanaryError) else 'unexpected_canary_error'
        receipt.update(error_code=code,error_type=type(exc).__name__,task_id=state.get('task_id'))
    finally:
        receipt['observed_at']=datetime.now(timezone.utc).isoformat()
        (args.output_dir/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(receipt,ensure_ascii=False),flush=True)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit',required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--owner',default=OWNER)
    parser.add_argument('--report-id',default=REPORT_ID)
    result=run(parser.parse_args())
    if result['status']!='passed': raise SystemExit(1)


if __name__=='__main__': main()
