#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/armbianbegin-mcp-server:latest"

# 默认构建并推送；--no-push 仅构建（--push 为兼容保留，等价于默认）
PUSH=true
if [[ "${1:-}" == "--no-push" ]]; then
    PUSH=false
fi

docker build -t "${IMAGE}" "${SCRIPT_DIR}"
if [[ "${PUSH}" == true ]]; then
    docker push "${IMAGE}"
fi
