# 受控 Git 访问调研：让 DSH 与 Hermes 能改代码并推送

> **需求（2026-09-25，所有者提出）**：DSH 与 Hermes 后续都要能**修改代码并推送到 Git 仓库**。本文回答三件事——给到什么权限、以什么形状给、以及**能不能不把凭据交给它们**。

- 调研日期：2026-09-25
- 代码基准：`armbianbegin` HEAD `0efb256`；`panghu_chat` 子模块 HEAD `94f8dc4`
- 起因：DSH 容器里用 GitHub 的 **SSH 地址** clone 失败（`Permission denied (publickey)`），追问后需求扩大为"两个服务都要能推"

---

## 结论摘要（TL;DR）

1. **SSH 地址本来就不适用于"拉公开仓库"。** GitHub 的 SSH **对公开仓库同样要认证**——不存在匿名的 SSH clone。**在没注册任何密钥的前提下，`Permission denied (publickey)` 就是唯一可能的结果**，不是配置漏了。
2. **真正需要凭据的只有 push**（以及拉私有仓库）。拉公开仓库用 HTTPS 匿名即可——工作站实测通过；**容器内在修掉那个错误 URL 之后尚未重跑**（见 §四）。
3. **凭据在服务里藏不住。** agent 与 git 是**同一个 uid 10000 进程**——git 能读到的，agent 代码都能读到。**没有一种挂载方式、文件权限或 Secret 形态能改变这一点**，只能压缩爆炸半径。
4. **推荐粒度**：细粒度 PAT，**只授 `Contents: Read and write`**，**只覆盖该服务真正要推的仓库**，**设到期日**。除 `Contents` 外一律不给。
5. **DSH 应做到"一项目一把"**——它本来就是每项目一个持久容器，天然可以一项目一把只对该项目仓库的 key。
6. **Hermes 目前完全不碰 git**（见 §二），给它挂 git 凭据是给一个用不上的服务发授权。要先确认它推什么。
7. **不要 GPG。** GPG 只影响 "Verified" 徽章，不参与认证授权；而签名私钥本身就是一条凭据，是笔独立买卖。
8. **`user.name` / `user.email` 不是凭据**，只决定提交归属；按本仓库约定走 **ConfigMap**，不进 Vault。
9. **子模块配的是 SSH URL，会连"读"一起挡住**（`.gitmodules` 三个都是 `git@github.com:`）。但这四个仓库都是公开的，容器侧一句 `url."https://github.com/".insteadOf "git@github.com:"` 就解决，**仍然不需要任何凭据**；**不要去改 `.gitmodules`**，那会连带改掉所有者工作站的 push 方式。见 §4.1。

---

## 一、先澄清两件常被当成凭据的东西

| 东西 | 实际作用 | 能不能换来推送权限 |
|---|---|---|
| `user.name` / `user.email` | 写进 commit 元数据的**标签**，任何值都合法 | ❌ 完全不参与认证 |
| GPG 密钥 | 给提交**签名**（"Verified" 徽章） | ❌ 与认证授权无关 |

`user.email` 唯一有实际后果的地方是**归属**：邮箱必须是 GitHub 账号**验证过的**，提交才会算到你名下。如果它不是你账号里的邮箱，提交照样能推上去，只是不归属。

> ⚠️ 而且**归属不等于来源证明**——agent 可以写任何 `user.name`。不要把 commit 作者当成"这条改动是人做的"的证据。

---

## 二、仓库内实证

### 2.1 现有边界：出站凭据是被**刻意**排除的

| 证据 | 内容 |
|---|---|
| `panghu_chat/dsh/README.md:28` | **只处理公开仓库**：HTTPS clone、本地提交；**推送由所有者在本仓库外完成**。不注入 Git 写凭据、SSH agent 或个人凭据助手 |
| `panghu_chat/dsh/docs/ssh-remote.md:502` | 客户端私钥只在 `dsh-ssh-client`（`dsh` 命名空间），**不在 runner**；主机私钥与 `authorized_keys` 在 `dsh-ssh-host`。两半互不交叉、**"哪一侧可以持有"是设计语言** |
| `panghu_chat/dsh/README.md:83-86` | 密钥对来自同一个 Vault 路径，由两个 ExternalSecret 按持有侧拆开 |

⇒ **`/state/keys` 里的东西是"谁能进来"（容器**被**认证）；"容器是谁"这一侧是刻意留空的。** 本次需求是在**改边界**，不是补一个漏掉的步骤——所以应该先改 `design.md` / `boundaries.md`，再动实现。

### 2.2 为什么藏不住：agent 与 git 同 uid

