# RAG 服务可行性 Spike

> 对应 OpenSpec change：`add-rag-service`（项目 `armbianbegin`）。
> 实测时间：2026-09-10，集群 `192.168.137.0/24`（ARM64）。
> 本文是可行性验证结论，非实现文档；实现规格见 OpenSpec `rag-service` 主 specs。

## 结论摘要（TL;DR）

**方案可行**，在现有 ARM64 集群上可以零 GPU 落地 RAG：

- Elasticsearch 8.15.3 的 `dense_vector` + HNSW + `knn` 工作正常，混合检索（keyword + 向量）端到端跑通，**hybrid 查询 47ms**。
- `bge-small-zh-v1.5` 在 RK3588 CPU 上跑 onnxruntime，**单条向量化 18.7ms、吞吐 48.7 docs/s、峰值内存约 470MB**。
- 中文关键词检索用镜像内置的 **IK**（索引 `ik_max_word` / 查询 `ik_smart`）+ 版本化领域词典；语义召回走向量，两者 RRF 融合。
- 一个关键约束：**ES 堆只有 2GB**，向量容量上限约 20～35 万条（pilot 规模绰绰有余）。

## 一、集群现状

| 节点 | 角色 | CPU | 内存 | SoC | 备注 |
|---|---|---|---|---|---|
| arm-cluster-master | control-plane | 8C | 15.5G | RK35xx | |
| orangepi5-max-server1 | worker | 8C | 15.5G | **RK3588** | ES/PG/Redis 所在，带 NPU |
| nanopct4-server1/2/3 | worker ×3 | 6C | 3.66G | RK3399 | 内存极紧，不适合放 embedding |

- ES 单副本、固定在 `orangepi5-max-server1`，`nodeSelector` 已钉死。
- 无 metrics-server，资源观测需直接 SSH。

## 二、Elasticsearch 侧实测

| 项 | 值 |
|---|---|
| 版本 | 8.15.3（Lucene 9.11.1） |
| 集群 | hubo-search，green，单节点（**spike 时为空**，便于做实验） |
| 资源 | requests 1000m/3Gi，limits 2C/4Gi；JVM `-Xms2g -Xmx2g` |
| 插件 | `analysis-ik 8.15.3`（镜像内置）+ 版本化词典 `domain-v1.dic` |

### 2.1 中文分词（IK 已装）

对比一下：ES 自带的 `standard` 分词器会把中文**切成单字**（`<IDEOGRAPHIC>`），
`match("历史")` 会命中含"历"或"史"的任意文本——**召回高、精度差**。本项目不用它。

镜像内置 `analysis-ik 8.15.3`（与 ES 版本一致），并加载版本化领域词典
`es/analysis/domain-v1.dic`（由 `IKAnalyzer.cfg.xml` 的 `ext_dict` 引入）：

```
ik_max_word（索引）"历史学基础，史官传统" -> 历史学/历史/史学/基础/史官/传统
ik_smart（查询）   "历史学基础"          -> 历史学/基础
```

实测 `match("历史")` 只命中真正含"历史"的文档，不再退化成按字乱命中。

词典覆盖有限，专名（如"四圣谛"当前会被切成 四/圣/谛）需按需往 `domain-v1.dic` 增补；
**词典或 analyzer 变更需重建镜像并重建受影响索引**——详见 `es/README.md`。

### 2.2 向量 + 混合检索冒烟

| 测试 | 结果 |
|---|---|
| `dense_vector` + HNSW + `knn`（3 维冒烟） | 正常，冷启动 247ms |
| 512 维 bulk 灌 10 条真实向量 | 200ms（含 refresh） |
| **hybrid 查询（`match` + `knn`）** | **47ms（热）**，排序正确（史记/左传排前） |

`bool.should = [match, knn]` 的混合检索机制可用；检索质量取决于权重调参，留待实现阶段。

## 三、Embedding 侧实测

模型：`bge-small-zh-v1.5`（BERT-small，4 层 8 头，24M 参数，**512 维**，512 token 截断）。
运行时：onnxruntime（CPU），模型文件 `model_optimized.onnx`。

| 线程数 | 吞吐 docs/s | 单条延迟 ms | 峰值内存 MB |
|---|---|---|---|
| 1 | 14.8 | 62.7 | 462 |
| **4** | **48.7** | **18.7** | 471 |
| 8 | 40.6 | 41.7 | 467 |

- 模型加载 0.24s，加载后常驻 RSS ~170MB。
- **4 线程最优**（RK3588 是 4×A76 + 4×A55 大小核，8 线程反而因大小核调度变慢）。
- 正确性 sanity：`sim(历史学研究, 历史学基础)=0.69`，`sim(历史学研究, 吃饭)=0.19`，语义区分正常。

