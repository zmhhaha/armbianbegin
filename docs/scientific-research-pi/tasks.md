# Pi 科研 worker 并行任务与交接

Change ID：`add-scientific-pi-worker`。项目：`ec663f5a-53d3-4a0e-9037-933eb788d183`。
状态更新：2026-10-22。独立 worker、专用 caller/PVC 及 API/UI 已部署，CrewAI 保持默认；显式选择 pi/brief 可运行。最终 ARM64 构建 182 项回归及 7 项系统检查全部通过，零失败、零跳过。真实来源任务、API/worker 重启恢复及最终浏览器中文任务已完成，报告/证据/下载一致。

下列勾选依据 [最终上线记录](rollout-20261022.md) 和对应回执，共 44/47 项；F4、E7、I1.2 保留未完成，不 apply/archive。F4 缺少 IPv6、metadata、人用 Pi 的可判定对照；E7 缺少全部无关工作负载的部署前后资源快照；I1.2 等待这些最终验收条件。科研结构验证不等于科学结论正确性验证。

源码已发布到 panghu_agent 的 codex/scientific-pi-worker 分支（75ee2e699c5af71a337a5434c0b554defd4dbbf8），外层记录已发布 gitlink。OpenSpec 服务为项目工件的权威来源，最新同步与校验见 [提交回执](submission.md)。历史文档中的未部署结论只描述当时阶段。

## 0. 所有 agent 先读

1. [仓库规范](../../AGENTS.md)、[项目映射](../../.openspec-project.json)、[设计与契约](design.md)。OpenSpec 使用映射项目；远端 change 成功创建后从 service 读取最新状态。当前远端 change 已存在，接手前读取最新工件和任务状态；本地文档是交接副本，不得覆盖其他 agent 的远端更新。
2. 先检查 git status、子模块分支和已有工作树；`panghu_agent` / `panghu_chat` 已有用户改动，禁止清理、覆盖或复用不明工作树。独立工作包使用独立分支/工作树，提交本包范围。
3. 文档中的新路径是所有权预留，不代表已存在。源代码实现集中在 panghu_agent，不在 panghu_chat/pi 维护第二套运行时或研究实现。
4. 接口变化交由 I 协调；所有权以本表为准。并行 agent 不直接改远端共享 design/tasks，也不自行 apply/archive。
5. 每个包交付：commit/分支、修改范围、执行命令、测试证据、未解决项；不要只报告“已完成”。实际部署由 E/I 单一执行者协调。

## 1. 分配与依赖

```text
I0 契约冻结 ─┬─ A 运行时可行性 ─┬─ B worker/持久化 ─┐
              ├─ C 技能与工具 ────┤                  │
              ├─ D API/UI（可用 fake worker） ────────┼─ F 集成验收 ─ I1 灰度/交接
              └─ E 部署草案 ─ A/B 确认后落地 ───────┘
```

| 包 | 可以立即并行做的事 | 等待项 | 独占范围 |
|---|---|---|---|
| I | 固定契约、协调和 OpenSpec | 远端登录 | 本目录、远端 change、共享契约文件 |
| A | 核实 Pi 版本/调用/技能/模型协议，写最小可行性验证 | 模型授权配置 | `panghu_agent/pi_worker/runtime/`、runtime 验证测试与报告 |
| B | 依契约实现队列/HTTP/状态机，用 fake Pi 测试 | A 的真实 Pi 适配 | `panghu_agent/pi_worker/{app,store,scheduler,artifacts,validation}.py` 等控制模块 |
| C | 精选技能审查、工具与证据 fixture | A 的技能加载方式 | `panghu_agent/scientific_skills/`、`panghu_agent/pi_worker/research_tools/` |
| D | API/UI、worker client、发布 reconciler，用 fake worker 测试 | B 真实 HTTP | API/UI 文件、`scientific_agent/pi_client.py`、`pi_projection.py` |
| E | 镜像/配置/网络/PVC 设计与渲染 | A/B 运行方式、模型协议 | 专用 Dockerfile/manifests/scripts；共享文件仅 E 修改 |
| F | 故障与兼容验收计划、集成测试 fixture | A–E 可运行版本 | 集成测试目录和最终验收报告 |

建议 3 个 agent 时：A+B 同一人，C 单独一人，D 单独一人；I 兼 E/F。人多时按表拆开。A/B 不能同时改 runtime；C 不改 API；D 不改镜像/共享 SQLite 服务。

## 2. I — 集成者、契约与 OpenSpec