| 证据 | 内容 |
|---|---|
| `panghu_chat/dsh/runner/Dockerfile` | `useradd --uid 10000 --create-home --shell /bin/bash --home-dir /workspace dev`；文件末尾 `USER 10000`、`WORKDIR /workspace` |
| `panghu_chat/dsh/templates/runner.yaml` | `HOME=/workspace`（持久项目卷）、`runAsUser: 10000`、`readOnlyRootFilesystem: true` |
| `panghu_chat/dsh/docs/closeout-2026-09-23.md` | 会话运行在 `danger-full-access`；**边界由 Kubernetes 容器承担**，不是 DSH 内层 |

⇒ 结论是同义反复但必须说透：**git 和 agent 是同一个进程身份**。任何 git 能读到的凭据，agent 代码都能读到；而根文件系统是只读的，所以密钥只能落在 `/workspace`（持久卷、可写、agent 的主场）。**目标不是"藏住"，是"万一泄了，最坏能坏到哪"。**

### 2.3 入站 sshd 的转发设置（解释"为什么借不到宿主密钥"）

`panghu_chat/dsh/runner/sshd_config`：

| 行 | 设置 | 含义 |
|---|---|---|
| 52 | `AllowAgentForwarding no` | **服务端显式关闭**——即使宿主机开着 `ssh-agent`，也透传不进来 |
| 48 | `AllowTcpForwarding yes` | DSH 的 streamlocal 转发需要它（见同文件 35 行的注释） |
| 59 / 61 | `PubkeyAuthentication yes` / `PasswordAuthentication no` | 只认公钥 |
| 64 | `PermitRootLogin no` | |

> 注意这是**入站**方向。本次要解决的是**出站**凭据，两者独立；关掉 agent 转发并不妨碍"在容器里放一把出站密钥"。

### 2.4 出站策略并不拦端口

`panghu_chat/dsh/k8s/networkpolicies.yaml` 的 `runner-egress`：公网规则是 `ipBlock: 0.0.0.0/0` + except 私网段，`ports: - protocol: TCP`——**没有端口限制**，注释里写明"包管理器、VCS 和语言工具链各自选端口"。所以**网络策略不是那次 SSH 失败的原因**，这和实测一致（失败发生在认证阶段）。

### 2.5 Hermes 与 git 无关

搜索 `panghu_chat/hermes/` 全目录，**没有任何 git / clone 调用**；它的出站是 HTTP 搜索与原文抓取。

> **更好的先例在同一仓库里**：`hermes-publisher` 是一个独立 Deployment，Hublog token 只在它手里，研究进程**读不到**——"agent 可以请求发布，但读不到 token"（`panghu_chat/hermes/k8s/native-publisher.yaml`、`app/delivery.py`）。**git push 是同一道题，有同一个形状的答案**，见 §五。

---

## 三、权限粒度对照

| 粒度 | 授予什么 | 泄漏后最坏情况 | 结论 |
|---|---|---|---|
| 账号级 SSH key | 你账号的读写身份 | **账号下所有仓库**都能推，还能动仓库设置 | ❌ 不用 |
| classic PAT（`repo` 范围） | 私有仓库完全控制 | 同上 | ❌ 不用 |
| **细粒度 PAT**：`Contents: Read and write`，限定仓库 | 指定仓库的内容读写 | **那一个仓库**的内容能改 | ✅ **推荐** |
| Deploy key（勾 Allow write access） | 单个仓库的读写 | 同上；但**不过期**、需逐仓管理 | ✅ 可行，见 §四 |
| GitHub App 安装令牌 | 选定仓库、选定权限，**约一小时内失效** | 同上，且窗口极短 | ✅ 最稳，需发令牌的组件 |

### 3.1 三个必须避开的坑

1. **不要给 `Workflows` 权限。** 有了它就能推 `.github/workflows/*`，而**推 workflow 文件 = 往那个仓库的 CI 里注入可执行代码**。这是整套权限里最锋利的一条边——比"改代码"危险得多。除非确实要改 workflow，否则明确不勾。
2. **别把有 secrets 的 CI 仓库交出去。** 能推代码就能让 CI 跑起来，而 CI 通常持有部署凭据。给 agent 推的仓库，最好**没有 Actions，或 Actions 里没有敏感 secret**。
3. **别把 token 塞进 remote URL。** `https://x-access-token:TOKEN@github.com/…` 会写进 `.git/config`，还会在 `git remote -v` 和 `ps` 里露出来。用 credential helper 从只读挂载的文件读：

   ```sh
   git config --global credential.helper \
     '!f() { echo username=x-access-token; echo "password=$(cat /run/secrets/gh-token)"; }; f'
   ```

