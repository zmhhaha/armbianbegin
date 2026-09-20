# 网络策略引擎选型与启用清单

**结论：集群当前没有任何 NetworkPolicy 生效。** 修复路径是 **kube-router 的 `--run-firewall` 策略-only 模式**，生效范围**只框在 `dsh` / `dsh-runners` / `hermes` 三个命名空间**。

- 调查日期：2026-09-20
- 调查方式：SSH 到 `arm-cluster-master` 只读查询 + 从 `dsh-runner` 容器内 TCP 探测
- 起因：复核 [infrastructure-assessment.md](../panghu_chat/docs/infrastructure-assessment.md) 时发现 DSH 的网络边界不成立

## 一、问题

集群 CNI 是 **`kube-flannel`**（5 节点各一个 DaemonSet）。`kube-system` 里除 `kube-proxy` 外没有其他 DaemonSet，**无 Calico / Cilium / kube-router / antrea，也无任何策略相关 CRD**。

**flannel 不实现 NetworkPolicy**。因此集群中现存的 **13 个 NetworkPolicy 对象全部空转**。

实测证据——从 `dsh-runner-armbianbegin` 容器内 TCP 探测（该容器的策略明确声称拒绝内网）：

| 目标 | 策略声称 | 实测 |
|---|---|---|
| `llm-service.llm.svc:80` | 拒绝 | **CONNECTED** |
| `rag-service.data.svc:8080` | 拒绝 | **CONNECTED** |
| `embedding-service.data.svc:8080` | 拒绝 | **CONNECTED** |
| `postgres.data.svc:5432` | 拒绝 | **CONNECTED** |
| `redis.data.svc:6379` | 拒绝 | **CONNECTED** |
| `kubernetes.default.svc:443` | 拒绝 | **CONNECTED** |
| `vault.vault.svc:8200` | 拒绝 | **CONNECTED** |
| `registry.npmmirror.com:443`（对照） | 放行 | CONNECTED |

**受影响范围**（13 个策略分布）：

| 命名空间 | 策略 |
|---|---|
| `dsh` | `default-deny`、`tunnel-ingress`、`web-egress` |
| `dsh-runners` | `default-deny`、`runner-ingress`、`runner-egress` |
| `hermes` | `default-deny`、`tunnel-ingress`、`research-egress`、`hublog-publisher` |
| `data` | `embedding-service`、`rag-service` |
| `llm` | `llm-service` |

## 二、选型

### ❌ Calico 策略-only —— 官方不支持

