# Soft-RoCE / DPDK / SPDK 真实硬件实验清单

> 面向本仓库实际拥有的两台"机器"：**Windows 主机（i7-4770 + RTX 2070S）** 与 **5 节点 Armbian 集群（Orange Pi 5 Plus / 5 Max / 3× NanoPC-T4）**。
> 文中所有"实测"数据均为 2026-10 在本机与集群上真机采集，采集命令见 [§10](#10-附本次实测原始数据与采集命令)。
> 目标不是"读完就懂"，而是**照着做能跑出数字**，每一步都有验收标准和失败分支。

---

## 0. 先看现实：能力矩阵（实测，不是推测）

### 0.1 结论速查

| 技术 | 现在能直接跑吗 | 在哪跑 | 缺什么 |
|---|---|---|---|
| **Soft-RoCE（rxe）** | ❌ 5 台 Armbian 全部不行 | x86 上的 Linux 虚拟机（Debian/Ubuntu 发行版内核自带） | Armbian 内核 `CONFIG_INFINIBAND` 未开；WSL 内置内核也没有 RDMA |
| **RDMA 用户态编程（Verbs/perftest）** | ✅ 有 rxe 设备后即可 | 同上 | 同上 |
| **DPDK（软件 PMD：af_packet/tap/pcap/ring）** | ✅ 现在就能跑 | 任意 Armbian 节点、WSL Debian、实验 VM | 只需 `apt install dpdk`（22.11.11 在仓库里） |
| **DPDK（poll-mode 网卡直通）** | ❌ 集群网卡没有 PMD | 实验 VM 内的 virtio-net / vmxnet3 | r8169 / rk_gmac-dwmac / brcmfmac 都无 DPDK PMD |
| **SPDK（编译 + 软件后端 + NVMe-oF TCP）** | ✅ 现在就能跑 | Armbian 节点或实验 VM | 源码构建（Debian 没有 spdk 包） |
| **SPDK（用户态 NVMe 直通）** | ⚠️ 需要一块**空闲** NVMe | Orange Pi 5 Max/Plus 的 M.2 槽（当前是空的） | 集群里的 NVMe 全归 Ceph，绝不能碰 |
| **NVMe-oF over RoCE（SPDK target + 内核 initiator）** | ⚠️ 依赖 rxe 先跑通 | 两台实验 VM | 同上（最有价值的"组合实验"） |
| **GPUDirect RDMA** | ❌ | — | GeForce 驱动不给 `ThirdPartyP2P`，与本次清单无关 |

### 0.2 实测硬件清单

**Windows 主机（192.168.137.191）**

| 项目 | 实测值 |
|---|---|
| OS | Windows 10 **Enterprise** 22H2，build 19045.6456 |
| CPU / 内存 | i7-4770 4 核 8 线程 / 16 GB |
| 磁盘空闲 | C: 232G 总 **仅 10G 空闲**；D: 466G 总 **315G 空闲**；G: 238G 总 41G 空闲 |
| 网卡 | Realtek PCIe GBE（就是给集群做 ICS 共享上网的那张）+ ZeroTier 虚拟口 (10.147.18.129) |
| 虚拟化 | **Hyper-V 角色未启用**（`vmms.exe` 不存在；`vmcompute` 服务在，那是 WSL/容器组件）。无 VirtualBox / VMware |
| WSL | 已安装 **Debian** 发行版（`TheDebianProject.DebianGNULinux_76v4gfsz19hv4`）；用的是 2021-04-13 的内置 WSL 内核（70 MB），二进制里搜不到 `rdma_rxe` / `ib_core` / `uverbs` → **无 RDMA**（`.wslconfig` 不存在） |
| 其他 | 沙箱会话里 `wsl.exe`、`Get-CimInstance` 被拒绝访问，属环境限制，不影响你手动操作 |

**Armbian 集群（192.168.137.0/24，网关 .1 = Windows ICS）**

| 主机 | IP | 板子 | 内核 | CPU / 内存 | 网卡 | 存储 |
|---|---|---|---|---|---|---|
| arm-cluster-master | .101 | Orange Pi 5 Plus | 6.1.115-**vendor**-rk35xx | 8C / 15.5G（闲 9.5G） | `enP4p65s0` r8169 2.5G（链路 1G）、**`enP3p49s0` 空闲未接**、`wlP2p33s0` rtw89 | eMMC 233G |
| orangepi5-max-server1 | .211 | Orange Pi 5 Max | 6.1.115-**vendor**-rk35xx | 8C / 15.5G（闲 7.5G） | `enP3p49s0` r8169 2.5G（链路 1G） | eMMC 233G，**M.2 槽空** |
| nanopct4-server1/2/3 | .201/.202/.203 | NanoPC-T4 (RK3399) | 6.18.35-**current**-rockchip64（mainline） | 6C / 3.85G（闲 0.6–2.0G） | `eth0` rk_gmac-dwmac 1G、`wlan0` brcmfmac | eMMC 14.6G + **NVMe 238.5G（Maxio MAP1202）** |

Master 与 OPi5 Max 的 PCI 总线上只有 `pcieport` + RTL8125，**没有任何 NVMe** → 两台的 M.2 M-key 槽是空的，可以加盘。

### 0.3 五台机器共同的"短板"（实测）

```text
# CONFIG_INFINIBAND is not set          ← vendor 6.1.115 与 mainline 6.18.35 都是
modinfo rdma_rxe → Module rdma_rxe not found
ls /sys/class/infiniband → No such file or directory
# 用户态库却在（装了也没设备）：
libibverbs1:arm64  44.0-2
librdmacm1:arm64   44.0-2
```

好消息（决定了下面大部分实验**现在就能做**）：

| 能力 | 实测 |
|---|---|
| 外网 / apt 源 | ✅ `deb.debian.org`、tuna 镜像均 HTTP 200 |
| DPDK 包 | ✅ `dpdk` / `dpdk-dev` = 22.11.11-0+deb12u1 |
| RDMA 用户态包 | ✅ `rdma-core` 44.0-2、`ibverbs-utils`、`libibverbs-dev`、`perftest` 4.5 |
| 大页 | ✅ `hugepages-{2048,32768,65536,1048576}kB` 目录齐全；`/dev/hugepages` 已挂载（RK3588 上 `pagesize=2M`）；当前分配数 0 |
| SPDK 构建依赖 | ✅ `build-essential` `meson` `ninja-build` `pkg-config` `libnuma-dev` `libssl-dev` `libaio-dev` `liburing-dev` `uuid-dev` `libcunit1-dev` `nasm` `libfabric` 1.17 `fio` 3.33 `nvme-cli` 2.4 |
| SPDK 包 | ❌ Debian 仓库**没有** `spdk`，必须源码构建 |
| 设备直通 | OPi5 Max：18 个 IOMMU group，`vfio-pci` 可用，`uio_pci_generic` 模块在（=m）；NanoPC（mainline）：`vfio-pci` 可用，但 `uio_pci_generic` **未编译** |
| 编译器 | RK3588 节点有 gcc 12.2 / make / python3，**缺 git、meson、ninja、pkg-config**；NanoPC 连 gcc 都没有（`apt install build-essential`） |

### 0.4 红线（先读，别踩）

1. **绝不在集群节点上执行 `spdk/scripts/setup.sh` 或 `dpdk-devbind.py -b vfio-pci`**。三台 NanoPC 的 NVMe 是 Ceph OSD 所在，`setup.sh` 默认会把 NVMe 从内核解绑 → OSD 掉 → k8s 存储层连带崩。只跑 `scripts/setup.sh status` 这类只读子命令。
2. **不要在 3 台 NanoPC（3.85G / 空闲 0.6–2.0G）上分配大页**。要测大页只在 OPi5（闲 7.5–9.5G）上临时分配，测完 `echo 0 > /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages` 归还。
3. **不要在 master 的 `enP4p65s0` 上做 DPDK af_packet 抓包/绑定实验**——那是集群与 ICS 上网的命脉。master 有个空闲口 `enP3p49s0` 可以用。
4. **Windows 上不要把 Hyper-V 外部虚拟交换机绑到那张给集群做 ICS 的 Realtek 网卡**。ICS + Hyper-V External Switch 会重排主机网络，最坏情况是全集群断网。实验台用 **Internal Switch**（见 §2.1）。
5. 内核/驱动级改动**一次只动一台**，并且留好回滚（见 §4.4）。

---

## 1. 三条路线（按性价比排序）

| 路线 | 需要新增硬件 | 耗时 | 风险 | 能学到 / 拿到什么 |
|---|---|---|---|---|
| **A. x86 双 VM 实验台**（推荐起点） | 无 | 半天 | 低（与集群完全隔离） | Soft-RoCE 全功能、perftest 数字、DPDK virtio、SPDK 全套、NVMe-oF over RoCE |
| **B. WSL2 单机**（顺手热身） | 无 | 1–2 小时 | 极低 | DPDK `--no-huge` 全套软件 PMD；可选自编 WSL 内核上 rxe |
| **C. 给 Armbian 内核加 IB/RXE 后重编** | 无 | 1–2 天 | **高**（集群节点换内核） | 真正跨板 RDMA，在自有硬件上跑出 rxe 数字 |
| **D. 硬件升级**（可选） | ¥120–400 | 半天 | 中 | SPDK 真 NVMe 路径；真硬件 RoCE；为 GPUDirect 铺路 |

**建议顺序：B（1 小时内见效）→ A（主战场）→ A 上的组合实验 → C → 按需 D。**

---

## 2. 路线 A：x86 双 VM 实验台（主战场）

### 2.1 建网 —— 关键是"内网交换机"，别碰 ICS

```powershell
# 管理员 PowerShell。启用 Hyper-V（Win10 Enterprise 支持）
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All
# 重启

# 关键：把虚拟机和虚拟磁盘默认路径挪到 D:（C: 只剩 10G，放不下 VM 磁盘）
Set-VMHost -VirtualMachinePath D:\vms -VirtualHardDiskPath D:\vms

# 只建【内部】交换机：两个 VM 之间 L2 互通，且完全不影响生产网
New-VMSwitch -Name RDMALab -SwitchType Internal

# 两块盘，各 2 vCPU / 3 GB（i7-4770 共 4C8T / 16G，留 10G 给宿主）
New-VM -Name rdma-a -MemoryStartupBytes 3GB -Generation 2 `
        -NewVHDPath D:\vms\rdma-a.vhdx -NewVHDSizeBytes 40GB -SwitchName RDMALab
New-VM -Name rdma-b -MemoryStartupBytes 3GB -Generation 2 `
        -NewVHDPath D:\vms\rdma-b.vhdx -NewVHDSizeBytes 40GB -SwitchName RDMALab
# 关掉动态内存、固定 2 vCPU，方便后面测延迟时不被抢
Set-VMProcessor rdma-a -Count 2; Set-VMProcessor rdma-b -Count 2
Set-VMMemory rdma-a -DynamicMemoryEnabled $false
Set-VMMemory rdma-b -DynamicMemoryEnabled $false
# 挂 Debian 12 netinst ISO 并安装（网络选 host 上的 vEthernet(RDMALab)，无需上网代理时够用；
# 需要 apt 装包的话，给 VM 加第二张网卡或用 Default Switch）
Add-VMDvdDrive rdma-a -Path D:\iso\debian-12-netinst-amd64.iso
```

**验收**：两台 VM 起来后互相 `ping` 通，`ip -br link` 能看到 vNIC，且 Windows 主机上 `Get-NetIPAddress -InterfaceAlias "vEthernet (RDMALab)"` 正常，`ping 192.168.137.101` 仍然通（说明集群没被影响）。

> 失败分支：若 rxe 在 Hyper-V 的 `hv_netvsc` 网卡上不工作（`rdma link add` 报错或没有流量），退到 **VirtualBox 7**（Linux 客户机可选 `virtio-net` 或 `Intel PRO/1000`）或 **VMware Workstation**（`vmxnet3`）。后者还顺带给 DPDK 一个真实的 `net_vmxnet3` PMD。
> 另一条更省事的观察点：Hyper-V 的 "Default Switch"（NAT）也能让两 VM 互通，但网段每次重启会变，做对照实验时不如 Internal 稳定。

### 2.2 装 RDMA 用户态 + 拉起 Soft-RoCE（两台 VM 都做）

```bash
sudo apt update
sudo apt install -y rdma-core ibverbs-utils perftest iproute2

modinfo rdma_rxe            # ← 发行版内核一般自带；若 not found，走 §3 的自定义内核
sudo modprobe rdma_rxe
ip -br addr                 # 记下实验网卡名（下面是 ens3 / eth0 之类）
sudo rdma link add rxe0 type rxe netdev ens3
rdma link show              # 期望：link rxe0/1 state ACTIVE  physical_state ACTIVE
ibv_devices                 # 期望：rxe0
ibv_devinfo -d rxe0         # 期望：port 1 state PORT_ACTIVE, link_layer Ethernet
```

**验收**：`ibv_devinfo -d rxe0` 里 `PORT_ACTIVE` + `max_mtu: 4096`。若 `rdma link add` 报 `Operation not supported`，90% 是内核没开 `CONFIG_RDMA_RXE`。

### 2.3 基线性能数字（**记录下来，这是你后面所有对比的参照物**）

```bash
# VM-A（服务端）
ib_send_bw -d rxe0 -F --report_gbits

# VM-B（客户端；把 A 的 IP 填进去）
ib_send_bw -d rxe0 -F --report_gbits 10.0.0.1
```

建议按这张表跑一遍，把结果填进去（rxe 是纯 CPU 软件实现，i7-4770 上单流大致在 **3–6 Gbps / 写延迟 20–40 µs** 量级，具体看实测）：

| 实验 | 命令（客户端加服务端 IP） | 关注 | 实测值 |
|---|---|---|---|
| 带宽 | `ib_send_bw -d rxe0 -F --report_gbits` | BW peak / avg | |
| 带宽（大包） | `ib_write_bw -d rxe0 -F -s 65536 --report_gbits` | 是否随包长上升 | |
| 带宽（小包） | `ib_write_bw -d rxe0 -F -s 64` | 小包能否打满 | |
| 延迟 | `ib_write_lat -d rxe0 -F` | t_avg / t_max | |
| 延迟（小包） | `ib_send_lat -d rxe0 -F -s 64` | 与 write_lat 对比 | |
| 多队列 | 服务端 `-q 4` 客户端 `-q 4` | 多 QP 是否线性 | |
| 对照（TCP） | `iperf3 -c <IP>` | RDMA vs 内核 TCP | |

**排错清单**：`ibv_devinfo` 看不到端口 → netdev 没 up；`ib_send_bw` 卡住 → 对端 IP/GID 选错（`show_gids`）、或防火墙挡了 UDP 4791（rxe 走 RoCEv2/UDP）；性能个位数 Mbps → CPU 被 VM 抢走（`ethtool -L` 关掉 vNIC offload，或在 `/sys/class/infiniband/rxe0/ports/1/counters` 看丢包）。

> 单机也能做"两个节点"：在**同一个内核**里用 network namespace 造两台"主机"——
> ```bash
> ip netns add a; ip netns add b
> ip link add va type veth peer name vb
> ip link set va netns a; ip link set vb netns b
> ip netns exec a ip addr add 10.10.10.1/24 dev va; ip netns exec a ip link set va up
> ip netns exec b ip addr add 10.10.10.2/24 dev vb; ip netns exec b ip link set vb up
> ip netns exec a rdma link add rxe-a type rxe netdev va
> ip netns exec b rdma link add rxe-b type rxe netdev vb
> ```
> 这条在 VM 里、甚至将来在跑通 rxe 的 Armbian 板上都能用，用来省机器做协议层实验。

### 2.4 往上一层：自己写 Verbs 程序（可选但推荐）

`perftest` 只是黑盒。想真正懂 QP/CQ/MR，用仓库 `github.com/Ljt0721/rdma-basic-tutorial`（中文、最小示例）或 `rdma-core` 自带 examples：

```bash
sudo apt install -y libibverbs-dev librdmacm-dev cmake gcc
git clone https://github.com/linux-rdma/rdma-core && cd rdma-core
# 需要 rdma-core 的 examples（ibv_rc_pingpong / ibv_ud_pingpong / rc_pingpong）
# 若 apt 的 ibverbs-utils 里没有这两个二进制，就从源码编：
#   在源码树里为 examples 建 build 目录编译，或直接对照 examples/*.c 抄一遍
```

**验收**：自己写一个 `ibv_rc_pingpong` 等价物，能打印出 "buffer contents OK" 和一轮时延。

---

## 3. 路线 B：WSL2 单机（1 小时内见效的热身 + 可选 rxe）

WSL Debian 已经装好，`apt install dpdk` 就能做**全套 DPDK 软件 PMD** 实验（WSL 里没有 hugepage，用 `--no-huge` 即可，这是 DPDK 官方支持的调试模式）：

```bash
sudo apt install -y dpdk dpdk-dev
dpdk-testpmd --version

# 1) 纯内存转发（不需要任何网卡）
sudo dpdk-testpmd --no-huge -m 512 --vdev=net_null0 --vdev=net_null1 -- -i --no-mac-updating

# 2) TAP 口 + 内核协议栈互通（最实用的一个）
sudo dpdk-testpmd --no-huge -m 512 --vdev=net_tap0,iface=dtap0 -- -i
# 另一个终端：ip addr add 10.9.9.1/24 dev dtap0; ip link set dtap0 up; ping 10.9.9.2
# testpmd 里：set fwd mac / start / show port stats all

# 3) 真实收发包（走内核 af_packet，不是 bypass，但能看 mbuf/ring/drop 统计）
sudo dpdk-testpmd --no-huge -m 512 --vdev=net_af_packet0,iface=eth0 -- -i
```

**关于 WSL 里的 rxe**：实测这台 WSL 的内置内核（2021-04-13，70 MB）里没有 `rdma_rxe`/`ib_core`/`uverbs` 符号，`modprobe rdma_rxe` 必然失败。要在这里跑 rxe 只有一条路——**自己编一个 WSL 内核**：

```bash
# 在 WSL Debian 内
sudo apt install -y build-essential flex bison libssl-dev libelf-dev bc git
git clone --depth 1 https://github.com/microsoft/WSL2-Linux-Kernel
cd WSL2-Linux-Kernel
cp Microsoft/config-wsl .config
scripts/config --module RDMA_RXE --module INFINIBAND --module INFINIBAND_USER_ACCESS \
               --module INFINIBAND_USER_VERBS --module RDMA_CM --enable INFINIBAND_ADDR_TRANS
make olddefconfig && make -j$(nproc)          # i7-4770 上约 20–40 分钟
sudo make modules_install
cp arch/x86/boot/bzImage /mnt/c/Users/<你>/wsl-rxe-bzImage
```
```ini
# Windows 上新建 %USERPROFILE%\.wslconfig
[wsl2]
kernel=C:\\Users\\<你>\\wsl-rxe-bzImage
```
`wsl --shutdown` 重进，再 `modprobe rdma_rxe && rdma link add rxe0 type rxe netdev eth0`。
**注意**：这条路只有单机（可以配 §2.3 的 netns 双栈），而且以后每次 WSL 升级可能要重编。如果 §2 的 VM 能开，优先用 VM。

---

## 4. 路线 C：把 IB/RXE 编进 Armbian 内核（真实跨板 RDMA）

目标：让板子（先一台、再两三台）出现 `rxe0`，在 1G/2.5G 局域网上跑出真实的跨板 verbs 数字。

### 4.1 需要打开的配置项（最小集合）

```text
CONFIG_INFINIBAND=m
CONFIG_INFINIBAND_USER_MAD=m
CONFIG_INFINIBAND_USER_ACCESS=m      # 会自动带上 USER_VERBS
CONFIG_INFINIBAND_ADDR_TRANS=y
CONFIG_INFINIBAND_ADDR_TRANS_CONFIGFS=y
CONFIG_INFINIBAND_VIRT_DMA=y         # rxe 在新内核走 virt-dma
CONFIG_RDMA_RXE=m
CONFIG_RDMA_CM=m
```
用 `scripts/config` 或 menuconfig 设置后跑一次 `make olddefconfig`（它会自动带上 `ib_umad` / `rdma_ucm` 等依赖项），**务必核对最终 `.config` 里这几项都不再是 `# ... is not set`**：

```bash
grep -E 'INFINIBAND|RDMA_RXE|RDMA_CM' .config | grep -v '^#'   # 应有输出
grep -E 'INFINIBAND|RDMA_RXE|RDMA_CM' .config | grep '^#'     # 应为空
```

### 4.2 两种构建做法

**C-1（推荐）用 Armbian 构建框架，在 x86 上交叉编译出内核 .deb**

```bash
git clone https://github.com/armbian/build && cd build
# 追加配置片段：Armbian 会把 userpatches/linux-<family>-<branch>.config 合并进最终 .config
mkdir -p userpatches
cat > userpatches/linux-rockchip64-current.config <<'EOF'
CONFIG_INFINIBAND=m
CONFIG_INFINIBAND_USER_ACCESS=m
CONFIG_INFINIBAND_ADDR_TRANS=y
CONFIG_RDMA_RXE=m
CONFIG_RDMA_CM=m
CONFIG_INFINIBAND_VIRT_DMA=y
EOF

# NanoPC-T4（mainline，现役 6.18.35-current-rockchip64）
./compile.sh kernel BOARD=nanopct4 BRANCH=current RELEASE=bookworm
# Orange Pi 5 Plus / 5 Max（vendor 6.1.115-vendor-rk35xx）
cp userpatches/linux-rockchip64-current.config userpatches/linux-rockchip64-vendor.config
./compile.sh kernel BOARD=orangepi5-max BRANCH=vendor RELEASE=bookworm
```
产物在 `output/debs/`，拿到 `linux-image-*.deb` / `linux-dtb-*.deb`。

**C-2 在设备上原地编（只建议用 OPi5，8C/16G）**：`apt install build-essential git` + `linux-source-6.1`，用 `/boot/config-$(uname -r)` 作基线改配置后 `make -j8 modules`。NanoPC 只有 3.85G 内存且无 gcc，**不要**在它上面编。

### 4.3 只在一台上先做

```bash
# 在 NanoPC-T4（比如 server3，负载最轻）上
sudo dpkg -i linux-image-*.deb linux-dtb-*.deb   # 注意与 dpkg 版本/依赖匹配
sudo reboot
# 回来后
uname -r && modinfo rdma_rxe | head -3
sudo modprobe rdma_rxe && sudo rdma link add rxe0 type rxe netdev eth0
ibv_devices && ibv_devinfo -d rxe0 | head -20
```
**验收**：`ibv_devinfo` 里 `PORT_ACTIVE`；`ib_send_bw -d rxe0 -F` 自环能出数（rxe 支持同设备回环）。

**预期性能（别期待太高）**：RK3399（A72/A53）CPU 软 RoCE 单流大致 **0.3–1.5 Gbps**、延迟 100 µs 量级；RK3588（A76）大致 **1–3 Gbps**、延迟 50–100 µs。它的价值在于"能跑通协议与代码"，不是性能。

### 4.4 验收、回滚与风险

- **留退路**：Armbian 的 `/boot/extlinux/extlinux.conf` 会保留其他内核条目；改前先 `cp extlinux.conf extlinux.conf.bak`，`apt-mark hold linux-image-*` 防止被自动升级冲掉。
- **集群影响**：换内核 = 节点重启。k8s 会把这台标记 NotReady 并把 Pod 迁走；NanoPC 内存极紧，**迁移期间容易触发 DiskPressure/OOM**（仓库 `docs/calico-migration-run.md` 记过一次连锁故障）。建议一次只重启一台，且避开正在跑批处理的时段。
- **Ceph/CSI**：内核变了，Ceph 内核模块（`rbd`/`ceph`）与 CSI 驱动要跟着对齐；NanoPC 上是宿主进程 + CSI DaemonSet，重启后确认 `ceph -s` 正常、OSD 全部 up 再动下一台。
- **回滚**：`extlinux.conf.bak` 覆盖回来 + 重启，或 `dpkg -i` 旧内核 deb。

### 4.5 跨板实验（两台打通后）

物理链路建议用 **master 的空闲口 `enP3p49s0` 直连**另一台板子（需要给那台配一个 USB3 网卡，见 §8；否则就走现有 1G 交换机）：

```bash
# 两台都做（示例用 master 空闲口 + OPi5 Max 的 USB 网卡）
sudo ip addr add 10.20.20.1/24 dev enP3p49s0 && sudo ip link set enP3p49s0 up   # master
rdma link add rxe0 type rxe netdev enP3p49s0
# 对端
sudo ip addr add 10.20.20.2/24 dev enxXXXXXXXX && sudo ip link set enxXXXXXXXX up
rdma link add rxe0 type rxe netdev enxXXXXXXXX

# 基准：跨板对比单机回环
ib_send_bw -d rxe0 -F --report_gbits                    # 服务端
ib_send_bw -d rxe0 -F --report_gbits 10.20.20.2         # 客户端
```
**验收**：跨板数字与单机回环对比，能看出"网络 + 两端 CPU 软件栈"的开销——这就是 Soft-RoCE 的真实成本。

---

## 5. SPDK 实验（实验 VM 或 OPi5；**不要在集群节点动 NVMe**）

### 5.1 构建（arm64 与 x86 都能编）

```bash
sudo apt install -y git build-essential python3 pkg-config meson ninja-build \
                    libssl-dev libnuma-dev libaio-dev liburing-dev uuid-dev \
                    libcunit1-dev nasm libibverbs-dev librdmacm-dev   # 最后两个为 RDMA transport
git clone --recursive https://github.com/spdk/spdk && cd spdk
./configure --with-rdma            # ← RDMA transport 必须显式打开，默认关
make -j$(nproc)
```
> 实测：OPi5 上 **git / meson / ninja / pkg-config 都没装**，NanoPC 连 gcc 都没有；先按上面补依赖。

### 5.2 大页与运行环境

```bash
# 两个 VM 上可以放心跑完整 setup.sh；Armbian 集群节点只跑只读子命令！
sudo scripts/setup.sh status
# 只分配大页（不碰设备）——现代 SPDK 的 setup.sh 支持子命令：
sudo HUGEMEM=1024 scripts/setup.sh hugepages      # 1 GiB = 512×2M
# 手工等价做法：
echo 512 | sudo tee /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages
grep -i huge /proc/meminfo
```
实测 RK3588 上 `/dev/hugepages` 已按 2M 挂载好，直接分配即可；**测完 `echo 0 > .../nr_hugepages` 归还**，否则会挤压 k8s 节点的可用内存。

### 5.3 纯软件后端：先把 SPDK 编程模型跑通

```bash
sudo build/bin/spdk_tgt &                 # 或 sudo build/bin/spdk_tgt -m 0x3
sudo scripts/rpc.py bdev_malloc_create -b Malloc0 128 4096
sudo scripts/rpc.py bdev_null_create Null0 1024 4096
sudo scripts/rpc.py bdev_aio_create /tmp/disk.img Aio0 4096      # 先 truncate -s 1G /tmp/disk.img
sudo scripts/rpc.py bdev_uring_create /tmp/disk2.img Uring0 4096
sudo scripts/rpc.py bdev_get_bdevs | head -40
```
**验收**：`bdev_get_bdevs` 列出 4 个 bdev；用 SPDK 的 fio plugin（`examples/nvme/fio_plugin`）或 `spdk_bdev_perf` 压一下，对比同盘的内核路径延迟。

### 5.4 NVMe-oF **TCP**（不需要 RDMA，两台 VM 之间就能做）

```bash
# Target（VM-A）
sudo scripts/rpc.py nvmf_create_transport -t TCP -u 8192
sudo scripts/rpc.py nvmf_create_subsystem nqn.2026-10.io.spdk:lab -a -s SPDK00000000000001
sudo scripts/rpc.py nvmf_subsystem_add_ns nqn.2026-10.io.spdk:lab Malloc0
sudo scripts/rpc.py nvmf_subsystem_add_listener nqn.2026-10.io.spdk:lab -t TCP -a 10.0.0.1 -s 4420

# Initiator（VM-B）——用 SPDK 自己当 host
sudo scripts/rpc.py bdev_nvme_attach_controller -b nvme0 -t tcp -a 10.0.0.1 -f ipv4 -s 4420 -n nqn.2026-10.io.spdk:lab
```
**更省事的 Initiator**（用 Linux 内核的 nvme-tcp，连 SPDK target）：
```bash
sudo apt install -y nvme-cli
sudo nvme connect -t tcp -a 10.0.0.1 -s 4420 -n nqn.2026-10.io.spdk:lab
lsblk                      # 期望出现 /dev/nvme1n1
sudo fio --name=t --filename=/dev/nvme1n1 --rw=randread --bs=4k --iodepth=32 --runtime=30 --time_based
```

### 5.5 NVMe-oF **RDMA over Soft-RoCE**（本清单的重头戏，需要 §2 已完成）

```bash
# Target（VM-A，已有 rxe0）
sudo scripts/rpc.py nvmf_create_transport -t RDMA -u 8192
sudo scripts/rpc.py nvmf_create_subsystem nqn.2026-10.io.spdk:lab -a -s SPDK00000000000001
sudo scripts/rpc.py nvmf_subsystem_add_ns nqn.2026-10.io.spdk:lab Malloc0
sudo scripts/rpc.py nvmf_subsystem_add_listener nqn.2026-10.io.spdk:lab -t RDMA -a 10.0.0.1 -s 4420

# Initiator（VM-B）：内核 nvme-rdma（Debian 自带 rdma_rxe/rdma_cm，只要 rxe0 起来了就能用）
sudo nvme connect -t rdma -a 10.0.0.1 -s 4420 -n nqn.2026-10.io.spdk:lab
```
**验收**：
- `nvme list` / `lsblk` 出现远端盘；
- `/sys/class/infiniband/rxe0/ports/1/counters/` 下的 `port_xmit_data`、`port_rcv_data` 随 fio 增长（这是"真的走了 RDMA"的硬证据，比任何日志都可靠）；
- 用 fio 做 **RDMA vs TCP** 对照（§5.4 同一 target/同一个 Malloc0），把延迟/带宽差异记下来——这是你在这套硬件上能做出的最有说服力的实验结论。

### 5.6 用户态 NVMe 真路径（需要一块**空闲** NVMe）

**当前可用的空闲槽：Orange Pi 5 Max / 5 Plus 的 M.2 M-key（实测 PCI 上无 NVMe）。** 买盘见 §8。

```bash
# 只在这块空闲盘所在的节点上做（先在 OPi5 上，别在集群 NanoPC 上）
pciutils 未装 → sudo apt install -y pciutils
lspci -nn | grep -i nvme                 # 例：0003:31:00.0 Non-Volatile memory controller
sudo apt install -y dpdk-dev
sudo /usr/bin/dpdk-devbind.py --status
sudo /usr/bin/dpdk-devbind.py -b vfio-pci 0003:31:00.0
sudo scripts/setup.sh status             # 确认盘已被 SPDK 认到
sudo build/bin/spdk_nvme_identify -r 'trtype:PCIe traddr:0003:31:00.0'
sudo build/bin/spdk_nvme_perf -r 'trtype:PCIe traddr:0003:31:00.0' -q 32 -o 4096 -w randread -t 30
# 实验结束务必解绑回内核，否则这块盘在系统里就"消失"了
sudo /usr/bin/dpdk-devbind.py -b nvme 0003:31:00.0
```
**验收**：`spdk_nvme_perf` 报出的 4K 随机读延迟明显低于内核块层（通常 1/3–1/2），CPU 占用一个核跑满——这就是轮询 + 用户态驱动的代价与收益。
**注意**：RK3588 上 `vfio-pci` 可用（18 个 IOMMU group 实测存在）；若绑定失败，优先查 IOMMU group 是否被 pcieport 共享（`ls /sys/kernel/iommu_groups/*/devices`）。

---

## 6. DPDK 实验（Armbian 节点或实验 VM）

### 6.1 安装与自检

```bash
sudo apt install -y dpdk dpdk-dev pciutils
dpdk-testpmd --version
# devbind 脚本名/路径以包内容为准：
dpkg -L dpdk dpdk-dev | grep -i devbind
dpdk-devbind.py --status                # 记下集群网卡当前的 driver（不要改！）
```

### 6.2 大页（只在 OPi5 / VM 上）

```bash
echo 512 | sudo tee /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages   # 1 GiB
grep -i huge /proc/meminfo
# 结束： echo 0 | sudo tee /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages
```
（VM/WSL 里没有大页时，一律加 `--no-huge -m 512`，功能不受影响。）

### 6.3 软件 PMD 实验矩阵（这五台机器的网卡都**没有** DPDK PMD，所以只能用这些）

| # | vdev | 命令骨架 | 学到什么 | 验收 |
|---|---|---|---|---|
| 1 | `net_null` | `dpdk-testpmd -l 4-5 --vdev=net_null0 --vdev=net_null1 -- -i` | DPDK 自身开销下限 | `show port stats` 有数、`start` 后无 drop |
| 2 | `net_tap` | `--vdev=net_tap0,iface=dtap0` | 与内核协议栈互通、pktgen/iperf 打流 | `ping`/`iperf3` 通过 dtap0 |
| 3 | `net_af_packet` | `--vdev=net_af_packet0,iface=enP3p49s0` | 真在物理口收发包（非 bypass） | `show port stats all` 的 RX/TX 与 `ethtool -S` 对得上 |
| 4 | `net_pcap` | `--vdev=net_pcap0,rx_pcap=in.pcap,tx_pcap=out.pcap` | 离线回放/确定性测试 | 输出 pcap 能被 tcpdump 解开 |
| 5 | 两个 DPDK 实例互转 | 两台 VM 各起一个 `net_tap`/af_packet，中间 Linux bridge（或 `l2fwd`） | 完整转发路径、MAC 学习 | A→B 单向打流，B 上收包率 ≥ 99% |

> `net_ring`（`--vdev=net_ring0`）可做"纯 DPDK 内部互联"，但**成对/互联的语法随版本变化**，先用上面 5 条；要试 ring 时以 `dpdk-testpmd --help` 与 DPDK 文档为准。

### 6.4 lcore 拓扑（别把大小核搞混）

- RK3588（OPi5 Plus/Max）：8 核 = 4×A55 + 4×A76。测试用大核：`-l 4-7 --main-lcore 4`（小核实测跑数据面会拖后腿，仓库 `docs/rag-service-spike.md` 里已经踩过"8 线程比 4 线程慢"的坑）。
- RK3399（NanoPC）：6 核 = 2×A72 + 4×A53，用 `-l 4-5`。
- 加 `--lcores '(4-5)@(4-5)'` 可显式绑定 lcore↔CPU，`-n 4` 内存通道数在 ARM 上可给 4。

### 6.5 该记录的对照数据

| 场景 | 命令 | 期望 |
|---|---|---|
| 内核路径基线 | `iperf3 -c <peer>`（1G 口） | ≈ 940 Mbps |
| DPDK af_packet 收包 | `dpdk-testpmd --vdev=net_af_packet0,iface=... -- -i --rxd=1024` | 与 iperf 同量级，但 CPU 占用、drop 计数完全不同 |
| 纯 DPDK 转发 | 两台 VM + `net_tap` + `l2fwd` | 可测出"每包 ~百纳秒"级的 DPDK 自身开销 |
| 大页的影响 | 同一实验加/不加 `--no-huge` | 量化 TLB 的影响（这就是 DPDK 要大页的原因） |

### 6.6 明确做不了的（别浪费时间）

- 真正的 poll-mode 网卡直通：`r8169` / `rk_gmac-dwmac` / `brcmfmac` **都没有 DPDK PMD**，绑 vfio 也没用。
- SR-IOV、`rte_flow` 硬件卸载：这些家用 SoC 网卡/无线网卡不支持。
- 想要"真 PMD"体验：只在**实验 VM**里用 virtio-net / vmxnet3 补上（VirtualBox 7 的 virtio-net / VMware 的 vmxnet3，DPDK 侧分别是 `net_virtio` / `net_vmxnet3`）。

---

## 7. 组合场景：把学到的东西拼成一个"小数据面"

### 7.1 一条端到端链路

```
[VM-A] SPDK target ──(NVMe-oF RDMA over rxe0)──> [VM-B] 内核 nvme-rdma initiator ──> /dev/nvme1n1 ──> fio
                     └─ 同时 VM-B 上用 DPDK(af_packet/tap) 转发另一路流量，观察 CPU 争抢
```
**产出**：一张"RDMA 传输 vs TCP 传输"的 4K 随机读延迟/带宽对比表，加上 `port_xmit_data` 计数器增长的截图/数字。这是整套硬件上最接近"高性能数据平面"的复现。

### 7.2 想再加一层：libfabric

实测仓库里有 `libfabric` 1.17（`libfabric-dev` 可用）。rxe 起来后：
```bash
sudo apt install -y libfabric-bin libfabric-dev
fi_info -p verbs            # 期望看到 rxe0 相关的 verbs provider
fi_pingpong -p verbs        # 服务端；客户端加对端地址
```
这条把"RDMA 之上还有一层可移植接口"的抽象打通（MPI/NCCL 走的正是这层）。

### 7.3 分布式共享内存的味道（可选，验证概念）

§2.3 的 netns 双栈 + 自己用 `ibv_reg_mr` + `RDMA_WRITE` 写一个"远端内存读写"小工具，就是 GiantVM/SSI 那套 DSM 的最小原型——目的是理解"跨机内存访问的代价"，不是真做 SSI。

---

## 8. 硬件升级选项（想把实验做成"真的"再看）

| 物品 | 约价 | 插哪 | 解锁什么 | 风险 |
|---|---|---|---|---|
| M.2 2280 NVMe 256 GB | ¥100–150 | **OPi5 Max / Plus 的 M.2 M-key（实测空槽）** | SPDK 用户态 NVMe 真路径、真实 µs 级延迟、NVMe-oF 有真盘可共享 | 低；注意 RK3588 的 PCIe 供电与散热，别买功耗异常高的盘 |
| USB3.0 2.5G/1G 网卡 | ¥60–120 | OPi5 Max（或任一台板子） | 与 master 空闲口 `enP3p49s0` 组成**专用实验链路**，完全不碰生产网 | 低；USB 网卡中断模式对 DPDK 不友好，但对 rxe/iperf 够用 |
| 二手 Mellanox ConnectX-3 (MCX311A) ×2 + DAC 线 | ¥300–400 | **x86 主机装 Linux 双系统**的两个 PCIe 槽，两卡用 DAC 直连 | **真硬件 RoCE**，perftest 能跑出 10–40 Gbps / 2 µs 级延迟；也是 GPUDirect RDMA 的前置条件 | 中；需要双系统（Windows 保留）、要装 mlx4 驱动（内核自带）、卡是 PCIe 3.0 x8 |
| M.2→PCIe x16 转接 + 12V 供电 | ¥60 | OPi5 的 M.2 槽 | 在 ARM 上跑**硬件 RoCE** | **高**：M.2 只供 3.3V（PCIe 卡要 12V，必须外加供电）、MLNX 驱动要编进内核、RK3588 PCIe 窗口/BAR 兼容性未知。不推荐作为第一步 |

**不建议**：为 2070S 折腾 GPUDirect RDMA（需要"社区魔改内核模块 + ConnectX 网卡 + 指定内核版本"三件事同时成立，且不稳定）。

---

## 9. 进度勾选表

### 阶段 1：零成本热身（半天内）
- [ ] WSL Debian：`dpdk-testpmd --no-huge` 起 `net_null`，`start` 后看到统计
- [ ] WSL Debian：`net_tap0` + `ping` 通内核侧
- [ ] 记录：本机 iperf3 基线、DPDK 软件 PMD 基线

### 阶段 2：双 VM 实验台（1 天）
- [ ] Hyper-V 启用，默认路径改到 `D:\vms`，建 `RDMALab` **Internal** Switch
- [ ] 两台 Debian 12 VM 起来，互相 ping 通，**且集群仍可 ping 通**（红线检查）
- [ ] 两 VM 上 `modprobe rdma_rxe` + `rdma link add rxe0` + `ibv_devinfo` 看到 `PORT_ACTIVE`
- [ ] `ib_send_bw` / `ib_write_lat` 出数并填表
- [ ] （可选）netns 双栈单机 RDMA 打通

### 阶段 3：SPDK 与组合实验（1 天）
- [ ] `./configure --with-rdma && make -j` 成功
- [ ] `bdev_malloc` / `bdev_uring` / `bdev_aio` 创建成功，`bdev_get_bdevs` 可见
- [ ] NVMe-oF **TCP** target + 内核 `nvme connect -t tcp` → `/dev/nvme1n1` 可用
- [ ] NVMe-oF **RDMA over rxe** 打通，`counters/port_xmit_data` 增长
- [ ] 产出 RDMA vs TCP 对照数据表
- [ ] （可选）`fi_pingpong -p verbs` 通过

### 阶段 4：DPDK 真机练习（1 天）
- [ ] 在 **OPi5 Max**（不是 NanoPC）装 dpdk，分配 512×2M 大页，测完归还
- [ ] `net_af_packet0` 在 `enP3p49s0`（或在有 USB 网卡时）跑起来，统计与 `ethtool -S` 对齐
- [ ] 两台 VM 之间 `net_tap` + bridge 的 `l2fwd` 转发
- [ ] 记录大页 vs `--no-huge` 的差异

### 阶段 5：真实硬件 RDMA（1–2 天，风险最高）
- [ ] x86 上交叉编出带 IB/RXE 的 Armbian 内核 deb（`output/debs/`）
- [ ] **只装一台**（建议 NanoPC server3），重启后 `ibv_devinfo` 看到 `rxe0`
- [ ] `ib_send_bw` 自环出数；`ceph -s` / `kubectl get nodes` 确认集群没被带崩
- [ ] 再扩充到第二台，跨板跑 `ib_send_bw`
- [ ] 若走 M.2 空槽：装 NVMe → SPDK `spdk_nvme_perf` 出数 → 解绑回内核

### 阶段 6：可选硬件（§8）
- [ ] NVMe 到货 → OPi5 Max 上跑通用户态 NVMe
- [ ] USB 网卡到货 → master `enP3p49s0` 直连实验链路
- [ ] （进阶）双系统 + 双 ConnectX-3 → 硬件 RoCE

### 阶段 7：后续可做但**尚未实施**的事项

> 本节只记录待办，不代表已经动过任何东西。截至本文档落盘：文档、探测脚本、实测数据是全部产出，**集群上没有任何配置被修改**（临时上传到 master 的 `/tmp/dsh_probe.sh` 已删除）。

- [ ] **脚本化阶段 1–2**：把 WSL2 的 `dpdk-testpmd --no-huge` 热身、Hyper-V 建网 + 两台 VM 的 rxe 拉起与 perftest，整理成可直接执行的 PowerShell + bash 脚本。（2026-10 决定：**暂不写代码**，先只留文档。）
- [ ] **把 §10 的探测脚本版本化**：`/tmp/dsh_probe.sh` 的内容建议收进仓库（例如 `docs/` 旁或 `scripts/`），做成 `probe-nodes.sh` 一键刷新 §0.2 的能力矩阵。
- [ ] **VM 内核里 rdma_rxe 的确认**：Debian/Ubuntu 发行版内核自带 `rdma_rxe` 是常见情况，但本文档未在 x86 上实测过，第一次开 VM 后用 `modinfo rdma_rxe` 复核；若缺失，退到 §3 的自定义内核做法。
- [ ] **`dpdk-testpmd` / `dpdk-devbind.py` 的确切包与路径**：本文档按 Debian 常规写法给出，首次安装后用 `dpkg -L dpdk dpdk-dev | grep -Ei 'testpmd|devbind'` 核对并回填。
- [ ] **升级到 OpenSpec 变更**：若这套实验要变成正式规划（而非临时清单），按仓库 `AGENTS.md` 走 OpenSpec Service（MCP 工具当前在本会话不可用，需要时再补）。
- [ ] **补充：真实 NVMe 采购与空闲盘确认**：OPi5 Max/Plus 的 M.2 槽当前实测为空，装盘前再 `lspci -nn | grep -i nvme` 复核一次（避免记错机器）。

---

## 10. 附：本次实测原始数据与采集命令

复现/更新这份清单只需在 master 上跑一次（Windows 无集群节点的免密密钥，workers 要通过 master 跳板）：

```bash
# Windows 侧（PowerShell）：master 可直连，worker 需经 master 转发
ssh root@192.168.137.101 'for h in 192.168.137.201 192.168.137.202 192.168.137.203 192.168.137.211; do
  echo "### $h"; ssh -o BatchMode=yes root@$h bash -s < /tmp/dsh_probe.sh; done'
```
`/tmp/dsh_probe.sh` 的内容（本次用的探测脚本，建议随仓库一起版本化）：

```bash
echo "HOST=$(hostname) KERNEL=$(uname -r) ARCH=$(uname -m) CPU=$(nproc) MEM_MB=$(free -m | awk '/Mem:/{print $2}')"
grep -E '^(BOARD|BOARD_NAME|BOARDFAMILY|VERSION)=' /etc/armbian-release | tr '\n' ' '; echo
for i in /sys/class/net/*; do n=$(basename $i); case $n in lo|cali*|veth*|flannel*|cni*|docker*|tunl*|br-*|virbr*) continue;; esac
  echo "   $n speed=$(cat $i/speed 2>/dev/null) drv=$(basename $(readlink -f $i/device/driver 2>/dev/null) 2>/dev/null)"; done
modinfo -F filename rdma_rxe 2>&1 | head -2
grep -E '^CONFIG_(RDMA_RXE|INFINIBAND|INFINIBAND_USER_ACCESS|RDMA_CM|HUGETLBFS|VFIO|UIO|PCI_STUB)' /boot/config-$(uname -r)
grep -iE 'HugePages_Total|Hugepagesize' /proc/meminfo
mount | grep -i hugepages
lsblk -o NAME,SIZE,TYPE,TRAN,MODEL | head -20
for d in /sys/bus/pci/devices/*; do echo "   $(basename $d) $(cat $d/vendor):$(cat $d/device) drv=$(basename $(readlink -f $d/driver 2>/dev/null) 2>/dev/null)"; done
ls /sys/kernel/iommu_groups | wc -l
for p in dpdk dpdk-dev rdma-core ibverbs-utils perftest nvme-cli liburing-dev fio linux-source spdk; do
  echo "   $p = $(apt-cache policy $p 2>/dev/null | awk '/Candidate/{print $2}')"; done
```

**本次关键实测值（可直接引用）**

| 项 | master (OPi5 Plus) | OPi5 Max | NanoPC-T4 ×3 |
|---|---|---|---|
| 内核 | 6.1.115-vendor-rk35xx | 6.1.115-vendor-rk35xx | 6.18.35-current-rockchip64 |
| `CONFIG_INFINIBAND` | is not set | is not set | is not set |
| `modinfo rdma_rxe` | not found | not found | not found |
| `/sys/class/infiniband` | 不存在 | 不存在 | 不存在 |
| HugePages_Total | 0（`/dev/hugepages` pagesize=2M 已挂） | 0（同左） | 0 |
| IOMMU groups | 18 | 18 | 5 |
| vfio-pci | 可用 | 可用 | 可用（模块 =m） |
| uio_pci_generic | 模块存在 | 模块存在 | **未编译** |
| NVMe | 无（M.2 空） | 无（M.2 空） | 有 238.5G，**归 Ceph，勿动** |
| apt: dpdk / perftest / nvme-cli / fio | 22.11.11 / 4.5 / 2.4 / 3.33 均可用 | 同左 | 同左 |

---

### 参考

- DPDK 官方文档（EAL、大页、`net_ring`/`net_tap`/`net_af_packet` PMD）
- SPDK 官方文档（`spdk.io/doc`）：`setup.sh`、`rpc.py`、NVMe-oF target/initiator
- rdma-core：`rdma link add ... type rxe`、`rxe(7)` man page
- 仓库内相关材料：[docs/platform-k8s-conventions.md](platform-k8s-conventions.md)（节点能力与内存约束）、[docs/calico-migration-run.md](calico-migration-run.md)（节点重启引发的连锁故障复盘）、[docs/rag-service-spike.md](rag-service-spike.md)（RK3588 大小核实测）
