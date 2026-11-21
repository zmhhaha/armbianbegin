> 归档说明：这是来源文档快照，原文中的“当前/已完成/待实施”只代表其记录时点。有效规格以映射 OpenSpec 服务为准。
> 来源：`operations/server-resource-audit-20261118/hardware/hardware.md`；正文 SHA-256：`1c89869a79852e9525db825ee2d91a80478c511798b81427a21fa7a2297a7d46`。本副本进行 UTF-8/LF 规范化并重定位文档链接，原件保留。
> [设计档案索引](../../../README.md)

# 五台 ARM 主机资源与底座调查

采样：2026-11-18T12:51:30.917423+00:00（主要资源约 2026-11-18 20:51 CST）。SSH、proc/sysfs、systemd、Docker、Kubernetes、现有 Ceph CLI 均为只读。没有修改配置、停止服务、启动渲染/压测、安装软件，也没有读取凭据文件或输出环境变量。

## 关键判断

- 五节点均可达且 Kubernetes Ready；CPU 短时采样未满载。34 个逻辑核，约 42.45 GiB RAM。NanoPC 三节点内存余量有限，但主要是 Ceph OSD/MON/MGR/MDS 占用，属于共享存储基础设施。
- 201 系统盘已用 76%、约剩 3.35 GiB，并触发 Ceph MON_DISK_LOW。Ceph OSD 池空间充足与 MON 系统盘偏紧需要分开判断。
- Ceph 当前 HEALTH_WARN，225/225 PG active+clean、3/3 OSD up/in；告警涉及 cephadm 管理面授权、原生 OSD 与 cephadm 管理登记、201 MON 所在盘空间。不能把 cephadm 的 master offline 记录等同于 master 主机宕机。
- master 有三只真正脱离 Kubernetes 的 PPT 开发容器，合计 Docker 当前内存约 153.08 MiB；没有 host published port，但共享 Docker 网络，不能据此认定无调用方。其收益明显小于共享底座，是否下线需结合应用引用判断。
- 五台未发现宿主独立 Gitea/MySQL 实例：相应 systemd 单元均 inactive；可见 gitea/mysqld 进程已映射至 Kubernetes Pod。
- 板载 Mali GPU 存在且驱动可见，但三个现有视频容器未暴露 GPU 设备，已安装 HyperFrames 启动源码指定 SwiftShader。当前视频渲染走软件路径，不能以板载 GPU 存在宣称已经硬加速。

## 节点实测

| 节点 | 型号 | 核 | RAM GiB | 可用 GiB | load 1/5/15 | CPU busy | iowait | 温度 °C |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 192.168.137.101 | Orange Pi 5 Plus | 8 | 15.58 | 6.11 | 5.49/4.02/3.98 | 24.81% | 0.26% | 58.23–62.85 |
| 192.168.137.201 | FriendlyElec NanoPC-T4 | 6 | 3.76 | 0.51 | 0.93/1.05/0.96 | 15.37% | 1.01% | 33.33–35.62 |
| 192.168.137.202 | FriendlyElec NanoPC-T4 | 6 | 3.76 | 0.89 | 0.74/1.08/1.07 | 11.51% | 1.18% | 33.89–36.25 |
| 192.168.137.203 | FriendlyElec NanoPC-T4 | 6 | 3.76 | 1.07 | 0.63/0.85/0.90 | 6.21% | 1.01% | 33.89–35.62 |
| 192.168.137.211 | RK3588 OPi 5 Max | 8 | 15.58 | 2.67 | 1.29/1.52/1.88 | 24.36% | 0.9% | 45.31–48.08 |

全部 SwapTotal=0。lsblk 中出现 zram 设备并不等于启用了 swap。memory PSI avg10 很低或为 0；不能从 MemAvailable 较低直接推断已发生严重持续抖动。CPU busy/iowait 是约 1 秒快照，load 是 1/5/15 分钟负载；两者不等同，也不代表长期峰值。

## 主机磁盘和 Ceph/PVC 边界

