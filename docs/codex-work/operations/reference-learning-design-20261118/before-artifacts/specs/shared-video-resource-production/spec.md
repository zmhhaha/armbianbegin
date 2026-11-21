> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/reference-learning-design-20261118/before-artifacts/specs/shared-video-resource-production/spec.md`；正文 SHA-256：`c63a14af8ef2a53e13b5d1dc4cdcb48a645e583c612cf8eee509f8d7336b85b6`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../../../README.md)

## ADDED Requirements

### Requirement: Director planning distinguishes runtime creation from advance-produced resources
The director SHALL plan the applicable resource requirements during overall expression planning before production composition. Each requirement SHALL identify its purpose, expression objective, inputs and dependencies, explicitly required capabilities or key effects, timing intent and finite execution bounds. HTML/SVG, Canvas2D and Three.js SHALL remain runtime drawing paths under HyperFrames. Manim and other admitted producers requiring advance execution SHALL deliver verified resources into that same project. Motion authoring libraries such as GSAP and Anime.js SHALL retain their separate authoring role. An ordinary owner SHALL NOT be required to confirm every resource separately.

#### Scenario: A film combines live drawing and a prerendered demonstration
- **WHEN** a confirmed plan uses Canvas drawing alongside Agent-authored Manim content
- **THEN** Canvas source is executed during HyperFrames rendering while the planned Manim resource is produced before its dependent consumer
- **AND** both enter the same film project rather than independent final-video concatenation

### Requirement: Laboratory and formal production share an internal resource foundation
The shared resource layer SHALL belong inside video-service for this scope and SHALL manage resource plans, dependency execution, durable task state, producer interfaces, output identities and basic checks for advance-produced visuals, narration and sound effects. Actual production SHALL remain delegated to admitted generic Agent/Pi roles, isolated executors, speech-service or other explicitly admitted producers. Sharing the foundation SHALL NOT require a new public microservice, relocating existing services, implementing every future producer, or imposing the formal whole-film workflow and polishing allowances on laboratory experiments.

#### Scenario: A new advance-produced content type is admitted
- **WHEN** a future content producer meets the common input, output, isolation and execution contracts
- **THEN** it can participate through the resource producer interface without creating another Manim-specific orchestration branch
- **AND** runtime admission and actual media verification remain required before availability is claimed

### Requirement: Dependencies determine execution and precise timing
Independent resource tasks MAY execute concurrently, while dependent tasks SHALL wait for their applicable verified inputs. Narrated passages SHALL obtain actual narration identity and measured timing before producing animation whose internal rhythm depends on that recording. Non-narrated passages SHALL use director-planned timing and MAY contain sound effects. Effect placement MAY bind to animation events. The resource workflow SHALL allow bounded re-entry from composition or review rather than requiring every resource to be completed in one unconditional batch.

#### Scenario: An animation depends on recorded explanation
- **WHEN** its internal actions must follow narration
- **THEN** the plan records that dependency and its production receives the applicable real recording and timing evidence
- **AND** a planning estimate is not presented as measured alignment

#### Scenario: A non-narrated passage uses sound-supported motion
- **WHEN** the director plans a demonstration without explanation audio
- **THEN** its visual and effect dependencies can complete under director-planned timing without manufacturing narration

### Requirement: Resource content identity is separate from whole-film placement
Resource versions SHALL bind their actual inputs, generated source or instructions, producer identity and applicable dimensions, media duration, local frame/time bounds and content hashes. Generated outputs SHALL remain separate from trusted fixed libraries and authorized to their owner, project and consuming operations. Film snapshots SHALL freeze their exact resource versions, usage instructions and whole-film placement. Position-only edits SHOULD reuse valid resource content; content, internal-rhythm or continuity-input changes SHALL invalidate the actual dependent work. Dependency propagation MAY span several segments and SHALL NOT promise that a single-shot edit only affects that shot.

#### Scenario: An unchanged resource moves later in the film
- **WHEN** only its global placement changes and its content and local timing inputs remain valid
- **THEN** the workflow can reuse that immutable resource version and update the film composition binding
- **AND** the old film snapshot retains its original placement and identities

#### Scenario: A preceding state or narration changes
- **WHEN** the change affects the internal timing or continuity of subsequent work
- **THEN** the dependency graph identifies and invalidates all affected resources or composition outputs while retaining unrelated valid work

### Requirement: Remediation and substitution preserve objectives and budgets
During composition or checking, the director MAY supplement or regenerate affected resources inside the current operation's finite budget and applicable production polishing allowance. A failed or inadequate resource MAY use an alternate implementation only when the expression objective, confirmed meaning and facts, explicitly required capabilities and key effects are preserved. Actual attempts and dependency changes SHALL be recorded. Budget exhaustion or an unmet mandatory requirement SHALL preserve useful completed work and report the blocker or unresolved issue; missing output or a lowered objective SHALL NOT count as success. Supplementation SHALL NOT automatically open a new commission or allocate a new formal polishing allowance.

#### Scenario: An interchangeable implementation fails
- **WHEN** another admitted capability can satisfy the same objective within the current bounds and no explicit requirement prohibits it
- **THEN** the director may record and execute that alternative and update affected consumers

#### Scenario: A mandatory effect cannot be produced within the budget
- **WHEN** every applicable permitted attempt fails or the budget is exhausted
- **THEN** valid completed resources remain available and the unmet requirement and stopping reason are reported without silently deleting the objective

### Requirement: Durable execution and verified consumption prevent false completion
Resource execution SHALL retain original task identities, reservations and immutable output versions through cancellation, restart, timeout and uncertain submission. Unknown outcomes SHALL be reconciled against the original operation before any new chargeable attempt. Late or foreign outputs SHALL be rejected and required stopping checks SHALL apply. Producer admission, consumer admission, basic media validation and actual HyperFrames consumption SHALL remain distinct evidence. Resource completion SHALL NOT imply whole-film audiovisual review, developer acceptance or Skill publication.

#### Scenario: A producer submission acknowledgement is unknown
- **WHEN** the orchestration restarts after that submission
- **THEN** it recovers or reconciles the same task and previously spent budget instead of silently generating another resource

#### Scenario: Resource files exist but have not been consumed
- **WHEN** only a manifest or stored output is available
- **THEN** the workflow records resource availability without claiming actual film use or complete audiovisual acceptance
