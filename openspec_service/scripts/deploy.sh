#!/usr/bin/env bash
set -Eeuo pipefail

# Deploy OpenSpec resources and provision its dedicated PostgreSQL credentials.
# The database password is kept in Vault and is reused on subsequent runs when
# possible. Gitea credentials in the same Vault path are preserved with kv patch.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd -- "${SERVICE_DIR}/.." && pwd)"
if [[ -f "${REPO_ROOT}/cluster_config.sh" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/cluster_config.sh"
fi

VAULT_MANIFEST="${REPO_ROOT}/vault/inventory/openspec-service-externalsecret.yaml"
CLOUDFLARE_MANIFEST="${REPO_ROOT}/cloudflare-tunnel/operator/openspec-service-route.yaml"
KUBECTL="${KUBECTL:-kubectl}"
KUBECONFIG="${KUBECONFIG:-/etc/kubernetes/super-admin.conf}"
export KUBECONFIG

NAMESPACE="openspec"
DB_NAME="${OPENSPEC_DB_NAME:-openspec_service}"
DB_USER="${OPENSPEC_DB_USER:-openspec_service}"
POSTGRES_ADMIN_USER="${POSTGRES_ADMIN_USER:-appuser}"
POSTGRES_ADMIN_DB="${POSTGRES_ADMIN_DB:-appdb}"

WAIT=0
CORE_ONLY=0
SKIP_VAULT=0
SKIP_CLOUDFLARE=0
WAIT_TIMEOUT="${WAIT_TIMEOUT:-180s}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: ./scripts/deploy.sh [options]

Provision the OpenSpec PostgreSQL role/database, synchronize Vault, and apply
OpenSpec Kubernetes resources from any working directory.

Options:
  --core-only       Apply only openspec_service/k8s/
  --skip-vault      Skip PostgreSQL/Vault provisioning and ExternalSecret
  --skip-cloudflare Do not apply the Cloudflare TunnelRoute
  --wait            Wait for the Deployment to become available
  -h, --help        Show this help

Environment overrides:
  KUBECTL, KUBECONFIG, WAIT_TIMEOUT, OPENSPEC_DB_NAME, OPENSPEC_DB_USER,
  OPENSPEC_DB_PASSWORD, POSTGRES_ADMIN_USER, POSTGRES_ADMIN_DB
EOF
}

while (($# > 0)); do
  case "$1" in
    --core-only) CORE_ONLY=1 ;;
    --skip-vault) SKIP_VAULT=1 ;;
    --skip-cloudflare) SKIP_CLOUDFLARE=1 ;;
    --wait) WAIT=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

command -v "${KUBECTL}" >/dev/null 2>&1 || fail "${KUBECTL} command not found"
[[ -f "${VAULT_MANIFEST}" ]] || fail "missing ${VAULT_MANIFEST}"
[[ -f "${CLOUDFLARE_MANIFEST}" ]] || fail "missing ${CLOUDFLARE_MANIFEST}"
[[ "${DB_NAME}" =~ ^[a-z_][a-z0-9_]*$ ]] || fail "OPENSPEC_DB_NAME must contain lowercase letters, digits, and underscores"
[[ "${DB_USER}" =~ ^[a-z_][a-z0-9_]*$ ]] || fail "OPENSPEC_DB_USER must contain lowercase letters, digits, and underscores"

echo "=== Preparing OpenSpec namespace ==="
"${KUBECTL}" create namespace "${NAMESPACE}" --dry-run=client -o yaml | \
  "${KUBECTL}" apply -f -

