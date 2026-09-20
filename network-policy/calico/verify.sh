#!/usr/bin/env bash
# Verify the flannel -> Calico migration actually landed.
#
# This checks the migration itself. It does NOT re-check your policies -- for
# that, run ../probe-matrix.sh, which is the whole point of the exercise: the
# `except` scenario should now behave (internal blocked, public reachable).
set -uo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

FAIL=0
ok()   { printf '  ✅ %s\n' "$1"; }
bad()  { printf '  ❌ %s\n' "$1"; FAIL=$((FAIL + 1)); }
warn() { printf '  ⚠️  %s\n' "$1"; }

echo "=== 1. calico-node 覆盖每个节点 ==="
desired="$(kubectl get nodes --no-headers 2>/dev/null | wc -l)"
ready="$(kubectl -n kube-system get ds calico-node -o jsonpath='{.status.numberReady}' 2>/dev/null)"
[[ "$ready" == "$desired" && -n "$ready" ]] && ok "calico-node ${ready}/${desired} Ready" \
    || bad "calico-node ${ready:-?}/${desired} Ready"

echo
echo "=== 2. 控制面 ==="
kubectl -n kube-system rollout status deploy/calico-kube-controllers --timeout=10s >/dev/null 2>&1 \
    && ok "calico-kube-controllers Ready" || bad "calico-kube-controllers 未就绪"

echo
echo "=== 3. 迁移完成后节点应全部标记为 calico ==="
all="$(kubectl get nodes --no-headers -o custom-columns=:metadata.name | wc -l)"
calf="$(kubectl get nodes -l projectcalico.org/node-network-during-migration=calico --no-headers 2>/dev/null | wc -l)"
if [[ "$calf" == "$all" ]]; then
    ok "全部 ${all} 个节点已迁移到 Calico"
else
    warn "只有 ${calf}/${all} 个节点标记为 calico"
    kubectl get nodes -l projectcalico.org/node-network-during-migration=flannel --no-headers 2>/dev/null | sed 's/^/      /'
    echo "      若迁移任务仍在跑，这是正常的；跑完了还这样就是没完成。"
fi

echo
echo "=== 4. IPAM 池存在且 CIDR 正确 ==="
pool="$(kubectl get ippool -o jsonpath='{.items[0].spec.cidr}' 2>/dev/null)"
[[ "$pool" == "10.244.0.0/16" ]] && ok "ippool cidr=${pool}" || bad "ippool cidr=${pool:-未找到}（期望 10.244.0.0/16）"

echo
echo "=== 5. flannel 残留 ==="
if kubectl -n kube-flannel get ds kube-flannel-ds >/dev/null 2>&1; then
    gone="$(kubectl -n kube-flannel get ds kube-flannel-ds -o jsonpath='{.status.numberReady}' 2>/dev/null)"
    [[ "${gone:-0}" == "0" ]] && ok "flannel DaemonSet 仍在但已无 Ready Pod（可留作回退）" \
        || warn "flannel DaemonSet 仍有 ${gone} 个 Pod 在跑"
else
    ok "flannel DaemonSet 已删除"
fi

echo
echo "=== 6. flannel 的 iptables 链（必须清掉，否则破坏 NetworkPolicy） ==="
echo "  在每台节点上检查（脚本无法远程覆盖全部节点，请手工跑一次）："
echo "    for n in arm-cluster-master nanopct4-server1 nanopct4-server2 nanopct4-server3 orangepi5-max-server1; do"
echo "      echo -n \"\$n: \"; ssh \$n 'iptables -S 2>/dev/null | grep -c FLANNEL'"
echo "    done"
echo "  期望全部为 0。不为 0 就按 README 阶段 4 的方法二清除。"

echo
echo "=== 7. 全集群 Pod 健康 ==="
total="$(kubectl get pods -A --no-headers 2>/dev/null | wc -l)"
unhealthy="$(kubectl get pods -A --no-headers 2>/dev/null | awk '$4!="Running" && $4!="Completed" {print $1"/"$2"  "$4}')"
if [[ -z "$unhealthy" ]]; then
    ok "全部 ${total} 个 Pod Running/Completed"
else
    bad "有 Pod 不正常（${total} 个中）："
    echo "$unhealthy" | sed 's/^/      /'
fi

echo
echo "=== 8. 跨节点 Pod 连通性 ==="
# Pick one pod per node and have each try to reach a known ClusterIP service.
# Cross-node is the path flannel's leftover masquerade rule used to break.
if kubectl get svc -n llm llm-service >/dev/null 2>&1; then
    target="llm-service.llm.svc.cluster.local"
    probe_node() {
        local node="$1"
        local pod
        pod="$(kubectl get pods -A --field-selector "spec.nodeName=${node}" \
                -o jsonpath='{range .items[?(@.status.phase=="Running")]}{.metadata.namespace}/{.metadata.name}{"\n"}{end}' \
                2>/dev/null | grep -vE 'kube-flannel|calico|kube-proxy|csi-' | head -1)"
        [[ -z "$pod" ]] && { echo "      ${node}: 无可用探针 Pod"; return; }
        local ns="${pod%%/*}" name="${pod##*/}"
        out="$(kubectl -n "$ns" exec "$name" -- timeout 4 sh -c "echo > /dev/tcp/${target}/80" 2>&1)"
        [[ -z "$out" ]] && echo "      ${node}: 可达 (${pod})" || echo "      ${node}: 不可达 (${pod})"
    }
    for n in $(kubectl get nodes --no-headers -o custom-columns=:metadata.name); do probe_node "$n"; done
    echo "      （只能证明该 Pod 里恰好有 sh；仅作烟雾测试）"
else
    warn "找不到 llm-service，跳过连通性烟雾测试"
fi

echo
echo "=== 9. 真正的验收：策略引擎现在能用了吗 ==="
cat <<'EOF'
  迁移成功 ≠ 目的达成。目的是让 NetworkPolicy 真正生效，
  尤其是 kube-router 表达不出来的 `ipBlock ... except`。

    bash ../probe-matrix.sh --node nanopct4-server1

  那个脚本已经改成引擎无关，Calico 下照跑。
  期望：场景 3 内网**断**、公网**通**。
  （在 kube-router 下是公网也断——那正是放弃它的原因。）
EOF

echo
if [[ "$FAIL" == 0 ]]; then
    echo "通过。"
else
    echo "有 ${FAIL} 项未通过。"
    exit 1
fi
