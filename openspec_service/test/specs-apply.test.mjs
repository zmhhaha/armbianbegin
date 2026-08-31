import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const require=createRequire(import.meta.url);
const packageEntry=require.resolve('@fission-ai/openspec');
const {findSpecUpdates,buildUpdatedSpec,writeUpdatedSpec}=await import(pathToFileURL(path.join(path.dirname(packageEntry),'core','specs-apply.js')).href);

test('official OpenSpec delta merge updates a nested main spec',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'openspec-merge-test-'));
  const change=path.join(root,'openspec','changes','add-login');
  const specs=path.join(root,'openspec','specs');
  await fs.mkdir(path.join(change,'specs','identity'),{recursive:true});
  await fs.mkdir(path.join(specs,'identity'),{recursive:true});
  await fs.writeFile(path.join(specs,'identity','spec.md'),'# Identity\n\n## Purpose\nUsers authenticate.\n\n## Requirements\n\n### Requirement: Existing login\nThe system SHALL accept a login.\n\n#### Scenario: Login works\n- **WHEN** credentials are valid\n- **THEN** access is granted\n');
  await fs.writeFile(path.join(change,'specs','identity','spec.md'),'## MODIFIED Requirements\n\n### Requirement: Existing login\nThe system SHALL accept a Casdoor login.\n\n#### Scenario: Login works\n- **WHEN** credentials are valid\n- **THEN** access is granted\n\n#### Scenario: Casdoor login works\n- **WHEN** Casdoor credentials are valid\n- **THEN** access is granted\n');
  const updates=await findSpecUpdates(change,specs);
  assert.deepEqual(updates.map(update=>update.id),['identity']);
  const built=await buildUpdatedSpec(updates[0],'add-login',{silent:true});
  assert.equal(built.counts.modified,1);
  await writeUpdatedSpec(updates[0],built.rebuilt,built.counts,{silent:true});
  const content=await fs.readFile(path.join(specs,'identity','spec.md'),'utf8');
  assert.match(content,/Casdoor login/);
  assert.doesNotMatch(content,/Existing login\nThe system SHALL accept a login/);
});
