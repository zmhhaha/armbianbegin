#!/usr/bin/env bash
# Deploy cert-manager, so that ClusterIssuers can be reconciled and Ingresses can
# obtain real certificates inside this cluster.
#
# Everything this repo does differently from upstream lives HERE, so that it is
# reviewable in one place:
#
#   1. nodeSelector kubernetes.io/arch: arm64
#      platform-k8s-conventions.md section 九.9: this repo pins the architecture
#      everywhere. Every node here is arm64.
#   2. resources.requests AND resources.limits
#      Upstream sets requests only (or nothing). The same convention requires both.
#   3. --acme-http01-solver-image -> private registry
#      The controller pulls the acmesolver image itself at solve time; it is not
#      in the manifest, so mirror.sh cannot rewrite it, and a missing solver image
#      fails at renewal time, silently. This repo uses DNS-01 (no solver Pod at
#      all), but the flag is set anyway so that a later switch of a single Issuer
#      to HTTP-01 cannot strand the cluster on quay.io.
#
# Assumes mirror.sh has been run and the images are in the private registry.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
CM_VERSION="${CM_VERSION:-v1.19.6}"
MANIFEST="rendered/cert-manager.yaml"
DRY_RUN=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --help|-h) sed -n '2,23p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

[[ -s "$MANIFEST" ]] || { echo "缺少 $MANIFEST，先跑 mirror.sh" >&2; exit 1; }
command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }

patch_deployments() {
    local n=0 name arch limits cname
    while read -r name; do
        [[ -z "$name" ]] && continue
        # The container name is not the deployment name (cert-manager's is
        # cert-manager-controller). A strategic merge patch on a containers list is
        # merged BY NAME, so omitting it fails with "does not contain declared
        # merge key: name" -- read it from the object instead of assuming.
        cname="$(kubectl -n cert-manager get deploy "$name" -o jsonpath='{.spec.template.spec.containers[0].name}' 2>/dev/null || true)"
        [[ -z "$cname" ]] && { echo "  $name: 取不到容器名，跳过" >&2; continue; }
        arch="$(kubectl -n cert-manager get deploy "$name" -o jsonpath='{.spec.template.spec.nodeSelector.kubernetes\.io/arch}' 2>/dev/null || true)"
        if [[ "$arch" != 'arm64' ]]; then
            kubectl -n cert-manager patch deploy "$name" --type=merge \
                -p '{"spec":{"template":{"spec":{"nodeSelector":{"kubernetes.io/arch":"arm64"}}}}}' >/dev/null
            echo "  $name: nodeSelector arm64 ✓"
        fi
        limits="$(kubectl -n cert-manager get deploy "$name" -o jsonpath='{.spec.template.spec.containers[0].resources.limits.cpu}' 2>/dev/null || true)"
        if [[ -z "$limits" ]]; then
            kubectl -n cert-manager patch deploy "$name" --type=strategic \
                -p '{"spec":{"template":{"spec":{"containers":[{"name":"'"$cname"'","resources":{"requests":{"cpu":"20m","memory":"64Mi"},"limits":{"cpu":"500m","memory":"512Mi"}}}]}}}}' >/dev/null
            echo "  $name: requests+limits ✓（容器 $cname）"
        fi
        n=$((n + 1))
    done < <(kubectl -n cert-manager get deploy -o name 2>/dev/null | sed 's#deployment.apps/##')
    echo "  共处理 $n 个 Deployment"
}

patch_solver_image() {
    local want="--acme-http01-solver-image=${REGISTRY}/jetstack/cert-manager-acmesolver:${CM_VERSION}"
    local cur
    cur="$(kubectl -n cert-manager get deploy cert-manager -o jsonpath='{.spec.template.spec.containers[0].args}' 2>/dev/null || true)"
    if grep -q -- '--acme-http01-solver-image' <<<"$cur"; then
        echo "  solver 镜像参数已存在，跳过 ✓"
    else
        kubectl -n cert-manager patch deploy cert-manager --type=json \
            -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"'"$want"'"}]' >/dev/null
        echo "  已设置 $want ✓"
    fi
}

echo "cert-manager ${CM_VERSION}, registry ${REGISTRY}, dry-run=${DRY_RUN}"
if [[ "$DRY_RUN" == 1 ]]; then
    echo "  DRY-RUN: 将应用 $MANIFEST 并打 3 类补丁，不实际执行。"
    grep -oE 'image: "[^"]+"' "$MANIFEST" | sort -u | sed 's/^/    镜像: /'
    exit 0
fi

echo "=== 1. 应用上游清单 ==="
kubectl apply -f "$MANIFEST" | tail -4

echo
echo "=== 2. 等待 rollout ==="
for d in cert-manager cert-manager-webhook cert-manager-cainjector; do
    kubectl -n cert-manager rollout status "deploy/$d" --timeout=300s || { echo "  $d 未就绪" >&2; exit 1; }
done

echo
echo "=== 3. 本集群差异补丁 ==="
patch_deployments
patch_solver_image

echo
echo "=== 4. 补丁后再次等待 rollout ==="
for d in cert-manager cert-manager-webhook cert-manager-cainjector; do
    kubectl -n cert-manager rollout status "deploy/$d" --timeout=300s
done

echo
echo '完成。下一步：bash verify.sh'
