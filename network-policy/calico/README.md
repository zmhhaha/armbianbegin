# flannel → Calico 迁移

**用官方支持的实时迁移，不需要重建 164 个 Pod 手工重来**——迁移控制器逐节点切换，自动 evict 该节点上的 Pod 让它们在新 CNI 上重建。有文档化的回退路径。

- 上游文档：<https://docs.tigera.io/calico/latest/getting-started/kubernetes/flannel/migration-from-flannel>
- 锁定版本：**Calico v3.32.2**
- 决策背景见 [../README.md](../README.md) 与 [../../docs/network-policy-engine.md](../../docs/network-policy-engine.md)

---

## ⚠️ 先读这一条：没有备份

**这是本仓库至今风险最高的一次操作，而集群没有 etcd 备份。**

需要重建 Pod，需要在每台节点上改 CNI 配置，需要删 iptables 链。出错时官方回退路径存在，但它假设集群状态是可用的。

> **建议**：先做一次 etcd 快照并放到集群外。这不在本目录的脚本里，但做之前值得花那 20 分钟。
> ```sh
> # 在 master 上（etcd 是静态 Pod）
> ETCDCTL_API=3 etcdctl \
>   --endpoints=https://127.0.0.1:2379 \
>   --cacert=/etc/kubernetes/pki/etcd/ca.crt \
>   --cert=/etc/kubernetes/pki/etcd/server.crt \
>   --key=/etc/kubernetes/pki/etcd/server.key \
>   snapshot save /root/etcd-$(date +%F-%H%M).db
> ```
> 另需离线保存 `/etc/kubernetes/` 与 `/etc/cni/net.d/`（迁移前后各一份）。

## 已核实的前提（2026-09-21）

| 前提 | 实测值 | 结论 |
|---|---|---|
| flannel 后端 | **VXLAN** | ✅ Calico 也用 VXLAN，这是实时迁移成立的前提 |
| flannel MTU | **1450** | ✅ 必须与 Calico 对齐，否则出现"大包丢、小包通"的诡异故障 |
| flannel 网络 | `10.244.0.0/16` | ✅ |
| `--allocate-node-cidrs` | **true** | ✅ Calico 硬依赖 |
| `--cluster-cidr` | `10.244.0.0/16` | ✅ |
| `--service-cluster-ip-range` | `10.96.0.0/12` | ✅ |
| `/run/flannel/subnet.env` | 存在 | ✅ 迁移控制器读它 |
| 现有 Calico 残留 | 0 个 CRD、0 个 DaemonSet | ✅ 干净 |
| 现有 CNI 配置 | `10-flannel.conflist` | Calico 写 `10-calico.conflist`，**字母序在前**，天然接管 |
| quay.io 可达 | 是 | 但仍按仓库惯例镜像进私有 registry |
| 镜像 | `quay.io/calico/{cni,node,kube-controllers,flannel-migration-controller}:v3.32.2` | |

## 分步方案

每一步都有**通过条件**，不满足就停下，不要往下走。

### 阶段 0：准备（不碰集群）

```sh
bash mirror.sh        # quay.io → arm-cluster-master:5000，产出 rendered/
```

产出：4 个镜像进私有 registry；`rendered/calico.yaml` 与 `rendered/migration-job.yaml`（镜像地址已改指向私有 registry）。

**通过条件**：`rendered/` 里两个清单存在，且用 `grep quay.io rendered/*.yaml` 查不到任何残留。

### 阶段 1：快照与记录（强烈建议）

上面那条 etcd 快照 + 保存 `/etc/cni/net.d/` 的当前内容：

```sh
for n in arm-cluster-master nanopct4-server1 nanopct4-server2 nanopct4-server3 orangepi5-max-server1; do
  ssh $n 'ls -l /etc/cni/net.d/; cat /etc/cni/net.d/*.conflist' > /root/cni-before-$n.txt
done
```

**通过条件**：快照文件存在且非空。

### 阶段 2：安装 Calico（尚未切换）

```sh
kubectl apply -f rendered/calico.yaml
kubectl -n kube-system rollout status ds/calico-node --timeout=300s
kubectl -n kube-system rollout status deploy/calico-kube-controllers --timeout=300s
```

Calico 会写 `10-calico.conflist`。它字母序在 `10-flannel.conflist` **之前**，所以**新** Pod 会立刻走 Calico，**存量** Pod 还在 flannel 上——这正是迁移控制器要接管的中间态。

**通过条件**：`calico-node` 5/5 Ready；`calico-kube-controllers` Ready；`kubectl get ippool` 有池。

