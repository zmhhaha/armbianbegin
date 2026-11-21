> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/reference-learning-design-20261118/spec-additions.md`；正文 SHA-256：`0322aada7a3201eec0ae2f136c0cb6f656418f7802b89464fae0df5f29c58e8a`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

### Requirement: Creative authors directly observe reference media and actual outputs
Picture and video learning SHALL provide creative authors with direct access to applicable original reference pixels, rendered outputs and goal-relevant temporal or audio evidence through admitted model inputs or media-reading tools. Research summaries MAY index and explain the evidence but SHALL NOT replace an author's only visual access. The system SHALL retain exact media, crop or frame identities, actual timestamps where applicable, role and operation bindings, and actual supplied/read evidence. Delivery receipts SHALL NOT imply model understanding or artistic success. The new transport, model capabilities and role contracts SHALL be admitted and versioned without rewriting historical frozen profiles or inputs. Missing or unsupported observation SHALL be reported rather than fabricated.

#### Scenario: The old author accepts text while the reviewer accepts images
- **WHEN** the current author contract rejects image files or requires empty observation.frames
- **THEN** a reviewer vision receipt SHALL NOT qualify the author as having seen the reference
- **AND** the new learning path SHALL require a separately admitted contract, real media transport and author-input evidence

#### Scenario: A creator checks its own rendered output
- **WHEN** an iteration compares a reference, the selected better baseline and a new result
- **THEN** applicable whole images, detail crops or temporal windows SHALL be available to the creator and tied to the exact rendered versions
- **AND** the recorded input/read scope SHALL distinguish delivered material from inferred conclusions

### Requirement: Picture learning retains editable drawing source and reproducible assets
An image-learning project SHALL reproduce selected reference techniques through Agent-authored drawing source and actual rendering. It SHALL preserve the resulting image, source, parameters, actual intermediate assets, their generation source or process, dependencies and render provenance so the work can be rendered again and developed further. The Agent MAY create brush textures, paper, geometry or other intermediate assets within the selected capabilities and budget. Reference media SHALL serve as observation and comparison inputs rather than being embedded as the delivered reproduction to claim that a technique was learned. An exported image or an internal video screenshot alone SHALL NOT constitute the complete picture-learning workflow.

#### Scenario: A mountain study needs a brush texture
- **WHEN** an Agent generates a texture and uses it with Canvas drawing
- **THEN** the project preserves both the authored texture or its actual bytes and the generation process, together with source and render evidence
- **AND** later editing does not depend on the original reference remaining accessible

#### Scenario: A picture technique is published before animation exists
- **WHEN** picture comparison supports a brush or material technique but motion was not produced or observed
- **THEN** the method MAY inform an explicitly requested whole-library release with static-only evidence and an explicit unverified-motion scope
- **AND** a later animation SHALL establish its own actual motion evidence

### Requirement: Video learning uses goal-adaptive temporal and audio observation
A video-learning experiment SHALL target one selected effect passage. The observation plan SHALL combine evidence for overall stages with goal-appropriate denser inspection of difficult motion, occlusion, transitions or deformation, and actual audio observation when expressive sound or audiovisual timing is a learning target. Requested and actually decoded frame times, repeated-frame aliases and observation limits SHALL remain distinguishable. A fixed set of sparse screenshots SHALL NOT substitute for all required temporal evidence. Video learning MAY refine keyframes first for appearance problems or begin with a continuous passage for motion problems; a separate completed image experiment SHALL NOT be mandatory. Reference, better-baseline and candidate comparisons SHALL support the relevant visual details and semantic events rather than assuming the same raw second always represents the same state. Applicable final temporal and sound conclusions SHALL remain bounded by actual observation.

#### Scenario: A reference has a difficult reveal and an expressive impact sound
- **WHEN** the selected learning target includes those events
- **THEN** observation SHALL inspect the relevant temporal windows and actual audio for both reference and generated work
- **AND** static frames, waveform existence or source assertions SHALL NOT establish smooth motion or audiovisual coordination

#### Scenario: Keyframe appearance is already adequate
- **WHEN** the learning problem concerns group movement or a transition
- **THEN** the creator MAY work directly on the continuous passage while recording its key states and observed limitations

### Requirement: Reproduction and creative exploration have distinct objectives
Reference learning SHALL first reproduce the selected reference techniques and effect-formation process, including relevant motion and rhythm, before claiming reproduction success. Creative exploration MAY independently choose duration, rhythm and expression within the current request. A visually attractive result that departs from the selected learning objective SHALL be retained as a separate creative or improvement result rather than substituting for successful reproduction. Reference aspect ratio, captions, watermarks, interface and all object positions SHALL NOT automatically become reproduction constraints. Explicit developer constraints SHALL determine the parts to reproduce.

#### Scenario: An attractive watercolor result replaces a dry-ink target
- **WHEN** a new candidate looks appealing but loses the requested dry-brush quality
- **THEN** the comparison SHALL record that target regression even if other qualities improve
- **AND** any retained creative variation SHALL remain distinguishable from the reproduction result

#### Scenario: A static study is developed into original animation
- **WHEN** the developer selects an image-study version and requests animation without a reference video
- **THEN** the service SHALL create a linked demand-creation project that may reuse the explicitly selected source, assets and methods
- **AND** the image-study history stays intact while the new motion and rhythm receive independent validation

### Requirement: Creators self-check and independent reviewers assess learning milestones
Creators SHALL inspect their own real outputs. Independent reviewers SHALL compare applicable reference, better-baseline and new outputs at complete reproduction, important revision and transfer milestones. Reports SHALL identify observed gains, regressions, evidence and uncertainty under versioned criteria, while leaving implementation choices to the creative author. Technical validity, reference reproduction, work quality, static appearance, continuous motion, audio, audiovisual coordination and transfer SHALL retain separate scopes. No aggregate score, source complexity or number of Agents SHALL establish success on an unsupported criterion. A newer result SHALL NOT automatically replace a better version or a developer-adopted default.

#### Scenario: Only a local texture improved
- **WHEN** comparison supports improved mountain texture while foreground quality regresses
- **THEN** both findings and their exact versions SHALL remain available and the previous better work SHALL be retained
- **AND** the report SHALL NOT describe overall artistic improvement without supporting evidence

### Requirement: In-flight learning is inspectable and stoppable without live feedback mutation
A running experiment SHALL expose inspection and stop operations while preserving its frozen goal, references, criteria, capabilities, knowledge binding and feedback cutoff. New developer comments or changed requirements SHALL apply to a subsequent experiment, not later review, recipe, component or integration operations of the active commission. Persisting a comment SHALL NOT authorize an active role to requery it as new instructions. A stop request SHALL preserve completed outputs and spent work, reconcile all original operations and distinguish requested stopping from proved termination. Viewing, refreshing, comparing, copying inputs or downloading SHALL NOT schedule creation or reset budgets. Continuation, fresh rebuild and technical retry SHALL retain their existing distinct contracts.

#### Scenario: A new preference is saved while a review or Manim iteration is pending
- **WHEN** the preference is newer than the active experiment's frozen feedback cutoff
- **THEN** the active operation SHALL NOT consume it through a live feedback lookup
- **AND** the preference MAY be explicitly bound to a new subsequent experiment

#### Scenario: The developer stops before transfer
- **WHEN** a stop request arrives after useful reproduction work but before transfer finishes
- **THEN** the service SHALL retain completed work and genuine execution state, show pending verification accurately and avoid automatic replacement tasks

### Requirement: Generated knowledge preserves scoped evidence and alternative methods
The WikiSkill compiler SHALL derive self-contained guidance from the frozen facts of all three libraries and preserve independently supported applicability and limitations. It MAY retain multiple effective approaches to the same effect instead of automatically discarding all but the highest-scored sample. Static techniques MAY be published before motion verification. Reproduction success with failed or absent transfer MAY support narrowly evidenced local techniques, but SHALL NOT establish a general reusable capability. Failed transfer SHALL NOT by itself establish universal failure. Source observations, developer judgements, hypotheses and unverified scope SHALL remain distinguishable. Research URLs or copied source-video content SHALL NOT replace internalized operational guidance. Publication SHALL remain an explicit whole-library operation; this requirement SHALL NOT add automatic releases, manual knowledge forms or per-method human approval gates.

#### Scenario: Two brush methods work under different conditions
- **WHEN** actual evidence supports both a procedural brush and an authored-texture approach
- **THEN** the generated WikiSkill MAY retain both with their conditions, steps, evidence and limitations for demand-driven discovery
- **AND** one sample's higher score SHALL NOT automatically erase the other valid method

#### Scenario: Reproduction works but transfer fails
- **WHEN** the frozen record supports only a local appearance technique under the original conditions
- **THEN** explicit publication MAY include that limited technique and its failed-transfer boundary
- **AND** the release SHALL NOT state that general transfer, continuous motion or audio quality passed without supporting evidence
