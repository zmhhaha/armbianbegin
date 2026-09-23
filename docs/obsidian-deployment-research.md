# Obsidian 部署调研

日期：2026-09-21

## 结论

如果目标是“在自己的基础设施里使用 Obsidian，并让桌面和移动端同步”，推荐优先部署 **CouchDB + Self-hosted LiveSync**。它和当前仓库的 K8s、Cloudflare Tunnel、Vault、ExternalSecret、PVC 模式最贴合，成本低，数据留在自有集群里。

如果目标是“浏览器里直接打开一个 Obsidian 桌面界面”，可以补充部署 `linuxserver/obsidian`，但它更像远程桌面/单用户工作台，不适合作为多人或公开服务的主入口。

如果目标是“把笔记发布成网站”，不要把 Obsidian 桌面容器当发布系统。优先选择 Obsidian Publish，或用 Quartz / MkDocs Material 这类静态站方案从 Git 仓库构建。

## 需求拆分

Obsidian 的“部署”容易混成三件不同的事：

| 目标 | 推荐方案 | 说明 |
| --- | --- | --- |
| 多设备同步私有笔记 | CouchDB + Self-hosted LiveSync | 自托管、移动端可用、可接现有 Cloudflare Tunnel |
| 浏览器访问 Obsidian GUI | `linuxserver/obsidian` | 浏览器串流桌面应用，适合个人远程编辑 |
| 对外发布知识库 | Obsidian Publish / Quartz / MkDocs | 只读发布，和编辑同步分离 |
| 最省维护 | 官方 Obsidian Sync | 付费托管，少折腾，但不在自有基础设施内 |

## 方案一：官方 Obsidian Sync

官方 Sync 是最省心方案。Obsidian 官方说明 Sync 用于跨设备同步，支持选择性同步、版本历史、共享 vault、Headless Sync，并提醒不要和 Dropbox / Google Drive / OneDrive 等云盘混用，避免同步冲突。

优点：

- 运维成本最低，桌面和移动端体验最好。
- 官方支持端到端加密，默认 E2EE。
- 适合不想维护同步后端的个人使用。

限制：

- 数据远端在 Obsidian 的托管服务，不是自有集群。
- 有订阅成本。官方价格页当前显示 Sync 年付 $4/月、月付 $5/月。
- 官方存储限制分 Standard / Plus：Standard 为 1 个 vault、最大文件 5 MB、总存储 1 GB；Plus 为 10 个 vault、最大文件 200 MB、总存储 10 GB 到 100 GB。

判断：如果“自托管”不是硬要求，官方 Sync 是最低风险选择；如果希望全部走自有 K8s，就跳过。

## 方案二：Self-hosted LiveSync + CouchDB

Self-hosted LiveSync 是社区插件。项目 README 说明它可以使用 CouchDB，或使用 MinIO / S3 / R2 等对象存储进行同步，也支持 WebRTC P2P；同时明确它不兼容官方 Obsidian Sync，不能和官方 Sync 混用。

推荐以 **CouchDB** 作为第一版，因为文档成熟、插件路径主流、排障资料最多。对象存储模式可以以后再评估。

### 推荐架构

```text
Obsidian desktop/mobile
  -> https://obsidian-sync.panghuer.top
  -> Cloudflare Tunnel
  -> couchdb.obsidian.svc.cluster.local:5984
  -> PVC
```

关键点：

- 不建议把 CouchDB 放在 `oauth2-proxy` 后面。Obsidian 插件需要直接访问 CouchDB API，移动端也需要有效 HTTPS；OIDC 浏览器跳转会破坏插件同步流程和 CORS。
- 鉴权交给 CouchDB 自身用户密码，密码放 Vault，再通过 ExternalSecret 同步为 K8s Secret。
- 域名建议独立为 `obsidian-sync.panghuer.top`，不要挂子路径。LiveSync 文档也提醒 CouchDB 放在根路径最省事，子路径需要额外 rewrite 和 `_session` 处理。
- 只暴露 CouchDB 同步 API，不暴露 Fauxton 管理 UI 给公网。最稳妥做法是在反代层或 Cloudflare 层限制 `/_utils`。
- 首版用单副本 CouchDB + ReadWriteOnce PVC，避免 CouchDB 集群化带来的复杂度。

