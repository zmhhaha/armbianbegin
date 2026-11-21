> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/ink-scene-depth-20261121/spec-draft/spec.md`；正文 SHA-256：`e95492a276fb0de8553145fc76da349672e4438c13a9e792503c41b017ebdd71`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

## ADDED Requirements

### Requirement: Shared versioned scene and learning semantics
The system SHALL use a bounded, versioned, inert description of scene worlds, objects, anchors, occupied regions, scale, depth, attachment, occlusion, layers, shots and local animation across film creation, picture learning, video learning and effect-method records. These workflows SHALL retain separate entry points, projects and histories. Source observations, inferred models, generated reconstructions and verified results SHALL remain distinguishable with traceable source identities, evidence locations, uncertainty and verification scope. A description SHALL NOT grant executable capabilities or silently upgrade historical records.

#### Scenario: A picture and a film describe the same spatial method
- **WHEN** picture learning describes an anchored tree behind a rock and a new film uses that method
- **THEN** both may express the same object and spatial semantics, while their own sources, object instances, dependencies and verification evidence remain separate.

#### Scenario: A historical record lacks spatial metadata
- **WHEN** a historical candidate or learning result has no new scene or temporal fields
- **THEN** its original meaning and identity remain valid, and missing data is recorded as unknown or absent rather than synthesized as verified capability.

### Requirement: Style-aware object layout and depth
Scene planning SHALL use stable object identities with anchors, parent or attachment relations, bounded extents, scale and depth information appropriate to the style and backend. Grids or point sets SHALL assist composition, region placement, support surfaces and scale constraints rather than force every stroke into a global point cloud. Logical or ordinal depth and geometric depth SHALL be distinguishable. Image-space Y alone SHALL NOT determine depth. Style-specific layouts MAY use scattered perspective, planar hierarchy or geometric projection while maintaining declared attachment and occlusion consistency.

#### Scenario: A tall foreground object reaches above distant mountains
- **WHEN** a near tree extends high in the image
- **THEN** its anchor and declared depth retain its foreground identity; its upper image position does not automatically shrink, blur or fade it into the background.

#### Scenario: Layout relationships are inconsistent
- **WHEN** an object floats off its declared support, a leaf detaches from its branch, scale constraints are violated or an attachment or occlusion graph is invalid
- **THEN** spatial validation identifies the affected objects and relations for bounded correction instead of treating a valid source file as a valid composition.

### Requirement: Separate scene worlds shots and execution intervals
A film SHALL plan a small set of complete scene worlds reusable by multiple shots within that film. A scene world, a shot and an execution interval SHALL be distinct concepts with exact world and plan references. Object identity and spatial relationships SHALL remain continuous across shots and interval boundaries. Execution splitting SHALL respect existing clock and module limits and SHALL NOT itself require new scene authoring. Shared live instances or caches across existing isolated module realms SHALL NOT be assumed without an admitted implementation.

#### Scenario: One world is viewed for longer than a module interval
- **WHEN** multiple shots or execution intervals reference the same world beyond the current per-interval duration limit
- **THEN** scheduling may split the execution while preserving world identity, absolute time and continuity, without silently raising the clock limit or generating an unrelated replacement world.

#### Scenario: A fixed segmentation would generate redundant scenery
- **WHEN** the requested duration crosses an arbitrary editing boundary but the existing world supports the next composition
- **THEN** planning reuses that world and does not introduce a new scene solely because a fixed number of seconds elapsed.

### Requirement: Fully automatic unified shot and motion planning
Before expensive scene production, the planner SHALL jointly determine worlds, visible coverage, object relationships, finite camera paths, focal areas, holds, maximum magnification, local animation and reuse needs. It SHALL automatically choose moving-camera, fixed-camera and local-animation combinations according to the creative goal; no camera movement, fog, birds or other effect SHALL be mandatory by default. Initial scope SHALL support a fixed principal viewing direction with translation and bounded push or pull, without claiming unseen backsides or unrestricted orbiting. This feature SHALL NOT introduce a user-facing per-shot local-editing path, whether through UI or API, and SHALL NOT require per-shot user confirmation.

#### Scenario: A fixed shot best serves the scene
- **WHEN** the creative plan calls for a fixed view with moving water, or for a scene without local motion
- **THEN** the planner may select that combination and shall not add camera movement or unrelated animation merely to satisfy a template.

#### Scenario: A camera path exceeds usable artwork
- **WHEN** a planned path exposes an undrawn edge or magnification exceeds the available detail
- **THEN** low-cost validation identifies the gap before full export and bounded correction considers the path, composition or necessary local artwork within the frozen goal and budget.

### Requirement: Backend-compatible bounded layer composition and replay
The renderer SHALL preserve common spatial meaning while using the actual admitted capabilities of Canvas, SVG/HTML or Three.js. Layer count, cached pixels, temporary storage and lifetime SHALL be bounded. Layer and object masks SHALL preserve correct paper, background and occlusion composition; fixed black foregrounds, uniformly faded distance layers, mandatory halos or exactly three layers SHALL NOT substitute for style-aware rendering. Camera and local animation state SHALL be derived from absolute task time and stable seeds so repeated and out-of-order frame evaluation is deterministic.

#### Scenario: Layered composition preserves the background
- **WHEN** soft fog separates near and far objects
- **THEN** masking targets the intended objects or layers without punching transparent holes through the final paper or introducing a hard horizontal cut as an accepted repair.

#### Scenario: A renderer does not admit an API
- **WHEN** the current Canvas realm prohibits OffscreenCanvas or a selected backend restricts another drawing API
- **THEN** the adapter uses its admitted mechanisms or reports the capability unavailable rather than relaxing isolation or pretending all backends share one native implementation.

#### Scenario: Frames are evaluated out of order
- **WHEN** a shot is sought repeatedly or across an execution boundary
- **THEN** the same absolute frame and seed produce consistent object placement, layer state, camera state and local animation without wall-clock or incremental-update dependence.

### Requirement: Controlled plan revisions and valid technical recovery
The unified plan SHALL constrain downstream authors and renderers. Changes to principal objects, spatial relationships, shot types or core animation SHALL create a traceable plan revision with reasons and identify dependent content, caches and checks that must be invalidated or repeated. Bounded local corrections MAY retain unaffected material. Technical recovery SHALL preserve its original frozen goal, plan, valid results, budget history and retry rules rather than silently becoming a fresh creative attempt.

#### Scenario: A principal object must move to repair composition
- **WHEN** automatic review requires moving a main peak or changing a shot from moving to fixed
- **THEN** the system updates the common plan and rechecks affected shots and dependencies, rather than letting one module independently contradict the other views.

#### Scenario: A stopped renderer is recovered
- **WHEN** a technical retry continues an otherwise valid frozen plan
- **THEN** it retains the original scene meaning, actual costs and terminal history and does not load a new direction or reset the accumulated lineage to gain more work.

#### Scenario: A fresh rebuild must not inherit the old composition
- **WHEN** an existing fresh-rebuild workflow excludes the old source, layout and dedicated methods
- **THEN** the new shared-world or cache mechanism does not reintroduce those inputs, while a legitimate technical recovery may retain its own original valid world under its existing rules.

### Requirement: Automatic staged quality gates and bounded repair
The workflow SHALL perform representative low-cost layout, keyframe and short-preview checks before full export. Technical, spatial, style-related visual, temporal and audio conclusions SHALL remain separate and bounded by actual evidence. Checks SHALL cover relevant anchors, proportions, attachment, occlusion, layer joins, view boundaries, magnification and temporal continuity. Visual evaluation SHALL use the creative goal and style and SHALL retain uncertainty; empty paper, pale distant objects or fixed cameras SHALL NOT alone imply a defect. Repairs SHALL remain within existing task, child-task and revision limits and SHALL NOT create unlimited post-film revision rounds or mandatory high-cost learning stages.

#### Scenario: The source compiles but the composition fails
- **WHEN** a preview is technically valid but reveals a detached leaf, an unsupported object, a hard mountain-foot cut or inconsistent depth
- **THEN** technical success does not pass the spatial or visual gate, and bounded correction targets the affected cause before formal full export.

#### Scenario: A preview has limited observation coverage
- **WHEN** a few keyframes or a short clip have passed their corresponding checks
- **THEN** the report states that coverage and does not claim the final long film has been rendered, continuously viewed, heard or artistically accepted.

### Requirement: Separate bounded model and rendering budgets
The host SHALL freeze platform caps and any stricter user limits and SHALL separately account for model generation and rendering or resource budgets. Planning MAY allocate and reallocate remaining budget within those caps but SHALL NOT increase total limits automatically. Reviews, collaboration, learning exercises, failed work and corrections SHALL share the applicable task budget and preserve cumulative lineage. When required quality remains unmet at exhaustion, the workflow SHALL stop formal export and preserve the best available preview, issues, actual recorded consumption and unfinished work. Unknown token or resource values SHALL remain unknown rather than estimated as measured savings.

#### Scenario: Automatic quality repair exhausts the budget
- **WHEN** the allowed learning or repair work is exhausted and required quality has not passed
- **THEN** no formal full-film export is admitted, while the best available preview and diagnostic record remain available without a new automatic budget or an accepted-film label.

#### Scenario: A world is reused by several shots
- **WHEN** existing scene data or drawing results serve another shot
- **THEN** the system records actual new model and render consumption separately and does not count old generation as new work or promise that frame capture and encoding are free.

### Requirement: Evidence-bounded spatial learning from pictures
Picture learning SHALL progressively describe observed composition, object anchors, occupied regions, scale, visible overlap, attachment, depth cues, layers and style-related space. Inferred spatial models SHALL carry their evidence and uncertainty. A single picture SHALL NOT establish calibrated three-dimensional depth, hidden geometry, observed camera movement, audio or continuous motion. Optional derived animation exercises SHALL be separately identified as generated work and SHALL NOT upgrade the source picture's static evidence contract.

#### Scenario: A picture suggests several depth arrangements
- **WHEN** a static reference supports more than one plausible ordering or depth interpretation
- **THEN** learning preserves alternative or unknown relationships and may test a bounded reconstruction without presenting the selected hypothesis as observed geometry.

#### Scenario: A picture is used to create a moving-camera exercise
- **WHEN** a learned spatial hypothesis is animated in a new exercise
- **THEN** the camera path and motion verification belong to that generated exercise, while the original reference remains static-only evidence.

### Requirement: Versioned temporal evidence for video camera learning
Video learning SHALL distinguish sampled stills, timestamped temporal sequences, actually observed bounded clips and full continuous observation. It SHALL retain source identity, frozen observation scope, requested times, actual PTS and time base, frame identity and duplicate mappings; repeated selection of the same decoded frame SHALL NOT increase observed coverage. Motion hypotheses SHALL distinguish camera movement, object motion, layer parallax, local deformation, digital crop or zoom and editing, preserving inconclusive alternatives where the evidence is insufficient. Existing strict v1 sampled_frames_only inputs and results SHALL retain their required false motion, audio and whole-video-observed flags. New temporal observation or verification SHALL require a separately versioned compatible contract and admitted capabilities.

#### Scenario: Old sampled-frame video learning proposes a camera path
- **WHEN** a legacy v1 task infers a pan or push from sampled stills
- **THEN** it records a bounded hypothesis under sampled_frames_only and does not set motion_observed, audio_observed or whole_video_watched to true or rewrite its frozen input.

#### Scenario: Camera motion is ambiguous
- **WHEN** an actually observed temporal sequence cannot uniquely distinguish a push from digital zoom, or an object move from camera motion
- **THEN** learning records the observed changes, timestamps, competing explanations and uncertainty rather than asserting a calibrated camera trajectory.

#### Scenario: A bounded clip contains a fixed camera and moving objects
- **WHEN** the new admitted temporal path observes that clip
- **THEN** it can learn the fixed-camera local-animation method for the real observed range without labeling all pixel changes as camera motion or claiming full-video or audio review.

#### Scenario: A reference reproduction requires specific camera motion
- **WHEN** a frozen reproduction goal requires the observed camera movement, action or rhythm
- **THEN** automatic planning preserves those requirements for reproduction and does not substitute another static or dynamic arrangement merely to reduce work; independent new-content transfer remains governed by its own new creative goal.

### Requirement: Progressive learning with optional stages and independent transfer
Picture learning, video learning and effect-method work SHALL be able to progress through source observation, spatial or layer hypotheses, bounded reconstruction, evidence-supported temporal study, independent new-content transfer and comparison or refinement. Stages SHALL be selected according to the goal, available evidence, capability and remaining budget rather than forced for every input. Records SHALL distinguish not attempted, proposed, executed, verified, failed, excluded and inconclusive work. Reconstruction success SHALL NOT imply transferable mastery. Transfer SHALL preserve existing separation from original reference media and reconstruction baseline source, and SHALL verify its own new output.

#### Scenario: Only static structure has been validated
- **WHEN** a task completes a spatial reconstruction but lacks admitted temporal observation or remaining budget
- **THEN** it retains the verified static result and explicit pending or unavailable temporal stages without generating compulsory extra work or claiming motion mastery.

#### Scenario: A method is tested on different content
- **WHEN** a transfer exercise uses learned layering or camera principles for a new subject
- **THEN** its inputs honor the existing original-reference and baseline-source isolation, and its own evidence determines transfer success independently of the reconstruction result.

### Requirement: Evidence-rich effect retention and explicit knowledge publication
Effect-method and candidate records SHALL be able to retain spatial and layer organization, camera or local-animation recipes, relevant parameters, dependencies, source evidence, comparisons, failure cases and applicability limits using compatible versioned metadata. Existing explicit effect selection and user-initiated whole-library WikiSkill publication SHALL remain separate actions. Learning or film completion SHALL NOT automatically adopt an effect, publish knowledge or create a cross-film executable scene asset store. A knowledge release MAY teach evidence-supported space, layering and camera methods but SHALL retain hypotheses, exclusions and observation limits.

#### Scenario: A successful layered effect is selected for retention
- **WHEN** an eligible real effect is explicitly selected through the existing library workflow
- **THEN** its code, preview and method evidence may retain the shared spatial or temporal learning record, while no WikiSkill release is implied by that selection.

#### Scenario: A new knowledge release includes camera learning
- **WHEN** the user explicitly starts a whole-library publication containing relevant learning records
- **THEN** the compiled methods cite or exclude their real evidence, distinguish tested motion from sampled-frame hypotheses and failures, and do not promote an unverified camera claim merely because it was stored or cited.

### Requirement: Frozen knowledge consumption and historical compatibility
New production and learning batches SHALL retain exact frozen knowledge and dependency identities and existing enabled or disabled WikiSkill behavior. Common scene and learning semantics SHALL NOT silently modify old source packages, tasks, strict input field sets, hashes, release bodies, selected effects, deadlines, retry rules or execution permissions. Cross-task influence through WikiSkill SHALL remain method and implementation guidance with applicable conditions; it SHALL NOT automatically inject old film objects or execute arbitrary knowledge attachments. Runtime changes, new contracts and any capability rollout SHALL require their own implementation and validation evidence, separate from this documentation change.

#### Scenario: A later batch reads an updated spatial method
- **WHEN** a new batch chooses an explicitly published compatible release
- **THEN** the batch freezes that exact release and its admitted dependencies, while an existing batch keeps its original selection and historical task semantics.

#### Scenario: Knowledge is disabled or a dependency is unavailable
- **WHEN** a task disables WikiSkill or lacks an admitted implementation needed by a learned method
- **THEN** existing disabled-knowledge and capability rules remain enforced without covert skill supply or execution authority inferred from the new design.

#### Scenario: This proposal validates without an implementation
- **WHEN** these design and specification artifacts pass the mapped OpenSpec validator
- **THEN** only the documentation milestone is established; implementation, actual temporal learning, deployed scene reuse, effect adoption, knowledge publication and artistic acceptance remain unclaimed.
