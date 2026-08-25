#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
install -D -m 0755 "${script_dir}/k8s-node-memory-guard.sh" /usr/local/sbin/k8s-node-memory-guard
install -D -m 0644 "${script_dir}/systemd/k8s-node-memory-guard.service" /etc/systemd/system/k8s-node-memory-guard.service
install -D -m 0644 "${script_dir}/systemd/k8s-node-memory-guard.timer" /etc/systemd/system/k8s-node-memory-guard.timer

systemctl daemon-reload
systemctl enable --now k8s-node-memory-guard.timer
systemctl start k8s-node-memory-guard.service
systemctl --no-pager status k8s-node-memory-guard.timer
