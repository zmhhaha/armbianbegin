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
#
# One more consequence of the same imbalance: the job will probably NOT reach
# "1/1 completions" here. Measured 2026-09-21 -- it ended `Failed 0/1` after ~10 h,
# the controller's own pod evicted repeatedly by DiskPressure on the 4 GiB nodes,
# and the last node was labelled by hand. So the acceptance criterion for the
# migration stage is PER-NODE LABEL COVERAGE, not job completion: waiting for 1/1
# hangs forever. The stage below watches coverage, and says so when the
# controller dies without finishing.
#
# `cleanup` removes the controller afterwards. It is the fourth thing the
# controller does not do for itself, and the one with a security edge -- see the
# stage for the cluster-wide RBAC it leaves behind.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

STAGE="${1:-all}"
case "$STAGE" in
    all|preflight|install|migrate|recover|verify|cleanup) ;;
    --help|-h) sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "Unknown stage: $STAGE (all|preflight|install|migrate|recover|verify|cleanup)" >&2; exit 2 ;;
esac

# Every stage talks to the cluster, and without this the failure is silent: the
# assignment below swallows stderr, so a missing kubectl exits 127 saying nothing.
command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }

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
    echo
    echo "  ❗ 判据不是 Job 的 1/1，而是【每个节点都带上 migration 标签】。"
    echo "     本集群上 Job 大概率到不了 1/1：orangepi5-max-server1 上有 94/164 个 Pod，"
    echo "     drain 后无处可去，小节点触发 DiskPressure 把控制器自己的 Pod 反复驱逐。"
    echo "     实测 2026-09-21 最终停在 Failed 0/1，最后一个节点是手工打的标签。"
    echo "     标签由谁打的都一样——验收只看覆盖。（见 ../../docs/calico-migration-run.md）"
    echo

    WATCH_MIN="${MIGRATE_WATCH:-45}"     # 有界观察，不做死等
    total="$(kubectl get nodes --no-headers 2>/dev/null | wc -l)"
    waited=0
    said_stall=0
    while :; do
        cal="$(kubectl get nodes -l projectcalico.org/node-network-during-migration=calico \
               --no-headers 2>/dev/null | wc -l)"
        active="$(kubectl -n kube-system get job flannel-migration \
                  -o jsonpath='{.status.active}' 2>/dev/null || true)"
        [[ -n "$active" ]] && job_state="在跑(${active})" || job_state="不在跑"
        printf '  [%3s min] 已带 calico 标签：%s/%s   控制器 Pod：%s\n' \
            "$((waited / 60))" "$cal" "$total" "$job_state"

        [[ "$cal" == "$total" ]] && { echo "  ✓ 全部节点已迁移。"; break; }
        [[ "$waited" -ge $((WATCH_MIN * 60)) ]] && {
            echo "  ⏱  已观察 ${WATCH_MIN} 分钟仍未覆盖全部节点，交回人工。"; break; }

        if [[ -z "$active" && "$said_stall" == 0 ]]; then
            said_stall=1
            echo "  ❗ 控制器已不在跑，标签却没打齐——它不会自己恢复。手工兜底："
            echo "       kubectl get nodes -L projectcalico.org/node-network-during-migration"
            echo "       kubectl label node <没标签的节点> projectcalico.org/node-network-during-migration=calico --overwrite"
            echo "     打完标签再看该节点上 calico-node 是否起来（desired 会自己跟到 $total）。"
        fi
        sleep 30
        waited=$((waited + 30))
    done

    echo
    echo "  当前覆盖（标签值在最后一列）："
    kubectl get nodes -L projectcalico.org/node-network-during-migration --no-headers 2>/dev/null \
        | sed 's/^/    /' || true
    read -r -p "  确认全部节点都已迁移后按回车进入收尾（没打齐就 Ctrl-C 停下）..." _ || true
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
    echo
    echo "  验收通过后收尾： bash migrate.sh cleanup   （删掉迁移控制器及其 RBAC）"
fi

