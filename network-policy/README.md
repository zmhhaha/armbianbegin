# 网络策略引擎（kube-router，仅防火墙模式）

**这个组件现在它唯一要做的事**：让集群里那 13 个 NetworkPolicy 对象**真的生效**。今天的 CNI 是 `kube-flannel`，不实现 NetworkPolicy，所以它们全部空转——完整证据见 [../docs/network-policy-engine.md](../docs/network-policy-engine.md) 与 [../panghu_chat/docs/infrastructure-assessment.md](../panghu_chat/docs/infrastructure-assessment.md) 第 8.0 节。

## 为什么不选 Calico

Calico 的策略-only 模式**不支持装在已有 flannel 的集群上**（[projectcalico/calico#8866](https://github.com/projectcalico/calico/issues/8866)，维护者明确回复；原因之一是 flannel 网桥会破坏 Calico 的同节点策略）。Calico 官方唯一的 flannel 组合是 `canal.yaml`，那等于**替换掉现有 flannel**，需要重建全部 164 个 Pod。

kube-router 有专门的 `--run-firewall` 模式：只写策略，Pod 网络留给 flannel，Service 留给 kube-proxy，**不装 CNI 插件、不改 kubelet 配置**。这是本仓库选它的唯一理由。

## ⚠️ 失败模式不是"策略没生效"

这是本文档最需要读进去的一段。

- **策略没生效** = fail-open = 和今天一样，不算事故。
- **真正的事故是**：kube-router 直接改宿主机 iptables 的 FORWARD 区，改动出错会让**那台节点上的 Pod 掉网**。

所以**一次只铺一台，而且第一台必须挑最空的**。当前各节点 Pod 数：

| 节点 | Pod 数 | 备注 |
|---|---:|---|
| `orangepi5-max-server1` | **94** | 全集群 164 个的 57%。**绝对不要从这里开始** |
| `nanopct4-server3` | 32 | |
| `nanopct4-server2` | 19 | |
| `arm-cluster-master` | 12 | |
| `nanopct4-server1` | **4** | 默认起点。4 个全是 hostNetwork 的基础设施（flannel / kube-proxy / CSI），没有应用负载 |

## 铺开步骤

```sh
# 0) 把镜像同步进私有 registry（固定 digest）
bash build.sh

# 1) 只上 nanopct4-server1，然后自证
bash deploy.sh --dry-run        # 先看渲染结果
bash deploy.sh                  # 默认就钉在这一台
bash verify.sh                  # 三阶段验证，见下

# ⚠️ 2 之前必须先做完下面「动 orangepi5 之前」的两件事

# 2) 上真正要紧的那台
bash deploy.sh --node orangepi5-max-server1
bash verify.sh --node orangepi5-max-server1

# 3) 全量
bash deploy.sh --all-nodes
```

> ### ⚠️ `verify.sh` 证明的是**引擎能工作**，不是**你的策略是对的**
>
> 探针 Pod 只受它自己那条临时策略影响。它 PASS 完全不能说明真实策略挂在 94 个真实 Pod 上会怎样。
> **真实策略的对错要单独审**——就是下面这两件事。

## 动 orangepi5 之前必须做的两件事

kube-router 只对它**所在节点上的 Pod** 生效。`orangepi5-max-server1` 上跑着 94 个 Pod，包括 `dsh-web`、`dsh-runner`、`hermes-web`、`embedding-service`、`llm-service`、postgres、redis。**引擎一装上去，选中这些 Pod 的策略会同时变成真的。**

### ① 把已修好的策略 apply 到集群

仓库里的修复**只提交了、不代表集群上是新的**。部署前先核对，否则会当场失联：

```sh
kubectl -n dsh    get networkpolicy tunnel-ingress -o jsonpath='{.spec.ingress[0].from[0].podSelector}'
kubectl -n hermes get networkpolicy tunnel-ingress -o jsonpath='{.spec.ingress[0].from[0].podSelector}'
# 期望：{"matchLabels":{"app":"cloudflared","tunnel":"main"}}
# 若仍是 {"matchLabels":{"dsh-ingress":"true"}} —— 那是旧版，cloudflared 没有这个标签，
# 装引擎 = DSH/Hermes 从公网失联。

kubectl -n hermes get networkpolicy hublog-publisher -o jsonpath='{.spec.egress[1].ports}'
# 期望同时含 80 与 8080；只有 8080 会让发布断掉。
```

不匹配就 apply（**当前引擎还没生效，apply 是零风险的**）：

```sh
kubectl apply -f ../panghu_chat/dsh/k8s/networkpolicies.yaml
kubectl apply -f ../panghu_chat/hermes/k8s/core.yaml
```

> `core.yaml` 是整个 Hermes 清单（15 个文档），apply 会一并同步 Deployment / PVC / CronJob——这正是 `hermes/deploy.sh` 本身的做法，幂等，且不会重启未变更的工作负载。**只想动策略的话**，把文件里那两个 `kind: NetworkPolicy` 抽出来单独 apply 即可。

### ② 删掉范围外的三条策略

`embedding-service` 与 `llm-service` 就在 orangepi5 上，它们的入站策略会被立刻执行：

```sh
kubectl -n data delete networkpolicy embedding-service rag-service
kubectl -n llm  delete networkpolicy llm-service
```

**不删的具体后果**：`embedding-service` 只放行带 `embedding-client: "true"` 的 Pod，而**实测全集群带该标签的 Pod 数量为 0**，`rag-service`（在 `nanopct4-server2`）是它唯一的调用方——**RAG 立刻断**。

（`data/rag-service` 那条反而暂时不会生效，因为 rag-service 不在 orangepi5 上；等哪天铺到 server2 再说。）

> 另一种选择是**修好它们而不是删掉**：`rag-service` 和 `llm-service` 的调用方标签实测都齐（10 / 12 个全带），只有 `embedding-service` 需要给 `rag-service` 补一个 `embedding-client: "true"` 标签。如果你想顺便把这三条也收口，这是最小改动——但会扩大第一次上 orangepi5 的爆炸半径。**默认建议还是先删。**

## `verify.sh` 为什么是三个阶段

"流量断了"本身什么都证明不了——可能只是数据面坏了。只有**能装上、也能干净卸掉、卸掉后连通性恢复**，才说明这是策略而不是破坏。

| 阶段 | 动作 | 期望 |
|---|---|---|
| A | 无策略时探测 | 全部 `CONNECTED`（基线） |
| B | 给探针 Pod 套一条 deny-all egress | 全部 `BLOCKED` / `TIMEOUT`（策略生效） |
| C | 删掉那条策略再探测 | 全部 `CONNECTED`（可逆） |

探针是一个**用完即删**的 Pod（`netpol-probe` 命名空间），镜像复用 registry 里已有的 `dsh-runner:latest`（自带 Node），不新建镜像、不碰任何真实负载。

**A 失败**说明数据面本来就坏了，与策略无关；**C 失败**是最危险的信号——策略可装不可卸，必须停下。

## 全量之前还要想的一件事

上面「动 orangepi5 之前」处理的是**当下会不会炸**。全量之后还有一层：届时集群里**每条**策略都在生效，包括那些今天看起来"人畜无害"的。选型与范围决策见 [../docs/network-policy-engine.md](../docs/network-policy-engine.md) 第三节。

## 文件

| 文件 | 作用 |
|---|---|
| `build.sh` | 拉 ARM64 上游 → 断言架构 → 解析 digest → 推私有 registry，摘要写进 `rendered/` |
| `deploy.sh` | 渲染模板、**拒绝未替换的占位符**、apply、等 rollout；`--remove` 回滚 |
| `verify.sh` | 三阶段自证；探针 Pod 用完即删 |
| `k8s/00-namespace.yaml` | `kube-router` 命名空间，PSA `privileged`（参照仓库已有的 `kube-flannel` 做法） |
| `k8s/10-rbac.yaml` | SA + ClusterRole + ClusterRoleBinding，改编自上游 |
| `k8s/20-kube-router.yaml` | **模板**，含 `__IMAGE__` / `__TEST_NODE__` 占位符，不能直接 apply |

`20-kube-router.yaml` 里 `--enable-cni=false` 是关键：kube-router **绝不能**往 `/etc/cni/net.d` 写配置，那是 flannel 的地盘。

## 回滚

```sh
bash deploy.sh --remove
```

它删 DaemonSet，并打印两件必须手工做的事：① 每个节点上清理 kube-router 写的 iptables 规则；② 删除 cluster 级 RBAC（脚本不自动删，是刻意的）。

## 本方案未覆盖

- **IPv6**：`ipBlock` 只有 IPv4，全仓无 IPv6 处理。需确认节点无 IPv6 出口。
- **同节点 vs 跨节点**：两者走不同的 iptables 路径。`verify.sh` 选的目标里既有同节点的也有跨节点的，但若只关心某一类，应自己补齐目标列表。
- **`br_netfilter` 依赖**：kube-router 依赖 `bridge-nf-call-iptables=1` 才能看到网桥上的 Pod 流量。三台抽查节点均为 `1`，但**未全量核对**。
- **策略本身的对错**：本目录只负责"让策略生效"，不负责策略写得对不对。启用前请按上一节自查。
