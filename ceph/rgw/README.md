# Ceph RGW / S3 部署

本目录为现有 Ceph Squid 19.x 集群部署通用 S3 兼容对象存储。RGW、HAProxy 和 Keepalived 全部由 cephadm 编排，不经过 Kubernetes Service 或 kube-proxy。

## 架构

| 项目 | 配置 |
| --- | --- |
| RGW 服务 | `rgw.s3`，2 个实例 |
| RGW 调度 | `host_pattern: "*"` + `count: 2` |
| RGW 后端端口 | `7481` |
| Ingress 服务 | `ingress.rgw.s3`，2 组 HAProxy/Keepalived |
| S3 服务端口 | `7480` |
| 服务入口 | 部署时指定的 VRRP 漂移 VIP |
| 推荐内部地址 | `http://s3.internal.panghuer.top:7480` |
| 可选公网地址 | `https://s3.panghuer.top` |
| 虎博 Bucket | `hubo-media` |

该方案与 RBD/CephFS 的目标一致：服务实例不绑定某个节点，节点故障后由 Ceph 编排器重新调度。S3 是 HTTP 协议，客户端不能通过 MON 自动发现 RGW，因此仍需要一个服务入口；这里使用 Ceph ingress 管理的 VRRP VIP，而不是任何节点自身 IP。Keepalived 会在 ingress 节点之间漂移 VIP，HAProxy 会自动发现 `rgw.s3` 的后端实例。

`192.168.137.101` 是 `arm-cluster-master` 的固定主机地址，不能作为漂移 VIP。部署前应从 `192.168.137.0/24` 选择一个未占用地址，并在内部 DNS 中将 `s3.internal.panghuer.top` 指向该 VIP。

## 文件说明

```text
rgw/
├── cephadm-rgw.yaml                # 动态调度的 RGW ServiceSpec
├── cephadm-ingress.yaml.tpl        # Ceph ingress 模板，部署时注入 VIP
├── build-ingress-images.sh         # 构建并推送 ARM64 ingress 镜像
├── configure-ingress-images.sh     # 配置 cephadm 镜像并执行安全 mgr failover
├── deploy.sh                       # 预检查、部署和就绪等待
├── check.sh                        # 只读健康检查
├── create-s3-user.sh               # 创建 S3 用户和权限受限凭据文件
├── bootstrap-bucket.sh             # 创建私有 Bucket、CORS 和生命周期规则
└── k8s/
    └── tunnel-route.yaml.tpl       # 可选公网入口模板

../../vault/inventory/
└── panghu-chat-s3-externalsecret.yaml # S3 凭据同步及部署说明

../../vault/scripts/
└── store-s3-credentials.sh         # 从凭据文件写入 Vault KV v2
```

## 前置条件

- 在 Ceph 管理节点上使用 root 或等价权限用户执行。
- `ceph`、`curl` 和 `python3` 可用。
- `docker` 可用，私有 Registry `arm-cluster-master:5000` 可访问。
- 至少两台 cephadm 主机在线。
- 在 `192.168.137.0/24` 中准备一个未占用 VIP，例如 `<S3_VIP>/24`。
- 网络允许 Keepalived VRRP；如交换机禁用 VRRP 组播，可在 ingress 模板中改用单播配置。
- Ceph 不得处于 `HEALTH_ERR`。

`deploy.sh` 默认拒绝在 `HEALTH_WARN` 状态下继续。确认告警与 RGW 无冲突后，可以设置 `ALLOW_HEALTH_WARN=1`。

## 部署

Ceph Squid 19.2.4 默认的 `quay.io/ceph/haproxy:2.3` 和
`quay.io/ceph/keepalived:2.2.4` 是 AMD64 镜像，不能直接运行在本集群的
ARM64 节点。首次部署先构建兼容镜像并配置 cephadm：

```bash
cd /root/armbianbegin/ceph/rgw
bash build-ingress-images.sh --push
bash configure-ingress-images.sh
```

`configure-ingress-images.sh` 会确认两个镜像都是 ARM64，并在存在 standby mgr
时执行一次标准 mgr failover，使 cephadm 的非运行时镜像选项生效。

然后确认候选 VIP 没有被使用并部署：
VIP部署为192.168.137.111

```bash
cd /root/armbianbegin/ceph/rgw
ping -c 2 <S3_VIP>

chmod +x deploy.sh check.sh create-s3-user.sh bootstrap-bucket.sh \
  ../../vault/scripts/store-s3-credentials.sh

RGW_VIRTUAL_IP=<S3_VIP>/24 ALLOW_HEALTH_WARN=1 ./deploy.sh
RGW_VIRTUAL_IP=<S3_VIP>/24 ./check.sh
```

