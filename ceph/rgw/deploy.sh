#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RGW_SPEC="${SCRIPT_DIR}/cephadm-rgw.yaml"
INGRESS_TEMPLATE="${SCRIPT_DIR}/cephadm-ingress.yaml.tpl"
TUNNEL_ROUTE_TEMPLATE="${SCRIPT_DIR}/k8s/tunnel-route.yaml.tpl"

RGW_SERVICE="rgw.s3"
INGRESS_SERVICE="ingress.rgw.s3"
RGW_PORT="7481"
INGRESS_PORT="7480"
EXPECTED_RGW="${EXPECTED_RGW:-2}"
EXPECTED_INGRESS="${EXPECTED_INGRESS:-2}"
RGW_VIRTUAL_IP="${RGW_VIRTUAL_IP:-}"
KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"
ALLOW_HEALTH_WARN="${ALLOW_HEALTH_WARN:-0}"
EXPOSE_PUBLIC="${EXPOSE_PUBLIC:-0}"
REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
HAPROXY_IMAGE="${HAPROXY_IMAGE:-${REGISTRY}/ceph-haproxy:2.8-arm64}"
KEEPALIVED_IMAGE="${KEEPALIVED_IMAGE:-${REGISTRY}/ceph-keepalived:2.2.8-arm64}"

log() {
    printf '[rgw] %s\n' "$*"
}

fail() {
    printf '[rgw] ERROR: %s\n' "$*" >&2
    exit 1
}

wait_for_daemon_type() {
    local service_name="$1"
    local daemon_type="$2"
    local expected="$3"
    local deadline=$((SECONDS + 600))
    local running

    while (( SECONDS < deadline )); do
        running="$({ ceph orch ps --service_name "${service_name}" --format json 2>/dev/null || printf '[]'; } | python3 -c '
import json
import sys

daemon_type = sys.argv[1]
daemons = json.load(sys.stdin)
print(sum(
    1 for daemon in daemons
    if daemon.get("daemon_type") == daemon_type
    and daemon.get("status_desc") == "running"
))
' "${daemon_type}")"
        log "${service_name}/${daemon_type}: running=${running}, expected=${expected}"
        if [[ "${running}" == "${expected}" ]]; then
            return 0
        fi
        sleep 5
    done

    ceph orch ps --service_name "${service_name}" --refresh || true
    fail "${service_name}/${daemon_type} 在 600 秒内未全部就绪"
}

for command_name in ceph curl ping python3; do
    command -v "${command_name}" >/dev/null 2>&1 || fail "缺少命令: ${command_name}"
done

[[ -f "${RGW_SPEC}" ]] || fail "找不到 ${RGW_SPEC}"
[[ -f "${INGRESS_TEMPLATE}" ]] || fail "找不到 ${INGRESS_TEMPLATE}"
[[ -n "${RGW_VIRTUAL_IP}" ]] || fail \
    "请设置 RGW_VIRTUAL_IP=<192.168.137.0/24 中未占用的地址>/24"

if ! vip_address="$(python3 - "${RGW_VIRTUAL_IP}" <<'PY'
import ipaddress
import sys

try:
    interface = ipaddress.ip_interface(sys.argv[1])
except ValueError as error:
    raise SystemExit(f"无效的 RGW_VIRTUAL_IP: {error}")

service_network = ipaddress.ip_network("192.168.137.0/24")
if interface.network != service_network:
    raise SystemExit(f"RGW_VIRTUAL_IP 必须位于 {service_network} 并使用 /24")
if interface.ip == ipaddress.ip_address("192.168.137.101"):
    raise SystemExit("192.168.137.101 是主节点固定地址，不能作为 Keepalived 漂移 VIP")
print(interface.ip)
PY
)"; then
    fail "RGW_VIRTUAL_IP 校验失败"
fi

managed_vip="$(ceph orch ls --export --format json 2>/dev/null | python3 -c '
import json
import sys

services = json.load(sys.stdin)
service = next(
    (item for item in services if item.get("service_name") == "ingress.rgw.s3"),
    {},
)
print(service.get("spec", {}).get("virtual_ip", ""))
' || true)"

if ping -c 1 -W 1 "${vip_address}" >/dev/null 2>&1 \
    && [[ "${managed_vip}" != "${RGW_VIRTUAL_IP}" ]]; then
    fail "VIP ${vip_address} 已有设备响应，且不是现有 ingress.rgw.s3 的受管 VIP"
fi

