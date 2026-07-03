#!/bin/bash
# ============================================================
#  Ceph 集群清理脚本 — 完全销毁集群
#  用法: bash ceph_cleanup.sh
#  ⚠️ 这会删除所有数据，不可逆！
# ============================================================

script_dir="$(cd "$(dirname "$0")" && pwd)"
[ -f "${script_dir}/../cluster_config.sh" ] && source "${script_dir}/../cluster_config.sh"

echo "============================================"
echo "  WARNING: 即将销毁整个 Ceph 集群！"
echo "  包括所有 OSD 数据和配置"
echo "============================================"
read -p "确认？输入 yes 继续: " confirm
if [ "$confirm" != "yes" ]; then
    echo "已取消"
    exit 0
fi

# ---- 1. 逐节点驱逐 ----
hostnames="nanopct4-server1 nanopct4-server2 nanopct4-server3"
IFS=' ' read -r -a hostnamearray <<< "$hostnames"
for i in "${hostnamearray[@]}"; do
    echo ">>> Draining ${i} ..."
    ceph orch host drain ${i} 2>/dev/null || true
    ceph orch osd rm status 2>/dev/null || true
    ceph orch ps ${i} 2>/dev/null
    ceph orch host rm ${i} 2>/dev/null || true
done
echo ">>> Stopping ceph.target ..."
systemctl stop ceph.target 2>/dev/null || true

# ---- 2. 删除集群 ----
echo ">>> Removing cluster ..."
FSID=$(ceph fsid 2>/dev/null | tr -d '[:space:]')
if [ -n "$FSID" ]; then
    cephadm rm-cluster --fsid "$FSID" --force --zap-osds
fi

# 清理遗留 FSID（上次部署的旧集群）
cephadm rm-cluster --fsid 3f12b9e4-fce0-11ef-97b1-ca1173533d33 --force --zap-osds 2>/dev/null || true

# ---- 3. 清理系统文件 ----
rm -rf /etc/systemd/system/ceph-*.service
rm -rf /etc/systemd/system/ceph.target.wants
systemctl daemon-reload

# ---- 4. 清理 Docker 容器 ----
docker ps -a --filter name=ceph -q | xargs -r docker stop
docker ps -a --filter name=ceph -q | xargs -r docker rm

# ---- 5. 清理数据和配置 ----
rm -rf /etc/ceph
rm -rf /var/lib/ceph

# ---- 6. 清理 K8s CSI（如果部署过）----
echo ">>> Cleaning K8s CSI resources ..."
K="--kubeconfig=/etc/kubernetes/super-admin.conf"
cd /root/ceph-csi/deploy/cephfs/kubernetes 2>/dev/null && {
    kubectl delete $K -f csi-provisioner-rbac.yaml 2>/dev/null || true
    kubectl delete $K -f csi-nodeplugin-rbac.yaml 2>/dev/null || true
    kubectl delete $K -f csi-cephfsplugin-provisioner.yaml 2>/dev/null || true
    kubectl delete $K -f csi-cephfsplugin.yaml 2>/dev/null || true
    kubectl delete $K -f csidriver.yaml 2>/dev/null || true
    kubectl delete $K -f ../../rbd/kubernetes/csi-nodeplugin-rbac.yaml 2>/dev/null || true
    kubectl delete $K -f ../../rbd/kubernetes/csi-provisioner-rbac.yaml 2>/dev/null || true
    kubectl delete $K -f ../../rbd/kubernetes/csi-rbdplugin-provisioner.yaml 2>/dev/null || true
    kubectl delete $K -f ../../rbd/kubernetes/csi-rbdplugin.yaml 2>/dev/null || true
    kubectl delete $K -f ../../rbd/kubernetes/csidriver.yaml 2>/dev/null || true
}

echo ""
echo "============================================"
echo "  Ceph 集群已完全清理！"
echo "============================================"