if ((CORE_ONLY == 0 && SKIP_VAULT == 0)); then
  for command_name in openssl python3 base64; do
    command -v "${command_name}" >/dev/null 2>&1 || fail "${command_name} command not found"
  done
  [[ -f "${KUBECONFIG}" ]] || fail "kubeconfig not found: ${KUBECONFIG}"

  echo "=== Checking PostgreSQL and Vault prerequisites ==="
  "${KUBECTL}" version --request-timeout=10s >/dev/null || fail "cannot connect to Kubernetes API"
  "${KUBECTL}" -n data get pod postgres-0 >/dev/null || fail "PostgreSQL pod postgres-0 not found"
  "${KUBECTL}" -n vault get pod vault-0 >/dev/null || fail "Vault pod vault-0 not found"
  "${KUBECTL}" get clustersecretstore vault-backend >/dev/null || fail "ClusterSecretStore vault-backend not found"

  vault_status_json="$("${KUBECTL}" -n vault exec vault-0 -- vault status -format=json 2>/dev/null || true)"
  [[ -n "${vault_status_json}" ]] || fail "cannot read Vault status"
  vault_sealed="$(printf '%s' "${vault_status_json}" | python3 -c 'import json,sys; print(str(json.load(sys.stdin)["sealed"]).lower())')" \
    || fail "cannot parse Vault status"
  [[ "${vault_sealed}" == "false" ]] || fail "Vault is sealed; unseal it before deployment"
  "${KUBECTL}" -n vault exec vault-0 -- vault token lookup >/dev/null 2>&1 || \
    fail "Vault CLI is not logged in"
  "${KUBECTL}" -n vault exec vault-0 -- vault kv get secret/openspec/service >/dev/null 2>&1 || \
    fail "Vault path secret/openspec/service is missing; add Gitea credentials first"

  postgres_admin_password="$("${KUBECTL}" -n data get secret postgres-secret -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d)"
  [[ -n "${postgres_admin_password}" ]] || fail "postgres-secret has no POSTGRES_PASSWORD"

  # Reuse the password already recorded in Vault to avoid rotating it on every
  # deploy. Set OPENSPEC_DB_PASSWORD explicitly to rotate it intentionally.
  existing_database_url="$("${KUBECTL}" -n vault exec vault-0 -- vault kv get -field=database_url secret/openspec/service 2>/dev/null || true)"
  if [[ -z "${OPENSPEC_DB_PASSWORD:-}" && -n "${existing_database_url}" ]]; then
    if ! OPENSPEC_DB_PASSWORD="$(printf '%s' "${existing_database_url}" | python3 -c 'import sys; from urllib.parse import unquote,urlsplit; print(unquote(urlsplit(sys.stdin.read().strip()).password or ""))' 2>/dev/null)"; then
      OPENSPEC_DB_PASSWORD=""
    fi
  fi
  OPENSPEC_DB_PASSWORD="${OPENSPEC_DB_PASSWORD:-$(openssl rand -hex 24)}"
  [[ -n "${OPENSPEC_DB_PASSWORD}" ]] || fail "cannot generate OpenSpec database password"

  run_admin_psql() {
    "${KUBECTL}" -n data exec -i postgres-0 -- \
      env PGPASSWORD="${postgres_admin_password}" \
      psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 \
      -U "${POSTGRES_ADMIN_USER}" -d "${POSTGRES_ADMIN_DB}" "$@"
  }

  echo "=== Provisioning OpenSpec PostgreSQL role and database ==="
  printf '%s\n' \
    "SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', '${DB_USER}', :'openspec_password') WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_USER}') \\gexec" \
    "ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD :'openspec_password';" \
    "SELECT format('CREATE DATABASE %I OWNER %I', '${DB_NAME}', '${DB_USER}') WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}') \\gexec" \
    | run_admin_psql --set="openspec_password=${OPENSPEC_DB_PASSWORD}"

  "${KUBECTL}" -n data exec postgres-0 -- \
    env PGPASSWORD="${postgres_admin_password}" \
    psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 \
    -U "${POSTGRES_ADMIN_USER}" -d "${DB_NAME}" \
    -c "ALTER SCHEMA public OWNER TO ${DB_USER}; GRANT ALL ON SCHEMA public TO ${DB_USER};" >/dev/null

  urlencode() {
    printf '%s' "$1" | python3 -c 'import sys; from urllib.parse import quote; print(quote(sys.stdin.read(), safe=""))'
  }

  database_password_encoded="$(urlencode "${OPENSPEC_DB_PASSWORD}")"
  database_url="postgresql://${DB_USER}:${database_password_encoded}@postgres.data.svc.cluster.local:5432/${DB_NAME}"

  echo "=== Synchronizing Vault and ExternalSecret ==="
  # Use patch because GITEA_TOKEN and GITEA_USERNAME live at this same path.
  "${KUBECTL}" -n vault exec vault-0 -- vault kv patch secret/openspec/service \
    "database_url=${database_url}" >/dev/null
  "${KUBECTL}" apply -f "${VAULT_MANIFEST}"
  "${KUBECTL}" -n "${NAMESPACE}" annotate externalsecret openspec-service-secrets \
    "force-sync=$(date +%s)" --overwrite >/dev/null
  "${KUBECTL}" -n "${NAMESPACE}" wait --for=condition=Ready \
    externalsecret/openspec-service-secrets --timeout=120s || {
    "${KUBECTL}" -n "${NAMESPACE}" describe externalsecret openspec-service-secrets >&2 || true
    fail "openspec-service-secrets ExternalSecret is not ready"
  }

  echo "=== Applying OpenSpec core resources ==="
  "${KUBECTL}" apply -k "${SERVICE_DIR}/k8s"
  echo "=== Restarting OpenSpec to load synchronized credentials ==="
  "${KUBECTL}" -n "${NAMESPACE}" rollout restart deployment/openspec-service
fi

if ((CORE_ONLY == 1 || SKIP_VAULT == 1)); then
  echo "=== Applying OpenSpec core resources ==="
  "${KUBECTL}" apply -k "${SERVICE_DIR}/k8s"
fi

if ((CORE_ONLY == 0 && SKIP_CLOUDFLARE == 0)); then
  echo "=== Applying Cloudflare TunnelRoute ==="
  "${KUBECTL}" apply -f "${CLOUDFLARE_MANIFEST}"
fi

if ((WAIT)); then
  echo "=== Waiting for openspec-service Deployment (${WAIT_TIMEOUT}) ==="
  "${KUBECTL}" -n "${NAMESPACE}" wait --for=condition=available \
    deployment/openspec-service --timeout="${WAIT_TIMEOUT}"
fi

echo "=== OpenSpec deployment status ==="
"${KUBECTL}" -n "${NAMESPACE}" get pods,pvc,svc
if ((CORE_ONLY == 0 && SKIP_VAULT == 0)); then
  "${KUBECTL}" -n "${NAMESPACE}" get externalsecret openspec-service-secrets || \
    echo "WARNING: could not query openspec-service-secrets ExternalSecret"
fi
if ((CORE_ONLY == 0 && SKIP_CLOUDFLARE == 0)); then
  echo "=== Cloudflare route status ==="
  "${KUBECTL}" -n default get tunnelroute openspec-service
fi