health="$(ceph health 2>/dev/null || true)"
[[ -n "${health}" ]] || fail "无法连接 Ceph 集群"
log "Ceph health: ${health}"

if [[ "${health}" == HEALTH_ERR* ]]; then
    fail "Ceph 处于 HEALTH_ERR，停止部署"
fi

if [[ "${health}" == HEALTH_WARN* && "${ALLOW_HEALTH_WARN}" != "1" ]]; then
    fail "Ceph 处于 HEALTH_WARN；修复告警，或确认风险后使用 ALLOW_HEALTH_WARN=1"
fi

online_hosts="$(ceph orch host ls --format json | python3 -c '
import json
import sys

hosts = json.load(sys.stdin)
print(sum(1 for host in hosts if str(host.get("status", "")).lower() != "offline"))
')"
required_hosts="${EXPECTED_RGW}"
if (( EXPECTED_INGRESS > required_hosts )); then
    required_hosts="${EXPECTED_INGRESS}"
fi
(( online_hosts >= required_hosts )) || fail \
    "在线 cephadm 主机只有 ${online_hosts} 台，至少需要 ${required_hosts} 台"

configured_haproxy="$(ceph config get mgr mgr/cephadm/container_image_haproxy 2>/dev/null || true)"
configured_keepalived="$(ceph config get mgr mgr/cephadm/container_image_keepalived 2>/dev/null || true)"
if [[ "${configured_haproxy}" != "${HAPROXY_IMAGE}" \
    || "${configured_keepalived}" != "${KEEPALIVED_IMAGE}" ]]; then
    fail "cephadm 尚未配置 ARM64 ingress 镜像。依次执行 build-ingress-images.sh --push 和 configure-ingress-images.sh，然后重新运行 deploy.sh"
fi

ingress_spec="$(mktemp)"
trap 'rm -f "${ingress_spec}"' EXIT
sed "s|__RGW_VIRTUAL_IP__|${RGW_VIRTUAL_IP}|g" \
    "${INGRESS_TEMPLATE}" >"${ingress_spec}"

log "应用动态 RGW ServiceSpec"
ceph orch apply -i "${RGW_SPEC}"
log "等待 ${EXPECTED_RGW} 个 RGW daemon"
wait_for_daemon_type "${RGW_SERVICE}" rgw "${EXPECTED_RGW}"

log "应用 Ceph ingress ServiceSpec（VIP ${RGW_VIRTUAL_IP}）"
ceph orch apply -i "${ingress_spec}"
log "等待 ${EXPECTED_INGRESS} 个 HAProxy 和 Keepalived 实例"
wait_for_daemon_type "${INGRESS_SERVICE}" haproxy "${EXPECTED_INGRESS}"
wait_for_daemon_type "${INGRESS_SERVICE}" keepalived "${EXPECTED_INGRESS}"

ready=0
for _ in {1..24}; do
    code="$(curl --silent --show-error --output /dev/null --connect-timeout 5 \
        --write-out '%{http_code}' "http://${vip_address}:${INGRESS_PORT}/" || true)"
    if [[ "${code}" == "200" || "${code}" == "403" ]]; then
        log "Ceph ingress VIP ready (HTTP ${code})"
        ready=1
        break
    fi
    sleep 5
done
(( ready == 1 )) || fail "VIP ${vip_address}:${INGRESS_PORT} 在 120 秒内未就绪"

if [[ "${EXPOSE_PUBLIC}" == "1" ]]; then
    command -v kubectl >/dev/null 2>&1 || fail "缺少命令: kubectl"
    [[ -f "${KUBECONFIG}" ]] || fail "找不到 kubeconfig: ${KUBECONFIG}"
    [[ -f "${TUNNEL_ROUTE_TEMPLATE}" ]] || fail "找不到 ${TUNNEL_ROUTE_TEMPLATE}"
    tunnel_route="$(mktemp)"
    trap 'rm -f "${ingress_spec}" "${tunnel_route}"' EXIT
    sed "s|__S3_BACKEND__|${vip_address}:${INGRESS_PORT}|g" \
        "${TUNNEL_ROUTE_TEMPLATE}" >"${tunnel_route}"
    log "创建 Cloudflare Tunnel 公网路由"
    kubectl --kubeconfig="${KUBECONFIG}" apply -f "${tunnel_route}"
fi

log "部署完成"
log "Ceph ingress endpoint: http://${vip_address}:${INGRESS_PORT}"
log "请将内部 DNS 的 S3 记录指向 ${vip_address}，应用不要使用 daemon 节点地址"
