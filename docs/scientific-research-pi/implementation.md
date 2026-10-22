# scientific-research Pi worker 实现与环境验证记录

更新时间：2026-10-22（Asia/Shanghai）。Change ID：`add-scientific-pi-worker`。

## 当前结果

后续生产部署、真实来源检索、浏览器与恢复验收统一记录在
[2026-10-22 上线记录](rollout-20261022.md)。下文保留首次候选构建的历史证据；
其中未部署、146 项测试和未提交的描述仅适用于该历史阶段。

## 首次候选构建时的状态（历史）

本地实现已完成，独立 ARM64 worker/API 候选镜像已构建并推送；真实科学网关工具回合、Linux 权限与进程回收验证已通过。现有科学 API 仍运行 `agent-api:ac61414`，CrewAI 默认路径未切换；没有部署长期 Pi worker、生产 PVC 或生产独立 caller。OpenSpec 保持 active，不 apply/archive。没有 Git commit/push。

## 已交付代码

| 包 | 入口 | 内容 |
|---|---|---|
| I 契约 | [pi_contracts.py](../../panghu_agent/scientific_agent/pi_contracts.py) | 严格 job、UUID/时间/长度、CanonicalJSON、固定 digest、旧 status 映射 |
| A 运行时 | [adapter.py](../../panghu_agent/pi_worker/runtime/adapter.py) | Pi JSONL、独立 HOME、provider 配置、事件/provenance、超时取消与进程 fence |
| B worker | [app.py](../../panghu_agent/pi_worker/app.py) | 私有 SQLite、持久化 UID、admission、attempt/lease、拒绝 tombstone、恢复与保留 |
| C 科研 | [工具包](../../panghu_agent/pi_worker/research_tools/__init__.py) | 原创程序性技能、查询 CLI、证据引用校验、摘要全文边界、unknown |
| D 接入 | [API](../../panghu_agent/app/api/scientific_agent.py) / [projection](../../panghu_agent/scientific_agent/pi_projection.py) | CrewAI 默认、dispatch 恢复、insert/readback/ack、独立通知状态、UI 查询/取消 |
| E 部署 | [渲染器](../../panghu_agent/k8s/scientific-pi/render.py) | 独立镜像、PVC/Service/网络、API 增量、ExternalSecret 映射 |
| F 验收 | [集成说明](../../panghu_agent/docs/scientific-pi-acceptance.md) | 实际 API/worker/队列/校验/发布链路及故障注入 |

未勾选的原始验收任务不等于没有代码；接手前查已有实现，不重复从零编写。

## 实际 Linux 测试

最终 ARM64 验收派生镜像内执行 `python scripts/test-scientific-pi.py`：**146 项全通过，0 跳过、0 失败**。

| 包 | 通过 |
|---|---:|
| contracts | 8 |
| research | 29 |
| worker | 24 |
| api | 33 |
| runtime | 27 |
| integration | 19 |
| deployment | 6 |

另外执行 Linux OS 专项：**7 项全通过，7.204 秒**。实际验证 controller capabilities 精确为 CHOWN/DAC_OVERRIDE/KILL/SETGID/SETUID（0xe3），只读根、断网、独立 PID namespace、无宿主挂载/socket/SA、tmpfs；子进程唯一 UID、空 capabilities/groups、NNP、RLIMIT_NPROC、控制/前任务拒读、detached 后代正常结束/取消/超时回收、controller SIGKILL 后恢复、FIFO 非阻塞拒绝。专项使用明确的合成 CLI，真实 Pi 协议另测。

日志：[146 项回归](evidence/20261022-arm64/linux-suite-87d68c0f.log)、[7 项系统验收](evidence/20261022-arm64/linux-os-87d68c0f.log)。平台：ARM64，内核6.1.115-vendor-rk35xx，Docker29.6.1，Node24.21.0，Python3.13。仅验证 ARM64，未验证 AMD64。

历史 Windows 首版结果135项（132通过/3平台跳过）保留为历史，不替代本次结果。后续新增严格协议测试在 Windows 出现 Pi 版本探测5秒超时，未弱化超时或掩盖失败；同一固定 CLI 在 Linux 严格请求 schema 与工具回合测试通过。TestClient 的弃用警告、预期故障注入日志不算失败。

## 候选镜像与来源

所有镜像都使用独立仓库，没有覆盖共享 latest。