# ------------------------------------------------------------------ cleanup --
# The fourth thing the controller does not do for itself: it does not remove
# itself. What it leaves in kube-system is a Failed Job, its ConfigMap, and --
# the part that matters -- a ServiceAccount, ClusterRole and ClusterRoleBinding
# named flannel-migration-controller. That ClusterRole can patch/update every
# node, exec into any pod, evict any pod, delete DaemonSets, and delete
# ippools/ipamconfigs/blockaffinities/ipamblocks/ipamhandles. Nothing needs that
# once the migration is finished; a cluster-wide grant left standing for a job
# that does not run is worse than the job itself.
#
# `kubectl delete -f rendered/migration-job.yaml` would remove all five, but
# rendered/ is a gitignored build artifact and may not exist on the machine this
# runs from, so the objects are addressed by name instead.
if [[ "$STAGE" == "cleanup" ]]; then
    echo
    echo "=== cleanup：删掉迁移控制器 ==="

    total="$(kubectl get nodes --no-headers 2>/dev/null | wc -l)"
    cal="$(kubectl get nodes -l projectcalico.org/node-network-during-migration=calico \
           --no-headers 2>/dev/null | wc -l)"
    active="$(kubectl -n kube-system get job flannel-migration \
              -o jsonpath='{.status.active}' 2>/dev/null || true)"

    # Two guards. Both are mistakes that were actually made on 2026-09-21 -- see
    # the "执行过程中我犯的三个错误" section of ../../docs/calico-migration-run.md.
    if [[ "$cal" != "$total" ]]; then
        echo "  ❌ 只有 ${cal}/${total} 个节点带 migration 标签，迁移尚未完成。" >&2
        echo "     控制器是唯一能把迁移跑完的工具，不能提前拆。" >&2
        echo "     先补齐标签： kubectl get nodes -L projectcalico.org/node-network-during-migration" >&2
        exit 1
    fi
    if [[ -n "$active" ]]; then
        echo "  ❌ job/flannel-migration 仍在运行（active=${active}）。" >&2
        echo "     删一个在跑的 Job 会中断控制器——2026-09-21 就是这么把集群停在" >&2
        echo "     最坏的中间点上的。等它结束（哪怕结束成 Failed）再删。" >&2
        exit 1
    fi

    echo "  迁移已完成（${cal}/${total} 节点带标签），控制器未在运行。将删除："
    echo "    job/flannel-migration                              -n kube-system"
    echo "    configmap/flannel-migration-config                 -n kube-system"
    echo "    serviceaccount/flannel-migration-controller        -n kube-system"
    echo "    clusterrole/flannel-migration-controller           (cluster 级)"
    echo "    clusterrolebinding/flannel-migration-controller    (cluster 级)"
    echo
    echo "  最后两项是重点：那份 ClusterRole 允许 patch/update 所有节点、"
    echo "  exec 进任意 Pod、驱逐任意 Pod、删除 DaemonSet，以及删除"
    echo "  ippools/ipamconfigs/blockaffinities/ipamblocks/ipamhandles。"
    echo "  迁移做完后没有东西需要它。"
    echo

    if [[ -n "$(kubectl get job flannel-migration -n kube-system --no-headers 2>/dev/null)" ]] \
       || [[ -n "$(kubectl get clusterrole flannel-migration-controller --no-headers 2>/dev/null)" ]]; then
        read -r -p "  按回车删除上述对象（Ctrl-C 取消）..." _ || true
    fi

    for spec in \
        "job flannel-migration -n kube-system" \
        "configmap flannel-migration-config -n kube-system" \
        "serviceaccount flannel-migration-controller -n kube-system" \
        "clusterrolebinding flannel-migration-controller" \
        "clusterrole flannel-migration-controller"
    do
        # Unquoted on purpose: $spec is a word list. Not fatal on error, so all
        # five are attempted and the check below shows whatever survived.
        # shellcheck disable=SC2086
        out="$(kubectl delete $spec --ignore-not-found 2>&1 || true)"
        printf '  %-58s %s\n' "$spec" "$(tr '\n' ' ' <<<"$out" | sed 's/  */ /g')"
    done

    echo
    echo "  核对（应全部为空）："
    kubectl get job,cm,sa -n kube-system 2>/dev/null | grep -i migration | sed 's/^/    /' || true
    kubectl get clusterrole,clusterrolebinding 2>/dev/null | grep -i migration | sed 's/^/    /' || true
    echo "  完成。flannel 的 DaemonSet 与 kube-flannel.yml 保持不变，回退路径仍然可用。"
fi
