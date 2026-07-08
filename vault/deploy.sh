#!/bin/bash
# ============================================================
#  Vault + External Secrets Operator — 一键部署脚本
#
#  用法:
#    ./deploy.sh               # 仅部署 Vault + ESO
#    ./deploy.sh --init        # 部署 + 初始化 Vault（首次运行）
#    ./deploy.sh --seed        # 部署 + 初始化 + 种子密钥
#    ./deploy.sh --unseal      # 仅执行解封操作（重启后需要）
#
#  前提条件:
#    - Helm 已安装（通常在 debian_begin.sh 中已装）
#    - kubectl 可访问集群
#    - 私有镜像仓库 arm-cluster-master:5000 可用
#
#  流程:
#    1. 拉取 Vault + ESO 镜像到本地并推送到私有 registry
#    2. 部署 Vault (Helm)
#    3. 部署 External Secrets Operator (Helm)
#    4. 创建命名空间 + PVC + ClusterSecretStore
#    5. （可选）初始化 Vault（K8s auth、policy、role）
#    6. （可选）种子密钥写入
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"
[ -f "../cluster_config.sh" ] && source "../cluster_config.sh"

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
K="${KUBECONFIG:---kubeconfig=/etc/kubernetes/super-admin.conf}"

VAULT_NS="vault"
ESO_NS="external-secrets"
VAULT_VERSION="${VAULT_VERSION:-1.18.0}"
ESO_VERSION="${ESO_VERSION:-0.11.0}"

# ============================================================
#  1. 拉取并推送镜像到私有仓库
# ============================================================
pull_and_push() {
    local official="$1" local_img="$2" name="$3"
    echo "=== [${name}] Pulling ${official} ==="
    docker pull "${official}"
    echo "=== [${name}] Pushing to ${local_img} ==="
    docker tag "${official}" "${local_img}"
    docker push "${local_img}"
}

pull_and_push_all() {
    echo ""
    echo "============================================"
    echo "  拉取镜像并推送到私有仓库"
    echo "============================================"

    # Vault 官方镜像已支持 linux/arm64
    pull_and_push "hashicorp/vault:${VAULT_VERSION}" \
        "${REGISTRY}/hashicorp/vault:${VAULT_VERSION}" "vault"
    docker tag "${REGISTRY}/hashicorp/vault:${VAULT_VERSION}" "${REGISTRY}/hashicorp/vault:latest"
    docker push "${REGISTRY}/hashicorp/vault:latest"

    echo ""
    echo "  镜像推送完成:"
    echo "    ${REGISTRY}/hashicorp/vault:${VAULT_VERSION}"
}

# ============================================================
#  2. 部署 Vault + ESO
# ============================================================
deploy_vault() {
    echo ""
    echo "============================================"
    echo "  部署 Vault（Helm）"
    echo "============================================"

    # 给 Vault images 打上私有仓库标签
    # 实际镜像名在 values 里没有暴露 image 完整路径用于替换
    # 我们通过 docker tag 方式替换: hashicorp/vault → arm-cluster-master:5000/hashicorp/vault
    # 注意: vault-values.yaml 中 image.repository 仍使用官方名
    # 需要在部署前替换镜像地址
    echo "=== 创建命名空间 ${VAULT_NS} ==="
    kubectl create namespace "${VAULT_NS}" --dry-run=client -o yaml $K | kubectl apply $K -f -

    echo "=== 创建 PVC ==="
    kubectl apply $K -f k8s/pvc.yaml

    echo "=== 安装/升级 Vault Helm Chart ==="
    helm repo add hashicorp https://helm.releases.hashicorp.com 2>/dev/null || true
    helm repo update

    # 临时替换镜像地址为私有仓库
    sed "s|repository: hashicorp/vault|repository: ${REGISTRY}/hashicorp/vault|g" \
        helm-values/vault-values.yaml | \
    helm upgrade --install vault hashicorp/vault \
        --namespace "${VAULT_NS}" \
        --values /dev/stdin \
        --set server.image.tag="${VAULT_VERSION}" \
        --wait \
        --timeout 5m

    echo ""
    echo "=== Vault 部署完成 ==="
}

