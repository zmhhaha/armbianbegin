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

## 两条路径：直接部署 vs 迁移

| 场景 | 用哪个 |
|---|---|
| **新集群，从来没有 flannel**（或你从一开始就想用 Calico） | **`install.sh`** |
| 集群**已经跑着 flannel**，要换成 Calico | **`migrate.sh`** |

> `install.sh` 会先检查有没有 flannel，有就拒绝运行——在活的 flannel 底下直接装 Calico 会把网络搞坏。

### `install.sh`：直接部署

```sh
bash mirror.sh            # 镜像进私有 registry（install.sh 也会自动调）
bash install.sh --dry-run # 看渲染结果
bash install.sh
```

它用的是上游 flannel-migration 那份清单，但**必须先改四处**，否则直接部署必然失败：

| # | 上游清单里的值 | 为什么必须改 |
|---|---|---|
| 1 | `calico-node` 的 nodeSelector 含 `projectcalico.org/node-network-during-migration: calico` | 那个标签只有迁移控制器会打。直接部署时留着 → **calico-node 永远不调度，什么都起不来** |
| 2 | `CALICO_IPV4POOL_IPIP=Always` / `..._VXLAN=Never` | 会建 **IPIP** 池。本集群跑 VXLAN |
| 3 | `IP=autodetect`，且没有 `IP_AUTODETECTION_METHOD` | **2026-09-21 就是这里断网两小时**：多网卡主机上 autodetect 挑错网卡。改成 `kubernetes-internal-ip` |
| 4 | 没设 `CALICO_IPV4POOL_CIDR` | 默认会用 `192.168.0.0/16`，与 `--cluster-cidr` 不符 |

脚本会把这四处渲染好，并在最后检查 IP 池 CIDR 与封装模式。

### `migrate.sh`：本次实际走的路

```sh
bash migrate.sh preflight   # 前置检查（flannel 后端、controller-manager 参数、无 Calico 残留）
bash migrate.sh install     # 装 Calico，尚未切换
bash migrate.sh migrate     # 跑迁移控制器，逐节点 drain；观察"标签覆盖"而不是 Job 的 1/1
bash migrate.sh recover     # ← 控制器不会做的三件收尾，这次全靠手工补
bash migrate.sh verify
bash migrate.sh cleanup     # ← 第四件：控制器不会删自己（见下）
# 或者 bash migrate.sh  一次跑完（每阶段之间会停）
```

> **编号对不上是有意的**：本文档把"准备"和"快照"算作两个阶段（0 和 1），脚本里它们是同一段 preflight，所以脚本内部的 `阶段 0..4` 比本文的编号各少 1。按**名字**对，别按数字对。
>
> `cleanup` **不在** `all` 链里——它要等 `verify` 通过之后单独跑。

**`recover` 那一段是这份脚本存在的主要理由。** 控制器在三处不收尾，2026-09-21 全部踩到：

1. **它把 drain 过的节点留着 cordon** → 0/5 可调度、114 个 Pod Pending。
2. **它每个节点的 `remove-flannel` 助手 Pod 可能被驱逐**，那台节点就会停在"CNI 配置是 Calico、数据面还是 flannel"的半迁移态。
3. **flannel 的 iptables 链（`FLANNEL-POSTRTG` / `FLANNEL-FWD`）会留下**，其 masquerade 规则 SNAT 跨节点 Pod 流量、破坏 Service 路由。

脚本会逐节点检查并报告这三项，而不是假设控制器做完了。

**第四件事它也不做：它不会删掉自己。** 而它留下的不只是那个 `Failed` 的 Job——还有一份叫 `flannel-migration-controller` 的 ServiceAccount + ClusterRole + ClusterRoleBinding，那份 ClusterRole 能 patch/update 所有节点、exec 进任意 Pod、驱逐任意 Pod、删 DaemonSet，以及删 `ippools`/`ipamconfigs`/`blockaffinities`/`ipamblocks`/`ipamhandles`。迁移做完后没有东西需要它，留在集群里就是一份没人用的集群级授权。`cleanup` 阶段负责清掉，见「阶段 6」。

### 完整过程记录

