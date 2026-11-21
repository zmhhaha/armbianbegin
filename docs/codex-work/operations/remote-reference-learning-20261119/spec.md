> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/remote-reference-learning-20261119/spec.md`；正文 SHA-256：`1c5dcb31d0f2e8614541ed9c24180c94007649b62a9249c87ce97d0346375d61`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

## ADDED Requirements

### Requirement: Shared remote video reference sources
The system SHALL allow picture and video learning to register a remote video reference by original source URL. Registration SHALL retain provider identity, available source metadata and quality provenance without storing a complete reference video or claiming media observation. Registration MAY perform bounded source metadata or container-header inspection; that operation SHALL NOT be represented as actual frame observation.

#### Scenario: Register a remote source without uploading a file
- **WHEN** a developer submits a supported HTTPS video source URL
- **THEN** the system returns an owner-scoped reference identity and metadata without requiring content_base64 or persisting complete video bytes.

### Requirement: Video-frame references for picture learning
Picture learning SHALL accept a video reference URL, a source timestamp and an optional normalized crop. The Agent SHALL author editable drawing source and the system SHALL render and compare a static image using the existing picture-learning lifecycle.

#### Scenario: Study ink texture from a reference video
- **WHEN** a developer specifies a video timestamp and a crop around a brush stroke
- **THEN** the host retrieves actual pixels for that location when needed, records the measured presentation timestamp and crop, and supplies them to picture creation and review without asserting motion verification.

### Requirement: On-demand remote observations
The system SHALL retrieve remote video content only when a registered source is inspected for analysis, creation, review or an explicit preview. Source catalogue reads and page refreshes SHALL NOT initiate media retrieval, model work or creation.

#### Scenario: Retrieve only the required reference region
- **WHEN** an experiment needs specified timestamps within its authorized reference scope
- **THEN** the host retrieves and decodes the required content from the source site, returns actual observations, and cleans up temporary media rather than materializing a permanent full-video reference.

### Requirement: Agent-directed additional observations
Creation and review roles SHALL be able to request additional reference timestamps or detail crops within the frozen source scope and remaining experiment budget. The host SHALL execute the request, preserve actual observation identity and resume the role with the retrieved pixels. Host-mediated stopped handoffs MAY be used; requesting content SHALL NOT itself count as observing it or as an optimization round.

#### Scenario: Ask to inspect a difficult material detail
- **WHEN** the Agent requests a higher-detail view of a permitted reference time and region
- **THEN** the host obtains that observation, binds it to the current run and supplies its pixels before the resumed role can cite it as evidence.

### Requirement: Observed quality and timestamps
Remote observations SHALL distinguish overview images from detail images and record actual source dimensions, delivered image dimensions, requested time, measured PTS/time base, crop and frame content digest. Detail observations SHALL NOT be unconditionally reduced to the legacy 640×480 observation ceiling.

#### Scenario: High-definition source with a detail request
- **WHEN** a supported source offers sufficient quality and the role requests a detail crop
- **THEN** the delivered frame preserves appropriate detail within the admitted image budget and reports its actual resolution rather than silently supplying a low-definition substitute.

### Requirement: Honest source identity and source change detection
The system SHALL distinguish provider metadata identity from complete media content identity. It SHALL NOT label a URL hash or provider descriptor hash as a complete video SHA-256. Changes in detectable source identity or selected quality SHALL be explicit; provider metadata identity SHALL NOT imply proof that all unobserved media bytes are unchanged.

#### Scenario: Source metadata changes between reads
- **WHEN** a fresh source resolution differs from the registered source identity or required quality
- **THEN** the system reports the detected change or quality restriction and does not silently reuse it as the same frozen observation.

### Requirement: Temporary media and experiment evidence
Remote reference media SHALL use bounded in-memory buffering or task-scoped temporary storage and SHALL be removed after use, including on timeout or failure. Only source locators, observation metadata and the bounded evidence actually supplied to the experiment MAY be retained; authored outputs and editable source SHALL continue to be preserved.

#### Scenario: Remote extraction fails or is cancelled
- **WHEN** fetching or decoding fails, reaches its deadline or is cancelled
- **THEN** all temporary resources are reclaimed and the system preserves a truthful failure record without retaining a complete reference video.

### Requirement: Scoped host access to remote content
The host SHALL restrict remote access to the registered source and supported provider/media adapters. It SHALL validate source URLs, resolved addresses, redirects, provider-resolved playback URLs and transport destinations, reject non-public destinations and unsupported protocols, and keep credentials and expiring playback URLs out of model inputs, public responses and logs.

#### Scenario: A remote URL redirects into a private network
- **WHEN** source or media resolution targets a loopback, private, reserved or otherwise unapproved destination
- **THEN** retrieval is rejected before accessing that destination.

### Requirement: Access and quality restrictions are visible
The system SHALL report supported-source limits, source availability, authentication restrictions and actual obtainable quality. It SHALL NOT bypass access restrictions or silently claim a requested quality that was not obtained.

#### Scenario: Source-site login is required for higher quality
- **WHEN** a requested source or quality is unavailable to the configured host access
- **THEN** the developer sees an actionable source/quality limitation while no credential is requested through the creative prompt or exposed to the Agent.

### Requirement: Common webpage and structured API source semantics
Both libraries and their structured APIs SHALL expose remote video sources consistently with upload and saved-reference sources. Picture references SHALL include timestamp and optional crop; video learning SHALL retain segment selection and independent source analysis. A source webpage URL SHALL NOT be used as a playable media URL.

#### Scenario: External Agent submits a link-based picture experiment
- **WHEN** an authorized external Agent posts the documented remote-reference JSON and then starts the picture experiment
- **THEN** it receives the same source identity, actual observations and lifecycle behavior as a webpage user without using browser form automation.

### Requirement: Idempotent registration and frozen technical retries
Remote registration, observation handoffs and project creation SHALL retain owner isolation, idempotent request identities, shared deadlines and stop evidence. A technical retry SHALL reuse already obtained frozen observations rather than silently fetching changed reference content. Deliberate new experiments MAY obtain new observations with explicit provenance.

#### Scenario: Recover a submission with unknown outcome
- **WHEN** the client refreshes or resends the same original request after a transport failure
- **THEN** it reconciles the existing operation without duplicating source registration, model work or learning experiments.

### Requirement: Learning and publication boundaries remain explicit
Remote reference acquisition SHALL NOT change adoption or WikiSkill publication policy. Static, sampled motion, continuous motion and audio validation SHALL remain distinct. Published techniques SHALL be self-contained and SHALL NOT depend on availability of the reference video or embed copied reference content as their own skill capability.

#### Scenario: Publish a technique learned from one video frame
- **WHEN** the developer manually publishes an accepted static technique
- **THEN** the WikiSkill retains static validation scope and an independently usable method without claiming whole-video or audio verification.