### 3.2 按服务分别定，不要一把通吃

- **DSH**：本来就是**每项目一个持久容器**（`templates/runner.yaml` 由 `provision.sh` 按项目渲染），所以可以做到**一项目一把只对该项目仓库的 key**。一把 key 泄了伤不到别的项目——这是本方案里最值得采用的一点。
- **Hermes**：**先确认它推什么**。如果只是把生成的内容提交到某个仓库，那形状和"改代码"不同，给它那个内容仓库的一把 deploy key 就够，不必与 DSH 共用。

---

## 四、传输：SSH 还是 HTTPS

**实测记录（**注意每条是在哪里测的**——把工作站的结果当成容器内的结果，正是本仓库反复踩过的那类错误）**：

| 项 | 在哪测的 | 结果 |
|---|---|---|
| 公开仓库 HTTPS clone（`jonschlinkert/is-number`） | 工作站（同网络） | ✅ 成功 |
| 公开仓库 HTTPS `ls-remote`、git 协议路径（`/info/refs?service=git-upload-pack`） | 工作站（同网络） | ✅ 成功，200，穿过 fake-ip 地址 `198.18.0.246` |
| `sindresorhus/is-number`（该仓库不公开／不存在） | 工作站（同网络） | 401——**GitHub 对私有或不存在的仓库一律回 401** |
| **GitHub SSH clone** | **项目容器内**（所有者报告，2026-09-25） | ❌ `Permission denied (publickey)`；**SSH 握手完整走完，失败在认证阶段** |
| HTTPS HEAD 到 GitHub／npm mirror | 项目容器（`closeout-2026-09-23.md`） | 301 / 302 |
| 任意公网地址:端口 | 工作站（同网络） | CONNECTED（连 `192.0.2.1` 等不可路由测试段也是）——**软路由透明代理**，所以"可达"只证明包离开了容器 |

> ⚠️ **还欠一条**：容器内的**公开仓库 HTTPS clone 在修掉那个错误 URL 之后尚未重跑**。上文"HTTPS 可用"在工作站成立、在容器内有旁证（HEAD 返回 301），但**没有一次端到端的容器内成功记录**。这与 `add-dsh-private-k8s-workbench` 里"公开仓库克隆、依赖安装…"那条验收项是同一件事。

**建议走 HTTPS + credential helper**，理由：不走 SSH 就不需要 `known_hosts`、不需要 `~/.ssh/config`，而且吃的是**已经实测可用**的 443。

> ⚠️ **未验证的外部推断**：普遍经验是**大陆链路上 GitHub 的 22 端口不稳**，常见绕法是 `~/.ssh/config` 里把 `github.com` 指到 `ssh.github.com:443`。**本仓库没有对这个网络做过这项实测**，所以仅作为"若坚持 SSH 时的备选"，不作为结论。

### 4.1 子模块配的是 SSH URL：会挡住容器里的**读**，但不需要凭据就能修

`.gitmodules` 里三个子模块全部是 SSH 形式：

| 子模块 | URL |
|---|---|
| `panghu_agent` | `git@github.com:zmhhaha/panghu_agent.git` |
| `panghu_game` | `git@github.com:zmhhaha/panghu_game.git` |
| `panghu_chat` | `git@github.com:zmhhaha/panghu_chat.git` |

`git clone --recurse-submodules` 会照着 `.gitmodules` 走 SSH → 容器里没有密钥 → `Permission denied (publickey)`。**于是"读"也被挡住了，尽管读本来不需要任何凭据。**

**但这四个仓库都是公开的。** 2026-09-25 实测，匿名 HTTPS `ls-remote`（无凭据、`GIT_TERMINAL_PROMPT=0`、`-c credential.helper=`）：

| 仓库 | 结果 |
|---|---|
| `zmhhaha/panghu_agent` | ✅ 返回 HEAD |
| `zmhhaha/panghu_game` | ✅ 返回 HEAD |
| `zmhhaha/panghu_chat` | ✅ 返回 HEAD |
| `zmhhaha/armbianbegin` | ✅ 返回 HEAD |

所以修法是**在容器一侧做 URL 重写**，而不是改 `.gitmodules`：

```sh
git config --global url."https://github.com/".insteadOf "git@github.com:"
```

