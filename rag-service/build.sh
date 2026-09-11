#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${REGISTRY}/rag-service:latest"

docker build --platform linux/arm64 -t "${IMAGE}" "${SCRIPT_DIR}"
if [[ "${1:-}" == "--push" ]]; then
  docker push "${IMAGE}"
fi
