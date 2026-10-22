#!/usr/bin/env bash
# Update only Gitea's VPS virtual host; existing Nginx/FRP must be installed.
set -Eeuo pipefail
umask 022

[[ $EUID -eq 0 ]] || { echo 'Run with sudo bash vps/deploy-gitea-nginx.sh' >&2; exit 1; }
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASE_DOMAIN="${BASE_DOMAIN:-panghuer.top}"
HTTPS_PORT="${HTTPS_PORT:-443}"
[[ "$BASE_DOMAIN" =~ ^[a-zA-Z0-9.-]+$ && "$HTTPS_PORT" =~ ^[0-9]+$ ]] || exit 1
command -v envsubst >/dev/null
nginx -t

install -d -m 0755 /var/backups
backup="$(mktemp -d /var/backups/gitea-nginx-XXXXXXXX)"
chmod 700 "$backup"
site=/etc/nginx/sites-available/gitea.conf
enabled=/etc/nginx/sites-enabled/gitea.conf
for entry in site enabled; do
    path="${!entry}"
    [[ ! -d "$path" ]] || { printf 'Refusing directory: %s\n' "$path" >&2; exit 1; }
    if [[ -e "$path" || -L "$path" ]]; then
        cp -a -- "$path" "$backup/$entry"
    fi
done
printf 'Backup: %s\n' "$backup"

changed=0
finish() {
    result=$?
    trap - EXIT
    if [[ $result -ne 0 && $changed -eq 1 ]]; then
        echo 'Deployment failed; restoring the previous Gitea configuration.' >&2
        for entry in site enabled; do
            path="${!entry}"
            rm -f -- "$path"
            if [[ -e "$backup/$entry" || -L "$backup/$entry" ]]; then
                cp -a -- "$backup/$entry" "$path"
            fi
        done
        if nginx -t; then systemctl reload nginx; fi
    fi
    exit "$result"
}
trap finish EXIT

BASE_DOMAIN="$BASE_DOMAIN" HTTPS_PORT="$HTTPS_PORT" envsubst '${BASE_DOMAIN} ${HTTPS_PORT}' \
    < "$SCRIPT_DIR/nginx/gitea.conf.template" | tr -d '\357\273\277\r' > "$backup/rendered.conf"
changed=1
install -m 0644 "$backup/rendered.conf" "$site"
ln -sfn "$site" "$enabled"
nginx -t
systemctl reload nginx
systemctl is-active --quiet nginx
echo 'Gitea virtual host deployed; Nginx reloaded.'
