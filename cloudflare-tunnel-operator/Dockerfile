# =============================================================
# Cloudflare Tunnel for Kubernetes (ARM64)
# 多阶段构建：cloudflared 二进制来自 Docker Hub（走 mirror），
# 其余基于自建 base 镜像（Debian + 国内源）
# =============================================================

# ARG 必须在第一个 FROM 之前声明才能跨阶段使用
ARG REGISTRY=arm-cluster-master:5000

# ---- 阶段 1：提取 cloudflared 二进制 ----
FROM cloudflare/cloudflared:latest AS cloudflared

# ---- 阶段 2：构建运行镜像 ----
FROM ${REGISTRY}/base:latest

LABEL maintainer="armbianbegin"
LABEL description="Cloudflare Tunnel (cloudflared) for K8s ARM64"

# 从 cloudflared 官方镜像复制二进制
COPY --from=cloudflared /usr/local/bin/cloudflared /usr/local/bin/cloudflared

# 验证二进制可用
RUN cloudflared --version && \
    mkdir -p /etc/cloudflared /var/run/cloudflared

# 启动入口脚本
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 非 root 运行
RUN useradd -r -u 65532 -s /bin/bash nonroot && \
    chown -R nonroot:nonroot /etc/cloudflared /var/run/cloudflared
USER nonroot

EXPOSE 2000 2001

# 按优先级：TUNNEL_TOKEN → config.yml → credentials.json
ENTRYPOINT ["/entrypoint.sh"]
