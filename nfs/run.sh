#nfs-server
apt update
apt install -y nfs-kernel-server
mkdir -p /mnt/nvme/nfs_share
chmod 755 /mnt/nvme/nfs_share
cat >> /etc/exports << EOF
/mnt/nvme/nfs_share *(rw,sync,no_root_squash,insecure)
EOF
systemctl restart rpcbind nfs-server
systemctl enable rpcbind nfs-server
systemctl status rpcbind nfs-server
#nfs-client
#apt install -y nfs-common
#mkdir -p /mnt/nfs_share
#mount -t nfs localhost:/mnt/nvme/nfs_share /mnt/nfs_share

