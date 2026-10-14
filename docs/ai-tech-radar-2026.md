# AI 技术雷达 2026：在本机与集群上能做的实验

> 调研时间 2026-10。方法：先检索"现在时兴什么"，再用**实测硬件**（见 [softroce-dpdk-spdk-lab-plan.md §0.2](softroce-dpdk-spdk-lab-plan.md)）逐条判可行性。
> 硬件约束一句话：**x86 主机（i7-4770 + RTX 2070S 8GB sm_75）+ 2× RK3588（8C/16GB，NPU 6 TOPS）+ 3× RK3399（6C/3.85GB）+ K8s 1.31 集群 + 已有 MCP/RAG/embedding/LLM 网关**。
> 姊妹篇：[kv-cache-kvmem-lab-plan.md](kv-cache-kvmem-lab-plan.md)（KV 生态）、[softroce-dpdk-spdk-lab-plan.md](softroce-dpdk-spdk-lab-plan.md)（数据面/存储）。

---

## 0. 一览表（按"你能不能真跑起来"排序）

| # | 技术 | 2026 热度 | 你的可行性 | 在哪跑 | 第一步 |
|---|---|---|---|---|---|
| 1 | **RK3588 NPU 跑 LLM/VLM（RKLLM）** | 🔥 端侧爆发 | ✅ **最佳性价比** | Orange Pi 5 Plus / Max | 用官方 benchmark 里已有的模型（Qwen3.5-2B / Qwen3-VL-2B）跑通 `rkllm` |
| 2 | **把本地 NPU 模型接进现有 llm-service 别名体系** | 🔥 混合推理 | ✅ **最有业务价值** | K8s 集群 + llm-service | 加一个 `local-npu` tier 别名，敏感/离线请求本地答 |
| 3 | **llama.cpp v0.6.0 + MTP 投机解码 + KV 量化** | 🔥 | ✅ 今天就能做 | 2070S | 见 [kv-cache 文档](kv-cache-kvmem-lab-plan.md) 的 A 组实验 |
| 4 | **Agent 长期记忆（自托管）** | 🔥🔥 2026 主线 | ✅ 集群正合适 | K8s + Postgres/ES | 选 Hindsight（单容器+内嵌 PG）或 Mem0 起一个 |
| 5 | **MCP 生态 / Registry / A2A** | 🔥 标准化落地 | ✅ 你已有一半 | 已有 `panghu-mcp` | 把 NPU 服务（OCR/VLM/embedding）包成 MCP 工具 |
| 6 | **RAG 新范式：reranker / contextual retrieval / GraphRAG 取舍** | 🔥 | ✅ | ES + embedding-service | 先上 reranker（llama.cpp 已支持 `classifier_pooling`） |
| 7 | **小模型 RL（GRPO）+ LoRA 微调** | 🔥 | ⚠️ 8GB 勉强 | 2070S | 0.5–1.5B 的 GRPO/LoRA，Unsloth 或 trl |
| 8 | **K8s 推理平台：KServe v0.19 / llm-d v0.7 / HAMi** | 🔥 | ⚠️ 概念可学、规模不匹配 | 集群 | 先读设计（KV-aware routing、PD 分离），再考虑小规模复刻 |
| 9 | **PD 分离 / KV 存储层（LMCache、Mooncake、NIXL）** | 🔥🔥 | ⚠️ 需 CUDA 机器 | x86 + WSL2 | LMCache 本地盘后端 → 与 SPDK/NVMe 文档汇合 |
| 10 | **Prompt injection 防御 / LLM 评测体系** | 🔥 | ✅ | 已有 llm-service guard | 对齐 2026 的防御分层，补评测 harness |
| 11 | **TileRT / 万亿参数 / FP8 训练 / 多卡 NCCL** | 🔥 但与你无关 | ❌ | — | 见 §3 |

---

## 1. 端侧 NPU：你集群里最被低估的资产

