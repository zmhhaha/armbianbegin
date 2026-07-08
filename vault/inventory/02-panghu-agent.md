# Panghu Agent — Secret 迁移追踪

## 状态: 🟡 进行中（research-agent 已完成）

## 组件信息

| 属性 | 值 |
|------|-----|
| **命名空间** | `research-agent`, `scientific-agent` |
| **Secret 名称** | `agent-secret`（两个 namespace 共用同名但独立副本） |
| **Vault 路径** | `secret/data/research-agent/api`, `secret/data/scientific-agent/api` |
| **现有文件** | `panghu_agent/k8s/secret.yaml` |

## 需要迁移的密钥

| 密钥 | 迁移到 Vault | ExternalSecret | 原文件清理 |
|------|-------------|----------------|-----------|
| `OPENAI_API_KEY` (research) | ✅ | ✅ | ⏳ |
| `CUSTOM_API_KEY` (research) | ✅ | ✅ | ⏳ |
| `PROVIDER` (research/config) | ✅ | ✅ | ⏳ |
| `CUSTOM_API_BASE` (research/config) | ✅ | ✅ | ⏳ |
| `CUSTOM_MODEL` (research/config) | ✅ | ✅ | ⏳ |
| `OPENAI_API_KEY` (scientific) | ⏳ | ⏳ | ⏳ |
| `CUSTOM_API_KEY` (scientific) | ⏳ | ⏳ | ⏳ |
| `PROVIDER` (scientific/config) | ⏳ | ⏳ | ⏳ |
| `CUSTOM_API_BASE` (scientific/config) | ⏳ | ⏳ | ⏳ |
| `CUSTOM_MODEL` (scientific/config) | ⏳ | ⏳ | ⏳ |

## 迁移步骤

- [x] Step 1: 在 Vault 中写入 research-agent 的 API Key 和 Config
- [x] Step 2: 为 research-agent 创建 ExternalSecret（仅 Secret）
- [x] Step 3: 应用并验证同步
- [ ] Step 4: 清理 `panghu_agent/k8s/secret.yaml`
- [ ] Step 5: 写入 scientific-agent 的密钥到 Vault
- [ ] Step 6: 验证 scientific-agent 同步

## 备注

- 两个命名空间使用同名 Secret `agent-secret`，但值可能不同
- Vault 路径需区分: `research-agent/api` 和 `scientific-agent/api`
- **ConfigMap（`agent-config`）手动维护**，因 ESO v2.7.0 CRD 不支持 template.kind.ConfigMap：
  ```bash
  kubectl create configmap agent-config -n <ns> \
    --from-literal=PROVIDER=deepseek \
    --from-literal=CUSTOM_API_BASE=http://... \
    --from-literal=CUSTOM_MODEL=deepseek-v4-pro \
    --dry-run=client -o yaml | kubectl apply -f -
  ```
- Deployment 通过 `envFrom` + `secretRef` 引用，迁移后无需修改
- ConfigMap 更新后需 restart Pod 才能生效
