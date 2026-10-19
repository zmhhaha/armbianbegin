# docs/ 索引

本目录是设计与调研笔记。**实现规格以 OpenSpec store 为准**（`armbianbegin` 项目，见仓库根的 `.openspec-project.json` 与 `AGENTS.md`）；这里放的是过程材料、现状调查和决策记录。

## Agent 模型接入

- [DSH、Hermes、Pi 接入 custom-llm](../panghu_chat/docs/agents-custom-llm.md)：2026-10-19 的直连配置步骤、DSH 故障修复、模型切换与验证状态；Pi 配置结果仍待确认。

> ## ⚡ 2026-09-20 更正：集群 NetworkPolicy 全部未生效
>
> 实测确认（非清单推断）：集群 CNI 是 **`kube-flannel`**，无 Calico / Cilium / kube-router / antrea。**flannel 不实现 NetworkPolicy，因此集群里现存的 13 个 NetworkPolicy 对象全部是空转的。**
>
> 从 `dsh-runner` 容器内探测，`llm-service`、`rag-service`、`embedding-service`、`postgres`、`redis`、**`kubernetes.default.svc:443`**、**`vault`** —— 7/7 全部 **CONNECTED**。
>
> **🟡 2026-09-22 补充**：引擎已换成 **Calico**（2026-09-21 迁移完成），DSH 策略里那条 `198.18.0.0/15` 也已删除。**但端到端复验尚未执行**，所以上面这条结论继续有效——按「截至 2026-09-20」读，别当成今天的现状。复验执行材料：[../panghu_chat/dsh/verify-network-boundary.sh](../panghu_chat/dsh/verify-network-boundary.sh)。
>
> **✅ 2026-09-29 更正：这次复验已经执行，「尚未执行」不再成立。** 2026-09-23 用上面那个脚本在**真实项目容器**里跑通，**退出码 0**；2026-09-29 又实测复现：`llm-service.llm.svc:80`、`kubernetes.default.svc:443`、`vault.vault.svc:8200`、`169.254.169.254:80`、`192.168.137.211:22` 全部 **BLOCKED**，`github.com:443`、`auth.panghuer.top:443` **CONNECTED**。Calico 的 `calico-node` 现在 5/5，**NetworkPolicy 确实在生效**。⇒ 上面两条更正保留作过程记录，但**本目录文档不应再按「边界未生效」读**。证据：[../panghu_chat/dsh/docs/closeout-2026-09-23.md](../panghu_chat/dsh/docs/closeout-2026-09-23.md)。
>
> **受影响的本目录文档**：[platform-k8s-conventions.md](platform-k8s-conventions.md) 第三节与 [platform-reusable-capabilities.md](platform-reusable-capabilities.md) 中"调用方 Pod 必须打 `llm-client` / `rag-client` / `embedding-client` 标签，否则连不上"的说法**在本集群上没有依据**，已就地加注更正。那条"最高频的坑"看起来是文档间相互引用，不是实测经验。
>
> **✅ 2026-09-29 再更正：上面这句「没有依据」，现在只对三分之二成立。** 它把三个标签一锅端了，但 Calico 迁移（2026-09-21）后 **`rag-client` 已经有依据**——`data/rag-service` 这条策略真的在执行，缺 `rag-client: "true"` 的 Pod 实测被拒。**`llm-client` 与 `embedding-client` 仍然没有依据**：集群里既没有 `llm/llm-service`、也没有 `data/embedding-service` 这两条策略（全集群 13 条清单见 [network-policy-engine.md](network-policy-engine.md)）。⇒ 既别再把三者并列读成"都无依据"，也别反过来读成"三者都已生效"。
>
> 完整结论与证据见 [panghu_chat/docs/infrastructure-assessment.md](../panghu_chat/docs/infrastructure-assessment.md) 第 8.0 节。

## 平台现状调查（动手前先读）

2026-09-16 的一次全仓库调查，代码基准 HEAD `3dd4128`。**目标是回答"新服务该怎么做"，并列出"哪些东西已经有了、别重复造"。** 行号会随代码演进漂移，引用前先核对。

| 文档 | 回答什么问题 |
|---|---|
| [platform-auth-ingress-survey.md](platform-auth-ingress-survey.md) | 要把内部 web 服务暴露到公网并做认证，该怎么做？现网的单用户白名单、MFA、会话 cookie 是什么状态？WebSocket/SSE 怎么配？ |
| [platform-k8s-conventions.md](platform-k8s-conventions.md) | 新增一个服务，manifest / namespace / 存储 / 镜像 / 资源 / 定时任务按什么约定写？集群有多大？ |
| [platform-reusable-capabilities.md](platform-reusable-capabilities.md) | 集群里已经有哪些可复用能力（LLM 网关、RAG、embedding、ES、邮件、定时采集框架）？哪些东西容易被重复造？ |

