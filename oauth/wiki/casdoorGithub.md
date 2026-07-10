在 Casdoor 中配置 GitHub 登录是三种 OAuth 配置中最标准、最简洁的。下面为您提供从零开始的完整操作指南。

---

### 📝 第一步：在 GitHub 上创建 OAuth App

1.  **进入设置**：
    *   登录 GitHub 账号，点击右上角头像 -> **Settings**。
    *   在左侧边栏底部，点击 **Developer settings**。

2.  **创建新 App**：
    *   在 Developer settings 页面，点击左侧的 **OAuth Apps**。
    *   点击右上角的 **New OAuth App** 按钮。

3.  **填写 App 信息**：
    | 字段 | 填写内容 |
    | :--- | :--- |
    | **Application name** | 自定义应用名称，例如 `MyApp-Casdoor` |
    | **Homepage URL** | 您的应用主页地址，例如 `https://your-app.com` 或 Casdoor 首页 |
    | **Application description** | （可选）应用描述 |
    | **Authorization callback URL** | **关键！** 填写您的 Casdoor 回调地址，格式为 `https://<您的Casdoor域名>/callback`<br>例如：`https://casdoor.example.com/callback` |

4.  **生成凭证**：
    *   点击 **Register application** 完成创建。
    *   创建成功后，页面会显示 **Client ID**。点击 **Generate a new client secret** 生成 **Client Secret**。
    *   **请立即保存 Client Secret**，关闭页面后无法再次查看。

---

### ⚙️ 第二步：在 Casdoor 中添加 GitHub Provider

1.  **进入 Providers 页面**：
    *   登录 Casdoor 管理后台，在左侧菜单栏找到 **提供商 (Providers)**，点击进入。

2.  **添加新 Provider**：
    *   点击页面顶部的 **添加提供者 (Add)** 按钮。

3.  **配置 Provider 参数**：
    | 字段 | 值 |
    | :--- | :--- |
    | **名称 (Name)** | 自定义，例如 `github` |
    | **显示名称 (Display Name)** | 自定义，例如 `GitHub` |
    | **类别 (Category)** | 选择 `OAuth` |
    | **类型 (Type)** | 选择 `GitHub` |
    | **Client ID** | 填入上一步从 GitHub 获取的 **Client ID** |
    | **Client Secret** | 填入上一步从 GitHub 获取的 **Client Secret** |
    | **Scopes** | 保持默认 `user:email`（用于获取用户邮箱信息） |
    | **区域 (Region)** | 留空（国内可直接访问 GitHub） |

    *   **其他字段**保持默认即可。

4.  **点击保存 (Save)**，Provider 即创建完成。

---

### 🔗 第三步：将 Provider 添加到您的应用

1.  进入 Casdoor 后台的 **应用 (Applications)** 页面。
2.  找到并点击您需要开启 GitHub 登录的应用（例如 `app-built-in`）。
3.  在应用编辑页面，向下滚动到 **提供者 (Providers)** 区域：
    *   点击 **添加 (Add)** 按钮。
    *   在弹出的选择框中，勾选您刚刚创建的 GitHub Provider。
4.  滚动到页面底部，点击 **保存 (Save)**。

---

### 🔄 第四步：设置登录入口

1.  确保您的应用配置中，**登录方式 (Signin methods)** 包含 `GitHub`。
2.  访问您的应用登录页面，现在应该能看到 GitHub 登录按钮（GitHub 猫图标）。
3.  点击该按钮，应跳转到 GitHub 授权页面，授权后返回您的应用。

---

### 🧪 第五步：测试与验证

1.  打开应用登录页，点击 GitHub 图标。
2.  如果尚未登录 GitHub，会先跳转至 GitHub 登录页面。
3.  登录后，GitHub 会显示授权确认页面（告知您的应用请求的权限）。
4.  点击 **Authorize** 授权后，页面应跳转回您的 Casdoor 应用，且用户信息（头像、昵称、邮箱）被成功获取。

---

### ⚠️ 故障排查

| 问题 | 检查点 |
| :--- | :--- |
| **点击登录跳转后 404 或报错** | 检查 Casdoor 回调 URL 是否与 GitHub App 中配置的 `Authorization callback URL` 完全一致（注意大小写、末尾斜杠）。 |
| **授权成功但 Casdoor 无法获取用户信息** | 检查 Casdoor Provider 配置中的 **Scopes** 是否包含 `user:email`。 |
| **登录后邮箱为空** | 确保 GitHub 账号已设置公开邮箱。同时，在 GitHub App 设置中，确认已勾选 `User email addresses` 权限。 |
| **提示 "Client Secret 无效"** | 检查 Casdoor 中粘贴的 Client Secret 是否完整（注意不要有多余空格）。如果丢失，请在 GitHub 重新生成并更新。 |
| **国内服务器无法访问 GitHub** | 如果您的 Casdoor 部署在无法直接访问 GitHub 的网络环境中，需配置代理或使用其他登录方式。 |

---

### 💡 补充建议

*   **生产环境**：建议在 GitHub App 设置中上传应用图标，提升用户体验。
*   **安全提示**：切勿将 Client Secret 提交到代码仓库，建议通过环境变量或 Kubernetes Secret 注入。
*   **用户绑定**：Casdoor 会自动根据 GitHub 的 `id` 和邮箱进行用户匹配，若首次登录则会自动创建新用户。

按以上步骤操作，通常 5 分钟内即可完成配置。如果仍有问题，请提供 Casdoor 日志中的具体错误信息，我将协助进一步分析。