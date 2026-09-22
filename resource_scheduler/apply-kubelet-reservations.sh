#!/usr/bin/env bash
# 给节点留出内存保底额度 —— master 和低资源 NanoPC 用同一套机制、不同的数值。
#
# ── 为什么需要这个 ─────────────────────────────────────────────
# 背景：kubeadm init 默认给 master 打 control-plane:NoSchedule，业务 Pod 一律落不到
# master；而三台 NanoPC 只有 3.76 GiB，其中约 2.6 GiB 已被宿主机进程（ceph-osd /
# mysqld / gitea / radosgw）吃掉。于是工作负载全堆到 orangepi5-max-server1 ——
# 2026-09-22 实测 132/200 个 Pod，而同规格 16 GiB 的 master 只跑 8 个、内存用了 22%。
# master 的污点已于同日摘除（见 debian_begin.sh）；NanoPC 仍靠静态污点不接业务 Pod。
#
# ── 摘掉污点之后，控制面靠什么保护 ──────────────────────────────
# 1. 内存：etcd / kube-apiserver / kube-controller-manager / kube-scheduler 都是
#    静态 Pod，priorityClassName=system-node-critical（priority 2000001000），
#    kubelet 的驱逐管理器按优先级排序，它们最后才被驱逐。这一层是有效的。
# 2. 磁盘 I/O：**没有任何保护**。etcd 每次写都要 fsync 落盘，如果同一个根盘上
#    有个爱写盘的邻居（数据库、狂写日志的服务、Ceph OSD），etcd 延迟上升 →
#    API Server 变慢 → 全集群卡顿。优先级机制对 I/O 调度完全无效，污点原本
#    起的作用就是"让那块盘上根本没有邻居"。
#
# ── 本脚本做什么 ───────────────────────────────────────────────
# 设 systemReserved + kubeReserved。这两个值会被 kubelet 从节点的 **allocatable**
# 里扣掉，而 allocatable 决定 `kubepods.slice/memory.max`（见下方实测）。所以它
# 真正的效果是：给"所有 Pod 加起来"设一个**内核层面的硬顶**。
#
# ⚠️ 它**不是**调度信号 —— 这点极易搞反，2026-09-22 我自己就先搞反过一次。
# 调度器的适配检查是 `sum(requests) <= allocatable`，而本集群的 Pod 几乎都不声明
# memory requests（实测：master 上 12 个 Pod 合计 0.23 GiB；三台 NanoPC 上
# calico-node 只有 `cpu: 250m`，kube-proxy 和 CSI 全是 `{}`）。requests 全为 0 时，
# allocatable 压到多小调度器都判定"放得下"，打分还按 requests 算、认为这些节点
# **最空** —— 不但挡不住，反而最吸引调度器。所以指望预留去"劝退"调度器是无效的，
# 劝退只能靠污点 / nodeAffinity。它挡住的是另一件事：**Pod 把宿主机吃死**。
#
# ⚠️ 它**不会**杀掉"必须存在"的基础设施 Pod。calico-node / kube-proxy / CSI node
# plugin 不写 requests 是**正确设计** —— calico-node 一旦因为 allocatable 变小而
# Pending，那台节点就没网络了。它们的安全来自**优先级**：实测这四类都是
# priority=2000001000（system-node-critical，最高档），csi-provisioner 是
# 2000000000（system-cluster-critical）。OOM killer 按 oom_score_adj 挑人，
# 它们最后才轮到。而 mysqld / ceph-osd / gitea 这些宿主机进程**根本不在 kubepods
# cgroup 里**，压根碰不到。
#
# 这是"构造保证"而不是"调度提示"：
#   * 对还不存在的服务自动生效，不需要逐个服务改 manifest；
#   * 不会因为重新 apply 上游 manifest 而丢失 —— 这正是 2026-09-22 CSI DaemonSet
#     丢掉 tolerations 的方式。
#
# ── 实测证据（2026-09-22，arm-cluster-master）──────────────────
# 本机是 cgroup v2 / systemd，kubeadm 生成的 config.yaml 里没有
# enforceNodeAllocatable，于是走 kubelet 默认值 ["pods"] —— kubelet 会把
# kubepods.slice 的 memory.max 设成节点的 allocatable。实测：
#
#     /sys/fs/cgroup/kubepods.slice/memory.max = 16733839360 B = 15.58 GiB
#     MemTotal                                 =                15.58 GiB
#
# 两者相等 = 当前 Pod 加起来可以吃掉整台机器，等于没有上限（实占仅 1.79 GiB）。
#
# 这一点是关键，因为本集群的 Pod 几乎都不声明 memory requests：master 上 12 个
# Pod 的 requests 合计只有 0.23 GiB，控制面静态 Pod 全部是 BestEffort。调度器按
# requests 算容量时看到的几乎是"空节点"，**光靠调度器挡不住它们**；真正拦得住
# BestEffort Pod 的是上面那个 cgroup 硬限额。
#
# systemReserved + kubeReserved 会直接从 allocatable 扣掉，memory.max 跟着变小。
# 于是"给控制面留 5 GiB"不是建议、不是提示，而是内核不放进来的硬边界。
#
# 这里**不**动 enforceNodeAllocatable：它默认已是 ["pods"]，够用。改成
# ["pods","system-reserved","kube-reserved"] 需要额外配 systemReservedCgroup /
# kubeReservedCgroup，配错 kubelet 直接起不来，收益不抵风险。
#
# ── 那 evictionHard 呢（另一套机制）────────────────────────────
# evictionHard 管的是"真没内存了才驱逐"，内置默认 memory.available<100Mi ——
# 几乎要撑爆才动手，config.yaml 里没写、走默认值，且**不受本脚本影响**。
# 预留做的是"根本不让你堆那么满"，比等 eviction 更早、更硬，两者互补。
#
# 用法（在目标节点上以 root 执行）：
#     bash apply-kubelet-reservations.sh --dry-run   # 先看会改什么
#     bash apply-kubelet-reservations.sh             # 应用（幂等，可重复执行）
#
# 数值可覆盖，不传则用下面的默认值：
#     SYSTEM_RESERVED=2.2Gi KUBE_RESERVED=0.5Gi bash apply-kubelet-reservations.sh
#
# 两类节点的取值（都写在 cluster_config.sh，由 debian_begin.sh 在 bootstrap 落地）：
#     master   3Gi   + 2Gi   = 5   GiB  → memory.max 15.58 → 10.58 GiB
#     NanoPC   2.2Gi + 0.5Gi = 2.7 GiB  → memory.max  3.76 →  1.06 GiB
#   NanoPC 那套是**安全网**不是容量开关：宿主机进程已占约 2.6 GiB，顶定在 1.06 GiB
#   才能保证"超了先杀 Pod"，而不是像 2026-09-21 那样杀掉 mysqld（Casdoor 的库就在
#   那台上，于是 40 个 oauth2-proxy 全部 CrashLoop）。基础设施本身占 0.42~0.58 GiB。
set -Eeuo pipefail