### CouchDB 配置要点

LiveSync 中文文档给出的核心配置包括：

```ini
[couchdb]
single_node=true
max_document_size = 50000000

[chttpd]
require_valid_user = true
max_http_request_size = 4294967296

[chttpd_auth]
require_valid_user = true
authentication_redirect = /_utils/session.html
```

CORS 需要允许 Obsidian 桌面和移动端来源。LiveSync 文档示例中包含：

```ini
[cors]
credentials = true
origins = app://obsidian.md,capacitor://localhost,http://localhost
headers = accept, authorization, content-type, origin, referer
```

反代还需要注意：

- 关闭响应缓冲，否则快速同步进度可能卡住。
- 提高请求体大小，避免附件同步出现 `413 Entity too large`。
- CouchDB 最好挂在域名根路径。

### 在本仓库的落地方式

建议新增目录：

```text
obsidian/
  README.md
  k8s/
    namespace.yaml
    couchdb-configmap.yaml
    couchdb.yaml
    service.yaml
  scripts/
    init-livesync-db.sh
```

同时新增或更新：

```text
vault/inventory/obsidian-externalsecret.yaml
cloudflare-tunnel/operator/tunnel-routes.yaml
```

注意：当前仓库的 Cloudflare Tunnel Operator 文档说明 `TunnelRoute` 只是后台配置备份，实际生效路由仍要去 Cloudflare 后台 Public Hostname 配置。因此增加 `obsidian-sync.panghuer.top -> couchdb.obsidian.svc.cluster.local:5984` 时，要在 Cloudflare 后台实际配置，再同步回 `tunnel-routes.yaml` 留档。

### Vault 密钥建议

Vault 路径：

```text
secret/obsidian/couchdb
```

字段：

```text
COUCHDB_USER
COUCHDB_PASSWORD
LIVESYNC_DATABASE
LIVESYNC_PASSPHRASE
```

`LIVESYNC_PASSPHRASE` 是 Obsidian vault 同步内容的端到端加密口令。它比 CouchDB 密码更重要，丢失后无法恢复远端加密数据，只能靠本地 vault 重新初始化。

### 初始化流程

1. 部署 namespace、ExternalSecret、ConfigMap、PVC、CouchDB Deployment 和 Service。
2. 确认 CouchDB 可从集群内访问。
3. 运行 LiveSync 官方初始化脚本，为目标数据库创建 LiveSync 元数据。
4. 通过桌面 Obsidian 安装 Self-hosted LiveSync 插件，生成 Setup URI。
5. 每台新设备使用 Setup URI 加入，而不是手工重复配置。
6. 同步稳定后再开启隐藏文件、插件、主题等扩展同步。

### 备份策略

必须备份两层：

- PVC / CouchDB 数据：用于服务端灾难恢复。
- 本地 Obsidian vault：用于插件误操作、同步冲突、误删后的最终兜底。

LiveSync 项目也明确建议安装或升级插件前先备份 vault，并且不要同时启用另一个同步方案。

## 方案三：`linuxserver/obsidian` 浏览器版

`linuxserver/obsidian` 是把 Obsidian 桌面应用通过 Selkies 串流到浏览器。文档说明 Web UI 默认在 `https://yourhost:3001/`，容器挂载 `/config` 保存配置，镜像支持多架构。

优点：

- 可以在浏览器里打开 Obsidian GUI。
- 对手机/临时设备很方便，不需要本地安装 Obsidian。
- 很适合配合现有 `oauth2-proxy` 暴露为 `obsidian.panghuer.top`。

风险：

- 这是远程桌面，不是原生 Web 版 Obsidian。
- LinuxServer 文档明确警告：该 Web 界面包含带无密码 sudo 的终端，不能裸露公网；必须放在强认证反代后面。
- 单用户体验更合理。多人共用同一个容器会共享同一套 Obsidian 状态和文件系统。
- 资源消耗高于纯 CouchDB，同步核心问题仍然要靠官方 Sync 或 LiveSync 解决。

判断：可以作为“个人远程编辑入口”的补充，但不应替代 CouchDB 同步后端。

推荐暴露方式：

