#!/usr/bin/env bash
# ============================================================
#  把八个人格的 oauth2-proxy 从「每个二级域名一个」合并成「八域名共用一个」。
#
#  前提：**Cloudflare 隧道不动** —— 8 条 Public Hostname 的 backend 仍指向
#    oauth2-proxy-<slug>-agent.oauth.svc.cluster.local:4180
#  所以本脚本保留这 8 个 Service 的**名字**当"壳"，只把 spec.selector 指向共享 Pod；
#  域名仍由请求的 Host 头携带，经 passHostHeader 透传到 UI，UI 据此选人格。
#  隧道、Casdoor、UI/API 代码都不需要改。
#
#  用法：
#    bash deploy-shared-agent-proxy.sh                 # 上线：切 selector，旧代理先留着
#    bash deploy-shared-agent-proxy.sh --dry-run       # 只做服务端校验，不改任何东西
#    bash deploy-shared-agent-proxy.sh --retire-old    # 观察稳定后，把 8 个旧代理缩到 0
#    bash deploy-shared-agent-proxy.sh --rollback      # 回滚：恢复 8 个独立代理
#
#  可覆盖的环境变量：
#    CANONICAL_HOST  唯一 canonical 回调所属的域名（默认 bingbichunqiu-agent.panghuer.top）
#    UPSTREAM        共享 UI 地址（默认 baijiazhengming-ui 的 ClusterIP Service）
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="${SCRIPT_DIR}/shared-agent-proxy.yaml"
NAMESPACE_OAUTH="oauth"

AGENTS=(bingbichunqiu daofaziran fofawubian xiaotanrenjian yimaneili zhenzhuzhida zhongkuifumo zhougongjiemeng)
SHARED="oauth2-proxy-baijiazhengming"

CANONICAL_HOST="${CANONICAL_HOST:-bingbichunqiu-agent.panghuer.top}"
UPSTREAM="${UPSTREAM:-http://baijiazhengming-ui.baijiazhengming.svc.cluster.local:7860}"

MODE="apply"
for arg in "$@"; do
    case "${arg}" in
        --dry-run)    MODE="dry-run" ;;
        --retire-old) MODE="retire-old" ;;
        --rollback)   MODE="rollback" ;;
        -h|--help)    sed -n '2,25p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "未知参数: ${arg}（可用：--dry-run / --retire-old / --rollback）" >&2; exit 2 ;;
    esac
done

target_of() { echo "oauth2-proxy-$1-agent"; }

# ---------------------------------------------------------------- 前置校验
# canonical 必须是**当前已在隧道里的**那八个域名之一：Casdoor 里那条回调已经注册过，
# 换成别的域名会因为回调未登记而登录失败。
canonical_ok="no"
for slug in "${AGENTS[@]}"; do
    [[ "${CANONICAL_HOST}" == "${slug}-agent.panghuer.top" ]] && canonical_ok="yes"
done
if [[ "${canonical_ok}" != "yes" ]]; then
    cat >&2 <<EOF
✗ CANONICAL_HOST="${CANONICAL_HOST}" 不是那八个域名之一。

  canonical 必须是**已在 Cloudflare 隧道里**的域名（Casdoor 里那条回调已注册过）：
$(printf '    %s-agent.panghuer.top\n' "${AGENTS[@]}")

  想用新域名做 canonical，就得在隧道里加一条并去 Casdoor 注册回调 —— 那是另一件事。
EOF
    exit 1
fi

# 8 个"壳"必须已经存在：它们的名字来自 Cloudflare 后台的 backend，本脚本不创建新名字。
missing=()
for slug in "${AGENTS[@]}"; do
    kubectl get svc -n "${NAMESPACE_OAUTH}" "$(target_of "${slug}")" -o name >/dev/null 2>&1 \
        || missing+=("$(target_of "${slug}")")