| 节点 | root | 总 GiB | 已用 GiB | 可用 GiB | df占用 |
| --- | --- | --- | --- | --- | --- |
| 192.168.137.101 | /dev/mmcblk0p1 | 227.06 | 131.76 | 92.96 | 59% |
| 192.168.137.201 | /dev/mmcblk2p1 | 14.13 | 10.6 | 3.35 | 76% |
| 192.168.137.202 | /dev/mmcblk2p1 | 14.13 | 8.23 | 5.73 | 59% |
| 192.168.137.203 | /dev/mmcblk2p1 | 14.13 | 8.1 | 5.86 | 59% |
| 192.168.137.211 | /dev/mmcblk0p1 | 227.05 | 62.22 | 162.49 | 28% |

| 节点 | 物理设备 | 型号 | 容量 GiB |
| --- | --- | --- | --- |
| 192.168.137.101 | mmcblk0 | eMMC/未提供型号 | 232.96 |
| 192.168.137.201 | mmcblk2 | eMMC/未提供型号 | 14.56 |
| 192.168.137.201 | nvme0n1 | NX-256 2280 | 238.47 |
| 192.168.137.202 | mmcblk2 | eMMC/未提供型号 | 14.56 |
| 192.168.137.202 | nvme0n1 | NX-256 2280 | 238.47 |
| 192.168.137.203 | mmcblk2 | eMMC/未提供型号 | 14.56 |
| 192.168.137.203 | nvme0n1 | NX-256 2280 | 238.47 |
| 192.168.137.211 | mmcblk0 | eMMC/未提供型号 | 232.96 |

可见物理 eMMC/NVMe 容量合计 1225.03 GiB。三个 NanoPC 的 NVMe 各约 238.47 GiB，其中约 93.13 GiB 的 p1 为 ext4、采样时未挂载；约 145.34 GiB 的 p2 属于 Ceph LVM/BlueStore。未挂载不等于可删除、空闲或没有数据。

五个系统 root 文件系统已用合计 220.91 GiB。Ceph 独立 OSD 原始总量 436.02 GiB、已用 27.56 GiB（6.32%）、原始可用 408.46 GiB。此处只统计这两组互不重叠的存储；不声称已覆盖未挂载分区中的实际用量。

Ceph 全部 8 个池均复制 size=3、min_size=2。逻辑数据约 9.80 GiB；pool 的 maximum available 约 128.75 GiB，业务可写量不能直接使用 raw free 408.46 GiB。各节点 df 中的 RBD/PVC/CephFS 是这套存储的逻辑映射，不能再与物理盘、OSD 原始容量相加。Docker 镜像/层、root 文件系统和容器路径也可能重叠，禁止重复加总。

限时目录元数据调查仅涉及 /var/log、/var/cache、/root/video-releases，每目录最多 5 秒；未遍历业务媒体目录或整个 /var/lib。master /root/video-releases 约 3.68 GiB、/var/cache 约 321 MiB，均未删除。

## Ceph 运行布局与告警

| 角色 | 节点 | 监听/作用 |
| --- | --- | --- |
| MON | 101 / 201 / 202 / 203 / 211 | 3300、6789；5 MON quorum齐 |
| OSD.0 / OSD.1 / OSD.2 | 201 / 202 / 203 | 6800–6807；3 OSD up/in |
| MDS | 201 | 6808/6809；1 active，无 standby |
| RGW | 201、211 | 7481 |
| RGW HAProxy/keepalived | 201、202 | VIP 192.168.137.111:7480；stats 1967 |
| MGR | 101、201 | 101 dashboard8443、metrics9283等；以监听证据为准 |
| 监控 | 101 | Grafana3000、Prometheus9095、Alertmanager9093/9094 |

| 告警 | 实际证据 | 含义 |
| --- | --- | --- |
| CEPHADM_HOST_CHECK_FAILED | cephadm连接master失败：Permission denied；本次SSH成功、K8sReady、现有daemon运行 | 管理面授权异常，不能认定主机离线 |
| CEPHADM_STRAY_DAEMON | 3个OSD运行于原生ceph-osd@0/1/2.service | 尚未统一纳入cephadm管理；不代表OSD多余或死掉 |
| MON_DISK_LOW | 201 MON可用空间约23% | MON所在系统盘偏紧，与OSD池6.32%占用无冲突 |

## 独立 Docker 与 Kubernetes

全部节点 Kubernetes 通过 Docker/cri-dockerd 运行。docker ps/system df 中大部分容器属于 Kubernetes；不得把 Docker 总容器数再算成另一套业务。非 K8s 容器以无 io.kubernetes.pod.name 标签及容器名/PID核实。Ceph 自身有 systemd/cephadm 管理的 Docker 容器，属于存储底座。

