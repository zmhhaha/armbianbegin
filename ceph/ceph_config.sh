#!/bin/bash
script_dir="$(cd "$(dirname "$0")" && pwd)"
[ -f "${script_dir}/../cluster_config.sh" ] && source "${script_dir}/../cluster_config.sh"

#rm -rf /etc/apt/keyrings/ceph.gpg
#curl -fsSL https://download.ceph.com/keys/release.asc |  gpg --dearmor -o /etc/apt/keyrings/ceph.gpg
#echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/ceph.gpg] https://download.ceph.com/debian-squid/ $(lsb_release -sc) main" | tee /etc/apt/sources.list.d/ceph.list
apt update
apt install -y ceph-mon ceph-osd ceph-mgr ceph-common ceph-volume

# Ceph 手动部署方式 已废弃
# mkdir -p /etc/ceph
# ceph-authtool --create-keyring /etc/ceph/ceph.mon.keyring --gen-key -n mon. --cap mon 'allow *'
# ceph-authtool --create-keyring /etc/ceph/ceph.client.admin.keyring --gen-key -n client.admin --cap mon 'allow *' --cap osd 'allow *' --cap mds 'allow *' --cap mgr 'allow *'
# chmod 644 /etc/ceph/ceph.client.admin.keyring
# monmaptool --create --add ceph-master 192.168.137.101 --fsid $(uuidgen) /tmp/monmap
# groupadd -g 2000 ceph && useradd -u 2000 -g ceph -m -s /bin/bash ceph
# sudo -u ceph ceph-mon --mkfs -i ceph-master --monmap /tmp/monmap --keyring /etc/ceph/ceph.mon.keyring
# systemctl start ceph-mon@ceph-master
# systemctl enable ceph-mon@ceph-master
# cat << EOF | tee /etc/ceph/ceph.conf
# [global]
# fsid = $(uuidgen)
# mon_initial_members = ceph-master, ceph-server1, ceph-server2
# mon_host = 192.168.137.201,192.168.137.202,192.168.137.203  # 替换为实际 IP
# public_network = 192.168.137.0/24
# cluster_network = 192.168.137.0/24
# auth_cluster_required = cephx
# auth_service_required = cephx
# auth_client_required = cephx
# osd_pool_default_size = 3
# EOF

apt install -y cephadm
cephadm add-repo --release squid
cephadm install
sed -i '/ceph-/d' ~/.ssh/authorized_keys

reboot

script_dir="$(cd "$(dirname "$0")" && pwd)"
[ -f "${script_dir}/../cluster_config.sh" ] && source "${script_dir}/../cluster_config.sh"
# master
cephadm bootstrap --mon-ip ${MASTER_IP} --cluster-network 192.168.137.0/24
ceph cephadm get-pub-key > ~/ceph.pub
ssh-copy-id -f -i ~/ceph.pub root@${MASTER_HOSTNAME}
ceph auth get client.bootstrap-osd -o /var/lib/ceph/bootstrap-osd/ceph.keyring
ceph orch host label add ${MASTER_HOSTNAME} ceph-master
#ceph orch host label rm ${MASTER_HOSTNAME} ceph-master

docker pull quay.io/ceph/ceph:v16
docker pull quay.io/ceph/ceph-grafana:8.3.5
docker pull quay.io/prometheus/prometheus:v2.33.4
docker pull quay.io/prometheus/node-exporter:v1.3.1
docker pull quay.io/prometheus/alertmanager:v0.23.0

docker tag quay.io/ceph/ceph:v16 ${REGISTRY}/quay.io/ceph/ceph:v16
docker tag quay.io/ceph/ceph-grafana:8.3.5 ${REGISTRY}/quay.io/ceph/ceph-grafana:8.3.5
docker tag quay.io/prometheus/prometheus:v2.33.4 ${REGISTRY}/quay.io/prometheus/prometheus:v2.33.4
docker tag quay.io/prometheus/node-exporter:v1.3.1 ${REGISTRY}/quay.io/prometheus/node-exporter:v1.3.1
docker tag quay.io/prometheus/alertmanager:v0.23.0 ${REGISTRY}/quay.io/prometheus/alertmanager:v0.23.0

docker push ${REGISTRY}/quay.io/ceph/ceph:v16
docker push ${REGISTRY}/quay.io/ceph/ceph-grafana:8.3.5
docker push ${REGISTRY}/quay.io/prometheus/prometheus:v2.33.4
docker push ${REGISTRY}/quay.io/prometheus/node-exporter:v1.3.1
docker push ${REGISTRY}/quay.io/prometheus/alertmanager:v0.23.0

