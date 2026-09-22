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
# kubelet 每节点的 Pod 上限。默认是 110，而 orangepi5-max-server1 承载了全集群
# 大部分工作负载，2026-09-22 实测被打满（25 个 Pod Pending，调度器报
# "Too many pods"）。本集群的服务都很小，200 是安全的。
# 由 debian_begin.sh 写入各节点的 /var/lib/kubelet/config.yaml —— 不写的话，
# 重建节点会悄悄回到 110。
export KUBELET_MAX_PODS="200"

# 控制面节点的内存保底。kubeadm 默认给 master 打 control-plane:NoSchedule
# 污点，业务 Pod 全落到工作节点上；本集群已于 2026-09-22 摘掉该污点，让同规格
# 16 GiB 的 master 分担 orangepi5-max-server1 的压力（当时 132/200 个 Pod）。
# 摘掉之后控制面就只剩 system-node-critical 优先级这一层保护，所以必须再给
# kubelet 留出预留：systemReserved/kubeReserved 会从节点 allocatable 里扣掉，
# 调度器看不到整块内存，工作负载挤不掉 etcd / kube-apiserver。
# 由 debian_begin.sh 写入 master 的 /var/lib/kubelet/config.yaml。
export KUBELET_SYSTEM_RESERVED="3Gi"   # 操作系统 + 系统守护进程
export KUBELET_KUBE_RESERVED="2Gi"     # kubelet + 容器运行时

# ---- 基础服务端口 ----
export COREDNS_HOSTS_FILE="/etc/hosts"  # CoreDNS hosts 插件用的 hosts 文件
