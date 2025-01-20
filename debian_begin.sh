#!/bin/bash
apt update
cd /etc/apt
debian_version=$(lsb_release -cs)
start_step="${1:-restart}"
name_tail="${2:-master}"
set_ip="${3:-192.168.10.200}"

timedatectl set-timezone Asia/Shanghai
timedatectl set-ntp true

if [ $start_step == "start" ];then
    old_name=$(hostname)
    hostnamectl set-hostname ${old_name}-${name_tail}
    sed -i 's/'${old_name}'/'$(hostname)'/g' /etc/hosts
    cat >> /etc/hosts << EOF
192.168.137.101 nanopct4-master
192.168.137.201 nanopct4-server1
192.168.137.202 nanopct4-server2
EOF

    mkfs.ext4 /dev/nvme0n1
    mkdir -p /mnt/nvme
    mount /dev/nvme0n1 /mnt/nvme
    echo "$(blkid /dev/nvme0n1 | awk '{print $2}' | sed 's/"//g') /mnt/nvme ext4 defaults 0 2" >> /etc/fstab

    sed -i 's/^X11Forwarding/#X11Forwarding/g' /etc/ssh/sshd_config

    sed -i 's/^deb/#deb/g' sources.list
    sed -i '$a\\' sources.list
    sed -i '$a\deb https://mirrors.ustc.edu.cn/debian/ '${debian_version}' main contrib non-free non-free-firmware' sources.list
    sed -i '$a\deb https://mirrors.ustc.edu.cn/debian/ '${debian_version}'-updates main contrib non-free non-free-firmware' sources.list
    sed -i '$a\deb https://mirrors.ustc.edu.cn/debian/ '${debian_version}'-backports main contrib non-free non-free-firmware' sources.list
    sed -i '$a\deb https://mirrors.ustc.edu.cn/debian-security/ '${debian_version}'-security main contrib non-free non-free-firmware' sources.list

    sed -i 's/^deb/#deb/g' sources.list.d/armbian.list
    sed -i '$a\\' sources.list.d/armbian.list
    sed -i '$a\deb [signed-by=/usr/share/keyrings/armbian.gpg] https://mirrors.ustc.edu.cn/armbian '${debian_version}' main '${debian_version}'-utils '${debian_version}'-desktop' sources.list.d/armbian.list
fi

apt update
apt upgrade -y

apt install -y ca-certificates curl software-properties-common

if [ $start_step == "start" ];then
    #curl -fsSL https://mirrors.ustc.edu.cn/docker-ce/linux/debian/gpg | apt-key add -
    #mv trusted.gpg /etc/apt/trusted.gpg.d/docker-ce.gpg
    #add-apt-repository -y "deb [arch=arm64] https://mirrors.ustc.edu.cn/docker-ce/linux/debian ${debian_version} stable"

    #curl -fsSL https://mirrors.ustc.edu.cn/docker-ce/linux/debian/gpg | gpg --import -
    #gpg --list-keys --with-colons #fpr字段为指纹
    #gpg --list-keys #key字段后面为id
    #KEYID_OR_FINGERPRINT=$(gpg --list-keys | sed -n '/Docker/{g;p;};h')
    #KEYID_OR_FINGERPRINT=$(gpg --list-keys | awk '/Docker/ {print prev} {prev=$0}')
    #gpg --output /etc/apt/keyrings/docker-ce.gpg --export $KEYID_OR_FINGERPRINT
    #echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker-ce.gpg] https://mirrors.ustc.edu.cn/docker-ce/linux/debian ${debian_version} stable" > /etc/apt/sources.list.d/docker-ce.list

    rm -rf /etc/apt/keyrings/docker-ce.gpg
    curl -fsSL https://mirrors.ustc.edu.cn/docker-ce/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker-ce.gpg
    echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker-ce.gpg] https://mirrors.ustc.edu.cn/docker-ce/linux/debian ${debian_version} stable" > /etc/apt/sources.list.d/docker-ce.list
