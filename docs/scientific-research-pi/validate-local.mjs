import { readFile, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const changeDir = resolve(root, 'docs/scientific-research-pi');
const validatorUrl = pathToFileURL(resolve(root, 'openspec_service/node_modules/.pnpm/@fission-ai+openspec@1.10.0/node_modules/@fission-ai/openspec/dist/core/validation/validator.js'));
const { Validator } = await import(validatorUrl.href);
const validator = new Validator(true);
const proposal = await validator.validateChange(resolve(changeDir, 'proposal.md'));
const deltas = await validator.validateChangeDeltaSpecs(changeDir);
const paths = ['proposal.md', 'design.md', 'tasks.md', 'specs/scientific-execution/spec.md'];
const files = Object.fromEntries(await Promise.all(paths.map(async path => [path, await readFile(resolve(changeDir, path), 'utf8')])));
const contracts = await readFile(resolve(changeDir, 'contracts.md'), 'utf8');
files['design.md'] = files['design.md'].replaceAll('(contracts.md)', '(#protocol-v1)') + '\n\n## Protocol v1\n\n' + contracts;
files['tasks.md'] = files['tasks.md'].replaceAll('(contracts.md)', '(design.md#protocol-v1)');
const implementation = await readFile(resolve(changeDir, 'implementation.md'), 'utf8');
files['design.md'] += '\n\n## Local implementation\n\n' + implementation;
for (const key of ['proposal.md', 'tasks.md']) {
  files[key] = files[key].replaceAll('(implementation.md)', '(design.md#local-implementation)');
}
const remainingCount = (files['tasks.md'].match(/^- \[ \]/gm) || []).length;
const checkedCount = (files['tasks.md'].match(/^- \[[xX]\]/gm) || []).length;
const taskCount = remainingCount + checkedCount;
const result = { scope: 'local-only; see remote-submission-receipt.json for service validation', changeId: 'add-scientific-pi-worker', proposal, deltas, taskCount, checkedCount, remainingCount };
console.log(JSON.stringify(result, null, 2));
await writeFile(resolve(changeDir, 'local-validation.json'), JSON.stringify(result, null, 2) + '\n');
await writeFile(resolve(changeDir, 'submission-payload.json'), JSON.stringify({ projectId: 'ec663f5a-53d3-4a0e-9037-933eb788d183', changeId: 'add-scientific-pi-worker', files }, null, 2) + '\n');
if (!proposal.valid || !deltas.valid) process.exitCode = 1;
