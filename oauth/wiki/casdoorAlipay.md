# 在 Casdoor 中配置支付宝登录（**当前不可用**）

> ## ⚠️ 现在不要照这份文档配置
>
> **2026-09-29 结论：这套集成从未正常使用，已放弃。**
> 照 §三 配完，登录时会稳定报 `asn1: syntax error: sequence truncated`。
>
> **根因在上游 Casdoor**：`idp/alipay.go` 的 `rsaSignWithRSA256()` 只用
> `x509.ParsePKCS8PrivateKey()` 解析私钥，失败就 `return "", err`，**没有回退到
> `x509.ParsePKCS1PrivateKey()`**。阿里云密钥工具生成的私钥在部分环境下会让 PKCS#8
> 解析失败，于是直接崩在这一步。已核对：**上游 v4.11.0 仍未修**（该函数与 v3.113.0 逐字相同）。
>
> 本文**保留作为调研记录**。以后想重新加支付宝登录，请先做 §四 的调研，不要直接照 §三 配。

## 一、历史调研：为什么不可用

| 项 | 结论 |
|---|---|
| 症状 | 支付宝 OAuth 绑定时报 `asn1: syntax error: sequence truncated` |
| 触发点 | `idp/alipay.go` → `rsaSignWithRSA256()` → `x509.ParsePKCS8PrivateKey(block.Bytes)` |
| 上游行为 | 解析失败**直接返回错误，无 PKCS#1 回退** |
| 为什么会解析失败 | 阿里官方密钥工具生成的是 PKCS#8（RFC5208）DER；Casdoor 的 `formatPrivateKey()` 给它加上 PKCS#8 PEM 头后再交给 `ParsePKCS8PrivateKey()` —— 部分环境下这一步就是解析失败 |
| 上游是否已修 | ❌ **没有**：v4.11.0 与 v3.113.0 的该函数逐字相同（2026-09-29 核对） |
| 当时的绕过 | 自编译打补丁：PKCS#8 失败后回退 PKCS#1（见 §二） |
| 最终决定 | **放弃**（所有者 2026-09-29）：该集成从未真正跑通，长期维护一个自编译 Casdoor 二进制不划算 |

## 二、当时尝试过的修法（脚本已删除，仅留记录）

补丁内容 —— `idp/alipay.go` 的 `rsaSignWithRSA256`：

```go
// 修复前
privateKeyRSA, err := x509.ParsePKCS8PrivateKey(block.Bytes)
if err != nil {
    return "", err
}

// 修复后
privateKeyRSA, err := x509.ParsePKCS8PrivateKey(block.Bytes)
if err != nil {
    privateKeyRSA, err = x509.ParsePKCS1PrivateKey(block.Bytes)
    if err != nil {
        return "", fmt.Errorf("failed to parse private key (tried PKCS8 and PKCS1): %w", err)
    }
}
```

> ⚠️ `formatPrivateKey()` **不能改**：它保持 `-----BEGIN PRIVATE KEY-----`（PKCS#8 头）是对的，
> 因为阿里工具产出的确实是 PKCS#8，只是解析端缺回退。

构建方式：`git clone` 上游 → `sed` 打补丁 → 用 `golang:1.25` 交叉编译静态链接 arm64 二进制
→ `docker cp` 进 `casdoor:latest` 镜像的 `/server` → `docker commit` / `push` 成
`casdoor:fix-alipay` → `kubectl set image`。

**这套脚本（`oauth/casdoor_fix/`：`build-fix.sh`、`deploy-fix.sh`、`Dockerfile_fix`、`README.md`）
已于 2026-09-29 删除。** 删除的另一个原因是它本身有三个缺陷：

1. `sed` 打补丁**不校验** —— 上游一改那段代码就会静默编出"声称修好、实际没修"的二进制；
2. 二进制来自 `git clone` 的**默认分支 HEAD**，而基础镜像是按 tag 拉的 → **二进制版本与镜像 tag 可能不一致**；
3. 镜像 tag 与清单漂移：清单写 `casdoor:latest`，部署却用 `casdoor:fix-alipay`；叠加
   `imagePullPolicy: Always`，"实际跑哪个版本"根本不由清单决定。

> 需要那些脚本时从 git 历史取：
> `git show 385dbd9^:oauth/casdoor_fix/README.md`（同法可取其余三个文件）。

## 三、配置步骤（原文记录，**当前不可用，勿照做**）

在 Casdoor 中配置支付宝登录，需要先准备好支付宝开放平台的应用凭证和证书，然后在 Casdoor 中创建对应的证书和 OAuth 提供者。详细步骤如下：

### 📝 第一步：在支付宝开放平台获取凭证与证书

