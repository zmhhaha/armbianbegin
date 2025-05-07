#rm -rf /etc/apt/keyrings/ceph.gpg
#curl -fsSL https://download.ceph.com/keys/release.asc |  gpg --dearmor -o /etc/apt/keyrings/ceph.gpg
#echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/ceph.gpg] https://download.ceph.com/debian-squid/ $(lsb_release -sc) main" | tee /etc/apt/sources.list.d/ceph.list
apt update
apt install -y ceph-mon ceph-osd ceph-mgr ceph-common
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
# mon_host = 192.168.137.101,192.168.137.201,192.168.137.202  # 替换为实际 IP
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

cephadm bootstrap --mon-ip 192.168.137.101 --cluster-network 192.168.137.0/24
ceph cephadm get-pub-key > ~/ceph.pub
ssh-copy-id -f -i ~/ceph.pub root@nanopct4-master
ceph auth get client.bootstrap-osd -o /var/lib/ceph/bootstrap-osd/ceph.keyring
ceph orch host label add nanopct4-master ceph-master
#ceph orch host label rm nanopct4-master ceph-master

docker tag quay.io/ceph/ceph:v16 nanopct4-master:5000/quay.io/ceph/ceph:v16
docker tag quay.io/ceph/ceph-grafana:8.3.5 nanopct4-master:5000/quay.io/ceph/ceph-grafana:8.3.5
docker tag quay.io/prometheus/prometheus:v2.33.4 nanopct4-master:5000/quay.io/prometheus/prometheus:v2.33.4
docker tag quay.io/prometheus/node-exporter:v1.3.1 nanopct4-master:5000/quay.io/prometheus/node-exporter:v1.3.1
docker tag quay.io/prometheus/alertmanager:v0.23.0 nanopct4-master:5000/quay.io/prometheus/alertmanager:v0.23.0

docker push nanopct4-master:5000/quay.io/ceph/ceph:v16
docker push nanopct4-master:5000/quay.io/ceph/ceph-grafana:8.3.5
docker push nanopct4-master:5000/quay.io/prometheus/prometheus:v2.33.4
docker push nanopct4-master:5000/quay.io/prometheus/node-exporter:v1.3.1
docker push nanopct4-master:5000/quay.io/prometheus/alertmanager:v0.23.0

cat >> /etc/ceph/ceph.conf << EOF
        auth_cluster_required = cephx
        auth_service_required = cephx
        auth_client_required = cephx
EOF

# 添加 server1 和 server2 为集群节点
hostnames="nanopct4-server1 nanopct4-server2 orangepi5-max-server1"
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

ceph config set mon public_network 192.168.137.0/24
ceph orch apply mon --unmanaged
ceph orch daemon add mon nanopct4-master:192.168.137.101
ceph orch daemon add mon nanopct4-server1:192.168.137.201
ceph orch daemon add mon nanopct4-server2:192.168.137.202
ceph orch daemon add mon orangepi5-max-server1:192.168.137.211

#scp /etc/ceph/ceph.conf nanopct4-server1:/etc/ceph/
#scp /etc/ceph/ceph.conf nanopct4-server2:/etc/ceph/
#ceph auth get client.bootstrap-osd -o /var/lib/ceph/bootstrap-osd/ceph.keyring
#scp /var/lib/ceph/bootstrap-osd/ceph.keyring nanopct4-server1:/var/lib/ceph/bootstrap-osd/
#scp /var/lib/ceph/bootstrap-osd/ceph.keyring nanopct4-server1:/var/lib/ceph/bootstrap-osd/
parted /dev/nvme0n1p2 mklabel msdos

ceph-volume lvm create --data /dev/nvme0n1p2 --bluestore
ceph-volume lvm activate --all

ceph orch device ls --wide
ceph osd tree

ceph orch daemon add osd nanopct4-master:/mnt/nvme
ceph orch daemon add osd nanopct4-server1:/mnt/nvme
ceph orch daemon add osd nanopct4-server2:/mnt/nvme

