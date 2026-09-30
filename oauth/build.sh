#!/bin/bash
# ============================================================
#  oauth2-proxy + Casdoor — 拉取镜像并推送到私有 registry
#
#  用法:
#    ./build.sh              # 拉取 + 推送到私有 registry（默认）
#    ./build.sh --push       # 拉取 + 推送（默认行为）
#    ./build.sh --deploy     # 拉取 + 推送 + 部署 Casdoor 基础服务（**不含** oauth2-proxy 实例）
#    ./build.sh --deploy-proxy  # 已不可用：只打印 oauth2-proxy 实例的正确部署方式后退出
#
#  镜像:
#    oauth2-proxy — quay.io/oauth2-proxy/oauth2-proxy (ARM64)
#    Casdoor      — casbin/casdoor (ARM64, 非 all-in-one)
#
#  ⚠️ oauth2-proxy 实例不由本脚本部署。各家族的实例形状（回调参数、匿名放行路由、
#     upstream 端口）已经分化，通用模板只适用于其中一部分 —— 见 deploy_proxy_guidance()
#     的说明，以及 k8s/deploy-{agent,game,hublog}-proxy.sh 三个专用脚本。
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"
[ -f "../cluster_config.sh" ] && source "../cluster_config.sh"

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
K="${KUBECONFIG:---kubeconfig=/etc/kubernetes/super-admin.conf}"

OAUTH_TAG="${OAUTH_TAG:-v7.8.0}"
# Casdoor 用**不可变 tag**：清单 oauth/k8s/casdoor-deployment.yaml 里固定的是同一个版本，
# 两边要一起改。历史上这里默认 latest、清单也写 latest，叠加 imagePullPolicy: Always，
# 结果就是「Pod 一重启就换版本」、升级不可控。改版本与升级步骤见清单顶部注释。
#
# ⚠️ tag 形状：Casdoor 的 CI 把 release tag 的 `v` 去掉再推镜像
#    （build.yml: `version=${GITHUB_REF_NAME#v}`，注释写明 "tag `v1.2.3` publishes `1.2.3`"）。
#    所以 GitHub 上游是 v4.11.0、**Docker Hub 上是 4.11.0** —— 写成 v4.11.0 会 403/404，
#    然后 fallback 到 registry-1.docker.io 报一个和真实原因无关的 EOF。
CASDOOR_TAG="${CASDOOR_TAG:-4.11.0}"

# 国内加速前缀。默认已指向实测可用的源（2026-09-29 验证 casbin/casdoor:4.11.0 返回 200 且含 arm64）；
# 传空串则改用服务器 Docker daemon 的 registry-mirrors（见 debian_begin.sh 的 daemon.json）。
# 同一约定见 network-policy/build.sh、panghu_chat/hermes/build.sh。
#
# ⚠️ 这里只能是**主机名**：docker 的镜像引用不接受 scheme，带 `https://` 会直接
#    `invalid reference format`。下面顺手把误传的 scheme 去掉，降低踩坑概率。
DOCKERHUB_MIRROR="${DOCKERHUB_MIRROR:-docker.m.daocloud.io}"
DOCKERHUB_MIRROR="${DOCKERHUB_MIRROR#https://}"; DOCKERHUB_MIRROR="${DOCKERHUB_MIRROR#http://}"
QUAY_MIRROR="${QUAY_MIRROR:-}"
QUAY_MIRROR="${QUAY_MIRROR#https://}"; QUAY_MIRROR="${QUAY_MIRROR#http://}"

pull_and_push() {
    local official="$1" local_img="$2" name="$3"
    echo "=== [${name}] Pulling ${official} ==="
    if ! docker pull "${official}"; then
        echo "‼️ 拉取失败：${official}" >&2
        echo "   换源（只填主机名，不要带 https://）：DOCKERHUB_MIRROR=docker.1ms.run bash oauth/build.sh（QUAY 用 QUAY_MIRROR=）" >&2
        return 1
    fi
    echo "=== [${name}] Pushing to ${local_img} ==="
    docker tag "${official}" "${local_img}"
    docker push "${local_img}"
}