最初的首选，查证后**排除**。[projectcalico/calico#8866](https://github.com/projectcalico/calico/issues/8866) 中维护者的明确答复：

> "For using calico policy only mode with flannel, **it is not possible to install calico on a cluster that already has flannel installed.**"

> "we do not have any official method for installing policy-only Calico on a cluster with a pre-existing Flannel overlay... **some configurations of Flannel are completely incompatible with how Calico enforces policy, e.g, Flannel bridges break Calico policy between pods on the same node.**"

提问者自行 patch ClusterRole 让 `calico-policy-only.yaml` 跑起来了，官方回复仍是不支持、不推荐。**不要从这里试起。**

### ⚠️ Canal（`canal.yaml`）—— 可行，但等于换 CNI

Calico 官方唯一的 flannel 组合，是一次性安装 flannel + Calico。**这意味着替换现有 flannel**：

- 需改每节点 kubelet 的 CNI 配置
- kube-router 的文档把代价写得很直白：**"Switching CNI providers on a running cluster requires re-creating all pods to pick up new pod IPs."**
- 本集群 **164 个 Pod** 需要重建

对本需求（只为挡住 DSH runner）代价过高。保留为 kube-router 验证失败时的退路。

### ✅ kube-router `--run-firewall` 策略-only —— 采用

```sh
kube-router --run-firewall=true --run-router=false --run-service-proxy=false
```

只做网络策略；Pod 网络留给 flannel，Service 留给 kube-proxy。**不装 CNI 插件、不改 kubelet 的 CNI 配置**——这是它与 Canal/Calico 的关键差别，也是**不需要重建 Pod** 的原因。

| 前提 | 状态 |
|---|---|
| 官方文档支持"只跑策略" | ✅ 四个开关 `--run-firewall` / `--run-router` / `--run-service-proxy` / `--run-loadbalancer` 可独立启用 |
| 宿主机 iptables 能看到网桥上的 Pod 流量 | ✅ `br_netfilter` 已加载、`bridge-nf-call-iptables=1`（master / nanopct4-server1 / orangepi5 三台实查） |
| 有 arm64 镜像 | ✅ release 含 `kube-router_2.11.1_linux_arm64.tar.gz`；Makefile 构建 `linux/amd64,linux/arm64,linux/arm,...` |
| 项目活跃 | ✅ v2.11.1（2026-08-17），最近提交 2026-09-13，未归档 |

**风险**：kube-router 是 cloudnativelabs 的第三方项目（约 2.5k stars、19 个 open issue），不是 CNI 厂商主线。

> ⚠️ **本方案有一环未验证**：`br_netfilter=1` 是**必要条件，不是充分条件**。kube-router 直接写宿主机 iptables 的 `KUBE-POD-FW-*` 链，模型与 Calico 不同，因此 Calico 那句"网桥会破坏同节点策略"**不能直接套用**，但也不能反过来假定它一定生效。**必须先做第五节的最小验证。**

## 三、生效范围：只框 dsh + hermes

NetworkPolicy 只影响被其 `podSelector` 选中的 Pod。**其余约 40 个命名空间没有任何策略选中它们 → 默认放行，行为完全不变。**

⚠️ **但生效范围不由"装在哪"决定，而由"谁被选中"决定。** `data/` 和 `llm/` 的 3 个策略已经存在，引擎一开就会一起变成真的。要只框 dsh + hermes，**必须把它们删掉**：

```sh
kubectl -n data delete networkpolicy embedding-service rag-service
kubectl -n llm  delete networkpolicy llm-service
```

保留它们的代价（若日后想全集群收口，这些是要补的）：

| 策略 | 保留后必须补的 |
|---|---|
| `data/embedding-service` | 给 `rag-service` Pod 补 `embedding-client: "true"` 标签——**实测全集群带该标签的 Pod 数量为 0**，而 rag-service 是 embedding-service 唯一的调用方；另需处理其 `egress: []`（连 DNS 都禁） |
| `data/rag-service` | 10 个调用方**均已带** `rag-client: "true"` ✅，无需改动 |
| `llm/llm-service` | 实测 12 个调用方**均已带** `llm-client: "true"` ✅，无需改动 |

**建议：先删，把引擎生效范围严格框在 dsh + hermes。** 全集群收口是一件独立的、可以慢慢做的事。

## 四、启用前必须完成的三件事

以下三处**当前都是坏的**，引擎一开就会立刻暴露：

### 1. cloudflared 的入口标签

`dsh/tunnel-ingress` 与 `hermes/tunnel-ingress` 原本要求来源 Pod 带 `dsh-ingress: "true"` / `hermes-ingress: "true"`。**实测 cloudflared 的标签只有 `{app: cloudflared, tunnel: main, pod-template-hash}`——这两个标签从来不存在。** 直接用现有策略启用引擎，**DSH 和 Hermes 会双双失联**。

**✅ 已在仓库修好**：两个策略改为选择 cloudflared 已有的稳定标签，零改 operator：

```yaml
from:
- namespaceSelector: {matchLabels: {kubernetes.io/metadata.name: default}}
  podSelector: {matchLabels: {app: cloudflared, tunnel: main}}
ports: [{protocol: TCP, port: 4180}]
```

### 2. Hermes → Hublog 的出站端口

`hublog-publisher` 原只放行 **8080**，而 `HUBLOG_URL` 无端口即 **80**（[hermes-code-review.md](hermes-code-review.md) 的 H1）。

**✅ 已在仓库修好**：同时放行 80 与 8080——具体哪个对取决于 CNI 在 DNAT 前还是后匹配端口，不赌。

### 3. 确认依赖的标签都在

| 依赖 | 状态 |
|---|---|
| cloudflared ← 两个 ingress 策略 | ✅ 改为选现有标签 |
| `hermes-web` Pod `role: web` | ✅ 实测存在 |
| `hermes-collect/report/publish` Pod 的 `role` | ✅ 实测分别为 `collect` / `report` / `publish`，与策略选择器一致 |
| `dsh-web` `role: web`、runner `role: runner` | ✅ 实测存在 |
| runner ↔ web 的 2222 互连 | ✅ 策略两侧一致 |

## 五、最小验证（不要直接上全集群）

```sh
# 1) 只调度到一台节点，且只跑策略
#    DaemonSet 加 nodeSelector: kubernetes.io/hostname: orangepi5-max-server1
#    args: --run-firewall=true --run-router=false --run-service-proxy=false

# 2) 只保留最值钱的那一条策略：runner-egress
kubectl -n dsh-runners delete networkpolicy default-deny runner-ingress
#    runner-egress 保持

# 3) 从 DSH runner 内重跑探测——应当与此前完全相反
#    内网 7 个目标 → TIMEOUT；公网 443 → CONNECTED
```

**同节点与跨节点都要测**（网桥问题只在同节点出现）。runner 在 `orangepi5-max-server1` 上，需同时试一个同节点目标（如 `redis.data.svc:6379`）和一个别的节点上的目标。

判定：

| 结果 | 动作 |
|---|---|
| 内网 TIMEOUT、公网 CONNECTED | ✅ 铺全集群，恢复被删的两条策略 |
| 内网仍 CONNECTED | ❌ kube-router 在此网络下不可用，转 Canal 路线（接受全量重建 Pod） |

## 六、启用后仍需注意

- **存量 Pod 是否被 kube-router 纳管**：策略-only 模式不装 CNI 插件，理论上能接管已存在的 Pod，但**未验证**。最小验证里若内网仍连通，先排查这一条再否定整个方案。
- **IPv6 未覆盖**：`ipBlock` 只有 IPv4，全仓无 IPv6 处理。需确认节点无 IPv6 出口（见 [../panghu_chat/dsh/docs/boundaries.md](../panghu_chat/dsh/docs/boundaries.md)）。
- **`calico-node` 不适用**：若最终转 Canal，注意其 `calico-node` 需要 privileged，可参考本仓库 `kube-flannel` 命名空间已有的 `pod-security=privileged` 做法。
- **不要把网络隔离计入任何已完成的验收**：在最小验证通过之前，[infrastructure-assessment.md](../panghu_chat/docs/infrastructure-assessment.md) 第 11 节那条"集群网络隔离实际生效"保持不通过。