# 创建存储池（例如为 K8s 创建专用池）
ceph osd pool create k8s-pool 64 64
ceph osd pool application enable k8s-pool rbd  # 启用 RBD 应用
#################################
# 测试创建的rbd池是否可用
rbd create --size 1G k8s-pool/test-image --id k8s --keyring=/etc/ceph/ceph.client.k8s.keyring
rbd ls k8s-pool --id k8s --keyring=/etc/ceph/ceph.client.k8s.keyring
rbd map k8s-pool/test-image --id k8s --keyring=/etc/ceph/ceph.client.k8s.keyring
rbd showmapped
mkfs.xfs /dev/rbd0
mkdir -p /mnt/rbd-test
mount /dev/rbd0 /mnt/rbd-test
echo "Hello Ceph RBD" | tee /mnt/rbd-test/test.txt
cat /mnt/rbd-test/test.txt
umount /mnt/rbd-test
rmdir /mnt/rbd-test
rbd unmap /dev/rbd0
rbd rm k8s-pool/test-image --id k8s --keyring=/etc/ceph/ceph.client.k8s.keyring
#################################
# 创建元数据池和数据池（如果尚未创建）
ceph fs ls
ceph fs status
ceph osd pool create k8s-cephfs-metadata 16 16
ceph osd pool create k8s-cephfs-data 16 16
#ceph config set mon mon_allow_pool_delete true
#ceph osd pool delete k8s-cephfs-metadata k8s-cephfs-metadata --yes-i-really-really-mean-it-not-faking
#ceph osd pool delete k8s-cephfs-data k8s-cephfs-data --yes-i-really-really-mean-it-not-faking
# 创建 CephFS 文件系统
ceph fs new k8s-cephfs k8s-cephfs-metadata k8s-cephfs-data
#ceph fs rm k8s-cephfs --yes-i-really-mean-it
ceph fs subvolumegroup create k8s-cephfs k8s-storageclass-volumes
ceph fs subvolumegroup ls k8s-cephfs
# ceph fs subvolumegroup depete k8s-cephfs k8s-storageclass-volumes
# 部署mds
ceph orch apply mds cephfs --placement="nanopct4-master"
# 创建秘钥
ceph auth del client.k8s
ceph auth get-or-create client.k8s \
  mon 'allow r' \
  osd 'allow rwx pool=k8s-pool, allow r pool=k8s-cephfs-metadata' \
  mds 'allow rw' \
  -o /etc/ceph/ceph.client.k8s.keyring
# 查看密钥（保存以下输出，稍后用于 K8s Secret）
ceph auth get-key client.k8s
ceph auth get client.k8s
# 挂载本地节点
mkdir -p /mnt/k8s_cephfs
mount -t ceph :/ /mnt/k8s_cephfs \
  -o name=admin,secret=$(ceph auth get-key client.admin)
mount -t ceph :/ /mnt/k8s_cephfs \
  -o name=k8s,secret=$(ceph auth get-key client.k8s)
mkdir -p /mnt/k8s_cephfs/k8s-volumes

##################################################
hostnames="nanopct4-server1 nanopct4-server2"
IFS=' ' read -r -a hostnamearray <<< "$hostnames"
for i in "${hostnamearray[@]}"; do
    #ssh root@${i} "systemctl stop ceph-mon@${i}"
    #ssh root@${i} "systemctl stop ceph-osd@${i}"
    ceph orch host drain ${i}
    #ssh root@${i} "systemctl stop ceph-mon.target"
    ceph orch osd rm status
    ceph orch ps ${i}
    ceph orch host rm ${i}
done
systemctl stop ceph.target

cephadm ls
cephadm rm-cluster --fsid ${FSID} --force --zap-osds
rm -rf /etc/systemd/system/ceph-*.service
rm -rf /etc/systemd/system/ceph.target.wants
systemctl daemon-reload
docker ps -a | grep ceph | awk '{print $1}' | xargs docker stop
docker ps -a | grep ceph | awk '{print $1}' | xargs docker rm
rm -rf /etc/ceph
rm -rf /var/lib/ceph

cephadm ls
cephadm rm-cluster --fsid 3f12b9e4-fce0-11ef-97b1-ca1173533d33 --force --zap-osds
rm -rf /etc/systemd/system/ceph-*.service
rm -rf /etc/systemd/system/ceph.target.wants
systemctl daemon-reload
###################################################

# 部署csi插件
git clone https://github.com/ceph/ceph-csi.git
cd ceph-csi/deploy/cephfs/kubernetes
sed -i 's#registry.k8s.io/sig-storage/#registry.aliyuncs.com/google_containers/#' csi-nodeplugin-rbac.yaml
sed -i 's#registry.k8s.io/sig-storage/#registry.aliyuncs.com/google_containers/#' csi-provisioner-rbac.yaml
sed -i 's#registry.k8s.io/sig-storage/#registry.aliyuncs.com/google_containers/#' csi-cephfsplugin-provisioner.yaml
sed -i 's#registry.k8s.io/sig-storage/#registry.aliyuncs.com/google_containers/#' csi-cephfsplugin.yaml
sed -i 's#registry.k8s.io/sig-storage/#registry.aliyuncs.com/google_containers/#' ../../rbd/kubernetes/csi-nodeplugin-rbac.yaml
sed -i 's#registry.k8s.io/sig-storage/#registry.aliyuncs.com/google_containers/#' ../../rbd/kubernetes/csi-provisioner-rbac.yaml
sed -i 's#registry.k8s.io/sig-storage/#registry.aliyuncs.com/google_containers/#' ../../rbd/kubernetes/csi-rbdplugin-provisioner.yaml
sed -i 's#registry.k8s.io/sig-storage/#registry.aliyuncs.com/google_containers/#' ../../rbd/kubernetes/csi-rbdplugin.yaml

