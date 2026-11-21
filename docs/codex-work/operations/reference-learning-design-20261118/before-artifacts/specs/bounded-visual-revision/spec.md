> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/reference-learning-design-20261118/before-artifacts/specs/bounded-visual-revision/spec.md`；正文 SHA-256：`528673487a5632fef483573406cbed7982d6b2e4df64395e3d0b945141bb830d`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../../../README.md)

## ADDED Requirements

The requirements in this capability apply exclusively to finished-video production and its end-user polishing workflow. They SHALL NOT impose a cumulative one-plus-two allowance on the developer effect library. Shared execution budgets and idempotency MAY be reused without importing these production allowances into developer iteration.

### Requirement: Default finished-video polishing is bounded to one review and revision
Initial finished-video production, before presentation to the end user, SHALL perform at most one independent visual review and at most one creator revision from its findings. It SHALL then rerender and perform technical verification, record unresolved issues and retain both initial and revised candidates without automatically issuing another review-generation loop. Technical failure SHALL NOT be disguised as a deliverable, and perceived-quality concerns SHALL NOT silently trigger unlimited retries.

#### Scenario: Issues remain after the first revision
- **WHEN** the creator has used the single default revision
- **THEN** the system presents the resulting draft and known remaining issues for owner judgement
- **AND** it does not automatically start another creative or independent-review round

### Requirement: Whole-video owner rounds require explicit initiation
After watching the whole draft, the owner MAY explicitly initiate up to two additional whole-video polishing rounds. Each round SHALL have a recorded source draft, feedback, scope and bounded review/revision work. A round spanning multiple segment tasks SHALL consume one whole-video round and SHALL NOT allocate a separate pair of rounds per shot. The interface SHALL expose the consumed and remaining rounds without implying unlimited improvement.

#### Scenario: Owner requests another overall polish
- **WHEN** the owner has remaining whole-video rounds and explicitly requests one after reviewing the draft
- **THEN** the system reserves one applicable round and creates its bounded tasks from that draft and feedback

#### Scenario: Two owner rounds have been used
- **WHEN** a further unrestricted whole-video polish is requested
- **THEN** the system directs the owner to create explicit scoped requirements rather than silently issuing more global rounds

### Requirement: Persistent revision ledger resists duplicate work and resets
The production lineage and applicable persistent allowance identity SHALL exist and be frozen before submission of the first default automatic revision. Round allowances SHALL attach to that persistent production lineage with atomic reservation, idempotent submission, operation identity and consumption evidence. Refresh, restart, cancellation, failure, candidate copying and new requirements SHALL NOT reset allowances. An already submitted attempt SHALL remain recorded; unknown submission SHALL be reconciled against the original operation before any resubmission. Release of a provably unsubmitted reservation SHALL preserve the audit trail.

#### Scenario: Concurrent requests compete for the last round
- **WHEN** two requests try to start the final available owner round
- **THEN** only one reservation can succeed and retrying the same request resolves to the original operation

#### Scenario: A submitted revision fails
- **WHEN** execution fails or its acknowledgement is temporarily unknown
- **THEN** the attempt remains bound to the lineage and original task for recovery without creating a fresh allowance or duplicate generation

### Requirement: Further work uses explicit requirements without renewing global rounds
After additional owner rounds are exhausted, further optimization SHALL use requirements bound to the relevant source version, unsatisfactory interval or global scope, problem and desired outcome. Each execution batch SHALL declare a bounded scope and task budget; requirements SHALL NOT automatically restart the default-plus-two whole-video sequence. Owner feedback SHALL remain distinct from Agent findings and technical checks.

#### Scenario: Owner identifies an unsatisfactory passage
- **WHEN** the owner records the affected interval, visible problem and expected improvement after global rounds are exhausted
- **THEN** the system can execute a scoped requirement batch with explicit bounds and preserve the previous global-round consumption

### Requirement: Visual revisions preserve confirmed narration and valid assets
Polishing SHALL by default change visuals, animation and transitions while retaining confirmed narration and audio. Material changes to confirmed narrative meaning, order or voice SHALL require an explicit owner requirement and invalidate affected dependencies. Visual segmentation and composition that preserve the confirmed meaning and audio MAY be reorganized by the Agent. Execution SHALL follow actual resource and continuity dependencies, reuse unrelated valid assets and examine adjacent transitions, preserving immutable history and actual audio identity. Placement-only changes SHOULD reuse unchanged resource content and update composition; internal timing, predecessor-state or cross-segment changes MAY invalidate additional dependent work. A one-shot change SHALL NOT imply that all other shots are necessarily unaffected.

#### Scenario: Owner asks for a clearer animation
- **WHEN** the request changes only visual expression
- **THEN** affected visual segments and necessary composition outputs are regenerated while confirmed text, applicable audio and unrelated assets remain intact

#### Scenario: Owner explicitly requests a narration change
- **WHEN** a requirement materially changes spoken text or recording
- **THEN** the affected audio, duration, alignment, visuals and review applicability are recomputed or invalidated rather than silently retaining stale approval

### Requirement: Resource remediation remains inside the current revision bounds
Resource supplementation, regeneration or implementation substitution during composition or review SHALL remain bound to the current production operation, finite budget and applicable revision allowance. It SHALL NOT create a new default-plus-two sequence or clear previous attempts. A substitute SHALL preserve the confirmed expression objective, facts and meaning and SHALL NOT override an explicitly required capability or key effect. Recovery of an uncertain existing task SHALL be distinguished from a newly charged attempt.

#### Scenario: A resource needs correction during an allowed visual revision
- **WHEN** the director identifies an unsuitable resource and the current operation has sufficient budget
- **THEN** it can update the applicable resource plan and regenerate the affected dependencies under that operation
- **AND** the supplementation neither allocates another whole-film polishing round nor changes immutable previous outputs

#### Scenario: An alternative violates an explicit requirement
- **WHEN** a proposed replacement would remove a required capability or key effect
- **THEN** it is rejected and the unsatisfied requirement remains visible instead of being reported as a successful fallback
