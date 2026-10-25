#!/usr/bin/env python3
"""Check a deployed API using existing reports, with canary-only preparation.

Run inside the scientific API container with its installed standard-library SQL
HTTP client. SELECT statements only inspect existing data; all allowed canary
writes go through revision-previews. This never submits/cancels research, sends
mail, edits schema, or directly changes a database row. Operator HTTP checks do
not certify a real user's Casdoor login or browser interaction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
import uuid


BASE_URL = 'http://127.0.0.1:8000'
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
TABLES = ('scientific_report_versions', 'scientific_report_snapshots',
          'scientific_report_revision_intents')
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ProbeError(Exception):
    pass


def require(value, code):
    if not value:
        raise ProbeError(code)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def identifier(value):
    require(isinstance(value, str), 'stored_report_id_invalid')
    require(str(uuid.UUID(value)) == value, 'stored_report_id_invalid')
    return value


def canary_owner(value):
    # Naming is intentionally conservative. An ordinary user's real identity
    # is never borrowed to create a revision-intent acceptance record.
    return any(marker in value.casefold() for marker in ('canary', 'acceptance'))


def request(path, owner=None, *, body=None, key=None):
    require(path.startswith('/') and not path.startswith('//'), 'invalid_probe_path')
    headers = {'Content-Type': 'application/json'}
    if owner is not None:
        require(isinstance(owner, str) and 0 < len(owner) <= 200
                and not any(ord(char) < 32 or ord(char) == 127 for char in owner),
                'stored_owner_invalid')
        headers['X-Forwarded-User'] = owner
    if key is not None:
        headers['Idempotency-Key'] = key
    req = urllib.request.Request(BASE_URL + path, headers=headers,
        data=None if body is None else json.dumps(body, ensure_ascii=False).encode('utf-8'),
        method='GET' if body is None else 'POST')
    try:
        response = OPENER.open(req, timeout=30)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        require(len(raw) <= MAX_RESPONSE_BYTES, 'probe_response_too_large')
        return response.code, raw, {key.casefold(): value for key, value in response.headers.items()}


def json_request(path, owner=None, *, body=None, key=None, expected=200):
    status, raw, _ = request(path, owner, body=body, key=key)
    require(status == expected, 'unexpected_api_status_' + str(status))
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ProbeError('invalid_api_json') from None
    require(isinstance(value, dict), 'unexpected_api_json_shape')
    return value


def counts(database, owner, report_id):
    """Counts only this owner/root; concurrent unrelated reports are irrelevant."""
    own, root = sql_literal(owner), sql_literal(report_id)
    queries = {
        'versions': 'SELECT COUNT(*) AS n FROM scientific_report_versions WHERE owner=' + own + ' AND root_report_id=' + root,
        'snapshots': 'SELECT COUNT(*) AS n FROM scientific_report_snapshots s WHERE s.owner=' + own
                     + ' AND EXISTS (SELECT 1 FROM scientific_report_versions v WHERE v.owner=s.owner AND v.version_id=s.version_id AND v.root_report_id=' + root + ')',
        'intents': 'SELECT COUNT(*) AS n FROM scientific_report_revision_intents WHERE owner=' + own + ' AND root_report_id=' + root,
        'research_index': 'SELECT COUNT(*) AS n FROM scientific_pi_index WHERE user_id=' + own,
    }
    return {name: database._query(query)[0]['n'] for name, query in queries.items()}


def check_sections(value, raw):
    require(value.get('report_sha256') == sha(raw), 'section_report_digest_mismatch')
    sections = value.get('sections')
    require(isinstance(sections, list) and bool(sections), 'sections_missing')
    seen = set()
    for item in sections:
        require(isinstance(item, dict), 'section_shape_invalid')
        start, end = item.get('start_byte'), item.get('end_byte')
        require(type(start) is int and type(end) is int and 0 <= start <= end <= len(raw),
                'section_range_invalid')
        require(item.get('sha256') == sha(raw[start:end]), 'section_range_digest_mismatch')
        require(item.get('section_id') not in seen, 'duplicate_section_id')
        seen.add(item.get('section_id'))
    editable = [item for item in sections if item.get('editable') is True]
    require(bool(editable), 'editable_section_missing')
    return editable[0]


def task_fingerprint(value):
    return {key: value.get(key) for key in
            ('id', 'state', 'status', 'attempt', 'revision', 'report_id', 'report_sha256', 'result_digest')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{40}', args.source_commit) is not None, 'full_source_commit_required')
    from tools import sqlite_client as database

    result = {'status': 'passed', 'source_commit': args.source_commit,
              'scope': 'deployed internal operator HTTP; existing reports; canary-only preparation',
              'checks': [], 'skipped': [], 'real_model_requested': False,
              'research_submitted': False, 'research_cancelled': False,
              'email_requested': False, 'direct_database_writes': False,
              'real_user_login_verified': False}
    health = json_request('/scientific-health')
    require(health.get('backend') == 'pi' and health.get('status') == 'ok'
            and health.get('worker_ready') is True, 'worker_not_ready')
    result['checks'].append('api_and_existing_worker_ready')
    for table in TABLES:
        require(database._query('SELECT COUNT(*) AS n FROM sqlite_master WHERE type=\'table\' AND name=' + sql_literal(table))[0]['n'] == 1,
                'writing_table_missing')
    result['checks'].append('api_initialized_private_writing_tables')

    legacy = database._query('SELECT r.id,r.task_id,r.content FROM scientific_reports r '
        'WHERE NOT EXISTS (SELECT 1 FROM scientific_pi_index i WHERE i.id=r.id OR i.id=r.task_id) '
        'ORDER BY r.created_at DESC,r.id DESC LIMIT 1')
    if legacy:
        old = legacy[0]
        old_id, old_task = identifier(old['id']), identifier(old['task_id'])
        original = old['content'].encode('utf-8')
        detail = json_request('/scientific-reports/' + old_id)
        status, raw, _ = request('/scientific-download/' + old_task)
        require(detail.get('content') == old['content'] and status == 200 and raw == original,
                'legacy_report_or_download_changed')
        result['legacy_report_id'], result['legacy_report_sha256'] = old_id, sha(original)
        result['checks'].append('legacy_shared_report_and_exact_download_preserved')
    else:
        result['skipped'].append('no_existing_legacy_report')

    recent = database._query('SELECT r.id,r.task_id,r.content,i.user_id FROM scientific_reports r '
        'JOIN scientific_pi_index i ON i.id=r.id AND i.id=r.task_id '
        'ORDER BY r.created_at DESC,r.id DESC LIMIT 10')
    require(bool(recent), 'no_existing_pi_report')
    ordered = sorted(recent, key=lambda row: not canary_owner(row['user_id']))
    selected, trace, task_before = None, None, None
    for candidate in ordered:
        report_id = identifier(candidate['id'])
        owner = candidate['user_id']
        task = json_request('/scientific-research/' + report_id, owner)
        require(task.get('state') == 'succeeded' and task.get('status') == 'done', 'stored_report_task_not_completed')
        available = json_request('/scientific-research/' + report_id + '/citations', owner)
        if available.get('availability') == 'available':
            selected, trace, task_before = candidate, available, task
            break
    if selected is None:
        selected = ordered[0]
        task_before = json_request('/scientific-research/' + identifier(selected['id']), selected['user_id'])
        result['status'] = 'partial'
        result['skipped'].append('no_available_evidence_among_latest_ten_pi_reports')

    report_id, owner = identifier(selected['id']), selected['user_id']
    raw = selected['content'].encode('utf-8')
    other = 'writing-release-negative-' + uuid.uuid4().hex
    require(other != owner, 'negative_identity_collision')
    result['report_id'], result['report_sha256'] = report_id, sha(raw)
    report_path = '/scientific-reports/' + report_id
    index_path = '/scientific-research/' + report_id
    detail = json_request(report_path, owner)
    status, downloaded, _ = request('/scientific-download/' + report_id, owner)
    require(detail.get('content') == selected['content'] and status == 200 and downloaded == raw,
            'pi_original_download_mismatch')
    result['checks'].append('pi_report_and_exact_original_download')
    if trace is not None:
        require(trace.get('report_sha256') == sha(raw) and isinstance(trace.get('citations'), list),
                'citation_report_digest_mismatch')
        result['citation_count'] = len(trace['citations'])
        result['checks'].append('existing_pi_evidence_trace_matches_published_report')
    for path in (index_path + '/citations', report_path + '/sections', report_path + '/versions'):
        require(request(path)[0] == 401, 'missing_identity_not_rejected')
        require(request(path, other)[0] == 404, 'foreign_identity_not_rejected')
    result['checks'].append('citation_section_history_identity_isolation')

    before = counts(database, owner, report_id)
    sections = json_request(report_path + '/sections', owner)
    section = check_sections(sections, raw)
    history = json_request(report_path + '/versions', owner)
    require(history.get('source_sha256') == sha(raw) and isinstance(history.get('items'), list),
            'history_source_digest_mismatch')
    after_reads = counts(database, owner, report_id)
    require(all(before[kind] == after_reads[kind] for kind in ('versions', 'snapshots', 'intents')),
            'read_only_history_changed_private_records')
    result['checks'].extend(('exact_utf8_sections', 'section_history_get_has_no_persistent_side_effect'))
    result['counts_before'] = before

    if trace is None:
        result['skipped'].append('preparation_requires_available_evidence')
    elif not canary_owner(owner):
        result['status'] = 'partial'
        result['skipped'].append('no_available_canary_report_preparation_not_attempted_on_real_user')
    else:
        body = {'base_sha256': sha(raw), 'section_id': section['section_id'],
                'instruction': 'Release acceptance only: prepare existing evidence input; do not dispatch a model or change the report.',
                'timeout_seconds': 600}
        key = 'writing-release-' + args.source_commit[:12] + '-' + report_id
        preview_path = report_path + '/revision-previews'
        require(request(preview_path, body=body, key=key)[0] == 401, 'anonymous_prepare_not_rejected')
        require(request(preview_path, other, body=body, key=key)[0] == 404, 'foreign_prepare_not_rejected')
        preview = json_request(preview_path, owner, body=body, key=key)
        require(preview.get('dispatch_available') is False, 'preview_unexpected_dispatch')
        intent, parent, snapshot = preview['intent'], preview['parent'], preview['snapshot']
        require(intent.get('status') == 'prepared' and intent.get('base_sha256') == sha(raw), 'intent_input_invalid')
        require(parent.get('report_sha256') == sha(raw) and snapshot.get('report_sha256') == sha(raw),
                'fixed_input_digest_mismatch')
        require(snapshot.get('material_policy') == 'recorded_evidence_only'
                and re.fullmatch('[0-9a-f]{64}', snapshot.get('snapshot_sha256', '')) is not None,
                'snapshot_scope_or_digest_invalid')
        require(not set(snapshot).intersection(('report', 'items', 'artifacts', 'payload')), 'snapshot_payload_exposed')
        prepared_section = preview.get('section', {})
        start, end = section['start_byte'], section['end_byte']
        require(prepared_section.get('text', '').encode('utf-8') == raw[start:end]
                and prepared_section.get('sha256') == section['sha256'], 'prepared_range_changed')
        replay = json_request(preview_path, owner, body=body, key=key)
        require(replay['intent']['intent_id'] == intent['intent_id']
                and replay['parent']['version_id'] == parent['version_id']
                and replay['snapshot']['snapshot_id'] == snapshot['snapshot_id'], 'idempotent_replay_changed')
        changed = dict(body, instruction=body['instruction'] + ' Different fingerprint.')
        require(request(preview_path, owner, body=changed, key=key)[0] == 409, 'changed_key_fingerprint_not_rejected')
        version_path = '/scientific-report-versions/' + identifier(parent['version_id'])
        snapshot_path = '/scientific-report-snapshots/' + identifier(snapshot['snapshot_id'])
        intent_path = '/scientific-revision-previews/' + identifier(intent['intent_id'])
        for path in (version_path, version_path + '/sections', version_path + '/download', snapshot_path, intent_path):
            require(request(path)[0] == 401, 'anonymous_private_read_not_rejected')
            require(request(path, other)[0] == 404, 'foreign_private_read_not_rejected')
        version = json_request(version_path, owner)
        require(version.get('content') == selected['content'] and version.get('report_sha256') == sha(raw),
                'private_version_original_changed')
        check_sections(json_request(version_path + '/sections', owner), raw)
        status, private_raw, headers = request(version_path + '/download', owner)
        require(status == 200 and private_raw == raw and headers.get('x-content-type-options') == 'nosniff',
                'private_version_download_mismatch')
        public_snapshot = json_request(snapshot_path, owner)
        require(public_snapshot.get('snapshot_id') == snapshot['snapshot_id']
                and public_snapshot.get('material_policy') == 'recorded_evidence_only'
                and not set(public_snapshot).intersection(('report', 'items', 'artifacts', 'payload')),
                'private_snapshot_metadata_invalid')
        restored = json_request(intent_path, owner)
        require(restored.get('dispatch_available') is False and restored['intent']['intent_id'] == intent['intent_id'],
                'prepared_intent_restore_invalid')
        result['intent_id'] = intent['intent_id']
        result['checks'].extend(('canary_preparation_fixes_exact_input_without_dispatch',
            'same_key_replay_and_different_fingerprint_conflict',
            'private_version_original_download_and_sections',
            'private_snapshot_metadata_and_intent_owner_isolation'))

    after = counts(database, owner, report_id)
    if 'intent_id' in result:
        require(after['research_index'] == before['research_index'], 'canary_research_index_changed')
    for kind in ('versions', 'snapshots', 'intents'):
        require(before[kind] <= after[kind] <= before[kind] + (1 if 'intent_id' in result else 0),
                'unexpected_writing_record_count')
    original = json_request(report_path, owner)
    require(original.get('content') == selected['content'], 'published_original_changed_after_probe')
    task_after = json_request(index_path, owner)
    require(task_fingerprint(task_before) == task_fingerprint(task_after), 'existing_worker_task_changed_after_probe')
    result['counts_after'] = after
    result['checks'].append('original_report_and_existing_worker_task_unchanged')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        if isinstance(exc, SystemExit):
            raise
        print(json.dumps({'status': 'failed', 'error_code': str(exc) if isinstance(exc, ProbeError)
                          else 'unexpected_probe_response', 'error_type': type(exc).__name__}))
        sys.exit(1)
