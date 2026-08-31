#!/usr/bin/env bash
set -euo pipefail

# Deploy OpenSpec core resources and its separately managed integrations.
# This script does not create Vault data or credentials; ExternalSecret reads
# the already prepared secret/data/openspec/service path.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SERVICE_DIR}/.." && pwd)"

VAULT_MANIFEST="${REPO_ROOT}/vault/inventory/openspec-service-externalsecret.yaml"
CLOUDFLARE_MANIFEST="${REPO_ROOT}/cloudflare-tunnel/operator/openspec-service-route.yaml"
KUBECTL="${KUBECTL:-kubectl}"
WAIT=0
CORE_ONLY=0
SKIP_VAULT=0
SKIP_CLOUDFLARE=0
WAIT_TIMEOUT="${WAIT_TIMEOUT:-180s}"

usage() {
  cat <<'EOF'
Usage: ./scripts/deploy.sh [options]

Apply OpenSpec Kubernetes resources from any working directory.

Options:
  --core-only       Apply only openspec_service/k8s/
  --skip-vault      Do not apply the Vault ExternalSecret
  --skip-cloudflare Do not apply the Cloudflare TunnelRoute
  --wait            Wait for the Deployment to become available
  -h, --help        Show this help

Environment overrides: KUBECTL, WAIT_TIMEOUT
EOF
}

while (($# > 0)); do
  case "$1" in
    --core-only)
      CORE_ONLY=1
      ;;
    --skip-vault)
      SKIP_VAULT=1
      ;;
    --skip-cloudflare)
      SKIP_CLOUDFLARE=1
      ;;
    --wait)
      WAIT=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

command -v "${KUBECTL}" >/dev/null 2>&1 || { echo "ERROR: ${KUBECTL} command not found" >&2; exit 1; }
[[ -f "${VAULT_MANIFEST}" ]] || { echo "ERROR: missing ${VAULT_MANIFEST}" >&2; exit 1; }
[[ -f "${CLOUDFLARE_MANIFEST}" ]] || { echo "ERROR: missing ${CLOUDFLARE_MANIFEST}" >&2; exit 1; }

echo "=== Applying OpenSpec core resources ==="
"${KUBECTL}" apply -k "${SERVICE_DIR}/k8s"

if ((CORE_ONLY == 0 && SKIP_VAULT == 0)); then
  echo "=== Applying Vault ExternalSecret ==="
  "${KUBECTL}" apply -f "${VAULT_MANIFEST}"
fi

if ((CORE_ONLY == 0 && SKIP_CLOUDFLARE == 0)); then
  echo "=== Applying Cloudflare TunnelRoute ==="
  "${KUBECTL}" apply -f "${CLOUDFLARE_MANIFEST}"
fi

if ((WAIT)); then
  echo "=== Waiting for openspec-service Deployment (${WAIT_TIMEOUT}) ==="
  "${KUBECTL}" -n openspec wait --for=condition=available \
    deployment/openspec-service --timeout="${WAIT_TIMEOUT}"
fi

echo "=== OpenSpec deployment status ==="
"${KUBECTL}" -n openspec get pods,pvc,svc
if ((CORE_ONLY == 0 && SKIP_VAULT == 0)); then
  "${KUBECTL}" -n openspec get externalsecret openspec-service-secrets || \
    echo "WARNING: could not query openspec-service-secrets ExternalSecret"
fi
if ((CORE_ONLY == 0 && SKIP_CLOUDFLARE == 0)); then
  echo "=== Cloudflare route status ==="
  "${KUBECTL}" -n default get tunnelroute openspec-service
fi
