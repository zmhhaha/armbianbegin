# Panghu Agent — Secret 迁移追踪

## 状态: 🟡 进行中（research-agent、scientific-agent 已完成，daofaziran-agent、fofawubian-agent 待写入）

## 组件信息

| 属性 | 值 |
|------|-----|
| **命名空间** | `research-agent`, `scientific-agent`, `daofaziran-agent`, `fofawubian-agent` |
| **Secret 名称** | `agent-secret`（各 namespace 共用同名但独立副本） |
| **Vault 路径** | `secret/data/research-agent/api`, `secret/data/scientific-agent/api`, `secret/data/daofaziran-agent/api`, `secret/data/fofawubian-agent/api` |
| **现有文件** | `panghu_agent/k8s/secret.yaml` |

## 需要迁移的密钥

| 密钥 | 迁移到 Vault | ExternalSecret | 原文件清理 |
|------|-------------|----------------|-----------|
| `OPENAI_API_KEY` (research) | ✅ | ✅ | ⏳ |
| `CUSTOM_API_KEY` (research) | ✅ | ✅ | ⏳ |
| ...（同前） | | | |
| `OPENAI_API_KEY` (daofaziran) | ⏳ | ✅ | ⏳ |
| `CUSTOM_API_KEY` (daofaziran) | ⏳ | ✅ | ⏳ |
| `OPENAI_API_KEY` (fofawubian) | ⏳ | ✅ | ⏳ |
| `CUSTOM_API_KEY` (fofawubian) | ⏳ | ✅ | ⏳ |

## 迁移步骤

- [x] Step 1-3: research-agent 完成
- [ ] Step 4: 清理 `panghu_agent/k8s/secret.yaml`
- [ ] Step 5: 写入 daofaziran-agent 的密钥到 Vault:
  ```bash
  kubectl exec -n vault vault-0 -- vault kv put secret/daofaziran-agent/api \
    OPENAI_API_KEY="sk-xxx" \
    CUSTOM_API_KEY="sk-xxx"
  ```
- [x] Step 6: 创建 daofaziran-agent ExternalSecret
- [ ] Step 7: 创建 daofaziran-agent ConfigMap:
  ```bash
  kubectl create configmap agent-config -n daofaziran-agent \
    --from-literal=PROVIDER=deepseek \
    --from-literal=CUSTOM_API_BASE=http://47.109.107.37/v1 \
    --from-literal=CUSTOM_MODEL=deepseek-v4-pro \
    --dry-run=client -o yaml | kubectl apply -f -
  ```
- [ ] Step 8: 重启 daofaziran-agent api pod
- [ ] Step 9: 写入 fofawubian-agent 密钥到 Vault（同样步骤）
- [x] Step 10: 创建 fofawubian-agent ExternalSecret
- [ ] Step 11: 创建 fofawubian-agent ConfigMap + restart

## 备注
...

