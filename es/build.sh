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
TARGET_IMAGE="${REGISTRY}/elasticsearch:${ES_VERSION}-ik-v1"

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
        : "${IK_SHA256:?Set IK_SHA256 to the independently verified plugin archive SHA256}"
        docker build --platform linux/arm64 --build-arg ES_VERSION="${ES_VERSION}" \
            --build-arg IK_SHA256="${IK_SHA256}" -t "${TARGET_IMAGE}" "${SCRIPT_DIR}"
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
