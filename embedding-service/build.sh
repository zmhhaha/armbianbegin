#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
: "${MODEL_SHA256:?Set the independently verified model archive SHA256}"
docker build --platform linux/arm64 --build-arg MODEL_SHA256="${MODEL_SHA256}" \
  -t "${REGISTRY}/embedding-service:latest" "${SCRIPT_DIR}"
if [[ "${1:-}" == "--push" ]]; then
  docker push "${REGISTRY}/embedding-service:latest"
fi
