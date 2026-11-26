# 模型响应等待时限部署验证（2026-11-26）

LLM 服务已将默认模型响应读取等待从 60 秒提高到 600 秒；线上七个路由原有的 60／120 秒配置均已调整到 600 秒。流式与非流式请求共用分阶段 HTTPX 时限：连接最多 10 秒、读取最多 600 秒、写入最多 60 秒、连接池等待最多 30 秒。显式配置较短 `timeout_seconds` 时，其他阶段也不会超过该值。

这些值约束每次 I/O 的空闲等待，不代表完整生成的总时限。业务任务截止时间、编译任务预算及调度租约仍独立生效。本次失败任务在模型启动前触发调度租约过期，其修复由应用仓库单独记录，不能将提高 LLM 等待时限当作该故障的直接修复证据。

## 源码与部署身份

| 内容 | 身份 |
| --- | --- |
| 保留的实际生产源码基线 | `4f1a8320ceba2e52e050495f46b30a5caeee73da` |
| LLM 等待时限代码 | `5b6661793c4ac89db4bf158936b9bae30c165abc` |
| VPS 模板读取／发送等待 | `f518b195df1ddf2dadcae31eec3090697f7d73dd` |
| LLM 滚动退出宽限清单 | `80ad447c1775e435b0e46d7a08fce2d0cae7454c` |
| 运行镜像 | `arm-cluster-master:5000/llm-service:latest@sha256:7dc5833b6ad856a82dd343952677311d69da87d1c61fc1786f953980994a803f` |
| 新路由 ConfigMap | `llm/llm-service-config-timeout-5b1ae948c677`，不可变 |
| Deployment | `llm/llm-service`，UID `d71e991d-211b-4da4-9c96-68812c01fc95` |
| 验证时 Pod | `llm-service-59f8fb776d-vg22r`，UID `4005bda5-cb3a-40ad-88d7-6662ea4dfa89` |

从确切生产基线创建干净 Git 工作树，完整构建并推送 `latest` 镜像，再按摘要部署。运行镜像八个 Python 模块逐文件哈希与构建源码、离线镜像检查一致；未修改的 Responses、历史工具调用、用量处理和 trusted 输出预算模块保持原生产内容。

路由配置沿用现场 ConfigMap 的完整数据，仅更新七个 `routes.*.timeout_seconds`。实际加载配置仍使用 `gpt-6.2-sol`，模型、上游选择、默认参数、重试次数及防护配置与原配置一致。Vault 只提供凭据和调用方令牌，本次没有修改 Vault 或 Secret。

部署使用带原 Deployment UID、resourceVersion 和完整旧 spec 校验的 JSON Patch。新清单将 `terminationGracePeriodSeconds` 从 150 秒提高到至少 660 秒，避免滚动更新先于慢模型响应硬终止进程；已有更长宽限会保留。实际 Uvicorn 版本 0.52.4，未配置 `timeout_graceful_shutdown`，其默认值为 `None`。镜像代码修订和部署配置修订分别记录，调整清单没有重建相同运行代码。

## 已完成验证

- 全套 `llm-service/tests`：161 项通过、456 个子测试通过。新增检查核对真实 HTTPX 请求携带的超时参数，覆盖流式／非流式、600 秒默认值、120 秒显式值和 2.5 秒短值。测试使用替身传输，不访问真实模型。
- 离线镜像在禁网容器中验证七个路由、阶段超时、trusted 32768 输出上限及运行模块哈希。
- 发布后读取实际 Pod：镜像摘要与目标一致，Ready 为真，重启数为 0，退出宽限为 660 秒。
- 在实际 Pod 中调用 `load_config()` 并核对应用已加载快照，七个别名均为 600 秒；真实 `_timeout()` 返回连接／读取／写入／连接池 `10/600/60/30`。
- `/health/ready` 返回 HTTP 200。验证未发起模型请求、编译任务或 WikiSkill 发布。

VPS 的 `custom-llm-proxy` 站点同步将读取和发送空闲等待从 180 秒提高到 600 秒，连接仍为 10 秒。只修改该站点的两条指令，保留其他配置。原配置检查和隔离候选配置检查通过后，执行一次平滑 reload；最终只读确认 nginx 仍 active，现场站点 SHA-256 为 `495419ccc68a082e58e84280b71f5b0e9fdcfaeb7facede64831203d0167fc62`。

## 证据及边界

本地证据目录：`D:/codex-work/operations/wikiskill-publication-failure-20261126-r2/llm-timeouts/`，包括 `tests.xml`、`server-evidence/prepare-r2/`、`final-runtime-verification.json`、`vps-applied.json`、`vps-final-verification.json` 和 `uvicorn-graceful-shutdown.json`。

服务器构建与计划目录：`/root/video-releases/llm-response-timeouts-20261126-r1/`。VPS 原配置、候选及执行收据：`/var/backups/custom-llm-timeouts-20261126-r1/`。

本次验证确认部署、实际配置和传输时限生效，没有进行真实慢模型推理或持续 600 秒的在线请求试验，也不构成 WikiSkill 编译成功或艺术效果验收。
