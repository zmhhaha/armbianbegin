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