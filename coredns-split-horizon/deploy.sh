#!/usr/bin/env bash
# 把 rules.txt 的分流规则追加进集群的 CoreDNS Corefile。
#
# 为什么需要分流 --
#   集群里的 oauth2-proxy 把 https://auth.panghuer.top 当 OIDC issuer 访问。
#   该域名在公网指向国内 VPS（62.234.50.20），于是每次内部鉴权都要
#   出集群 -> 公网 -> VPS -> frp 隧道 -> 回到家里，实测 3336 ms；
#   而 Casdoor 就在同一个集群里。
#
# 为什么指向 Service 名而不是 IP --
#   rewrite 的目标写成完整 Service 名（ingress-nginx-controller.ingress-nginx.svc.cluster.local），
#   由 CoreDNS 的 kubernetes 插件解析成 ClusterIP。Service 重建、ClusterIP 变化都不影响本文件，
#   而写死 IP 的那种做法会在某次重装 ingress-nginx 之后悄悄失效。
#
# 为什么目标是 ingress-nginx 而不是 Casdoor --
#   客户端连的是 443 + TLS，而 Casdoor 只监听 8000 且是明文 HTTP。
#   集群内唯一能"用该域名出示正确证书并终结 TLS"的端点就是 ingress-nginx
#   （证书由 cert-manager 经 Cloudflare DNS-01 签发，见 cert-manager/ 与 oauth/k8s/auth-ingress.yaml）。
#
# 注意：改的是集群级的 Corefile。脚本只做「追加一行 + 滚动重启」，不改任何现有行，
#       并在改动前把原 ConfigMap 备份到 /tmp。
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

KUBECTL=(kubectl)
[[ -n "${KUBECONFIG_FILE:-}" ]] && KUBECTL=(kubectl --kubeconfig="$KUBECONFIG_FILE")
NS=kube-system
CM=coredns
DRY_RUN=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --help|-h) sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

command -v "${KUBECTL[0]}" >/dev/null || { echo 'kubectl is required.' >&2; exit 1; }
[[ -s rules.txt ]] || { echo '缺少 rules.txt' >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"${KUBECTL[@]}" -n "$NS" get cm "$CM" -o jsonpath='{.data.Corefile}' > "$TMP/Corefile.old"
"${KUBECTL[@]}" -n "$NS" get cm "$CM" -o yaml > "$TMP/coredns-backup.yaml"
cp rules.txt "$TMP/rules.txt"

python3 - "$TMP" <<'PY'
import io, sys
tmp = sys.argv[1]
old = io.open(f'{tmp}/Corefile.old', encoding='utf-8').read()
rule = io.open(f'{tmp}/rules.txt', encoding='utf-8').read().rstrip('\n')
marker = 'rewrite stop name exact auth.panghuer.top'
if marker in old:
    print('  分流规则已存在，无需改动 ✓')
    raise SystemExit(0)
idx = old.rstrip().rfind('\n}')
if idx < 0:
    print('  找不到 .:53 块的结尾，停止。', file=sys.stderr)
    raise SystemExit(1)
io.open(f'{tmp}/Corefile.new', 'w', encoding='utf-8').write(old[:idx] + '\n' + rule + old[idx:])
print('  已生成新 Corefile ✓')
PY

if [[ ! -f "$TMP/Corefile.new" ]]; then
    exit 0
fi

echo "  原 Corefile 备份：$TMP/coredns-backup.yaml（脚本退出前会被删，需要留档请先复制 ✓）"
echo "  --- 将要生效的 Corefile ---"
sed 's/^/    /' "$TMP/Corefile.new"

if [[ "$DRY_RUN" == 1 ]]; then
    echo "  DRY-RUN：不实际应用。"
    exit 0
fi

"${KUBECTL[@]}" -n "$NS" create configmap "$CM" --from-file=Corefile="$TMP/Corefile.new" \
    --dry-run=client -o yaml | "${KUBECTL[@]}" apply -f -
"${KUBECTL[@]}" -n "$NS" rollout restart deploy/coredns
"${KUBECTL[@]}" -n "$NS" rollout status deploy/coredns --timeout=180s

echo
echo '完成。下一步：bash verify.sh'
