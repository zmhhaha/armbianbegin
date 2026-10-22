import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const directory = dirname(fileURLToPath(import.meta.url));
const sha256 = value => createHash('sha256').update(value, 'utf8').digest('hex');
function canonical(value) {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isSafeInteger(value)) return String(value);
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') {
    const codePoints = (a, b) => {
      const left = Array.from(a, ch => ch.codePointAt(0));
      const right = Array.from(b, ch => ch.codePointAt(0));
      for (let i = 0; i < Math.min(left.length, right.length); i++) {
        if (left[i] !== right[i]) return left[i] - right[i];
      }
      return left.length - right.length;
    };
    return '{' + Object.keys(value).sort(codePoints).map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  }
  throw new TypeError('Unsupported canonical value');
}
const report = 'abc';
const reportHash = sha256(report);
const input = { topic: '研究题目', user_id: 'trusted-opaque-user', engine: 'pi', mode: 'review', timeout_seconds: 1800 };
const envelope = {
  schema_version: '1', task_id: '00000000-0000-4000-8000-000000000001', attempt: 1,
  report_sha256: reportHash,
  artifacts: [{ artifact_id: 'report', media_type: 'text/markdown', size: 3, sha256: reportHash }],
  provenance: { runtime_revision: 'pinned', skill_bundle_revision: 'pinned', model: 'fixture-model', image_digest: 'sha256:' + '0'.repeat(64) },
};
const output = {
  scope: 'Protocol hash fixture only; not real scientific or runtime acceptance',
  canonicalization: 'contracts.md CanonicalJSON v1; safe integers; Unicode code point key sorting',
  input: { value: input, canonical_utf8: canonical(input), input_digest: sha256(canonical(input)) },
  report: { markdown: report, utf8_hex: '616263', report_sha256: reportHash },
  result: { envelope, canonical_utf8: canonical(envelope), result_digest: sha256(canonical(envelope)) },
};
const target = resolve(directory, 'contract-vectors.json');
if (process.argv.includes('--check')) {
  const existing = JSON.parse(await readFile(target, 'utf8'));
  if (JSON.stringify(existing) !== JSON.stringify(output)) throw new Error('Protocol hash vector mismatch');
  console.log('Protocol hash vectors match: input_digest, report_sha256, result_digest');
} else {
  await writeFile(target, JSON.stringify(output, null, 2) + '\n');
  console.log(JSON.stringify({ input_digest: output.input.input_digest, report_sha256: reportHash, result_digest: output.result.result_digest }, null, 2));
}