三份合起来的要点：**`content_agents` 已是一套完整的定时采集→中文报告框架；`llm-service` 是统一 LLM 入口（14 个消费方已迁移）；RAG/embedding/ES 检索层已建好且可扩展；周期性任务一律用 K8s CronJob。**

## 专题调研

| 文档 | 主题 |
|---|---|
| [platform-mcp-auth.md](platform-mcp-auth.md) | **平台 MCP 服务器的认证设计（2026-09-29 调研，2026-10-02 落地）**。MCP 规范要求服务器侧实现 OAuth 2.1，而 **Casdoor 已经把授权服务器那一半做完**（RFC 8414 metadata / OIDC discovery / PKCE / JWKS + consent + custom scopes）⇒ **平台侧不要自建授权服务器**，每个 MCP 服务器只需发布 **Protected Resource Metadata（RFC 9728）指向 Casdoor**，并校验它签发的 JWT。**OpenSpec 已整条跑通**：服务端发布 PRM 与 401 `WWW-Authenticate` 挑战头（§3.1/§3.2），Casdoor 侧建了 Agent/MCP 类型应用 `panghu-mcp`（§3.3，**公共客户端、不需要 `client_secret`**），audience 改成逗号分隔列表；实测走完 `401+挑战头 → PRM → Casdoor AS metadata → 授权码+PKCE → token → /mcp 200 → tools/list 返回 9 个工具`（§五）。**旧的「人工取长期 JWT 再贴进工具配置」路径随之退役**（`GET /token` 删除，能力归档在 [`../oauth/token-dispenser/`](../oauth/token-dispenser/README.md)）。⚠️ 两处实测更正：本集群 Casdoor 实为 **4.11.0**（不是抬头原先写的 4.13.0）；**DCR 开关存在（`organization.dcr_policy`）但默认关闭，且启用也与固定 audience 不兼容** —— 详见 §3.4 与 §七 |
| [oauth-proxy-consolidation.md](oauth-proxy-consolidation.md) | **八个人格的 oauth2-proxy 已合并为一个共享实例**（2026-09-28 部署，2026-09-29 修正回调）。最终形态：八条 Public Hostname 的 backend **全部指向 `oauth2-proxy-baijiazhengming`**，Pod 16→2、Deployment 8→1、ConfigMap 8→1；八个旧代理零流量留存作单域名退路。关键一条是**回调按请求 Host 生成**（共享实例不写 `--redirect-url`，只给 `--whitelist-domain`）——写死会让「从其它域名首次登录」被绕到被写死的那个域名，`182a78c` 就是修它；因此**没有 canonical 域名，Casdoor 八条回调每条都在用**。应用零改动（`passHostHeader` + UI 按 `Host` 查白名单）。§五 记录回滚**不再是一条命令**（旧 api/ui 已被 retire 脚本删除）；§六 留档那套**未采用且已删除**的方案（它那两个文件会覆盖同名 Deployment、把写死回调的坑挖回来，2026-09-29 已从仓库删除） |
| [service-git-access.md](service-git-access.md) | **让 DSH 与 Hermes 能改代码并推送的受控 Git 访问调研（2026-09-25）**。核心结论：**凭据在服务里藏不住**（agent 与 git 是同一个 uid 10000 进程），能做的是压缩半径——细粒度 PAT 只授 `Contents: Read and write`、只限必需仓库、设到期日；**不要给 `Workflows`**（能推 workflow 文件 = 往那个仓库的 CI 注入可执行代码）。另有两处纠偏：GitHub 的 **SSH 对公开仓库也要认证**（不存在匿名 SSH clone，所以那次 `Permission denied (publickey)` 是唯一可能的结果），而 `user.name`/`user.email` 与 GPG **都不是凭据**。§六 是动手前确认清单 |
| [node-container-log-wipe.md](node-container-log-wipe.md) | **这台节点上的容器日志会被定期清零（2026-09-28）**。成因是 Armbian 自带的 `armbian-truncate-logs`（每 15 分钟一次；`/var/log` 超过 75% 就把其中所有 `*.log` 截成 0），而 `/var/log/containers/*.log` 和 `/var/log/pods/**/0.log` 都是指向 docker 容器日志的**符号链接**，`truncate` 跟随链接 —— 于是所有容器的日志一起没了。**绕过办法：重跑一次并立刻读**。最容易踩的误判是把「日志是空的」读成「进程什么都没做」 |
| [calico-migration-run.md](calico-migration-run.md) | **Calico 迁移实录（2026-09-21）**。⚠️ **顶部有更正横幅，先读它**：真正的卡点不是 CNI，而是 DSH 策略里 except 列表中的 `198.18.0.0/15`——本网络 OpenClash fake-ip DNS 把所有外部域名解析到那个段，那一行等于排除整个公网。**"kube-router 不支持 except"是误判。** 文档保留完整过程（cordon 未解除、remove-flannel 未执行、kube-router 残留、磁盘压力），那些都是真的 |
| [obsidian：笔记同步](../panghu_chat/obsidian/README.md) | **已部署并跑通到设备侧（2026-09-27）**：CouchDB + Self-hosted LiveSync，设备侧原生 Obsidian（JWT 认证），服务端用 `livesync-cli` 的 daemon 模式物化出纯 Markdown 到 CephFS RWX 卷；索引作业每小时把 `百家争鸣/秉笔春秋` 索引进 rag-service。云端密文、端到端加密。目录内的 [deployment-notes.md](../panghu_chat/obsidian/deployment-notes.md) 是**踩坑与排查手册**（40 条；2026-09-27 补入「旗标文件 / 从设备侧重置远端 / 锁与 `mark-resolved`」一批，出问题先看它）；[downstream-distribution.md](../panghu_chat/obsidian/downstream-distribution.md) 设计笔记如何按 corpus 分给不同消费方（各服务独立 collection、Hermes/DSH 的共享记忆）。⚠️ 本目录下另有 [obsidian-deployment-research.md](obsidian-deployment-research.md)（2026-09-21，从未被本索引收录），它当时推荐的 CouchDB + LiveSync 方向**最终被采纳**，但域名与 TunnelRoute 效力两点已就地更正 |
| [rag-service-spike.md](rag-service-spike.md) | RAG 可行性实测（2026-09-10）：ES/embedding 基准数据、索引 schema 草案、容量估算。注意草案里的字段与实际实现的 mapping 有出入，以代码为准 |
| [llm-service-abuse-defense.md](llm-service-abuse-defense.md) | 防止调用方把 llm-service 当通用 LLM 白嫖的调研（2026-09-11）：威胁模型、杠杆排序、落实状态 |
| [jdwatch-work-research.md](jdwatch-work-research.md) | `jdwatch.work` 就业信息采集方式调研（2026-09-04）：结论是职位聚合站 + 自动化爬虫管道 |
| [ARC.md](ARC.md) | Actions Runner Controller 科普与部署指南。与 RAG/情报方向无关 |

