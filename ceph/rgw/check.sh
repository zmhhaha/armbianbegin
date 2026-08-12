#!/usr/bin/env bash
set -Eeuo pipefail

RGW_SERVICE="rgw.s3"
INGRESS_SERVICE="ingress.rgw.s3"
RGW_VIRTUAL_IP="${RGW_VIRTUAL_IP:-}"
INGRESS_PORT="7480"

printf '%s\n' '=== Ceph health ==='
ceph status

printf '%s\n' '=== cephadm hosts ==='
ceph orch host ls

printf '%s\n' '=== RGW service ==='
ceph orch ls --service_name "${RGW_SERVICE}" || true
ceph orch ps --service_name "${RGW_SERVICE}" --refresh || true

printf '%s\n' '=== Ceph ingress service ==='
ceph orch ls --service_name "${INGRESS_SERVICE}" || true
ceph orch ps --service_name "${INGRESS_SERVICE}" --refresh || true

if [[ -n "${RGW_VIRTUAL_IP}" ]]; then
    vip_address="${RGW_VIRTUAL_IP%/*}"
    printf '%s\n' '=== Ceph ingress VIP ==='
    code="$(curl --silent --show-error --output /dev/null --connect-timeout 5 \
        --write-out '%{http_code}' "http://${vip_address}:${INGRESS_PORT}/" || true)"
    printf '%s:%s HTTP %s\n' "${vip_address}" "${INGRESS_PORT}" "${code:-000}"
else
    printf '%s\n' 'RGW_VIRTUAL_IP 未设置，跳过 VIP HTTP 检查。'
fi
