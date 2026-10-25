## ADDED Requirements

### Requirement: Dedicated noninteractive Pi execution
The scientific service SHALL support a Pi execution backend through a dedicated worker, while preserving the existing CrewAI backend. Each Pi attempt MUST use a separate process, session, HOME and workspace, without reusing the human Pi terminal or its persistent volumes, sessions or credentials.

#### Scenario: Explicit Pi submission
- **WHEN** an enabled Pi research job is submitted
- **THEN** the service persists its selected engine and dispatches it to the dedicated worker
- **AND** changing the default backend does not change that job's engine

#### Scenario: Pi unavailable
- **WHEN** the Pi backend is disabled or its required configuration is unavailable
- **THEN** submission fails with an actionable service-unavailable response
- **AND** the service does not silently execute the job with another backend

### Requirement: Verified runtime and model capability
The Pi worker MUST pin its runtime and skill versions and SHALL be enabled for production research only after its noninteractive protocol, structured completion, errors, tool round trip and cancellation are demonstrated with the configured model path. CLI help, an open terminal listener or unauthenticated connectivity alone MUST NOT count as execution evidence.

#### Scenario: Runtime capability gate
- **WHEN** a candidate runtime is evaluated
- **THEN** recorded evidence includes its exact version, selected invocation protocol, successful model/tool round trip and bounded cancellation
- **AND** no capability is inferred from the existing human terminal deployment

### Requirement: Durable and idempotent Pi acceptance
The dedicated worker SHALL persist accepted Pi jobs in its private durable queue before acknowledging acceptance. It MUST atomically enforce one active Pi job per trusted user, validate input digests and support replay of the same task identifier without creating duplicate execution. API dispatch intentions MUST be durable and reconciled after interrupted dispatch.

#### Scenario: Replayed dispatch
- **WHEN** dispatch of the same task identifier and input digest is repeated after a timeout
- **THEN** the worker returns the existing task
- **AND** a different digest for that identifier is rejected as a conflict

#### Scenario: Concurrent submissions
- **WHEN** two Pi jobs for the same trusted user are accepted concurrently
- **THEN** at most one becomes an active accepted job
- **AND** the other receives a defined concurrency response

### Requirement: Bounded lifecycle and recovery
The worker SHALL provide durable queued, running, validation, publication and terminal states with attempt fencing, total deadlines and bounded retry policy. API restarts MUST NOT blanket-fail Pi jobs. Cancellation and timeout MUST stop the Pi process tree and prevent stale attempts from publishing results.

#### Scenario: Restart with active task
- **WHEN** the API restarts while a Pi task runs
- **THEN** the worker task remains authoritative and queryable after reconciliation
- **AND** legacy startup cleanup does not mark it failed

#### Scenario: Interrupted worker attempt
- **WHEN** the worker restarts after an interrupted attempt
- **THEN** it fences that attempt and either starts a bounded fresh attempt or records a terminal failure according to the total deadline and retry limit
- **AND** it does not claim to resume the interrupted model session

#### Scenario: Cancellation races with completion
- **WHEN** cancellation and result completion race
- **THEN** conditional state transitions choose one consistent outcome
- **AND** a terminal task cannot be overwritten by a late attempt

### Requirement: Backward compatible research interfaces
The public scientific interfaces SHALL retain their existing paths, core response fields, report identifier semantics and Markdown downloads. Public task status MUST remain pending, running, done or failed for Pi jobs; detailed state, stage and error information SHALL be additive. Report identifiers MUST equal task identifiers.

#### Scenario: Existing client polls a cancelled task
- **WHEN** an existing client polls a cancelled or timed-out Pi task
- **THEN** it receives public status failed with an explanatory reason
- **AND** it does not wait indefinitely on an unfamiliar terminal status

#### Scenario: Existing report history and download
- **WHEN** a client lists reports and downloads an entry using its identifier
- **THEN** it receives the published Markdown using the existing endpoint semantics

### Requirement: Recoverable report publication
The service SHALL publish Pi results through a recoverable protocol: the worker commits an immutable validated result, the API idempotently saves and verifies the canonical report, and the worker accepts a matching attempt and result digest acknowledgement. Public done MUST only be exposed after this acknowledgement. Notification failures MUST NOT change successful research into failed research.

#### Scenario: Report store unavailable
- **WHEN** the canonical report store fails after Pi has produced a valid result
- **THEN** the immutable result remains pending publication
- **AND** publication retries do not rerun the research or report done before durable publication

#### Scenario: Crash before publication acknowledgement
- **WHEN** the API crashes after saving the report but before acknowledging publication
- **THEN** reconciliation verifies or repeats the same publication and acknowledges the matching result
- **AND** it does not create a second report or overwrite a different result