## 实验路线（自有硬件上的动手清单）

| 文档 | 主题 |
|---|---|
| [softroce-dpdk-spdk-lab-plan.md](softroce-dpdk-spdk-lab-plan.md) | **Soft-RoCE / DPDK / SPDK 的可执行实验清单（2026-10，基于真机实测）**。先给能力矩阵：5 台节点的 `# CONFIG_INFINIBAND is not set`、`modinfo rdma_rxe` not found、无 `/sys/class/infiniband`（但 `libibverbs1`/`librdmacm1` 已装）；大页目录齐全、`/dev/hugepages` 已挂 2M；OPi5 有 18 个 IOMMU group 且 `vfio-pci` 可用、NanoPC 的 `uio_pci_generic` 未编译；apt 里 `dpdk` 22.11.11 / `rdma-core` / `perftest` / `nvme-cli` / `fio` 都可装，**没有 `spdk` 包**。再给四条路线：x86 双 VM 实验台（推荐起点，Soft-RoCE 全靠它）、WSL2 `--no-huge` 热身、给 Armbian 内核加 IB/RXE 后重编（附 config 与交叉编译）、硬件升级清单（M.2 NVMe / USB 网卡 / 双 ConnectX-3）。⚠️ **红线**：NanoPC 上的 NVMe 归 Ceph，禁止 `spdk/scripts/setup.sh` 与 `dpdk-devbind`；别在 3.85G 的 NanoPC 上分大页；别把 Hyper-V 外部交换机绑到给集群做 ICS 的那张 Realtek 网卡。**集群只被只读探测过，未做任何配置改动** |
| [ai-tech-radar-2026.md](ai-tech-radar-2026.md) | **2026 时兴 AI 技术的可行性雷达（2026-10 调研）**。按"你能不能真跑起来"排序给 11 条：① **RK3588 NPU 跑 LLM/VLM（RKLLM）**——官方 benchmark 实测 Qwen3-VL-2B 14.9 tok/s、SmolVLM-256M **78 tok/s**、DeepSeekOCR-3B **31.8 tok/s**、Gemma4-E2B 还带**音频** encoder（273ms/1.5s），这是集群里最被低估的资产；② 把本地 NPU 模型接进现有 llm-service 别名体系（`local-npu` tier）；③ llama.cpp **v0.6.0**（2026-10-05）的 MTP 投机解码 / KV 量化；④ 自托管 Agent 记忆（Hindsight/Mem0/Graphiti/Letta/Cognee 的部署成本对比）；⑤ MCP Registry / A2A 标准化（CNCF 已介入，你们 2026-09 的 [platform-mcp-auth.md](platform-mcp-auth.md) 方向踩对了）；⑥ reranker + contextual retrieval（GraphRAG 的 2026 结论是"先做上下文优化"）；⑦ 小模型 GRPO/LoRA；⑧ KServe v0.19 / llm-d v0.7 / HAMi。**明确别碰**：TileRT（硬要求 8×B200 或 8×MI355X）、万亿参数、FP8 训练、多卡 NCCL、NVFP4。另附 6 周路线与完整引用清单 |
| [kv-cache-kvmem-lab-plan.md](kv-cache-kvmem-lab-plan.md) | **KV Cache / KV Mem 的名词核实与硬件可行性分级（2026-10）**。核实结果：KVMem 论文**真实存在**（*Virtualizing Million-Token Agent Workspaces on **a Consumer GPU***，与本机 2070S 同档）；会话里的 "KV-CAT" **查无此名**（内容对应 *Training Transformers for KV Cache Compressibility*，ICML 2026），"Trellis" 与 `--kvmem-budget` 存疑/疑似编造 —— 那份分享的 `reference[N]` 是生成引用，**不能当出处**。可行性：KV 量化（`-ctk/-ctv`）、`-nkvo` 把 KV 甩到主机内存、MHA↔GQA 对照在 2070S 上**今天就能做**；vLLM PagedAttention + LMCache（KV 落到 NVMe，与上一篇交汇）要 WSL2；MLA（唯一现实权重 DeepSeek-V2-Lite，Q4 ≈10GB > 8GB 显存）与训练侧压缩**只能看**。⚠️ Windows 侧 CUDA Toolkit 只有 **v9.0（2016）**，别拿它编现代框架 —— 原生用 llama.cpp 预编译 CUDA 包，Linux 侧走 WSL2 驱动透传 |

