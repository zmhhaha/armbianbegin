#!/bin/bash
apt update
apt install vim -y
apt install lrzsz -y
cd /etc/apt

sed -i 's/^deb/#deb/g' sources.list
sed -i '$a\\' sources.list
sed -i '$a\deb https://mirrors.ustc.edu.cn/debian/ bookworm main contrib non-free non-free-firmware' sources.list
sed -i '$a\deb https://mirrors.ustc.edu.cn/debian/ bookworm-updates main contrib non-free non-free-firmware' sources.list
sed -i '$a\deb https://mirrors.ustc.edu.cn/debian/ bookworm-backports main contrib non-free non-free-firmware' sources.list
sed -i '$a\deb https://mirrors.ustc.edu.cn/debian-security/ bookworm-security main contrib non-free non-free-firmware' sources.list

sed -i 's/^deb/#deb/g' sources.list.d/armbian.list
sed -i '$a\\' sources.list.d/armbian.list
sed -i '$a\deb [signed-by=/usr/share/keyrings/armbian.gpg] https://mirrors.ustc.edu.cn/armbian bookworm main bookworm-utils bookworm-desktop' sources.list.d/armbian.list

apt update

apt install -y ca-certificates curl software-properties-common

#curl -fsSL https://mirrors.ustc.edu.cn/docker-ce/linux/debian/gpg | apt-key add -
#mv trusted.gpg trusted.gpg.d/docker-ce.gpg
#add-apt-repository "deb [arch=arm64] https://mirrors.ustc.edu.cn/docker-ce/linux/debian $(lsb_release -cs) stable"

#curl -fsSL https://mirrors.ustc.edu.cn/docker-ce/linux/debian/gpg | gpg --import -
#gpg --list-keys --with-colons #fpr字段为指纹
#gpg --list-keys #key字段后面为id
#gpg --output /etc/apt/trusted.gpg.d/docker-ce.gpg --export $KEYID_OR_FINGERPRINT
#add-apt-repository "deb [arch=arm64] https://mirrors.ustc.edu.cn/docker-ce/linux/debian $(lsb_release -cs) stable"

curl -fsSL https://mirrors.ustc.edu.cn/docker-ce/linux/debian/gpg > /etc/apt/trusted.gpg.d/docker-ce.asc
gpg -output /etc/apt/keyrings/docker-ce.gpg
add-apt-repository 'deb [arch=arm64 signed-by=/etc/apt/keyrings/docker-ce.gpg] https://mirrors.ustc.edu.cn/docker-ce/linux/debian '$(lsb_release -cs)' stable'