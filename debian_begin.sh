#!/bin/bash
apt update
cd /etc/apt
debian_version=$(lsb_release -cs)
start_step="${1:-restart}"
name_tail="${2:-master}"
set_ip="${3:-192.168.10.200}"

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
        "https://docker.m.daocloud.io"
    ]
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker

usermod -aG docker zmh

if [ $start_step == "start" ];then
    rm -rf /etc/apt/keyrings/kubernetes-apt-keyring.gpg
    curl -fsSL https://mirrors.ustc.edu.cn/kubernetes/core:/stable:/v1.31/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
    echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://mirrors.ustc.edu.cn/kubernetes/core:/stable:/v1.31/deb/ /" > /etc/apt/sources.list.d/kubernetes.list
fi

apt update
apt install -y kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl

containerd config default > /etc/containerd/config.toml
sed -i 's#pause:3.8#pause:3.10#g' /etc/containerd/config.toml
sed -i 's#sandbox_image = "registry.k8s.io#sandbox_image = "registry.cn-hangzhou.aliyuncs.com/google_containers#g' /etc/containerd/config.toml
sed -i 's#SystemdCgroup = false#SystemdCgroup = true#' /etc/containerd/config.toml
sed '/\[plugins."io.containerd.grpc.v1.cri".registry.mirrors\]/a\
        [plugins."io.containerd.grpc.v1.cri".registry.mirrors."docker.io"]\
          endpoint = ["http://nanopct4-master:5000"]' /etc/containerd/config.toml > /etc/containerd/config.toml.tmp
mv /etc/containerd/config.toml.tmp /etc/containerd/config.toml
systemctl daemon-reload && systemctl restart containerd.service
cat > /etc/crictl.yaml << EOF
runtime-endpoint: unix:///var/run/containerd/containerd.sock
image-endpoint: unix:///var/run/containerd/containerd.sock
timeout: 10
debug: false
EOF

if [ $start_step == "start" ] && [ $name_tail == "master" ];then
    docker pull arm64v8/registry:latest
    docker run -d -p 5000:5000 --name registry -v /mnt/nvme/docker_registry:/var/lib/registry arm64v8/registry:latest
    docker pull arm64v8/debian:latest
    docker tag arm64v8/debian:latest localhost:5000/arm64v8/debian:latest
    docker push localhost:5000/arm64v8/debian:latest
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

sed -i 's#KUBELET_EXTRA_ARGS=#KUBELET_EXTRA_ARGS="--cgroup-driver=systemd"#g' /etc/default/kubelet
#打印k8s初始化配置文件
#kubeadm config print init-defaults > kubeadm_config.yaml

#修改镜像拉取地址
#sed -i 's#imageRepository: registry.k8s.io#imageRepository: registry.cn-hangzhou.aliyuncs.com/google_containers#' kubeadm_config.yaml

#kubeadm config images pull --kubernetes-version=v1.31.2 --image-repository=registry.cn-hangzhou.aliyuncs.com/google_containers
#kubeadm init --config kubeadm_config.yaml --upload-certs

swapoff -a
kubeadm init --apiserver-advertise-address=192.168.137.101 \
--control-plane-endpoint=nanopct4-master \
--kubernetes-version=v1.31.2 \
--image-repository=registry.cn-hangzhou.aliyuncs.com/google_containers \
--service-cidr=10.96.0.0/12 \
--pod-network-cidr=10.244.0.0/16

#journalctl -xefu kubelet

mkdir -p $HOME/.kube
cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
chown $(id -u):$(id -g) $HOME/.kube/config
export KUBECONFIG=/etc/kubernetes/admin.conf

wget https://docs.projectcalico.org/manifests/calico.yaml --no-check-certificate
#kubectl create -f https://docs.projectcalico.org/archive/v3.20/manifests/calico.yaml

sed -i 's?# - name: CALICO_IPV4POOL_CIDR?- name: CALICO_IPV4POOL_CIDR?g' calico.yaml
sed -i 's?#   value: "192.168.0.0/16"?  value: "10.244.0.0/16"?g' calico.yaml
sed -i 's#docker.io/calico#registry.cn-hangzhou.aliyuncs.com/kubesphereio#g' calico.yaml
sed -i 's/:v[0-9]*\.[0-9]*\.[0-9]*/:v3.20.1/g' calico.yaml

ctr -n k8s.io i pull registry.cn-hangzhou.aliyuncs.com/google_containers/calico/cni:v3.20.1
ctr -n k8s.io i pull registry.cn-hangzhou.aliyuncs.com/google_containers/calico/node:v3.20.1
ctr -n k8s.io i pull registry.cn-hangzhou.aliyuncs.com/google_containers/calico/kube-controllers:v3.20.1

docker pull calico/cni:v3.20.1
docker pull calico/node:v3.20.1
docker pull calico/kube-controllers:v3.20.1

kubectl apply -f calico.yaml
#kubectl describe pod ${pod_name} -n kube-system
kubectl get pod -A
kubectl get pod -n kube-system
kubectl get nodes


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