fi

apt update
apt install -y docker-ce

mkdir -p /etc/docker
mkdir -p /mnt/nvme/docker
cat > /etc/docker/daemon.json << EOF
{
    "exec-opts": ["native.cgroupdriver=systemd"],
    "storage-driver": "overlay2",
    "data-root": "/mnt/nvme/docker/",
    "registry-mirrors": [
        "https://registry.docker-cn.com",
        "https://dockerproxy.cn",
        "https://docker.m.daocloud.io",
        "https://registry.aliyuncs.com"
    ],
    "insecure-registries": ["http://nanopct4-master:5000"]
}
EOF
systemctl daemon-reload
systemctl restart docker

usermod -aG docker zmh

if [ $start_step == "start" ];then
    rm -rf /etc/apt/keyrings/kubernetes-apt-keyring.gpg
    curl -fsSL https://mirrors.ustc.edu.cn/kubernetes/core:/stable:/v1.31/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
    echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://mirrors.ustc.edu.cn/kubernetes/core:/stable:/v1.31/deb/ /" > /etc/apt/sources.list.d/kubernetes.list
fi

apt update
apt install -y kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl

if [ $start_step == "start" ] && [ $name_tail == "master" ];then
    mkdir -p /certs
    cat > /certs/csr_config.cnf << EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
x509_extensions = v3_req
distinguished_name = req_distinguished_name
 
[req_distinguished_name]
C = CN
ST = Tianjin
L = Tianjin
O = ZMH
OU = zmh
CN = nanopct4-master # 注意：这里的 CN 通常不会被用作 SAN，但它是证书主题的一部分
 
[v3_req]
keyUsage = keyEncipherment, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = @alt_names
 
[alt_names]
DNS.1 = nanopct4-master
# 如果你的服务是基于 IP 地址的，你可以添加以下行（替换为你的 IP 地址）
# IP.1 = 192.168.1.100
EOF
    openssl req -x509 -newkey rsa:2048 -nodes -sha256 -config /certs/csr_config.cnf -extensions v3_req -keyout /certs/self_registry_ca.key -days 365 -out /certs/self_registry_ca.crt
    cp /certs/self_registry_ca.crt /etc/ssl/certs/
    cp /certs/self_registry_ca.key /etc/ssl/certs/
    docker pull arm64v8/registry:latest
    docker run -d -p 5000:5000 --name registry \
        -v /mnt/nvme/docker_registry:/var/lib/registry \
        -v /etc/ssl/certs/:/certs \
        -e REGISTRY_HTTP_ADDR=0.0.0.0:5000 \
        -e REGISTRY_HTTP_TLS_CERTIFICATE=/certs/self_registry_ca.crt \
        -e REGISTRY_HTTP_TLS_KEY=/certs/self_registry_ca.key \
        arm64v8/registry:latest
    curl --cacert /etc/ssl/certs/self_registry_ca.crt https://nanopct4-master:5000/v2/_catalog
    #curl --cacert /etc/ssl/certs/self_registry_ca.crt https://nanopct4-master:5000/v2/<repository-name>/tags/list
    #curl --cacert /etc/ssl/certs/self_registry_ca.crt --header "Accept: application/vnd.docker.distribution.manifest.v2+json" -I https://nanopct4-master:5000/v2/<repository-name>/manifests/<tag>
    #curl -X DELETE https://nanopct4-master:5000/v2/<repository-name>/manifests/<digest>
    #docker exec registry bin/registry garbage-collect /etc/docker/registry/config.yml
    docker pull arm64v8/debian:latest
    docker tag arm64v8/debian:latest nanopct4-master:5000/arm64v8/debian:latest
    docker push nanopct4-master:5000/arm64v8/debian:latest
fi