### 3.1 模型获取（重要坑）

`huggingface_hub` 新版默认走 **xet/CAS** 下载，`hf-mirror.com` 不代理其 CAS 服务器，直接 `HF_HUB_DISABLE_XET=1` 也未能可靠绕过。**可行的方式是用 fastembed 注册表里给的 Google Cloud Storage 直链**：

```bash
curl -L -o bge.tar.gz \
  https://storage.googleapis.com/qdrant-fastembed/fast-bge-small-zh-v1.5.tar.gz
tar -xzf bge.tar.gz   # 解出 fast-bge-small-zh-v1.5/{model_optimized.onnx,tokenizer.json,...}
```

依赖：`pip install onnxruntime tokenizers`（两者都有 ARM64 wheel）。

## 四、索引 Schema 草案

```json
{
  "mappings": {
    "properties": {
      "content":          { "type": "text" },
      "content_vector":   { "type": "dense_vector", "dims": 512, "index": true, "similarity": "cosine" },
      "collection":       { "type": "keyword" },
      "agent":            { "type": "keyword" },
      "source_id":        { "type": "keyword" },
      "chunk_seq":        { "type": "integer" },
      "work":             { "type": "keyword" },
      "author":           { "type": "keyword" },
      "topic":            { "type": "keyword" },
      "source_type":      { "type": "keyword" },
      "language":         { "type": "keyword" },
      "edition":          { "type": "keyword" },
      "copyright_status": { "type": "keyword" },
      "provenance":       { "type": "keyword" },
      "ingest_ts":        { "type": "date" }
    }
  }
}
```

要点：
- `content_vector` 固定 **512 维**（`bge-small-zh-v1.5` 实际维度，**不是 384**）。换模型/改维度 → 新建索引版本并重灌（spec 已约束）。
- 过滤字段全部 `keyword`（精确匹配），用于 collection 隔离与元数据过滤。
- `content` 用 `text` + IK（索引 `ik_max_word` / 查询 `ik_smart`）做关键词召回；语义召回靠 `content_vector` 的 `knn`，两者 RRF 融合。

## 五、资源估算

### 5.1 Embedding 服务

| 项 | 估算 |
|---|---|
| 副本 | 1（pilot） |
| CPU | 0.5～1 核（4 线程） |
| 内存 | requests 512Mi、limits 1Gi（峰值约 470MB） |
| 单条查询向量化 | ~19ms |
| 批量入库吞吐 | ~49 docs/s（1000 条约 20s，1 万条约 3.5 分钟） |

### 5.2 ES 向量容量（2GB 堆约束）

- 512 维 float32 = 2KB/向量，叠加 HNSW 图开销约 1.5～2 倍 → **约 3～4KB/向量（堆内）**。
- ES 堆 2GB，向量安全预算按 ~1GB 计 → **约 20～35 万条向量**。
- pilot（8 个 agent × 数百～数千条 chunk）仅占几 MB～几十 MB，**远未触顶**；但"把整个仓库/历史内容全量索引"会超，需先扩容堆或换单列存储（backlog）。

### 5.3 端到端 `/v1/query` 延迟预算

| 环节 | 延迟 |
|---|---|
| embedding 单条 | ~19ms |
| ES hybrid 查询 | ~47ms（热） |
| LLM 生成 | 主导项（取决于 provider，未在本 spike 测） |

## 六、关键决策与风险

1. **向量 + IK 关键词双通道**：语义走向量，专名/术语走 `ik_max_word`，RRF 融合；元数据过滤走 `keyword` 精确匹配。
2. **embedding 线程固定 4**，不要设 8（大小核）。
3. **模型下载**：spike 用 GCS 直链绕开 hf-hub xet；`embedding-service` 已改为国内源 hf-mirror（见该服务 README）。
4. **维度=512**，schema 与重灌逻辑都以此为准。
5. ES 单节点无高可用——pilot 可接受，生产前需评估（副本/冷备）。
6. ES 堆 2GB 是容量天花板，超出 pilot 规模前先解决（扩容或向量外置）。

## 七、复现

```bash
# 1) 下载模型（spike 用 GCS 直链；生产见 embedding-service，走 hf-mirror 国内源）
curl -L -o bge.tar.gz https://storage.googleapis.com/qdrant-fastembed/fast-bge-small-zh-v1.5.tar.gz
tar -xzf bge.tar.gz

# 2) 依赖
pip install onnxruntime tokenizers

# 3) 推理（示例，CLS 池化 + L2 归一化）
#   input: input_ids / attention_mask / token_type_ids
#   output: last_hidden_state[:, 0, :] -> normalize
```

完整 benchmark 脚本与 ES 检查脚本见 spike 期间的 `/root/spike/`（服务器临时目录，已可清理）。
