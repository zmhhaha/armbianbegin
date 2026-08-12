#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
HAPROXY_TAG="${HAPROXY_TAG:-2.8-arm64}"
KEEPALIVED_TAG="${KEEPALIVED_TAG:-2.2.8-arm64}"
HAPROXY_IMAGE="${REGISTRY}/ceph-haproxy:${HAPROXY_TAG}"
KEEPALIVED_IMAGE="${REGISTRY}/ceph-keepalived:${KEEPALIVED_TAG}"

usage() {
    cat <<EOF
用法:
  bash build-ingress-images.sh --push

输出镜像:
  ${HAPROXY_IMAGE}
  ${KEEPALIVED_IMAGE}
EOF
}

[[ "${1:-}" == "--push" ]] || {
    usage >&2
    exit 2
}

command -v docker >/dev/null 2>&1 || {
    printf 'ERROR: 缺少命令: docker\n' >&2
    exit 1
}

printf '[rgw-images] Building %s\n' "${HAPROXY_IMAGE}"
docker build --platform linux/arm64 \
    --tag "${HAPROXY_IMAGE}" \
    "${SCRIPT_DIR}/images/haproxy"

printf '[rgw-images] Building %s\n' "${KEEPALIVED_IMAGE}"
docker build --platform linux/arm64 \
    --tag "${KEEPALIVED_IMAGE}" \
    "${SCRIPT_DIR}/images/keepalived"

docker run --rm --entrypoint haproxy "${HAPROXY_IMAGE}" -vv \
    | grep -q 'prometheus-exporter' || {
        printf 'ERROR: HAProxy 镜像缺少 Prometheus exporter 支持\n' >&2
        exit 1
    }
docker run --rm --entrypoint stat "${HAPROXY_IMAGE}" /var/lib >/dev/null
docker run --rm --entrypoint /usr/sbin/keepalived \
    "${KEEPALIVED_IMAGE}" --version >/dev/null 2>&1
docker run --rm --entrypoint /usr/bin/curl \
    "${KEEPALIVED_IMAGE}" --version >/dev/null
docker run --rm --entrypoint stat "${KEEPALIVED_IMAGE}" /var/lib >/dev/null

for image in "${HAPROXY_IMAGE}" "${KEEPALIVED_IMAGE}"; do
    architecture="$(docker image inspect "${image}" --format '{{.Architecture}}')"
    [[ "${architecture}" == "arm64" ]] || {
        printf 'ERROR: 镜像 %s 的架构是 %s，不是 arm64\n' "${image}" "${architecture}" >&2
        exit 1
    }
    docker push "${image}"
done

printf '%s\n' '[rgw-images] ARM64 ingress images pushed.'
