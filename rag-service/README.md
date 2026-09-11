# rag-service

内部 RAG API，使用 Elasticsearch、embedding-service 和可选的 OpenAI-compatible LLM。

```bash
bash build.sh --push
bash deploy.sh
```

部署前需先运行 embedding-service，并确保 `elasticsearch-secret` 已由 Vault 同步。服务使用 ClusterIP，不提供公网入口。
