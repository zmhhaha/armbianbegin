> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/video-learning-time-budget-20261119/sdk-replay-audit.md`；正文 SHA-256：`dd3730be305e21289046d9ed2742b0269a2f1aa1b3667fd4a6e5bd6a77597d2e`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# Read-only investigation: failed video-learning author operation

Observed project: `588a5b7ef481471b950f392f85223bed`\
Observed run: `478486c62b364bd69f55c356f107effc`\
Observed operation: `478486c62b364bd69f55c356f107effc-1`\
Agent job: `8d3057d7-0076-4c36-9a1d-06875cf42491`\
Attempt: `4ef651b5-7900-4fd9-a904-bc50ce1131c4`, fence `419`.

## Established facts

- The operation failed during initial **authoring**, with `model_error`. No candidate/media or renderer operation had been created. It is not a measured Shader or frame-rendering failure.
- Agent job timeout was 600 seconds. The job failed approximately 212 seconds after creation, with approximately 388 seconds remaining before that job deadline. The enclosing experiment budget was 900 seconds. Increasing the time budget has not been established as a repair for this failure.
- Four upstream model requests were recorded complete, with HTTP 200 and completed Responses events. The last response had valid, matching function-call arguments across deltas and terminal events. These observations establish upstream completion, not successful end-to-end Pi execution.
- Exact runtime image used for the failed job and offline replay: `arm-cluster-master:5000/agent-service-pi:latest@sha256:0a334832372c20852f0b684e0d52793d51267337b05dac055a7a587e3b8a11bb`.
- Installed runtime: `@earendil-works/pi-coding-agent` 0.99.2, with `@earendil-works/pi-ai` Responses provider.
- A frozen response-only SSE fixture of 2,032,045 bytes was replayed through the installed provider's exported `stream` entry. Fixture SHA-256: `ec0010ad6b9b4c4492c86e230695580881a5a2714af5153ff0e4110d1e6efcd4`.
- Replay container used `--network none --read-only`; the immutable fixture was mounted read-only. A local fetch stub returned a `Response` made from that fixture, with a dummy API key. No real provider request, production job, model call, dependency installation, image download, or image build occurred.
- Replay succeeded in 3,509 ms: exactly one local stub fetch, 7,095 tool-call delta events, one final `done`, `stopReason=toolUse`, `write` arguments of 20,271 characters, no provider parser error.
- Static inspection of the pinned `worker-cli.mjs` found the fixed argument-validation and CLI-import wrapper. It supplies no separate per-response callback that proves this production failure's cause.

## Limits of the evidence

- The retired production worker pod and its exact log directory had already been removed; the original native error details could not be recovered there.
- The replay verifies parsing of the final response in the pinned Responses provider. It does not replay the full multi-turn conversation, Pi CLI lifecycle, tool execution, sandbox, event transport, or resource conditions of the retired worker.
- No fifth-request scope error, deterministic SDK bug, malformed final SSE, task deadline expiry, or renderer failure has been established. Do not present any of those as the root cause.
- No application source, SDK, time limit, or production record was changed by this diagnostic work. The business task was not rerun.

## Evidence

- `new-author-agent-job.json`: public job and ordered lifecycle events.
- `new-author-agent-custody.json`: submitted timeout/deadline and custody fields.
- `worker-pod-events.json`: worker scheduling and stopping events.
- `retired-worker-fixed-diagnostics.json`: absence of original log directory.
- `job-model-responses-safe.json`, `last-tool-arguments-shape-safe.json`, `completed-shape-comparison-safe.json`: upstream completion and shape checks.
- `pinned-pi-sdk-layout.json`, `pinned-cli-dependencies.json`: actual pinned module locations and CLI entry.
- `pinned-pi-offline-replay.json`: exact replay result.
- `replay_pinned_pi.py`: isolated replay command and bounded output implementation.

Investigation date: 2026-11-19.
