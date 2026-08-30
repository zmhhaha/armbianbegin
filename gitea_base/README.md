# Gitea + Drone 部署

本目录部署 Gitea、Drone Server 和 Kubernetes Runner。Gitea 使用 `data` 命名空间中已有的 PostgreSQL 服务；Casdoor 继续使用自己的 MySQL，不新增 PostgreSQL PVC。

## 前置条件

- Kubernetes 已配置并可使用 `kubectl`。
- `data/postgres-0`、`data/postgres-secret` 和 `vault-backend` 已就绪。
- 本地镜像仓库地址为 `arm-cluster-master:5000`。

## 1. 初始化 Gitea 数据库

初始化脚本会在 PostgreSQL Pod 内调用 `psql`，本机不需要安装 PostgreSQL 客户端：

```bash
cd ~/armbianbegin/gitea_base
export GITEA_DB_PASSWORD='Gitea 专用数据库密码'
bash ./init-db.sh
```

脚本默认使用以下参数，可通过环境变量覆盖：

```text
Pod:         postgres-0（data 命名空间）
管理员用户:  appuser
管理员数据库: appdb
Gitea 用户:  gitea
Gitea 数据库: gitea
```

## 2. 写入 Gitea Vault 密钥

```bash
kubectl -n vault exec vault-0 -- vault kv put secret/gitops/gitea \
  GITEA_POSTGRES_PASSWORD='与上一步相同的密码' \
  GITEA_SECRET_KEY="$(openssl rand -hex 32)" \
  GITEA_INTERNAL_TOKEN="$(openssl rand -hex 32)" \
  GITEA_OAUTH2_JWT_SECRET="$(openssl rand -hex 32)"
```

## 3. 部署 Gitea

```bash
cd ~/armbianbegin/gitea_base
bash ./deploy-gitea.sh
```

检查状态：

```bash
kubectl get pods -n gitops
kubectl logs -n gitops statefulset/gitea
```

访问地址：`https://gitea.panghuer.top`

## 4. 配置 Casdoor OIDC

在 Casdoor 创建 Gitea OIDC 应用，回调地址填写：

```text
https://gitea.panghuer.top/user/oauth2/casdoor/callback
```

在 Gitea 管理后台配置 Casdoor 的 OIDC Client ID、Client Secret 和发现地址。

### 首次进入管理后台

登录页面右上角只有“登录”而没有“站点管理”时，说明还没有 Gitea 管理员。先在服务器创建一个本地应急管理员：

```bash
kubectl -n gitops exec -it gitea-0 -- \
  /usr/local/bin/gitea --config /etc/gitea/app.ini \
  admin user create \
  --username admin \
  --password '设置一个临时强密码' \
  --email admin@panghu.top \
  --admin \
  --must-change-password=false
```

使用该账号登录 `https://gitea.panghuer.top`。点击右上角头像，在菜单中选择“站点管理”（Site Administration），再进入“身份认证源”（Authentication Sources）。

### 手动添加 Casdoor 登录源

1. 在“身份认证源”页面点击“添加认证源”（Add Authentication Source）。
2. 类型选择“OAuth2”。不要选择“OpenID”，后者会要求输入 OpenID URI。
3. OAuth2 提供商选择“OpenID Connect”。
4. 名称填写 `casdoor`，建议使用全小写，因为它会出现在回调 URL 中。
5. 发现地址填写：

   ```text
   https://auth.panghuer.top/.well-known/openid-configuration
   ```

6. 填入 Casdoor 应用的 Client ID 和 Client Secret。
7. 点击页面底部“添加认证源”（Add Authentication Source）保存。

在 Casdoor 应用的“允许跳转 URI”中添加：

```text
https://gitea.panghuer.top/user/oauth2/casdoor/callback
```

保存后返回 Gitea 登录页，按钮应显示“使用 Casdoor 登录”。首次登录会自动创建 Gitea 用户；如需授予该用户管理员权限，可执行：

```bash
kubectl -n gitops exec -it gitea-0 -- \
  /usr/local/bin/gitea --config /etc/gitea/app.ini \
  admin user change-permission --username 用户名 --admin
```

确认 Casdoor 登录正常后，可在“站点管理 -> 用户”中删除临时本地管理员，建议至少保留一个应急管理员账号。

## 5. 配置 Drone OAuth

创建 Drone 使用的 OAuth 客户端，回调地址填写：

```text
https://drone.panghuer.top/login
```

将客户端信息写入 Vault：

```bash
kubectl -n vault exec vault-0 -- vault kv put secret/gitops/drone \
  DRONE_GITEA_CLIENT_ID='客户端ID' \
  DRONE_GITEA_CLIENT_SECRET='客户端密钥' \
  DRONE_RPC_SECRET="$(openssl rand -hex 32)"
```

## 6. 部署 Drone

```bash
cd ~/armbianbegin/gitea_base
bash ./deploy-drone.sh
```

检查状态：

```bash
kubectl get pods -n gitops
kubectl get pods -n drone-builds
```

访问地址：`https://drone.panghuer.top`

## 构建镜像

```bash
cd ~/armbianbegin/gitea_base
bash ./gitops_config.sh build
```

构建脚本会构建并推送 Gitea、Drone、Drone Runner 及编译器镜像。Drone Runner 使用本目录的 `Dockerfile_drone_runner_kube`，不依赖 Alpine CDN。

## 故障排查

```bash
kubectl describe pod -n gitops -l app=gitea
kubectl logs -n gitops -l app=gitea
kubectl describe externalsecret -n gitops
kubectl logs -n gitops statefulset/drone-server
```

## Drone 部署问题记录

### `Invalid port configuration`

Drone 2.21 使用 `DRONE_SERVER_PORT`，不要使用旧的 `DRONE_HTTP_BIND`：

```yaml
DRONE_SERVER_PORT: ":8080"
```

修改后重新应用并重启：

```bash
kubectl apply -f drone-env.yaml
kubectl rollout restart statefulset/drone-server -n gitops
```

如果服务器 ConfigMap 仍有旧变量，说明本地修改没有同步到服务器；`git pull` 不会同步本地未提交的改动。

### `Unregistered Redirect URI`

Drone 实际发送给 Gitea 的 OAuth 回调地址是：

```text
https://drone.panghu.top/login
```

在 Gitea“右上角头像 -> 设置 -> 应用 -> 管理 OAuth2 应用”中，将 Drone 应用的重定向 URI 精确设置为该地址。必须使用 HTTPS，域名和路径完全一致，末尾不能多 `/`。

### `Complete your Drone Registration`

这是首次登录的正常资料补充页面。填写邮箱、全名和公司名称（个人使用可填写 `Personal`）后提交即可。每个首次登录的用户都需要完成一次；如反复出现，请先在 Gitea“头像 -> 设置 -> 账户”中补充邮箱和全名。
