#!/usr/bin/env bash
# Replace flannel with Calico on a LIVE cluster, using Calico's official
# migration controller -- plus the recovery steps that turned out to be
# necessary on a small, unevenly loaded cluster.
#
# Read ../../docs/calico-migration-run.md before running this. Short version:
#
#   The official controller migrates one node at a time: label the node, let
#   calico-node schedule there, drain the node, evict its pods so they come back
#   on Calico. That works when the drained node's pods can land elsewhere.
#
#   On THIS cluster they could not: orangepi5-max-server1 held 94 of 164 pods
#   (57%), and the other four nodes are 4 GiB boxes already near their limits.
#   When orangepi5 was drained there was nowhere for those pods to go. The small
#   nodes hit DiskPressure, the controller's own pod got evicted, and the run
#   stalled half-migrated.
#
#   Three things the controller does NOT clean up after itself, all of which had
#   to be done by hand:
#     1. it leaves the drained node CORDONED (0/5 nodes schedulable, 114 pods
#        pending, until `kubectl uncordon`).
#     2. its per-node `remove-flannel` helper can be evicted before it runs, so
#        that node keeps flannel's dataplane (flannel.1 + cni0 + routes) while
#        its CNI config is already Calico. Half-migrated.
#     3. flannel's iptables chains (FLANNEL-POSTRTG / FLANNEL-FWD) survive. Their
#        masquerade rule SNATs cross-node pod traffic and breaks service routing.
#
# Stages 4-5 below exist to catch exactly those.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

STAGE="${1:-all}"
case "$STAGE" in
    all|preflight|install|migrate|recover|verify) ;;
    --help|-h) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "Unknown stage: $STAGE (all|preflight|install|migrate|recover|verify)" >&2; exit 2 ;;
esac

NODES=$(kubectl get nodes --no-headers -o custom-columns=:metadata.name 2>/dev/null)

# ---------------------------------------------------------------- preflight --
if [[ "$STAGE" == "all" || "$STAGE" == "preflight" ]]; then
    echo "=== 阶段 0：前置检查 ==="
    fail=0
    chk() { printf '  %-42s %s\n' "$1" "$2"; [[ "$2" == *❌* ]] && fail=1; return 0; }

    backend=$(kubectl -n kube-flannel get cm kube-flannel-cfg -o jsonpath='{.data.net-conf\.json}' 2>/dev/null | grep -o '"Type": *"[a-z]*"' || true)
    chk "flannel 后端（必须是 vxlan）" "$([[ "$backend" == *vxlan* ]] && echo ✅ || echo "❌ $backend")"
    chk "flannel DaemonSet 存在" "$(kubectl -n kube-flannel get ds kube-flannel-ds >/dev/null 2>&1 && echo ✅ || echo '❌ 没有 flannel，用 install.sh')"
    for f in cluster-cidr service-cluster-ip-range allocate-node-cidrs; do
        v=$(ps -ef 2>/dev/null | grep -oE -- "--$f=[^ ]*" | head -1)
        chk "controller-manager --$f" "$([[ -n "$v" ]] && echo "✅ $v" || echo ❌)"
    done
    chk "现有 Calico 残留（必须为 0）" "$(c=$(kubectl get crd --no-headers 2>/dev/null | grep -c projectcalico); [[ "$c" == 0 ]] && echo ✅ || echo "❌ $c 个 CRD")"

    echo
    echo "  强烈建议先做："
    echo "    etcd 快照（本方案要重建 Pod，而集群目前没有备份）"
    echo "    记录 /etc/cni/net.d/ 与 /run/flannel/subnet.env（每台节点）"
    echo
    [[ "$fail" == 1 ]] && { echo '  前置检查未通过，停下。' >&2; exit 1; }
    echo '  前置检查通过。'
    [[ "$STAGE" == "preflight" ]] && exit 0
fi

# ------------------------------------------------------------------ install --
if [[ "$STAGE" == "all" || "$STAGE" == "install" ]]; then
    echo
    echo "=== 阶段 1：安装 Calico（尚未切换）==="
    bash mirror.sh
    # NOTE: the migration manifest's calico-node carries
    # `projectcalico.org/node-network-during-migration: calico` in its
    # nodeSelector. That is CORRECT here -- the controller sets the label per
    # node. Do NOT strip it (that is install.sh's job for a fresh cluster).
    kubectl apply -f rendered/calico.yaml 2>&1 | tail -5
    kubectl wait --for=condition=Established --timeout=180s \
        crd/ippools.crd.projectcalico.org crd/felixconfigurations.crd.projectcalico.org 2>&1 | tail -2
    kubectl -n kube-system rollout status deploy/calico-kube-controllers --timeout=300s 2>&1 | tail -2
    echo "  calico-node 此刻 desired=0 是正常的：它在等控制器给节点打标签。"
    [[ "$STAGE" == "install" ]] && exit 0
