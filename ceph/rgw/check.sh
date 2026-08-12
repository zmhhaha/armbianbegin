#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="rgw.s3"
RGW_PORT="7480"
RGW_ENDPOINTS=("192.168.137.211" "192.168.137.201")
KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"

printf '%s\n' '=== Ceph health ==='
ceph status

printf '%s\n' '=== cephadm hosts ==='
ceph orch host ls

printf '%s\n' '=== RGW service ==='
ceph orch ls --service_name "${SERVICE_NAME}" || true
ceph orch ps --service_name "${SERVICE_NAME}" --refresh || true

printf '%s\n' '=== Direct endpoints ==='
for endpoint in "${RGW_ENDPOINTS[@]}"; do
    code="$(curl --silent --show-error --output /dev/null --connect-timeout 5 \
        --write-out '%{http_code}' "http://${endpoint}:${RGW_PORT}/" || true)"
    printf '%s:%s HTTP %s\n' "${endpoint}" "${RGW_PORT}" "${code:-000}"
done

if [[ -f "${KUBECONFIG}" ]]; then
    printf '%s\n' '=== Kubernetes service ==='
    kubectl --kubeconfig="${KUBECONFIG}" get service ceph-rgw -n data -o wide || true
    kubectl --kubeconfig="${KUBECONFIG}" get endpointslice ceph-rgw -n data -o wide || true
fi