**为什么值得先做**：OPi5 的 RK3588 带 6 TOPS NPU，而 `rknn-llm`（Rockchip 官方工具链）已经把它做成了可用的推理后端。社区实测「RK3588 NPU 解码约为 llama.cpp 的 4 倍」——即同样的板子，走 NPU 比走 CPU 快一个档。

**官方 benchmark（[airockchip/rknn-llm/benchmark.md](https://github.com/airockchip/rknn-llm/blob/main/benchmark.md)，RK3588 / w8a8 / seqlen 128 / 生成 64 token）**：

| 模型 | 规模 | TTFT | 解码 | 内存 |
|---|---|---|---|---|
| LFM2.5-VL | 450M | 103 ms | **62.2 tok/s** | 437 MB |
| MiniCPM4 | 0.5B | 135 ms | 45.3 tok/s | 535 MB |
| Qwen2 | 0.5B | 146 ms | 41.6 tok/s | 670 MB |
| Qwen3 | 0.6B | 199 ms | 32.9 tok/s | 791 MB |
| **Qwen3.5** | **0.8B** | 588 ms | 27.1 tok/s | 1040 MB |
| Qwen2.5 | 1.5B | 378 ms | 16.7 tok/s | 1689 MB |
| **Qwen3.5** | **2B** | 777 ms | **13.6 tok/s** | 2122 MB |
| Gemma2 | 2B | 598 ms | 10.4 tok/s | 2779 MB |
| Qwen3.5 | 4B | 2069 ms | 6.2 tok/s | 4576 MB |
| ChatGLM3 | 6B | 1353 ms | 5.0 tok/s | 5986 MB |

**多模态（同一张表，NPU 跑 encoder + decoder）**：

| 模型 | 图像编码 | Decode |
|---|---|---|
| **SmolVLM-256M** | 842 ms | **78 tok/s** |
| Qwen3-VL-2B | 2.08 s | 14.9 tok/s |
| Qwen2-VL-2B | 3.28 s | 16.6 tok/s |
| **DeepSeekOCR-3B (A570M)** | 2.09 s | **31.8 tok/s** |
| Gemma4-E2B（图） | 758 ms | 11.2 tok/s |
| **Gemma4-E2B（音频）** | 273 ms/1.5s | 11.2 tok/s |

**⇒ 可做的实验（每一条都能变成集群里的一个服务）**：
1. **本地 OCR 服务**：DeepSeekOCR-3B 在 NPU 上 31.8 tok/s + 2 秒出图编码——完全够做文档/截图 OCR，替代云端调用。
2. **本地 VLM 服务**：Qwen3-VL-2B 或 SmolVLM（78 tok/s 那个适合"快问快答"）。
3. **语音**：Gemma4-E2B 的 audio-encoder 实测 273 ms/1.5 s 音频 + 11 tok/s，可以做本地语音理解（配合 Whisper 系 ASR）。
4. **embedding/reranker 上 NPU**：你们现在的 embedding 是 RK3588 **CPU** 上的 onnxruntime（[rag-service-spike.md](rag-service-spike.md)：单条 18.7 ms）。`rknn-llm` 里还有 embedding/reranker 类模型（LFM2.5-Encoder、`classifier_pooling` reranker）——**把 RAG 的向量化和重排挪到 NPU，CPU 让给业务**，这是可量化收益。
5. **对照实验（最有说服力）**：同一模型在 OPi5 上跑 `llama.cpp CPU` vs `RKLLM NPU`，出 TTFT/吞吐/功耗对照表。

> 注意：NPU 路线的代价是**模型必须先转换**（RKNN 工具链，需要在 x86 Linux 上做转换，`rknn-toolkit2`），且只支持官方已验证的架构。所以"能不能用 NPU"取决于模型是否在 [rknn-llm](https://github.com/airockchip/rknn-llm) 支持列表内——benchmark 表就是那张列表。

**参考项目**：[freed-dev-llc/turing-rk1-cluster](https://github.com/freed-dev-llc/turing-rk1-cluster) —— 4 节点 RK3588 裸金属 K8s（Talos + Longhorn + **RKNN NPU 支持**），和你们集群形态几乎一样，值得对照读。

---

## 2. 推理与 KV 生态（x86 + 2070S 侧）

### 2.1 llama.cpp v0.6.0（2026-10-05 发布，就在几天前）

[Release v0.6.0](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0) 里对你有用的：

- **MTP 投机解码**：Qwen4Exp 上 MTP 约 **1.5× 解码加速**（官方在 DGX Spark 上测的）。你的 2070S 是带宽受限卡，投机解码正是这类卡收益最大的优化——**可以直接量出"你的卡上能拿多少倍"**。
- **`/v1/embeddings` 支持带类型的 vision/audio/video 输入** → 可以用一个 llama.cpp 服务同时做多模态 embedding。
- **reranker 支持**（`classifier_pooling`）→ 直接补上 RAG 的重排环节，不用再引一个服务。
- **Web UI 重做，内置 Hugging Face Hub 数据层与模型下载管线** → 上手成本显著降低。
- **量化 KV 的稀疏 flash attention（Vulkan）**、F16 KV 的 Metal flash attention —— KV 优化的新进展，和 [kv-cache 文档](kv-cache-kvmem-lab-plan.md) 呼应。

### 2.2 vLLM 在 Turing（sm_75）上还行不行

- 仍然有人在为 **sm_75 及更早**架构加特性（例：[vLLM PR #45829](https://github.com/vllm-project/vllm/pull/45829) 给 sm75 加 TRITON_ATTN 的 fp8 KV cache 支持），说明 Turing 没被抛弃，但**新特性通常默认为 sm_80+**。
- 实操结论：**llama.cpp 当主力，vLLM 当"工业实现对照"**。vLLM 走 WSL2（Turing 无 FlashAttention-2/FP8，需走 XFormers/Triton 分支）。

### 2.3 PD 分离 / KV 存储层 —— 热度最高、但你只能"学一半"

- **vLLM × TileRT**：用专用 decode 引擎做延迟敏感的分离式服务（[vLLM 博客 2026-07-14](https://vllm.ai/blog/2026-07-14-vllm-tilert-pd)）。但 [TileRT 的硬要求](https://github.com/tile-ai/TileRT)是 **8×B200 或 8×MI350X、CUDA 13.2、PyTorch 2.11+** —— 与你无关（见 §3）。
- **LMCache × Mooncake** 联手做 KV 存储层（[联合公告](https://blog.lmcache.ai/en/2026/05/26/when-open-source-meets-open-source-a-joint-effort-between-lmcache-and-mooncake/)），传输层用 **NIXL/UCX**——这里出现了 `UCX_NET_DEVICES` 这类 RDMA 参数，正是 [Soft-RoCE 文档](softroce-dpdk-spdk-lab-plan.md) 能接上的地方。
- **能学的部分**：把 KV 块**当存储对象**来调度（分页、检索、换入换出、预算控制）。在 2070S + LMCache 本地盘后端上，你能亲手量出"KV 落 NVMe 的带宽 vs 命中率"这条曲线。

---

## 3. 明确别碰（省钱省时间）

| 技术 | 为什么 |
|---|---|
| **TileRT / 万亿参数推理** | 硬要求 8×B200 或 8×MI355X；单机 8 卡起步。读它的**思想**（PD 分离、MTP、KV dtype、NIXL 传输）就够了 |
| **大模型预训练 / 全参微调 / FP8 训练** | 8GB 显存 + 无 FP8（Turing）。最多到 1.5B 的 LoRA/QLoRA |
| **多卡 NCCL / GPUDirect RDMA** | 你只有一块卡；且 GeForce 驱动不支持 GPUDirect RDMA（见前一份调研） |
| **NVFP4 量化模型** | 原生要在 Blackwell 上跑；老卡只能等 GGUF 社区转档 |
| **视频生成大模型（Wan/Veo 类）** | 8GB 显存门槛不够，且与你的方向无关 |

---

## 4. Agent 记忆与上下文工程（2026 主线，集群正合适）

自托管记忆系统的横向对比（数据来自 [2026-08 的自托管选型对比](https://raw.githubusercontent.com/vectorize-io/hindsight/b4c9071d4cdaa2174d9d9b509a7c9fcae21024c5/hindsight-docs/blog/2026-08-11-open-source-agent-memory-systems.md)，注意该文作者是 Hindsight 一方，但**部署形态与许可证是客观可查的**）：

| 系统 | ★ | 许可 | 自托管真实成本 | 存储 | 最擅长 |
|---|---|---|---|---|---|
| **Mem0** | ~63.0K | Apache-2.0 | 开源核心默认内嵌，生产通常外挂向量库 | 向量（+可选图） | 社区生态、对话个性化 |
| **Cognee** | ~30.0K | Apache-2.0 | 默认内嵌（SQLite/LanceDB/Kuzu），无强制云 | 图管道 | 图式 ECL 流水线 |
| **Graphiti / Zep** | ~29.8K | Apache-2.0 | 自托管的是 **Graphiti 引擎**，Zep CE 已废弃 | 时序知识图（Neo4j/FalkorDB） | **时间维度的"何时为真"** |
| **Letta**（原 MemGPT） | ~24.2K | Apache-2.0 | 自托管 server | Agent 运行时 + 记忆 | 一整套 Agent 运行时（memory blocks + archival） |
| **Hindsight** | ~19.6K | MIT | **一条 docker 命令，内嵌 PostgreSQL，无外部 DB** | 单 PG、多策略 | 精度 + 部署极简 |

**给你的建议**：
- 只想加一层记忆 → **Hindsight**（单容器 + 内嵌 PG，你们的 Ceph RWO 卷直接挂）或 **Mem0**。
- 需要"事实的时间有效性"（审计/履历类，你们 `panghu_game` 里那种世界观状态）→ **Graphiti** 的时序图模型，这个抽象值得学。
- 需要**一整套 Agent 运行时** → Letta。你们已经有 DSH/Hermes 两套 agent 框架，先别急着换运行时。
- ⚠️ 评测口径要看清：LongMemEval 已接近饱和（头部都在 90 分档），真正有区分度的是**十万 token 级长程记忆**（如 BEAM）。
- 概念补充：[Data Management for Agentic Memory (VLDB)](https://dl.acm.org/doi/abs/10.14778/3827998.3828145)、[AI Agent Memory Architectures: Episodic, Semantic, Working Memory](https://zenodo.org/records/21921640)、[中文全景对比（附录15）](https://github.com/cdavid817/awesome-agent-tutorial)。

### MCP / A2A：标准化正在落到基础设施层

- [CNCF 正在评估把 MCP 作为云原生 Agent 的线协议](https://tech.yahoo.com/ai/meta-ai/articles/cncf-evaluates-mcp-cloud-native-142016206.html)——你们 2026-09 就已经把 [MCP 认证按 OAuth 2.1 落地](platform-mcp-auth.md)，**方向踩对了**。
- **MCP Registry**（服务发现）在推进 v1.4.x：你们有 9 个工具的平台 MCP server，下一步自然是"多服务器 + 注册发现"。
- **A2A（Agent 间协作）+ MCP 协同**被业界称作"智能体时代的 HTTP"：可以做一个小实验——让 panghu_agent 与 Hermes 通过 A2A 交换任务，工具调用仍走 MCP。

---

## 5. RAG 新范式（你们已有 ES + embedding，边际成本最低）

- **"GraphRAG 到底需不需要"** 已经有 2026 的系统性回答（[ACL 2026: Is GraphRAG Needed? From Basic RAG to Graph-/Agentic Solutions with Context Optimization](https://aclanthology.org/2026.gem-main.40/)）：结论倾向"**先做上下文优化（rerank/压缩/chunk 策略），图不是默认答案**"。你们现在的 hybrid 检索（47 ms）离需要图还远。
- **可立刻做的三件事**：① 上 reranker（llama.cpp 已内置支持）；② contextual retrieval（chunk 时用模型补上下文）；③ 多模态 GraphRAG 的**评测**（[跨模态关系学习](https://ieeexplore.ieee.org/document/11536532)是前沿，先别实现）。
- 如果要做图：**Graphiti** 顺带就是"时序知识图"，比另起一套 GraphRAG 更贴合你们的记忆需求。

---

## 6. 训练与对齐（8GB 的现实边界）

| 方向 | 你能做到 | 依据 |
|---|---|---|
| **LoRA/QLoRA 微调** | 0.5–1.5B 模型可做（7B 要 4bit + 梯度检查点，勉强） | 通用实践 |
| **小模型 RL（GRPO）** | 2B 级 RL 已有公开教程（[Databricks: Gemma4-2B 的强化学习](https://learn.microsoft.com/zh-cn/azure/databricks/machine-learning/ai-runtime/examples/tutorials/sgc-rl-gemma4-2b)）；8GB 上要极小的 batch + LoRA | 同上 |
| **CPU/边缘侧微调** | 2026 已把"在 AI PC 上微调"做成教程（[HF blog](https://huggingface.co/blog/dmsuehir/efficient-llm-fine-tuning-on-intel-ai-pcs)）——**你们 i7-4770 没有 AVX-512，别指望 CPU 训练**，但可跑推理/小规模 embedding 微调 | 硬件限制 |
| **量化模型服务** | KServe **v0.19** 支持 **Static LoRA Adapters**（一个基座 + 多个适配器按请求切换）——这才是你该学的部署形态 | [KServe v0.19](https://kserve.github.io/website/blog/kserve-0.19-release) |
| **DPO/蒸馏** | 1.5B 级可行，用于把云模型的输出蒸馏到本地小模型 | 通用实践 |

**方向性判断**：2026 的端侧趋势是[小模型（SLM）进入主流技术雷达](https://www.thoughtworks.com/zh-cn/radar/techniques/small-language-models)（[英文版](https://www.thoughtworks.com/pt-br/radar/techniques/small-language-models)），配合[端侧 LLM 的系统性综述](https://europepmc.org/article/PPR/PPR1208649)。**你的 NPU 正好是这条趋势的硬件**——把算力花在"小而专"（OCR/VLM/rerank/分类）比追大模型划算得多。

---

## 7. 平台与调度（集群侧）

| 技术 | 2026 状态 | 与你集群的关系 |
|---|---|---|
| **llm-d v0.7** | 从"加特性"转向"生产加固"（[发布说明](https://llm-d.ai/blog/llm-d-v0.7-from-feature-introduction-to-production-hardening)） | 目标是 vLLM on K8s；你集群无 GPU。**可以学它的调度抽象**（KV-aware 路由、PD 分离拓扑） |
| **KV-cache 感知路由** | IBM 在 KubeCon EU 2026 做了"AI-aware LLM routing on Kubernetes"（[论文](https://research.ibm.com/publications/kv-cache-wins-you-can-feel-building-ai-aware-llm-routing-on-kubernetes)） | **你们能低成本复刻**：在 llm-service 里按 `prompt 前缀哈希 → 后端实例` 做亲和路由，量出命中率/延迟收益 |
| **KServe v0.17→v0.19** | v0.17 出 LLMInferenceService，v0.18 多节点推理 + OpenAI Responses API + llm-d v0.6，v0.19 Static LoRA Adapters / 模型名路由 / 优雅关闭 | 完整 KServe 需要 Knative+Istio，对 44 GiB 集群偏重；**建议只借它的 API 形态**（`LLMInferenceService`） |
| **HAMi（vGPU）** | 异构算力共享平台（[部署选项](https://project-hami.io/docs/next/get-started/choose-your-setup)） | 只有把它们接进 K8s 才有意义（例如给 x86 主机装 K8s 再共享那张 2070S）；NPU 共享目前不在其覆盖内 |
| **CPU/ARM 上的 K8s 推理** | 有 [K8s 上 GenAI 推理的性能评估论文](https://browse-export.arxiv.org/pdf/2602.04900)（ASR 到 LLM 摘要） | 直接对应你们的 ARM 集群：**量"K8s 网络/存储开销对推理延迟的影响"**是个没人替你做过的实验 |

---

## 8. 安全与评测（你们已有 guard，边际成本低）

- **Prompt injection 防御分层**：2026 已有体系化整理（[Prompt Injection Defense Architectures in 2026](https://safeguard.sh/resources/blog/prompt-injection-defense-architectures-2026)）。对照你们 llm-service 现有的 **canary + 别名白名单 + 参数白名单**（见 [llm-service-abuse-defense.md](llm-service-abuse-defense.md)），缺的通常是：**工具调用边界的注入检测**、**输出侧的动作校验**（agent 场景的核心）。
- **评测体系**：从"跑分"转向"任务级+可复现"。（参考 [Stanford AI Index 2026 技术性能章](https://hai.stanford.edu/ai-index/2026-ai-index-report/technical-performance) 的口径；工具层面 2026 的讨论见[评测框架盘点](https://github.com/hernanda-git/ai-knowledge-library/blob/main/69-AI-Evaluation-and-LLM-Testing/04-Tools-and-Frameworks.md)。）
- **对你们的实际价值**：给 `panghu_game` 那套多 agent 流水线建一个**回归评测集**（固定输入 → 断言关键行为），比接任何新框架都值。

---

## 9. 推荐的 6 周路线（每周一个可交付）

| 周 | 主题 | 交付物 |
|---|---|---|
| 1 | NPU 起步：OPi5 上跑通 `rkllm` + 一个 2B 模型 | 本地 `rkllm_server`，用 curl 验证；记录 TTFT/吞吐 |
| 2 | NPU vs CPU 对照 + 选型 | 同一模型两条路径的对照表（含功耗/温度） |
| 3 | 本地服务进集群：NPU OCR/VLM 服务 + llm-service 新别名 | 一个 `local-npu` tier；敏感请求路由验证 |
| 4 | 记忆层：Hindsight（或 Mem0）接入现有 agent | 一个容器 + Ceph 卷；长会话召回率前后对比 |
| 5 | RAG 升级：reranker + contextual retrieval | 检索命中率/延迟的前后数据（对照 rag-service-spike 的 47 ms 基线） |
| 6 | KV 生态（x86）：llama.cpp v0.6.0 MTP 投机解码 + KV 量化 | 2070S 上的加速比与显存表（接 [kv-cache 文档](kv-cache-kvmem-lab-plan.md)） |

---

## 10. 引用清单

**端侧 / NPU**：[rknn-llm benchmark](https://github.com/airockchip/rknn-llm/blob/main/benchmark.md) · [社区实测：NPU 解码是 llama.cpp 的 4 倍](https://jishuzhan.net/article/2099289570509246466) · [RK3588 Gemma3-4B w8a8 转换件](https://huggingface.co/jamescallander/gemma-3-4b-it_w8a8_g128_rk3588.rkllm) · [turing-rk1-cluster（RK3588 K8s + NPU）](https://github.com/freed-dev-llc/turing-rk1-cluster) · [端侧 LLM 系统性综述](https://europepmc.org/article/PPR/PPR1208649) · [Thoughtworks 技术雷达：小模型](https://www.thoughtworks.com/zh-cn/radar/techniques/small-language-models)

**推理 / KV**：[llama.cpp v0.6.0](https://github.com/ggml-org/llama.cpp/releases/tag/v0.6.0) · [vLLM × TileRT](https://vllm.ai/blog/2026-07-14-vllm-tilert-pd) · [TileRT README（硬要求）](https://github.com/tile-ai/TileRT) · [vLLM sm75 fp8-KV PR](https://github.com/vllm-project/vllm/pull/45829) · [LMCache × Mooncake](https://blog.lmcache.ai/en/2026/05/26/when-open-source-meets-open-source-a-joint-effort-between-lmcache-and-mooncake/) · [PD 分离架构研究](https://zenodo.org/records/19316904) · [TPLA：PD 分离的张量并行潜在注意力](https://dl.acm.org/doi/abs/10.1145/3779212.3790237)

**平台 / 调度**：[llm-d v0.7](https://llm-d.ai/blog/llm-d-v0.7-from-feature-introduction-to-production-hardening) · [KServe v0.19](https://kserve.github.io/website/blog/kserve-0.19-release) · [KServe v0.18](https://kserve.github.io/website/blog/kserve-0.18-release) · [KServe v0.17](https://kserve.github.io/website/blog/kserve-0.17-release) · [KV-cache 感知路由（IBM）](https://research.ibm.com/publications/kv-cache-wins-you-can-feel-building-ai-aware-llm-routing-on-kubernetes) · [HAMi](https://project-hami.io/docs/next/get-started/choose-your-setup) · [K8s GenAI 推理评估论文](https://browse-export.arxiv.org/pdf/2602.04900)

**Agent / 记忆 / 检索**：[自托管 Agent 记忆对比 2026-08](https://raw.githubusercontent.com/vectorize-io/hindsight/b4c9071d4cdaa2174d9d9b509a7c9fcae21024c5/hindsight-docs/blog/2026-08-11-open-source-agent-memory-systems.md) · [中文全景（附录15）](https://github.com/cdavid817/awesome-agent-tutorial) · [VLDB: Data Management for Agentic Memory](https://dl.acm.org/doi/abs/10.14778/3827998.3828145) · [Agent 记忆架构（Episodic/Semantic/Working）](https://zenodo.org/records/21921640) · [CNCF 评估 MCP](https://tech.yahoo.com/ai/meta-ai/articles/cncf-evaluates-mcp-cloud-native-142016206.html) · [MCP Registry v1.4.0 进展](https://cloud.tencent.cn/developer/article/2611536) · [Is GraphRAG Needed? (ACL 2026)](https://aclanthology.org/2026.gem-main.40/) · [多模态 GraphRAG](https://ieeexplore.ieee.org/document/11536532)

**训练 / 安全 / 评测**：[Gemma4-2B 强化学习教程](https://learn.microsoft.com/zh-cn/azure/databricks/machine-learning/ai-runtime/examples/tutorials/sgc-rl-gemma4-2b) · [在 AI PC 上高效微调](https://huggingface.co/blog/dmsuehir/efficient-llm-fine-tuning-on-intel-ai-pcs) · [Prompt Injection 防御架构 2026](https://safeguard.sh/resources/blog/prompt-injection-defense-architectures-2026) · [Stanford AI Index 2026](https://hai.stanford.edu/ai-index/2026-ai-index-report/technical-performance)

---

## 11. 待办（尚未实施）

- [ ] 拉 `rknn-llm` 工具链，在 OPi5 上跑通 Qwen3.5-2B（NPU），记录 TTFT/吞吐/功耗
- [ ] 做同一模型的 NPU vs llama.cpp CPU 对照
- [ ] 决定本地模型服务进集群的形态（独立 Deployment + llm-service 新别名 tier）
- [ ] 记忆层选型：Hindsight（极简）vs Mem0（生态）vs Graphiti（时序）——先用最小可用集
- [ ] reranker 与 contextual retrieval 的 A/B（对照 47 ms 基线）
- [ ] 2070S 上测 llama.cpp v0.6.0 MTP 投机解码的实际加速比
- [ ] （可选）把 NPU 服务包成 MCP 工具，接入已有 `panghu-mcp`
