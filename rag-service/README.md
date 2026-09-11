# rag-service

内部 RAG API，使用 Elasticsearch、embedding-service 和可选的 OpenAI-compatible LLM。

```bash
bash build.sh --push
bash deploy.sh
```

部署前需先运行 embedding-service，并确保 `elasticsearch-secret` 已由 Vault 同步。服务使用 ClusterIP，不提供公网入口。

通过 `rag-config` 配置 OpenAI-compatible LLM：

```bash
kubectl -n data create configmap rag-config \\
  --from-literal=LLM_URL=http://llm-service.data.svc.cluster.local/v1/chat/completions \\
  --from-literal=LLM_MODEL=deepseek-v4-flash \\
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n data rollout restart deployment/rag-service
```

未配置 `LLM_URL` 时，query 返回检索片段；配置后返回 LLM 生成的回答。LLM 超时或返回格式错误时，RAG 返回 HTTP 502，不伪造生成结果。
