> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`archives/video-service/20261116/c-rendered/audio-clock/process/agent-process-deployment-plan.md`；正文 SHA-256：`5ae88689ffb61629c51b3851076d842200ea8d08115980fe5b792605876d37c9`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# Process Agent 增量发布准备（仅计划，未执行发布）

2026-11-05 只读核对：当前 `agent-service-api`、`agent-model-proxy`、`agent-service-dispatcher` 均 1 副本就绪，共用镜像：

`arm-cluster-master:5000/agent-service-control:latest@sha256:cf2f61033d5cbd9eb4036452d954afc15fb5d16ff284166163a340db0add5b21`

三项 Deployment 共挂载 `agent-service-config-263b27a275f074e5c71a`。已读取旧 `/root/video-motion-profile-overlay-prep.py` 和 `prepare_overlay_r3.py`；其模式是从线上包导出后做少量注册补丁，不用开发分支整包覆盖共享 Agent。旧 r3 特别修复了 umask 077 下 UID 10000 读不到 Docker COPY 资源的问题：公开目录 0755、文件 0644。

当前 motion Pi Worker 的实际 image digest、host ConfigMap 内容和最新注册桥内容仍需根节点导出。本准备没有查询 Secret，没有执行模型请求、probe、镜像构建或集群修改。旧生产目录中 promotion/candidate 脚本尚未完整核读，因此本文没有把它们标成已验证可直接用于 process 的发布工具。

## 最小镜像与文件变更

新建两个 Agent 镜像，都使用 `latest` 标签，发布身份记在 label、Deployment annotation 和 digest：

1. 从上述**当前 control digest** 构建 process 注册 overlay；API、proxy、dispatcher 共用新 digest。
2. 从当前已接受 motion Pi Worker 的**实际 digest** 构建独立 process Worker overlay；只给新的 process pool 使用。所有旧 profile 的 pool/image/acceptance 原样保留。

`prepare_agent_process_overlay.py` 对每个基底包独立准备新上下文，只修改 5 项：

- `profiles/__init__.py`：新增精确 `video.process-plan.v1` dispatch。
- `registry.py`：OutputSchema 新增 `video-process-plan-output.v1`。
- `resources.py`：新增 process 根目录与独立资源校验分支。
- `deploy/acceptance_probe.py`：管理员允许的 profile 新增 process；内置 fixture 范围不变。
- `deploy/candidate_scenario.py`：新增仅接收 canonical `process-input.json` 的独立分支。

新增 8 项：`profiles/video_process.py`、`profiles/video_process_contract.py`、`deploy/process_catalog.py`，以及 `video-process-v1` 下 5 项固定资源。已存在的新注册/新文件、非预期源结构、资源 hash 不符、可变基底镜像都会在写入输出前拒绝。

不覆盖线上 `catalog.py`。`prepare_agent_process_candidate.py` 在新 overlay 镜像中离线执行，从当前 public config 和实际 motion host 提取已接受的 Pi adapter/model 组合，创建**独立** process environment、未接受 binding、disabled route、未预留 UID 的独立 pool，以及只含 process 的 disabled host catalog。然后调用已测试的 `merge_process_catalog`，只给现有 video-workbench caller 追加 process 权限，保留所有旧记录及旧撤销。

## 后续执行顺序