## 决策记录

| 文档 | 记录了什么 |
|---|---|
| [hermes-code-review.md](hermes-code-review.md) | 对 Hermes 已写代码的评审（2026-09-16 初评，**2026-09-17 修订**：代码大幅改动且已部署）。当前仍存 1 高危 —— Hublog 出站 NetworkPolicy 写 8080 而实际连 80；另有 6 中危、5 低危。也记录了 SSRF 防护、凭据最小权限分离、双层认证等做得好的地方。**注：该高危的"端口不匹配"结论建立在 NetworkPolicy 生效的前提上，而 2026-09-20 实测该策略未生效——见上方更正** |
| [hermes-intelligence-review.md](hermes-intelligence-review.md) | 对 OpenSpec change `add-hermes-geopolitical-intelligence` 的**方案层**评审（2026-09-16，同日两次修订）。**未改动该 change 本身** |

## 相关：集群现状基线

| 文档 | 记录了什么 |
|---|---|
| [../panghu_chat/docs/infrastructure-assessment.md](../panghu_chat/docs/infrastructure-assessment.md) | 服务器上全部服务的汇总评估。2026-08-07 初版，**2026-09-20 全面复核**：45 个命名空间 / 164 个 Pod、已部署服务、缺失清单、Ceph/Vault/备份/监控现状，以及第 8.0 节的 NetworkPolicy 未生效实测结论。**动手改集群或设计新服务前先读它。** |
| [network-policy-engine.md](network-policy-engine.md) | 网络策略引擎的选型与启用清单（2026-09-20）。**选型过程与结论已过期**：文中"Calico 策略-only 官方不支持，采用 kube-router `--run-firewall`"是当时的判断，**实际落地的是完整 Calico**（2026-09-21 迁移，见 [calico-migration-run.md](calico-migration-run.md)），文中"kube-router 不支持 `except`"更是**误判**（顶部横幅已更正）。**保留价值**：三种方案的取舍论证、启用范围只框 dsh/hermes 的理由、启用前必须修的标签与端口三处。kube-router 的部署代码按所有者决定保留作备用路线，可执行材料在同名目录 [../network-policy/](../network-policy/README.md)。 |
