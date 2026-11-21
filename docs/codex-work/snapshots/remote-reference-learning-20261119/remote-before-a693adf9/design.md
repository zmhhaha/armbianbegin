> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/remote-reference-learning-20261119/remote-before.json`，JSON 字段 `/artifacts/design.md`；正文 SHA-256：`155a0c295620747d501ee9f0518901c194a8235570968deab60c6e7c51bfaf91`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# 共享远程参考读取设计

## Source and observation

Both libraries reuse POST /references. Uploaded bytes keep their current body. A remote video body uses `{request_id, source_type:"video-url", source_url}`; picture bodies also carry `timestamp_seconds` and optional normalized `crop:{x,y,width,height}`. Source rows are metadata, not uploaded media. Source URLs are original stable webpage locators; transient playback URLs and host credentials are private runtime state.

A shared host adapter provides `describe(source_url, deadline_at=None)` and `observe(source, times, crop=None, quality="overview"|"detail", deadline_at=None)`. It resolves supported providers, retrieves bounded necessary media ranges through validated transport, and returns actual frame bytes, measured PTS and quality metadata. The adapter never writes to the permanent blob store. Library services may retain only the image evidence supplied to roles and its provenance. No full reference-video blob is created.

Provider metadata identity uses `source_snapshot_sha256` with an explicit identity scope. It is distinct from `media_sha256` available for fully uploaded videos. Pixel identity is the actual image SHA-256. Address validation must cover extraction and redirects, not only the original URL; decoder network access must not create an alternative unvalidated fetch path.

## Learning lifecycle

Source registration and list/detail reads do not run models or retrieve all frames. Registration may perform bounded metadata or container-header inspection without claiming actual frame observation. The source is observed at analysis or production time. Picture learning starts with its selected frame; video learning obtains a bounded overview of the selected segment. The observed frame set is frozen for comparisons and technical retry. Deliberate later experiments may re-read the source and show changes.

Roles can request additional observations using a structured host handoff scoped to the declared reference. The role must stop before the host retrieves content; the host resumes a new role operation with actual pixel inputs, the exact request and provenance. This is a reference-read continuation inside the same round and budget. It does not falsely claim synchronous pixels or grant unrestricted browsing. Requests are bounded by per-request frame count, total observation allowance and the same overall deadline; outstanding source/model operations obey existing stop proof.

Overview and detail have separate dimensions/byte budgets. The role can request an original-region crop without re-reading every full-resolution frame. New evidence remains sampled_frames_only; no continuous playback or audio observation is implied.

## Web and API

Both forms offer video-link, upload and saved-reference sources. Picture links include source time and optional region. Video links use the existing project segment or independently budgeted source analysis. Responses show source identity and actual observed quality; an unobserved source is labelled as such. Remote source page links open the original site and never become `<video src>` values. Playback is supplied only when a valid playable resource exists. Structured JSON and pending-request recovery use the same exact source body and request ID.

## Rollout and verification

First implement and test the shared provider/transport, then source registration and real observation, then Agent observation handoffs and the two web forms. Verify measured frame timestamps, high-detail crops, cleanup on all terminal paths, source changes, private-address rejection, cross-owner isolation, unknown-outcome recovery, technical retry freezing and full existing uploaded-reference regressions. A real source read must be distinguished from an actual model creation, render, review and publication. Publish deploy images as latest with digest identity; no source read automatically starts an experiment or WikiSkill release.

## Deployment source egress

The trusted executor explicitly admits public TCP 443 for remote reference reading and controlled HTTPS DNS resolution. Private, link-local, benchmark Fake-IP and multicast destinations remain excluded. Existing DNS and internal Agent rules are retained. Scene renderers and Agent workers gain no network access. The current proxy DNS requires `--remote-reference-dns alidns`; TLS and pinned public destinations remain mandatory.