##################################################
# 为保证服务可以在控制平面启动的配置
# csi-*plugin-provisioner.yaml必须修改 否则在控制平面上的存储服务无法对外提供
cat >> csi-cephfsplugin-provisioner.yaml << EOF
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          operator: Exists
          effect: NoSchedule
EOF
cat >> ../../rbd/kubernetes/csi-rbdplugin-provisioner.yaml << EOF
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          operator: Exists
          effect: NoSchedule
EOF
# csi-*plugin.yaml必须修改 否则在控制平面上启动的服务无法使用ceph提供的存储服务
sed -i '/volumes:/i\
      tolerations:\
        - key: node-role.kubernetes.io/control-plane\
          operator: Exists\
          effect: NoSchedule' csi-cephfsplugin.yaml
sed -i '/volumes:/i\
      tolerations:\
        - key: node-role.kubernetes.io/control-plane\
          operator: Exists\
          effect: NoSchedule' ../../rbd/kubernetes/csi-rbdplugin.yaml
##################################################

# 创建 RBAC 和 Provisioner
cd ~
cd ceph-csi/deploy/cephfs/kubernetes
kubectl apply -f csi-provisioner-rbac.yaml
kubectl apply -f csi-nodeplugin-rbac.yaml
kubectl apply -f csi-cephfsplugin-provisioner.yaml
kubectl apply -f csi-cephfsplugin.yaml
kubectl apply -f csidriver.yaml
kubectl apply -f ../../rbd/kubernetes/csi-nodeplugin-rbac.yaml
kubectl apply -f ../../rbd/kubernetes/csi-provisioner-rbac.yaml
kubectl apply -f ../../rbd/kubernetes/csi-rbdplugin-provisioner.yaml
kubectl apply -f ../../rbd/kubernetes/csi-rbdplugin.yaml
kubectl apply -f ../../rbd/kubernetes/csidriver.yaml
kubectl get pods -n default | grep csi

cd ~
cd ceph-csi/deploy/cephfs/kubernetes
kubectl delete -f csi-provisioner-rbac.yaml
kubectl delete -f csi-nodeplugin-rbac.yaml
kubectl delete -f csi-cephfsplugin-provisioner.yaml
kubectl delete -f csi-cephfsplugin.yaml
kubectl delete -f ../../rbd/kubernetes/csi-nodeplugin-rbac.yaml
kubectl delete -f ../../rbd/kubernetes/csi-provisioner-rbac.yaml
kubectl delete -f ../../rbd/kubernetes/csi-rbdplugin-provisioner.yaml
kubectl delete -f ../../rbd/kubernetes/csi-rbdplugin.yaml

docker pull quay.io/cephcsi/cephcsi:canary
docker pull registry.k8s.io/sig-storage/csi-attacher:v4.8.0
docker pull registry.k8s.io/sig-storage/csi-provisioner:v5.1.0
docker pull registry.k8s.io/sig-storage/csi-resizer:v1.13.1
docker pull registry.k8s.io/sig-storage/csi-snapshotter:v8.2.0
docker pull registry.k8s.io/sig-storage/csi-node-driver-registrar:v2.13.0

docker pull registry.aliyuncs.com/google_containers/csi-attacher:v4.8.0
docker pull registry.aliyuncs.com/google_containers/csi-provisioner:v5.1.0
docker pull registry.aliyuncs.com/google_containers/csi-resizer:v1.13.1
docker pull registry.aliyuncs.com/google_containers/csi-snapshotter:v8.2.0
docker pull registry.aliyuncs.com/google_containers/csi-node-driver-registrar:v2.13.0

kubectl logs -f <pod_name> -c <pod_group_name>
kubectl exec -it <csi-rbdplugin-pod> -- ceph -s --cluster ceph --name client.k8s
kubectl logs -l app=csi-rbdplugin-provisioner -n <namespace> --tail=100
rados -p k8s-pool ls --name client.k8s --keyring /etc/ceph/ceph.client.k8s.keyring


kubectl get pods -l app=csi-rbdplugin-provisioner  # RBD 插件
kubectl get pods -l app=csi-cephfsplugin-provisioner  # CephFS 插件

kubectl rollout restart deployment csi-rbdplugin-provisioner
kubectl rollout restart daemonset csi-rbdplugin

kubectl delete -f ceph-rbd-storageclass.yaml -f cephfs-storageclass.yaml
kubectl apply -f ceph-rbd-storageclass.yaml -f cephfs-storageclass.yaml