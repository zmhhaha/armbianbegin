# Casdoor 升级记录：3.113.0 → 4.11.0（2026-09-29）

> 执行人：所有者。本文按升级后的实测复盘整理，保留可复用的判据与本次踩到的坑。
> 相关：[deployment-guide.md](deployment-guide.md)（部署手册）、[casdoor不下发第三方token.md](casdoor不下发第三方token.md)（JWT 字段白名单）、[casdoorAlipay.md](casdoorAlipay.md)（已放弃的支付宝集成）。

## 结论

**升级成功。** Casdoor 真的跑在 4.11.0 上；数据完整（表只增不减、用户/应用/证书计数不变）；
13 个 oauth2-proxy 未被牵连；11 个域名的登录链路正常；**已签发的 token 不失效**（JWKS 的 kid 未变）。

## 一、怎么证明"真的换版本了"

只看 `kubectl get deploy -o yaml` 会被期望值骗——那只是清单里写的，不等于在跑。本次用了五条独立证据：

| 证据 | 升级前 | 升级后 |
|---|---|---|
| Deployment 里写的镜像 | `4.11.0`（拉不到） | `4.11.0`（真的在跑） |
| **实际运行镜像** | `casdoor:latest`（07-10 构建） | `casdoor:4.11.0`（09-26 构建） |
| **Service endpoints** | 旧 Pod `10.244.96.144` | 新 Pod `10.244.0.28` |
| 镜像身份 | — | registry 与运行容器的 image id `073c0e22…` **双向一致** |
| 公网 `/api/health` | ok | ok |

关键一条是 **Service endpoints 变了**：它证明流量真的切到了新 Pod，而不是"清单改了、Pod 没换"。

## 二、升级前后逐项对比

| 指标 | 升级前 | 升级后 |
|---|---|---|
| Deployment 镜像 | `4.11.0`（拉不到） | `4.11.0` 真的在跑 |
| 实际运行镜像 | `casdoor:latest`（07-10 构建） | `casdoor:4.11.0`（09-26 构建） |
| rollout | 卡死 ImagePullBackOff | successfully rolled out |
| Service endpoints | `10.244.96.144`（旧 Pod） | `10.244.0.28`（新 Pod） |
| 镜像身份 | — | registry / 运行容器 = `073c0e22…` 双向一致 |
| 公网 health | ok | ok |
| **JWKS 公钥** | 5 个 | 5 个，**kid 同名**（含 `cert-built-in`） |
| OIDC discovery | 正常 | 端点未变 |
| **DB 表数** | 44 | 47（迁移新增 3 张） |
| **DB 用户/应用/证书** | 42 / 2 / 5 | 42 / 2 / 5（无丢失） |
| 13 个代理 | — | 重启数未增加；20 分钟内日志无 OIDC 报错 |
| 登录链路 | — | 11 个域名 302 → `auth.panghuer.top`，`client_id` 与 secret 一致 |

## 三、迁移日志怎么读

xorm 的 `Sync2` 在启动时自动迁移表结构。判定"迁移安全"的四条：

| 观测 | 本次结果 | 说明 |
|---|---|---|
| 日志级别 | 只有 `[warn]` 与一条 `[info]` | **红线是 `error` / `panic` / `fatal`**——本次一条都没有 |
| 表数量 | 44 → 47 | **只增不减**；新增 3 张是 v4 需要的 |
| 业务计数 | 用户 42 / 应用 2 / 证书 5，前后一致 | 迁移没动业务数据 |
| JWKS | 5 个公钥，**kid 同名** | 签名证书未被重新生成 → **已登录用户不会被强制踢下线** |

本次实际出现的告警（都无害）：

- 若干老 schema 的列类型漂移 `[warn]`；
- `[info] Table provider column scopes change type from varchar(100) to varchar(200)`。

## 四、`progress deadline exceeded` 是**滞后误报**

本次 `rollout status` 报了 `error: deployment "casdoor" exceeded its progress deadline`，
但那是**镜像还没推进 registry 时的等待超时**，不是故障：

- `rollout status` 的默认窗口（600s）量的是「**旧 Pod 终止 + 新 Pod ready**」这个整体；
  新 Pod 一直 `ImagePullBackOff` 时，它必然先超时；
- 镜像推上去后 **kubelet 原地把那个 Pod 拉起来**：Pod 名未变（`casdoor-86d4fb48d-zfkth`）、
  重启次数 0、启动时间就是镜像可拉取的那一刻；
- 所以看到这个报错时：**不要急着回滚，也不要删 Pod**，先看 `describe pod` 的 Events
  与镜像是否真的已进入私有 registry。