cat >> /etc/ceph/ceph.conf << EOF
        auth_cluster_required = cephx
        auth_service_required = cephx
        auth_client_required = cephx
EOF

# 添加 server1 和 server2 为集群节点
# server
hostnames="nanopct4-server1 nanopct4-server2 nanopct4-server3 orangepi5-max-server1 orangepi5-plus-server1"
IFS=' ' read -r -a hostnamearray <<< "$hostnames"
for i in "${hostnamearray[@]}"; do
    #scp cephadm ${i}:~
    #ssh root@${i} "./cephadm add-repo --release squid && ./cephadm install"
    #ssh root@${i} "rm -rf /etc/ceph && systemctl stop ceph.target"
    ssh root@${i} "sed -i '/ceph-/d' ~/.ssh/authorized_keys"
    ssh-copy-id -f -i ~/ceph.pub root@${i}
    scp /var/lib/ceph/bootstrap-osd/ceph.keyring ${i}:/var/lib/ceph/bootstrap-osd/
    scp /etc/ceph/ceph.conf ${i}:/etc/ceph/
    if grep -q "nanopct4" ${i};then
      tailname=$(echo $i | awk -F- '{print $2}')
    else
      tailname=${i}
    fi
    ceph orch host add ${i} --labels=ceph-${tailname}
done
ceph orch host ls
ceph status
ceph health detail

# Dashboard 密码（cephadm bootstrap 生成后可能丢失，手动重置）
# Dashboard URL: https://${MASTER_IP}:8443/
# Username: admin
# Password: Ceph@2026.Admin
# 重置命令: echo -n '新密码' > /tmp/ceph_pwd && ceph dashboard ac-user-set-password admin -i /tmp/ceph_pwd && rm /tmp/ceph_pwd
ceph dashboard ac-user-set-password admin -i /dev/stdin <<< 'Ceph@2026.Admin' 2>/dev/null

ceph config set mon public_network 192.168.137.0/24
ceph orch apply mon --unmanaged
ceph orch daemon add mon ${MASTER_HOSTNAME}:${MASTER_IP}
ceph orch daemon add mon nanopct4-server1:192.168.137.201
ceph orch daemon add mon nanopct4-server2:192.168.137.202
ceph orch daemon add mon nanopct4-server3:192.168.137.203
ceph orch daemon add mon orangepi5-max-server1:192.168.137.211
ceph orch daemon add mon orangepi5-plus-server1:192.168.137.212

# 限制ceph占用内存
ceph config set osd osd_memory_target 1073741824
ceph config set osd osd_memory_cache_min 536870912
ceph config get osd osd_memory_target
ceph config get osd osd_memory_cache_min

# 设置标签，排除 master 节点
systemctl stop ceph-mgr@${MASTER_HOSTNAME}
ceph mgr fail ${MASTER_HOSTNAME}
ceph mgr module disable mgr
ceph mgr stat
systemctl disable ceph-mgr@${MASTER_HOSTNAME}
ceph orch host label add ${MASTER_HOSTNAME} no-mgr
ceph orch apply mgr --placement="orangepi5-max-server1,orangepi5-plus-server1"
ceph orch apply mds k8s-cephfs --placement="orangepi5-max-server1,orangepi5-plus-server1"

#scp /etc/ceph/ceph.conf nanopct4-server1:/etc/ceph/
#scp /etc/ceph/ceph.conf nanopct4-server2:/etc/ceph/
#scp /etc/ceph/ceph.conf nanopct4-server3:/etc/ceph/
#ceph auth get client.bootstrap-osd -o /var/lib/ceph/bootstrap-osd/ceph.keyring
#scp /var/lib/ceph/bootstrap-osd/ceph.keyring nanopct4-server1:/var/lib/ceph/bootstrap-osd/
#scp /var/lib/ceph/bootstrap-osd/ceph.keyring nanopct4-server2:/var/lib/ceph/bootstrap-osd/
#scp /var/lib/ceph/bootstrap-osd/ceph.keyring nanopct4-server3:/var/lib/ceph/bootstrap-osd/

# ============================================================
#  OSD 部署 — 每台 worker 的 NVMe 分区给 Ceph Bluestore
#  ARM64 上 cephadm 容器无法读取 NVMe udev 数据，必须用宿主机 ceph-volume
# ============================================================
hostnames="nanopct4-server1 nanopct4-server2 nanopct4-server3"
IFS=' ' read -r -a hostnamearray <<< "$hostnames"