fi

# ------------------------------------------------------------------ migrate --
if [[ "$STAGE" == "all" || "$STAGE" == "migrate" ]]; then
    echo
    echo "=== 阶段 2：跑迁移控制器（逐节点 drain + evict）==="
    kubectl apply -f rendered/migration-job.yaml 2>&1 | tail -4
    echo "  监控： kubectl -n kube-system get jobs flannel-migration"
    echo "  日志： kubectl -n kube-system logs -l k8s-app=flannel-migration-controller -f"
    echo
    echo "  ⚠️  每个节点会经历 drain → Pod 重建 → 重新就绪，在小集群上很慢（每台可能 10 分钟以上）。"
    echo "     不要因为'看起来卡住'就删 Job——它可能仍在推进。"
    read -r -p "  等到 1/1 完成后按回车继续..." _ || true
fi

# ------------------------------------------------------------------ recover --
if [[ "$STAGE" == "all" || "$STAGE" == "recover" ]]; then
    echo
    echo "=== 阶段 3：控制器不会做的三件收尾 ==="

    echo "--- 3.1 解除被 drain 节点的 cordon ---"
    for n in $NODES; do
        if [[ "$(kubectl get node "$n" -o jsonpath='{.spec.unschedulable}' 2>/dev/null)" == "true" ]]; then
            kubectl uncordon "$n" && echo "  已 uncordon $n"
        fi
    done
    echo "  可调度节点： $(kubectl get nodes --no-headers 2>/dev/null | grep -vc SchedulingDisabled) / $(echo "$NODES" | wc -l)"

    echo
    echo "--- 3.2 各节点 flannel 数据面必须已清除 ---"
    for n in $NODES; do
        out=$(ssh -n -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$n" \
              'echo -n "flannel.1="; ip link show flannel.1 >/dev/null 2>&1 && echo -n 在 || echo -n 无; echo -n " cni0="; ip link show cni0 >/dev/null 2>&1 && echo -n 在 || echo -n 无; echo -n " vxlan.calico="; ip link show vxlan.calico >/dev/null 2>&1 && echo 在 || echo 无' 2>/dev/null)
        printf '  %-24s %s\n' "$n" "$out"
        if [[ "$out" == *"flannel.1=在"* || "$out" == *"cni0=在"* ]]; then
            echo "      ↑ 半迁移：CNI 是 Calico、数据面还是 flannel。控制器被驱逐时就会这样。"
            echo "      修：ssh $n 'ip link delete flannel.1; ip link delete cni0' 然后重启该节点 calico-node"
        fi
    done

    echo
    echo "--- 3.3 flannel 的 iptables 链必须清除 ---"
    for n in $NODES; do
        c=$(ssh -n -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10 "$n" \
            'n=0; for ipt in iptables-legacy iptables-nft iptables; do
               command -v "$ipt" >/dev/null 2>&1 || continue
               "$ipt" -w -t nat -D POSTROUTING -j FLANNEL-POSTRTG 2>/dev/null
               "$ipt" -w -t nat -F FLANNEL-POSTRTG 2>/dev/null
               "$ipt" -w -t nat -X FLANNEL-POSTRTG 2>/dev/null
               "$ipt" -w -t filter -D FORWARD -j FLANNEL-FWD 2>/dev/null
               "$ipt" -w -t filter -F FLANNEL-FWD 2>/dev/null
               "$ipt" -w -t filter -X FLANNEL-FWD 2>/dev/null
             done
             iptables -S 2>/dev/null | grep -c FLANNEL' 2>/dev/null)
        printf '  %-24s 残留 FLANNEL 引用: %s\n' "$n" "${c:-?}"
    done
    echo "  全为 0 才算干净。不为 0 时按 Calico 文档的就地清除法处理（或滚动重启节点）。"
fi

# ------------------------------------------------------------------- verify --
if [[ "$STAGE" == "all" || "$STAGE" == "verify" ]]; then
    echo
    echo "=== 阶段 4：验收 ==="
    bash verify.sh || true
    echo
    echo "  然后跑策略矩阵（引擎无关，Calico 下照跑）："
    echo "    bash ../probe-matrix.sh --node <某个已迁移节点>"
    echo "  期望：场景 3 内网断、公网通。"
    echo
    echo "  ⚠️  若公网通不了，先查 except 列表里有没有 198.18.0.0/15——"
    echo "     软路由若跑 OpenClash fake-ip，所有外部域名都解析到那个段。"
fi
