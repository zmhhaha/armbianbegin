#!/usr/bin/env bash
# Prerequisite for switching the memory guard to NoExecute.
#
# NoExecute evicts every pod that does not tolerate the taint -- including
# DaemonSets. Two of this cluster's infrastructure DaemonSets do not tolerate it
# and must be given the toleration FIRST, or the guard will tear storage off the
# very node it is trying to relieve:
#
#   default/csi-cephfsplugin   tolerates only control-plane NoSchedule
#   default/csi-rbdplugin      same
#
# The other two are already safe:
#   kube-system/calico-node    tolerates "*:NoExecute"
#   kube-system/kube-proxy     tolerates "*" with no effect (matches all effects)
#
# Run this BEFORE enabling the NoExecute guard, and re-run it after any change
# that replaces the CSI DaemonSets from their upstream manifests.
set -Eeuo pipefail

TAINT_KEY="memory.guard/over-80"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }

patch_one() {
    local ns="$1" name="$2"
    local cur
    cur="$(kubectl -n "$ns" get ds "$name" -o jsonpath='{.spec.template.spec.tolerations}' 2>/dev/null || true)"
    if [[ "$cur" == *"$TAINT_KEY"* ]]; then
        printf '  %-34s 已有容忍，跳过\n' "$ns/$name"
        return 0
    fi
    printf '  %-34s 补 toleration\n' "$ns/$name"
    if [[ "$DRY_RUN" == 1 ]]; then
        echo "      (dry-run) 会追加 tolerations += {key: $TAINT_KEY, operator: Exists, effect: NoExecute}"
        return 0
    fi
    # Strategic merge appends list items by key, so this adds without replacing
    # any existing toleration.
    kubectl -n "$ns" patch daemonset "$name" --type=strategic -p "$(cat <<EOF
spec:
  template:
    spec:
      tolerations:
      - key: $TAINT_KEY
        operator: Exists
        effect: NoExecute
EOF
)" >/dev/null
    echo "      已应用"
}

echo "=== 给基础设施 DaemonSet 补 $TAINT_KEY:NoExecute 容忍 ==="
patch_one default csi-cephfsplugin
patch_one default csi-rbdplugin
echo

if [[ "$DRY_RUN" == 1 ]]; then
    echo 'dry-run 结束，未改动集群。'
    exit 0
fi

echo "=== 复核（两个都应为 ✅）==="
kubectl get ds -n default -o json 2>/dev/null | python3 -c "
import json,sys
for d in json.load(sys.stdin)['items']:
    tol=d['spec']['template']['spec'].get('tolerations') or []
    ok=any(t.get('key')=='memory.guard/over-80' and t.get('effect')=='NoExecute' for t in tol)
    print(f\"  {'✅' if ok else '❌'} default/{d['metadata']['name']}\")
"
echo
echo '前置条件就绪。现在可以启用 NoExecute 守卫了。'