if [ $start_step == "start" ];then
    sed -i 's/^[^#]/#&/g' /etc/netplan/10-dhcp-all-interfaces.yaml
    echo ${set_ip}

    cat > /etc/netplan/99-custom-netplan-config.yaml << EOF
network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: no
      addresses: [${set_ip}/24]
      routes:
        - to: default
          via: 192.168.137.1
      nameservers:
        addresses: [8.8.8.8, 8.8.4.4]
EOF

    netplan apply
fi

apt install -y python3 python3-pip
apt install -y vim
apt install -y lrzsz

reboot

cat > /etc/modules-load.d/k8s.conf << EOF
br_netfilter
EOF
modprobe -- br_netfilter

cat > /etc/sysctl.d/k8s.conf << EOF
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
vm.swappiness = 0
EOF
sysctl --system

apt install -y ipset ipvsadm
mkdir -p /etc/default/modules
cat > /etc/default/modules/ipvs.module << EOF
#!/bin/bash
modprobe -- ip_vs
modprobe -- ip_vs_rr
modprobe -- ip_vs_wrr
modprobe -- ip_vs_sh
modprobe -- nf_conntrack
EOF
chmod +x /etc/default/modules/ipvs.module
/etc/default/modules/ipvs.module

containerd config default > /etc/containerd/config.toml
sed -i 's#pause:3.8#pause:3.10#g' /etc/containerd/config.toml
sed -i 's#sandbox_image = "registry.k8s.io#sandbox_image = "nanopct4-master:5000#g' /etc/containerd/config.toml
sed -i 's#SystemdCgroup = false#SystemdCgroup = true#' /etc/containerd/config.toml
#sed -i '/\[plugins."io.containerd.grpc.v1.cri".registry.mirrors\]/{N;s#\n.*$#\n        \[plugins."io.containerd.grpc.v1.cri".registry.mirrors."nanopct4-master"\]\n          endpoint = \["https://nanopct4-master:5000"\]\n#}' /etc/containerd/config.toml

systemctl daemon-reload && systemctl restart containerd.service
#ctr image pull nanopct4-master:5000/arm64v8/debian:latest

cat > /etc/crictl.yaml << EOF
runtime-endpoint: unix:///var/run/containerd/containerd.sock
image-endpoint: unix:///var/run/containerd/containerd.sock
timeout: 10
debug: false
EOF

echo 'KUBELET_EXTRA_ARGS="--cgroup-driver=systemd"' > /etc/default/kubelet
#打印k8s初始化配置文件
kubeadm config print init-defaults > kubeadm_config.yaml

sed -i 's#advertiseAddress: 1.2.3.4#advertiseAddress: 192.168.137.101#' kubeadm_config.yaml
sed -i 's#1.31.0#1.31.2#' kubeadm_config.yaml
sed -i 's#name: node#name: nanopct4-master#' kubeadm_config.yaml
sed -i 's#imageRepository: registry.k8s.io#imageRepository: nanopct4-master:5000#' kubeadm_config.yaml
sed -i '/serviceSubnet/a\  podSubnet: "10.244.0.0/16"' kubeadm_config.yaml
#sed -i 's#criSocket: unix:///var/run/containerd/containerd.sock#criSocket: unix:///var/run/cri-dockerd.sock#' kubeadm_config.yaml


kubeadm config images list --kubernetes-version=v1.31.2 --image-repository=registry.aliyuncs.com/google_containers
docker pull registry.aliyuncs.com/google_containers/kube-apiserver:v1.31.2
docker pull registry.aliyuncs.com/google_containers/kube-controller-manager:v1.31.2
docker pull registry.aliyuncs.com/google_containers/kube-scheduler:v1.31.2
docker pull registry.aliyuncs.com/google_containers/kube-proxy:v1.31.2
docker pull registry.aliyuncs.com/google_containers/coredns:v1.11.3
docker pull registry.aliyuncs.com/google_containers/pause:3.10
docker pull registry.aliyuncs.com/google_containers/etcd:3.5.15-0

