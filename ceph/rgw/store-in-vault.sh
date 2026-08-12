#!/usr/bin/env bash
set -Eeuo pipefail

CREDENTIALS_FILE="${1:?用法: store-in-vault.sh <credentials-file> [vault-path]}"
VAULT_PATH="${2:-secret/panghu-chat/s3}"

for command_name in vault python3; do
    command -v "${command_name}" >/dev/null 2>&1 || {
        printf 'ERROR: 缺少命令: %s\n' "${command_name}" >&2
        exit 1
    }
done

[[ -f "${CREDENTIALS_FILE}" ]] || {
    printf 'ERROR: 凭据文件不存在: %s\n' "${CREDENTIALS_FILE}" >&2
    exit 1
}

[[ -n "${VAULT_ADDR:-}" ]] || {
    printf 'ERROR: 未设置 VAULT_ADDR\n' >&2
    exit 1
}

vault token lookup >/dev/null

set -a
# shellcheck disable=SC1090
source "${CREDENTIALS_FILE}"
set +a

required=(
    S3_ACCESS_KEY_ID
    S3_SECRET_ACCESS_KEY
    S3_INTERNAL_ENDPOINT
    S3_PUBLIC_ENDPOINT
    S3_BUCKET
    S3_REGION
    S3_FORCE_PATH_STYLE
)
for variable_name in "${required[@]}"; do
    [[ -n "${!variable_name:-}" ]] || {
        printf 'ERROR: 凭据文件缺少 %s\n' "${variable_name}" >&2
        exit 1
    }
done

payload_file="$(mktemp)"
chmod 0600 "${payload_file}"
trap 'rm -f "${payload_file}"' EXIT

python3 - <<'PY' >"${payload_file}"
import json
import os

keys = (
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "S3_INTERNAL_ENDPOINT",
    "S3_PUBLIC_ENDPOINT",
    "S3_BUCKET",
    "S3_REGION",
    "S3_FORCE_PATH_STYLE",
)
print(json.dumps({key: os.environ[key] for key in keys}))
PY

vault kv put "${VAULT_PATH}" "@${payload_file}" >/dev/null

printf 'S3 credentials stored at Vault path %s\n' "${VAULT_PATH}"