done
if (( ${#missing[@]} > 0 )); then
    cat >&2 <<EOF
✗ 下面这些 Service 在 ${NAMESPACE_OAUTH} 里不存在，不能继续：

$(printf '    %s\n' "${missing[@]}")

  它们是隧道的 backend。请先去 Cloudflare 后台 → 该 tunnel 的 Public Hostname，
  核对八条路由的 backend 到底指向哪些 Service 名（**后台才是权威来源**，
  operator 那份 tunnel-routes.yaml 只是备份），名字对上再来。
EOF
    exit 1
fi

KUBECTL_DRY=()
[[ "${MODE}" == "dry-run" ]] && KUBECTL_DRY=(--dry-run=server)

# ---------------------------------------------------------------- 回滚
if [[ "${MODE}" == "rollback" ]]; then
    echo "== 回滚：恢复 8 个独立代理（各自的 ConfigMap/Deployment/Service 与副本数）=="
    for slug in "${AGENTS[@]}"; do
        target="$(target_of "${slug}")"
        echo "  -> ${target}"
        bash "${SCRIPT_DIR}/deploy-agent-proxy.sh" "${target}" "${UPSTREAM}"
    done
    echo "== 把共享代理缩到 0 =="
    kubectl -n "${NAMESPACE_OAUTH}" scale "deployment/${SHARED}" --replicas=0
    cat <<EOF

回滚完成。共享代理的 ConfigMap 与 Service 仍留着（未删，便于再切回来）：
  kubectl -n ${NAMESPACE_OAUTH} delete configmap oauth2-proxy-config-baijiazhengming
  kubectl -n ${NAMESPACE_OAUTH} delete svc ${SHARED}
  kubectl -n ${NAMESPACE_OAUTH} delete pdb ${SHARED}
EOF
    exit 0
fi

# ---------------------------------------------------------------- 只缩容旧代理
if [[ "${MODE}" == "retire-old" ]]; then
    echo "== 把 8 个旧代理缩到 0（Service 与 ConfigMap 保留，回滚更快）=="
    for slug in "${AGENTS[@]}"; do
        target="$(target_of "${slug}")"
        kubectl -n "${NAMESPACE_OAUTH}" scale "deployment/${target}" --replicas=0
    done
    cat <<EOF

确认八个域名都正常后，可以彻底清掉旧 Deployment 与各自的 ConfigMap：
$(printf '  kubectl -n %s delete deploy oauth2-proxy-%s-agent\n' "${NAMESPACE_OAUTH}" "${AGENTS[@]}")
  # ConfigMap 名字是 oauth2-proxy-config-<slug>-agent，连同删除即可
EOF
    exit 0
fi

# ---------------------------------------------------------------- 上线
echo "== 1/2 部署共享代理（canonical=${CANONICAL_HOST}）=="
echo "        upstream=${UPSTREAM}"
sed -e "s/__CANONICAL_HOST__/${CANONICAL_HOST}/g" \
    -e "s|__UPSTREAM__|${UPSTREAM}|g" \
    "${MANIFEST}" | kubectl apply "${KUBECTL_DRY[@]}" -f -

echo "== 2/2 把 8 个 Service 的 selector 指向共享 Pod =="
cat <<'EOF'
  （上面那条 apply 已经带了 Service 的 spec.selector；这里只做校验）
EOF
for slug in "${AGENTS[@]}"; do
    target="$(target_of "${slug}")"
    if [[ "${MODE}" == "dry-run" ]]; then
        echo "  [dry-run] ${target} 将被指向 app=oauth2-proxy-baijiazhengming"
        continue
    fi
    selector="$(kubectl get svc -n "${NAMESPACE_OAUTH}" "${target}" -o jsonpath='{.spec.selector.app}')"
    if [[ "${selector}" != "${SHARED}" ]]; then
        echo "  ✗ ${target} 的 selector 仍是 '${selector}'，期望 '${SHARED}'" >&2
        exit 1
    fi
    echo "  ✓ ${target} -> ${selector}"
done

if [[ "${MODE}" == "dry-run" ]]; then
    echo; echo "dry-run 结束，未改动集群。"
    exit 0
fi

kubectl -n "${NAMESPACE_OAUTH}" rollout status "deployment/${SHARED}" --timeout=180s

cat <<EOF

上线完成。旧代理**仍在运行**（已不被 Service 选中），回滚只需：
    bash ${BASH_SOURCE[0]##*/} --rollback

请逐个域名验证（每个都要能看到**自己的人格的品牌与文案**）：
$(printf '    https://%s-agent.panghuer.top/\n' "${AGENTS[@]}")

重点验这三个：
  1. 从 A 域名登录后，直接访问 B 域名 —— 应当**免登录**（cookie-domain=.panghuer.top 生效）
  2. 登录往返过程中地址栏会短暂出现 canonical 域名（${CANONICAL_HOST}），
     但最终会跳回你原本访问的域名；若**没有跳回**，就是 --whitelist-domain 没生效
  3. 八个域名各显示各自的人格 —— 这一条同时证明了 Host 头被正确透传

稳定运行几天后再缩容旧代理：
    bash ${BASH_SOURCE[0]##*/} --retire-old
EOF
