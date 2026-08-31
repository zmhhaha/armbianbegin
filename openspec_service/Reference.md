可以的，目前主要有两种方式可以让 OpenSpec MCP 服务器通过 HTTPS 请求工作：

### 🚀 方案一：使用官方托管服务 (GitMCP)

这是最直接的方式，无需自己搭建服务器。OpenSpec 官方在 [GitMCP](https://gitmcp.io) 上托管了一个 MCP 服务器。

*   **配置方法**：你只需在支持 **SSE (Server-Sent Events)** 的 MCP 客户端中，将服务器 URL 配置为 `https://gitmcp.io/Fission-AI/OpenSpec` 即可。
*   **示例配置**：例如，在 VSCode 的 MCP 配置文件中可以这样写:
    ```json
    {
      "servers": {
        "OpenSpec Docs": {
          "type": "sse",
          "url": "https://gitmcp.io/Fission-AI/OpenSpec"
        }
      }
    }
    ```
*   **工作原理**：这种方式的核心是使用 `mcp-remote` 命令，它会将本地的 MCP 协议通过 `npx` 桥接到远程的 HTTPS 服务上。

### 🏗️ 方案二：自建支持 HTTP/HTTPS 的服务器

如果你想完全掌控服务器，可以自己搭建。`@igor-olikh/openspec-mcp-server` 这个包提供了相关选项。

*   **启用 Web 面板**：在启动命令中添加 `--with-dashboard` 或 `--dashboard` 参数，可以启动一个 Web 界面。
    ```bash
    npx -y @igor-olikh/openspec-mcp-server --with-dashboard
    ```
*   **重要提示**：这个 Web 面板主要用于提供可视化管理界面。关于如何配置它以接受安全的远程 HTTPS 连接（如绑定域名、配置 SSL 证书等），在公开文档中暂无详细说明，可能需要你自行研究其源码或进行相关配置。

### 💎 总结
对于大多数开发者，**推荐使用方案一（GitMCP）**，因为它配置简单，无需自己维护服务器。如果你有特殊需求，可以探索方案二（自建服务器）。