docker tag registry.aliyuncs.com/google_containers/kube-apiserver:v1.31.2 nanopct4-master:5000/kube-apiserver:v1.31.2
docker tag registry.aliyuncs.com/google_containers/kube-controller-manager:v1.31.2 nanopct4-master:5000/kube-controller-manager:v1.31.2
docker tag registry.aliyuncs.com/google_containers/kube-scheduler:v1.31.2 nanopct4-master:5000/kube-scheduler:v1.31.2
docker tag registry.aliyuncs.com/google_containers/kube-proxy:v1.31.2 nanopct4-master:5000/kube-proxy:v1.31.2
docker tag registry.aliyuncs.com/google_containers/coredns:v1.11.3 nanopct4-master:5000/coredns:v1.11.3
docker tag registry.aliyuncs.com/google_containers/pause:3.10 nanopct4-master:5000/pause:3.10
docker tag registry.aliyuncs.com/google_containers/etcd:3.5.15-0 nanopct4-master:5000/etcd:3.5.15-0

docker push nanopct4-master:5000/kube-apiserver:v1.31.2
docker push nanopct4-master:5000/kube-controller-manager:v1.31.2
docker push nanopct4-master:5000/kube-scheduler:v1.31.2
docker push nanopct4-master:5000/kube-proxy:v1.31.2
docker push nanopct4-master:5000/coredns:v1.11.3
docker push nanopct4-master:5000/pause:3.10
docker push nanopct4-master:5000/etcd:3.5.15-0

#kubeadm config images pull --kubernetes-version=v1.31.2 --image-repository=registry.aliyuncs.com/google_containers
#kubeadm init --config kubeadm_config.yaml --upload-certs --v=5

swapoff -a

kubeadm init --apiserver-advertise-address=192.168.137.101 \
--apiserver-bind-port=6443 \
--control-plane-endpoint=nanopct4-master \
--kubernetes-version=v1.31.2 \
--image-repository=nanopct4-master:5000 \
--service-cidr=10.96.0.0/12 \
--pod-network-cidr=10.244.0.0/16 \
--upload-certs \
--v=5

#systemctl status kubelet
#journalctl -xefu kubelet
#crictl --runtime-endpoint unix:///var/run/containerd/containerd.sock ps -a | grep kube | grep -v pause
#crictl --runtime-endpoint unix:///var/run/containerd/containerd.sock logs CONTAINERID

mkdir -p $HOME/.kube
cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
chown $(id -u):$(id -g) $HOME/.kube/config
export KUBECONFIG=/etc/kubernetes/admin.conf

kubectl create secret generic registry-secret \
--from-file=tls.crt=/etc/ssl/certs/self_registry_ca.crt \
--from-file=tls.key=/etc/ssl/certs/self_registry_ca.key \
--namespace=kube-system

#wget https://docs.projectcalico.org/manifests/calico.yaml --no-check-certificate
##kubectl create -f https://docs.projectcalico.org/archive/v3.20/manifests/calico.yaml
#sed -i 's?# - name: CALICO_IPV4POOL_CIDR?- name: CALICO_IPV4POOL_CIDR?g' calico.yaml
#sed -i 's?#   value: "192.168.0.0/16"?  value: "10.244.0.0/16"?g' calico.yaml
#sed -i 's#docker.io/calico#nanopct4-master:5000/calico#g' calico.yaml
#sed -i 's/:v[0-9]*\.[0-9]*\.[0-9]*/:v3.20.1/g' calico.yaml
#docker pull calico/cni:v3.20.1
#docker pull calico/node:v3.20.1
#docker pull calico/kube-controllers:v3.20.1
#docker tag calico/cni:v3.20.1 nanopct4-master:5000/calico/cni:v3.20.1
#docker tag calico/node:v3.20.1 nanopct4-master:5000/calico/node:v3.20.1
#docker tag calico/kube-controllers:v3.20.1 nanopct4-master:5000/calico/kube-controllers:v3.20.1
#docker push nanopct4-master:5000/calico/cni:v3.20.1
#docker push nanopct4-master:5000/calico/node:v3.20.1
#docker push nanopct4-master:5000/calico/kube-controllers:v3.20.1
#kubectl apply -f calico.yaml

