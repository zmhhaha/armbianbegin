在 Casdoor 中配置第三方登录（OAuth）非常直观，核心都是在 **“提供商”** 页面添加对应类型的提供商，然后将其添加到你的应用中。

以下分别是 GitHub、支付宝和微信的配置方法。

### 🐙 配置 GitHub 登录
这是三者中最简单的，因为 GitHub 的 OAuth 流程非常标准。

1.  **创建 GitHub App**：
    *   前往 GitHub 的 **Developer Settings** 创建一个新的 GitHub App。
    *   填写 App 名称、主页 URL 等基本信息。
    *   关键步骤：在 GitHub App 的设置中，将 **`Callback URL`** 设置为你的 Casdoor 回调地址。这个地址通常为 `https://<你的Casdoor域名>/api/login/oauth`。
    *   创建完成后，生成并记录 **`Client ID`** 和 **`Client Secret`**。

2.  **在 Casdoor 中添加提供商**：
    *   在 Casdoor 管理后台，进入 **提供商** -> **添加**。
    *   将 **类别 (Category)** 选为 `OAuth`，**类型 (Type)** 选为 `GitHub`。
    *   在 **Client ID** 和 **Client Secret** 字段中，填入上一步从 GitHub App 获取的信息。
    *   保存即可。

### 💰 配置支付宝登录
支付宝的登录（Alipay OAuth）基于证书模式，配置会稍微复杂一些。

1.  **获取支付宝开放平台凭证**：
    *   登录 [支付宝开放平台](https://open.alipay.com/) 并创建一个应用。创建后，记录下 **`APPID`**。
    *   按照支付宝文档生成 RSA2 密钥对。你会得到应用私钥 (`appPrivateKey.txt`) 和应用公钥 (`appPublicKey.txt`)。
    *   将应用公钥上传到支付宝应用，并下载支付宝提供的三个证书文件：
        *   `alipayRootCert.crt` (支付宝根证书)
        *   `appCertPublicKey.crt` (应用公钥证书)
        *   `alipayCertPublicKey.crt` (支付宝公钥证书)

2.  **在 Casdoor 中创建证书 (Certs)**：
    *   在 Casdoor 管理后台，进入 **证书 (Certs)** -> **添加证书**。
    *   **App Cert (应用证书)**：
        *   **类型 (Type)**：`x509 Certificate`
        *   **证书 (Certificate)**：填入 `appCertPublicKey.crt` 文件的内容。
        *   **私钥 (Private Key)**：填入 `appPrivateKey.txt` 文件的内容。
    *   **Root Cert (根证书)**：
        *   **类型 (Type)**：`x509 Certificate`
        *   **证书 (Certificate)**：填入 `alipayCertPublicKey.crt` 文件的内容。
        *   **私钥 (Private Key)**：填入 `alipayRootCert.crt` 文件的内容。

3.  **在 Casdoor 中添加提供商**：
    *   进入 **提供商** -> **添加**。
    *   将 **类别 (Category)** 选为 `OAuth`，**类型 (Type)** 选为 `Alipay`。
    *   在 **Client ID** 字段中填入你的支付宝 `APPID`。
    *   在 **App Cert** 和 **Root Cert** 字段中，选择你刚刚创建的两个证书。

### 💬 配置微信登录
微信的配置需要区分两种登录场景。

1.  **获取凭证**：
    *   前往微信开放平台，注册开发者账号并创建网站或移动应用。审核通过后，你将获得 **`AppID`** 和 **`AppSecret`**。

2.  **在 Casdoor 中添加提供商**：
    *   进入 **提供商** -> **添加**。
    *   将 **类别 (Category)** 选为 `OAuth`，**类型 (Type)** 选为 `WeChat`。
    *   Casdoor 的微信提供商有两套密钥对：
        *   **第一套 (`Client ID` / `Client Secret`)**：用于 **PC 端扫码登录**（微信开放平台）。填入你在微信开放平台获取的 `AppID` 和 `AppSecret`。
        *   **第二套 (`Client ID 2` / `Client Secret 2`)**：用于 **微信内网页登录**（微信公众平台）。如果你想支持用户在微信内置浏览器中直接登录，可以额外配置。请注意，这一般需要服务号并配置回调域名。

### 🔗 通用最后一步：将提供商关联到应用
无论配置哪种登录方式，完成上述步骤后，都**必须**将提供商添加到你的应用中才能生效。

*   进入 **应用** 页面，编辑你的应用。
*   在 **提供商 (Providers)** 区域，点击添加，从列表中选择你刚刚创建好的 GitHub、支付宝或微信提供商。
*   保存应用即可。

---

### 💎 总结与注意事项

1.  **回调地址 (Callback URL) 是核心**：在第三方平台（如 GitHub/支付宝）配置时，**必须**将回调地址（`Redirect URI`）正确设置为你的 Casdoor 地址，通常是 `https://<你的casdoor域名>/api/login/oauth`。同时，在 Casdoor 应用配置中，**重定向 URL (Redirect URL)** 也要设置为你的**业务应用**的回调地址。
2.  **注意微信的“第二套”密钥**：微信登录的“第二套密钥”（`Client ID 2` / `Client Secret 2`）是为**微信内网页**场景设计的。如果你只是想在普通网页上提供扫码登录，配置第一套即可。
3.  **支付宝需要证书**：支付宝登录强制使用证书模式，因此必须在 Casdoor 中正确创建并关联证书。
4.  **遇到问题看日志**：如果配置后无法登录，首先检查 Casdoor 和第三方平台的回调地址是否完全一致，并查看 Casdoor 的日志获取详细错误信息。

按照这些步骤操作，你应该能顺利配置好 GitHub、支付宝和微信的第三方登录。如果遇到具体报错，可以随时再问我。