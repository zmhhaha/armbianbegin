#!/usr/bin/env bash
# 给 kubeadm 控制面节点的内存留出保底额度。
#
# ── 为什么需要这个 ─────────────────────────────────────────────
# kubeadm init 默认给 master 打 node-role.kubernetes.io/control-plane:NoSchedule，
# 业务 Pod 一律落不到 master 上。本集群的 NanoPC 只有 4 GiB 且大部分被宿主机进程
# （ceph-osd / mysqld / gitea）吃掉，于是工作负载全堆到 orangepi5-max-server1 ——
# 2026-09-22 实测 132/200 个 Pod，而同规格 16 GiB 的 master 只跑 8 个、内存用了 22%。
# 该污点已于同日摘除（见 debian_begin.sh）。
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
# 里扣掉，于是调度器看到的可用内存比物理内存少 —— 工作负载从数学上就堆不到
# 挤垮控制面的程度，无论往这台机器上调什么。
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
# 用法（在控制面节点上以 root 执行）：
#     bash apply-master-reservations.sh --dry-run   # 先看会改什么
#     bash apply-master-reservations.sh             # 应用
set -Eeuo pipefail

KUBECTL="${KUBECTL:-/usr/bin/kubectl}"
export KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"
KUBELET_CONFIG="${KUBELET_CONFIG:-/var/lib/kubelet/config.yaml}"
SYSTEM_RESERVED="${SYSTEM_RESERVED:-3Gi}"   # 操作系统 + 系统守护进程
KUBE_RESERVED="${KUBE_RESERVED:-2Gi}"       # kubelet + 容器运行时
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

MARK_BEGIN='# >>> kubelet-reservations (managed by resource_scheduler/apply-master-reservations.sh)'
MARK_END='# <<< kubelet-reservations'

NODE="$(hostname)"

[[ -f "$KUBELET_CONFIG" ]] || {
    echo "$KUBELET_CONFIG 不存在 —— 这个脚本要在控制面节点上跑。" >&2
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

cp -a "$KUBELET_CONFIG" "${KUBELET_CONFIG}.bak-$(date +%Y%m%d-%H%M%S)"

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
for _ in $(seq 1 20); do
    sleep 3
    if "$KUBECTL" get node "$NODE" >/dev/null 2>&1; then break; fi
done
sleep 5

echo
echo "=== 变更后 ==="
"$KUBECTL" get node "$NODE" -o custom-columns='NODE:.metadata.name,CAPACITY:.status.capacity.memory,ALLOCATABLE:.status.allocatable.memory'
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
echo "这个差值就是工作负载碰不到的控制面保底 —— 内核层面挡住，与 Pod 有没有写"
echo "requests 无关。"
echo
echo "注意：已有的 Pod 不会被重新调度（调度器不回填），余量会在后续新建/重启的 Pod 上体现。"