| 节点 | 镜像 total/active | 镜像占用 | Docker估算可回收 | 容器total/running |
| --- | --- | --- | --- | --- |
| 101 | 397/111 | 42.09 GB | 1.355 GB (3%) | 319/174 |
| 201 | 10/10 | 4.047 GB | 0 | 34/21 |
| 202 | 14/14 | 4.35 GB | 0 | 47/26 |
| 203 | 11/11 | 4.226 GB | 0 | 35/22 |
| 211 | 385/60 | 52.84 GB | 21.88 GB (41%) | 276/156 |

可回收量为 Docker 自身估算，不构成安全删除承诺；本次未执行清理。master首轮 system df 10秒超时，后续18秒限时重查成功；两个结果均有证据。

| 节点 | 独立业务容器 | Docker当前内存 | CPU | 监听/引用证据 |
| --- | --- | --- | --- | --- |
| 101 | ppt-service-materials-dev-20261022 | 43.55 MiB | 0.63% | 容器8000，无host发布；172.18.0.4同开发网络 |
| 101 | ppt-service-webdev-api-20261021 | 63.14 MiB | 0.35% | 容器8000，无host发布；172.18.0.3同开发网络 |
| 101 | ppt-service-webdev-db-20261021 | 46.39 MiB | 0.26% | 容器5432，无host发布；172.18.0.2同开发网络 |
| 101 | registry | 60.85 MiB | 0.00% | host5000；镜像分发底座 |

三只 PPT 容器进程RSS合计分别为48.14、66.96、81.75 MiB；Postgres多进程RSS包含共享页，不能与Docker当前内存口径直接相加。三只 PPT 容器均位于 ppt-service-webdev-20261021 Docker 网络。Postgres存在多个后端进程；本次未读取连接用户名/SQL/连接配置，无法仅凭PID归因具体调用方，也未核实是否另有外部调用。它们没有K8s Pod标签；已与正式K8s PPT部署区分。

## GPU / NPU：硬件、驱动、暴露、使用分开

| 层次 | 101/211 | 201/202/203 |
| --- | --- | --- |
| 板载硬件/宿主驱动 | gpuinfo=Mali-G610 4 cores r0p0；mali driver；RKNPU driver v0.9.8 | GPU设备绑定panfrost；具体GPU型号本次未实测 |
| 设备节点 | /dev/dri/card0/card1/renderD128/renderD129、/dev/mali0 | /dev/dri/card0/card1/renderD128 |
| 宿主瞬时GPU观测 | GPU devfreq 0@300MHz；bounded全/proc FD扫描未见GPU用户 | 未见GPU FD用户；不推断硬件不存在 |
| NPU实际使用者 | 211 speech-service Python PID1836788持有card1，driver=RKNPU；申请panghuer.top/rknpu:1 | 未发现NPU节点/驱动 |
| NPU采样 | debug各核load0%、poweroff；devfreq100@1GHz与debug不一致，不作为100%利用率证据 | 未验证 |

视频现有 creation-executor（101）、motion executor（211）、workbench（211）容器均 privileged=false；内部看不到 /dev/dri、mali、rknpu。采样时未有 Chromium/headless进程，未新建GPU上下文。只读核实三个容器已安装源码：

| 源文件 | 已安装启动参数/路径 |
| --- | --- |
| hyperframes_film_browser.mjs | --use-gl=angle、--use-angle=swiftshader、--enable-unsafe-swiftshader |
| engine_runtime.mjs / engine_observe.mjs | WebGL分支SwiftShader；非WebGL分支--disable-gpu |
| observe.mjs | --disable-gpu |

SwiftShader 是 CPU 软件实现；这些事实支持当前配置的软件渲染结论，不能据此推断换硬件驱动后一定更快，或未跑的每一种历史任务实际GPU利用率。Speech NPU 的 request、FD 与驱动证明资源已接入，不能证明采样时正在持续推理。

## 主机 Gitea/MySQL 核实

| 节点 | 进程 | PID | RSS MiB | 实际Pod |
| --- | --- | --- | --- | --- |
| 192.168.137.101 | gitea | 16997 | 265.12 | gitops/gitea-0 |
| 192.168.137.211 | mysqld | 7307 | 665.37 | oauth/mysql-0 |