- [x] I0.1 确认源码基线、已有 CrewAI 技能变更及工作树归属，记录各工作包分支；不得覆盖已经完成的 CrewAI 改进。
- [x] I0.2 冻结设计 v1：字段、状态映射、超时/重试、内部 HTTP、结果产物、发布协议、隔离门槛。
- [x] I0.3 建立 `panghu_agent/scientific_agent/pi_contracts.py` 与契约样例（唯一写入者）；其他包使用它，避免多份 schema 分叉。C 提供科研产物 schema，I 合并固定版本。
- [x] I0.4 OpenSpec 登录后读取已有 specs/changes，确认无同名 change/重复需求；创建或审慎更新本 change，validate 必须 valid=true。未实现不 apply/archive。
- [x] I1.1 依次合并包提交，检查共享依赖/锁文件/构建路径；先发布子模块 commit，再在外层更新 gitlink，不提交不可访问的子模块 SHA。
- [ ] I1.2 F 通过后记录 canary、配置切换与回滚证据，更新任务状态；有缺项明确保留未勾选。

验收：远端 proposal/design/tasks/spec 可读且校验通过；各包没有重叠写入范围，接口变更经单一作者合并，未擅自声称 Pi 可用。

## 3. A — Pi 非交互运行时验证

所有权：`panghu_agent/pi_worker/runtime/`、`panghu_agent/tests/scientific_pi/runtime/`、`panghu_agent/docs/scientific-pi-runtime-verification.md`。

- [x] A1 记录实际 Pi 包名/版本、Node、架构和基础镜像 digest；核对与 [现有人用部署](../../panghu_chat/pi/README.md) 的关系。固定版本，禁止仅记录 latest。
- [x] A2 在隔离环境选择并验证 CLI/JSONL、RPC 或 SDK 中的一种；交付 execute(job,event_sink,cancel_signal) 适配，不通过 serve/浏览器终端抓取。
- [x] A3 证明非交互启动、完成、失败、工具调用回合、事件解码、退出码和进程树取消；意外 stdin 交互或格式变化须有限超时退出。
- [x] A4 验证精选技能发现/读取及资源文件路径；不继承私人 HOME/extensions/memory。
- [x] A5 验证模型 provider/API：优先现有 scientific 网关，失败记录协议证据并与 E/I 决定 worker 独立配置；不得恢复已退役 pi-trusted 或复制人用密钥。
- [x] A6 实测子进程 UID、环境剥离和跨任务/控制目录拒读。若同 Pod 权限隔离不可实现，暂停真实执行接入并提交替代边界，不把 cwd 当隔离。

验收：短模型对话+一次真实工具往返成功；故障/超时/取消有结构事件和结束证据；无交互提示挂起；无 token 泄露；Pi/模型/工具能力是实测结果。源码片段和 `--help` 不能代替端到端证明。

## 4. B — worker、队列、产物和生命周期

所有权：`panghu_agent/pi_worker/` 除 A runtime、C research_tools、I contracts 外的模块；`panghu_agent/tests/scientific_pi/worker/`。控制依赖需求交 E，禁止直接改 E 锁文件。

- [x] B1 实现 v1 内部 HTTP、token 鉴权、UUID/版本/大小检查和缺失配置 fail closed。
- [x] B2 用 worker 私有 SQLite 事务实现持久化提交、同用户并发限制、幂等冲突、claim/revision/attempt/fence；不能调用共享 SQL /query 实现 claim。
- [x] B3 单实例锁、并发 1；queued 恢复；中断 attempt 在总 deadline/max_attempts 内重排。attempt 失效后拒绝晚到结果。
- [x] B4 独立 HOME/cwd、权限隔离、最小环境；真实调用 A；进程异常/模型暂时失败按有界策略处理。
- [x] B5 幂等取消、总超时、TERM/KILL 进程树；完成/取消竞争只接受一个终态。
- [x] B6 结合 C schema 验证成果、重算 digest、复制到不可变结果目录；防路径穿越、符号链接、超限、跨任务文件。
- [x] B7 实现 publishing 及待发布列表、result、匹配 attempt+digest 的 publication-ack；任务报告未发布前不得 done。
- [x] B8 白名单 artifact_id 下载、保留期清理、队列可写/能力健康检查、脱敏事件；不公开原始会话/环境。

验收：重复提交、并发门控、worker kill/restart、超时、取消、旧 attempt、错误 manifest、控制目录/跨任务读取都经测试；fake Pi 可完成全部调度测试，真实 Pi 至少完成一项任务。失败保留受控中间产物且不切后端。

## 5. C — 科研技能、工具与证据

