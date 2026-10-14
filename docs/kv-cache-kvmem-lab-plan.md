# KV Cache / KV Mem 实验评估：哪些能在本机玩

> 来源：DeepSeek 分享会话 <https://chat.deepseek.com/share/4k7ux8ayhn570uozl6>（2026-10-05，单轮问答，主题「kvmem kvcache 训练与推理」）。
> 本文对该会话的内容做**名词核实 + 硬件可行性评估**，并列出本机（Windows 主机 + Armbian 集群）真能动手的实验。
> 姊妹篇：[softroce-dpdk-spdk-lab-plan.md](softroce-dpdk-spdk-lab-plan.md)（存储/网络数据面），两者在「KV 分层落到 NVMe」处交汇。

---

## 1. 那份分享讲了什么

一句话区分：

| | KV Cache | KV Mem |
|---|---|---|
| 是什么 | 推理期**计算优化**：缓存历史 K/V，避免重复计算 | 一种**记忆架构/系统**：把历史 KV 当可检索记忆做分层存储 |
| 出现在 | 只在推理（decode 阶段），训练时不存在 | 训练可参与（学"压缩友好"表示），推理期做跨层调度 |
| 核心矛盾 | 显存**容量**与**带宽** | 存储层级之间的**调度/检索效率** |
| 优化手段 | 结构压缩（MQA/GQA/MLA）、淘汰稀疏（H2O/SnapKV）、训练感知压缩 | 查询条件化检索、有界工作集、与推理引擎集成（llama.cpp） |

### 1.1 名词核实（**重要**：那份回答里的引用标记是模型生成的，不能当出处）

