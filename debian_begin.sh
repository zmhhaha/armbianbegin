#!/bin/bash
apt update
cd /etc/apt
debian_version=$(lsb_release -cs)
start_step="${1:-restart}"

if [ $start_step -eq "start" ];then
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
# 设置完成后重启
sudo systemctl daemon-reload
sudo systemctl restart docker

usermod -aG docker zmh

rm -rf /etc/apt/keyrings/kubernetes-apt-keyring.gpg
curl -fsSL https://mirrors.ustc.edu.cn/kubernetes/core:/stable:/v1.31/deb/Release.key | gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://mirrors.ustc.edu.cn/kubernetes/core:/stable:/v1.31/deb/ /" > /etc/apt/sources.list.d/kubernetes.list
apt update
apt install -y kubelet kubeadm kubectl
apt-mark hold kubelet kubeadm kubectl

#containerd config default > /etc/containerd/config.toml
sed -i 's/disabled_plugins = ["false"]/disabled_plugins = ["cri"]/g'

docker pull arm64v8/registry:latest
docker run -d -p 5000:5000 --name registry -v /mnt/nvme/docker_registry:/var/lib/registry arm64v8/registry:latest
docker pull arm64v8/debian:latest
docker tag arm64v8/debian:latest localhost:5000/arm64v8/debian:latest
docker push localhost:5000/arm64v8/debian:latest

apt install -y python3 python3-pip
apt install -y vim
apt install -y lrzsz