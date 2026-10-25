"""Run one actual pinned Pi revision against saved real abstract evidence.

Execute in an isolated candidate-image Pod with an empty /data volume and the
existing reviewed model configuration. No production queue/database or mail is
used. Source materials are historical records; no new retrieval is performed.
"""
from __future__ import annotations

import argparse
import base64
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

sys.path.insert(0, '/app')

from scientific_agent.pi_contracts import parse_timestamp, utc_now
from scientific_agent.pi_revision_contracts import RevisionJob, revision_input_digest, revision_material_digest
from scientific_agent.pi_revision_validation import compose_revision, validate_revision_input
from scientific_agent.pi_runtime_config import runtime_from_env
from scientific_agent.pi_sections import index_sections, select_section
from pi_worker.artifacts import artifact_bytes
from pi_worker.scheduler import Scheduler
from pi_worker.store import QueueStore


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def redacted_model_error(raw, model_env):
    """Bounded private diagnostic text; never included in the log export."""
    text = raw if isinstance(raw,str) else ''
    values = sorted({str(value) for value in model_env.values() if value},key=len,reverse=True)
    for value in values:
        text = text.replace(value,'[REDACTED]')
    text = re.sub(r'(?i)\bBearer\s+[^\s\"\'<>;,]+','Bearer [REDACTED]',text)
    text = re.sub(r'(?i)([\"\']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|authorization)[\"\']?\s*[:=]\s*)'
                  r'(?:\"[^\"]*\"|\'[^\']*\'|[^\s,;}&]+)',r'\1[REDACTED]',text)
    text = re.sub(r'\b(?:sk-|sk_|ghp_|github_pat_)[A-Za-z0-9_-]{8,}','[REDACTED]',text)
    text = re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b','[REDACTED]',text)
    text = re.sub(r'(https?://)[^/@\s]+:[^/@\s]+@',r'\1[REDACTED]@',text)
    text = ''.join(char if char in '\n\t' or ord(char)>=32 else ' ' for char in text)
    return text[:2000]


def model_error_diagnostic(message, classification, model_env):
    """Public flags/hash only; private excerpt excludes full event/prompt/tools."""
    raw = message.get('errorMessage') if isinstance(message,dict) else None
    text = raw if isinstance(raw,str) else ''
    lower = text.lower()
    patterns = {
        'context_limit':r'context[_ -]?(?:length|window)|maximum context|too many (?:input )?tokens|prompt (?:is )?too long',
        'token_limit':r'max[_ -]?(?:output[_ -]?)?tokens|token limit|maximum.*tokens',
        'tool_schema':r'tool[_ -]?(?:call|schema|choice)|function[_ -]?(?:call|schema)|(?:invalid|unsupported).*tool|additionalproperties|json schema',
        'rate_limit':r'rate[_ -]?limit|too many requests|quota|capacity',
        'timeout':r'time[_ -]?out|timed out|deadline',
        'authentication':r'unauthorized|forbidden|authentication|invalid api[_ -]?key|api[_ -]?key.*(?:missing|not found|invalid)|no api[_ -]?key',
        'model_unavailable':r'model.*(?:not found|does not exist|not available|unsupported)|unknown model',
        'invalid_request':r'invalid[_ -]?(?:request|parameter|argument)|unsupported parameter|bad request|validation error',
        'connection':r'connection|econn|enotfound|dns|network|fetch failed|socket',
        'server_error':r'internal server|bad gateway|service unavailable|upstream error',
    }
    status = re.match(r'\A\s*(?:HTTP(?:/[0-9.]+)?\s+)?([45][0-9]{2})(?:\s|:)',text,re.I)
    code = getattr(classification,'code',None)
    if not isinstance(code,str) or re.fullmatch(r'[a-z0-9_]{1,80}',code) is None:
        code = 'unrecognized_error_class'
    diagnostic = dict(type='model_error_diagnostic',schema_version='1',
        runtime_error_code=code,retryable=getattr(classification,'retryable',False) is True,
        http_status=int(status.group(1)) if status else None,
        categories=[name for name,pattern in patterns.items() if re.search(pattern,lower)],
        error_message_present=isinstance(raw,str),error_message_bytes=len(text.encode('utf-8',errors='replace')),
        error_message_sha256=sha(text.encode('utf-8',errors='replace')),
        error_text_in_stdout=False)
    diagnostic['schema_field_markers']=[field for field in (
        'max_tokens','max_completion_tokens','temperature','top_p','parallel_tool_calls','tool_choice',
        'tools','parameters','additionalproperties','strict','reasoning_effort','response_format','input_schema')
        if re.search(r'(?<![a-z0-9_])'+field+r'(?![a-z0-9_])',lower)]
    diagnostic['provider_code_markers']=[code for code in (
        'context_length_exceeded','invalid_request_error','unsupported_parameter','unknown_parameter',
        'unsupported_value','invalid_schema','model_not_found','insufficient_quota','rate_limit_exceeded')
        if re.search(r'(?<![a-z0-9_])'+code+r'(?![a-z0-9_])',lower)]
    private = dict(diagnostic,error_message_redacted=redacted_model_error(text,model_env),
                   error_message_redacted_max_characters=2000)
    return diagnostic,private


