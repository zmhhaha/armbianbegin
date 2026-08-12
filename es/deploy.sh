#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../cluster_config.sh" ]]; then
    # shellcheck disable=SC1091
    source "${SCRIPT_DIR}/../cluster_config.sh"
fi

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
ES_VERSION="${ES_VERSION:-8.15.3}"
ES_IMAGE="${ES_IMAGE:-${REGISTRY}/elasticsearch:${ES_VERSION}}"
KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"
K="--kubeconfig=${KUBECONFIG}"

K8S_DIR="${SCRIPT_DIR}/k8s"

fail() {
    printf '[elasticsearch] ERROR: %s\n' "$*" >&2
    exit 1
}

command -v kubectl >/dev/null 2>&1 || fail "缺少 kubectl"
[[ -f "${KUBECONFIG}" ]] || fail "找不到 kubeconfig: ${KUBECONFIG}"

printf '%s\n' '=== Applying Vault ExternalSecret ==='
kubectl "${K}" apply -f "${K8S_DIR}/external-secret.yaml"

printf '%s\n' '=== Waiting for Elasticsearch password ==='
if ! kubectl "${K}" wait --for=condition=Ready \
    externalsecret/elasticsearch-secret -n data --timeout=90s; then
    echo "ExternalSecret 未就绪。请确认 Vault secret/elasticsearch/app 包含 ELASTIC_PASSWORD。" >&2
    exit 1
fi

printf '%s\n' '=== Applying Elasticsearch resources ==='
kubectl "${K}" apply -f "${K8S_DIR}/configmap.yaml"
kubectl "${K}" apply -f "${K8S_DIR}/service.yaml"
kubectl "${K}" apply -f "${K8S_DIR}/statefulset.yaml"

printf '=== Setting image: %s ===\n' "${ES_IMAGE}"
kubectl "${K}" set image statefulset/elasticsearch \
    elasticsearch="${ES_IMAGE}" -n data

printf '%s\n' '=== Waiting for Elasticsearch ==='
kubectl "${K}" rollout status statefulset/elasticsearch -n data --timeout=600s

printf '%s\n' '=== Elasticsearch status ==='
kubectl "${K}" get pod,svc,pvc -n data -l app.kubernetes.io/name=elasticsearch -o wide

printf '%s\n' 'Deployment complete.'
printf '%s\n' 'Internal endpoint: http://elasticsearch.data.svc.cluster.local:9200'