# 1. 安装 ceph-volume 到宿主机（cephadm 容器里 udev 有 bug）
for i in "${hostnamearray[@]}"; do
    ssh root@${i} "apt install -y ceph-volume 2>/dev/null"
done

# 2. 确保 NVMe 分区 p2 存在并清理旧数据
for i in "${hostnamearray[@]}"; do
    ssh root@${i} "ls /dev/nvme0n1p2 2>/dev/null || parted /dev/nvme0n1 --script mkpart primary 50% 100%; partprobe /dev/nvme0n1"
    ssh root@${i} "wipefs -a /dev/nvme0n1p2 2>/dev/null; pvremove -ff /dev/nvme0n1p2 2>/dev/null; dd if=/dev/zero of=/dev/nvme0n1p2 bs=1M count=200 2>/dev/null"
done

# 3. 在宿主机直接跑 ceph-volume（不用 cephadm shell，绕过容器 udev 问题）
for i in "${hostnamearray[@]}"; do
    echo "Creating OSD on ${i}:/dev/nvme0n1p2 ..."
    ssh root@${i} "ceph-volume lvm create --data /dev/nvme0n1p2 --no-systemd"
done

# 4. 启动 OSD 守护进程（systemd 方式，因为 cephadm orch 发现不到 NVMe）
osd_hosts=("nanopct4-server1:0" "nanopct4-server2:1" "nanopct4-server3:2")
for entry in "${osd_hosts[@]}"; do
    host="${entry%%:*}"
    id="${entry##*:}"
    ssh root@${host} "systemctl start ceph-osd@${id} && systemctl enable ceph-osd@${id}"
done

# 5. 等待 OSD 上线
sleep 20

ceph orch device ls --wide
ceph osd tree
ceph -s

# ============================================================
#  K8s 存储池 & 认证
# ============================================================

# 1. 创建 RBD 池
ceph osd pool create k8s-pool 64 64
ceph osd pool application enable k8s-pool rbd

# 2. 创建 k8s 用户认证（必须在测试之前）
ceph auth get-or-create client.k8s \
    mon 'allow r' \
    osd 'allow rwx pool=k8s-pool' \
    mds 'allow rw' \
    -o /etc/ceph/ceph.client.k8s.keyring

# 3. 测试 RBD 是否可用
echo "Testing RBD..."
rbd create --size 1G k8s-pool/test-image --id k8s --keyring=/etc/ceph/ceph.client.k8s.keyring
rbd ls k8s-pool --id k8s --keyring=/etc/ceph/ceph.client.k8s.keyring
rbd map k8s-pool/test-image --id k8s --keyring=/etc/ceph/ceph.client.k8s.keyring
rbd showmapped
mkfs.xfs /dev/rbd0
mkdir -p /mnt/rbd-test
mount /dev/rbd0 /mnt/rbd-test
echo "Hello Ceph RBD" | tee /mnt/rbd-test/test.txt
cat /mnt/rbd-test/test.txt
umount /mnt/rbd-test && rmdir /mnt/rbd-test
rbd unmap /dev/rbd0
rbd rm k8s-pool/test-image --id k8s --keyring=/etc/ceph/ceph.client.k8s.keyring
echo "RBD test passed!"

# 4. 创建 CephFS 池 + 文件系统
ceph osd pool create k8s-cephfs-metadata 16 16
ceph osd pool create k8s-cephfs-data 16 16
ceph fs new k8s-cephfs k8s-cephfs-metadata k8s-cephfs-data
ceph fs subvolumegroup create k8s-cephfs k8s-storageclass-volumes

# 5. 部署 MDS（CephFS 需要）
ceph orch apply mds cephfs --placement="${MASTER_HOSTNAME}"

# 6. 补充 k8s 用户的 CephFS 权限
ceph auth caps client.k8s mon 'allow r' osd 'allow rwx pool=k8s-pool, allow rwx pool=k8s-cephfs-metadata, allow rwx pool=k8s-cephfs-data' mds 'allow rw'
ceph auth get client.k8s
ceph auth get-key client.k8s

# 7. 测试 CephFS 挂载
mkdir -p /mnt/k8s_cephfs
mount -t ceph :/ /mnt/k8s_cephfs -o name=k8s,secret=$(ceph auth get-key client.k8s)
mkdir -p /mnt/k8s_cephfs/k8s-volumes
echo "CephFS mounted successfully!"

