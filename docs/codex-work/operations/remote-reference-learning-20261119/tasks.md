> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/remote-reference-learning-20261119/tasks.md`；正文 SHA-256：`7b93c9d0cde32494358249cd9e742876414cd59814e852ccdee18e3a7e0325e2`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

## 1. Specification and source contracts
- [x] 1.1 Publish this proposal, shared design and requirement delta to the mapped OpenSpec project and validate exact readback.
- [x] 1.2 Reconcile existing upload-only/source_url-as-note requirements and document the remote source/observation contract.

## 2. Shared remote media reader
- [x] 2.1 Implement supported source metadata resolution without storing full reference media.
- [x] 2.2 Implement validated bounded on-demand retrieval, measured PTS, normalized crops, overview/detail quality and explicit source identity.
- [x] 2.3 Verify address/redirect restrictions, identity or quality changes, deadlines and temporary cleanup with real decoder fixtures.

## 3. Picture and video services
- [x] 3.1 Add idempotent owner-scoped remote reference registration alongside existing uploads.
- [x] 3.2 Integrate video-frame picture references, remote segment observation and independent reference analysis.
- [x] 3.3 Freeze actual observation evidence for each experiment and preserve technical retry semantics without persisting full video.

## 4. Agent-directed observation
- [x] 4.1 Admit scoped additional-observation requests and source/frame provenance in picture and video roles.
- [x] 4.2 Implement host-mediated stopped handoff, real fetch and role resumption within the same round and shared budget.
- [x] 4.3 Verify observation requests cannot escape the source scope, fabricate observation, duplicate attempts or overrun stop/budget policy.

## 5. Web and external Agent API
- [x] 5.1 Add consistent link/upload/saved-reference inputs, picture timestamp and optional region.
- [x] 5.2 Display actual source quality, observation state and valid original-site links without pretending webpage URLs are media streams.
- [x] 5.3 Update both OpenAPI contracts and unknown-outcome/idempotent recovery coverage.

## 6. Release and acceptance
- [x] 6.1 Run focused regressions for both existing upload paths and new remote paths.
- [x] 6.2 Validate real remote metadata, frame timestamps, high-detail observation and absence of full-video persistence without launching unsolicited creation.
- [x] 6.3 Build/deploy latest images with recorded revision/digests and verify production source/API/UI admission.
- [x] 6.4 Record implementation limits and acceptance evidence, update OpenSpec task status based on actual verification.

Acceptance record (2026-11-20): clean-source latest builds from 2a1a8bb (control/Pi/lab) and 43a0379 (executor); all four roles independently admitted and production routes activated with existing caller/runtime credentials preserved. API registration/isolation/read-only checks: 66 passed. Real lab HTTP resource/catalogue checks: 93 passed, 12 assets match the source commit. Controlled source probes verified the 38s frame, normalized crop and 24-frame overview, measured PTS and temporary cleanup. No new business creation was started by release smoke; browser visual interaction, continuous motion, audio and artistic quality were not accepted by these checks. Repository evidence: video_workbench/docs/remote-reference-validation-20261119.md and video_workbench/docs/evidence/remote-reference-learning-20261119.json.
