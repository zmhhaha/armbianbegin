#!/usr/bin/env bash
set -Eeuo pipefail

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
HAPROXY_IMAGE="${HAPROXY_IMAGE:-${REGISTRY}/ceph-haproxy:2.8-arm64}"
KEEPALIVED_IMAGE="${KEEPALIVED_IMAGE:-${REGISTRY}/ceph-keepalived:2.2.8-arm64}"

log() {
    printf '[rgw-images] %s\n' "$*"
}

fail() {
    printf '[rgw-images] ERROR: %s\n' "$*" >&2
    exit 1
}

for command_name in ceph docker python3; do
    command -v "${command_name}" >/dev/null 2>&1 || fail "缺少命令: ${command_name}"
done

for image in "${HAPROXY_IMAGE}" "${KEEPALIVED_IMAGE}"; do
    docker pull "${image}" >/dev/null
    architecture="$(docker image inspect "${image}" --format '{{.Architecture}}')"
    [[ "${architecture}" == "arm64" ]] || fail \
        "镜像 ${image} 的架构是 ${architecture}，不是 arm64"
done

current_haproxy="$(ceph config get mgr mgr/cephadm/container_image_haproxy 2>/dev/null || true)"
current_keepalived="$(ceph config get mgr mgr/cephadm/container_image_keepalived 2>/dev/null || true)"

if [[ "${current_haproxy}" == "${HAPROXY_IMAGE}" \
    && "${current_keepalived}" == "${KEEPALIVED_IMAGE}" ]]; then
    log "cephadm 已配置 ARM64 ingress 镜像"
    exit 0
fi

standby_count="$(ceph mgr dump --format json | python3 -c '
import json
import sys

document = json.load(sys.stdin)
print(len(document.get("standbys", [])))
')"
(( standby_count >= 1 )) || fail \
    "镜像配置需要 mgr failover 才能生效，但当前没有健康的 standby mgr"

active_mgr="$(ceph mgr dump --format json | python3 -c '
import json
import sys
print(json.load(sys.stdin).get("active_name", ""))
')"
[[ -n "${active_mgr}" ]] || fail "无法取得 active mgr 名称"

log "配置 HAProxy 镜像: ${HAPROXY_IMAGE}"
ceph config set mgr mgr/cephadm/container_image_haproxy "${HAPROXY_IMAGE}"
log "配置 Keepalived 镜像: ${KEEPALIVED_IMAGE}"
ceph config set mgr mgr/cephadm/container_image_keepalived "${KEEPALIVED_IMAGE}"

log "执行 mgr failover，使非运行时镜像选项生效（当前 ${active_mgr}）"
ceph mgr fail "${active_mgr}"

deadline=$((SECONDS + 120))
while (( SECONDS < deadline )); do
    read -r available next_active < <(ceph mgr dump --format json | python3 -c '
import json
import sys
document = json.load(sys.stdin)
print(str(document.get("available", False)).lower(), document.get("active_name", ""))
')
    if [[ "${available}" == "true" && -n "${next_active}" \
        && "${next_active}" != "${active_mgr}" ]]; then
        log "mgr failover 完成，新 active mgr: ${next_active}"
        exit 0
    fi
    sleep 2
done

fail "mgr 在 120 秒内未完成 failover；请执行 ceph -s 检查状态"
