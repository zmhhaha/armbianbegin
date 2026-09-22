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

# kubelet 内存预留。它设的是 **cgroup 硬顶**，不是调度信号 —— 本集群的 Pod 几乎
# 都不写 memory requests（master 上 12 个 Pod 合计 0.23 GiB；三台 NanoPC 上
# calico-node 只有 cpu、kube-proxy 和 CSI 全是空的）。requests 全为 0 时，调度器
# 的适配检查 sum(requests) <= allocatable 恒真、打分还认为这些节点最空，所以把
# allocatable 压到多小都挡不住调度。真正的效果是：allocatable 决定
# kubepods.slice/memory.max，于是给"所有 Pod 加起来"设了内核层面的硬顶。
# 详见 resource_scheduler/apply-kubelet-reservations.sh 的头部注释。
#
# 两类节点目的不同：
#   master —— 2026-09-22 摘掉了 kubeadm 默认的 control-plane 污点，它会跑业务 Pod，
#             留 5 GiB 给控制面+宿主机。控制面静态 Pod 是 system-node-critical，
#             cgroup 内最后被 OOM killer 选中；但**磁盘 I/O 没有保护**（etcd 每次写
#             都 fsync），所以别把数据库/Ceph OSD 放 master 上。
#   NanoPC —— 安全网：宿主机进程（ceph-osd/mysqld/gitea）实测已占约 2.6 GiB，
#             留 2.7 GiB 让顶落在 ~1.06 GiB，超了先杀 Pod，而不是像 2026-09-21 那样
#             杀 mysqld（Casdoor 的库在那台上，连带 40 个 oauth2-proxy 全部 CrashLoop）。
# 由 debian_begin.sh 写入各节点的 /var/lib/kubelet/config.yaml。
export MASTER_SYSTEM_RESERVED="3Gi"     # master: 操作系统 + 系统守护进程
export MASTER_KUBE_RESERVED="2Gi"       # master: kubelet + 容器运行时
export NANOPC_SYSTEM_RESERVED="2.2Gi"   # NanoPC: 宿主机进程实测占 ~2.6 GiB
export NANOPC_KUBE_RESERVED="0.5Gi"     # NanoPC: kubelet + 容器运行时

# ---- 基础服务端口 ----
export COREDNS_HOSTS_FILE="/etc/hosts"  # CoreDNS hosts 插件用的 hosts 文件
