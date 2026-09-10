# RAG 服务可行性 Spike

> 对应 OpenSpec change：`add-rag-service`（项目 `armbianbegin`）。
> 实测时间：2026-09-10，集群 `192.168.137.0/24`（ARM64）。
> 本文是可行性验证结论，非实现文档；实现规格见 OpenSpec `rag-service` 主 specs。

## 结论摘要（TL;DR）

**方案可行**，在现有 ARM64 集群上可以零 GPU 落地 RAG：

- Elasticsearch 8.15.3 的 `dense_vector` + HNSW + `knn` 工作正常，混合检索（keyword + 向量）端到端跑通，**hybrid 查询 47ms**。
- `bge-small-zh-v1.5` 在 RK3588 CPU 上跑 onnxruntime，**单条向量化 18.7ms、吞吐 48.7 docs/s、峰值内存约 470MB**。
- 两个关键约束：**ES 没有中文分词器（无 IK）**，keyword 只能当弱信号、向量必须是主信号；**ES 堆只有 2GB**，向量容量上限约 20～35 万条（pilot 规模绰绰有余）。

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
| 集群 | hubo-search，green，单节点，**当前 0 shard（空）** |
| 资源 | requests 1000m/3Gi，limits 2C/4Gi；JVM `-Xms2g -Xmx2g` |
| 插件 | **无**（未装 IK 中文分词器） |

### 2.1 中文分词行为（决定性发现）

`standard` 分词器把中文**切成单字**（token 类型 `<IDEOGRAPHIC>`）：

```
"历史学基础" -> [历][史][学][基][础]
```

后果：`match` 对中文退化成"按字 OR"，`match("历史")` 能命中含"历"或"史"的任意文本——**召回高、精度差，没有词级语义**。因此：

- **向量检索必须是主召回通道**；keyword 只用于元数据精确过滤（`collection`/`work`/`topic` 等 `keyword` 字段）。
- 若要词级 keyword 召回，两条可选路径（pilot 阶段都**不是必需**）：
  1. 编译安装 `analysis-ik`（社区插件，需为 ES 8.15.3 编译 ARM64 二进制，无官方现成包）；
  2. 对文本字段加 `ngram`（bigram）分词器做子串召回（内置、免费，但索引体积变大且仍偏噪）。

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
- `content` 用 `text`（standard 分词）仅作弱 keyword 信号；主召回靠 `content_vector` 的 `knn`。

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

1. **向量为主、keyword 为辅**（无 IK 下的必然选择）；元数据过滤走 `keyword` 精确匹配。
2. **embedding 线程固定 4**，不要设 8（大小核）。
3. **模型下载走 GCS 直链**，绕开 hf-hub xet；仓库内应固化下载/校验脚本。
4. **维度=512**，schema 与重灌逻辑都以此为准。
5. ES 单节点无高可用——pilot 可接受，生产前需评估（副本/冷备）。
6. ES 堆 2GB 是容量天花板，超出 pilot 规模前先解决（扩容或向量外置）。

## 七、复现

```bash
# 1) 下载模型（GCS 直链）
curl -L -o bge.tar.gz https://storage.googleapis.com/qdrant-fastembed/fast-bge-small-zh-v1.5.tar.gz
tar -xzf bge.tar.gz

# 2) 依赖
pip install onnxruntime tokenizers

# 3) 推理（示例，CLS 池化 + L2 归一化）
#   input: input_ids / attention_mask / token_type_ids
#   output: last_hidden_state[:, 0, :] -> normalize
```

完整 benchmark 脚本与 ES 检查脚本见 spike 期间的 `/root/spike/`（服务器临时目录，已可清理）。
