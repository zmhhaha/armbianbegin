#!/usr/bin/env bash
# Install Calico as the cluster CNI directly -- for a cluster that was
# bootstrapped WITHOUT flannel, or where flannel was never the right choice.
#
# This is NOT the migration path. If the cluster already runs flannel, use
# migrate.sh instead; installing Calico underneath a live flannel will break it.
#
# The upstream flannel-migration manifest is used as the source, but FOUR things
# must be changed before it is safe to apply outside a migration. All four were
# learned the hard way on 2026-09-21 (see ../../docs/calico-migration-run.md):
#
#   1. the calico-node DaemonSet carries
#      `projectcalico.org/node-network-during-migration: calico` in its
#      nodeSelector. Only the migration controller sets that label. Left in
#      place, calico-node never schedules anywhere and nothing works.
#   2. it sets CALICO_IPV4POOL_IPIP=Always / CALICO_IPV4POOL_VXLAN=Never, which
#      creates an IPIP pool. This cluster runs VXLAN.
#   3. it sets IP=autodetect with no IP_AUTODETECTION_METHOD. On a host with more
#      than one interface that can pick the wrong one -- here it picked addresses
#      that took the whole cluster's pod networking down for two hours.
#      kubernetes-internal-ip pins it to what Kubernetes itself considers the
#      node address.
#   4. it never sets CALICO_IPV4POOL_CIDR, so the default 192.168.0.0/16 would be
#      used -- which does not match --cluster-cidr on this cluster.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

POD_CIDR="${POD_CIDR:-10.244.0.0/16}"
SERVICE_CIDR="${SERVICE_CIDR:-10.96.0.0/12}"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --help|-h)
            echo 'Usage: bash install.sh [--dry-run]'
            echo '  POD_CIDR / SERVICE_CIDR / REGISTRY can be overridden via env.'
            exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }

# --- Refuse to run on a cluster that still has flannel -----------------------
if kubectl -n kube-flannel get ds kube-flannel-ds >/dev/null 2>&1; then
    echo 'kube-flannel is still present. This script is for clusters WITHOUT flannel.' >&2
    echo 'If you are replacing flannel on a live cluster, use migrate.sh.' >&2
    exit 1
fi

# --- Make sure the manifests exist ------------------------------------------
if [[ ! -f rendered/calico.yaml ]]; then
    echo 'rendered/calico.yaml missing; running mirror.sh first.'
    bash mirror.sh
fi

echo "=== 1. 渲染直接部署用的清单 ==="
python3 - "$POD_CIDR" <<'PY'
import sys, yaml
pod_cidr = sys.argv[1]
docs = [d for d in yaml.safe_load_all(open("rendered/calico.yaml", encoding="utf-8")) if d]
for d in docs:
    if d.get("kind") != "DaemonSet":
        continue
    spec = d["spec"]["template"]["spec"]

    # (1) drop the migration gate
    sel = spec.get("nodeSelector") or {}
    sel.pop("projectcalico.org/node-network-during-migration", None)
    if sel:
        spec["nodeSelector"] = sel
    else:
        spec.pop("nodeSelector", None)

    env = spec["containers"][0].setdefault("env", [])
    by_name = {e["name"]: e for e in env}

    def setenv(name, value):
        if name in by_name:
            by_name[name].pop("valueFrom", None)
            by_name[name]["value"] = value
        else:
            env.append({"name": name, "value": value})

    # (2) VXLAN, not IPIP
    setenv("CALICO_IPV4POOL_IPIP", "Never")
    setenv("CALICO_IPV4POOL_VXLAN", "Always")
    # (3) pin the node address to what Kubernetes calls the node IP
    setenv("IP_AUTODETECTION_METHOD", "kubernetes-internal-ip")
    # (4) the pool must match --cluster-cidr
    setenv("CALICO_IPV4POOL_CIDR", pod_cidr)

yaml.safe_dump_all(docs, open("rendered/calico-install.yaml", "w", encoding="utf-8"),
                   default_flow_style=False, sort_keys=False, allow_unicode=True)
print(f"  rendered/calico-install.yaml  ({len(docs)} docs)")
print(f"  pod pool     : {pod_cidr} (VXLAN)")
print(f"  node address : kubernetes-internal-ip")
print(f"  migration gate removed from calico-node nodeSelector")
PY

if [[ "$DRY_RUN" == 1 ]]; then
    echo
    echo '--- dry run: 前 40 行 ---'
    head -40 rendered/calico-install.yaml
    exit 0
fi

echo
echo "=== 2. 安装 Calico ==="
kubectl apply -f rendered/calico-install.yaml 2>&1 | tail -8

echo
echo "=== 3. 等 CRD 建立 ==="
kubectl wait --for=condition=Established --timeout=180s \
    crd/ippools.crd.projectcalico.org \
    crd/felixconfigurations.crd.projectcalico.org \
    crd/clusterinformations.crd.projectcalico.org 2>&1 | tail -3

echo
echo "=== 4. 等 calico-node 覆盖每个节点 ==="
NODES=$(kubectl get nodes --no-headers | wc -l)
kubectl -n kube-system rollout status ds/calico-node --timeout=600s 2>&1 | tail -2
kubectl -n kube-system rollout status deploy/calico-kube-controllers --timeout=300s 2>&1 | tail -2

echo
echo "=== 5. 通过条件 ==="
READY=$(kubectl -n kube-system get ds calico-node -o jsonpath='{.status.numberReady}' 2>/dev/null)
echo "  calico-node Ready: ${READY}/${NODES}   $([[ "$READY" == "$NODES" ]] && echo ✅ || echo '❌ 没覆盖全')"
echo "  IP 池:"
kubectl get ippool -o custom-columns='NAME:.metadata.name,CIDR:.spec.cidr,IPIP:.spec.ipipMode,VXLAN:.spec.vxlanMode' --no-headers 2>/dev/null | sed 's/^/    /'

echo
cat <<'EOF'
完成。下一步（必做）：
  1. 确认 ippool 的 CIDR 是 10.244.0.0/16、VXLAN=Always —— 不是就停下来查。
  2. 起一个测试 Pod，验证公网、跨节点 Pod、ClusterIP 三者都通。
  3. 确认软路由没有 fake-ip 与你的 except 列表冲突：
     任何域名解析出 198.18.0.0/15 段，说明 OpenClash fake-ip 在接管 DNS，
     那么 NetworkPolicy 的 except 列表里绝不能有 198.18.0.0/15。
     见 ../../cloudflare-tunnel/TROUBLESHOOTING-1033.md
EOF
