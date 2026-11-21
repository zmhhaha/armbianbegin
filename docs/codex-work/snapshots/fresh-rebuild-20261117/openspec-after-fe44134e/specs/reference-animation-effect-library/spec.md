> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/fresh-rebuild-20261117/openspec-after.json`，JSON 字段 `/artifacts/specs~1reference-animation-effect-library~1spec.md`；正文 SHA-256：`ff4613b9eee4a79b4d110ad82acedc4af23b28ca827879adb0d972ac2b97b4f1`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../../../README.md)

## ADDED Requirements

This capability governs a developer-facing creative-method and effect-demonstration library. Developer curation and publication are distinct from finished-video end-user polishing. No requirement here imports the finished-video one-plus-two lifetime allowance.

### Requirement: Creative methods are the primary reusable knowledge
The library SHALL distribute creative methods as versioned SKILL.md packages with frozen content and attachment identities. Foundation skills SHALL explain HyperFrames project, clock, dependency and admitted drawing-runtime conventions; expression skills SHALL explain reusable understanding and animation techniques. Guidance SHALL include applicability, independent principles, steps and judgements, trade-offs, failure modes and evaluation criteria. Agents SHALL maintain methods. Self-created verified examples MAY support understanding and reproduction; copying example source or filling developer-authored fixed compositions SHALL NOT define successful reuse. Published package versions SHALL be immutable.

#### Scenario: A production task needs an expression technique
- **WHEN** an Agent reads a published expression Skill and applicable foundation guidance
- **THEN** it can independently compose a new animation within the admitted HyperFrames project contract
- **AND** it need not copy a demonstration's composition or source

#### Scenario: A published package needs a content or attachment change
- **WHEN** guidance, attachments or tested applicability change
- **THEN** the system creates a new candidate version rather than modifying the published package or inheriting its approval

### Requirement: Complete demonstrations and methods have versioned many-to-many evidence
The system SHALL separate methods, complete demonstrations, candidate media and experimental commissions. A demonstration MAY validate multiple method versions and a method version MAY be validated by multiple demonstrations. Evidence SHALL bind the method, demonstration, objective and criteria versions with reference or transfer role, outcome and observation limitations. Complete demonstrations SHALL retain setup, coordinated process, attention guidance and closure without a universal eight-second or single-shot constraint. By default they SHALL omit explanatory narration while allowing applicable sound effects.

#### Scenario: One passage uses multiple techniques
- **WHEN** a passage combines identity tracking, progressive reveal and causal statistics
- **THEN** the complete playable passage remains the viewing and acceptance object while its distinct method-version relationships are recorded

#### Scenario: Sound effects contribute to expression
- **WHEN** a demonstration's objective includes sound-supported action
- **THEN** its actual playable result retains those effects and their timing even though it has no explanatory narration

### Requirement: Reference observation and explicit goals establish the experiment
The lab SHALL accept accessible reference media or a described expression objective. For a long reference, an Agent SHALL propose evidence-bound complete intervals and learning objectives for developer selection; an already specified interval and objective SHALL skip redundant selection. Media identity, actual ordered observation coverage and limitations SHALL be recorded. Links, subtitles or sparse screenshots SHALL NOT be represented as viewing an entire animation. Experiments without external reference SHALL still declare objectives and supporting inputs.

#### Scenario: Developer selects a passage from a long reference
- **WHEN** actual accessible media contains several relevant passages
- **THEN** the Agent proposes observed intervals and learning reasons before implementation
- **AND** access or unobserved-content restrictions remain visible

#### Scenario: Developer supplies a goal without reference media
- **WHEN** the developer describes a concrete expression problem
- **THEN** the lab can propose criteria and begin an explicit experiment without inventing a viewed reference

### Requirement: Goal-specific observable criteria drive comparison
Before exploration, the system SHALL freeze developer-supplied observable criteria or let the Agent propose and record a small set tied to the intended understanding result, including process and causality where applicable. Empty criteria SHALL NOT introduce a mandatory human-confirmation pause. A fresh rebuild SHALL define criteria for its current goal and confirmed problems rather than require unchanged historical criteria. The developer SHALL be able to adjust them. Criteria SHALL have versions and SHALL distinguish technical validity, expressive achievement, comparative improvement, transfer evidence and human acceptance. Original and candidate comparisons SHALL bind comparable goals and conditions; a new input SHALL NOT silently substitute for improving the original passage.

#### Scenario: Improve cohort filtering
- **WHEN** the goal is to make a selection process understandable
- **THEN** criteria can address trackable identities, visible removal reasons and a perceivable causal link between the retained group and statistics
- **AND** readable output or successful rendering alone does not establish that these goals were achieved

#### Scenario: Criteria or task conditions change
- **WHEN** the developer changes the expression goal or a material task condition
- **THEN** the system records the new criteria or transfer role rather than claiming a directly comparable improvement under the old goal

### Requirement: Experimental commissions support bounded autonomous exploration and later continuation
A commission SHALL have an explicit goal, starting versions and feedback where applicable, finite execution bounds, immutable candidates and recoverable task identities. Within that commission an Agent MAY autonomously explore, review and revise across multiple rounds without per-round developer confirmation. It SHALL stop when the objective is met, the budget is exhausted, cancellation or failure requires stopping, or materially different attempts yield no observable progress. It SHALL present the best available candidate with comparative evidence, unresolved problems, actual attempts and stop reason. A stopped commission SHALL NOT permanently disable further work on the effect or method, and SHALL NOT automatically start a new commission or reset spent work.

#### Scenario: Exploration stalls before its budget is exhausted
- **WHEN** multiple meaningfully different attempts produce no demonstrated improvement
- **THEN** the commission may stop early and explain its best candidate, remaining issues and evidence for stopping
- **AND** the developer can explicitly continue from the selected version in a later commission

#### Scenario: Refresh or unknown submission occurs
- **WHEN** a commission is reopened or an external submission acknowledgement is unknown
- **THEN** the original tasks and reserved budget are reconciled without duplicate generation
- **AND** the finished-video owner-round quota is neither consumed nor imposed on the commission

### Requirement: Motion and sound evaluation use applicable observed evidence
An independent shared-Agent reviewer SHALL assess applicable criteria and original/candidate comparisons using actual rendered temporal evidence and any sound required by the objective. Findings SHALL bind versions, criteria, intervals, observation evidence, proposed changes and uncertainty. Source assertions or static-frame checks SHALL NOT establish continuous motion, rhythm, audio quality or audiovisual coordination. Unsupported or insufficient observation SHALL remain incomplete; actual human viewing/listening SHALL be a separate evidence record rather than fabricated Agent observation.

#### Scenario: Reviewer receives only sampled stills for an audiovisual goal
- **WHEN** supplied evidence lacks the necessary movement or sound
- **THEN** the result identifies the unsupported criteria and observation limitations
- **AND** it does not mark the full audiovisual review complete

#### Scenario: A new candidate fixes one issue and introduces another
- **WHEN** comparison detects a regression under an unchanged criterion
- **THEN** the report retains both outcomes and does not automatically select the latest candidate as best

### Requirement: Focused refinement precedes milestone transfer checks
The lab SHALL support deep refinement of a representative complete passage before milestone evaluation on a small budget-appropriate set of materially different tasks. Transfer SHALL change relevant structure, explanation problem, staging, timing or other substantive conditions rather than only labels. Transfer failures SHALL inform method revisions followed by checks of the original, failed and affected cases. Broader validation before claiming verified reusable improvement SHALL match the scope of changed methods; every exploration round SHALL NOT require regenerating the entire library. Whole-library compilation SHALL preserve unverified scope and observed failures as limitations rather than requiring new animation generation or a separate human acceptance as a publication gate.

#### Scenario: A method works on the reference but fails on a changed relationship structure
- **WHEN** transfer reveals that the method depends on the original arrangement
- **THEN** the Agent revises the method or narrows its applicability and tests the affected evidence
- **AND** it does not merely patch a second sample while claiming the general method improved

### Requirement: Explicit whole-library publication generates the production WikiSkill
The system SHALL publish a whole WikiSkill only after an explicit developer request freezes the current effect-library evidence and an Agent generates and validates a complete self-contained version. It SHALL NOT require separate per-method human acceptance or a second content approval for this workflow, and SHALL NOT fabricate legacy demonstration or transfer acceptances.

#### Scenario: The developer requests publication
- **WHEN** the developer clicks publish
- **THEN** one recoverable job SHALL freeze evidence, generate the complete WikiSkill, validate it, and atomically activate the release only after every necessary stage succeeds
- **AND** automatic checks SHALL NOT generate new animation samples or claim unobserved aesthetic quality

#### Scenario: Generation or validation fails
- **THEN** the previous active release SHALL remain in use and the original snapshot, failure, and request identity SHALL remain recoverable without automatic replacement jobs

### Requirement: The main laboratory interface is a complete-effect gallery
The primary interface SHALL present complete playable effects with objectives, best candidates and meaningful experiment/publication state. Developers SHALL be able to submit references or goals, compare candidates, provide natural-language feedback, continue optimization, inspect transfer results and navigate from the effect context to explicit whole-library publication. Method text, diffs, source, technical regression and execution diagnostics SHALL be available as details or internal tools rather than mandatory creation steps. Feedback SHALL target the actual current candidate version. Legacy test works and annotations SHALL NOT be required migration inputs; obsolete product entries MAY be retired according to the replacement plan.

#### Scenario: Developer wants to improve an existing effect
- **WHEN** the developer opens a playable passage and describes what is unclear
- **THEN** a new explicit commission can bind that version and feedback without a manual method-text edit or engineering pull request

### Requirement: Visual creation capabilities are discoverable from demonstrated evidence
The developer-facing gallery SHALL identify and filter demonstrated visual creation capabilities including HTML/SVG, Canvas 2D, Three.js and Manim, with runtime drawing and advance production identified as execution paths. GSAP and Anime.js SHALL appear together as motion-authoring tools. Internal frozen browser engine values SHALL retain their HTML/SVG, Canvas and Three.js meaning rather than adding Manim as a fourth browser engine. Labels SHALL bind the exact representative source, runtime and applicable resource production and consumption evidence, and filters SHALL compose with text search and lifecycle state. Candidate, experiment-history and transfer views SHALL identify their own demonstrated capabilities. Missing or conflicting evidence SHALL remain unconfirmed; requested engines, method requirements, names, or other experiments in the same effect SHALL NOT establish the representative's capabilities. Filtering SHALL NOT change representative selection or create work.

The interface SHALL distinguish currently available generation engines from technologies with no demonstrated works or unavailable generation support. An engine name in a contract, a selectable empty filter, or an old fixed demonstration SHALL NOT imply that Agent-authored generation is available. Filtered counts and empty results SHALL explain the current scope and allow clearing filters. Legacy test works SHALL NOT be recreated merely to populate categories.

#### Scenario: Developer searches by rendering technology
- **WHEN** the developer selects Canvas 2D and optionally combines a text query or state
- **THEN** only effects whose current representative has consistent demonstrated Canvas evidence match
- **AND** unrelated HTML/SVG representatives remain excluded even if another historical version used Canvas
- **AND** an empty result does not start generation and clearly offers clearing filters

#### Scenario: Technology lacks consistent demonstrated evidence
- **WHEN** no completed demonstration verifies the candidate's declared engine or its source and runtime conflict
- **THEN** the interface marks the technology as unconfirmed
- **AND** method requirements and allowed engine lists do not silently supply a verified label

#### Scenario: A representative consumes a Manim resource
- **WHEN** the exact representative has verified Agent-authored Manim production and actual resource consumption in its HyperFrames project
- **THEN** its developer-visible capability labels and filters may include Manim alongside the applicable runtime drawing capability
- **AND** the internal browser engine value retains its original meaning and laboratory evidence does not imply formal production admission

### Requirement: Production consumes one published WikiSkill version per creation batch
New creation SHALL enable animation WikiSkill loading by default and allow explicit disabling through the web interface and structured API. When enabled, planning, resource creation and visual creation SHALL progressively discover and read the same immutable published WikiSkill release selected at the beginning of a creation batch. When disabled, every stage SHALL inherit the explicit disabled binding and retain platform runtime guidance without loading animation-library knowledge. Discovery SHALL NOT be replaced by a fixed lexical shortlist. Reading receipts SHALL describe actual returned bytes and SHALL NOT assert successful creative application.

#### Scenario: A new complete creation begins
- **THEN** the loading choice SHALL be frozen; if enabled, the active release or an explicitly selected release among the latest five SHALL be frozen, and if disabled, that distinct state SHALL be frozen
- **AND** adopted planning, subsequent creation and refinement SHALL retain that release even when the active pointer changes

#### Scenario: An existing project is recreated
- **THEN** a new planning batch MAY use the current release or an explicitly retained historical release, without rewriting previous runs

#### Scenario: No release exists
- **THEN** the system SHALL expose the true empty published catalogue without pretending old candidates are published

### Requirement: Reference research is internalized into self-contained skills
External reference URLs, media identity, access and observation coverage, original observations and provenance SHALL be retained in separate versioned research records linked to the experiment or method. Operational SKILL.md guidance SHALL independently explain the reusable technique; it SHALL NOT substitute a reference URL, copied transcript, storyboard or original source for its own instructions. Supporting operational demonstrations and examples SHALL be self-created and verified. Production use SHALL NOT require continued access to the original reference. Internalization SHALL mean reusable documented guidance and evidence, not an assertion of model-weight training.

#### Scenario: The original reference becomes unavailable
- **WHEN** original media and research viewing materials are removed from the creative input
- **THEN** the Agent can still understand and apply the Skill using its own guidance and verified supporting materials
- **AND** separate research provenance remains available without becoming a production runtime dependency

#### Scenario: A candidate claims reference-independent reuse
- **WHEN** verified reference-independent reuse is claimed
- **THEN** supporting evaluation includes substantively different content and structure without the original reference inputs
- **AND** merely replacing names, labels or numbers does not establish successful transfer

### Requirement: Direct sample exploration must become reusable method improvement
An experimental Agent MAY directly edit demonstration source to explore and compare alternatives. Claimed reusable improvements SHALL be distilled into a candidate Skill version and checked at representative milestones by regeneration and/or materially different content and structure. A repaired single source SHALL NOT by itself establish improved general creative capability. Failed transfer SHALL update guidance or its applicability and trigger affected-case checks rather than only another one-off source patch.

#### Scenario: A direct edit improves the representative sample
- **WHEN** an Agent produces a better sample by changing its source
- **THEN** it records the reusable decisions in candidate guidance and verifies applicable transfer before claiming verified method improvement
- **AND** unverified transfer remains an explicit limitation in the frozen evidence and does not introduce a separate per-method approval or new-sample requirement for whole-library publication
- **AND** it need not regenerate the entire library after every small edit

### Requirement: Laboratory and production share resource-making foundations
Laboratory effects SHALL use the same admitted producer interfaces, resource identities, dependency execution and basic verification foundations as formal production when advance-produced content is required. Generated HTML/SVG, Canvas2D and Three.js source SHALL remain available for runtime drawing under HyperFrames rather than being forced through offline prerendering. Shared resource mechanisms SHALL remain internal to video-service for this scope. Laboratory goals, explicit commission budgets, continued developer optimization and acceptance/publication rules SHALL remain distinct from finished-video workflows. New formal content with animation knowledge enabled SHALL be authored using applicable published guidance rather than requiring reuse of a laboratory's generated frames or clip. Disabling that knowledge SHALL retain the same resource and HyperFrames runtime contracts.

#### Scenario: A laboratory effect needs a Manim resource
- **WHEN** an Agent explores a complete effect using admitted Manim and optional sound effects
- **THEN** it uses the common resource-producing and verification interfaces before composing the laboratory HyperFrames project
- **AND** it need not execute a whole-film workflow, generate narration or consume finished-video polishing allowances

#### Scenario: A published whole-library release becomes production-available
- **WHEN** the developer explicitly requests whole-library publication and the complete generated WikiSkill passes its automatic release checks
- **THEN** a subsequent formal creation batch may select that exact immutable release and progressively read its guidance while creating new content through the same admitted resource foundations
- **AND** publication does not fabricate representative, structural-transfer or human acceptance, and does not alter an existing frozen production input

### Requirement: Effect and experiment removal is recoverable and version-bound
The laboratory SHALL let the authenticated owner move an individual experimental commission or an entire effect into a recycle bin and restore it. Whole-effect deletion SHALL bind its exact member snapshot. Removing a representative commission SHALL retain the stable effect identity and elect a remaining visible representative. Restoring a whole-effect entry SHALL NOT restore commissions independently deleted earlier or legacy hidden failed attempts. Destructive actions SHALL require explicit scope confirmation, server-side ownership and current-version eligibility, and idempotent request identities. Stale snapshots SHALL be rejected rather than broadening the deletion set.

Published versions and evidence referenced by formal production SHALL be protected. Active operations, unknown submissions, and operations without proven termination SHALL prevent deletion. Conflicting lifecycle mutations SHALL coordinate with deletion to prevent a check/use race. Soft deletion SHALL NOT cancel work, modify immutable frozen records, reset budgets, unpublish methods, or physically reclaim artifacts. Backend reads and mutations SHALL enforce the visibility boundary in addition to the user interface. Business recycle-bin behavior SHALL remain distinct from shared-platform storage reclamation.

#### Scenario: Delete one experiment while retaining another sample
- **WHEN** the owner deletes an eligible commission in a multi-experiment effect
- **THEN** its siblings and their playable samples remain visible under the same effect identity
- **AND** its own frozen history and consumed budget remain intact and restorable

#### Scenario: Restore an effect after an earlier individual deletion
- **WHEN** an individual experiment was independently deleted before the remaining effect was deleted
- **THEN** restoring the effect restores only the members affected by that effect deletion
- **AND** the earlier individual deletion and legacy failed-attempt tombstones remain effective

#### Scenario: Deletion would affect protected or unfinished work
- **WHEN** an object is published, formally referenced, active, uncertain, or lacks termination proof
- **THEN** the service rejects deletion and explains the restriction
- **AND** neither a stale page, concurrent publication nor repeated requests bypass the protection

#### Scenario: Verify termination of historical Agent work
- **WHEN** an eligible effect contains work admitted under a prior protocol or caller identity
- **THEN** stop verification uses that operation's frozen protocol through the current unified caller after an audited ownership migration
- **AND** authentic stopped `needs_input` or `timed_out` Agent outcomes are accepted only with their bound termination proof
- **AND** a missing job, active state, identity mismatch or unproven stop still rejects deletion without submitting or cancelling work

### Requirement: Unify historical task access without rewriting execution provenance
Historical laboratory jobs, including hidden and recycled work, SHALL be transferable once to the current Agent caller together with their owned inputs and checkpoints. Migration SHALL bind an inspected plan and backup, validate termination, ownership closure and destination idempotency uniqueness, and update ownership atomically. Job identifiers, original profiles and requests, idempotency keys, content hashes, execution pins, stop receipts and consumed budgets SHALL remain unchanged. The current credential SHALL read migrated historical jobs; legacy profiles SHALL NOT gain new execution admission. Following verified migration, the laboratory SHALL remove its legacy caller credential configuration and runtime wiring.

#### Scenario: Complete the caller cutover
- **WHEN** all historical ownership has migrated under the exact inspected plan
- **THEN** the current caller reads the same jobs, inputs and artifacts with their original proofs
- **AND** legacy caller configuration and mounts are removed while hidden, recycled, published and visible business records retain their identities

### Requirement: External Agents can commission through the existing authenticated HTTP interface
The laboratory SHALL expose a documented, machine-readable HTTP contract for structured creation goals, criteria, duration, budget and continuation relationships. HTTP submissions SHALL use the same owner-scoped commission, rendering, feedback and media records as the developer gallery. Explicit request identities SHALL retain idempotency and unknown acknowledgements SHALL NOT cause automatic resubmission under a new identity. Read requests SHALL NOT initiate execution. API transport SHALL NOT fabricate developer sample acceptance, transfer acceptance or Skill publication.

The initial integration SHALL retain the existing OAuth session, developer allowlist, exact write Origin and CSRF boundary. A caller-provided session file MAY be consumed by a standalone client without operating the form. The client SHALL NOT extract browser credentials, follow authentication or cross-origin redirects with credentials, forge owner headers or expose internal executor credentials. Independent Bearer credentials and browser-free authorization SHALL remain explicitly unsupported until separately implemented and verified. The guide, OpenAPI contract and client download SHALL retain the same developer authorization boundary.

#### Scenario: An external harness submits a structured goal
- **WHEN** an authorized developer session submits a documented JSON goal with an explicit request_id and budget
- **THEN** the existing API returns the durable commission identity asynchronously and the same experiment appears in the gallery
- **AND** the harness can read status, media and source and explicitly continue with bound feedback without filling a browser form

#### Scenario: A submission acknowledgement is lost
- **WHEN** the HTTP client cannot determine whether a creation POST was accepted
- **THEN** it reports an uncertain outcome and preserves the original request_id for catalogue reconciliation or explicit identical replay
- **AND** it does not automatically submit a new paid experiment or count a read as execution

#### Scenario: Login is expired or an unauthorized path is requested
- **WHEN** a session is absent, expired, outside the developer allowlist or redirected to login
- **THEN** the existing identity boundary or client rejects the call and no worker is scheduled
- **AND** the client does not leak session material to a redirect target or substitute an internal service token

### Requirement: Explicitly authorized permanent cleanup is separate from soft deletion
An owner's explicit permanent-cleanup instruction MAY be performed as a scoped operational procedure, without changing the default recoverable deletion behavior. It SHALL bind exact recycled entries, immutable member identities and a checked resource closure. It SHALL reject active or unproven work, preserve resources referenced outside that closure, and remove business content and recycle-bin dependencies consistently. Other visible effects, legacy hidden attempts, published knowledge and formal production SHALL remain intact.

Necessary usage, consumed budgets, idempotency reservations, original request hashes and stop/cleanup evidence SHALL remain. Content-bearing results for exclusively removed work SHALL be replaced by minimal identifiers, hashes and a purged status rather than releasing request identities. Shared-framework resource release and deletion SHALL enforce retention references; cleanup SHALL NOT resubmit jobs or claim a general permanent-delete UI exists.

#### Scenario: Permanently clear the four explicitly selected recycle-bin entries
- **WHEN** the owner explicitly requests permanent removal of the current four recycled entries
- **THEN** the procedure removes only their verified exclusive content and original recycle-bin dependencies
- **AND** exact request replay cannot recreate content or consume a fresh budget, while remaining effects and samples retain their identities and media

### Requirement: Separate page navigation from progress and experiment creation
The laboratory SHALL distinguish navigation between the effect library and the knowledge library from task-progress reads and new-experiment creation. The knowledge page SHALL be named 知识库 and use the common laboratory page shell and navigation style. Existing automatic polling and explicit refresh SHALL remain read-only and accessible during detail, form and recycle-bin views. Navigation and actions SHALL remain usable on narrow screens. Changing the page shell SHALL NOT imply that whole-library release management or full-text search has been implemented.

#### Scenario: Inspect progress and open a new experiment
- **WHEN** a developer uses the separated progress control or new-experiment action
- **THEN** progress reads do not submit work, and opening the creation form does not itself commission an experiment
- **AND** existing pending-request and recycle-bin reconciliation retain their original behavior

### Requirement: Effect-library evidence is the source for generated WikiSkill
The system SHALL preserve real effect requirements, source and result identities, feedback, withdrawals, failures and observed limitations as evidence. All such current records MAY inform publication; unsupported hypotheses SHALL NOT become established capabilities. Human changes SHALL be made through effect feedback and optimization rather than editing knowledge fields.

#### Scenario: A failed attempt provides a useful counterexample
- **THEN** the generating Agent MAY cite the observed failure and its limits without claiming the proposed fix succeeded

#### Scenario: An effect changes or is removed
- **THEN** the next release SHALL derive from the new snapshot and SHALL NOT unconditionally inherit unsupported content that exists only in a previous release

### Requirement: Browsing and production use the same published WikiSkill artifact
The knowledge page SHALL browse the exact immutable WikiSkill packages used by formal production. There SHALL NOT be a separate browsing release line. One explicit publish request SHALL trigger snapshot, Agent generation, validation and activation. Reads, searches, refreshes and experiment completion SHALL NOT publish.

#### Scenario: A publication acknowledgement is lost
- **THEN** the client SHALL query the original request and SHALL NOT automatically create a different request or rerun the generating Agent

#### Scenario: Evidence changes while generation runs
- **THEN** the job SHALL continue using its original immutable snapshot and later changes SHALL wait for a subsequent explicit publication

### Requirement: Retain five published WikiSkill versions for browsing, selection and activation
The system SHALL expose the latest five successful complete WikiSkill releases for browsing, explicit historical creation and restoring the active default. Failed jobs SHALL NOT count as releases. Restoration SHALL NOT regenerate skills and SHALL NOT alter in-progress creation batches.

#### Scenario: A sixth version is published
- **THEN** the oldest version SHALL leave new-selection browsing while exact artifacts required by existing frozen tasks and acknowledgement recovery SHALL remain available to those tasks

#### Scenario: The developer restores a retained version
- **THEN** subsequent default creation batches SHALL use that version and previous batches SHALL remain unchanged

### Requirement: Knowledge search and reading stay inside the selected WikiSkill release
The searchable bodies SHALL be the actual SKILL.md and subordinate files from the selected published packages, including applicability, limitations and counterexamples; directory-title-only filtering SHALL NOT satisfy this requirement.
The knowledge interface SHALL provide read-only browsing and full-text search of the selected release's knowledge bodies, applicability, limitations, counterexamples and associated knowledge. Search results and subsequent reads SHALL bind the same exact release and SHALL NOT mix current working Wiki, another release or historical task-only material. Catalogue-title or serialized metadata filtering alone SHALL NOT count as body full-text search. Source evidence SHALL state its actual observation limits and SHALL NOT invent playable media relationships. Reading, selecting a version, searching and refreshing SHALL NOT initiate model, audio or render work.

Successful whole-library publication SHALL make that exact immutable WikiSkill release available to subsequent production batches, and explicit activation of a retained release SHALL set the default for subsequent batches. Publication and activation SHALL NOT mutate any previously published package or existing task catalogue freeze, and SHALL NOT fabricate demonstration, transfer or human acceptance. This workflow SHALL NOT require a second per-method publication, representative acceptance or structural-transfer acceptance gate; experimental claims of verified quality or transfer SHALL continue to state their actual supporting evidence and limitations.

#### Scenario: A developer searches an older selectable release
- **WHEN** the developer selects that release and searches a phrase present only in a knowledge body
- **THEN** the body match and its exact released page are readable within that release
- **AND** later working Wiki edits do not alter those results or silently switch formal-production knowledge

#### Scenario: No library release exists
- **WHEN** the developer opens the knowledge library before its first explicit release
- **THEN** the interface explains that no published version is available
- **AND** it does not create a release, start an Agent or substitute an unannounced live-Wiki version


### Requirement: Bounded collaboration for complex effect authorship

The service SHALL offer an explicit, independently admitted collaboration mode in which a director Agent plans two to four creative responsibilities, component Agents receive only a scoped agreement and direct dependencies, and an integration Agent authors the complete final source consumed by HyperFrames. The host SHALL preserve one commission deadline, durable operation budgets and original submission identities, run at most two components concurrently, and create only one final candidate per initial collaborative commission. Collaboration scheduling SHALL be independent of drawing technology. The video adapter SHALL preserve the task-frozen admitted HTML/SVG, Canvas or Three.js engine set and require the plan, components, final source and reusable Skill dependencies to agree. Support SHALL NOT imply Manim preproduction or transfer support.

#### Scenario: A developer explicitly requests collaborative Canvas creation
- **WHEN** an admitted caller creates a one-round commission with collaboration.max_components between two and four
- **THEN** the service reserves at most N+2 creator operations, one final render and one review, displays actual phase and operation-budget progress, and leaves ordinary experiments unchanged.

#### Scenario: A component submission is uncertain or cancellation is requested
- **WHEN** a component acknowledgment is lost or a collaborative commission must stop
- **THEN** the service reconciles the original operation and drains every active sibling before declaring a terminal commission, without replacement submissions or new budgets.

#### Scenario: Planning lists keyframe times without a rendered preview
- **WHEN** the director proposes keyframe_times but no prior preview was rendered and checked
- **THEN** the service records those times as planning data and SHALL NOT claim that a prior visual gate, complete motion inspection, developer approval or Skill publication has occurred.

### Requirement: Evidence-aware creative improvement and candidate selection

New collaborative commissions SHALL freeze bounded creative direction before paid operations. The director SHALL prioritize the actual expressive signature, coherent materials, shared interfaces and goal-specific responsibilities rather than a fixed object-per-agent split. Supplied developer opinions SHALL remain verbatim with source scope; omitted context SHALL be disclosed rather than silently clipped.

Automatic selection SHALL retain the original model assessment separately from the host decision. When a technically usable comparison baseline exists, any explicitly failed frozen criterion SHALL veto automatic promotion of the new candidate. Insufficient evidence SHALL NOT mean failed quality, but SHALL prevent a claim of goal completion. Unobserved motion or audio requirements SHALL remain incomplete in method validation. Exact-pair developer preferences SHALL be frozen with a subsequent review input; recording feedback alone SHALL NOT select, accept, publish or rewrite a historical sample.

#### Scenario: Clearer composition loses the requested material language
- **WHEN** a new candidate has an explicitly failed expression criterion despite a positive model recommendation
- **THEN** the host retains the usable baseline, preserves the model result and records the veto reason without claiming the new candidate met its goal.

#### Scenario: Only sampled images were observed
- **WHEN** continuous movement or audio has not been observed
- **THEN** the review does not treat that absence as a proved visual regression, and does not certify the corresponding method standard as passed.

### Requirement: Laboratory tool selection is explicit and independent of production user choices
The developer form and structured HTTP creation contract SHALL expose the same optional capability_selection with creation values html-svg, canvas, three, manim and motion values native-js, gsap, animejs. An omitted or empty group SHALL delegate selection to the Agent, except that a Manim-only creation selection SHALL use Manim native animation with no browser motion choice. A nonempty group SHALL bound the capabilities the Agent may choose or combine; a single value SHALL require substantive use. The host SHALL freeze authoritative admission and dependencies, reject unsupported values or client-supplied runtime evidence, and preserve selections through continuation and retry. Requested choices SHALL NOT establish observed capability labels or artistic acceptance. Ordinary production SHALL continue choosing tools through its Agent and frozen WikiSkill without requiring end-user technical selections.

#### Scenario: An external Agent requests an Anime.js experiment
- **WHEN** its valid structured request specifies creation canvas and motion animejs
- **THEN** the same owner-scoped experiment constrains authored drawing to Canvas and requires substantive local Anime.js use with source-bound render evidence; merely loading the library or silently substituting GSAP does not satisfy the request

#### Scenario: A developer reopens a completed or failed experiment
- **WHEN** they open continuation or retry
- **THEN** the form restores both capability groups and the exact bounded Manim duration, and no model or render starts before explicit submission

### Requirement: Manim experiments iterate their own authored resource
Manim SHALL be a peer laboratory drawing capability rather than only an immutable supplied asset. Ordinary inherited continuations SHALL provide the owned exact previous Python recipe, strategy, criteria, review and developer feedback where present to a new recipe Agent. Fresh rebuilds SHALL instead follow fresh-authoring isolation and SHALL NOT inherit previous Python, layout, dedicated methods or resource recipes merely because the effect identity is retained. Later exploration rounds SHALL produce independent resources under stable round identities and the existing commission deadline and budget; cancellation and recovery SHALL retain original operations. Oversized context SHALL be rejected before reserving new resource work rather than truncating source or feedback. Manim-only selections SHALL use the real resource for primary geometry and native Manim animation. For new requests whose candidate creation range includes Manim, the existing planning operation SHALL complete before resource reservation or recipe/Cairo execution. The host SHALL derive and immutably bind the adopted drawing engine and producer dependency to the original completed plan identity and result digest. A mixed selection SHALL NOT require every candidate; if Manim is not adopted, no Manim task SHALL be reserved or submitted, resource progress SHALL say not_adopted with zero attempts (or not_started when the commission ends before a plan is adopted), and methods SHALL NOT retain an unused producer dependency. If Manim is adopted, the host SHALL produce and consume the real resource within the original budget and deadline. Manim-only forms SHALL clear and disable browser motion choices, and new API requests SHALL reject nonempty browser motion choices for that selection. For mixed selections, applicable browser motion choices remain an allowed range rather than proof of actual library use; a pure Manim adoption SHALL clear that range and SHALL NOT add unrelated decoration to satisfy it. Necessary HTML/SVG carriers MAY accompany adopted Manim but SHALL NOT replace its primary geometry or bypass a browser-only selection. Existing immutable historical requests SHALL retain their original input and execution identity.

#### Scenario: The review asks to improve a Manim transformation
- **WHEN** another bounded round is permitted
- **THEN** a newly authored Manim recipe receives exact prior source and actual feedback, creates a distinct resource, and leaves earlier resources and evidence unchanged; editing the HTML wrapper alone does not establish Manim improvement

#### Scenario: Collaboration cannot produce Manim resources
- **WHEN** a request combines collaboration with Manim preproduction
- **THEN** the request is refused before execution and the UI explains the real limitation, while admitted HTML/SVG, Canvas and Three.js collaboration remains selectable


#### Scenario: A mixed selection chooses Canvas without Manim
- **WHEN** a new or continued experiment permits Canvas and Manim but its existing plan chooses a Canvas method without a producer dependency
- **THEN** the host freezes that decision, starts no Manim resource stage, recipe or Cairo, and authors the Canvas candidate using the applicable browser motion range
- **AND** continuing an earlier Canvas-only effect does not require a nonexistent previous Manim descriptor

#### Scenario: Only Manim is selected
- **WHEN** the developer selects only Manim
- **THEN** the form clears and disables browser motion choices and states that Manim orchestrates its own animation
- **AND** the corresponding new JSON request accepts empty or omitted motion but rejects a nonempty browser motion list

#### Scenario: Transfer planning returns an empty method list
- **WHEN** the frozen transfer protocol requires result.methods to be empty
- **THEN** resource adoption is derived from the exact frozen plan input methods rather than the empty output list, without a new model role or an additional planning operation

#### Scenario: A request stops before resource adoption
- **WHEN** cancellation or the original deadline occurs before a completed plan is adopted
- **THEN** no new resource task is reserved, the original operation is reconciled, and retry or recovery does not rewrite the immutable request identity or reset its budget


### Requirement: Inspect submitted requirements and exact per-operation authoring inputs
The developer detail SHALL provide separate, initially collapsed views for the commission submission and its main Agent operation inputs. New commissions SHALL preserve the first structured submission outside the immutable normalized execution identity. Historical commissions without that snapshot SHALL expose an explicitly labeled reconstruction from public frozen requirement fields and SHALL NOT be backfilled or claimed to contain an original form. Effective frozen requirements SHALL be distinct from the submission, including inherited defaults where applicable.

Operation indexes SHALL identify planning, authoring, independent review and collaborative Agent inputs by the original operation, mode or phase, round, candidate association and input digest. Complete input documents SHALL be read lazily from the actual frozen operation, preserving their exact canonical semantics and digest. Ordinary detail polling SHALL NOT embed all full inputs. The view SHALL support readable requirement text, copying and JSON export with bounded caches and response sizes.

The system SHALL NOT claim a current profile reconstruction is the historical system prompt, a business input is the complete model message trace, a source download is a prompt, or the main commission ledger includes separately stored resource producer tasks. Such observation limits SHALL be visible. Every read SHALL enforce the existing developer authentication, owner and commission visibility boundaries, including removed records, and SHALL NOT submit, advance, retry or render work.

#### Scenario: A developer inspects an older successful ink effect
- **WHEN** they expand submitted requirements and choose an actual authoring operation
- **THEN** the historical submission is labeled as reconstructed if no original exists, and the operation view shows its exact stored goal, feedback, criteria, methods and frozen context rather than inventing a new combined prompt
- **AND** copying or exporting it does not start a new experiment

#### Scenario: A detail switches while an input read is pending
- **WHEN** the read for an earlier commission completes after another experiment is selected
- **THEN** the earlier input does not replace or appear inside the new commission detail

#### Scenario: Public transport contains absolute or nested URLs in an input
- **WHEN** the public laboratory proxies a stored input
- **THEN** it preserves the frozen input body and digest and only adapts the index link used to request it

#### Scenario: A request replays an existing commission
- **WHEN** the same accepted identity is replayed
- **THEN** the first submission remains unchanged and an older commission without a snapshot is not silently backfilled


### Requirement: Effect ownership and authoring inheritance are independent
The system SHALL distinguish a stable effect identity, a new commission, authoring inheritance and technical retry lineage. A fresh rebuild SHALL remain under the selected owned effect without initializing the new creation from its old candidate, source, layout, dedicated methods, resource recipes or collaboration responsibilities. It MAY receive the current goal, explicit constraints and a concise problem summary grounded in developer statements or reliable observations. The summary SHALL retain provenance and observation limits; hypotheses SHALL remain checks rather than mandatory facts. This isolation SHALL apply to planning, ordinary authors, collaborative components, integration and resource recipe Agents, including indirect baseline fallbacks and readable task attachments. Historical artifacts SHALL remain available for later comparison without becoming fresh-authoring input. Generic animation knowledge independently enabled by the developer SHALL follow the frozen knowledge policy.

#### Scenario: Rebuild an existing ink-animation effect
- **WHEN** a developer starts a fresh rebuild under the existing owned effect
- **THEN** the new commission retains that effect identity and current goal, freezes its new criteria and concise reliable problems, and does not supply old implementation or responsibilities to its creation roles
- **AND** the old media and history remain preserved for comparison after the new work exists

#### Scenario: New criteria are omitted
- **WHEN** the developer submits a fresh rebuild without explicit criteria
- **THEN** the Agent proposes and records current goal-specific criteria before authoring and proceeds without a required second human confirmation
- **AND** changed goals or criteria are identified in comparison evidence rather than represented as unchanged-condition improvement

### Requirement: Fresh rebuild results require explicit default-work adoption
A fresh rebuild SHALL save its completed work as an immutable candidate under the original effect and SHALL NOT replace the effect gallery's current default work on completion, internal best selection, failure recovery or refresh. The developer SHALL be able to compare and explicitly adopt an owned valid candidate with version-bound concurrency checks. Internal commission best selection, default-work adoption, aesthetic acceptance and WikiSkill publication SHALL remain distinct. Capability labels and filters SHALL follow the exact adopted representative's source and runtime evidence, while candidate history retains its own evidence. New effects without a previous representative MAY display their first work under their creation workflow.

#### Scenario: A fresh candidate is completed
- **WHEN** a fresh rebuild produces a valid candidate
- **THEN** the previous gallery default remains unchanged and the new candidate is available for comparison and explicit adoption
- **AND** no WikiSkill release or human acceptance is created by completing or adopting the candidate

#### Scenario: A stale page attempts to adopt a candidate
- **WHEN** ownership or the expected current representative does not match
- **THEN** adoption is rejected without silently changing the representative or publishing knowledge

### Requirement: Every creation freezes an explicit animation-knowledge loading policy
New laboratory experiments, continuations, fresh rebuilds and formal production batches SHALL default to enabling animation WikiSkill and SHALL allow explicit disabling through equivalent web and structured API controls. The choice SHALL be independent of authoring mode, drawing capabilities and collaboration. Enabled new creation SHALL bind an exact published whole-library version. The laboratory SHALL freeze that release's complete SKILL.md and attachment bodies as bounded inline input with explicit published-release-inline provenance, rather than claim on-demand tool reading. Oversized content SHALL be rejected explicitly, without silent truncation or mutable-Wiki fallback. Formal production SHALL retain catalogue, search and on-demand read tools for the same frozen release. Delivery of inline bytes SHALL NOT be recorded as model reading or successful creative application. The laboratory SHALL NOT silently refresh mutable working-Wiki pages or experiences between planning and creation. Existing historical snapshots SHALL retain their actual provenance and SHALL NOT be relabeled as published releases. No available release, an enabled empty catalogue and explicit disabling SHALL be distinguishable. Disabled creation SHALL retain platform interfaces, admitted tools, HyperFrames clock and resource contracts, while excluding animation-library guidance through default methods, working-Wiki injection, search/read tools and child tasks. Registered formal discovery tools MAY remain available with an actually empty catalogue and no knowledge packages; their presence SHALL NOT imply knowledge was provided. Persisting new experimental facts SHALL remain allowed. Ordinary continuation may retain its explicitly selected old work and SHALL NOT claim that disabling knowledge erased methods already embodied in that source.

#### Scenario: A new creation omits the loading choice
- **WHEN** an experiment or formal batch starts without an explicit choice
- **THEN** loading is enabled by default, including for fresh rebuilds, and the exact available release or true empty state is frozen and recorded

#### Scenario: An external Agent disables animation knowledge
- **WHEN** a structured request explicitly disables loading
- **THEN** all applicable authoring and resource roles retain that disabled policy, receive platform runtime instructions and cannot recover animation knowledge through hidden snapshot or tool fallbacks
- **AND** the submitted request and effective-input view expose the real choice without starting additional work

#### Scenario: A release changes during creation
- **WHEN** a newer release is published or the default pointer changes
- **THEN** the in-progress commission or production batch retains its original enabled release, empty state or disabled binding through downstream work and technical retry

### Requirement: Technical retry preserves the creative contract and completed plan
A technical retry SHALL retain the original goal, criteria, explicit capability constraints, knowledge policy and exact binding, completed creative plan and responsibility interfaces. It SHALL recover or repair the failed stage and reuse valid completed outputs rather than silently replan the creative direction. Changed goals, criteria, knowledge choices or creative direction SHALL use a new continuation or fresh experiment rather than mutate an original request identity. Unknown submissions SHALL reconcile the original operation. Prior spending, failed attempts and real stop evidence SHALL remain recorded; additional required attempts SHALL consume an explicit bounded budget rather than erase prior work. Developer laboratory budgets SHALL remain independent of formal-video polishing allowances.

#### Scenario: Integration fails after collaborative planning and components succeed
- **WHEN** the developer requests technical retry
- **THEN** the original requirements, criteria, frozen knowledge, plan and usable components are retained and only necessary failed work is recovered or repaired
- **AND** the system does not ask a new planner to change responsibilities merely because a retry was requested

#### Scenario: Retry proposes a different creative direction
- **WHEN** the submitted retry changes the goal, criteria, knowledge choice or completed creative plan
- **THEN** it is rejected as a technical retry and the interface directs that intent to a new continuation or fresh experiment without rewriting the original task