所有权：`panghu_agent/scientific_skills/`、`panghu_agent/pi_worker/research_tools/`、`panghu_agent/tests/scientific_pi/research/`、`panghu_agent/docs/scientific-pi-skills.md`。

- [x] C1 审查五项候选技能；记录 upstream commit、路径/hash、每项许可证、NOTICE、补丁与 optional/hard 依赖；未审查者不得默认加载。
- [x] C2 去除自动推广引用等不适用执行指令，保留合法来源署名；不依赖未配置 Parallel/OpenRouter 等 SaaS，默认禁用可选外部服务。
- [x] C3 提供科研任务模板与精简、固定版本技能包；工具路径与 A 加载机制对齐，不在运行时全量 clone 或自动更新。
- [x] C4 基于 framework-neutral 学术函数实现检索和元数据校验；需要改现有 academic 工具时先请求 I 转移单一文件所有权，不并行重构。
- [x] C5 实现 search/papers/screening/evidence/claims/references/validation 的 schema 和控制样例，提交 I 纳入 v1 contracts；区分 metadata/abstract/full_text。
- [x] C6 fixture 覆盖零结果、来源失败、重复论文、矛盾证据、缺引用、只有摘要、标识符核验 unknown；不得编造筛选数或承诺科学准确性。

验收：技能可被 A 发现和读取；无未申明付费硬依赖；证据关系可追溯；报告如实展示资料局限，普通输出不自动标为系统综述。审查与许可证证据随包交付。

## 6. D — API、报告投影与 UI

所有权：[API](../../panghu_agent/app/api/scientific_agent.py)、[UI](../../panghu_agent/app/ui/scientific_agent.py)、新 `panghu_agent/scientific_agent/{pi_client,pi_projection}.py` 和 `tests/scientific_pi/api/`。不修改共享 sqlite_client/server；需要通用能力先经 I 分配。

- [x] D1 新增 engine/mode/timeout 与增量响应字段；默认 CrewAI，明确拒绝不可用 Pi，保留原路径、响应结构、报告 id/字符串 keywords。
- [x] D2 持久化 engine index/email/dispatch 意图，提交 worker 使用稳定 task_id 和输入 hash；ambiguous timeout 用同 id 查询/重放。新 Pi task 不进入旧启动清理/懒超时逻辑。
- [x] D3 进程启动及每 10 秒 reconciler 修复 pending dispatch、拉取 publishing，幂等保存报告、读回 digest、ack；保存失败不丢报告、不重跑研究、不返回 done。
- [x] D4 report-store 失败、同 id 异内容冲突、保存后 ack 前崩溃及 worker 临时不可达有明确处理；不用跨库“原子提交”表述掩盖间隙。
- [x] D5 通知与科研成功解耦；失败邮件不会翻转完成任务，记录可能重复/未知投递结果。
- [x] D6 取消和 artifact 白名单转发；沿用受信内部入口，不开放未认证公网 worker/API；验证身份输入和错误响应不泄露内部 token/路径。
- [x] D7 UI 显示真实 stage/state、unknown 进度、限制说明和可选取消；旧状态兼容；20 分钟停止轮询不取消任务，可重新按 ID 查询。

验收：旧 CrewAI 提交/历史/下载继续可用；Pi 默认切换不影响在途任务；无 polling 也能发布报告；API 重启不把运行中 Pi 标失败；共享库暂时不可用恢复后能发布同一正文；邮件异常不改变报告成功。

## 7. E — 镜像、部署、模型配置与回滚

所有权：新 `panghu_agent/Dockerfile.scientific-pi`、`panghu_agent/k8s/scientific-pi/`、`panghu_agent/scripts/deploy-scientific-pi.sh`、worker package/requirements 锁文件、部署文档；共享构建模板/脚本及外层 Vault inventory 仅本包单一作者修改。

- [x] E1 与 A 固定运行方式、权限边界、模型协议、精确依赖；构建目标节点架构的 digest 固定镜像，不启动网页/ttyd，不依赖人用 Pi PVC。
- [x] E2 单副本 Recreate worker、专用 RWO PVC、内部 Service、健康探针、资源/输出/保留期配置；manifest 不硬编码私人路径和凭据。
- [x] E3 内部 token 及 worker 模型 caller 使用 Vault → ExternalSecret；验证缺 secret fail closed，Pi 子进程不可继承控制凭据，禁手工 kubectl create secret。
- [x] E4 默认拒绝网络，最小 DNS/模型/来源出站，只有 scientific API 可入站控制端口；禁止误带 Redis/OIDC/DB/Vault/人用 Pi 例外。记录 broad public443 与 fake-IP 限制。
- [x] E5 校验无服务账号 token、hostPath/hostNetwork/容器 socket/kubeconfig；nonroot Pi、只读根、capabilities/seccomp、临时目录与限额。
- [x] E6 新科学服务镜像/配置构建部署不通过共享 latest 覆盖其他 agent；输出渲染与 diff、dry-run、canary/暂停/排空/回滚指令。
- [ ] E7 canary 不发送邮件，先显式 engine=pi，再按 I 决策切默认；验证人用 Pi、现有 CrewAI 及其他 agent 资源未变。