KUBECTL="${KUBECTL:-/usr/bin/kubectl}"
# master 上是 super-admin.conf；工作节点没有这个文件，用 kubelet.conf。
# 缺了它 kubectl 会静默失败，脚本就读不到节点状态（本脚本改配置不依赖它，
# 但前后的对比输出会变成空的）。
if [[ -z "${KUBECONFIG:-}" ]]; then
    for _kc in /etc/kubernetes/super-admin.conf /etc/kubernetes/admin.conf /etc/kubernetes/kubelet.conf; do
        [[ -r "$_kc" ]] && { export KUBECONFIG="$_kc"; break; }
    done
fi
KUBELET_CONFIG="${KUBELET_CONFIG:-/var/lib/kubelet/config.yaml}"
SYSTEM_RESERVED="${SYSTEM_RESERVED:-3Gi}"   # 操作系统 + 系统守护进程
KUBE_RESERVED="${KUBE_RESERVED:-2Gi}"       # kubelet + 容器运行时
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

MARK_BEGIN='# >>> kubelet-reservations (managed by resource_scheduler/apply-kubelet-reservations.sh)'
MARK_END='# <<< kubelet-reservations'

NODE="$(hostname)"

[[ -f "$KUBELET_CONFIG" ]] || {
    echo "$KUBELET_CONFIG 不存在 —— 这个脚本要在 Kubernetes 节点上跑。" >&2
    exit 1
}

# 别人手工写过这两个键的话，直接追加会造成 YAML 重复键，kubelet 起不来。
if grep -qE '^(systemReserved|kubeReserved):' "$KUBELET_CONFIG" &&
   ! grep -qF "$MARK_BEGIN" "$KUBELET_CONFIG"; then
    echo "！！ $KUBELET_CONFIG 里已经存在 systemReserved/kubeReserved，且不是本脚本写的。" >&2
    echo "   拒绝追加，以免产生重复键把 kubelet 弄挂。请人工确认后处理。" >&2
    exit 1