# ============================================================
#  CSI 插件部署 — CephFS + RBD
#  ceph-csi v3.14.1（兼容 Ceph Squid 19.x）
# ============================================================

script_dir="$(cd "$(dirname "$0")" && pwd)"
[ -f "${script_dir}/../cluster_config.sh" ] && source "${script_dir}/../cluster_config.sh"
# 0. 解压本地包
tar -xzf ceph-csi-3.14.1.tar.gz -C /tmp/ 2>/dev/null
CSI_DIR="/tmp/ceph-csi-3.14.1"
[ -d "$CSI_DIR" ] || CSI_DIR="/root/ceph-csi"

# 0. 拉镜像 → 推本地 registry（阿里云中转，国内可用）
IMAGES=(
    "quay.io/cephcsi/cephcsi:v3.14.1"
    "registry.aliyuncs.com/google_containers/csi-provisioner:v5.2.0"
    "registry.aliyuncs.com/google_containers/csi-node-driver-registrar:v2.13.0"
    "registry.aliyuncs.com/google_containers/csi-resizer:v1.13.1"
    "registry.aliyuncs.com/google_containers/csi-snapshotter:v8.2.0"
    "registry.aliyuncs.com/google_containers/livenessprobe:v2.15.0"
    "registry.aliyuncs.com/google_containers/csi-attacher:v4.8.0"
)
REG="arm-cluster-master:5000"
for img in "${IMAGES[@]}"; do
    base_name=$(echo "$img" | sed 's#registry.aliyuncs.com/google_containers/##')
    base_name=$(echo "$base_name" | sed 's#quay.io/cephcsi/##')
    echo "=== Processing $img ==="
    docker pull "$img" 2>/dev/null || echo "(already cached)"
    dst="${REG}/${base_name}"
    docker tag "$img" "$dst" 2>/dev/null || docker tag "$base_name" "$dst"
    docker push "$dst"
done