1.  **获取 APPID**：登录 [支付宝开放平台](https://open.alipay.com/) 控制台，创建一个网页应用。创建成功后，在应用详情页即可找到并记录下 **`APPID`**。
2.  **生成并上传密钥**：按照支付宝文档生成一套 **RSA2** 密钥对，你会得到两个文件：
    *   `appPrivateKey.txt` (应用私钥)
    *   `appPublicKey.txt` (应用公钥)
    将 `appPublicKey.txt`（应用公钥）上传到你的支付宝应用中。
3.  **下载证书**：上传公钥后，在支付宝应用中可以下载三个证书文件：
    *   `alipayRootCert.crt` (支付宝根证书)
    *   `appCertPublicKey.crt` (应用公钥证书)
    *   `alipayCertPublicKey.crt` (支付宝公钥证书)

### 🔑 第二步：在 Casdoor 中创建证书 (Certs)

支付宝的 OAuth 登录基于证书模式，因此需要将上一步获取的证书和私钥配置到 Casdoor 中。

1.  登录 Casdoor 管理后台，进入 **证书 (Certs)** 页面，点击 **添加证书 (Add)**。
2.  你需要创建两个证书，配置如下：

**证书一：App Cert (应用证书)**

| 字段 | 值 |
| :--- | :--- |
| **名称 (Name)** | 自定义，例如 `alipay-app-cert` |
| **类型 (Type)** | `x509 Certificate` |
| **证书 (Certificate)** | 填入 `appCertPublicKey.crt` 文件的**全部内容** |
| **私钥 (Private Key)** | 填入 `appPrivateKey.txt` 文件的**全部内容** |

**证书二：Root Cert (根证书)**

| 字段 | 值 |
| :--- | :--- |
| **名称 (Name)** | 自定义，例如 `alipay-root-cert` |
| **类型 (Type)** | `x509 Certificate` |
| **证书 (Certificate)** | 填入 `alipayCertPublicKey.crt` 文件的**全部内容** |
| **私钥 (Private Key)** | 填入 `alipayRootCert.crt` 文件的**全部内容** |

### ⚙️ 第三步：在 Casdoor 中创建 OAuth 提供者 (Provider)

1.  进入 Casdoor 后台的 **提供者 (Providers)** 页面，点击 **添加提供者 (Add)**。
2.  配置支付宝 OAuth 提供者：

| 字段 | 值 |
| :--- | :--- |
| **类别 (Category)** | 选择 `OAuth` |
| **类型 (Type)** | 选择 `Alipay` |
| **客户端ID (Client ID)** | 填入第一步获取的 **`APPID`** |
| **应用证书 (App Cert)** | 选择上一步创建的 **App Cert** (例如 `alipay-app-cert`) |
| **根证书 (Root Cert)** | 选择上一步创建的 **Root Cert** (例如 `alipay-root-cert`) |

### 🔗 第四步：将提供者添加到你的应用 (Application)

1.  进入 Casdoor 后台的 **应用 (Applications)** 页面，找到并编辑你需要开启支付宝登录的应用。
2.  在应用编辑页面的 **提供者 (Providers)** 区域，点击 **添加 (Add)**。
3.  从列表中选择你刚刚创建的支付宝 OAuth 提供者，并保存应用配置。

### 🔄 第五步：配置回调 URL (Callback URL)

这是确保授权流程能跳转回你网站的关键一步。

1.  **在 Casdoor 中**：你的应用配置页面中，**重定向 URL (Redirect URL)** 需要设置为你的应用自身的回调地址。
2.  **在支付宝开放平台**：在你的支付宝应用**开发设置**中，找到 **授权回调地址**，将其设置为 Casdoor 的回调 URL。这个地址通常是 `https://<你的Casdoor域名>/api/callback`。

### ⚠️ 故障排查

如果配置后登录失败，可以检查以下几点：
*   **证书内容**：确认 `Certificate` 和 `Private Key` 字段粘贴的是正确文件的内容，没有多余空格或换行。
*   **APPID**：确认 Casdoor 中填写的 `Client ID` 与支付宝应用详情页的 `APPID` 完全一致。
*   **回调地址**：确认 Casdoor 应用的回调地址与支付宝应用设置的授权回调地址完全一致。

> 补充：当年这份排查清单**没能解决问题** —— 真正的失败点在服务端私钥解析，与上面三条都无关。
> 再遇到同样的报错，直接看 §一。

## 四、以后想重新加：先做这些调研

1.  **确认上游是否已修**：拉当时的 Casdoor tag，看 `idp/alipay.go` 的 `rsaSignWithRSA256`
    有没有 PKCS#1 回退。**修了就不需要任何自编译镜像**，一切从简。
2.  **换一把私钥**：用 `openssl genrsa`（PKCS#1）而不是阿里云工具生成，或把 PKCS#8 显式转成
    PKCS#1，看能否绕开解析失败。**这是不碰 Casdoor 代码的捷径，优先试。**
3.  **确认支付宝应用形态**：现在需要网页应用 + 证书模式，还是可以用更简单的密钥模式；
    支付宝开放平台的规则这些年一直在变，§三 的步骤未必还适用。
4.  **评估认证面**：能不能不引入新 provider。当前 `panghu-suite` 的 TokenFormat 是
    `JWT-Custom` + 字段白名单，加 provider 时注意别让新的第三方 token 混进 JWT
    （见 [casdoor不下发第三方token.md](casdoor不下发第三方token.md)）。
5.  **算清维护成本**：只要上游没修，就意味着要**长期维护一个自编译 Casdoor 镜像**，并在
    每次升级时重打补丁。**第 1 条没通过之前，不要开工。**