#!/usr/bin/env bash
set -Eeuo pipefail

RGW_UID="${1:-hubo}"
DISPLAY_NAME="${2:-虎博媒体服务}"
OUTPUT_FILE="${3:-${PWD}/${RGW_UID}-s3.env}"

S3_ADMIN_ENDPOINT="${S3_ADMIN_ENDPOINT:-http://192.168.137.211:7480}"
S3_INTERNAL_ENDPOINT="${S3_INTERNAL_ENDPOINT:-http://ceph-rgw.data.svc.cluster.local:7480}"
S3_PUBLIC_ENDPOINT="${S3_PUBLIC_ENDPOINT:-https://s3.panghuer.top}"
S3_BUCKET="${S3_BUCKET:-hubo-media}"
S3_REGION="${S3_REGION:-us-east-1}"

for command_name in radosgw-admin python3; do
    command -v "${command_name}" >/dev/null 2>&1 || {
        printf 'ERROR: 缺少命令: %s\n' "${command_name}" >&2
        exit 1
    }
done

if [[ -e "${OUTPUT_FILE}" && "${FORCE:-0}" != "1" ]]; then
    printf 'ERROR: 凭据文件已存在: %s；如确认覆盖，请设置 FORCE=1\n' "${OUTPUT_FILE}" >&2
    exit 1
fi

umask 077
user_json="$(mktemp)"
trap 'rm -f "${user_json}"' EXIT

if radosgw-admin user info --uid="${RGW_UID}" >"${user_json}" 2>/dev/null; then
    printf 'S3 user already exists: %s\n' "${RGW_UID}"
else
    printf 'Creating S3 user: %s\n' "${RGW_UID}"
    radosgw-admin user create \
        --uid="${RGW_UID}" \
        --display-name="${DISPLAY_NAME}" \
        --max-buckets=10 \
        --format=json >"${user_json}"
fi

key_summary="$(python3 - "${user_json}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    document = json.load(handle)
keys = document.get("keys") or []
if keys:
    print("1", keys[0].get("access_key", ""), keys[0].get("secret_key", ""))
else:
    print("0", "", "")
PY
)"
read -r key_count access_key secret_key <<<"${key_summary}"

if [[ "${key_count}" == "0" ]]; then
    radosgw-admin key create --uid="${RGW_UID}" --key-type=s3 --format=json >"${user_json}"
    key_summary="$(python3 - "${user_json}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    document = json.load(handle)
key = (document.get("keys") or [{}])[0]
print(key.get("access_key", ""), key.get("secret_key", ""))
PY
)"
    read -r access_key secret_key <<<"${key_summary}"
fi

[[ -n "${access_key}" ]] || { printf 'ERROR: 未取得 S3 Access Key\n' >&2; exit 1; }
[[ -n "${secret_key}" ]] || { printf 'ERROR: 未取得 S3 Secret Key\n' >&2; exit 1; }

{
    printf 'S3_ACCESS_KEY_ID=%q\n' "${access_key}"
    printf 'S3_SECRET_ACCESS_KEY=%q\n' "${secret_key}"
    printf 'S3_ADMIN_ENDPOINT=%q\n' "${S3_ADMIN_ENDPOINT}"
    printf 'S3_INTERNAL_ENDPOINT=%q\n' "${S3_INTERNAL_ENDPOINT}"
    printf 'S3_PUBLIC_ENDPOINT=%q\n' "${S3_PUBLIC_ENDPOINT}"
    printf 'S3_BUCKET=%q\n' "${S3_BUCKET}"
    printf 'S3_REGION=%q\n' "${S3_REGION}"
    printf 'S3_FORCE_PATH_STYLE=true\n'
} >"${OUTPUT_FILE}"

chmod 0600 "${OUTPUT_FILE}"
printf 'Credentials written to %s (mode 0600). Secret values were not printed.\n' "${OUTPUT_FILE}"
