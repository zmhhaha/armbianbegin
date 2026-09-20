#!/usr/bin/env bash
# Deploy kube-router in firewall-only mode, pinned to ONE node by default.
#
# Rolling this out cluster-wide is the LAST step, not the first. The failure
# mode of a host-iptables policy engine is not "the policy fails to apply" --
# that fails open, i.e. no worse than today -- it is "the node's FORWARD chain
# gets rearranged and pod traffic on that node drops". Read README.md.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

DEFAULT_NODE=nanopct4-server1     # 4 pods, all host-networked infrastructure
NODE="$DEFAULT_NODE"
ALL_NODES=0
DRY_RUN=0

usage() {
    cat <<'EOF'
Usage: bash deploy.sh [--node <name>] [--all-nodes] [--dry-run] [--remove]

  (default)        deploy pinned to nanopct4-server1
  --node <name>    deploy pinned to another node
  --all-nodes      drop the node pin. Only after verify.sh passes on one node.
  --dry-run        render and print, touch nothing
  --remove         delete the DaemonSet (cluster-scoped RBAC is left behind on
                   purpose; the script prints the exact command to remove it)
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --node)      NODE="${2:?--node needs a value}"; shift 2 ;;
        --all-nodes) ALL_NODES=1; shift ;;
        --dry-run)   DRY_RUN=1; shift ;;
        --remove)    REMOVE=1; shift ;;
        --help|-h)   usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ "${REMOVE:-0}" == 1 ]]; then
    command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }
    kubectl -n kube-router delete daemonset kube-router --ignore-not-found
    echo
    echo 'DaemonSet removed. The daemon writes iptables rules directly; to clean those too, run on each node:'
    echo '  docker run --privileged --net=host cloudnativelabs/kube-router --cleanup-config'
    echo
    echo 'Cluster-scoped RBAC was left in place on purpose. To remove it:'
    echo '  kubectl delete clusterrolebinding kube-router && kubectl delete clusterrole kube-router'
    echo '  kubectl delete ns kube-router'
    exit 0
fi

if [[ ! -f rendered/image.txt ]]; then
    echo 'rendered/image.txt is missing. Run bash build.sh first.' >&2
    exit 1
fi
IMAGE="$(tr -d '\r\n' < rendered/image.txt)"
[[ "$IMAGE" == *@sha256:* ]] || { echo "rendered/image.txt is not a digest: $IMAGE" >&2; exit 1; }

RENDERED=rendered/20-kube-router.yaml
mkdir -p rendered
if [[ "$ALL_NODES" == 1 ]]; then
    sed -e '/# --- pins the rollout to ONE node/d' \
        -e '\#kubernetes.io/hostname: __TEST_NODE__#d' \
        k8s/20-kube-router.yaml > "$RENDERED"
    TARGET='all nodes'
else
    sed -e "s/__TEST_NODE__/${NODE}/" k8s/20-kube-router.yaml > "$RENDERED"
    TARGET="node ${NODE}"
fi
sed -i -e "s#__IMAGE__#${IMAGE}#" "$RENDERED"

if grep -n '__[A-Z_]\{2,\}__' "$RENDERED"; then
    echo 'Refusing to apply: unreplaced placeholders above.' >&2
    exit 1
fi

echo "Image   : $IMAGE"
echo "Scope   : $TARGET"
echo "Order   : ns/kube-router -> SA+ClusterRole+Binding -> DaemonSet"
echo

if [[ "$DRY_RUN" == 1 ]]; then
    echo '--- rendered DaemonSet (dry run, nothing applied) ---'
    cat "$RENDERED"
    exit 0
fi

# Only the applying path needs a cluster client; --dry-run renders anywhere.
command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }

kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/10-rbac.yaml
kubectl apply -f "$RENDERED"
kubectl -n kube-router rollout status daemonset/kube-router --timeout=180s

echo
echo 'Applied. kube-router is running and will now program whatever NetworkPolicy'
echo 'objects select pods on the target node(s).'
echo
echo 'NEXT: run bash verify.sh to prove enforcement actually works, before you'
echo 'widen the scope or rely on any policy.'
