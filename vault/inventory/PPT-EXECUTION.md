# PPT Hermes 执行凭据

已有网站的 OAuth、数据库凭据继续使用 [PPT-SERVICE.md](PPT-SERVICE.md)。
本页只投射 Hermes 任务代理所需的一项已有上游凭据，不重建数据库、不改变网站白名单。

| Vault CLI 路径 | 字段 | Kubernetes Secret / 键 | 消费者 |
| --- | --- | --- | --- |
| `secret/llm-service/providers` | `CUSTOM_API_KEY` | `ppt-service/ppt-model-upstream` / `PPT_UPSTREAM_API_KEY` | 每次任务的模型代理 Pod |

采用 [ppt-execution-externalsecret.yaml](ppt-execution-externalsecret.yaml) 显式映射字段，沿用
`ClusterSecretStore/vault-backend`。不把 Casdoor client secret、私人 Hermes HOME 或其 `.env`
复制给执行器。上游域名、固定模型和 Responses 协议由执行配置管理，不存入密钥记录。

当前复用 llm-service 已有的供应商 key，只通过精确字段映射读取，不新建或复制 Vault
记录，不投射其他 provider/caller 字段，不修改 llm-service 的源值。应用前由管理员只检查
现有 `llm/llm-service-secret` 的 `CUSTOM_API_KEY` 非空，检查结果仅输出布尔值。
已有 key 可用后直接应用：

```bash
kubectl apply -f vault/inventory/ppt-execution-externalsecret.yaml
kubectl -n ppt-service wait --for=condition=Ready externalsecret/ppt-model-upstream --timeout=120s
```

命令不输出 API key，也不触碰已有数据库密码。ESO 使用现有
`secret/data/llm-service/providers` 路径的 `CUSTOM_API_KEY` 字段；不为网站或 Worker 配置
Vault token。当前是共享供应商凭据，不能视为独立供应商配额或独立限权 key。
以后改用专用 key 时再调整该精确映射并验证同步，不改变代理之外的消费范围。

Controller 不投射上游 Secret、不读取上游值；它只在创建代理 Pod 时引用该 Secret。
Controller 作为可信调度组件，具有 namespace 内创建 Pod 和管理一次性任务 Secret 的权限，
该权限不能描述为对同 namespace Secret 的强隔离。Worker/代理/校验沙箱不挂 Kubernetes
ServiceAccount token；上游值只进入代理进程，Worker 使用每次 attempt 新建的代理凭据。

完整构建、网络及接线顺序见
[执行部署说明](../../panghu_agent/ppt_service/deploy/hermes/README.md)。