def observe_model_errors(runtime, output_dir):
    """Instrument this isolated probe instance without changing error policy."""
    original = runtime._model_request_error
    diagnostics = []
    def observed(message):
        classification = original(message)
        diagnostic,private = model_error_diagnostic(message,classification,runtime.settings.model_env)
        diagnostics.append(diagnostic)
        try:
            target = output_dir / ('model-error-%03d.private.json' % len(diagnostics))
            target.write_text(json.dumps(private,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
            target.chmod(0o600)
        except OSError:
            diagnostic['private_record_saved'] = False
        else:
            diagnostic['private_record_saved'] = True
        print(json.dumps(diagnostic,ensure_ascii=True),flush=True)
        return classification
    runtime._model_request_error = observed
    return original,diagnostics


def queue_failure_diagnostic(snapshot, observed_errors):
    """Queue survives workspace cleanup; expose controlled fields and hashes."""
    states={'queued','running','validating','publishing','succeeded','failed','cancelled','timed_out'}
    code=snapshot.get('error_code')
    if not isinstance(code,str) or re.fullmatch(r'[a-z0-9_]{1,80}',code) is None:
        code=None
    error=snapshot.get('error')
    text=error if isinstance(error,str) else ''
    return dict(type='queue_failure_diagnostic',schema_version='1',
        state=snapshot.get('state') if snapshot.get('state') in states else 'unknown',error_code=code,
        attempt=snapshot.get('attempt') if type(snapshot.get('attempt')) is int else None,
        revision=snapshot.get('revision') if type(snapshot.get('revision')) is int else None,
        error_message_bytes=len(text.encode('utf-8',errors='replace')),
        error_message_sha256=sha(text.encode('utf-8',errors='replace')),
        observed_model_error_count=len(observed_errors),
        diagnostic_source='isolated queue snapshot; independent of deleted attempt workspace',
        raw_error_in_stdout=False)


def review_artifacts(task_id, files):
    """Export only explicit public review bytes, never runtime files or env."""
    if sum(len(raw) for raw in files.values()) > 4 * 1024 * 1024:
        raise ValueError('Public review artifacts exceed the bounded log export')
    return dict(type='review_artifacts',schema_version='1',task_id=task_id,
        artifacts=[dict(name=name,size_bytes=len(raw),sha256=sha(raw),encoding='base64',
                        data=base64.b64encode(raw).decode('ascii'))
                   for name,raw in sorted(files.items())])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--materials-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.output_dir.mkdir(parents=True,exist_ok=False)
    # A dropped task UID must traverse this ancestor of the runtime workspace.
    # Controller receipts and source copies remain 0600; directory listing and
    # the runtime control directory remain inaccessible to task processes.
    args.output_dir.chmod(0o711)
    report_raw = (args.materials_dir/'report.md').read_bytes()
    report = report_raw.decode('utf-8')
    records = {name:(args.materials_dir/(name+('.json' if name=='references' else '.jsonl'))).read_bytes()
               for name in ('papers','evidence','claims','references')}
    items = [dict(artifact_id=name,size=len(raw),sha256=sha(raw),media_type=(
                'text/markdown' if name=='report' else 'application/json' if name=='references' else 'application/x-ndjson'))
             for name,raw in dict(records,report=report_raw).items()]
    sections = index_sections(report)
    section = next(row for row in sections['sections'] if row['title'].startswith('背面供电：'))
    validate_revision_input(report,items,records,section['section_id'],sections['report_sha256'])
    material = dict(report=report,items=items,
                    artifacts={name:base64.b64encode(raw).decode('ascii') for name,raw in records.items()})
    created = utc_now()
    job = dict(schema_version='1',task_kind='revision',task_id=str(uuid.uuid4()),
        topic='真实 Pi 章节修订验收：芯片制造综述的背面供电章节',
        user_id='scientific-revision-isolated-acceptance',engine='pi',mode='review',
        timeout_seconds=600,created_at=created,
        execution_deadline_at=(parse_timestamp(created)+timedelta(seconds=600)).isoformat(),
        runtime_revision=os.environ['SCIENTIFIC_PI_RUNTIME_REVISION'],
        skill_bundle_revision=os.environ['SCIENTIFIC_PI_SKILL_BUNDLE_REVISION'],
        intent_id=str(uuid.uuid4()),parent_version_id=str(uuid.uuid4()),
        root_report_id='1e5cec61-23d5-5a68-a658-82a9b168de2d',
        base_sha256=sections['report_sha256'],section_id=section['section_id'],section_sha256=section['sha256'],
        instruction=('将本节改为两段连贯综述：第一段比较配电设计收益与诊断约束；第二段明确摘要证据的比较局限。'
                     '保持原三级标题和现有引用编号[4]与[5]，不新增性能数字，不声称读取全文或完成新检索。'),
        input_sha256=revision_material_digest(material),material_policy='recorded_evidence_only')
    job['input_digest'] = revision_input_digest(job)
    checked = RevisionJob.from_dict(job)
    runtime_root = args.output_dir/'runtime'
    runtime = runtime_from_env(runtime_root)
    health = runtime.health()
    if health.get('ready') is not True:
        (args.output_dir/'runtime-health.json').write_text(json.dumps(health,ensure_ascii=False,indent=2))
        raise RuntimeError('Candidate runtime is not ready; inspect isolated private health evidence')
    store = QueueStore(runtime_root/'control'/'queue.sqlite')
    store.submit_revision(checked,material)
    scheduler = Scheduler(store,runtime,runtime_root,max_attempts=1)
    print(json.dumps(dict(stage='actual_pi_revision_started',task_id=job['task_id'],
        material_sha256=job['input_sha256'],base_sha256=job['base_sha256'],section_title=section['title'])),flush=True)
    original_error_classifier,model_errors = observe_model_errors(runtime,args.output_dir)
    try:
        scheduler.run_claim(store.claim())
    finally:
        runtime._model_request_error = original_error_classifier
    snapshot = store.get(job['task_id'])
    (args.output_dir/'task.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2))
    if snapshot['state']!='publishing':
        queue_diagnostic=queue_failure_diagnostic(snapshot,model_errors)
        (args.output_dir/'queue-failure-diagnostic.json').write_text(
            json.dumps(queue_diagnostic,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(queue_diagnostic,ensure_ascii=True),flush=True)
        print(json.dumps(dict(status='failed',task_id=job['task_id'],state=snapshot['state'],
                              error_code=queue_diagnostic['error_code'],
                              observed_model_error_count=len(model_errors))),flush=True)
        return 1
    result = store.result(job['task_id'])
    output_raw = artifact_bytes(store,job['task_id'],'revision_output')[0]
    output = json.loads(output_raw)
    recomposed = compose_revision(report,items,records,section['section_id'],job['base_sha256'],output)
    candidate = result['report_markdown'].encode('utf-8')
    assert recomposed['report_markdown'].encode('utf-8')==candidate
    target = select_section(report,section['section_id'],job['base_sha256'])
    suffix = report_raw[target['end_byte']:]
    assert candidate[:target['start_byte']]==report_raw[:target['start_byte']]
    assert not suffix or candidate[-len(suffix):]==suffix
    for name in ('papers','evidence','references'):
        assert artifact_bytes(store,job['task_id'],name)[0]==records[name]
    assert sha(candidate)==result['report_sha256']
    assert result['provenance']['retrieval_performed'] is False
    assert result['provenance']['full_text_restored'] is False
    (args.output_dir/'base-report.md').write_bytes(report_raw)
    (args.output_dir/'candidate-report.md').write_bytes(candidate)
    (args.output_dir/'revision-output.json').write_bytes(output_raw)
    (args.output_dir/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    public_files={'base-report.md':report_raw,'candidate-report.md':candidate,
                  'revision-output.json':output_raw,
                  'validation.json':artifact_bytes(store,job['task_id'],'validation')[0]}
    for name,raw in records.items():
        extension='.json' if name=='references' else '.jsonl'
        public_files['base-'+name+extension]=raw
        public_files['candidate-'+name+extension]=artifact_bytes(store,job['task_id'],name)[0]
    provenance=result['provenance']
    public_keys=('model','pi_version','node_version','image_digest','skill_bundle_revision',
                 'runtime_revision','material_policy','retrieval_performed','full_text_restored','revision')
    public_files['public-provenance.json']=json.dumps(
        {key:provenance[key] for key in public_keys if key in provenance},
        ensure_ascii=False,sort_keys=True).encode('utf-8')
    exported=review_artifacts(job['task_id'],public_files)
    for name,raw in public_files.items():
        (args.output_dir/name).write_bytes(raw)
    store.ack(job['task_id'],1,result['result_digest'],job['task_id'])
    summary = dict(status='passed',observed_at=utc_now(),task_id=job['task_id'],
        source_root_report_id=job['root_report_id'],source_material='saved real report and public abstract records from 2026-10-23',
        actual_pi_called=True,actual_model_called=True,fixture_runtime=False,
        selected_title=section['title'],base_sha256=job['base_sha256'],
        candidate_sha256=sha(candidate),result_digest=result['result_digest'],
        pi_version=result['provenance'].get('pi_version'),node_version=result['provenance'].get('node_version'),
        image_digest=result['provenance'].get('image_digest'),model=result['provenance'].get('model'),
        unchanged_prefix_bytes=target['start_byte'],unchanged_suffix_bytes=len(suffix),
        fixed_record_bytes_unchanged=['papers','evidence','references'],
        new_claim_count=len(output['claims']),final_state=store.get(job['task_id'])['state'],
        new_retrieval=False,full_text_restored=False,production_database_accessed=False,email_sent=False,
        scientific_review='pending independent reading of candidate claims against supplied evidence')
    (args.output_dir/'receipt.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    # Completed Pods cannot be exec'ed. The launcher reads this bounded record
    # from private logs and validates every byte before deleting this Pod.
    print(json.dumps(exported,ensure_ascii=False,separators=(',',':')),flush=True)
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