- worker：`arm-cluster-master:5000/scientific-pi-worker@sha256:dbdf5c05fdf669b16ed065fbbe19f094244542e2a26639c880115ac284e6a04b`
- API：`arm-cluster-master:5000/scientific-pi-api@sha256:89caf56457ee7f778ebe26337278ca3ede6bf6550d7f6339386473c18dcfbaa9`
- 仅供测试的派生镜像：`arm-cluster-master:5000/scientific-pi-acceptance@sha256:944b3a3add1778b803fed88475d8e1ff171ef93873cd40c1859512e6dd27facf`
- worker/测试快照摘要：`87d68c0f93ed2536e942e4ffb749af8ab97fde5df381b58107570b88b58e23a5`；API 构建快照 `7adf3f47d1a6ca1a3191e12a348bee5adfe0f21354e9c9c9a5b445e3da702569`，其后 API 源码未变。
- Node 基础：`node@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20`；Python 基础：`python@sha256:cf50a4f6ac4f026458b08d5222023d700ac806410dff5e9ca8728fa44f2b850f`（trixie）。这是本次明确覆盖的基础，不是 Dockerfile 默认版本标签已验收。
- API 基础为当前线上精确 digest `sha256:62f908474e4df08436ea64f5a54f663a11cdadb5b304c1675bcf5c77de035674`。

Pi 固定 `@mariozechner/pi-coding-agent@0.73.1`，不同于人用工作台的 earendil-works 包；npm 弃用提示仍存在，没有静默升级。Python 顶层依赖固定、传递依赖当前由 pip 解析；本次最终镜像 digest 固定，不宣称从基础重建必然逐字节一致。

## 真实模型与工具回合

独立受限 Pod 使用上述测试派生镜像，真实 Pi0.73.1 经现有科学网关 alias `llm-trusted` 两次请求，实际 bash 执行固定标记命令，第二次请求含工具结果。SSE model 字段为 `gpt-6.1-sol`，是网关自报，不是独立模型身份认证。

[脱敏结果](evidence/20261022-arm64/model-probe-report.json)：valid=true、command_exact、marker_exact、second_request_tool_marker、UID300000清理、真实密钥不在工作目录/provenance/events 均通过。测试从已有科学服务 Secret 引用获得凭据，只在根控制进程内存中持有；Pi 仅拿本机代理的 dummy key。没有读取人用 Pi 配置，没有邮件、研究数据库写入或在线文献研究。

此 harness 临时声明验证开关以收集证据；报告明确 `production_acceptance=false`。生产 readiness 三个开关仍默认0，正式 worker 独立 caller 的注册和 Vault/ExternalSecret 尚未完成。

## 本次关闭的问题

1. 现有 CrewAI 整目录 ConfigMap 会遮住新 Pi 模块：API 镜像改为固定 `/opt/scientific-pi-extension`，原 CrewAI 路径优先；33项 API 测试和实际 Linux 只读整目录覆盖导入均通过，见 [覆盖验证](evidence/20261022-arm64/api-overlay-test.json)。实际覆盖测试使用合成 CrewAI 模块，不是线上功能回归。
2. Pi 默认请求含网关不接受的 store/stream_options/max_completion_tokens：固定 compat profile 禁用不支持字段、使用 max_tokens、上限8192。真实 CLI 对实际网关 ChatRequest schema 的两回合测试通过，随后真实网关验证通过；未放宽网关。
3. Linux fixture 模式在根进程已退出时只发信号即返回，出现子进程仍 R 状态：补充有界进程组扫描，两次无活动进程才确认。三个确定性回归与完整 Linux 复测通过。生产 UID 确认逻辑不变。
4. 原有 durable 拒绝、publishing commit 边界、insert/readback/ack、FIFO/符号链接/硬链接防护、私有全文材料、唯一 UID 和未知清理 fence 均通过回归。

## 网络验证与剩余门槛

三份网络报告：[跨节点基线](evidence/20261022-arm64/network-baseline.log)、[同节点基线](evidence/20261022-arm64/network-samenode.log)、[同节点受限](evidence/20261022-arm64/network-restricted.log)。这些无凭据 Pod 使用原 API 基础镜像，验证 renderer 生成的等价 egress 策略，仅选择临时标签。

- 模型健康 HTTP200/格式正确，基线和受限都允许。
- Kubernetes TLS+HTTP200、Vault200、SQLite200、Redis NOAUTH、节点 SSH banner 在同节点基线成立，受限超时，支持这5项拒绝结论。
- 人用 Pi 地址基线也超时、metadata 基线拒绝连接，均为 unknown，不声称策略已证明阻断。
- Crossref/PubMed/arXiv 都解析为198.18/15 fake-IP；探针未拨号，无 TLS/应用证据，外部文献访问未验收。没有放开 fake-IP 或修改全局 DNS。

仍待：受控真实解析/学术 HTTPS 路径、正式 worker 独立 caller 与 Secret、生产 PVC 重启和全流程科研 fixture、真实共享 SQLite/邮件/Gradio浏览器、IPv6与更完整网络矩阵、真实质量/全文/资源成本测量、K-Dense 候选审查、canary/回滚与默认切换。崩溃恢复后的 root 私有 launch 配置清理可后续改进，当前不阻碍进程隔离结论。

临时4个 Pod、2个专属 NetworkPolicy、1个 ConfigMap 已在确认 Succeeded 后删除。构建目录和脱敏证据保留；线上 API 镜像仍为原 ac61414，没有切换默认后端。所有用户已有修改和其他 agent 工作保留，没有重置工作树或 Git 提交。
