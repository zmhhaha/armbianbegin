#!/usr/bin/env bash
set -Eeuo pipefail

KEEPALIVED_DEBUG="${KEEPALIVED_DEBUG:-false}"
KEEPALIVED_CONF="${KEEPALIVED_CONF:-/etc/keepalived/keepalived.conf}"
KEEPALIVED_VAR_RUN="${KEEPALIVED_VAR_RUN:-/var/run/keepalived}"

if [[ "${KEEPALIVED_DEBUG,,}" == "true" ]]; then
    default_command="/usr/sbin/keepalived -n -l -D -f ${KEEPALIVED_CONF}"
else
    default_command="/usr/sbin/keepalived -n -l -f ${KEEPALIVED_CONF}"
fi

KEEPALIVED_CMD="${KEEPALIVED_CMD:-${default_command}}"
rm -rf "${KEEPALIVED_VAR_RUN}"

exec ${KEEPALIVED_CMD}