pull_and_push_all() {
    local proxy_src="quay.io/oauth2-proxy/oauth2-proxy:${OAUTH_TAG}"
    [[ -n "${QUAY_MIRROR}" ]] && proxy_src="${QUAY_MIRROR%/}/oauth2-proxy/oauth2-proxy:${OAUTH_TAG}"
    pull_and_push "${proxy_src}" \
        "${REGISTRY}/oauth2-proxy:${OAUTH_TAG}" "oauth2-proxy"
    docker tag "${REGISTRY}/oauth2-proxy:${OAUTH_TAG}" "${REGISTRY}/oauth2-proxy:latest"
    docker push "${REGISTRY}/oauth2-proxy:latest"

    local casdoor_src="casbin/casdoor:${CASDOOR_TAG}"
    [[ -n "${DOCKERHUB_MIRROR}" ]] && casdoor_src="${DOCKERHUB_MIRROR%/}/${casdoor_src}"
    pull_and_push "${casdoor_src}" \
        "${REGISTRY}/casdoor:${CASDOOR_TAG}" "Casdoor"
    # ⚠️ 这里**故意不再**把新版本同时打成 :latest。
    # 之前会把 :latest 覆盖成刚拉到的版本，等于每升一次就抹掉一次回滚点：
    # 想 `kubectl rollout undo` 回旧版时，:latest 已经指向新版本了（清单里也没人再用
    # :latest，全部固定不可变 tag）。回滚改为显式拉旧版本：
    #   docker pull docker.m.daocloud.io/casbin/casdoor:3.113.0   # Docker tag 不带 v
    #   docker tag  docker.m.daocloud.io/casbin/casdoor:3.113.0 ${REGISTRY}/casdoor:3.113.0
    #   docker push ${REGISTRY}/casdoor:3.113.0
    #   kubectl -n oauth set image deploy/casdoor casdoor=${REGISTRY}/casdoor:3.113.0

    echo ""
    echo "全部镜像已推送:"
    echo "  ${REGISTRY}/oauth2-proxy:${OAUTH_TAG}"
    echo "  ${REGISTRY}/casdoor:${CASDOOR_TAG}"
}

deploy_k8s() {
    echo ""
    echo "=== 部署 Casdoor 基础服务到 K8s ==="
    kubectl apply ${K} -f k8s/namespace.yaml
    # 2026-10-01 修正：这里原来还会 apply k8s/secret.yaml，而那份清单里是**占位符**
    # （COOKIE_SECRET=change-me-...、OIDC_CLIENT_ID=oauth2-proxy-client-id）。
    # 线上 oauth2-proxy-secret 由 Vault 经 ExternalSecret 管理（creationPolicy: Owner），
    # apply 会把真凭证覆盖掉。代理是 envFrom.secretRef，环境变量只在容器启动时注入一次，
    # 所以在跑的 Pod 不受影响 —— 但只要有一个代理重启，它就会拿占位符 client_id 去
    # Casdoor 换 token（登录直接失败），直到 ExternalSecret 下次同步
    # （refreshInterval: 1h）才恢复。新集群请走 Vault，不要用这份占位符清单。
    if ! kubectl get ${K} -n oauth secret oauth2-proxy-secret >/dev/null 2>&1; then
        echo "  ⚠️ oauth 命名空间里还没有 oauth2-proxy-secret" >&2
        echo "     请应用 vault/inventory/oauth-externalsecret.yaml（不要用 k8s/secret.yaml 的占位符）" >&2
    fi
    kubectl apply ${K} -f k8s/casdoor-configmap.yaml
    # 2026-09-29 修正：这里原写作 k8s/deployment.yaml，而该文件并不存在（实际叫
    # casdoor-deployment.yaml）。配合 set -e，--deploy 会中止在这一行，后面的
    # mysql.yaml / ExternalSecret 全都不会被 apply。
    kubectl apply ${K} -f k8s/casdoor-deployment.yaml   # Casdoor deployment
    kubectl apply ${K} -f k8s/mysql.yaml          # MySQL for Casdoor

    # ExternalSecret 同步：原来在 deploy_proxy() 里做，deploy_proxy 不再部署实例后挪到此处。
    echo ""
    echo "=== 同步 oauth2-proxy-secret 从 Vault ==="
    if [ -f "../vault/inventory/oauth-externalsecret.yaml" ]; then
        kubectl apply ${K} -f ../vault/inventory/oauth-externalsecret.yaml
        echo "  ExternalSecret 已应用"
    else
        echo "  ⚠️ vault/inventory/oauth-externalsecret.yaml 未找到，跳过" >&2
        echo "  Vault 未部署时需按 vault/inventory/02-panghu-agent.md 手动创建 Secret" >&2
    fi

    echo ""
    echo "=== Casdoor 基础服务已部署 ==="
}