全五台的 gitea.service/mysql.service/mysqld.service/mariadb.service均inactive。没有发现独立宿主Gitea/MySQL进程。历史文档中的宿主部署信息不作为当前运行事实。

## systemd 与监听清单

下表只关联 MainPID 或监听进程 cgroup 能直接匹配的 unit。Ceph systemd unit 的 MainPID 可能是容器包装进程，监听应结合独立容器表，不把 unit MemoryCurrent 与 daemon RSS相加。无直接监听不等于无服务依赖。

| 节点 | 运行systemd unit | 直接关联监听协议:端口 |
| --- | --- | --- |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@alertmanager.arm-cluster-master.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@ceph-exporter.arm-cluster-master.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@crash.arm-cluster-master.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@grafana.arm-cluster-master.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@mgr.arm-cluster-master.nkzkbr.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@mon.arm-cluster-master.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@node-exporter.arm-cluster-master.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@prometheus.arm-cluster-master.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | ceph-crash.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | chrony.service | udp:323 |
| 192.168.137.101 | containerd.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | cri-dockerd.service | tcp:34719 |
| 192.168.137.101 | cron.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | dbus.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | docker.service | tcp:5000 |
| 192.168.137.101 | getty@tty1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | kubelet.service | tcp:10248, tcp:10250 |
| 192.168.137.101 | polkit.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | rsyslog.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | serial-getty@ttyFIQ0.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | ssh.service | tcp:22 |
| 192.168.137.101 | systemd-journald.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | systemd-logind.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | systemd-networkd.service | udp:546 |
| 192.168.137.101 | systemd-resolved.service | tcp:53, tcp:5355, udp:53, udp:5355 |
| 192.168.137.101 | systemd-udevd.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | user@0.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | wpa_supplicant.service | 未发现直接监听；容器另见下表 |
| 192.168.137.101 | zerotier-one.service | tcp:9993, udp:31464, udp:41215, udp:9993 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@ceph-exporter.nanopct4-server1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@crash.nanopct4-server1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@haproxy.rgw.s3.nanopct4-server1.xfngcc.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@keepalived.rgw.s3.nanopct4-server1.ukmqor.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@mds.cephfs.nanopct4-server1.meywzp.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@mgr.nanopct4-server1.vqstso.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@mon.nanopct4-server1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@node-exporter.nanopct4-server1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@rgw.s3.nanopct4-server1.lzgmgj.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | ceph-crash.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | ceph-osd@0.service | tcp:6800, tcp:6801, tcp:6802, tcp:6803, tcp:6804, tcp:6805, tcp:6806, tcp:6807 |
| 192.168.137.201 | chrony.service | udp:323 |
| 192.168.137.201 | containerd.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | cri-dockerd.service | tcp:38965 |
| 192.168.137.201 | cron.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | dbus.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | docker.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | getty@tty1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | kubelet.service | tcp:10248, tcp:10250 |
| 192.168.137.201 | rsyslog.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | serial-getty@ttyS2.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | smartmontools.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | ssh.service | tcp:22 |
| 192.168.137.201 | systemd-journald.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | systemd-logind.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | systemd-networkd.service | udp:546 |
| 192.168.137.201 | systemd-resolved.service | tcp:53, tcp:5355, udp:53, udp:5355 |
| 192.168.137.201 | systemd-udevd.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | user@0.service | 未发现直接监听；容器另见下表 |
| 192.168.137.201 | wpa_supplicant.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@ceph-exporter.nanopct4-server2.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@crash.nanopct4-server2.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@haproxy.rgw.s3.nanopct4-server2.bkuhfq.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@keepalived.rgw.s3.nanopct4-server2.smwwuh.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@mon.nanopct4-server2.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@node-exporter.nanopct4-server2.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | ceph-crash.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | ceph-osd@1.service | tcp:6800, tcp:6801, tcp:6802, tcp:6803, tcp:6804, tcp:6805, tcp:6806, tcp:6807 |
| 192.168.137.202 | chrony.service | udp:323 |
| 192.168.137.202 | containerd.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | cri-dockerd.service | tcp:33601 |
| 192.168.137.202 | cron.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | dbus.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | docker.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | getty@tty1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | kubelet.service | tcp:10248, tcp:10250 |
| 192.168.137.202 | rsyslog.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | serial-getty@ttyS2.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | smartmontools.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | ssh.service | tcp:22 |
| 192.168.137.202 | systemd-journald.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | systemd-logind.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | systemd-networkd.service | udp:546 |
| 192.168.137.202 | systemd-resolved.service | tcp:53, tcp:5355, udp:53, udp:5355 |
| 192.168.137.202 | systemd-udevd.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | user@0.service | 未发现直接监听；容器另见下表 |
| 192.168.137.202 | wpa_supplicant.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@ceph-exporter.nanopct4-server3.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@crash.nanopct4-server3.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@mon.nanopct4-server3.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@node-exporter.nanopct4-server3.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | ceph-crash.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | ceph-osd@2.service | tcp:6800, tcp:6801, tcp:6802, tcp:6803, tcp:6804, tcp:6805, tcp:6806, tcp:6807 |
| 192.168.137.203 | chrony.service | udp:323 |
| 192.168.137.203 | containerd.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | cri-dockerd.service | tcp:43333 |
| 192.168.137.203 | cron.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | dbus.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | docker.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | getty@tty1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | kubelet.service | tcp:10248, tcp:10250 |
| 192.168.137.203 | rsyslog.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | serial-getty@ttyS2.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | smartmontools.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | ssh.service | tcp:22 |
| 192.168.137.203 | systemd-journald.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | systemd-logind.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | systemd-networkd.service | udp:546 |
| 192.168.137.203 | systemd-resolved.service | tcp:53, tcp:5355, udp:53, udp:5355 |
| 192.168.137.203 | systemd-udevd.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | user@0.service | 未发现直接监听；容器另见下表 |
| 192.168.137.203 | wpa_supplicant.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@ceph-exporter.orangepi5-max-server1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@crash.orangepi5-max-server1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@mon.orangepi5-max-server1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@node-exporter.orangepi5-max-server1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a@rgw.s3.orangepi5-max-server1.oetpvm.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | ceph-crash.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | chrony.service | udp:323 |
| 192.168.137.211 | containerd.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | cri-dockerd.service | tcp:33619 |
| 192.168.137.211 | cron.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | dbus.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | docker.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | getty@tty1.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | kubelet.service | tcp:10248, tcp:10250 |
| 192.168.137.211 | rsyslog.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | serial-getty@ttyFIQ0.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | ssh.service | tcp:22 |
| 192.168.137.211 | systemd-journald.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | systemd-logind.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | systemd-networkd.service | udp:546 |
| 192.168.137.211 | systemd-resolved.service | tcp:53, tcp:5355, udp:53, udp:5355 |
| 192.168.137.211 | systemd-udevd.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | user@0.service | 未发现直接监听；容器另见下表 |
| 192.168.137.211 | wpa_supplicant.service | 未发现直接监听；容器另见下表 |

