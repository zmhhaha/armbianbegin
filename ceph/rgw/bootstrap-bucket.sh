#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CREDENTIALS_FILE="${1:?用法: bootstrap-bucket.sh <credentials-file>}"
CORS_ORIGIN="${CORS_ORIGIN:-https://hubo.panghuer.top}"

command -v aws >/dev/null 2>&1 || {
    printf 'ERROR: 缺少 AWS CLI 命令: aws\n' >&2
    exit 1
}

[[ -f "${CREDENTIALS_FILE}" ]] || {
    printf 'ERROR: 凭据文件不存在: %s\n' "${CREDENTIALS_FILE}" >&2
    exit 1
}

set -a
# shellcheck disable=SC1090
source "${CREDENTIALS_FILE}"
set +a

S3_BUCKET="${S3_BUCKET:-hubo-media}"
S3_REGION="${S3_REGION:-us-east-1}"
[[ -n "${S3_ADMIN_ENDPOINT:-}" ]] || {
    printf 'ERROR: 凭据文件缺少 S3_ADMIN_ENDPOINT\n' >&2
    exit 1
}

export AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY}"
export AWS_DEFAULT_REGION="${S3_REGION}"
export AWS_EC2_METADATA_DISABLED=true

if aws --endpoint-url "${S3_ADMIN_ENDPOINT}" s3api head-bucket --bucket "${S3_BUCKET}" >/dev/null 2>&1; then
    printf 'Bucket already exists: %s\n' "${S3_BUCKET}"
else
    aws --endpoint-url "${S3_ADMIN_ENDPOINT}" s3api create-bucket --bucket "${S3_BUCKET}" >/dev/null
    printf 'Bucket created: %s\n' "${S3_BUCKET}"
fi

cors_file="$(mktemp)"
lifecycle_file="$(mktemp)"
trap 'rm -f "${cors_file}" "${lifecycle_file}"' EXIT

cat >"${cors_file}" <<JSON
{
  "CORSRules": [
    {
      "AllowedOrigins": ["${CORS_ORIGIN}"],
      "AllowedMethods": ["GET", "PUT", "POST", "HEAD"],
      "AllowedHeaders": ["*"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3600
    }
  ]
}
JSON

cat >"${lifecycle_file}" <<'JSON'
{
  "Rules": [
    {
      "ID": "abort-incomplete-multipart-uploads",
      "Status": "Enabled",
      "Filter": {"Prefix": ""},
      "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7}
    }
  ]
}
JSON

aws --endpoint-url "${S3_ADMIN_ENDPOINT}" s3api put-bucket-cors \
    --bucket "${S3_BUCKET}" \
    --cors-configuration "file://${cors_file}"

aws --endpoint-url "${S3_ADMIN_ENDPOINT}" s3api put-bucket-lifecycle-configuration \
    --bucket "${S3_BUCKET}" \
    --lifecycle-configuration "file://${lifecycle_file}"

printf 'Bucket %s configured as private with CORS origin %s\n' "${S3_BUCKET}" "${CORS_ORIGIN}"