- **不要改 `.gitmodules`。** 那会把所有者自己工作站上的 `push` 也改成 HTTPS，而工作站是靠 SSH 密钥推的。**重写留在容器侧**：工作站保持 SSH、容器走匿名 HTTPS，两边同时满足，且**容器里仍然没有任何凭据**。
- 不想落盘可以用环境变量注入（git ≥ 2.31）：`GIT_CONFIG_COUNT=1`、`GIT_CONFIG_KEY_0=url.https://github.com/.insteadOf`、`GIT_CONFIG_VALUE_0=git@github.com:`。
- 已经 init 过的子模块：`insteadOf` 在 git **解析 URL 时**生效，所以它们也会跟着走 HTTPS。万一没生效，用 `git submodule sync` 刷新其 `remote.origin.url`。
- ⚠️ **重写对 `push` 同样生效。** 加了之后容器里的 `git push` 也会走 HTTPS、因而需要凭据——方向与 §三 一致，但要知道它改的不只是读。

---

## 五、架构：直接挂进服务，还是隔离的推送路径

| 形状 | agent 能读凭据吗 | 代价 |
|---|---|---|
| **直挂**：Secret → 挂进 runner / Hermes pod | **能**（同 uid，无法避免） | 最小。适合"愿意接受半径 = 一个仓库" |
| **隔离推送路径**：独立组件持凭据，服务只能**请求**推送 | **不能** | 要新增 Deployment + Vault 条目 + 验收项。**照 `hermes-publisher` 的现成形状** |
| **GitHub App 安装令牌**：短时令牌按需签发 | 令牌本身仍可读，但**约一小时失效** | 需要发令牌的组件；可与上面两者叠加 |

三者可以组合：**隔离路径 + App 短时令牌**是半径最小的组合（凭据读不到、令牌还会过期）。

---

## 六、动手前先确认清单

- [ ] **推哪些仓库**——逐仓列出。DSH 是按项目一一对应，还是几个项目共用一个仓库？Hermes 推哪个？
- [ ] **Hermes 推什么内容**——代码，还是生成的内容？后者不需要 `WORKFLOWS` 之类的任何额外权限。
- [ ] **仓库上有没有 Actions / CI secrets**——有就先确认"能推代码"不会顺带拿到部署凭据。
- [ ] **勾权限时只勾 `Contents: Read and write`**，不勾 `Workflows`、`Administration`、`Actions`、`Secrets`。
- [ ] **设到期日 + 记轮换**——凭据被 agent 读过就算"可能已泄露"，到期与轮换是主要止损手段。
- [ ] **撤销演练**——想清楚"发现异常后几秒钟内怎么撤销"，并确认那条路径今天就能走通。
- [ ] **`user.name` / `user.email` 进 ConfigMap**（不是 Vault），邮箱用你账号验证过的那个。
- [ ] **先改文档再改实现**：`panghu_chat/dsh/README.md:28` 与 `docs/boundaries.md` 现在写的是"不注入 Git 写凭据""推送由所有者在本仓库外完成"，这是**改边界**，要同步 `add-dsh-private-k8s-workbench` 的 design / proposal。
- [ ] **同步 OpenSpec**：本调研是文档，**不等于改了 change**——见 `AGENTS.md` 与 `.openspec-project.json`。

---

## 七、未定项

| 项 | 状态 |
|---|---|
| 推哪些仓库、Hermes 推什么 | **待所有者确认**（决定范围，范围定不下来无法实施） |
| 走 A（deploy key，SSH）／B（细粒度 PAT，HTTPS）／C（隔离推送路径） | **待定**；§三、§四、§五 给了取舍依据 |
| 是否要 "Verified" 徽章 | 待定。要就得单独引入 GPG 签名私钥，**那本身也是一条 agent 可读的凭据** |
| 大陆链路 22 端口是否真的不稳 | **未在本仓库实测**，需要时按 §四 的备选处理 |

---

## 附：与本文相关的既有材料

| 材料 | 关系 |
|---|---|
| `panghu_chat/dsh/README.md` | DSH 的边界与凭据归属表（§28、83-86 行是本文的主要依据） |
| `panghu_chat/dsh/docs/boundaries.md` | DSH 网络边界设计；本文涉及的是**出站凭据**，与它的网络边界是两件独立的事 |
| `panghu_chat/dsh/docs/ssh-remote.md` | 传输层调研；§十、§十三解释内层沙箱与 `danger-full-access` |
| `panghu_chat/dsh/docs/closeout-2026-09-23.md` | 本文 §四 全部实测的来源 |
| `panghu_chat/hermes/k8s/native-publisher.yaml` | **凭据隔离的现成先例**，§五 的模板 |
| `docs/network-policy-engine.md` | fake-ip 与透明代理这两个读数陷阱的完整记录 |