#### Scenario: Email failure after report completion
- **WHEN** a completion email fails after successful report publication
- **THEN** the report remains successful and downloadable
- **AND** notification status separately records failure or uncertain delivery

### Requirement: Traceable scientific artifacts
Each Pi research result SHALL include versioned search records, deduplicated paper metadata, screening decisions, evidence, claim mappings, bibliography mappings, report, validation and artifact manifest. Evidence MUST distinguish metadata-only, abstract-only and full-text access. Unknown counts and unavailable external verification MUST be represented explicitly instead of fabricated.

#### Scenario: Abstract-only evidence
- **WHEN** a paper is available only as an abstract
- **THEN** evidence records and the report disclose that limitation
- **AND** the report does not claim full-text inspection

#### Scenario: Invalid citation relationship
- **WHEN** a report references a missing bibliography item or a claim references missing evidence
- **THEN** validation rejects successful publication and records the specific inconsistency

#### Scenario: No usable literature
- **WHEN** searches yield no usable literature
- **THEN** the result may explain insufficient evidence using accurate search records
- **AND** it does not invent papers, counts or supported conclusions

### Requirement: Controlled scientific skill bundle
The worker SHALL load only reviewed scientific skills pinned to upstream revisions and hashes, preserving applicable licenses and attribution while documenting local patches and tool dependencies. Optional external SaaS MUST NOT become an undeclared default requirement. Promotional citation instructions MUST NOT automatically become scientific references.

#### Scenario: Unconfigured optional service
- **WHEN** a selected upstream skill mentions an optional external service without configured authorization
- **THEN** that integration remains disabled with an explicit capability limitation
- **AND** the worker does not request or reuse private human-agent credentials

### Requirement: Task, credential and artifact isolation
The worker SHALL authenticate internal control requests and restrict its control surface to the scientific API. Pi child processes MUST NOT receive control-plane credentials or read control storage, private human sessions or other task workspaces. Artifact downloads MUST resolve server-registered opaque identifiers and validate containment, type, size and digest. Deployment MUST enforce and test least-privilege filesystem and network boundaries.

#### Scenario: Malicious artifact path
- **WHEN** an artifact attempts path traversal, symbolic-link escape, cross-task access or an output limit violation
- **THEN** the service rejects the artifact and exposes no out-of-scope file

#### Scenario: Control credential access attempt
- **WHEN** a Pi child process attempts to read worker queue files or control credentials
- **THEN** operating-system permissions deny access
- **AND** deployment cannot pass isolation acceptance merely because the process has a different working directory

#### Scenario: Existing interactive Pi remains isolated
- **WHEN** scientific worker resources are deployed or rolled back
- **THEN** the human Pi terminal configuration, PVCs, credentials and loopback cage listener remain unchanged

### Requirement: Reproducible acceptance and parallel ownership
Implementation SHALL be divided into runtime, worker, scientific skills/tools, API/UI, deployment and integration acceptance work packages with explicit ownership and dependencies. The coordinating agent MUST own shared contracts and OpenSpec updates. Production rollout SHALL require recorded compatibility, lifecycle, publication, artifact, permission and real network tests, plus a scoped rollback plan.

#### Scenario: Parallel agents change shared contracts
- **WHEN** a work package requires a contract or shared deployment-file change
- **THEN** it submits that change through the coordinating owner before integration
- **AND** independently edited protocol copies are not treated as compatible without review

#### Scenario: Definitive dispatch rejection
- **WHEN** the worker definitively rejects a dispatch with a validation, conflict or user-concurrency response
- **THEN** the API marks its dispatch intent rejected and never automatically replays it
- **AND** an ambiguous transport failure instead preserves a recoverable task identifier for confirmation

#### Scenario: Publication commit boundary
- **WHEN** a task has entered publishing and cancellation is requested before acknowledgement
- **THEN** cancellation returns the current immutable publication state without withdrawing the result
- **AND** execution deadlines no longer terminate publication recovery

#### Scenario: Conflicting stored report
- **WHEN** publication finds an existing report with the same identifier and different exact UTF-8 content digest
- **THEN** it rejects publication without overwriting the existing content
- **AND** the operator receives a diagnostic while the result remains recoverable

#### Scenario: Mixed backend concurrency
- **WHEN** a trusted user submits one CrewAI task and one Pi task during initial rollout
- **THEN** the defined per-engine admission policy may admit both
- **AND** a second active Pi task is still rejected atomically

#### Scenario: Artifact retention expires
- **WHEN** an artifact expires after its configured retention period
- **THEN** the artifact endpoint returns gone while terminal task snapshots and idempotency bindings remain available for their longer retention period
- **AND** published report history and Markdown downloads remain supported

#### Scenario: Acceptance is incomplete
- **WHEN** any required runtime or integration gate lacks evidence
- **THEN** corresponding tasks remain incomplete
- **AND** the change is not applied or archived as fully implemented
