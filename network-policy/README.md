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

## 三步铺开

```sh
# 0) 把镜像同步进私有 registry（固定 digest）
bash build.sh

# 1) 只上 nanopct4-server1，然后自证
bash deploy.sh --dry-run        # 先看渲染结果
bash deploy.sh                  # 默认就钉在这一台
bash verify.sh                  # 三阶段验证，见下

# 2) 上真正要紧的那台（先读下面"验证通过之后"）
bash deploy.sh --node orangepi5-max-server1
bash verify.sh --node orangepi5-max-server1

# 3) 全量
bash deploy.sh --all-nodes
```

## `verify.sh` 为什么是三个阶段

"流量断了"本身什么都证明不了——可能只是数据面坏了。只有**能装上、也能干净卸掉、卸掉后连通性恢复**，才说明这是策略而不是破坏。

| 阶段 | 动作 | 期望 |
|---|---|---|
| A | 无策略时探测 | 全部 `CONNECTED`（基线） |
| B | 给探针 Pod 套一条 deny-all egress | 全部 `BLOCKED` / `TIMEOUT`（策略生效） |
| C | 删掉那条策略再探测 | 全部 `CONNECTED`（可逆） |

探针是一个**用完即删**的 Pod（`netpol-probe` 命名空间），镜像复用 registry 里已有的 `dsh-runner:latest`（自带 Node），不新建镜像、不碰任何真实负载。

**A 失败**说明数据面本来就坏了，与策略无关；**C 失败**是最危险的信号——策略可装不可卸，必须停下。

## 验证通过之后：先决定哪些策略该生效

这是最容易踩的一步。**引擎一开，集群里现存的 13 个策略会一起变成真的**，其中 3 个不在 dsh/hermes 范围内：

```sh
kubectl -n data delete networkpolicy embedding-service rag-service
kubectl -n llm  delete networkpolicy llm-service
```

不删的后果是具体的：`embedding-service` 只放行带 `embedding-client: "true"` 的 Pod，而**实测全集群带这个标签的 Pod 数量为 0**，`rag-service` 是它唯一的调用方——RAG 会立刻断。详见 [../docs/network-policy-engine.md](../docs/network-policy-engine.md) 第三节。

**建议先删，把生效范围严格框在 `dsh` / `dsh-runners` / `hermes`。** 全集群收口是一件独立的、可以慢慢做的事。

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