# 2026-10-01：本函数**不再**部署 oauth2-proxy 实例，只打印正确做法。
#
# 原来它遍历一份写死的名单，把 k8s/proxy-configmap.yaml / k8s/proxy-deployment.yaml 用
# sed 换掉 __TARGET_NAME__ 就 apply。这套逻辑有三处已经和线上脱节，跑一次就是故障：
#
#  1) proxy-configmap.yaml 里还有 __UPSTREAM__，原来从来不替换它。apply 之后在线实例的
#     ConfigMap 会变成 `uri: __UPSTREAM__`；实测这个值会让 oauth2-proxy 在**启动时 panic**
#     （validation.Validate: index out of range [0] with length 0）。而改 ConfigMap 不触发
#     滚动更新，在跑的 Pod 照旧 —— 所以 apply 当时看不出任何异常，等它下次重启/滚动就直接
#     CrashLoop，该域名登录全挂。受害的是名单里与线上同名的 research-agent /
#     scientific-agent / txt2img。
#  2) 名单停在 2026-09-28 之前。八个人格（daofaziran / fofawubian / xiaotanrenjian /
#     yimaneili / zhenzhuzhida / zhongkuifumo / zhougongjiemeng / bingbichunqiu）的
#     per-domain 代理那时已经删除，改由共享实例 oauth2-proxy-baijiazhengming 服务。
#     跑一次会新建 8 个线上并不存在的 Deployment，同时漏掉真正在线的 10 个。
#  3) hublog 的 5 条 --skip-auth-route（匿名分享页）只存在于它自己的脚本里，用通用模板
#     apply 会把它们抹掉，分享页会开始要求登录。
#
# 各家族的实例形状（回调参数、匿名放行路由、upstream 端口）本来就不一样，正确做法是按
# 家族用各自的脚本，而不是从通用模板盲拍。
deploy_proxy_guidance() {
    cat >&2 <<'EOS'

⚠️  oauth2-proxy 实例不由本脚本部署 —— 请按家族使用 k8s/ 下的专用脚本：

    一域一实例（含多域名共享实例 baijiazhengming）：
      bash k8s/deploy-agent-proxy.sh <target> [upstream]
      默认 upstream 是 http://ui.<target>.svc.cluster.local:7860；共享实例要显式给：
        bash k8s/deploy-agent-proxy.sh baijiazhengming \
          http://baijiazhengming-ui.baijiazhengming.svc.cluster.local:7860

    游戏系（guanliao / qianfu / school-of-one / shapan / tewu / xuye）：
      bash k8s/deploy-game-proxy.sh <target>

    Hublog（额外带匿名分享页的 --skip-auth-route）：
      bash k8s/deploy-hublog-proxy.sh

    在线实例以集群为准：  kubectl -n oauth get deploy | grep oauth2-proxy
EOS
}

case "${1:-}" in
    --deploy)
        pull_and_push_all
        deploy_k8s
        deploy_proxy_guidance

        sleep 10
        kubectl get pods -n oauth ${K}

        echo ""
        echo "============================================"
        echo "  Casdoor 基础服务已部署，镜像已推送到私有 registry。"
        echo ""
        echo "  注意：本命令**不部署** oauth2-proxy 实例（见上方指引），"
        echo "        在线实例请以集群为准：kubectl -n oauth get deploy | grep oauth2-proxy"
        echo ""
        echo "  下一步:"
        echo "    1. 访问 https://auth.panghuer.top 确认 Casdoor 版本与 OIDC 发现正常"
        echo "    2. 要改动某个代理，用 k8s/deploy-{agent,game,hublog}-proxy.sh"
        echo "    3. 客户端凭证走 Vault（vault/inventory/oauth-externalsecret.yaml），"
        echo "       不要用 k8s/secret.yaml 里的占位符"
        echo "============================================"
        ;;
    --deploy-proxy)
        deploy_proxy_guidance
        exit 1
        ;;
    --push|"")
        pull_and_push_all
        ;;
    --help)
        echo "用法: $0 [--push|--deploy|--deploy-proxy|--help]"
        echo ""
        echo "  (无参数)        拉取 oauth2-proxy + Casdoor 镜像并推送到私有 registry（默认）"
        echo "  --push          拉取 oauth2-proxy + Casdoor 镜像并推送到私有 registry"
        echo "  --deploy        拉取镜像 + 部署 Casdoor 基础服务（**不含** oauth2-proxy 实例）"
        echo "  --deploy-proxy  已不可用；只打印 oauth2-proxy 实例的正确部署方式并以 1 退出"
        echo ""
        echo "  组件:"
        echo "    oauth2-proxy : quay.io/oauth2-proxy/oauth2-proxy:${OAUTH_TAG}"
        echo "    Casdoor      : casbin/casdoor:${CASDOOR_TAG}"
        echo ""
        echo "  oauth2-proxy 实例按家族用 k8s/ 下的专用脚本部署，理由见 deploy_proxy_guidance()。"
        ;;
    *)
        echo "未知参数: ${1}" >&2
        echo "用法: $0 [--push|--deploy|--deploy-proxy|--help]" >&2
        echo "" >&2
        echo "  组件:" >&2
        echo "    oauth2-proxy : quay.io/oauth2-proxy/oauth2-proxy:${OAUTH_TAG}" >&2
        echo "    Casdoor      : casbin/casdoor:${CASDOOR_TAG}" >&2
        exit 1
        ;;
esac