# 1. 替换 CSI yaml 镜像 → arm-cluster-master:5000/xxx:tag
REG="arm-cluster-master:5000"
for dir in ${CSI_DIR}/deploy/cephfs/kubernetes ${CSI_DIR}/deploy/rbd/kubernetes; do
    for f in $(ls $dir/*.yaml 2>/dev/null); do
        sed -i "s|registry.k8s.io/sig-storage/csi-provisioner:.*|${REG}/csi-provisioner:v5.2.0|" $f
        sed -i "s|registry.k8s.io/sig-storage/csi-node-driver-registrar:.*|${REG}/csi-node-driver-registrar:v2.13.0|" $f
        sed -i "s|registry.k8s.io/sig-storage/csi-resizer:.*|${REG}/csi-resizer:v1.13.1|" $f
        sed -i "s|registry.k8s.io/sig-storage/csi-snapshotter:.*|${REG}/csi-snapshotter:v8.2.0|" $f
        sed -i "s|registry.k8s.io/sig-storage/csi-attacher:.*|${REG}/csi-attacher:v4.8.0|" $f
        sed -i "s|registry.k8s.io/sig-storage/livenessprobe:.*|${REG}/livenessprobe:v2.15.0|" $f
        sed -i "s|quay.io/cephcsi/cephcsi:.*|${REG}/cephcsi:v3.14.1|" $f
    done
done

# 2. 创建必需的 ConfigMaps
rm -rf ${CSI_DIR}/deploy/rbd/kubernetes/csi-config-map.yaml
rm -rf ${CSI_DIR}/deploy/cephfs/kubernetes/csi-config-map.yaml
FSID=$(ceph fsid 2>/dev/null | tr -d '[:space:]')
C8S_KEY=$(ceph auth get-key client.k8s)

# ceph-config：ceph.conf + 空 keyring（CSI 驱动会写入）
kubectl create configmap ceph-config -n default \
    --from-file=ceph.conf=/etc/ceph/ceph.conf \
    --from-literal=keyring= \
    --dry-run=client -o yaml | kubectl apply -f -

# ceph-csi-config：集群连接信息（v3.14+ 必需）
cat > /tmp/csi-config.json << JSONEOF
[{"clusterID":"${FSID}","monitors":["${MASTER_IP}:6789","192.168.137.201:6789","192.168.137.202:6789","192.168.137.203:6789"]}]
JSONEOF
kubectl create configmap ceph-csi-config -n default \
    --from-file=config.json=/tmp/csi-config.json \
    --dry-run=client -o yaml | kubectl apply -f -

# ceph-csi-encryption-kms-config（占位，CSI 要求存在）
kubectl create configmap ceph-csi-encryption-kms-config -n default \
    --from-literal=dummy=true \
    --dry-run=client -o yaml | kubectl apply -f -

# 3. 创建认证 Secret（v3.14 格式：userID + userKey）
for ns in default kube-system; do
    kubectl create secret generic ceph-secret -n $ns \
        --from-literal=userID=k8s \
        --from-literal=userKey=${C8S_KEY} \
        --dry-run=client -o yaml | kubectl apply -f -
done

# 4. 部署 CSI RBAC + Driver + Provisioner
kubectl apply -f ${CSI_DIR}/deploy/cephfs/kubernetes/
kubectl apply -f ${CSI_DIR}/deploy/rbd/kubernetes/

# 5. 清理 low-resource taint + 给 DaemonSet/provisioner 加 control-plane toleration
#   ——确保 CSI 能调度到集群所有节点
for node in nanopct4-server1 nanopct4-server2 nanopct4-server3; do
    kubectl taint node ${node} node-type=low-resource:NoSchedule- 2>/dev/null || true
done
sleep 3
# 为 CSI 节点插件（DaemonSet）添加容忍度，使其可调度到 Master 节点
for ds in csi-cephfsplugin csi-rbdplugin; do
    kubectl patch daemonset "$ds" -n default --type='json' -p='[
        {
            "op": "add",
            "path": "/spec/template/spec/tolerations",
            "value": [
                {"key": "node-role.kubernetes.io/control-plane", "operator": "Exists", "effect": "NoSchedule"},
                {"key": "node-role.kubernetes.io/master", "operator": "Exists", "effect": "NoSchedule"}
            ]
        }
    ]'
done

# 为 CSI 控制器（Deployment）添加容忍度，并缩放到 1 个副本
for deploy in csi-cephfsplugin-provisioner csi-rbdplugin-provisioner; do
    kubectl patch deployment "$deploy" -n default --type='json' -p='[
        {
            "op": "add",
            "path": "/spec/template/spec/tolerations",
            "value": [
                {"key": "node-role.kubernetes.io/control-plane", "operator": "Exists", "effect": "NoSchedule"}
            ]
        }
    ]' 2>/dev/null || true

    kubectl scale deployment "$deploy" -n default --replicas=1 2>/dev/null || true
done

# 6. 等待就绪并验证
sleep 20
echo ""
echo "=== CSI DaemonSet (each node should have a pod) ==="
kubectl get daemonset -n default | grep csi
echo ""
echo "=== CSI provisioner (all should be ready) ==="
kubectl get deploy -n default | grep csi


cat /etc/ceph/ceph.conf | grep mon
mon_host = [v2:192.168.137.101:3300/0,v1:192.168.137.101:6789/0] [v2:192.168.137.201:3300/0,v1:192.168.137.201:6789/0] [v2:192.168.137.202:3300/0,v1:192.168.137.202:6789/0] [v2:192.168.137.203:3300/0,v1:192.168.137.203:6789/0] [v2:192.168.137.211:3300/0,v1:192.168.137.211:6789/0]
ceph auth print-key client.k8s | base64 -w 0
QVFBQ3MwZHFUbkVLTFJBQXZCRDIwMm1WT250RFduWkRiM0RnMnc9PQ==
ceph fsid
3a4899f0-7689-11f1-90a0-c0742bfe683a

kubectl delete pod csi-cephfsplugin-4ffqq -n default                    
kubectl delete pod csi-cephfsplugin-62g8d -n default                    
kubectl delete pod csi-cephfsplugin-84nhp -n default                    
kubectl delete pod csi-cephfsplugin-h6w8f -n default                    
kubectl delete pod csi-cephfsplugin-jj2mr -n default                    
kubectl delete pod csi-cephfsplugin-provisioner-5f4f84f69d-ch6bd -n default                    
kubectl delete pod csi-rbdplugin-2jdtj -n default                    
kubectl delete pod csi-rbdplugin-provisioner-78f9c5547b-m2mrf -n default                    
kubectl delete pod csi-rbdplugin-qp2l2 -n default                    
kubectl delete pod csi-rbdplugin-v5qph -n default                    
kubectl delete pod csi-rbdplugin-wqqmd -n default                    
kubectl delete pod csi-rbdplugin-zngps -n default                    
