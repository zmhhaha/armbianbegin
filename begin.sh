#!/bin/bash
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

