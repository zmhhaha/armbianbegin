#!/usr/bin/env bash
set -euo pipefail

: "${BASE_URL:=https://openspec.panghuer.top}"
: "${CASDOOR_JWT:?Set CASDOOR_JWT to a Casdoor access token}"

curl --fail --silent --show-error "${BASE_URL%/}/healthz"
printf '\n'
curl --fail --silent --show-error "${BASE_URL%/}/readyz"
printf '\n'
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${CASDOOR_JWT}" \
  -H 'Accept: application/json' \
  "${BASE_URL%/}/v1/projects"
printf '\n'
