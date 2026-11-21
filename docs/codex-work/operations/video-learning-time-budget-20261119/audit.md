> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/video-learning-time-budget-20261119/audit.md`；正文 SHA-256：`af0ead850e58c1debefe9c14984beeb23e22c7faebf33ab0644e14be749f8e6e`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# Video learning time-budget audit — 2026-11-19

Scope: read-only source audit of `panghu_agent` in the `video-mainline-reference` worktree. No source, deployment, admission, or production record was changed. Runtime incident facts below were supplied by the parent investigator; this audit did not independently query credentials or the production Agent catalog.

## Conclusion for the newest failed task

The newest author job (`8d3057d7…`, project `588a5b7e…`, experiment `478486…`) failed with `model_error` about 212 seconds after launch. Its 600-second deadline still had about 388 seconds left, and rendering had not started. Increasing creation or Shader rendering time would not address this incident. Diagnose the model call first. Do not label it a timeout or reduce visual scope on that basis.

Separately, the previously blocked original peak Shader demonstrates a genuine render-budget mismatch: the parent reports a server CPU single frame at 30.587 seconds and a complete export at about 1201 seconds under an offline 180-second screenshot / 7200-second outer limit. That source cannot fit the normal 10-second screenshot and 360-second render limits. A timeout alone does not determine whether the original has better visual quality; the rendered original is needed for comparison.

## Current complete limit chain

Paths below are relative to `panghu_agent/`; line numbers are from the audited worktree.

| Layer | Current limit / behavior | Evidence |
| --- | --- | --- |
| Video form | Default 15 min; range 1–60 min; rounds default 3, range 1–8 | `video_workbench/animation_lab_web/video-library.html:79` |
| Client request builder | 900-second default, max 3600; retry ignores newly entered feedback/budget and submits only request identity + retry mode | `animation_lab_web/video-model.mjs:23–27,45–54` |
| Public API contract | Start default 900, max 3600; subsequent experiment max 3600 | `animation_lab_web/video-api.openapi.json:901–905,979–983` |
| Shared service validation | `_budget`: default 900, accepted 60–3600, rounds 1–8. Video inherits it | `picture_learning_service.py:153–160`; `video_learning_service.py:90` |
| Whole experiment deadline | Frozen as `created_at + max_seconds`; covers author, render, review, refinements, transfer | `picture_learning_service.py:222–233` |
| Public capability catalog | Video `max_seconds=3600`, maximum clip 60 s, 1280×720, 24 fps | `video_learning_service.py:323` |
| Author/review gateway | `min(600, authoritative route max_timeout_seconds, remaining experiment seconds)`; absolute whole-experiment deadline also sent | `animation_review_gateway.py:112–118`; both video classes inherit it |
| Reference profile source | Generated author/review profiles advertise max 1200 seconds. Actual production catalog not independently inspected here | `agent_service/deploy/reference_learning_catalog.py:81` |
| Generic Agent contract | Per-job request and route upper bound 3600 seconds; authoritative profile can reject excess | `agent_service/contracts.py:175,376,433` |
| HTTP transport | AgentClient timeout 30 seconds. This bounds an individual API HTTP call, not execution of the stopped Agent job | `animation_creation_executor.py:209` |
| Method renderer constructor | Default 360 sec; accepted range 30–600 | `animation_method_renderer.py:42,298–305` |
| Video renderer | Copies method renderer timeout; no dedicated extended video timeout | `video_learning_renderer.py:18` |
| Executor/deploy configuration | Creates method renderer without timeout override; no renderer timeout CLI / generated setting currently | `animation_creation_executor.py:83–88,269`; `deploy/animation_creation_executor.py:147` |
| Render attempt deadline | Effective timeout is min(configured timeout, remaining whole-experiment time); first claim freezes it. Replay preserves that frozen value | `animation_method_renderer.py:576–606` |
| Actual Docker run | Remaining budget recomputed at execution; 15 sec reserved for cleanup; 2 CPU, 1 GiB RAM, 128 MiB shm, 256 MiB tmpfs | `animation_method_renderer.py:217–221,251–253` |
| Browser default wait | 10 seconds | `animation_method_host.mjs:194` |
| Browser navigation / reload | 20 seconds | `animation_method_host.mjs:215,280` |
| Frame screenshot | Explicit 10 seconds, independently caps each frame | `animation_method_host.mjs:254` |
| HyperFrames readiness | 20 seconds default | `motion_renderer/hyperframes_project.mjs:176` |
| HyperFrames seek | 15 seconds default; timeout helper currently accepts at most 60 seconds | `motion_renderer/hyperframes_project.mjs:92–93,193` |
| Encoder/probe command | Each spawnSync timeout 180 seconds | `animation_method_host.mjs:312` |
| Review/next-stage entry | At least 90 seconds remaining required for relevant later phases | `picture_learning_service.py:587–601,664–665` |
| Reference analysis | Separate operation, default 600 and max 1800 seconds; not production/creation budget | `video_learning_analysis.py:24–26` |

## Minimal coordinated future change for complex CPU rendering

Do not implement this as a speculative fix for the current `model_error`. When implementing the authorized longer production policy, the following is the smallest coherent route:

1. Scope larger budgets to video learning. A practical initial profile is total default 60 minutes / maximum 120 minutes, with rounds unchanged. Override the video budget policy and update its form, client builder, OpenAPI, and advertised catalog together. Leave picture, reference-analysis, narration, and unrelated production limits alone.
2. Allow video author/review jobs up to 1200 seconds through an explicit subclass cap consumed by the shared gateway. Keep `min(profile cap, remaining whole budget)` and verify actual production profile readiness. This resolves a latent source 1200 / gateway 600 inconsistency; it does not explain an exit at 212 seconds.
3. Add a dedicated configurable video render timeout. For this measured workload, 3600 seconds is a reasonable initial default, with a hard maximum 7200. Do not lengthen method or picture render defaults implicitly by modifying one shared default. Preserve the whole-experiment deadline, minimum-start check, fixed first-attempt binding, stop proof, and cleanup reserve.
4. Provide a declared long-frame host profile with 180-second screenshot and, if measured initialization requires it, navigation/default waits up to 180 seconds. Record the profile in immutable request/binding/provenance. The normal 10-second host can remain available for ordinary work. Do not blindly increase encoder limits or HyperFrames seek limits: the observed original failure was frame capture. If a real seek timeout occurs, make it an explicit separately measured change and update its bounded helper too.
5. Update the reference acceptance verifier's `configured_timeout <= 600` check to the chosen declared video maximum and verify >600-second bindings. The method and picture verifiers also contain <=600 checks; only change those if the design intentionally extends those workflows. A shared renderer constant alone is insufficient.
6. A larger-resource retry must create a new operation identity with an explicit new runtime/budget binding while preserving the original source SHA. Ordinary `retry` currently freezes prior source, knowledge pin, and original budget; its API intentionally rejects injected budget fields. Never edit an old completed binding or old stop receipt to make it appear newly authorized.
7. Resource failure handling should preserve source, diagnostics, and best available result; report the constrained phase and measured resource need. Offer the user increased time/compute. Do not use timeout evidence to auto-simplify source, claim bad quality, or claim a successful rerender.

If avoiding a new host profile initially, updating the common host is possible but affects every engine/authoring admission and all new bindings. The profile approach narrows that impact; it needs an explicit request/host selection contract rather than an untracked runtime patch.

## Admission and history requirements

Changing `animation_method_host.mjs` changes host SHA. `MethodAnimationRenderer.capabilities()` compares it to measured engine admission, and Anime.js admission embeds that runtime identity. Changing the HyperFrames adapter additionally changes project runtime SHA. These are real runtime changes, so fresh stopped Canvas / Three.js / authoring-library executions must establish the new identity before those capabilities are advertised. Also inspect Manim resource-consumption admissions that bind the method runtime. Updating an old JSON SHA without a new measured render is not admission.

Old complete results and frozen bindings must remain historical facts. New operations use the new profile; recovery reconciles the existing claim, not recomputed limits. Acceptance reconstruction must agree on the declared host, configured/effective timeouts, actual execution timeout, source SHA, image digest, cleanup proof, frame count, absolute/reverse/repeated/reload seek checks, full decode, and output media SHA.

Known acceptance hard caps:

- `agent_service/deploy/reference_learning_acceptance.py:151–158`: effective <= configured <=600.
- `agent_service/deploy/animation_method_acceptance.py:153–160`: effective <= configured <=600.
- `agent_service/deploy/picture_learning_acceptance.py:172–176`: effective <= configured <=600.
- `tests/video_workbench/test_video_learning_import.py:59–65`: exact allowable offline host patch derivation currently recognizes 10s ->180s screenshot/default and 20s ->180s navigation. If host defaults change, preserve a narrow derivation; do not broaden it to arbitrary host modifications.

## Necessary verification when implementing

- Client/API: default and max budget boundaries match; old inputs still parse; technical retry remains immutable; explicit resource retry cannot overwrite source/history. `video-library-ui.test.mjs` and `test_video_learning_service.py`.
- Gateway: video gets 1200 only when route and total remaining allow it; other gateway caps stay unchanged; 212-second `model_error` remains distinct from deadline failure. `test_animation_review_gateway.py` plus video gateway coverage.
- Renderer: >600 configuration accepted only in the intended profile; 29-second remaining rejection, min(configured, remaining), frozen replay, actual cleanup reserve, source SHA retention. `test_animation_method_renderer.py`, `test_video_learning_renderer.py`, `test_video_learning_render_repair.py`.
- Configuration: dedicated timeout/profile reaches executor and generated deployment, invalid and incomplete settings rejected. `test_animation_creation_executor.py`, `test_animation_creation_executor_deploy.py`.
- Host: long frame capture receives the declared timeout; whole budget remains bounded; frame seek determinism/full decode stay required. `animation-method-host.test.mjs`, `hyperframes-project.test.mjs`.
- Acceptance/import: independently reconstruct a declared >600-second render, reject inconsistent or forged limits/host identity, preserve prior import provenance. `tests/agent_service/test_reference_learning_acceptance.py`, `test_video_learning_import.py`.
- Production measurement: rerender the untouched original source using the new admitted profile, with elapsed time, peak RSS/CPU, source/host/image hashes, cleanup, frame/seek/decode receipts. Compare the real outputs visually; do not treat longer completion as proof of visual superiority.

No tests were run because no source was changed. Existing unrelated dirty files, including `tests/video_workbench/video-library-ui.test.mjs`, were not modified.
