#!/usr/bin/env bash
# Deploy metrics-server, so that `kubectl top nodes` / `kubectl top pods -A` work.
#
# Three changes to the upstream manifest, all applied HERE so that everything
# this repo does differently from upstream is in one reviewable place:
#
#   1. --kubelet-insecure-tls
#      kubeadm does not enable serverTLSBootstrap, so the kubelet's serving
#      certificate is self-signed and a CA-based verification cannot succeed.
#      Read the cost of this flag in README.md before removing or defending it.
#   2. resources.limits
#      Upstream sets requests only. platform-k8s-conventions.md section 九.9
#      requires both on this cluster.
#   3. nodeSelector kubernetes.io/arch: arm64
#      Upstream pins the OS only; this repo pins the architecture everywhere.
#
# The image registry is rewritten by mirror.sh, not here.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

DRY_RUN=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --help|-h) sed -n '2,17p' "$0"; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [[ ! -f rendered/metrics-server.yaml ]]; then
    echo 'rendered/metrics-server.yaml 不存在；先跑 mirror.sh。' >&2
    exit 1
fi

echo "=== 1. 渲染（上游清单 + 三处改动）==="
python3 - <<'PY'
import sys
import yaml

SRC = "rendered/metrics-server.yaml"
OUT = "rendered/metrics-server-deploy.yaml"

docs = [d for d in yaml.safe_load_all(open(SRC, encoding="utf-8")) if d]

# Fail loudly rather than silently mis-patch: if upstream renames or restructures
# anything, this must stop, not produce a half-patched manifest.
dep = next((d for d in docs
            if d.get("kind") == "Deployment" and d["metadata"]["name"] == "metrics-server"), None)
if dep is None:
    sys.exit("  渲染失败：清单里没有 metrics-server Deployment，上游结构变了。")
pod = dep["spec"]["template"]["spec"]
ctr = next((c for c in pod.get("containers", []) if c["name"] == "metrics-server"), None)
if ctr is None:
    sys.exit("  渲染失败：Deployment 里没有名为 metrics-server 的容器。")

# 1. See the header. The flag is idempotent so a re-render is safe.
if "--kubelet-insecure-tls" not in ctr["args"]:
    ctr["args"].append("--kubelet-insecure-tls")

# 2. Requests AND limits. On this cluster most Pods declare no memory request at
#    all, which is exactly why the metrics are worth having -- so the values here
#    are stated explicitly rather than inherited.
res = ctr.setdefault("resources", {})
req = res.setdefault("requests", {})
req.setdefault("cpu", "100m")
req.setdefault("memory", "200Mi")
res["limits"] = {"cpu": "500m", "memory": "300Mi"}

# 3. Architecture pinning, repo convention.
pod.setdefault("nodeSelector", {})["kubernetes.io/arch"] = "arm64"

yaml.safe_dump_all(docs, open(OUT, "w", encoding="utf-8"), allow_unicode=True, sort_keys=False)
print(f"  {OUT}  ({len(docs)} 文档)")

# Re-read and assert, so a silent no-op cannot reach the cluster.
check = [d for d in yaml.safe_load_all(open(OUT, encoding="utf-8")) if d]
cdep = next(d for d in check if d.get("kind") == "Deployment")
cc = cdep["spec"]["template"]["spec"]["containers"][0]
assert "--kubelet-insecure-tls" in cc["args"], "flag 没写进去"
assert cc["resources"]["limits"]["memory"] == "300Mi", "limits 没写进去"
assert cdep["spec"]["template"]["spec"]["nodeSelector"]["kubernetes.io/arch"] == "arm64", "nodeSelector 没写进去"
print("  ✓ 三处改动都已落地")
PY

if [[ "$DRY_RUN" == 1 ]]; then
    echo
    echo '--- rendered/metrics-server-deploy.yaml（前 60 行）---'
    head -60 rendered/metrics-server-deploy.yaml
    echo '...'
    echo '（--dry-run：只渲染，不碰集群）'
    exit 0
fi

command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }

echo
echo "=== 2. apply ==="
kubectl apply -f rendered/metrics-server-deploy.yaml 2>&1 | tail -20

echo
echo "=== 3. 等 rollout ==="
kubectl -n kube-system rollout status deploy/metrics-server --timeout=300s

echo
echo "=== 4. 等 APIService 变 Available ==="
# Rollout alone is not the condition: the aggregation layer needs a ready
# backend, and the first metric point needs --metric-resolution=15s to elapse.
for i in $(seq 1 24); do
    state="$(kubectl get apiservice v1beta1.metrics.k8s.io \
             -o jsonpath='{range .status.conditions[?(@.type=="Available")]}{.status}{end}' 2>/dev/null || true)"
    if [[ "$state" == "True" ]]; then
        echo "  ✓ v1beta1.metrics.k8s.io Available（第 ${i} 次检查）"
        break
    fi
    printf '  ...等待中（%s/24）\n' "$i"
    sleep 5
done
if [[ "${state:-}" != "True" ]]; then
    echo "  ⚠️  APIService 仍未 Available。跑 bash verify.sh 看具体哪一层没通；" >&2
    echo "     常见原因：镜像没拉起来、replica 因反亲和 Pending。" >&2
fi

echo
echo "=== 5. 结果 ==="
kubectl -n kube-system get pods -l k8s-app=metrics-server -o wide 2>/dev/null | sed 's/^/    /' || true
echo
kubectl top nodes 2>&1 | sed 's/^/    /' || true
echo
echo '指标首次可用可能有 15–75 秒延迟；`<unknown>` 是正常的，等一会儿再跑 verify.sh。'
