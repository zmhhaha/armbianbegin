#!/bin/bash
# =============================================================
#  SSH 密钥分发 — 将所有节点的公钥分发到集群
# =============================================================
script_dir="$(cd "$(dirname "$0")" && pwd)"
[ -f "${script_dir}/cluster_config.sh" ] && source "${script_dir}/cluster_config.sh"

ssh-keygen -t rsa -b 2048 -f ~/.ssh/id_rsa -N ""

# 使用集群配置中的节点列表
for node in "${ALL_NODES[@]}"; do
    ssh-copy-id -o StrictHostKeyChecking=no "${node}"
done

# 清除旧 known_hosts（可选）
# for node in "${ALL_NODES[@]}"; do
#     ssh-keygen -f "/root/.ssh/known_hosts" -R "${node}"
# done
