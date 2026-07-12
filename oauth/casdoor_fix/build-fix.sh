#!/bin/bash
# ============================================================
#  Casdoor 支付宝 OAuth 修复 — 完整编译 & 部署脚本
#
#  功能:
#    1. 从源码编译修复版 Casdoor 二进制（静态链接 arm64）
#    2. 基于 casdoor:latest 制作修复镜像
#    3. 推送到私有仓库并部署到 K8s
#
#  用法:
#    bash build-fix.sh               # 编译 + 推送 + 部署
#    bash build-fix.sh --build-only  # 仅编译二进制
#    bash build-fix.sh --deploy      # 仅部署（使用已有镜像）
#
#  前提:
#    - 已配置好 SSH key 可 clone GitHub
#    - Docker 可用，能访问 arm-cluster-master:5000
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CASDOOR_SRC="${CASDOOR_SRC:-/tmp/casdoor}"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
K="${KUBECONFIG:---kubeconfig=/etc/kubernetes/super-admin.conf}"

# ============================================================
#  编译修复版 Casdoor 二进制（静态链接）
# ============================================================
do_build() {
    echo "=== 准备 Casdoor 源码 ==="
    if [ ! -d "${CASDOOR_SRC}/.git" ]; then
        rm -rf "${CASDOOR_SRC}"
        git clone git@github.com:casdoor/casdoor.git "${CASDOOR_SRC}"
    fi

    cd "${CASDOOR_SRC}"

    # 重置并拉取最新
    git checkout -- idp/alipay.go 2>/dev/null || true
    git checkout master
    git pull

    echo "=== 手动打补丁（仅修改 rsaSignWithRSA256，不改 formatPrivateKey）==="
    # 定位到第 309 行附近，把 if err != nil { return "", err } 替换为回退逻辑
    # 精确匹配目标代码块
    sed -i '/privateKeyRSA, err := x509.ParsePKCS8PrivateKey(block.Bytes)/{
        N
        s/if err != nil {\n\t\treturn "", err/if err != nil {\n\t\tprivateKeyRSA, err = x509.ParsePKCS1PrivateKey(block.Bytes)\n\t\tif err != nil {\n\t\t\treturn "", fmt.Errorf("failed to parse private key (tried PKCS8 and PKCS1): %w", err)\n\t\t}\n\t}\n\tif privateKeyRSA == nil {
    }' idp/alipay.go

    echo "=== 编译静态链接的 arm64 二进制 ==="
    docker run --rm -v "${CASDOOR_SRC}:/src" -w /src golang:1.25 \
      /bin/sh -c "CGO_ENABLED=0 GOOS=linux GOARCH=arm64 GOPROXY=https://mirrors.aliyun.com/goproxy go build -ldflags='-s -w' -o /src/casdoor-fix ."

    # 验证
    file "${CASDOOR_SRC}/casdoor-fix"
    echo "  ✅ 编译完成: ${CASDOOR_SRC}/casdoor-fix"
}

# ============================================================
#  制作修复版镜像并部署
# ============================================================
do_image() {
    if [ ! -f "${CASDOOR_SRC}/casdoor-fix" ]; then
        echo "  ❌ 未找到 casdoor-fix 二进制，请先执行 build-fix.sh（不带参数）"
        exit 1
    fi

    echo "=== 创建基于 casdoor:latest 的修复镜像 ==="
    docker rm -f casdoor-tmp 2>/dev/null || true
    docker pull "${REGISTRY}/casdoor:latest"
    docker run -d --name casdoor-tmp "${REGISTRY}/casdoor:latest" sh -c "sleep 9999"

    echo "=== 复制修复版二进制 ==="
    docker cp "${CASDOOR_SRC}/casdoor-fix" casdoor-tmp:/server
    docker exec casdoor-tmp chmod +x /server

    # 验证镜像里的二进制
    docker exec casdoor-tmp file /server

    echo "=== 提交镜像 ==="
    docker commit casdoor-tmp "${REGISTRY}/casdoor:fix-alipay"
    docker rm -f casdoor-tmp
    docker push "${REGISTRY}/casdoor:fix-alipay"
    echo "  ✅ 镜像已推送: ${REGISTRY}/casdoor:fix-alipay"
}

# ============================================================
#  部署到 K8s
# ============================================================
do_deploy() {
    echo "=== 部署到 K8s ==="
    kubectl set image deploy/casdoor -n oauth "casdoor=${REGISTRY}/casdoor:fix-alipay" $K
    kubectl rollout status deploy/casdoor -n oauth --watch $K
    echo ""
    echo "  ✅ Casdoor 已更新！"
    echo "  检查日志: kubectl logs -n oauth deploy/casdoor --tail=10"
}

# ============================================================
#  main
# ============================================================
case "${1:-}" in
    --build-only)
        do_build
        ;;
    --deploy)
        do_deploy
        ;;
    --image-only)
        do_image
        ;;
    *)
        do_build
        do_image
        do_deploy
        ;;
esac