部署脚本会依次：

1. 校验 VIP 的网段、占用情况和在线 cephadm 主机数量。
2. 部署两个动态调度的 RGW daemon。
3. 部署两个 HAProxy 和两个 Keepalived 实例。
4. 等待 Ceph ingress VIP 返回 S3 XML。

### 从 `Exec format error` 恢复

如果 ingress 已经因为默认 AMD64 镜像失败，而 `rgw.s3` 两个实例已经运行，
无需删除 RGW 服务或对象池。中止旧的等待脚本，同步最新代码后执行：

```bash
cd /root/armbianbegin/ceph/rgw
bash build-ingress-images.sh --push
bash configure-ingress-images.sh
RGW_VIRTUAL_IP=192.168.137.111/24 ALLOW_HEALTH_WARN=1 bash deploy.sh
```

cephadm 会重试现有 `ingress.rgw.s3`，不会重复创建对象数据。

如果需要公网入口：

```bash
RGW_VIRTUAL_IP=<S3_VIP>/24 ALLOW_HEALTH_WARN=1 EXPOSE_PUBLIC=1 ./deploy.sh
```

Cloudflare Tunnel 将直接访问 Ceph ingress VIP，不经过 Kubernetes Service。

## 内部 DNS

在局域网 DNS 中添加：

```text
s3.internal.panghuer.top -> <S3_VIP>
```

应用使用：

```text
http://s3.internal.panghuer.top:7480
```

以后 RGW、HAProxy 或 Keepalived 换节点，应用和 Vault 配置都不需要修改。只有迁移到其他网段时才需要更换 VIP/DNS。

## 创建虎博 S3 用户

脚本不会打印 Access Key 和 Secret Key，而是写入权限为 `0600` 的文件。必须显式提供稳定的 S3 地址：

```bash
S3_ENDPOINT=http://s3.internal.panghuer.top:7480 \
  ./create-s3-user.sh hubo "虎博媒体服务" /root/hubo-s3.env
```

如果需要覆盖本地凭据文件：

```bash
S3_ENDPOINT=http://s3.internal.panghuer.top:7480 FORCE=1 \
  ./create-s3-user.sh hubo "虎博媒体服务" /root/hubo-s3.env
```

如果 Ceph 用户已存在，脚本复用已有第一组 S3 Key，不会自动轮换 Ceph 中的 Key。

## 写入 Vault

本地 `vault` CLI 已登录后执行：

```bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN='...'
../../vault/scripts/store-s3-credentials.sh \
  /root/hubo-s3.env secret/panghu-chat/s3
kubectl apply -f ../../vault/inventory/panghu-chat-s3-externalsecret.yaml
kubectl annotate externalsecret hubo-s3 -n panghu-chat \
  force-sync="$(date +%s)" --overwrite
```

Vault CLI 写入路径为 `secret/panghu-chat/s3`；ExternalSecret 读取路径为 `secret/data/panghu-chat/s3`。确认同步成功后删除本地明文文件：

```bash
shred -u /root/hubo-s3.env
```

## 创建 Bucket

`bootstrap-bucket.sh` 依赖 AWS CLI v2：

```bash
./bootstrap-bucket.sh /root/hubo-s3.env
```

脚本幂等创建 `hubo-media`，配置 `https://hubo.panghuer.top` 的浏览器 CORS，并清理超过 7 天的未完成分片上传。Bucket 保持私有。

## 验证

```bash
RGW_VIRTUAL_IP=<S3_VIP>/24 ./check.sh
curl -i http://s3.internal.panghuer.top:7480/
kubectl get externalsecret hubo-s3 -n panghu-chat
```

HTTP `200` 或未认证访问的 `403` 均表示 S3 入口正常。可使用以下命令确认实际调度节点：

```bash
ceph orch ps --service_name rgw.s3
ceph orch ps --service_name ingress.rgw.s3
```

## 安全说明

- RGW 后端 `7481` 和 ingress `7480` 仅应允许受信任网段访问。
- 公网 TLS 由 Cloudflare Tunnel 终止。
- 每个应用使用独立 RGW 用户，不复用 Ceph 管理员身份。
- Bucket 默认私有，上传和下载使用短期预签名 URL。
- 删除 RGW 服务不会自动删除对象池；对象数据清理需要单独、明确的操作。
