# Ceph RGW / S3 部署

本目录为现有 Ceph Squid 19.x 集群部署一套通用 S3 兼容对象存储。RGW 由 cephadm 管理，Kubernetes 通过无 Selector Service 和 EndpointSlice 访问宿主机上的 RGW 实例。

## 默认拓扑

| 项目 | 默认值 |
| --- | --- |
| Ceph 服务名 | `rgw.s3` |
| RGW 节点 | `orangepi5-max-server1`、`nanopct4-server1` |
| 节点地址 | `192.168.137.211`、`192.168.137.201` |
| RGW 端口 | `7480` |
| K8s 内部地址 | `http://ceph-rgw.data.svc.cluster.local:7480` |
| 可选公网地址 | `https://s3.panghuer.top` |
| 虎博 Bucket | `hubo-media` |

当前 `arm-cluster-master` 在 cephadm 中被标记为 `Offline`，因此默认不在该节点部署 RGW。调整部署节点时，必须同时修改 `cephadm-rgw.yaml` 和 `k8s/service.yaml` 中的主机/IP。

## 文件说明

```text
rgw/
├── cephadm-rgw.yaml                # 双实例 RGW ServiceSpec
├── deploy.sh                       # 预检查、部署、等待和 K8s 接入
├── check.sh                        # 只读健康检查
├── create-s3-user.sh               # 创建 S3 用户并输出权限受限的凭据文件
├── store-in-vault.sh               # 从凭据文件写入 Vault KV v2
├── bootstrap-bucket.sh             # 创建私有 Bucket、CORS 和生命周期规则
└── k8s/
    ├── service.yaml                # K8s Service + EndpointSlice
    ├── tunnel-route.yaml           # 可选 Cloudflare Tunnel 公网入口
    └── panghu-chat-external-secret.yaml
```

## 前置条件

- 在 Ceph 管理节点上使用 root 或具有等价权限的用户执行。
- `ceph`、`cephadm`、`kubectl`、`curl`、`python3` 可用。
- `/etc/ceph/ceph.conf` 和管理员 keyring 可用。
- 两个目标节点在 `ceph orch host ls` 中存在且不为 `Offline`。
- Kubernetes kubeconfig 默认位于 `/etc/kubernetes/super-admin.conf`。
- Ceph 不得处于 `HEALTH_ERR`。

`deploy.sh` 默认拒绝在 `HEALTH_WARN` 状态下继续。确认告警与 RGW 无冲突后，可以显式允许：

```bash
ALLOW_HEALTH_WARN=1 ./deploy.sh
```

不建议长期依赖该开关。当前集群应优先修复 cephadm SSH、stray OSD 和 MON 系统盘空间告警。

## 部署 RGW

```bash
cd /root/armbianbegin/ceph/rgw
chmod +x deploy.sh check.sh create-s3-user.sh store-in-vault.sh bootstrap-bucket.sh
./check.sh
./deploy.sh
```

部署完成后，Kubernetes 内部服务使用：

```text
http://ceph-rgw.data.svc.cluster.local:7480
```

默认不创建公网入口。需要为浏览器签名直传提供公网地址时执行：

```bash
EXPOSE_PUBLIC=1 ./deploy.sh
```

该操作创建 `s3.panghuer.top` 的 `TunnelRoute`。客户端应使用 path-style 地址，例如：

```text
https://s3.panghuer.top/hubo-media/path/to/object.jpg
```

## 创建虎博 S3 用户

脚本不会在终端打印 Access Key 和 Secret Key，而是写入权限为 `0600` 的凭据文件：

```bash
./create-s3-user.sh hubo "虎博媒体服务" /root/hubo-s3.env
```

如果需要重新生成同一路径的凭据文件，必须显式使用 `FORCE=1`；脚本不会自动轮换 Ceph 中已有的 Key：

```bash
FORCE=1 ./create-s3-user.sh hubo "虎博媒体服务" /root/hubo-s3.env
```

如果用户已存在，脚本复用现有第一组 S3 Key，不会自动轮换密钥。凭据文件包含：

```text
S3_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY
S3_ADMIN_ENDPOINT
S3_INTERNAL_ENDPOINT
S3_PUBLIC_ENDPOINT
S3_BUCKET
S3_REGION
S3_FORCE_PATH_STYLE
```

## 写入 Vault

本地 `vault` CLI 已登录后执行：

```bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN='...'
./store-in-vault.sh /root/hubo-s3.env secret/panghu-chat/s3
kubectl apply -f k8s/panghu-chat-external-secret.yaml
```

Vault 写入路径使用 KV v2 CLI 写法 `secret/panghu-chat/s3`；ExternalSecret 读取路径为 `secret/data/panghu-chat/s3`。

确认 ExternalSecret 同步成功后，删除本地明文凭据文件：

```bash
shred -u /root/hubo-s3.env
```

## 创建 Bucket

`bootstrap-bucket.sh` 依赖 AWS CLI v2 或兼容的 `aws` 命令：

```bash
./bootstrap-bucket.sh /root/hubo-s3.env
```

脚本会幂等创建 `hubo-media`，配置 `https://hubo.panghuer.top` 的浏览器 CORS，并清理超过 7 天的未完成分片上传。Bucket 保持私有，不配置匿名读写策略。

如需修改域名或 Bucket 名：

```bash
CORS_ORIGIN=https://hubo.example.com S3_BUCKET=hubo-media ./bootstrap-bucket.sh /root/hubo-s3.env
```

## 应用配置

虎博应用通过 `hubo-s3` Secret 获取配置。服务端访问使用 `S3_INTERNAL_ENDPOINT`，为浏览器生成预签名 URL 时使用 `S3_PUBLIC_ENDPOINT`。AWS SDK 需要启用 path-style：

```text
S3_FORCE_PATH_STYLE=true
```

图片和附件必须保存在私有 Bucket 中，下载和上传均使用短期预签名 URL。不要把 S3 Secret Key 返回给浏览器。

## 验证

```bash
./check.sh
kubectl get service ceph-rgw -n data
kubectl get endpointslice ceph-rgw -n data
kubectl get externalsecret hubo-s3 -n panghu-chat
```

正常情况下，两个直连地址和 K8s Service 都应返回 S3 XML，HTTP 状态可能是 `200` 或未认证访问的 `403`。

## 安全说明

- RGW 的 `7480` 是集群内 HTTP，公网 TLS 由 Cloudflare Tunnel 终止。
- 防火墙应只允许集群网段访问节点 `7480`。
- 每个应用使用独立 RGW 用户，不复用 Ceph 管理员身份。
- Bucket 默认私有，公开资源也应优先通过短期签名 URL 或受控 CDN 发布。
- 密钥轮换必须先创建新 Key、更新 Vault、等待应用滚动完成，再删除旧 Key。
- 删除 RGW 服务不会自动删除对象池；对象数据清理需要单独、明确的操作。
