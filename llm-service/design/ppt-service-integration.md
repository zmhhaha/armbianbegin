# PPT 工作台的模型网关接入合同

P2 是网站 SSO 配置。它不调用模型，也不需要新增 llm-service 路由、caller 或密钥。OAuth 配置归 [oauth/k8s](../../oauth/k8s/PPT.md)，敏感值映射归 [Vault](../../vault/inventory/PPT-SERVICE.md)，业务部署归 [ppt_service/deploy/k8s](../../panghu_agent/ppt_service/deploy/k8s/README.md)。

后续模型链路应为：受信控制器授权任务 → 每任务模型代理 → 配置的上游。Pi Worker 只持绑定 project/job/attempt/fencing/phase、期限与预算的任务 token；长期供应商 key 或 llm-service caller token 仅给受信代理。网站、Worker、数据库和迁移 Job 都不持长期模型凭据。取消或租约丢失要撤销任务授权并中断流，不能只改模型名称。

当前 `ppt_service/worker/model_proxy.py` 的 `ProxyConfig` 强制 HTTPS，默认 Responses 上游为 `https://custom-llm-proxy.panghuer.top/v1`。集群网关 `http://llm-service.llm.svc.cluster.local/v1` 无法仅替换 URL 接入。后续接线必须确认受控 HTTPS 或经过验证的内部传输合同、固定模型与稳定别名语义、Responses 参数、用量/预算和实际网络边界，再按 [INTEGRATION.md](../INTEGRATION.md) 新增独立 caller 及仅投射到代理的 Vault Secret。

本次不创建空壳 caller、额外别名或未经实际消费者使用的模型 Secret。已有 `llm-trusted` 路由不代替任务授权；P2 登录成功也不启用 Pi 模型执行。当前 Pi 业务和 K8s 差异见 [K8S_DEPLOYMENT_HANDOFF.md](../../panghu_agent/ppt_service/K8S_DEPLOYMENT_HANDOFF.md)。
