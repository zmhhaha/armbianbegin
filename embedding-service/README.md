# embedding-service

内部中文向量服务：bge-small-zh-v1.5、ONNX Runtime CPU、CLS 池化和 L2 归一化，输出 512 维。默认 4 个推理线程，单进程单推理请求，繁忙返回 429 和 Retry-After。

## 构建和部署

模型不进入 Git；构建时从国内可达的镜像（默认 `hf-mirror.com`）下载 `model_optimized.onnx` 和 `tokenizer.json`，pip 依赖也走国内源（默认清华 TUNA）。**摘要无需手动配置**；如需固定版本，可显式传入 `MODEL_SHA256` / `TOKENIZER_SHA256` 做校验。

```bash
bash build.sh --push
bash deploy.sh
```

默认镜像为 arm-cluster-master:5000/embedding-service:latest。部署强制拉取并重启。模型随镜像发布，运行时无需外网或 PVC。更新模型后仍必须重建对应 ES 索引，模型身份和索引版本独立于镜像标签管理。

默认源可在环境变量中覆盖：

```bash
PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
MODEL_BASE_URL=https://hf-mirror.com/Qdrant/bge-small-zh-v1.5/resolve/main \
bash build.sh --push
```

部署要求已有 data namespace；默认调度 orangepi5-max-server1。NetworkPolicy 只允许带 embedding-client: "true" 标签的集群 Pod 访问，需要 CNI 支持 NetworkPolicy。

## API

地址：http://embedding-service.data.svc.cluster.local:8080

```json
{"model":"bge-small-zh-v1.5","input":["历史学研究"],"input_type":"query"}
```

POST /v1/embeddings 返回 data[].embedding、index 和 model。input_type 默认 passage；query 添加模型要求的中文检索指令。每次 1 至 16 条，每条最多 8192 字符，模型最多 512 tokens（超长截断）；摄入端应先分块。健康接口为 /health/live 和 /health/ready。模型缺失时启动失败。

## 本地运行与验证

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
python prepare_model.py --destination models/fast-bge-small-zh-v1.5
MODEL_DIR=models/fast-bge-small-zh-v1.5 uvicorn app:app --host 127.0.0.1 --port 8080
python -m unittest discover -s tests
```

单元测试用替代模型验证接口及归一化；真实模型语义效果和 ARM64 镜像需要构建后冒烟验证。

## 已知问题与排查

**1. pip 与模型都必须走国内源**
pip 走清华源、模型走 hf-mirror。直连 PyPI / hf-hub / GCS 在这套网络上会超时或中断。

**2. 模型下载 403**
hf-mirror 会按 **User-Agent** 拦截：`curl` 能下、Python `urllib` 的默认 UA 会被 403。
`prepare_model.py` 已显式设置 `User-Agent`，改下载逻辑时别丢掉这一点。

**3. 摘要不再需要手工配置**
`build.sh` 原先强制外部传入模型摘要；现在由脚本下载后自动计算。
需要固定版本时再传 `MODEL_ONNX_SHA256` / `TOKENIZER_SHA256` 即可。

**4. 忙时会返回 429**
服务是单进程单推理 + 一把锁，**并发请求一律 429**。调用方（如 rag-service）必须自己带退避重试，
否则并发灌库会把上游打挂。