deploy_eso() {
    echo ""
    echo "============================================"
    echo "  部署 External Secrets Operator（Helm）"
    echo "============================================"

    echo "=== 创建命名空间 ${ESO_NS} ==="
    kubectl create namespace "${ESO_NS}" --dry-run=client -o yaml $K | kubectl apply $K -f -

    echo "=== 安装/升级 ESO Helm Chart ==="
    helm repo add external-secrets https://charts.external-secrets.io 2>/dev/null || true
    helm repo update

    helm upgrade --install external-secrets external-secrets/external-secrets \
        --namespace "${ESO_NS}" \
        --values helm-values/eso-values.yaml \
        --wait \
        --timeout 3m

    # 如果 GitHub 网络不通导致 CRD 安装不完整，可以后续手动修复:
    # kubectl apply -f https://raw.githubusercontent.com/external-secrets/external-secrets/v2.7.0/deploy/crds/bundle.yaml --server-side

    echo ""
    echo "=== ESO 部署完成 ==="
}

deploy_k8s_manifests() {
    echo ""
    echo "============================================"
    echo "  创建 ClusterSecretStore"
    echo "============================================"

    # 注意: 必须等到 Vault 和 ESO 都就绪后再创建
    # 先创建命名空间（已由 helm 创建）
    # 创建 ClusterSecretStore（集群级别，无 namespace）
    kubectl apply $K -f k8s/cluster-secret-store.yaml

    echo "=== ClusterSecretStore 'vault-backend' 已创建 ==="
}

# ============================================================
#  3. 验证部署
# ============================================================
verify() {
    echo ""
    echo "============================================"
    echo "  验证部署状态"
    echo "============================================"

    echo "=== Vault Pods ==="
    kubectl get pods -n "${VAULT_NS}" $K

    echo ""
    echo "=== ESO Pods ==="
    kubectl get pods -n "${ESO_NS}" $K

    echo ""
    echo "=== ClusterSecretStore ==="
    kubectl get clustersecretstore $K

    echo ""
    echo "=== Vault Service ==="
    kubectl get svc -n "${VAULT_NS}" $K

    echo ""
    echo "============================================"
    echo "  部署完成！下一步操作："
    echo ""
    echo "  1. 初始化 Vault："
    echo "     bash scripts/init-vault.sh"
    echo ""
    echo "  2. 访问 Vault UI："
    echo "     kubectl port-forward -n vault svc/vault 8200:8200"
    echo "     然后浏览器打开 http://localhost:8200"
    echo ""
    echo "  3. 写入种子密钥："
    echo "     bash scripts/seed-secrets.sh"
    echo ""
    echo "  4. 查看迁移指南："
    echo "     cat rules.migrate.md"
    echo "============================================"
}

# ============================================================
#  main
# ============================================================
case "${1:-}" in
    --init)
        pull_and_push_all
        deploy_vault
        deploy_eso
        deploy_k8s_manifests
        echo ""
        echo "=== 执行 Vault 初始化 ==="
        bash scripts/init-vault.sh
        verify
        ;;
    --seed)
        pull_and_push_all
        deploy_vault
        deploy_eso
        deploy_k8s_manifests
        echo ""
        echo "=== 执行 Vault 初始化 ==="
        bash scripts/init-vault.sh
        echo ""
        echo "=== 写入种子密钥 ==="
        bash scripts/seed-secrets.sh
        verify
        ;;
    --unseal)
        bash scripts/unseal.sh
        ;;
    *)
        # 仅部署或手动指定子命令
        if [ $# -eq 0 ]; then
            pull_and_push_all
            deploy_vault
            deploy_eso
            deploy_k8s_manifests
            verify
        else
            echo "用法: $0 [--init|--seed|--unseal]"
            echo ""
            echo "  (无参数)  仅部署 Vault + ESO"
            echo "  --init    部署 + 初始化 Vault（首次运行）"
            echo "  --seed    部署 + 初始化 + 种子密钥写入"
            echo "  --unseal  仅解封 Vault（重启后需要）"
        fi
        ;;
esac
