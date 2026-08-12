#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CEPH_SPEC="${SCRIPT_DIR}/cephadm-rgw.yaml"
K8S_SERVICE="${SCRIPT_DIR}/k8s/service.yaml"
TUNNEL_ROUTE="${SCRIPT_DIR}/k8s/tunnel-route.yaml"

SERVICE_NAME="rgw.s3"
RGW_PORT="7480"
EXPECTED_DAEMONS="2"
RGW_HOSTS=("orangepi5-max-server1" "nanopct4-server1")
RGW_ENDPOINTS=("192.168.137.211" "192.168.137.201")
KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"
ALLOW_HEALTH_WARN="${ALLOW_HEALTH_WARN:-0}"
EXPOSE_PUBLIC="${EXPOSE_PUBLIC:-0}"

log() {
    printf '[rgw] %s\n' "$*"
}

fail() {
    printf '[rgw] ERROR: %s\n' "$*" >&2
    exit 1
}

for command_name in ceph kubectl curl python3; do
    command -v "${command_name}" >/dev/null 2>&1 || fail "缺少命令: ${command_name}"
done

[[ -f "${CEPH_SPEC}" ]] || fail "找不到 ${CEPH_SPEC}"
[[ -f "${K8S_SERVICE}" ]] || fail "找不到 ${K8S_SERVICE}"
[[ -f "${KUBECONFIG}" ]] || fail "找不到 kubeconfig: ${KUBECONFIG}"

health="$(ceph health 2>/dev/null || true)"
[[ -n "${health}" ]] || fail "无法连接 Ceph 集群"
log "Ceph health: ${health}"

if [[ "${health}" == HEALTH_ERR* ]]; then
    fail "Ceph 处于 HEALTH_ERR，停止部署"
fi

if [[ "${health}" == HEALTH_WARN* && "${ALLOW_HEALTH_WARN}" != "1" ]]; then
    fail "Ceph 处于 HEALTH_WARN；修复告警，或确认风险后使用 ALLOW_HEALTH_WARN=1"
fi

host_table="$(ceph orch host ls)"
for host_name in "${RGW_HOSTS[@]}"; do
    host_row="$(awk -v host="${host_name}" '$1 == host { print }' <<<"${host_table}")"
    [[ -n "${host_row}" ]] || fail "cephadm 中不存在主机: ${host_name}"
    [[ "${host_row}" != *Offline* ]] || fail "cephadm 主机处于 Offline: ${host_name}"
done

log "应用 cephadm ServiceSpec: ${CEPH_SPEC}"
ceph orch apply -i "${CEPH_SPEC}"

log "等待 ${EXPECTED_DAEMONS} 个 RGW daemon 进入 running"
deadline=$((SECONDS + 300))
ready=0
while (( SECONDS < deadline )); do
    status="$({ ceph orch ls --format json 2>/dev/null || printf '[]'; } | python3 -c '
import json
import sys

service_name = sys.argv[1]
services = json.load(sys.stdin)
service = next((item for item in services if item.get("service_name") == service_name), {})
state = service.get("status", {})
print("{} {}".format(state.get("running", 0), state.get("size", 0)))
' "${SERVICE_NAME}")"
    read -r running size <<<"${status}"
    log "daemon: running=${running}, size=${size}"
    if [[ "${running}" == "${EXPECTED_DAEMONS}" && "${size}" == "${EXPECTED_DAEMONS}" ]]; then
        ready=1
        break
    fi
    sleep 5
done

if (( ready != 1 )); then
    ceph orch ps --service_name "${SERVICE_NAME}" || true
    fail "RGW 在 300 秒内未全部就绪"
fi

failed_endpoints=0
for endpoint in "${RGW_ENDPOINTS[@]}"; do
    code="$(curl --silent --show-error --output /dev/null --connect-timeout 5 \
        --write-out '%{http_code}' "http://${endpoint}:${RGW_PORT}/" || true)"
    if [[ "${code}" == "200" || "${code}" == "403" ]]; then
        log "RGW endpoint ${endpoint}:${RGW_PORT} ready (HTTP ${code})"
    else
        printf '[rgw] WARN: RGW endpoint %s:%s returned HTTP %s\n' \
            "${endpoint}" "${RGW_PORT}" "${code:-000}" >&2
        failed_endpoints=$((failed_endpoints + 1))
    fi
done

(( failed_endpoints == 0 )) || fail "至少一个 RGW endpoint 未通过健康检查"

log "创建 Kubernetes 内部 Service"
kubectl --kubeconfig="${KUBECONFIG}" apply -f "${K8S_SERVICE}"

if [[ "${EXPOSE_PUBLIC}" == "1" ]]; then
    [[ -f "${TUNNEL_ROUTE}" ]] || fail "找不到 ${TUNNEL_ROUTE}"
    log "创建 Cloudflare Tunnel 公网路由"
    kubectl --kubeconfig="${KUBECONFIG}" apply -f "${TUNNEL_ROUTE}"
fi

log "部署完成"
log "K8s endpoint: http://ceph-rgw.data.svc.cluster.local:${RGW_PORT}"
if [[ "${EXPOSE_PUBLIC}" == "1" ]]; then
    log "Public endpoint: https://s3.panghuer.top"
fi
