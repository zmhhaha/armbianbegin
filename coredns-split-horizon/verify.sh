#!/usr/bin/env bash
# 验证集群内分流确实生效：必须从一个【Pod 里】看，而不是从节点或本机看 ——
# 只有 Pod 的 DNS 才走 CoreDNS，节点用的是宿主机的解析器。
#
# 判据（缺一不可）：
#   1. auth.panghuer.top 解析到集群内地址（10.x），而不是公网 62.234.50.20
#   2. 从 Pod 内访问 https://auth.panghuer.top/.well-known/openid-configuration 返回 200
#      且 issuer 仍是 https://auth.panghuer.top（issuer 变了会让所有 oauth2-proxy 拒绝令牌）
#   3. 顺带确认没有把集群 DNS 改坏：kubernetes.default 与一个外网域名仍能解析
set -uo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

FAIL=0
ok()  { printf '  ✅ %s\n' "$1"; }
bad() { printf '  ❌ %s\n' "$1"; FAIL=$((FAIL + 1)); }

command -v kubectl >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }

# 探针 Pod：默认借用 dsh-web 里带 node 的容器（集群内任一带 node 的 Pod 都行）
PROBE_NS="${PROBE_NS:-dsh}"
PROBE_SELECTOR="${PROBE_SELECTOR:-app=dsh-web}"
PROBE_CONTAINER="${PROBE_CONTAINER:-dsh}"

echo "=== 1. 取探针 Pod（$PROBE_NS/$PROBE_SELECTOR 容器 $PROBE_CONTAINER）==="
POD="$(kubectl -n "$PROBE_NS" get pod -l "$PROBE_SELECTOR" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z "$POD" ]]; then
    bad "找不到探针 Pod；可用 PROBE_NS/PROBE_SELECTOR/PROBE_CONTAINER 指定"
    exit 1
fi
ok "探针 Pod：$POD"

echo
echo "=== 2. Pod 内解析与访问 ==="
OUT="$(kubectl -n "$PROBE_NS" exec "$POD" -c "$PROBE_CONTAINER" -- node -e '
const dns = require("dns").promises;
(async () => {
  let addr = "";
  try { addr = (await dns.lookup("auth.panghuer.top")).address; } catch (e) { addr = "ERR:" + e.message; }
  console.log("ADDR " + addr);
  try {
    const t0 = Date.now();
    const res = await fetch("https://auth.panghuer.top/.well-known/openid-configuration", {signal: AbortSignal.timeout(25000)});
    const j = await res.json();
    console.log("OIDC " + res.status + " " + (Date.now()-t0) + " " + j.issuer);
  } catch (e) { console.log("OIDC ERR " + ((e.cause && e.cause.code) || e.message)); }
  for (const n of ["kubernetes.default.svc.cluster.local", "github.com"]) {
    try { console.log("REG " + n + " " + (await dns.lookup(n)).address); }
    catch (e) { console.log("REG " + n + " ERR"); }
  }
})();
' 2>/dev/null)" || true
echo "$OUT" | sed 's/^/    /'

ADDR="$(awk '/^ADDR /{print $2}' <<<"$OUT")"
case "$ADDR" in
    10.*) ok "auth.panghuer.top → $ADDR（集群内 ✓）" ;;
    62.234.50.20) bad "auth.panghuer.top → 公网 VPS，分流未生效（或探针的 DNS 没走 CoreDNS）" ;;
    ERR*) bad "auth.panghuer.top 解析失败：$ADDR" ;;
    *) ok "auth.panghuer.top → $ADDR（非公网，通常可接受）" ;;
esac

OIDC="$(awk '/^OIDC /{print $2, $3, $4}' <<<"$OUT")"
read -r code ms issuer <<<"$OIDC"
if [[ "$code" == "200" ]]; then
    ok "OIDC discovery 200（耗时 ${ms:-?} ms）"
    [[ "$issuer" == "https://auth.panghuer.top" ]] && ok "issuer 正确：$issuer" \
        || bad "issuer 不符：$issuer（会让所有 oauth2-proxy 拒绝令牌）"
else
    bad "OIDC discovery 失败：$(awk '/^OIDC /{print}' <<<"$OUT")"
    echo "      常见原因：Pod 所在命名空间是 default-deny 且 egress 未放行 ingress-nginx"
fi

echo
echo "=== 3. 回归：集群 DNS 未被改坏 ==="
grep -q '^REG kubernetes.default.svc.cluster.local 10\.' <<<"$OUT" \
    && ok "kubernetes.default 正常" || bad "kubernetes.default 解析异常"
grep -q '^REG github.com ' <<<"$OUT" \
    && ok "外网域名解析正常" || bad "外网域名解析异常"

echo
if [[ "$FAIL" -eq 0 ]]; then echo "全部通过 ✅"; else echo "有 $FAIL 项失败 ❌"; exit 1; fi