1. 根节点冻结当前 Deployment、Pod imageID、public config、motion host config、motion Worker digest 和旧 binding fingerprints；只导出 Agent 源包/固定资源，排除 Secret、环境变量和数据库。
2. 分别对 control/Pi 导出包运行 overlay 准备脚本，审查 `registration.patch` 和 `manifest.json`。用对应镜像和其实际 Python 离线验证 import、bundle、TaskContract、现有 public catalog；验证新文件可由镜像运行 UID 读取。通过后才构建、push `latest`，记录 registry digest。
3. 在新 overlay 镜像中、网络关闭时运行 candidate 准备脚本。检查所有旧行和 acceptance 保持不变，新 environment 仅有 read/write 和 process output capability，新 pool 未启用且无 UID。检查新 public/configmap 仍符合线上 publication byte budgets。
4. **先只更新三项 control Deployment 的镜像，继续使用旧 public ConfigMap**。所有实例读取旧配置就绪后，才允许引入包含 process 的新 public config。旧 control 镜像无法识别新 handler，即使新 route 是 disabled，也不能让旧实例读它。
5. 使用独立只读场景进行管理员 candidate 验收：3 个卡片、同一个请求 token，语义 beat 绑定，draw/reveal 在 transfer 前，状态变更合法。根节点先核对旧 `agent_candidates.py` 的预算/UID/停止证明流程再复用。`acceptance_probe` 的实际执行包含一次模型连通性请求和后续 Agent tool-call 运行，离线准备本身不会触发它；预算应单独登记，不能复用旧 ledger 当作尚未消耗的新预算。
6. 验收必须核对 exact profile/revision、新 Worker digest、新 binding combination SHA、输入 SHA、结果 SHA、single process-result artifact、所有 writer 停止及 Pod 容器实际终止。候选生成只产生数据，不做 TTS、渲染、采用、发布或时序核准。再用 compiler2 校验/展示其动作计划，确认业务语义和布局。
7. 独立记录新的 `video.process-plan-contract.v1` acceptance，绑定**新 combination SHA**。旧 motion/scientific/PPT acceptance 不能替代。仅此后启用新 process route/pool，并从线上统一 UID 分配机制预留新范围；保存独立不可变 host ConfigMap。
8. 最后开启工作台 `VIDEO_PROCESS_ENABLED`。普通 diagram 继续走旧 profile；用户明确选择 process 才进入新 profile。做一笔受预算约束的工作台候选验收，核对刷新恢复、预览、明确采用、真实音频绑定与人工时序核准。业务验收是独立步骤，管理员 candidate 的成功不能自动变成业务项目采用。

回退先关闭工作台 process 新提交，保留已提交任务使用原 process gateway 对账。禁用新 route/pool 的新分配后，保留其 pinned images、host、binding、已发生任务所需资源，直到已有 writer 停止及任务收束。只要 public config 中仍有 process 数据，control 就应保留能识别它的新代码；不可单独回退旧 control 镜像。

## 可审查准备命令（不包含部署）

```sh
# --source-root 指向包含 agent_service 的已审查源码根目录。
# control/Pi 分别运行；base-dir 必须是对应实际镜像的导出包。
python prepare_agent_process_overlay.py \
  --base-dir /path/to/exported-control/agent_service \
  --source-root /path/to/reviewed/panghu_agent \
  --base-image 'arm-cluster-master:5000/agent-service-control:latest@sha256:cf2f61033d5cbd9eb4036452d954afc15fb5d16ff284166163a340db0add5b21' \
  --package-path /app/agent_service --output-dir /path/to/new-control-context

# 新 overlay 镜像中离线执行；Pi digest 必须替换为新构建推送后读取的真实值。
python prepare_agent_process_candidate.py \
  --current /public/current.json --base-host /public/motion-host.json \
  --pi-image 'registry/agent-pi:latest@sha256:<actual-new-digest>' \
  --runtime-revision '<reviewed-runtime-identity>' --output /public/new-process-candidate
```

候选准备输出：`candidate.public.json`、`merged.public.json`、`host.config.json`、`worker-host-configmap.json`、`summary.json`。仅生成可审查文件，未调用 kubectl、registry、model 或读取 Secret。

准备脚本离线覆盖 9 项全部通过：保留已有逻辑、固定新文件范围、拒绝重复/意外源结构/可变基底、保留旧接受记录、新 host 仅含 process、不复用旧 acceptance。最终完整 JUnit 为 `test-agent-process-preparation-final.xml`。Windows 深目录的第一次执行与单项路径重跑也保留为 `test-agent-process-preparation.xml` 和 `test-agent-overlay-path-retry.xml`。这些合成测试不等于实际镜像 import/UID/内核隔离或模型验收。
