# DSH、Hermes、Pi 专用网关方案退役记录

2026-10-19：三个通用 Agent 采用各自的 `custom-llm` 公网直连配置，用户明确同意清理原先预留的专用网关路由与网络例外。当前配置步骤及应用验证状态见 [直连接入记录](../../panghu_chat/docs/agents-custom-llm.md)。

## 清理范围

| 对象 | 原作用 | 处理 |
|---|---|---|
| `dsh-trusted`、`pi-trusted`、`hermes-trusted` | 各 Agent 独立选择共享上游 | 从 `k8s.yaml` 与 `config.example.json` 的 routes 中删除 |
| `dsh/llm-service-egress` | DSH web → llm-service | 删除源清单与集群对象 |
| `hermes/llm-service-egress` | Hermes web → llm-service | 删除源清单与集群对象 |
| `pi/llm-service-egress` | 当前 `pi/pi` → llm-service | 删除源清单与集群对象 |
| `llm/llm-agent-clients` | 网关接受以上三个 namespace + app 组合 | 从网关清单移除，并删除集群对象 |

`custom`、`deepseek`、`openai` 共享上游以及原有七条通用/固定路由继续服务其他业务。`active_upstream`、其余路由的 defaults/tier/timeout 和所有凭据不变。

三个 Agent 的默认拒绝、内网隔离、公网 HTTPS 443、DNS、登录及工具/发布网络规则继续保留。DSH runner 和 Hermes publisher 未参与此次放行撤销。直连配置使用上游 API Key，无需网关调用令牌。

## 部署顺序

1. 保存四条现有 NetworkPolicy、网关 Deployment 与实际引用的不可变 ConfigMap，记录其他网络策略和 Agent Pod 身份作为比较基线。
2. 提交并同步源清单及文档，确认远端检出包含三个策略文件的删除。
3. 精确删除四条旧策略；普通 `kubectl apply` 不会替你删除已移出清单的对象：

   ```bash
   KUBECONFIG=/etc/kubernetes/super-admin.conf kubectl -n dsh delete networkpolicy llm-service-egress --ignore-not-found
   KUBECONFIG=/etc/kubernetes/super-admin.conf kubectl -n hermes delete networkpolicy llm-service-egress --ignore-not-found
   KUBECONFIG=/etc/kubernetes/super-admin.conf kubectl -n pi delete networkpolicy llm-service-egress --ignore-not-found
   KUBECONFIG=/etc/kubernetes/super-admin.conf kubectl -n llm delete networkpolicy llm-agent-clients --ignore-not-found
   ```

4. 从三个主 Agent 容器检查中转站 `/v1/models` 的 HTTPS 可达性，以及集群内网关访问已被阻断。未提供上游密钥时，401 是预期的连通性结果，不代表推理验收。
5. 用当前线上镜像经 `render-deploy.py` 生成新的不可变 ConfigMap 及匹配的 Deployment，应用并等待滚动完成。普通完整部署入口为 `bash llm-service/deploy.sh --skip-build`；本次配置清理可直接应用渲染结果，避免无关凭据同步。不要直接 apply 含 `latest` 和占位 ConfigMap 名称的源模板。
6. 确认网关健康、模型目录只剩原有七条路由、这些路由的解析 revision 不变，现有通用调用方仍能访问。三个 Agent 不需要重启。

## 规格与历史

原 OpenSpec change 为 `add-independent-agent-routes`。它曾增加三个 trusted 别名，均显式引用 `custom`、超时 120 秒，不随 `active_upstream` 切换；网关测试和三个别名的实际请求当时通过。后续 `allow-agent-llm-service-access` 开放的专用 NetworkPolicy 仅覆盖主 Agent Pod，没有覆盖 DSH runner 或 Hermes publisher。

这次撤销的是该预留接入方案。新的 OpenSpec change `retire-unused-agent-gateway-access` 记录别名与网络例外的退役，以及其他业务路由和网络隔离保留的要求；项目仍为根 `.openspec-project.json` 指定的独立 `armbianbegin` 项目。

该变更已校验通过并应用到主规格，未归档；应用后规格版本为 `1558323180e9f80dfbaee26cbfaebe0f465b4596`。

## 验收记录

- 源变更：主仓库 `17ec945`、`panghu_chat` 子模块 `0208250`，已推送并同步到管理节点。
- 本地现有网关测试 54 项通过；部署配置与示例一致，只移除三个路由，其他 YAML 资源 spec 不变；`custom` 与 `deepseek` 两种渲染均通过检查。
- 备份与验收结果保存于管理节点 `/root/retire-agent-gateway-20261019T131916Z/`，包含 `networkpolicies.json`、`deployment.json`、`configmaps.json`、`network-before.json`、`network-after.json`、`network-final.json` 和 `gateway-after.json`。
- 四条专用 NetworkPolicy 已删除，其余 21 条策略 spec 与基线完全一致。三个主 Agent 对网关 Service:80 和 Pod:8000 均超时，对公网中转站 `/v1/models` 均返回未鉴权 401；三个 Pod UID 与全部容器重启计数未变。
- 网关沿用 `arm-cluster-master:5000/llm-service:547980f`，配置为 `llm-service-config-fa03fe6fac9c`。服务端 dry-run 确认 Deployment 只改变 ConfigMap 引用，滚动部署完成，readiness 为 ready。
- 通过现有 `data/rag-service` 验证健康接口 200、鉴权模型目录恰为保留的七条路由。各路由解析元数据和 revision 均与清理前相同；对三个退役别名的鉴权请求均按未知模型返回 400。
- 滚动更新后调用方计数由旧进程的 22 变为 25：新进程与当前 Secret 都有 25 个 `LLM_TOKEN_*` 键，其中包括 DSH、Hermes、Pi 三个键。本次没有更新 Secret、ExternalSecret 或 Vault，也没有删除这些凭据；此计数变化单独记录，不宣称调用方数量未变。

公网探测只证明连接可达；Pi 直连配置与模型对话仍待用户确认，本次未触发实际模型推理或 Agent 工具循环。
