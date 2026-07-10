# Vault 部署与运维手册

记录了 Vault + External Secrets Operator 部署过程中的步骤、常用命令和常见问题。

---

## 目录

- [一、架构概述](#一架构概述)
- [二、部署流程](#二部署流程)
- [三、Vault 初始化配置](#三vault-初始化配置)
- [四、External Secrets Operator](#四external-secrets-operator)
- [五、常用运维命令](#五常用运维命令)
- [六、常见问题与排查](#六常见问题与排查)
- [七、KV v2 路径规则（重要）](#七kv-v2-路径规则重要)

---

## 一、架构概述

```
Vault（密钥存储 + Web UI）
    │
    ▼
External Secrets Operator（同步组件）
    │
    ▼
K8s Secret（应用读取，无需修改现有 Deployment）
```

| 组件 | 命名空间 | 端口 |
|------|---------|------|
| Vault | `vault` | 8200 (API + UI) |
| External Secrets Operator | `external-secrets` | - |

### Vault 配置

- **模式**: Standalone（单节点文件存储，非 HA Raft）
- **存储**: 文件存储，PVC `vault-data` (10Gi, Ceph RBD)
- **TLS**: 关闭（内网使用，外网由 Cloudflare Tunnel 保护）
- **Secrets Engine**: KV v2，挂载路径 `secret/`
- **认证方式**: Kubernetes Auth（ESO 用 SA JWT 认证）

---

## 二、部署流程

### 前置条件

- Helm 已安装（`debian_begin.sh` 中已装）
- kubectl 可访问集群（kubeconfig: `/etc/kubernetes/super-admin.conf`）
- 私有镜像仓库 `arm-cluster-master:5000` 可用

### Step 1: 部署 Vault

```bash
cd ~/armbianbegin/vault

# 拉取镜像并推送到私有仓库
docker pull hashicorp/vault:1.18.0
docker tag hashicorp/vault:1.18.0 arm-cluster-master:5000/hashicorp/vault:1.18.0
docker push arm-cluster-master:5000/hashicorp/vault:1.18.0

# 创建命名空间
kubectl create namespace vault

# 创建 PVC
kubectl apply -f k8s/pvc.yaml

# 安装 Helm Chart
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo update

# 注意：需替换镜像地址为私有仓库
sed "s|repository: hashicorp/vault|repository: arm-cluster-master:5000/hashicorp/vault|g" \
  helm-values/vault-values.yaml | \
helm upgrade --install vault hashicorp/vault \
  --namespace vault \
  --values /dev/stdin \
  --set server.image.tag=1.18.0 \
  --wait
```

### Step 2: 初始化 Vault

```bash
bash scripts/init-vault.sh
```

该脚本会自动完成：
1. 等待 Pod Running
2. 初始化（生成 root token + 5 份 unseal keys）
3. 解封（用 3/5 key 阈值）
4. 启用 KV v2 引擎
5. 启用 Kubernetes Auth
6. 创建 policy `kv-reader`
7. 创建 role `eso-role`（绑定 ESO ServiceAccount）

### Step 3: 安装 External Secrets Operator

```bash
# 方法一：Helm（需要 GitHub 网络可达）
helm repo add external-secrets https://charts.external-secrets.io
helm upgrade --install external-secrets external-secrets/external-secrets \
  --namespace external-secrets \
  --create-namespace \
  --values helm-values/eso-values.yaml

# 方法二：kubectl apply + server-side（推荐，避免 CRD annotation 超限）
kubectl apply --server-side -f \
  https://raw.githubusercontent.com/external-secrets/external-secrets/v2.7.0/deploy/crds/bundle.yaml
kubectl apply -f https://raw.githubusercontent.com/external-secrets/external-secrets/v2.7.0/deploy/deployment.yaml
```

### Step 4: 创建 ClusterSecretStore

```bash
kubectl apply -f k8s/cluster-secret-store.yaml
kubectl get clustersecretstore vault-backend  # 应显示 Valid/True
```

### Step 5: 写入密钥 + 创建 ExternalSecret

```bash
# 写入测试密钥
kubectl exec -n vault vault-0 -- vault kv put secret/test hello=world

# 创建 ExternalSecret
kubectl apply -f - <<EOF
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: test-secret
  namespace: default
spec:
  refreshInterval: "30s"
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: test-secret
    creationPolicy: Owner
  data:
    - secretKey: hello
      remoteRef:
        key: secret/data/test
        property: hello
EOF

# 验证
kubectl get externalsecret test-secret -n default
kubectl get secret test-secret -n default

# 清理测试
kubectl delete externalsecret test-secret -n default
kubectl exec -n vault vault-0 -- vault kv metadata delete secret/test
```

---

## 三、Vault 初始化配置

### 手动初始化步骤

如果 `init-vault.sh` 不可用，可手动执行：

```bash
# 1. 初始化
kubectl exec -n vault vault-0 -- vault operator init \
  -key-shares=5 -key-threshold=3 -format=json > vault-credentials.json

# 2. 解封（需要 3 个 key）
kubectl exec -n vault vault-0 -- vault operator unseal <key1>
kubectl exec -n vault vault-0 -- vault operator unseal <key2>
kubectl exec -n vault vault-0 -- vault operator unseal <key3>

# 3. 登录
kubectl exec -n vault vault-0 -- vault login <root_token>

# 4. 启用 KV v2
kubectl exec -n vault vault-0 -- vault secrets enable -path=secret kv-v2

# 5. 启用 Kubernetes Auth
kubectl exec -n vault vault-0 -- vault auth enable kubernetes

# 6. 配置 K8s 连接
kubectl exec -n vault vault-0 -- vault write auth/kubernetes/config \
  kubernetes_host=https://kubernetes.default.svc.cluster.local:443

# 7. 创建 policy
kubectl exec -n vault vault-0 -- sh -c 'cat > /tmp/policy.hcl << EOF
path "secret/data/*" { capabilities = ["read", "list"] }
path "secret/metadata/*" { capabilities = ["read", "list"] }
EOF
vault policy write kv-reader /tmp/policy.hcl'

# 8. 创建 role
kubectl exec -n vault vault-0 -- vault write auth/kubernetes/role/eso-role \
  bound_service_account_names=external-secrets \
  bound_service_account_namespaces=external-secrets \
  policies=kv-reader \
  ttl=24h
```

### 解封（重启后）

```bash
bash scripts/unseal.sh
# 或手动：
kubectl exec -n vault vault-0 -- vault operator unseal <key1>
kubectl exec -n vault vault-0 -- vault operator unseal <key2>
kubectl exec -n vault vault-0 -- vault operator unseal <key3>
```

### 暴露 Vault UI 到局域网

```bash
bash scripts/expose-ui.sh          # 随机端口
bash scripts/expose-ui.sh 31200   # 指定固定端口
bash scripts/expose-ui.sh --cluster  # 取消暴露（改回 ClusterIP）
```

---

## 四、External Secrets Operator

### 核心 CRD

| CRD | 作用范围 | 说明 |
|-----|---------|------|
| `ClusterSecretStore` | 集群 | 定义 Vault 后端连接（全局可用） |
| `SecretStore` | 命名空间 | 定义 Vault 后端连接（单命名空间） |
| `ExternalSecret` | 命名空间 | 从 Vault 同步一个密钥到 K8s Secret |

### ClusterSecretStore 示例

```yaml
apiVersion: external-secrets.io/v1
kind: ClusterSecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "http://vault.vault.svc.cluster.local:8200"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "eso-role"
          serviceAccountRef:
            name: "external-secrets"
            namespace: "external-secrets"    # ClusterSecretStore 必须指定
```

### ExternalSecret 示例

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: my-secret
  namespace: my-namespace
spec:
  refreshInterval: "1h"
  secretStoreRef:
    name: vault-backend
    kind: ClusterSecretStore
  target:
    name: my-secret            # 生成的 K8s Secret 名称
    creationPolicy: Owner
  data:
    - secretKey: MY_KEY       # K8s Secret 中的 key
      remoteRef:
        key: secret/data/my-app  # Vault 路径（注意必须加 data/）
        property: MY_KEY        # Vault 中的 key
```

### ESO Pod 组件

```
external-secrets-c98c44698-2jmkp                    # 主控制器
external-secrets-cert-controller-57574944dd-wvtt6    # 证书控制器
external-secrets-webhook-784f665fcd-qsrkc            # Webhook
```

---

## 五、常用运维命令

### Vault 操作

```bash
# 查看 Vault 状态
kubectl exec -n vault vault-0 -- vault status

# 写入密钥（注意路径规则 —— 不加 data/）
kubectl exec -n vault vault-0 -- vault kv put secret/oauth/oauth2-proxy \
  COOKIE_SECRET="xxx" OIDC_CLIENT_ID="xxx" OIDC_CLIENT_SECRET="xxx"

# 读取密钥（注意路径规则 —— 加 data/）
kubectl exec -n vault vault-0 -- vault kv get secret/data/oauth/oauth2-proxy

# 以 JSON 格式读取
kubectl exec -n vault vault-0 -- vault kv get -format=json secret/data/oauth/oauth2-proxy

# 列出路径下的密钥
kubectl exec -n vault vault-0 -- vault kv list secret/data/oauth/

# 删除一个密钥
kubectl exec -n vault vault-0 -- vault kv metadata delete secret/oauth/oauth2-proxy

# 查看已启用的引擎
kubectl exec -n vault vault-0 -- vault secrets list

# 查看认证方法
kubectl exec -n vault vault-0 -- vault auth list

# 查看 policy
kubectl exec -n vault vault-0 -- vault policy list
kubectl exec -n vault vault-0 -- vault policy read kv-reader

# 查看 role
kubectl exec -n vault vault-0 -- vault read auth/kubernetes/role/eso-role
```

### K8s 操作

```bash
# 查看 ESO 同步状态
kubectl get externalsecret -A
kubectl describe externalsecret <name> -n <ns>

# 查看 ClusterSecretStore 状态
kubectl get clustersecretstore vault-backend
kubectl describe clustersecretstore vault-backend

# 查看 K8s Secret（由 ESO 同步生成）
kubectl get secret <name> -n <ns>
kubectl get secret <name> -n <ns> -o jsonpath='{.data.<key>}' | base64 -d

# 查看 Vault Pod 日志
kubectl logs -n vault vault-0
kubectl logs -n external-secrets -l app.kubernetes.io/instance=external-secrets

# 端口转发访问 Vault UI
kubectl port-forward -n vault svc/vault 8200:8200

# 查看 Pod 事件
kubectl describe pod -n vault vault-0
```

---

## 六、常见问题与排查

### 问题 1：Vault Pod 一直 CrashLoopBackOff

**现象**：
```
kubectl logs vault-0 -n vault
service_registration is configured, but storage does not support HA
```

**原因**：Standalone 模式下配置了 `service_registration "kubernetes" {}`，该配置仅 HA/Raft 模式使用。

**解决**：删掉 vault-values.yaml 中的 `service_registration "kubernetes" {}`，Helm 升级修复。

---

### 问题 2：Readiness probe 一直失败

**现象**：
```
Readiness probe failed: Key        Value
---        -----
Seal Type  shamir
Initialized false
Sealed     true
```

**原因**：Vault 未初始化前，`vault status` 返回非 0 退出码，导致 readiness probe 一直失败。**这是正常的**，初始化后会自动恢复。

**解决**：执行初始化 `bash scripts/init-vault.sh`，初始化后 readiness probe 自动通过。

**注意**：`kubectl wait --for=condition=Ready` 在 Vault 未初始化时永远等不到，需改用等待 `Running` 状态。

---

### 问题 3：ExternalSecret 报 "ServiceAccount not found"

**现象**：
```
Warning  UpdateFailed  ...  cannot get Kubernetes service account "external-secrets": ServiceAccount "external-secrets" not found
```

**原因**：ClusterSecretStore 中的 `serviceAccountRef` 只写了 `name` 但没写 `namespace`。ClusterSecretStore 是集群范围资源，不指定 namespace 的话 ESO 不知道去哪个命名空间找 SA。

**解决**：在 `cluster-secret-store.yaml` 的 `serviceAccountRef` 中加上 `namespace: external-secrets`。

```yaml
serviceAccountRef:
  name: "external-secrets"
  namespace: "external-secrets"    # 必须
```

---

### 问题 4：ExternalSecret 报 "Secret does not exist"

**现象**：
```
error processing spec.data[0] (key: secret/data/test), err: Secret does not exist
```

**原因**：Vault KV v2 路径写错。通常是因为用 `vault kv put secret/data/test` 写入，命令自动加了 `data/`，导致实际路径变成了 `secret/data/data/test`。

**解决**：见下方 [KV v2 路径规则](#七kv-v2-路径规则重要)。

---

### 问题 5：Helm 安装 ESO 超时/网络错误

**现象**：
```
Error: Get "https://github.com/...": read tcp ...: connection reset by peer
```

**原因**：国内网络无法稳定访问 GitHub。

**解决**：
1. 用 `kubectl apply -f` 代替 Helm
2. 或在本地 Windows 下载 chart 后传到集群
3. 或配置代理

---

### 问题 6：ExternalSecret 报 "cannot find secret data for key"

**现象**：
```
error processing spec.data[1] (key: secret/data/research-agent/api), err: cannot find secret data for key: "CUSTOM_API_KEY"
```

**原因**：Vault 中存在该路径，但缺少某个 key。ExternalSecret 中声明的 `remoteRef.property` 在 Vault 的对应路径下找不到。

**解决**：`vault kv put` 写入时**必须补全所有在 ExternalSecret 中声明了的 key**，不能只写部分。

```bash
# ❌ 只写了部分 key，ESO 找不齐会报错
kubectl exec -n vault vault-0 -- vault kv put secret/research-agent/api \
  OPENAI_API_KEY="sk-xxx"

# ✅ 必须写全所有 ExternalSecret 中声明的 key
kubectl exec -n vault vault-0 -- vault kv put secret/research-agent/api \
  OPENAI_API_KEY="sk-xxx" \
  CUSTOM_API_KEY="sk-xxx"
```

**原理**：ESO 的 data 列表中的每一项 `remoteRef` 都会从 Vault 读取对应的 property。如果某个 property 在 Vault 路径中不存在（哪怕路径本身存在），ESO 会报错整个 ExternalSecret 都不同步。

**如何避免**：在编辑 ExternalSecret 时，`data` 列表里的每个 `property` 都要确保 Vault 里有对应值。用不到的值可以**在声明时就排除掉**，而不是在 Vault 里给个空值。

---

### 问题 7：Web UI 暴露后访问不了

**现象**：浏览器访问 `http://192.168.137.101:31200` 连接超时。

**排查步骤**：
```bash
# 1. 确认 Service 类型是 NodePort
kubectl get svc vault -n vault

# 2. 确认 NodePort 端口
kubectl get svc vault -n vault -o jsonpath='{.spec.ports[0].nodePort}'

# 3. 在 master 节点本地测试
curl -s http://127.0.0.1:<NodePort> | head

# 4. 检查防火墙
iptables -L -n | grep <NodePort>
```

---

## 七、KV v2 路径规则（重要）

这是最容易出错的地方。KV v2 引擎的路径有一个**自动加 `data/`** 的行为：

| 操作 | 命令写法 | 实际路径 |
|------|---------|---------|
| **写入** `vault kv put` | `vault kv put secret/test k=v` | `secret/data/test` |
| **读取** `vault kv get` | `vault kv get secret/data/test` | `secret/data/test` |
| **ExternalSecret** `remoteRef.key` | `secret/data/test` | `secret/data/test` |

### 错误示例

```bash
# ❌ 错误：命令自动加 data/，实际变成 secret/data/data/test
kubectl exec -n vault vault-0 -- vault kv put secret/data/test hello=world

# ❌ 错误：ExternalSecret 中少写了 data/
remoteRef:
  key: secret/test    # 应该是 secret/data/test
```

### 正确用法

```bash
# ✅ 写入（不加 data/）
kubectl exec -n vault vault-0 -- vault kv put secret/test hello=world

# ✅ 读取（加 data/）
kubectl exec -n vault vault-0 -- vault kv get secret/data/test

# ✅ ExternalSecret（加 data/）
remoteRef:
  key: secret/data/test
  property: hello
```

---

### 问题 8：ExternalSecret 报 "unknown field spec.target.template.kind"

**现象**：在 ExternalSecret 中使用 `template.kind: ConfigMap` 时，apply 报错：
```
strict decoding error: unknown field "spec.target.template.kind"
```

**原因**：当前集群安装的 ESO 版本不支持 `template.kind: ConfigMap` 功能，`kind` 字段未在 CRD schema 中定义。即使通过 `--validate=false` 放行后，因 CRD 底层不存在该字段定义，实际 behavior 是将 `kind: ConfigMap` 忽略并按默认行为生成 Secret。

**结论**：**此版本的 ESO 不支持 template 生成 ConfigMap**。ConfigMap 请手动维护：

```bash
kubectl create configmap agent-config -n research-agent \
  --from-literal=PROVIDER=deepseek \
  --from-literal=CUSTOM_API_BASE=http://... \
  --from-literal=CUSTOM_MODEL=deepseek-v4-pro \
  --dry-run=client -o yaml | kubectl apply -f -
```

**Secret 部分正常工作**，无需特殊处理（直接 `kubectl apply -f` 即可）：

```bash
kubectl apply -f inventory/research-agent-externalsecret.yaml
```

**安装 CRD（bundle.yaml）时的注意事项**：
```bash
# bundle.yaml 文件过大，用 --server-side 避免 annotation 超限
kubectl apply --server-side -f \
  https://raw.githubusercontent.com/external-secrets/external-secrets/v2.7.0/deploy/crds/bundle.yaml
```

---

### 问题 9：Secret 更新了但 Pod 还读旧值

**现象**：在 Vault 中修改了 Secret 值，ESO 也成功同步到 K8s Secret，但 Pod 中的环境变量还是旧的。

**原因**：Kubernetes 的环境变量（`env`/`envFrom`）只在 Pod **启动时**注入一次，运行时不会自动刷新。

**解决**：修改 Secret 后需要**重启**引用了该 Secret 的 Pod。

```bash
# 重启 deployment
```