```text
https://obsidian.panghuer.top
  -> Cloudflare Tunnel
  -> oauth2-proxy-obsidian.oauth.svc.cluster.local:4180
  -> obsidian-ui.obsidian.svc.cluster.local:3001
```

需要注意上游是 HTTPS 且自签证书；`oauth2-proxy` 或中间反代要能接受 upstream 自签证书。

## 方案四：静态发布

如果目标是公开或半公开知识库，应把“编辑同步”和“发布”拆开：

- 私有编辑：本地 Obsidian + LiveSync / 官方 Sync。
- 发布站点：从 Git 仓库或导出的 Markdown 构建静态站。

可选：

- Obsidian Publish：官方托管，价格页当前显示年付 $8/月、月付 $10/月，支持主题、图谱、全文搜索、自定义域名。
- Quartz：面向 Obsidian 数字花园的静态站方案，适合 GitOps。
- MkDocs Material：偏工程文档和知识库，结构化更强。

对当前仓库而言，静态发布更适合走已有门户、Cloudflare Tunnel 和 OAuth 模板，部署复杂度低于远程 Obsidian GUI。

## 推荐路线

第一阶段先做同步后端：

1. 新增 `obsidian/` K8s 清单，部署单副本 CouchDB。
2. 新增 `vault/inventory/obsidian-externalsecret.yaml` 管理 CouchDB 用户和 LiveSync 初始配置。
3. 在 Cloudflare 后台新增 `obsidian-sync.panghuer.top`，后端指向 `couchdb.obsidian.svc.cluster.local:5984`。
4. 初始化 LiveSync 数据库，完成一台桌面端和一台移动端双向同步验证。
5. 加 PVC 备份和 vault 本地备份流程。

第二阶段再按需补浏览器工作台：

1. 部署 `linuxserver/obsidian`，单副本，持久化 `/config`。
2. 通过 `oauth2-proxy` 暴露 `obsidian.panghuer.top`。
3. 禁止绕过 OAuth 直接访问 service。
4. 只作为个人远程 GUI 使用，不承载核心同步职责。

第三阶段如果要发布：

1. 选择 Obsidian Publish 或 Quartz / MkDocs。
2. 建立从 vault 到发布仓库的筛选规则，避免把私密笔记发布出去。
3. 静态站独立暴露，不和 CouchDB API 混在同一域名。

## 风险清单

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| LiveSync 和其他同步方案混用 | 冲突、重复、丢文件 | 同一个 vault 只启用一种同步 |
| CouchDB 裸露公网 | 数据泄露或被撞库 | 强密码、HTTPS、限制管理 UI、监控日志 |
| 忘记 LiveSync 加密口令 | 新设备无法解密远端数据 | 口令进密码管理器，保留本地 vault 备份 |
| 单副本 CouchDB 节点故障 | 同步服务中断 | PVC 备份；必要时再评估 CouchDB 集群 |
| Obsidian GUI 容器公开 | 远程终端被滥用 | 必须走 OAuth，禁止直接公网暴露 |
| TunnelRoute 与后台不一致 | 误以为路由已生效 | Cloudflare 后台是权威来源，仓库文件只备份 |

## 资料来源

- Obsidian Sync 介绍：https://obsidian.md/help/Obsidian%2BSync/Introduction%2Bto%2BObsidian%2BSync
- Obsidian 价格页：https://obsidian.md/pricing
- Obsidian Sync 存储限制：https://obsidian.md/help/Obsidian%2BSync/Plans%2Band%2Bstorage%2Blimits
- Obsidian Sync 安全与隐私：https://obsidian.md/help/Obsidian%2BSync/Security%2Band%2Bprivacy
- Obsidian Publish 介绍：https://obsidian.md/help/Obsidian%2BPublish/Introduction%2Bto%2BObsidian%2BPublish
- Self-hosted LiveSync README：https://github.com/vrtmrz/obsidian-livesync
- Self-hosted LiveSync CouchDB 部署文档：https://raw.githubusercontent.com/vrtmrz/obsidian-livesync/main/docs/setup_own_server.md
- LinuxServer Obsidian 镜像文档：https://docs.linuxserver.io/images/docker-obsidian/