[../../docs/calico-migration-run.md](../../docs/calico-migration-run.md) —— 含**顶部更正横幅**：2026-09-21 真正卡住集群的不是 CNI，是 DSH 策略 except 列表里的 `198.18.0.0/15`（软路由 OpenClash fake-ip 把所有外部域名解析到那个段）。**"kube-router 不支持 except"是误判。**

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

**通过条件**：`kubectl get nodes -l projectcalico.org/node-network-during-migration=calico` 返回全部节点。

> ### ❗ 通过条件是**标签覆盖**，不是 Job 的 `1/1 completions`
>
> 上一版这里写的是「`1/1 completions`」，**那个判据在本集群上永远达不成，照它等就是死等。**
>
> 实测 2026-09-21：Job 跑了约 10 小时后停在 **`Failed 0/1`**。`orangepi5-max-server1` 被 drain 时那 94 个 Pod 无处可去，4 GiB 的小节点触发 DiskPressure，**控制器自己的 Pod 被反复驱逐**、卡在半迁移态。**最后一个节点的标签是手工打的。**
>
> 所以：迁移是否完成，看的是**每个节点有没有带上迁移标签**——控制器打的还是手工打的都一样。`migrate.sh` 现在按这个判据轮询（默认 45 分钟，`MIGRATE_WATCH` 可调），并在控制器已经不在跑却还没打齐标签时**明确提示手工兜底**：
>
> ```sh
> kubectl label node <没标签的节点> projectcalico.org/node-network-during-migration=calico --overwrite
> ```
>
> **不要因为"看起来卡住"就删 Job。** 实录里犯过的第一个错误就是它：看到停在 1/5 就删，实际控制器仍在推进。

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

> 这一步证明的是**引擎能工作**，不是**你的策略写对了**——`probe-matrix.sh` 用的是它自己创建的一次性探针 Pod，只受它自己那条临时策略约束。真实策略挂在真实负载上的行为，要用真实负载去测：DSH 那份见 [`../../panghu_chat/dsh/verify-network-boundary.sh`](../../panghu_chat/dsh/verify-network-boundary.sh)（它从真实项目容器里探测）。

### 阶段 6：`cleanup`——删掉迁移控制器

```sh
bash migrate.sh cleanup
```

控制器不会删自己。留在 `kube-system` 里的是那个 `Failed` 的 Job、它的 ConfigMap，以及**一份 ServiceAccount + ClusterRole + ClusterRoleBinding**：

| 对象 | 说明 |
|---|---|
| `job/flannel-migration` | `Failed 0/1`，不会自己消失 |
| `configmap/flannel-migration-config` | 迁移用的 flannel 配置快照 |
| `serviceaccount/flannel-migration-controller` | |
| `clusterrole/flannel-migration-controller` | **重点**：可 patch/update 所有节点、exec 进任意 Pod、驱逐任意 Pod、删 DaemonSet、删 `ippools`/`ipamconfigs`/`blockaffinities`/`ipamblocks`/`ipamhandles` |
| `clusterrolebinding/flannel-migration-controller` | 把上面那份 ClusterRole 绑给上面那个 SA |

Job 和 ConfigMap 放着不动其实无害（只是难看），**那份 ClusterRole 不是**——一个已经不跑的 Job 留下一份没人用的集群级授权，是本次迁移最该顺手清掉的东西。

**两道守卫**，任一不满足就退出非零、什么都不删：

1. **并非全部节点带迁移标签 → 拒绝。** 控制器是唯一能把迁移跑完的工具，提前拆掉等于把集群永久留在半迁移态。
2. **Job 仍在 `active` → 拒绝。** 删一个在跑的 Job 会中断控制器——2026-09-21 就是这么把集群停在最坏的中间点上的（实录「我犯的三个错误」第 1 条）。

**通过条件**：`cleanup` 跑完后的自查输出为空（脚本自己会打）。它按对象名删除，**不依赖 `rendered/`**——那个目录是 gitignore 的构建产物，换台机器就没有了。

> flannel 的 DaemonSet 与 `kube-flannel.yml` **不受影响**，回退路径仍然可用。

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
