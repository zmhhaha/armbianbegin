> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/ink-native-drain-20261121/README.md`；正文 SHA-256：`32adcaa41992fe1d39f4513bdc37619839df05e81503a09ea1d5ead12581ba23`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../README.md)

# Native stdout drain repair operations

The sole ordinary worker build is sourced from clean reviewed commit
`e4fc65cf04397d3ab9f906adc132b9d9066c0af6`. Its pushed immutable identity is
`arm-cluster-master:5000/agent-service-pi:latest@sha256:a16cec9a04c32f2268e49d8f1cc7c407248dbaa5fd4d4ec80538a479779c2af4`.
The first postbuild file-list check used an obsolete extension name; its failure
is preserved. `finish_worker_measurement.py` independently measured the correct
files in the same pushed image without rebuilding. See `build-completed.json`.

Remote root: `/root/video-releases/ink-native-drain-20261121`.
The compiler candidate lives in `compiler-v4/candidate-wkc-drain-20261121`;
its original capture and successful disabled admission are separate directories.
The module candidate and this candidate's independent one-second media evidence
are owned by the runtime agent in `module-v2`. Old candidate outputs are not reused.

`prepare_combined_catalog.py hosts` creates only new offline enabled host and
catalog documents. `plan --module-acceptance-dir EXACT_DIRECTORY` checks both
final hosts with `accepted_host` and writes three immutable ConfigMap objects
and three exact Deployment UID/resourceVersion/spec CAS patches. Existing
control images stay pinned; only their config pointer and catalog/worker
annotations change. `apply_combined_catalog.py` requires root's explicit review
and authorization before execution. No sixth publication is started by these
operations.

For the next explicitly authorized real job, run `monitor_task_control.py` with
its exact Agent job UUID and a fresh control JSON path. In parallel run
`capture_task_diagnostics.py --control-file SAME_PATH --job-id EXACT_UUID
--image EXACT_NEW_IMAGE --output FRESH_CAPTURE_DIRECTORY`. Both paths must be
under `D:/codex-work` locally. The control reader selects only one job's compact
durable identity. The log follower waits for that exact Pod UID/image and a
running or terminated worker before attaching; it waits for startup only until
the native deadline and drains logs no later than deadline plus 45 seconds.

Filtering happens on the cluster host before SSH. Only the reviewed schemas
in `diagnostic-schema.json` for `execution_failure`, attempt-bound
`runtime_output_accounting`, and `pi_model_failure` survive. Arbitrary
stdout/stderr, extra JSON fields, native error text, prompts, source data,
credentials and model/provider property names are discarded. Safe lines are
flushed and fsynced locally as they arrive. Candidate admission's required
original private worker log remains a separate original capture.