验收：目标架构可运行、版本可复现、缺凭据受控失败；真实网络允许/拒绝和权限证据；回滚保留 PVC/报告，恢复 CrewAI 默认且不删除私人数据。

## 8. F — 集成与故障验收

所有权：`panghu_agent/tests/scientific_pi/integration/`、`panghu_agent/docs/scientific-pi-acceptance.md`；可向其他包提交缺陷，不直接改其文件。

- [x] F1 旧接口契约回归：提交、查询、搜索、报告详情与 Markdown 下载；兼容 status 与 report_id=task_id。
- [x] F2 真实 Pi 完成受控科研 fixture，核对 source→paper→evidence→claim→citation，报告/manifest/digest 与最终下载一致。
- [x] F3 生命周期故障矩阵：重复提交、并发门控、API 重启、worker kill/OOM、deadline、取消、晚到 attempt、报告库失败和 ack 中断、通知失败。
- [ ] F4 对实际 worker 做网络/文件隔离测试：API/Vault/Redis/DB/LAN/metadata/人用 Pi；同节点/跨节点、IPv4/IPv6；成功必须有 TLS/应用响应，不能只用 CONNECTED。
- [x] F5 两次连续任务不能读取前一任务 HOME、控制文件与密钥；artifact 路径、symlink、超限和恶意来源提示有负向验证。
- [x] F6 记录启动耗时、总时间、峰值内存/CPU、可得 token/费用指标；没有数据不声称 Pi 更轻。在线文献研究与控制 fixture 分别报告局限。
- [x] F7 提交可复现验收记录：命令、版本、时间、结果、脱敏日志和未通过项；由 I 更新 OpenSpec 完成勾选，不提前归档。

## 9. 跨包必须覆盖的评审补充

- 契约以 [contracts.md](design.md#protocol-v1) 为准。I0.3 固定 CanonicalJSON、input_digest、report_sha256、result_digest 的真实字节与完整测试向量，禁止各包独立推断。
- B 所有权排除 A 的 `pi_worker/runtime/`、C 的 `pi_worker/research_tools/`；I 的契约实际位于 `scientific_agent/pi_contracts.py`，不属于 B。
- D2 必须实现 prepared/accepted/rejected/ambiguous；明确 409/422/429 拒绝永不重新投递，超时/崩溃歧义用同 ID 查询与重放。
- D3 必须 insert-if-absent 再核对 report_sha256，禁止复用 INSERT OR REPLACE；ack 绑定 attempt+result_digest。
- B/F 测试进入 publishing 后取消返回当前状态、执行 deadline 不再终止发布；仍占 Pi 用户并发位，storage_unavailable 不是终态。
- F3 额外覆盖：API 在派单前崩溃、worker 接受后 HTTP 返回前崩溃、明确 429 之后不执行、报告保存后 ack 前取消、相同报告 ID 不同正文、排队时 deadline 到期、publishing 超执行 deadline、租约过期但进程仍在、混合 engine 并发。
- F 验证 30 天成果清理与 180 天快照/index/幂等保留，artifact 410，历史报告仍可查询下载。

## 10. 给其他 agent 的接手提示词

```text
在 D:\github\armbianbegin 处理 add-scientific-pi-worker 的工作包 <A/B/C/D/E/F>。
先读 AGENTS.md、.openspec-project.json 与 docs/scientific-research-pi/{proposal,design,tasks}.md，
远端 change 已创建，请从映射的 OpenSpec Service 获取最新状态；本地文档仅作交接副本。
仅修改你工作包的独占文件；
先检查已有修改并使用独立分支/工作树，不清理其他人的工作，不修改远端共享任务状态。
遵守 v1 HTTP、状态和产物契约；需要改契约或共享文件先通知集成者。
先做本包不依赖他人的工作，用约定 fake/mock 隔离依赖，标明未验证能力。
交付 commit、测试命令与证据、集成方式和剩余项；不要把文档设计当实现通过。
```
