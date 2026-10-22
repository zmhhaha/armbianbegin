# Pi 科研 worker：部署与交接入口

独立 Pi worker、专用 caller/PVC 和配套 API/UI 已部署；CrewAI 继续作为默认后端。真实 arXiv/Crossref 研究在 API 和 worker 重启后成功发布，报告、证据附件和下载字节一致。最新测试、镜像、恢复记录与限制见 [上线记录](rollout-20261022.md)。OpenSpec 保持 active，完整验收以 [任务状态](tasks.md) 为准。

接手请先读上线记录；[implementation.md](implementation.md) 保留最初候选的实现与历史测试证据，不应把其中早期未部署状态当作当前状态。

## 阅读顺序

1. [proposal.md](proposal.md)：目标、范围、兼容策略。
2. [design.md](design.md)：首版架构与生命周期决策。
3. [contracts.md](contracts.md)：并行实现共同遵守的协议，包含精确摘要测试向量。
4. [tasks.md](tasks.md)：47 项完整验收清单、独占文件、依赖及剩余门槛。
5. [提交状态](submission.md)：本地校验和后续 OpenSpec 提交流程。

## 首版决定

专用长驻 worker + 私有 SQLite 队列/PVC，每项研究创建独立 Pi 进程、会话、HOME 和工作目录。首版并发 1。现有科研 API/UI 和 CrewAI 保留，不接管人用 Pi 网页终端。

执行产物先校验并固定，API 再向旧报告库幂等发布，验证正文后确认完成。API 重启、报告存储暂时失败都不应丢失已校验成果。进入 publishing 后不再取消成果；执行超时与报告发布恢复明确分开。

## 分配方式

| 包 | 主要工作 | 可以先开展 |
|---|---|---|
| I 集成 | 契约 schema、跨包协调、合并和最终交接 | 固定源码基线、将文档契约变成共享 schema |
| A 运行时 | Pi 非交互、模型与工具回合、取消、进程隔离 | 能力验证 |
| B worker | HTTP、队列、租约、恢复、校验和结果下载 | 用 fake Pi 实现状态机；共享 schema 固定后接协议 |
| C 科研能力 | 精选技能审查、工具、证据与 fixture | 来源/许可证/依赖审查 |
| D API/UI | 后端接入、派单恢复、报告发布、状态展示 | 旧契约回归和 fake worker；共享 schema 固定后接协议 |
| E 部署 | 独立镜像、PVC、内部服务、凭据、网络、回滚 | 部署草案，等 A/B 固定运行方式 |
| F 验收 | 兼容性、故障矩阵、科研成果与隔离 | 测试计划，待 A–E 集成后实际验证 |

建议先分配 A、C；B/D 在 I 固定共享 schema 后并行；E 与 I 协调共享构建和 manifests；F 最后验收。三个实现 agent 时可合并 A+B，另分 C、D，集成者兼 E/F。

## 校验证据

- [最终上线与验收](rollout-20261022.md)：182 项回归、7 项系统检查、真实中文网页任务及剩余 3 项验收条件。
- [最初草稿校验（历史）](local-validation.json)：当时 proposal 和 delta 严格校验均通过，0 error、0 warning，47 项待办、0 项完成。
- [固定协议向量](contract-vectors.json)：input_digest、report_sha256、result_digest 的精确输入和预期结果。
- [首次提交载荷（历史）](submission-payload.json)：协议附录内嵌 design。[最终部署载荷](rollout-submission-payload.json) 保留远端原有设计与协议，追加实际部署证据；提交证明见 [同步回执](submission.md)。

复核命令（在仓库根目录执行，使用已安装依赖，不联网安装）：

```bash
node docs/scientific-research-pi/verify-contract-vectors.mjs --check
node docs/scientific-research-pi/validate-local.mjs
```

这些校验只验证文档格式、任务计数和协议摘要，不证明 Pi runtime、模型或科研质量已通过验收。
