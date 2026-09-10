#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../cluster_config.sh" ]]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/../cluster_config.sh"
fi

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/embedding-service:latest"

# 国内源（可在环境变量中覆盖）
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
MODEL_BASE_URL="${MODEL_BASE_URL:-https://hf-mirror.com/Qdrant/bge-small-zh-v1.5/resolve/main}"

usage() {
    cat <<'EOF'
用法:
  bash build.sh            # 构建镜像
  bash build.sh --push     # 构建并推送
  bash build.sh --help

可选环境变量（一般不需要设置）:
  REGISTRY=arm-cluster-master:5000
  PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
  MODEL_BASE_URL=https://hf-mirror.com/Qdrant/bge-small-zh-v1.5/resolve/main
  MODEL_SHA256=<onnx sha256，可选，用于固定校验>
  TOKENIZER_SHA256=<tokenizer sha256，可选，用于固定校验>
EOF
}

case "${1:-}" in
    --help|-h)
        usage
        exit 0
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
    --build-arg "MODEL_BASE_URL=${MODEL_BASE_URL}" \
    --build-arg "MODEL_SHA256=${MODEL_SHA256:-}" \
    --build-arg "TOKENIZER_SHA256=${TOKENIZER_SHA256:-}" \
    -t "${IMAGE}" "${SCRIPT_DIR}"

if [[ "${1:-}" == "--push" ]]; then
    echo "Pushing image: ${IMAGE}"
    docker push "${IMAGE}"
fi

echo "Image ready: ${IMAGE}"