非 Kubernetes 容器监听（仅当前观察到的host端口；未对内部容器网络发起探测）：

| 节点 | 容器 | host网络 | 实际观察监听 |
| --- | --- | --- | --- |
| 192.168.137.101 | ppt-service-materials-dev-20261022 | False | 无host监听关联 |
| 192.168.137.101 | ppt-service-webdev-api-20261021 | False | 无host监听关联 |
| 192.168.137.101 | ppt-service-webdev-db-20261021 | False | 无host监听关联 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-alertmanager-arm-cluster-master | True | tcp:9093, tcp:9094, udp:9094 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-crash-arm-cluster-master | True | 无host监听关联 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-grafana-arm-cluster-master | True | tcp:3000 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-mon-arm-cluster-master | True | tcp:3300, tcp:6789 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-prometheus-arm-cluster-master | True | tcp:9095 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-ceph-exporter-arm-cluster-master | True | tcp:9926 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-mgr-arm-cluster-master-nkzkbr | True | tcp:6800, tcp:6801, tcp:7150, tcp:8443, tcp:8765, tcp:9283 |
| 192.168.137.101 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-node-exporter-arm-cluster-master | True | tcp:9100 |
| 192.168.137.101 | registry | False | 无host监听关联 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-haproxy-rgw-s3-nanopct4-server1-xfngcc | True | tcp:1967, tcp:7480, udp:39265 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-crash-nanopct4-server1 | True | 无host监听关联 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-mgr-nanopct4-server1-vqstso | True | tcp:8443, tcp:9283 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-keepalived-rgw-s3-nanopct4-server1-ukmqor | True | 无host监听关联 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-ceph-exporter-nanopct4-server1 | True | tcp:9926 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-mds-cephfs-nanopct4-server1-meywzp | True | tcp:6808, tcp:6809 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-mon-nanopct4-server1 | True | tcp:3300, tcp:6789 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-node-exporter-nanopct4-server1 | True | tcp:9100 |
| 192.168.137.201 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-rgw-s3-nanopct4-server1-lzgmgj | True | tcp:7481 |
| 192.168.137.202 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-keepalived-rgw-s3-nanopct4-server2-smwwuh | True | 无host监听关联 |
| 192.168.137.202 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-ceph-exporter-nanopct4-server2 | True | tcp:9926 |
| 192.168.137.202 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-mon-nanopct4-server2 | True | tcp:3300, tcp:6789 |
| 192.168.137.202 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-node-exporter-nanopct4-server2 | True | tcp:9100 |
| 192.168.137.202 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-crash-nanopct4-server2 | True | 无host监听关联 |
| 192.168.137.202 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-haproxy-rgw-s3-nanopct4-server2-bkuhfq | True | tcp:1967, tcp:7480, udp:37795, udp:52898 |
| 192.168.137.203 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-node-exporter-nanopct4-server3 | True | tcp:9100 |
| 192.168.137.203 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-ceph-exporter-nanopct4-server3 | True | tcp:9926 |
| 192.168.137.203 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-crash-nanopct4-server3 | True | 无host监听关联 |
| 192.168.137.203 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-mon-nanopct4-server3 | True | tcp:3300, tcp:6789 |
| 192.168.137.211 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-ceph-exporter-orangepi5-max-server1 | True | tcp:9926 |
| 192.168.137.211 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-rgw-s3-orangepi5-max-server1-oetpvm | True | tcp:7481 |
| 192.168.137.211 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-crash-orangepi5-max-server1 | True | 无host监听关联 |
| 192.168.137.211 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-node-exporter-orangepi5-max-server1 | True | tcp:9100 |
| 192.168.137.211 | ceph-3a4899f0-7689-11f1-90a0-c0742bfe683a-mon-orangepi5-max-server1 | True | tcp:3300, tcp:6789 |