**此时不要停太久**：存量 Pod 仍在 flannel，新 Pod 在 Calico，跨 CNI 通信由迁移机制处理，但这个中间态不该长期停留。

### 阶段 3：跑迁移

```sh
kubectl apply -f rendered/migration-job.yaml
watch kubectl get jobs -n kube-system flannel-migration    # 1/1 表示完成
kubectl logs -n kube-system -l k8s-app=flannel-migration-controller -f
```

**逐节点 evict 该节点的 Pod**。`orangepi5-max-server1` 上有 94 个（全集群的 57%），那一步影响最大。

**通过条件**：`1/1 completions`；`kubectl get nodes -l projectcalico.org/node-network-during-migration=calico` 返回全部 5 个节点。

### 阶段 4：清理 flannel（**这一步不能省**）

```sh
kubectl delete -f rendered/migration-job.yaml
```

**然后必须清掉 flannel 的 iptables 链。** 官方文档明确说：迁移控制器删了 flannel 的网络设备，但留下了 `FLANNEL-POSTRTG` / `FLANNEL-FWD` 链，**它们的 masquerade 规则会 SNAT 跨节点 Pod 流量，从而破坏 Kubernetes NetworkPolicy**。

```sh
# 每台节点，二选一：
#  方法一（推荐）：滚动重启 —— 规则不跨重启存活
#  方法二：就地清除，立即生效、不中断负载、可重复执行
for n in arm-cluster-master nanopct4-server1 nanopct4-server2 nanopct4-server3 orangepi5-max-server1; do
  ssh $n 'for ipt in iptables-legacy iptables-nft ip6tables-legacy ip6tables-nft; do
    command -v "$ipt" >/dev/null 2>&1 || continue
    "$ipt" -w -t nat -D POSTROUTING -j FLANNEL-POSTRTG 2>/dev/null
    "$ipt" -w -t nat -F FLANNEL-POSTRTG 2>/dev/null
    "$ipt" -w -t nat -X FLANNEL-POSTRTG 2>/dev/null
    "$ipt" -w -t filter -D FORWARD -j FLANNEL-FWD 2>/dev/null
    "$ipt" -w -t filter -F FLANNEL-FWD 2>/dev/null
    "$ipt" -w -t filter -X FLANNEL-FWD 2>/dev/null
  done'
done

kubectl delete -f rendered/calico.yaml   # ❌ 不要！那会删掉 Calico 本身
kubectl -n kube-flannel delete ds kube-flannel-ds
```

> ⚠️ 删 flannel 的 DaemonSet **不是** `kubectl delete -f rendered/calico.yaml`。删 flannel 用它的原始清单 `kube-flannel.yml`，或者只删 DaemonSet（见上）。

### 阶段 5：验证

```sh
bash verify.sh
```

**通过条件**（这条是关键）：**重新跑 `probe-matrix.sh`，`except` 场景现在应当按预期工作**——即场景 3 公网通、内网断。

```sh
bash ../probe-matrix.sh --node nanopct4-server1
# 期望变成：3 内网断 公网通 ✅
# 这正是整件事的目的
```

## 回退

官方路径，逐节点把 CNI 换回 flannel：

```sh
kubectl delete -f rendered/migration-job.yaml -f rendered/calico.yaml
kubectl get nodes -l projectcalico.org/node-network-during-migration=calico
# 对每个上面的节点：
kubectl drain <node>
ssh <node> 'rm /etc/cni/net.d/10-calico.conflist'
ssh <node> 'reboot'
kubectl label node <node> projectcalico.org/node-network-during-migration=flannel --overwrite
kubectl uncordon <node>
# 全部做完后：
kubectl patch ds/kube-flannel-ds -n kube-flannel -p '{"spec":{"template":{"spec":{"nodeSelector":null}}}}'
kubectl label node --all projectcalico.org/node-network-during-migration-
```

**回退的前提是 flannel 的 DaemonSet 还在**。所以阶段 4 里删 flannel 那一步，要等阶段 5 验证通过之后再考虑——或者干脆留着 DaemonSet（只是没有节点选它，不占资源）。

## 本方案不做的事

- **不动 kube-proxy**：Calico 以 `CLUSTER_TYPE: k8s,bgp` 运行，Service 仍由 kube-proxy 处理。本方案不引入 Calico 的 kube-proxy 替代。
- **不引 Typha**：`typha_service_name: none`，5 节点用不上。
- **不启用 eBPF**：用 iptables 数据面，避开厂商内核（`6.1.115-vendor-rk35xx`）上的不确定性。
