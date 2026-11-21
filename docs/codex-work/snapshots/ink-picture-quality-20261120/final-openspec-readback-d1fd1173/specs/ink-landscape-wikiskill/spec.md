> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/ink-picture-quality-20261120/final-openspec-readback.json`，JSON 字段 `/artifacts/specs~1ink-landscape-wikiskill~1spec.md`；正文 SHA-256：`f6c03b63477280e9a07769341d36a659589d113b091ba1cff1907c3ed8c77df3`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../../../README.md)

## ADDED Requirements

### Requirement: Reusable ink library Skill
The project SHALL maintain an independently reusable ink-landscape Skill with progressively disclosed API guidance and executable examples for editable brush, texture, ink-layer and subject creation. It SHALL preserve creative choice and distinguish procedural technique approximations from artistic acceptance.

#### Scenario: Author custom rock geometry
- **WHEN** an Agent selects the ink library for a picture or video learning goal
- **THEN** the Skill explains real APIs while allowing custom paths, pressure, regions and composition, and the work retains editable source.

### Requirement: Pinned offline drawing code
The learning host SHALL supply a fixed source revision of ink-landscape as local module assets with verified hashes and license. Drawing-library dependencies SHALL be distinct from drawing engines and motion orchestration libraries. Rendering SHALL reject undeclared or changed library assets without granting network access.

#### Scenario: Import the declared local module
- **WHEN** a learning scene imports the host-declared ink-landscape entrypoint
- **THEN** the host serves the exact frozen module and records its source revision and assets, rather than requiring an online npm install or CDN.

### Requirement: Manual WikiSkill source capture
The existing developer-triggered whole-library publication SHALL capture the fixed code-library guidance and dependency identity as source records for compilation. Installation, catalogue refresh and experiment completion SHALL NOT automatically publish or modify an existing release.

#### Scenario: Prepare the next knowledge release
- **WHEN** the developer starts a new WikiSkill publication
- **THEN** its frozen records include the installed ink library guidance and dependency identity, while previous releases remain unchanged.

### Requirement: Knowledge choice and dependency compatibility
Learning SHALL preserve the selected immutable WikiSkill release and knowledge-loading policy. Disabled knowledge SHALL NOT receive the ink Skill by another route. This policy SHALL NOT remove baseline source explicitly supplied by the task. Consumers SHALL reject or exclude packages requiring unknown or unavailable drawing libraries.

#### Scenario: Learn without WikiSkill
- **WHEN** a developer disables WikiSkill for an experiment
- **THEN** the task receives no ink Skill prose while retaining the allowed runtime metadata and explicitly supplied task source.

### Requirement: Actual library consumption evidence
Implementation acceptance SHALL include actual local-module API execution and rendered still/video outputs, hash-bound to source and library revision. Module availability, loading, API use, time reproducibility and artistic quality SHALL be recorded separately.

#### Scenario: Verify a code-based learning sample
- **WHEN** a technical sample uses ink-landscape in picture and video learning renderers
- **THEN** real output and local code consumption are verified without claiming reference similarity, listening acceptance or publication of a new knowledge version.

### Requirement: Phase independent runtime API contract
Picture and video learning SHALL receive neutral API signatures and parameter constraints for the installed drawing library in stable runtime constraints, including changed-content transfer. The contract SHALL remain available when the task goal changes or WikiSkill is disabled. It SHALL describe technical types, validation limits and renderer entrypoints without injecting artistic recipes or unpublished technique Skill prose.

#### Scenario: Transfer without guessing API fields
- **WHEN** an ink-library learning experiment changes content with WikiSkill disabled
- **THEN** the author still receives valid group/stroke field structure, colour and paperTexture types, document capacity and transparent offscreen rendering constraints, and derives its own image geometry and brush arrangement.
