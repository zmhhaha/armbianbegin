apt install memtester
memtester 1G 5  # 测试 1GB 内存，循环 5 次

smartctl -a /dev/sda
smartctl -d emmc -a /dev/mmcblk2
smartctl -d ata -a /dev/mmcblk2
smartctl -d scsi -a /dev/mmcblk2

dmesg | grep -i "error\|warning\|fail\|panic"  # 过滤关键错误信息
journalctl -k --since "1 hour ago"            # 查看最近的内核日志（systemd系统）