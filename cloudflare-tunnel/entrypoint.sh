#!/bin/sh
# =============================================================
# cloudflared K8s entrypoint — 支持三种配置方式
# =============================================================
set -e

CONFIG_FILE="${CONFIG_FILE:-/etc/cloudflared/config.yml}"
CREDENTIALS_FILE="${CREDENTIALS_FILE:-/etc/cloudflared/credentials.json}"
LOGLEVEL="${LOGLEVEL:-info}"

echo "=== cloudflared starting ==="

# ============================================================
# 方式 1：环境变量 TUNNEL_TOKEN（最简单）
# 在 Cloudflare Zero Trust → Tunnels 中获取 token
# ============================================================
if [ -n "${TUNNEL_TOKEN}" ]; then
    echo ">> Mode: TUNNEL_TOKEN"
    exec cloudflared tunnel --loglevel ${LOGLEVEL} run --token "${TUNNEL_TOKEN}"
fi

# ============================================================
# 方式 2：配置文件 config.yml（有 credentials-file 引用）
# 适用于已经用 cloudflared tunnel create 创建了 tunnel
# ============================================================
if [ -f "${CONFIG_FILE}" ]; then
    # 如果 config.yml 引用了 credentials-file，检查它是否存在
    if grep -q "credentials-file" "${CONFIG_FILE}" 2>/dev/null; then
        CRED_FILE=$(grep "credentials-file" "${CONFIG_FILE}" | awk '{print $2}' | tr -d '"')
        if [ -n "${CRED_FILE}" ] && [ ! -f "${CRED_FILE}" ]; then
            echo "ERROR: credentials-file ${CRED_FILE} not found"
            exit 1
        fi
    fi
    echo ">> Mode: config.yml (${CONFIG_FILE})"
    exec cloudflared tunnel --loglevel ${LOGLEVEL} run --config "${CONFIG_FILE}"
fi

# ============================================================
# 方式 3：传统 credentials.json + 命令行
# credential.json: {AccountTag, TunnelSecret, TunnelID}
# ============================================================
if [ -f "${CREDENTIALS_FILE}" ]; then
    TUNNEL_ID=$(grep -o '"TunnelID"[[:space:]]*:[[:space:]]*"[^"]*"' "${CREDENTIALS_FILE}" | cut -d'"' -f4)
    if [ -n "${TUNNEL_ID}" ]; then
        echo ">> Mode: credentials.json (tunnel ${TUNNEL_ID})"
        exec cloudflared tunnel --loglevel ${LOGLEVEL} run \
            --credentials-file "${CREDENTIALS_FILE}"
    fi
fi

# ============================================================
# 无有效配置
# ============================================================
echo "ERROR: No valid configuration found."
echo "  Provide one of:"
echo "    1. TUNNEL_TOKEN environment variable"
echo "    2. /etc/cloudflared/config.yml (ConfigMap mount)"
echo "    3. /etc/cloudflared/credentials.json (Secret mount)"
exit 1
