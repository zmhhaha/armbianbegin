#!/usr/bin/env bash
# Verify that the Metrics API is actually being served, i.e. that `kubectl top`
# works -- not merely that the Deployment is Running.
#
# Run deploy.sh first. Metrics are scraped every --metric-resolution=15s, and the
# aggregation layer needs a ready backend, so `kubectl top` can report <unknown>
# for up to ~75s after the Pods come up. That is why the checks below wait and
# why <unknown> is reported as a warning rather than a failure.
set -uo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# Without this the checks below report a wall of ❌ for a Deployment that is
# probably fine -- "kubectl is missing" is not "metrics-server is broken".
# calico/install.sh:44 and deploy.sh:41 guard the same way; calico/verify.sh
# does not, which is an inconsistency, not a precedent.
command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }

FAIL=0
ok()   { printf '  ✅ %s\n' "$1"; }
bad()  { printf '  ❌ %s\n' "$1"; FAIL=$((FAIL + 1)); }
warn() { printf '  ⚠️  %s\n' "$1"; }

NODES="$(kubectl get nodes --no-headers 2>/dev/null | wc -l)"

echo "=== 1. Deployment 就绪 ==="
ready="$(kubectl -n kube-system get deploy metrics-server -o jsonpath='{.status.readyReplicas}' 2>/dev/null)"
want="$(kubectl -n kube-system get deploy metrics-server -o jsonpath='{.spec.replicas}' 2>/dev/null)"
if [[ -n "$ready" && "$ready" == "$want" ]]; then
    ok "metrics-server ${ready}/${want} Ready"
else
    bad "metrics-server ${ready:-0}/${want:-?} Ready"
    kubectl -n kube-system get pods -l k8s-app=metrics-server -o wide 2>/dev/null | sed 's/^/      /'
fi

echo
echo "=== 2. 两个 replica 落在不同节点（反亲和生效）==="
placed="$(kubectl -n kube-system get pods -l k8s-app=metrics-server \
          -o jsonpath='{range .items[*]}{.spec.nodeName}{"\n"}{end}' 2>/dev/null | sort -u | grep -c . || true)"
if [[ "${placed:-0}" == "$ready" && "${ready:-0}" -gt 0 ]]; then
    ok "${placed} 个 replica 在 ${placed} 个不同节点上"
else
    warn "replica 分布：$(kubectl -n kube-system get pods -l k8s-app=metrics-server -o jsonpath='{range .items[*]}{.metadata.name}={.spec.nodeName} {end}' 2>/dev/null)"
    echo '      若某 replica 长期 Pending，是 required 反亲和找不到第二个可调度节点；'
    echo '      三台 NanoPC 带 memory.guard/over-80:NoSchedule 污点，本就不该跑在那里。'
    echo '      解决：把 deploy.sh 渲染出的 podAntiAffinity 由 required 改成 preferred。'
fi

echo
echo "=== 3. APIService 已注册且 Available ==="
if kubectl get apiservice v1beta1.metrics.k8s.io >/dev/null 2>&1; then
    state="$(kubectl get apiservice v1beta1.metrics.k8s.io \
             -o jsonpath='{range .status.conditions[?(@.type=="Available")]}{.status}{end}' 2>/dev/null || true)"
    if [[ "$state" == "True" ]]; then
        ok "v1beta1.metrics.k8s.io Available=True"
    else
        bad "v1beta1.metrics.k8s.io Available=${state:-<无>}"
        kubectl get apiservice v1beta1.metrics.k8s.io -o yaml 2>/dev/null | sed -n '/status:/,$p' | head -12 | sed 's/^/      /'
    fi
else
    bad "集群里没有 v1beta1.metrics.k8s.io APIService"
fi

echo
echo "=== 4. Metrics API 真的在返回数据 ==="
raw="$(kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes 2>&1 || true)"
if grep -q '"items"' <<<"$raw" && ! grep -q '"items":\[\]' <<<"$raw"; then
    got="$(python3 -c "
import json,sys
try:
    print(len(json.load(sys.stdin)['items']))
except Exception:
    print('?')
" <<<"$raw")"
    ok "Metrics API 返回了 ${got} 个节点的指标（集群共 ${NODES} 个）"
    if [[ "$got" != "?" && "$got" != "$NODES" ]]; then
        warn "节点数对不上：指标 ${got} 个，集群 ${NODES} 个。可能是刚起来还没抓全。"
    fi
else
    bad "Metrics API 没有返回数据"
    head -5 <<<"$raw" | sed 's/^/      /'
fi

echo
echo "=== 5. kubectl top nodes ==="
if out="$(kubectl top nodes 2>&1)"; then
    if grep -q '<unknown>' <<<"$out"; then
        warn "有节点显示 <unknown>——首次抓取尚未完成，等 30–60 秒再跑一次"
        sed 's/^/      /' <<<"$out"
    else
        ok "kubectl top nodes 可用"
        sed 's/^/      /' <<<"$out"
    fi
else
    bad "kubectl top nodes 失败"
    sed 's/^/      /' <<<"$out"
fi

echo
echo "=== 6. kubectl top pods -A ==="
if out="$(kubectl top pods -A 2>&1)"; then
    ok "kubectl top pods -A 可用（$(grep -c . <<<"$out") 行输出）"
    head -8 <<<"$out" | sed 's/^/      /'
else
    bad "kubectl top pods -A 失败"
    sed 's/^/      /' <<<"$out"
fi

echo
if [[ "$FAIL" == 0 ]]; then
    echo '通过。Metrics API 已可用。'
    echo
    echo '⚠️ 这只解决了「看得见」，没有解决「调得动」：调度器依据的是 requests，'
    echo '   而本集群的 Pod 几乎都不写 requests。把观测到的真实用量回填成 requests'
    echo '   才是改善调度的那一步，那是另一件事。'
else
    echo "有 ${FAIL} 项未通过。"
    exit 1
fi
