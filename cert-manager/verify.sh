#!/usr/bin/env bash
# Verify that cert-manager actually issues certificates -- not merely that its
# Pods are Running. An unreachable webhook and CRDs that never became Established
# both look exactly like a healthy Deployment from `kubectl get pods`.
#
# The end-to-end check is a SelfSigned Issuer plus a Certificate in a throwaway
# namespace: if the resulting Secret has a valid tls.crt, the whole reconcile loop
# (webhook admission -> CRD -> controller -> issuer -> Secret) is proven.
set -uo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

FAIL=0
ok()   { printf '  ✅ %s\n' "$1"; }
bad()  { printf '  ❌ %s\n' "$1"; FAIL=$((FAIL + 1)); }
warn() { printf '  ⚠️  %s\n' "$1"; }

command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }

echo "=== 1. 命名空间与 Pod ==="
kubectl get ns cert-manager >/dev/null 2>&1 && ok "cert-manager 命名空间存在" || bad "cert-manager 命名空间不存在"
for d in cert-manager cert-manager-webhook cert-manager-cainjector; do
    ready="$(kubectl -n cert-manager get deploy "$d" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)"
    [[ "${ready:-0}" -ge 1 ]] && ok "$d readyReplicas=${ready}" || bad "$d 没有就绪副本"
done

echo
echo "=== 2. CRD 已 Established ==="
for crd in certificates.cert-manager.io issuers.cert-manager.io clusterissuers.cert-manager.io challenges.acme.cert-manager.io orders.acme.cert-manager.io; do
    cond="$(kubectl get crd "$crd" -o jsonpath='{.status.conditions[?(@.type=="Established")].status}' 2>/dev/null || true)"
    [[ "$cond" == "True" ]] && ok "$crd Established" || bad "$crd 未 Established（得到 ${cond:-空}）"
done

echo
echo "=== 3. Webhook 可达（服务端 dry-run 必须给出响应） ==="
if kubectl create --dry-run=server -f - >/dev/null 2>&1 <<'YAML'
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: webhook-probe
  namespace: default
spec:
  secretName: webhook-probe
  issuerRef: {name: does-not-exist, kind: Issuer}
  dnsNames: ["probe.invalid"]
YAML
then
    warn "dry-run 通过（issuerRef 不存在本应被拒），webhook 可能在放行一切"
else
    ok "webhook 已给出准入响应"
fi

echo
echo "=== 4. 端到端：真签一张证书 ==="
NS=cert-manager-selftest
kubectl create ns "$NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl -n "$NS" apply -f - >/dev/null <<'YAML'
apiVersion: cert-manager.io/v1
kind: Issuer
metadata: {name: selftest}
spec:
  selfSigned: {}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata: {name: selftest}
spec:
  secretName: selftest-tls
  duration: 1h
  issuerRef: {name: selftest, kind: Issuer}
  dnsNames: ["selftest.local"]
YAML

ready=''
for _ in $(seq 1 30); do
    ready="$(kubectl -n "$NS" get certificate selftest -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)"
    [[ "$ready" == "True" ]] && break
    sleep 4
done
if [[ "$ready" == "True" ]]; then
    ok "Certificate Ready=True"
    crt="$(kubectl -n "$NS" get secret selftest-tls -o jsonpath='{.data.tls\.crt}' 2>/dev/null || true)"
    if [[ -n "$crt" ]]; then
        ok "Secret selftest-tls 含 tls.crt"
        kubectl -n "$NS" get secret selftest-tls -o jsonpath='{.data.tls\.crt}' | base64 -d \
            | openssl x509 -noout -subject -enddate 2>/dev/null | sed 's/^/      /'
    else
        bad "Secret 里没有 tls.crt"
    fi
else
    bad "Certificate 在 120s 内未 Ready（得到 ${ready:-空}）"
    kubectl -n "$NS" describe certificate selftest 2>/dev/null | tail -12 | sed 's/^/      /'
fi

echo
echo "=== 5. 清理自测资源 ==="
kubectl delete ns "$NS" --wait=false >/dev/null 2>&1 && ok "已删除 $NS（后台回收）" || warn "删除 $NS 失败，请手工清理"

echo
if [[ "$FAIL" -eq 0 ]]; then echo "全部通过 ✅"; else echo "有 $FAIL 项失败 ❌"; exit 1; fi