fi

echo "=== 目标节点 $NODE ==="
echo "    $KUBELET_CONFIG"
echo "    systemReserved.memory = $SYSTEM_RESERVED"
echo "    kubeReserved.memory   = $KUBE_RESERVED"
echo
printf '  变更前: '
"$KUBECTL" get node "$NODE" -o jsonpath='capacity={.status.capacity.memory}  allocatable={.status.allocatable.memory}' 2>/dev/null || printf '(取不到)'
echo
echo

if [[ "$DRY_RUN" == 1 ]]; then
    echo "(dry-run) 将要执行："
    echo "    1. 备份 $KUBELET_CONFIG"
    echo "    2. 删掉旧的 $MARK_BEGIN .. $MARK_END 块（如果有）"
    echo "    3. 追加新块"
    echo "    4. systemctl restart kubelet"
    exit 0
fi

BACKUP="${KUBELET_CONFIG}.bak-$(date +%Y%m%d-%H%M%S)"
cp -a "$KUBELET_CONFIG" "$BACKUP"

# 幂等：先删掉本脚本上次写的块。按整行精确匹配，不碰其它内容。
if grep -qF "$MARK_BEGIN" "$KUBELET_CONFIG"; then
    awk -v b="$MARK_BEGIN" -v e="$MARK_END" '
        $0 == b { skip = 1; next }
        $0 == e { skip = 0; next }
        !skip   { print }
    ' "$KUBELET_CONFIG" > "${KUBELET_CONFIG}.tmp"
    mv "${KUBELET_CONFIG}.tmp" "$KUBELET_CONFIG"
    echo "  已移除上一次写入的块"
fi

{
    printf '%s\n' "$MARK_BEGIN"
    printf 'systemReserved:\n  memory: %s\n' "$SYSTEM_RESERVED"
    printf 'kubeReserved:\n  memory: %s\n' "$KUBE_RESERVED"
    printf '%s\n' "$MARK_END"
} >> "$KUBELET_CONFIG"
echo "  已写入预留"

echo
echo "=== 重启 kubelet（不会杀掉已在运行的容器，包括控制面静态 Pod）==="
systemctl restart kubelet
sleep 6

# 配置写错 kubelet 会起不来，节点直接 NotReady。发现就回滚，别把节点留在坏状态。
if ! systemctl is-active --quiet kubelet; then
    echo "！！ kubelet 没起来，回滚配置" >&2
    systemctl status kubelet --no-pager -n 15 >&2 || true
    cp -a "$BACKUP" "$KUBELET_CONFIG"
    systemctl restart kubelet
    echo "   已恢复 $BACKUP，请人工检查后再试。" >&2
    exit 1
fi
echo "  kubelet 已重启"

for _ in $(seq 1 15); do
    "$KUBECTL" get node "$NODE" >/dev/null 2>&1 && break
    sleep 3
done

echo
echo "=== 变更后 ==="
"$KUBECTL" get node "$NODE" \
    -o custom-columns='NODE:.metadata.name,CAPACITY:.status.capacity.memory,ALLOCATABLE:.status.allocatable.memory' 2>/dev/null \
    || echo "  (kubectl 读不到节点状态，看下面的 cgroup 数字即可)"
echo
echo "--- kubepods cgroup 硬限额（真正的拦阻点，应该比物理内存小 $SYSTEM_RESERVED + $KUBE_RESERVED）---"
for f in /sys/fs/cgroup/kubepods.slice/memory.max /sys/fs/cgroup/kubepods.slice/memory.current; do
    if [[ -f "$f" ]]; then
        printf '  %-52s %s\n' "$(basename "$(dirname "$f")")/$(basename "$f")" "$(cat "$f")"
    fi
done
echo
echo "期望：allocatable 比 capacity 少约 $SYSTEM_RESERVED + $KUBE_RESERVED，"
echo "      kubepods.slice/memory.max 同步跟着变小。"
echo "这个差值就是所有 Pod 加起来碰不到的保底 —— 内核层面挡住，与 Pod 有没有写"
echo "requests 无关。"
echo
echo "注意：已有的 Pod 不会被重新调度（调度器不回填），余量会在后续新建/重启的 Pod 上体现。"
