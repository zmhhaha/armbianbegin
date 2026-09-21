# Calico 迁移实录（2026-09-21）

> ## 🔴 本文档的"根本原因"一节是错的，先看这里
>
> 迁移完成后集群网络仍不通，本文档原先把原因归结为 Calico 的 NAT 层未定位。**实际原因在 2026-09-21 当天查明：**
>
> **DSH 的 `runner-egress` 策略在 except 列表里写了 `198.18.0.0/15`，而本网络的 OpenClash fake-ip DNS 把所有外部域名都解析到 `198.18.x.x`。这一条等于把整个公网排除掉。**
>
> 实测（同一 Pod、同一策略形状，只改这一条 CIDR）：
>
> | except 列表 | 内网 | 公网 |
> |---|---|---|
> | 13 条（含 `198.18.0.0/15`） | 断 | **断** |
> | 12 条（去掉） | 断 | **通** |
>
> **⇒ kube-router 和 Calico 的 `except` 实现都是正确的。** "kube-router 不支持 except"是**误判**——`probe-matrix.sh` 的场景复刻了同一条错误的 except 列表，于是"验证"出一个不存在的引擎缺陷，并据此做了这次本来不必要的换 CNI 手术。
>
> **ClusterIP 那一节同样是假象**：它测的是"公网域名解析失败"，不是 Service 路由故障。用户随后修正 Calico 的 `IP_AUTODETECTION_METHOD`（改为 `kubernetes-internal-ip`，避免 autodetect 选错网卡）后，公网、跨节点 Pod、ClusterIP 全部恢复。
>
> **本文档保留完整过程**，因为那些操作性问题（cordon 未解除、remove-flannel 未执行、kube-router 残留、磁盘压力）都是真的，也都值得记。**但"根因"要按上面这条读。**
>
> 最终处置：集群留在 Calico（它能兑现 NetworkPolicy，flannel 不能），DSH 策略删掉那条 CIDR 并加注防复发。

**结果：过程曲折，最终集群在 Calico 上正常工作。** 最初记录的"未成功"状态是误判——真正卡住的是策略里的一条 CIDR，不是 CNI。

- 执行日期：2026-09-21
- 目标：用 flannel → Calico 的官方实时迁移让 NetworkPolicy 真正生效
- 执行材料：[../network-policy/calico/](../network-policy/calico/README.md)
- 决策背景：[network-policy-engine.md](network-policy-engine.md)

## 结论摘要

| 项 | 状态 |
|---|---|
| CNI 切换 | ✅ 5 台全 Calico，flannel 数据面与 DaemonSet 已移除 |
| 残余引擎 | ✅ kube-router 已彻底清除（它曾与 Calico 并行写 iptables） |
| 节点 | ✅ 全部 Ready，无污点 |
| calico-node | ✅ 5/5 Ready |
| **Pod 公网出网** | ✅ 通 |
| **跨节点 Pod ↔ Pod** | ✅ 路径通（`ECONNREFUSED` = 到达对端但端口无服务） |
| **ClusterIP（Service）** | ❌ **TIMEOUT，未解决** |

**关键判据**：overlay 是好的；坏掉的只有 Service 的 DNAT 这一层。重启 kube-proxy（5 台）**无效**。

## 最重要的发现：本集群的结构不适合官方实时迁移

官方迁移的设计前提是：**被 drain 的节点上的 Pod 能在别的节点上重新调度**。

本集群不满足这个前提：

| 节点 | 迁移前的 Pod 数 | 特点 |
|---|---:|---|
| `orangepi5-max-server1` | **94（57%）** | 唯一的大节点 |
| `nanopct4-server3` | 32 | 4 GiB，迁移期间触发 DiskPressure |
| `nanopct4-server2` | 19 | 4 GiB |
| `arm-cluster-master` | 12 | control-plane 污点，不接受业务 Pod |
| `nanopct4-server1` | 4 | 4 GiB |

**⇒ 当 `orangepi5` 被 drain 时，94 个 Pod 无处可去。** 小节点被塞满、触发 DiskPressure 驱逐，迁移控制器自己也被赶走，形成循环。

这是结构性问题，不是配置问题。**再跑一次还会遇到同样的事。**

## 问题与处置

