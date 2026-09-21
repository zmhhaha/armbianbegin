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
    local kind="$1" ns="$2" name="$3"
    local cur
    cur="$(kubectl -n "$ns" get "$kind" "$name" -o jsonpath='{.spec.template.spec.tolerations}' 2>/dev/null || true)"
    if [[ "$cur" == *"$TAINT_KEY"* ]]; then
        printf '  %-14s %-40s 已有容忍，跳过\n' "$kind" "$ns/$name"
        return 0
    fi
    printf '  %-14s %-40s 补 toleration\n' "$kind" "$ns/$name"
    if [[ "$DRY_RUN" == 1 ]]; then
        echo "      (dry-run) 会追加 tolerations += {key: $TAINT_KEY, operator: Exists, effect: NoExecute}"
        return 0
    fi
    # Strategic merge appends list items by key, so this adds without replacing
    # any existing toleration.
    kubectl -n "$ns" patch "$kind" "$name" --type=strategic -p "$(cat <<EOF
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
patch_one daemonset default csi-cephfsplugin
patch_one daemonset default csi-rbdplugin
echo
echo "=== 给 CSI provisioner Deployment 补（它们同样是基础设施）==="
echo "    注意：这两个有 requiredDuringScheduling 的 podAntiAffinity，要求每个"
echo "    副本落在不同节点。不加容忍时，节点一旦被污点覆盖，它们只能放下 1 个副本，"
echo "    其余的永远 Pending（2026-09-22 实际发生过）。"
patch_one deployment default csi-cephfsplugin-provisioner
patch_one deployment default csi-rbdplugin-provisioner
echo

if [[ "$DRY_RUN" == 1 ]]; then
    echo 'dry-run 结束，未改动集群。'
    exit 0
fi

echo "=== 复核（四项都应为 ✅）==="
kubectl -n default get ds,deploy -o json 2>/dev/null | python3 -c "
import json,sys
want={'csi-cephfsplugin','csi-rbdplugin','csi-cephfsplugin-provisioner','csi-rbdplugin-provisioner'}
for d in json.load(sys.stdin)['items']:
    n=d['metadata']['name']
    if n not in want: continue
    tol=d['spec']['template']['spec'].get('tolerations') or []
    ok=any(t.get('key')=='memory.guard/over-80' and t.get('effect')=='NoExecute' for t in tol)
    print(f\"  {'OK  ' if ok else 'FAIL'} {d['kind']}/{n}\")
"
echo
echo '前置条件就绪。现在可以启用 NoExecute 守卫了。'