完整监听地址、PID、comm、cgroup见 hardware-summary.json 的 observed_listeners；没有保存完整启动命令或容器环境。

## 定时器与失败单元

五节点运行的 timer 集合均为 apt-daily、apt-daily-upgrade、dpkg-db-backup、e2scrub_all、fstrim、logrotate、man-db、systemd-tmpfiles-clean，未发现业务定时器。失败单元保留如下，仅代表该unit最近状态，历史oneshot失败不能直接等同当前业务故障：

- 192.168.137.101：logrotate.service; smartmontools.service; speech-plugin-mirror-20261031.service; speech-plugin-mirror-daocloud-20261031.service; speech-plugin-mirror-direct-20261031.service; speech-plugin-mirror-proxy-20261031.service; systemd-update-utmp.service; video-workbench-arm-media-validation-20261031.service; video-workbench-audio-live-20261031.service; video-workbench-audio-live-r2-20261031.service; video-workbench-audio-live-r3-20261031.service; video-workbench-media-base-20261031.service; video-workbench-media-base-r2-20261031.service
- 192.168.137.201：logrotate.service
- 192.168.137.202：logrotate.service
- 192.168.137.203：logrotate.service
- 192.168.137.211：ap6611s-bluetooth.service; logrotate.service; smartmontools.service; speech-image-build-20261031.service; speech-image-planner-build-20261031.service

## 数据与测量边界

- 请求量、limits、allocatable是调度/约束信息，不当作实际CPU/RAM使用。docker stats为容器内存口径，进程RSS会重复计算共享页；二者不能直接相加。
- 本次只做短时观测，没有峰值、P95或长期趋势保证，没有GPU benchmark，没有测试渲染，也未打开GPU计算上下文。
- 不遍历业务媒体树、不扫描凭据文件、不输出环境变量或完整进程命令；Ceph health自动附带的SSH长日志已截断为失败摘要，URL仅保留host。
- hardware.json/node-*.json 是宿主原始白名单证据；followup.json 是端口/独立容器/Ceph/设备证据；final-checks.json 是进程Pod归属、已安装渲染flags与复制参数复核；hardware-summary.json提供可整合结构化数据。