> 顺带一条流程教训：**先把镜像推进 registry，再 apply 改过 tag 的清单**。
> 顺序颠倒就会白白经历一次"清单已指向新版本、镜像还没有"的窗口。

## 五、回滚方法（注意 `:latest` 已不可用）

升级过程中 `build.sh` 会把新版本同时覆盖成 `casdoor:latest`，所以私有 registry 里的
`casdoor:latest` **现在指向 4.11.0** —— `kubectl rollout undo` 回不到 3.113.0。
（`build.sh` 已修：不再覆盖 `:latest`。）

正确的回滚：

```bash
docker pull docker.m.daocloud.io/casbin/casdoor:3.113.0    # Docker tag 不带 v；已确认可取
docker tag  docker.m.daocloud.io/casbin/casdoor:3.113.0 arm-cluster-master:5000/casdoor:3.113.0
docker push arm-cluster-master:5000/casdoor:3.113.0
kubectl -n oauth set image deploy/casdoor casdoor=arm-cluster-master:5000/casdoor:3.113.0
```

## 六、本次踩的三个坑（均已在代码里修掉）

| 坑 | 症状 | 修法 |
|---|---|---|
| **tag 形状** | 拉 `v4.11.0` → 各加速源 403/404 → fallback 到 `registry-1.docker.io` → 报一个**与真实原因无关的** `EOF` | 用 `4.11.0`：Casdoor CI 去掉 release tag 的 `v`（`build.yml`: `version=${GITHUB_REF_NAME#v}`） |
| **加速前缀带 scheme** | `docker pull https://docker.m.daocloud.io/...` → `invalid reference format` | 前缀只填主机名；`build.sh` 已自动剥掉 `https://` / `http://` |
| **`:latest` 被覆盖** | 每升级一次就抹掉一次回滚点 | `build.sh` 不再推 `:latest`（清单全部固定不可变 tag，无人再用它） |

另：`debian_begin.sh` 生成的 daemon.json 原有 4 个 mirror，其中 `registry.docker-cn.com`
（2024 年即停服）与 `registry.aliyuncs.com`（**不是** Hub 加速器）是坏的，已换成实测可用的四项。

## 七、下次升级照这个清单做

```bash
# 1) 备份 + 记下"升级前"基线
kubectl -n oauth exec deploy/mysql -- mysqldump -uroot -p"$PW" casdoor > /tmp/casdoor-db-$(date +%F).sql
kubectl -n oauth get deploy casdoor -o yaml > /tmp/casdoor-rollback.yaml
kubectl -n oauth get deploy casdoor -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
kubectl -n oauth get endpoints casdoor

# 2) 取镜像并推送（默认已走加速源；Docker tag 不带 v）
CASDOOR_TAG=<新版本> bash oauth/build.sh

# 3) **确认镜像真的进了私有 registry 再往下**
docker manifest inspect arm-cluster-master:5000/casdoor:<新版本> >/dev/null && echo ok

# 4) 改清单 tag（与 build.sh 默认值保持一致）并 apply
kubectl apply -f oauth/k8s/casdoor-deployment.yaml
kubectl -n oauth rollout status deploy/casdoor --timeout=600s

# 5) 验证：按 §一 的五条 + §三 的四条逐项核
```

## 八、顺带发现：两个域名没发布（与本次升级无关）

| 域名 | 现象 | 原因 |
|---|---|---|
| `tewu.panghuer.top` | 公网超时 | [tunnel-routes.yaml](../../cloudflare-tunnel/operator/tunnel-routes.yaml) 里有这条路由（**备份**），但 **Cloudflare 后台没有对应的 Public Hostname**——本文件只是备份、不生效 |
| `baijiazhengming.panghuer.top` | SSL 握手失败 | 仓库里**从未有过**这条路由，应用侧也没有 host 白名单——等于没发布过 |

两个域名**在集群内**从 Casdoor Pod 直连服务都是正常 302 → `auth.panghuer.top`，
说明代理与 OIDC 链路是好的，问题只在 Cloudflare 边缘那一段。

> ⚠️ `baijiazhengming` 光加 Public Hostname 还不够：共享 UI 按 Host 查
> `panghu_agent/baijiazhengming/registry.yaml` 的白名单，该 host 不在表里，
> 指过去只会渲染「当前域名未登记」。要做统一入口，得先补 host 映射或做路径分段
> （见 [../../docs/oauth-proxy-consolidation.md](../../docs/oauth-proxy-consolidation.md)）。
