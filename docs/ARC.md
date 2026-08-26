**Actions Runner Controller (ARC)** 是一个 **Kubernetes 控制器**，用于在 Kubernetes 集群中自动化地管理和扩缩容 GitHub Actions 的自托管运行器（self-hosted runners）。

简单来说，它让你能用管理 Kubernetes 应用的方式来管理 GitHub Actions 的运行器。

### 🎯 主要功能与优势

*   **自动化扩缩容**：ARC 能够根据 GitHub 仓库、组织或企业中正在运行的工作流数量，自动创建或销毁运行器实例。这些运行器通常是**临时的（ephemeral）**，基于容器运行，可以快速、干净地伸缩。
*   **简化管理**：以往在 Kubernetes 上运行自托管运行器并不直观。ARC 简化了部署流程，你只需在 Kubernetes 中创建自定义资源（如 `Runner` 或 `RunnerSet`），ARC 便会自动完成运行器的部署和配置。
*   **原生集成**：它是与 GitHub Actions 团队合作开发的开源项目，旨在提供官方支持级别的集成体验。其官方文档也托管在 `docs.github.com` 上。

### ⚙️ 工作原理

1.  **控制器**：ARC 作为一个 Pod 运行在你的 Kubernetes 集群中，持续监控 GitHub 的 API 和集群内的自定义资源状态。
2.  **自定义资源**：你可以通过创建 `Runner`、`RunnerSet` 或 `RunnerDeployment` 等 Kubernetes 自定义资源来声明你想要的运行器规模和行为。
3.  **自动注册**：当需要新的运行器时，ARC 会创建新的 Pod，并使用你提供的 GitHub Personal Access Token (PAT) 或 GitHub App 凭证，自动将其注册到指定的仓库、组织或企业。
4.  **执行任务**：注册成功后，这些运行器 Pod 就可以被 GitHub Actions 的工作流所使用。
5.  **自动清理**：任务执行完毕后，临时的运行器 Pod 会被自动销毁，实现资源的按需使用和释放。

### 🚀 快速部署指南

以下是在 Kubernetes 集群上部署和使用 ARC 的核心步骤：

#### 1. 环境准备
*   一个运行中的 Kubernetes 集群（如 Minikube）。
*   已安装并配置好 `kubectl`。
*   （可选但推荐）已安装 Helm。

#### 2. 安装 cert-manager
ARC 的准入控制器（Admission Webhook）需要使用 cert-manager 来管理证书。
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.8.2/cert-manager.yaml
```
> 请根据需要替换为最新的 cert-manager 版本。

#### 3. 生成 GitHub Personal Access Token (PAT)
在 GitHub 设置中生成一个具有 `repo` 和 `workflow` 权限的 PAT。

#### 4. 部署 ARC 控制器

*   **使用 Helm (推荐)**:
    ```bash
    # 1. 添加 Helm 仓库
    helm repo add actions-runner-controller https://actions-runner-controller.github.io/actions-runner-controller

    # 2. 安装控制器
    helm upgrade --install --namespace actions-runner-system --create-namespace \
      --set=authSecret.create=true \
      --set=authSecret.github_token="YOUR_PAT_HERE" \
      --wait actions-runner-controller actions-runner-controller/actions-runner-controller
    ```

*   **使用 Kubectl**:
    ```bash
    # 1. 部署控制器
    kubectl apply -f https://github.com/actions/actions-runner-controller/releases/download/v0.22.0/actions-runner-controller.yaml

    # 2. 配置 PAT
    kubectl create secret generic controller-manager -n actions-runner-system --from-literal=github_token="YOUR_PAT_HERE"
    ```

#### 5. 部署运行器集合 (Runner Scale Set)
```bash
# 设置你的 GitHub 仓库信息
export GITHUB_CONFIG_URL="https://github.com/YOUR_USERNAME/YOUR_REPO"
export GITHUB_PAT="YOUR_PAT_HERE"

# 使用 Helm 安装一个运行器集合
helm install arc-runner-set \
  --namespace arc-runners --create-namespace \
  --set githubConfigUrl="${GITHUB_CONFIG_URL}" \
  --set githubConfigSecret.github_token="${GITHUB_PAT}" \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set
```


#### 6. 在 GitHub Actions 中使用
在你的工作流文件中，将 `runs-on` 指定为你部署的运行器集合名称即可：
```yaml
jobs:
  build:
    runs-on: arc-runner-set
    steps:
      # ... 你的任务步骤
```

### ⚠️ 重要提示

*   **版本选择**：请注意，官方文档中提到的“传统（legacy）自动扩缩容模式”目前仅由社区维护。新项目应优先使用基于“运行器规模集（runner scale sets）”的自动扩缩容方式。
*   **官方文档**：所有最新的官方文档和指南都可在 `docs.github.com` 上找到。

### 💎 总结

Actions Runner Controller (ARC) 是将 GitHub Actions 的灵活性与 Kubernetes 的弹性相结合的理想工具。它非常适合需要动态、高效、大规模运行 CI/CD 任务的团队。

如果想深入了解，可以查阅 GitHub 官方文档中的 [Quickstart for Actions Runner Controller](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners-with-actions-runner-controller/quickstart-for-actions-runner-controller)。