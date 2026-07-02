#!/bin/bash
# =============================================================
#  集群统一配置文件
#  所有脚本通过 source 此文件获取集群信息
#  迁移集群时只需改这一个文件
# =============================================================

# ---- Master 节点 ----
export MASTER_HOSTNAME="arm-cluster-master"
export MASTER_IP="192.168.137.101"

# ---- 私有 Registry ----
export REGISTRY_PORT="5000"
# registry 地址（供 docker tag/push 使用）
export REGISTRY="${MASTER_HOSTNAME}:${REGISTRY_PORT}"

# ---- 工作节点 ----
# 低资源节点（会打 taint）
export LOW_RESOURCE_NODES=(
    "nanopct4-server1"
    "nanopct4-server2"
    "nanopct4-server3"
)
# 所有服务器节点（SSH 批量操作时使用）
export ALL_NODES=(
    "${MASTER_HOSTNAME}"
    "nanopct4-server1"
    "nanopct4-server2"
    "nanopct4-server3"
    "orangepi5-max-server1"
    "orangepi5-plus-server1"
)

# ---- 网络 ----
export NETWORK_GATEWAY="192.168.137.1"
export NETWORK_SUBNET="192.168.137.0/24"
export NETWORK_DNS="8.8.8.8,8.8.4.4"

# ---- K8s ----
export K8S_VERSION="v1.31.2"
export POD_CIDR="10.244.0.0/16"
export SERVICE_CIDR="10.96.0.0/12"
export K8S_API_PORT="6443"

# ---- 基础服务端口 ----
export COREDNS_HOSTS_FILE="/etc/hosts"  # CoreDNS hosts 插件用的 hosts 文件