| 名字 | 核实结果 |
|---|---|
| **KVMem** | ✅ **真实存在**：[KVMem: Virtualizing Million-Token Agent Workspaces on a Consumer GPU](https://www.semanticscholar.org/paper/KVMem%3A-Virtualizing-Million-Token-Agent-Workspaces-Chai-Wang/0b18b6a7fd2a8e97eb549ba6c0d2ccb1cadf45ea)。副标题就是 "on a Consumer GPU" —— 和本机 2070S 同一档硬件，值得精读 |
| **KV-CAT** | ⚠️ **这个名字没查到**。内容对得上的是 [Training Transformers for KV Cache Compressibility](https://ar5iv.labs.arxiv.org/html/2605.05971)（ICML 2026，牛津/NVIDIA 等，讲"训练时让模型学会断舍离"）。按真名检索，别按 KV-CAT 找代码 |
| **Trellis（元学习压缩 KV）** | ❓ **未能证实**。同名的知名项目是 3D 生成方向的 Trellis，与 KV cache 无关。当作存疑信息 |
| `--kvmem-budget` 这类"参数" | ❌ 看着像编造的接口细节。KVMem 是论文不是现成 CLI，别去 grep 这个 flag |
| MQA / GQA / MLA、H2O、SnapKV、PagedAttention、Prefill/Decode 拆分 | ✅ 都是真实且成熟的概念，下面按能不能跑分类 |

---

## 2. 你的算力盘点（实测）

| 资源 | 规格 | 对这条线的意义 |
|---|---|---|
| **RTX 2070 SUPER** | 8192 MiB，compute **7.5**（Turing），驱动 580.88 | 主力。有 INT8/FP16 Tensor Core；**没有 BF16、没有 FP8、没有 FlashAttention-2**（要 sm_80+） |
| **CUDA Toolkit（Windows 侧）** | 只有 **v9.0**（2016 年） | ⚠️ 别拿它编任何现代框架。正确做法：Windows 原生用 llama.cpp 的**预编译 CUDA 包**（只要驱动）；Linux 侧走 WSL2，CUDA 由驱动透传，**不需要** Windows 上的 toolkit |
| i7-4770 | 4C/8T，AVX2，无 AVX-512 | CPU 推理偏慢（prompt 处理是算力瓶颈）；`-nkvo` 实验的"主机内存"就是它的 16 GB |
| D: 盘 | 315 GB 空闲 | 够放模型（7B Q4 ≈ 4–5 GB）+ 实验数据；C: 只剩 10 GB，别放模型 |
| OPi5 Plus / Max | RK3588 8C / 16 GB，NPU 6 TOPS | 能跑 llama.cpp **CPU** 推理（小模型、慢）。NPU 只走 Rockchip `rknn-llm` 那套，与 KV cache 研究不对路 |
| NanoPC-T4 ×3 | RK3399 6C / 3.85 GB | ❌ 基本出局，连 1.5B 都吃力 |

**一个关键事实**：仓库里目前**没有任何本地推理**——[llm-service](../llm-service/) 是云端 API 网关（`deepseek-v4-flash` / `gpt-4o-mini`），embedding 是 RK3588 CPU 上的 ONNX（见 [rag-service-spike.md](rag-service-spike.md)）。所以这条线是全新的，第一步不是"改造"，而是"先跑起一个本地推理"。

---

## 3. 可行性矩阵

### A. 必玩：今天就能出数字（Windows 原生 llama.cpp）

| 技术 | 怎么做 | 能测到什么 |
|---|---|---|
| **KV Cache 显存账本** | llama.cpp **预编译 CUDA 包**（GitHub Releases 的 `llama-*-bin-win-cuda-x64.zip`，无需编译），`-ngl 99`，`--ctx-size` 从 4k 递增到 32k | 亲手验证"KV 随 ctx 线性增长、长上下文下会超过权重本身"；`nvidia-smi` 曲线就是结论 |
| **KV 量化** ⭐最省事 | `-ctk q8_0 -ctv q4_0`（= `--cache-type-k/v`） | 同 ctx 下显存降幅 + 生成质量变化，用 `llama-perplexity` 量化代价 |
| **KV 放主机内存** | `-nkvo`（no KV offload），配 16 GB 内存 | "显存墙"到底卡在哪一步；换来多少 tok/s 的下降 |
| **MHA vs GQA 对比** | 选架构不同的模型跑同一 ctx：GPT-2/Llama-2-7B（MHA）、Qwen2.5-1.5B/7B（GQA）、Mistral-7B（GQA+SWA） | 同一上下文长度下 KV 占用差几倍——这就是 GQA 存在的理由 |
| **prefix / prompt cache** | `--prompt-cache`、`cache_prompt` | 复用前缀能省掉多少 prefill：Agent/RAG 场景的真实收益 |

**验收方式**：每项都留一条 `nvidia-smi --query-gpu=memory.used --format=csv -l 1` 的采样记录 + tok/s，做成一张表。这是后面所有"优化声称"的对照基线。

### B. 值得玩：需要 Linux（WSL2 Debian + CUDA 透传）

| 技术 | 怎么做 | 价值 |
|---|---|---|
| **PagedAttention / vLLM** | WSL2 Debian 里装 vLLM（Turing 可用但有限制：无 FlashAttention-2/FP8，注意力走 XFormers/Triton 分支）。`--gpu-memory-utilization`、`--max-model-len`、`--swap-space`（KV 换到主机 RAM） | 真实工业实现的分页 KV 管理，和 llama.cpp 的实现对比 |
| **prefix caching** | `--enable-prefix-caching` | 多轮 Agent 场景的命中率/延迟收益 |
| **LMCache（KV connector）** ⭐ | [LMCache 架构](https://docs.lmcache.ai/zh_CN/developer_guide/architecture.html) + [vLLM 的 LMCache 示例](https://docs.vllm.ai/en/stable/examples/disaggregated/lmcache/)；后端可选 CPU / **本地磁盘(NVMe)** / 远端 | **这就是"KV Mem 分层存储"的现成工程实现**，也是与 [softroce-dpdk-spdk-lab-plan.md](softroce-dpdk-spdk-lab-plan.md) 的交汇点 |
| **H2O / SnapKV** | 研究代码，需要 HF transformers + 改注意力；1B–3B 模型在 8 GB 上够跑 | 亲手看"淘汰低分 token"的精度-显存权衡 |
| **KVMem 的思路** | 论文不是框架：先自己写一个最小版"KV 块 → 文件 → 按查询加载"，在 llama.cpp/vLLM 上量"检索质量 vs 加载带宽" | 复现其**核心论断**（消费级 GPU 支撑百万 token 工作空间）要哪些前提 |

### C. 只能看、不能玩

| 技术 | 为什么 |
|---|---|
| **MLA** | 唯一现实权重是 DeepSeek-V2-Lite（16B MoE），Q4 也要 ~10 GB > 8 GB 显存，必须 offload，能跑但很慢。想学 MLA 就**读实现 + 自己写小规模版本**，别指望跑整模型 |
| **训练侧压缩（Training for KV Cache Compressibility）** | 8 GB 训不了。最多做 0.5–1.5B 的 LoRA 微调，做不了"让模型学会压缩友好表示"这种规模的训练 |
| **NPU 上的 KV 实验** | RK3588 NPU 走 `rknn-llm`，是另一套栈，没有可改的 KV cache 接口；CPU 推理可以，但只适合量"KV 在内存里占多少" |

---

## 4. 第一批实验（建议顺序，半天内做完 A 组）

```powershell
# 1) 拿预编译 CUDA 版 llama.cpp（只要驱动 580.88，不需要编 CUDA）
#    GitHub Releases → llama-bXXXX-bin-win-cuda-x64.zip，解到 D:\llm\llama.cpp

# 2) 拿一个小模型（GQA）+ 一个 MHA 老模型做对照，放 D: 盘
#    例：Qwen2.5-1.5B-Instruct-GGUF(Q4_K_M) 与 gpt2 / Llama-2-7B-Chat-GGUF(Q4_K_M)

# 3) 基线：显存账本
.\llama-server.exe -m D:\llm\models\qwen2.5-1.5b-q4_k_m.gguf -ngl 99 -c 32768 --port 8080
#   另开一个窗口采样：
nvidia-smi --query-gpu=memory.used --format=csv -l 1

# 4) KV 量化对照（同 ctx、同模型，比显存与困惑度）
.\llama-cli.exe -m <model> -ngl 99 -c 32768 -ctk q8_0 -ctv q4_0 -p "test"
.\llama-perplexity.exe -m <model> -ngl 99 -c 4096 -f wiki.test.raw -ctk q8_0 -ctv q4_0

# 5) KV 不卸载到显存（KV 放主机 RAM）
.\llama-cli.exe -m <model> -ngl 99 -nkvo -c 32768 -p "test"
```

记录成表：`模型 | ctx | ctk/ctv | 显存占用 | tok/s(prefill) | tok/s(decode) | 困惑度`。

> ⚠️ 先确认 `-ctk/-ctv` 在你拿到的 llama.cpp 版本里的确切写法（不同版本用过 `--cache-type-k` / `--cache-type-v`，取值 `f16/f32/q8_0/q4_0` 等）；`llama-server --help | findstr cache` 一秒确认。

**B 组的入口**（等 A 组做完再做）：WSL2 Debian 里 `nvidia-smi` 能看到 2070S 之后，装 vLLM → 跑通 paged attention → 再接 LMCache 的本地磁盘后端，这就是"KV 落到 NVMe"的最小闭环。

---

## 5. 与存储/网络实验的交叉点

| 母题 | 上一份文档 | 这份文档 |
|---|---|---|
| 存储层级调度 | DPDK/SPDK/Soft-RoCE、NVMe-oF、Ceph OSD | KV Cache 从显存 → 主机 RAM → NVMe |
| 硬件瓶颈 | 网卡/大页/IOMMU、消费级 SSD | 8 GB 显存墙、PCIe 带宽、CPU 软 RoCE 的开销 |

两件事可以直接拼起来：在 **x86 实验 VM** 里跑 vLLM + LMCache（本地盘后端），用上一份清单里的 **NVMe/FIO 方法**去量"KV 块换入换出"打到盘上的 IOPS/带宽——这正是 KVMem 那类系统真正要解决的问题。

---

## 6. 待办（尚未实施）

- [ ] 拉预编译 llama.cpp CUDA 包 + 两个对照模型到 D: 盘，跑完 A 组的 5 个实验并留表
- [ ] 确认 `llama-server --help` 里 KV 量化参数的当前写法，回填本文
- [ ] 精读 [KVMem 论文](https://www.semanticscholar.org/paper/KVMem%3A-Virtualizing-Million-Token-Agent-Workspaces-Chai-Wang/0b18b6a7fd2a8e97eb549ba6c0d2ccb1cadf45ea)：它把 KV 块放哪、怎么检索、工作集预算怎么定
- [ ] 按真名找 [Training Transformers for KV Cache Compressibility](https://ar5iv.labs.arxiv.org/html/2605.05971) 的代码（若开源）
- [ ] WSL2 + CUDA 透传验证（`nvidia-smi` 在 WSL 里可见）→ 再上 vLLM / LMCache
- [ ] 决定是否把这份评估并入正式规划（OpenSpec，见 `AGENTS.md`）
