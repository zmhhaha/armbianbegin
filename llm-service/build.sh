#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../cluster_config.sh" ]]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/../cluster_config.sh"
fi

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/llm-service:latest"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

usage() {
    cat <<'EOF'
用法:
  bash build.sh            # 构建并推送镜像（默认）
  bash build.sh --no-push  # 仅构建镜像，不推送
  bash build.sh --help

可选环境变量:
  REGISTRY=arm-cluster-master:5000
  PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
EOF
}

# 默认构建并推送；--no-push 仅构建（--push 为兼容保留，等价于默认）
PUSH=true
case "${1:-}" in
    --help|-h)
        usage
        exit 0
        ;;
    --no-push)
        PUSH=false
        ;;
    --push|"")
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

docker build --platform linux/arm64 \
    --build-arg "PIP_INDEX_URL=${PIP_INDEX_URL}" \
    -t "${IMAGE}" "${SCRIPT_DIR}"

if [[ "${PUSH}" == true ]]; then
    echo "Pushing image: ${IMAGE}"
    docker push "${IMAGE}"
fi

echo "Image ready: ${IMAGE}"