wget https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 -O get_helm.sh
chmod +x get_helm.sh
./get_helm.sh

wget https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
sed -i 's#docker.io#nanopct4-master:5000#' kube-flannel.yml

kubectl create ns kube-flannel
kubectl label --overwrite ns kube-flannel pod-security.kubernetes.io/enforce=privileged
ARCH=$(uname -m)
  case $ARCH in
    armv7*) ARCH="arm";;
    aarch64) ARCH="arm64";;
    x86_64) ARCH="amd64";;
  esac
mkdir -p /opt/cni/bin
curl -O -L https://github.com/containernetworking/plugins/releases/download/v1.6.0/cni-plugins-linux-$ARCH-v1.6.0.tgz
tar -C /opt/cni/bin -xzf cni-plugins-linux-$ARCH-v1.6.0.tgz
#helm repo add flannel https://flannel-io.github.io/flannel/
#helm install flannel \
#--set podCidr="10.244.0.0/16" \
#--set image.repository="nanopct4-master:5000/flannel/flannel" \
#--set image.tag="v0.26.2" \
#--namespace kube-flannel \
#--version="v0.26.2" \
#flannel/flannel 
#helm status flannel -n kube-flannel
#helm uninstall flannel -n kube-flannel
#helm repo remove flannel

docker pull flannel/flannel-cni-plugin:v1.6.0-flannel1
docker pull flannel/flannel:v0.26.2

docker tag flannel/flannel-cni-plugin:v1.6.0-flannel1 nanopct4-master:5000/flannel/flannel-cni-plugin:v1.6.0-flannel1
docker tag flannel/flannel:v0.26.2 nanopct4-master:5000/flannel/flannel:v0.26.2

docker push nanopct4-master:5000/flannel/flannel-cni-plugin:v1.6.0-flannel1
docker push nanopct4-master:5000/flannel/flannel:v0.26.2

kubectl apply -f kube-flannel.yml

systemctl restart kubelet
systemctl restart containerd

#kubectl describe pod ${pod_name} -n kube-system
kubectl get pod -A
kubectl get pod -n kube-system
kubectl get nodes
kubectl get events -n kube-system
kubectl logs pod-name -n kube-system --previous

kubeadm token create --print-join-command -v=5

kubeadm reset -f
rm -rf $HOME/.kube/config
rm -rf /etc/cni/net.d
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X
iptables -P INPUT ACCEPT
iptables -P FORWARD ACCEPT
iptables -P OUTPUT ACCEPT
 
# 遍历所有镜像ID并删除
for id in $(crictl images -q); do
    crictl rmi $id
done

docker restart $(docker ps -a | grep arm64v8/registry:latest | awk '{print $1}')

servercmd=$(kubeadm token create --print-join-command)
hostnames="nanopct4-server1 nanopct4-server2"
IFS=' ' read -r -a hostnamearray <<< "$hostnames"
for i in "${hostnamearray[@]}"; do
    ssh root@${i} "swapoff -a;\
        kubeadm reset -f;\
        rm -rf $HOME/.kube/config;\
        rm -rf /etc/cni/net.d;\
        iptables -F;\
        iptables -X;\
        iptables -t nat -F;\
        iptables -t nat -X;\
        iptables -t mangle -F;\
        iptables -t mangle -X;\
        iptables -P INPUT ACCEPT;\
        iptables -P FORWARD ACCEPT;\
        iptables -P OUTPUT ACCEPT"
    
    ssh root@${i} "${servercmd}"
done