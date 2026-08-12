#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../cluster_config.sh" ]]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/../cluster_config.sh"
fi

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
ES_VERSION="${ES_VERSION:-8.15.3}"
SOURCE_IMAGE="docker.elastic.co/elasticsearch/elasticsearch:${ES_VERSION}"
TARGET_IMAGE="${REGISTRY}/elasticsearch:${ES_VERSION}"

usage() {
    cat <<'EOF'
用法:
  bash build.sh --push
  bash build.sh --help

环境变量:
  ES_VERSION=8.15.3
  REGISTRY=arm-cluster-master:5000
EOF
}

case "${1:-}" in
    --push)
        echo "Pulling ARM64 image: ${SOURCE_IMAGE}"
        docker pull --platform linux/arm64 "${SOURCE_IMAGE}"
        docker tag "${SOURCE_IMAGE}" "${TARGET_IMAGE}"
        echo "Pushing image: ${TARGET_IMAGE}"
        docker push "${TARGET_IMAGE}"
        echo "Image ready: ${TARGET_IMAGE}"
        ;;
    --help|-h)
        usage
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