| # | 问题 | 根因 | 处置 | 结果 |
|---|---|---|---|---|
| 1 | `orangepi5` 被 cordon，**0/5 节点可调度**、114 Pod Pending | 迁移控制器 drain 完该节点后**未 uncordon** | `kubectl uncordon orangepi5-max-server1` | ✅ 解决 |
| 2 | 迁移控制器反复重启（`86kwn`→`tz8zb`→`9dvzc`） | T4 节点 DiskPressure 驱逐它的 Pod | prune 镜像；kubelet GC 自行释放 | ✅ 缓解 |
| 3 | 磁盘写满（server3 仅剩 97 MB） | 镜像堆积 + 驱逐 churn 反复重拉镜像 | `docker image prune -a`；后续自行 GC 到 6.8 G 可用 | ✅ 解决 |
| 4 | orangepi5「半迁移」：CNI 配置是 Calico，数据面还是 flannel（`flannel.1`/`cni0`/路由仍在，`vxlan.calico` 未建） | 负责清理的 `remove-flannel` 助手 Pod 被 Evicted，**这步从未执行** | 手工删接口 + 重启 calico-node | ✅ 解决 |
| 5 | 4 台节点残留 flannel iptables 链（`FLANNEL-POSTRTG`/`FLANNEL-FWD`） | 同 #4 | 全 5 台清除 | ✅ 解决 |
| 6 | **kube-router 仍在运行**，与 Calico 并行写 iptables | 早先回滚只删了 DaemonSet；后来 `deploy.sh` 被重跑又装回 server1 | 删 DS + `--cleanup-config` + 删 ns/RBAC/CRB | ✅ 解决 |
| 7 | **ClusterIP 全部 TIMEOUT** | **未定位**。kube-proxy 重启无效 | — | ❌ **未解决** |

## 执行过程中我犯的三个错误

按时间顺序，都值得记下来：

1. **过早删除了迁移 Job。** 我看到它 23 分钟停在 1/5 就判定"卡住"，实际它仍在推进（后来到了 4/5）。删 Job 中断了控制器，把集群停在了最坏的中间点。**教训：控制器的进度不由"节点标签数"单独反映，drain 一个节点要等它的 Pod 全部重新就绪，在小集群上很慢。**
2. **误判了第一现场。** 主要问题是 `orangepi5` 被 cordon 导致 0/5 可调度，我却先去查了磁盘（磁盘问题真实存在，但不是当时的主因）。
3. **以为"迁移完成"就结束了。** 实际上迁移的收尾步骤（`remove-flannel`）因为 Pod 被驱逐而从未执行，导致数据面半迁移。**「控制器跑过」不等于「它每一步都成功了」。**

## 当前未解决项：ClusterIP

**症状**：命名空间内全新 Pod（无任何策略施加）访问 `kubernetes.default.svc:443` 或 `postgres.data.svc:5432` 全部 TIMEOUT，但公网和跨节点 Pod IP 都正常。

**已排除**：
- overlay 不通 —— 不是，跨节点 Pod IP 可达
- 策略拦截 —— 无策略的 Pod 也一样
- kube-proxy 规则陈旧 —— 5 台重启后无变化

**未排查**：Calico 的 `cali-nat-outgoing` 链内容、`FelixConfiguration` 的 service CIDR 相关设置、conntrack 残留。

## 安全网

- **etcd 快照**：`/root/etcd-snapshots/etcd-20260921T041451Z.db`（29 MB，revision 26125031），另有一份在集群外
- **迁移前 CNI 配置**：`/root/cni-before/<node>.txt`（5 台）
- flannel DaemonSet 的清单仍在仓库（`kube-flannel.yml`），回退可用

## 下一步的两个选项

**A. 继续排查 ClusterIP。** 已缩小到 NAT 层，但仍有未解层。

**B. 回滚到 flannel。** 官方文档化路径，逐节点：drain → 删 `/etc/cni/net.d/10-calico.conflist` → 重启 → 标签改回 flannel → uncordon；最后去掉 flannel DaemonSet 的 nodeSelector。代价是 5 台各一次 drain + 重启。

**若再尝试迁移，先解决前提**：给集群腾出足以容纳 `orangepi5` 那 94 个 Pod 的容量，或改用逐节点手工迁移（不用控制器的整体 drain）。**本集群当前的容量分布不适合官方的实时迁移。**
