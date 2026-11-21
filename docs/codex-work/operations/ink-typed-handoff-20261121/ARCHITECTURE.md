> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/ink-typed-handoff-20261121/ARCHITECTURE.md`；正文 SHA-256：`8cd839d17cbc0d731429b687e215c1db146c31e5a4982bb87cc02ff28eda5acf`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# Typed predecessor handoff assessment

The measured fifth original is valid, but its complete reference JSON alone is
16,049 bytes. Generated prose compaction cannot fit it into the strict v1/v2
16,000-character instruction contract. No source, state or user text should be
cut, rewritten or represented as having been delivered when omitted.

The scoped path is a separately tagged author context v3 for an unchanged
`video.hyperframes-film-clock.v1` film. Its additional typed
`predecessor_appearance` is complete inert data, outside scene.instruction.
Keep the old context v1/v2 exact fields and 16,000-character instruction rules.
V3 keeps that same instruction limit, a 512 KiB canonical reference bound and
a 2 MiB complete input bound including the frozen Skill catalog. Reject larger
originals before a paid admission; these are finite bounds, not a claim that
every permitted 2 MiB output module will fit its successor's 512 KiB reference.

The actual Skill task reader is unchanged and capped at 2 MiB, despite the
profile's existing 4 MiB input quota. Keep that global quota/TaskContract
revision identity unchanged; enforce the stricter v3 limit conditionally.
This avoids a catalog identity conflict and does not change legacy capacity.
Reference files/hashes/states/asset hashes must match the exact predecessor
metadata; first scene must use null, later scenes a complete nonrecursive
reference. Do not copy previous package/input histories into the reference.

The same profile v1 can use a fresh bundle/instruction revision v3, image,
binding, candidate, acceptance and permanent UID range. Retain historical
bundle v1/v2 prompt pins and reject v3 input under their package pins. This
uses the existing module-only catalog upgrade while retaining old accepted
bindings/pools/UIDs/callers. Required tools and output/module schemas remain
unchanged. Model cap stays 16. A new publication/compiler admission is unrelated.

Actual source paths establish the renderer boundary:

- `film_production_assembly.py:66` validates author packages in the workbench,
  then extracts result scene/transition modules and boundary records.
- It calls `compile_film_project` with film, module sources, recordings, assets
  and boundaries; the compiled manifest has no author input/context/package.
- `hyperframes_film_project.py:386` emits the same project v1 manifest and
  composable module v1 records, including legitimate transition modules.
- `hyperframes_film_snapshot.py:223` decodes the compiled archive and verifies
  the same snapshot/project/browser schemas and pinned release identities.
- `hyperframes_film_execution.py:82` consumes that compiled snapshot;
  `hyperframes_film_browser.py:57` creates realms from compiled module metadata.

Thus the unchanged `af8a17…` renderer does not parse author context v3. Keep
that renderer and its admission when compiled module/project/snapshot schemas,
lifecycle, assets and runtime/host hashes remain exact. A short actual af8
candidate execution still verifies that the new author output crosses this
boundary correctly; a unit test or a copied source hash cannot replace it.

Compatibility checks include v3 explicit-clock dispatch and is_silent_task,
legacy rejection of unknown fields/oversized instructions, exact reference
identity/files/state/asset checks, 512 KiB and final 2 MiB boundaries, catalog
task hash including the typed reference, historical package reconstruction,
and a genuine candidate whose actual v3 reference exceeds 16,000 characters.
Existing first-scene v2 fixtures cannot establish typed-reference coverage.

The downloader remains paused. Its old scene-only equality against
snapshot.module_sha256 must later become a scene subset check plus full
compiled-project/transition validation. It must also use the eventual actual
run state, never the failed second attempt as a substitute completed film.
