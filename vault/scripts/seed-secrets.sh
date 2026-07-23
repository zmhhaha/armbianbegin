#!/bin/bash
# ============================================================
#  种子密钥写入脚本
#  功能: 将项目中现有的所有 Secret 一次性写入 Vault
#
#  用法:
#    bash scripts/seed-secrets.sh              # 交互式确认每个组件
#    bash scripts/seed-secrets.sh --all        # 写入所有组件
#    bash scripts/seed-secrets.sh --dry-run    # 仅显示将要写入的内容
#
#  前提:
#    - Vault 已初始化并解封
#    - root token 可用（或已登录）
#    - 如需更新，在 Vault UI 上操作或重新运行
#
#  注意:
#    - 密码等敏感值会从你的终端交互式输入，不会留在脚本中
#    - 建议先运行 --dry-run 查看需要准备哪些信息
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

VAULT_NS="vault"
VAULT_POD="vault-0"
K="${KUBECONFIG:---kubeconfig=/etc/kubernetes/super-admin.conf}"

MODE="${1:-interactive}"

# 检查 Vault 就绪
VAULT_READY=$(kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault status -format=json 2>/dev/null || echo '{"sealed":true,"initialized":false}')
SEALED=$(echo "${VAULT_READY}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('false' if d.get('sealed')==False else 'true')" 2>/dev/null || echo "true")
INITIALIZED=$(echo "${VAULT_READY}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('true' if d.get('initialized')==True else 'false')" 2>/dev/null || echo "false")

if [ "${INITIALIZED}" = "false" ] || [ "${SEALED}" = "true" ]; then
    echo "ERROR: Vault 未就绪（initialized=${INITIALIZED}, sealed=${SEALED}）"
    echo "请先运行: bash scripts/init-vault.sh"
    exit 1
fi

# ============================================================
#  定义每个组件的密钥映射
#  格式: <Vault路径> <描述>
#  注意: 实际值会在运行时交互式输入
# ============================================================
declare -A COMPONENTS
COMPONENTS["secret/data/oauth/oauth2-proxy"]="OAuth2-Proxy 凭证（OIDC_CLIENT_ID/SECRET, COOKIE_SECRET）"
COMPONENTS["secret/data/oauth/mysql"]="Casdoor MySQL 数据库密码"
COMPONENTS["secret/data/email-service/smtp"]="Email Service SMTP 配置（SMTP_USER, SMTP_PASS）"
COMPONENTS["secret/data/research-agent/api"]="Research Agent API Key（OPENAI_API_KEY, CUSTOM_API_KEY）"
COMPONENTS["secret/data/scientific-agent/api"]="Scientific Agent API Key（OPENAI_API_KEY, CUSTOM_API_KEY）"
COMPONENTS["secret/data/daofaziran-agent/api"]="道法自然 Agent API Key（OPENAI_API_KEY, CUSTOM_API_KEY）"
COMPONENTS["secret/data/fofawubian-agent/api"]="佛法无边 Agent API Key（OPENAI_API_KEY, CUSTOM_API_KEY）"
COMPONENTS["secret/data/zhongkuifumo-agent/api"]="钟馗伏魔 Agent API Key（OPENAI_API_KEY, CUSTOM_API_KEY）"
COMPONENTS["secret/data/yimaneili-agent/api"]="以马内利 Agent API Key（OPENAI_API_KEY, CUSTOM_API_KEY）"
COMPONENTS["secret/data/zhenzhuzhida-agent/api"]="真主至大 Agent API Key（OPENAI_API_KEY, CUSTOM_API_KEY）"
COMPONENTS["secret/data/gitops/gitea"]="Gitea 密钥配置"
COMPONENTS["secret/data/gitops/drone"]="Drone CI 密钥（DRONE_RPC_SECRET, DRONE_GITEA_CLIENT_SECRET）"
COMPONENTS["secret/data/infra/registry"]="私有镜像仓库 TLS 证书"
COMPONENTS["secret/data/infra/ceph"]="Ceph 认证密钥"
COMPONENTS["secret/data/txt2img/ark"]="txt2img-proxy 火山引擎视觉 CV AK/SK"
COMPONENTS["secret/data/txt2img/replicate"]="txt2img-proxy Replicate API Key"
COMPONENTS["secret/data/txt2img/together"]="txt2img-proxy Together AI API Key"
COMPONENTS["secret/data/txt2img/stability"]="txt2img-proxy Stability AI API Key"
COMPONENTS["secret/data/txt2img/openai"]="txt2img-proxy OpenAI API Key"
COMPONENTS["secret/data/postgres/app"]="PostgreSQL 通用数据库密码"
COMPONENTS["secret/data/redis/app"]="Redis 通用缓存密码"
COMPONENTS["secret/data/school-of-one/db"]="School of One 数据库连接串"
COMPONENTS["secret/data/school-of-one/jwt"]="School of One JWT 签名密钥"
COMPONENTS["secret/data/school-of-one/llm"]="School of One DeepSeek API Key"
COMPONENTS["secret/data/school-of-one/redis"]="School of One Redis 连接串"

# 定义每个路径下要写入的键值映射（交互式提示用）
declare -A KEY_MAP
KEY_MAP["secret/data/oauth/oauth2-proxy"]="COOKIE_SECRET OIDC_CLIENT_ID OIDC_CLIENT_SECRET OIDC_ISSUER_URL ALLOWED_DOMAINS"
KEY_MAP["secret/data/oauth/mysql"]="MYSQL_ROOT_PASSWORD MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD"
KEY_MAP["secret/data/email-service/smtp"]="SMTP_HOST SMTP_PORT SMTP_USER SMTP_PASS SMTP_FROM"
KEY_MAP["secret/data/research-agent/api"]="OPENAI_API_KEY CUSTOM_API_KEY"
KEY_MAP["secret/data/scientific-agent/api"]="OPENAI_API_KEY CUSTOM_API_KEY"
KEY_MAP["secret/data/daofaziran-agent/api"]="OPENAI_API_KEY CUSTOM_API_KEY"
KEY_MAP["secret/data/fofawubian-agent/api"]="OPENAI_API_KEY CUSTOM_API_KEY"
KEY_MAP["secret/data/zhongkuifumo-agent/api"]="OPENAI_API_KEY CUSTOM_API_KEY"
KEY_MAP["secret/data/yimaneili-agent/api"]="OPENAI_API_KEY CUSTOM_API_KEY"
KEY_MAP["secret/data/zhenzhuzhida-agent/api"]="OPENAI_API_KEY CUSTOM_API_KEY"
KEY_MAP["secret/data/gitops/gitea"]="GITEA_SECRET_KEY GITEA_INTERNAL_TOKEN GITEA_OAUTH2_JWT_SECRET"
KEY_MAP["secret/data/gitops/drone"]="DRONE_RPC_SECRET DRONE_GITEA_CLIENT_ID DRONE_GITEA_CLIENT_SECRET"
KEY_MAP["secret/data/infra/registry"]="TLS_CRT TLS_KEY"
KEY_MAP["secret/data/infra/ceph"]="CEPH_USER_ID CEPH_USER_KEY"
KEY_MAP["secret/data/txt2img/ark"]="ARK_ACCESS_KEY ARK_SECRET_KEY"
KEY_MAP["secret/data/txt2img/replicate"]="REPLICATE_API_KEY"
KEY_MAP["secret/data/txt2img/together"]="TOGETHER_API_KEY"
KEY_MAP["secret/data/txt2img/stability"]="STABILITY_API_KEY"
KEY_MAP["secret/data/txt2img/openai"]="OPENAI_API_KEY"
KEY_MAP["secret/data/postgres/app"]="POSTGRES_PASSWORD"
KEY_MAP["secret/data/redis/app"]="REDIS_PASSWORD"
KEY_MAP["secret/data/school-of-one/db"]="DB_URL（连接串: postgresql://appuser:密码@postgres.data.svc.cluster.local:5432/school_of_one）"
KEY_MAP["secret/data/school-of-one/jwt"]="JWT_SECRET（随机 64 位 hex）"
KEY_MAP["secret/data/school-of-one/llm"]="DEEPSEEK_API_KEY OPENAI_API_KEY（可选）"
KEY_MAP["secret/data/school-of-one/redis"]="REDIS_URL（连接串: redis://:密码@redis.data.svc.cluster.local:6379/0）"

# ============================================================
#  写入 Vault 函数
# ============================================================
write_to_vault() {
    local path="$1"
    shift
    local kv_pairs=("$@")

    if [ ${#kv_pairs[@]} -eq 0 ]; then
        echo "  ⏭️  跳过 ${path}（无数据）"
        return
    fi

    # 构建 JSON 数据
    local json_data="{"
    local first=true
    for pair in "${kv_pairs[@]}"; do
        local key="${pair%%=*}"
        local value="${pair#*=}"
        if [ "$first" = true ]; then
            first=false
        else
            json_data+=", "
        fi
        json_data+="\"${key}\": \"${value}\""
    done
    json_data+="}"

    echo "  📝 写入 ${path} ..."
    kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault kv put "${path}" $(echo "${json_data}" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for k, v in data.items():
    print(f'{k}={v}')
")
    echo "  ✅ 成功"
}

# ============================================================
#  Dry-run 模式：只显示信息
# ============================================================
if [ "${MODE}" = "--dry-run" ]; then
    echo ""
    echo "============================================"
    echo "  Seed Secrets — Dry Run"
    echo "============================================"
    echo ""
    echo "以下密钥将被写入 Vault："
    echo ""

    for path in "${!COMPONENTS[@]}"; do
        local keys="${KEY_MAP[$path]:-}"
        echo "  📁 ${path}"
        echo "     ${COMPONENTS[$path]}"
        if [ -n "${keys}" ]; then
            for k in ${keys}; do
                echo "     - ${k}: [需要输入]"
            done
        fi
        echo ""
    done | sort

    echo "============================================"
    echo "  请准备以上信息后运行: bash scripts/seed-secrets.sh"
    echo "============================================"
    exit 0
fi

# ============================================================
#  All 模式：跳过交互式确认
# ============================================================
if [ "${MODE}" = "--all" ]; then
    echo ""
    echo "============================================"
    echo "  Seed Secrets — 批量写入全部密钥"
    echo "============================================"
    echo ""
    echo "⚠️  警告：这将覆盖 Vault 中已有的同名密钥！"
    echo "============================================"
    echo ""

    for path in "${!COMPONENTS[@]}"; do
        echo ""
        echo "📁 ${path} — ${COMPONENTS[$path]}"
        echo "  跳过（--all 模式下需要手动运行带具体值的脚本）"
    done | sort

    echo ""
    echo "  --all 模式暂不实现自动输入值，请逐条使用 bash scripts/seed-secrets.sh 手动写入"
    echo "  建议:"
    echo "  kubectl exec -n vault vault-0 -- vault kv put secret/data/oauth/oauth2-proxy \\"
    echo "    COOKIE_SECRET=<value> OIDC_CLIENT_ID=<value> ..."
    exit 0
fi

# ============================================================
#  交互式模式
# ============================================================
echo ""
echo "============================================"
echo "  Seed Secrets — 交互式写入"
echo "============================================"
echo "  将逐个引导您将密钥写入 Vault"
echo "  输入 'skip' 跳过当前组件"
echo "  输入 'exit' 退出"
echo "============================================"
echo ""

# 获取 root token 提示
echo "=== Vault 登录状态检查 ==="
LOGIN_CHECK=$(kubectl exec -n ${VAULT_NS} ${VAULT_POD} -- vault token lookup -format=json 2>/dev/null || echo '{"data":{"display_name":"unknown"}}')
TOKEN_NAME=$(echo "${LOGIN_CHECK}" | python3 -c "import sys,json; d=json.load(sys.stdin).get('data',{}); print(d.get('display_name','unknown'))" 2>/dev/null || echo "unknown")
echo "  当前 token: ${TOKEN_NAME}"
if [ "${TOKEN_NAME}" = "unknown" ] || [ "${TOKEN_NAME}" = "root" ]; then
    echo "  ✅ Token 有效"
else
    echo "  ⚠️  可能需要登录 root token"
    echo "  运行: kubectl exec -n vault vault-0 -- vault login <root_token>"
fi

echo ""

# 按排序后的路径遍历
for path in $(echo "${!COMPONENTS[@]}" | tr ' ' '\n' | sort); do
    desc="${COMPONENTS[$path]}"
    keys="${KEY_MAP[$path]:-}"

    echo ""
    echo "──────────────────────────────────────────"
    echo "📁 ${path}"
    echo "   ${desc}"
    echo "──────────────────────────────────────────"

    if [ -z "${keys}" ]; then
        echo "  ⏭️  跳过（无键定义）"
        continue
    fi

    # 构建键值对数组
    local kv_pairs=()
    for k in ${keys}; do
        read -p "  请输入 ${k}（留空跳过）: " val
        if [ "${val}" = "skip" ]; then
            kv_pairs=()
            break
        fi
        if [ "${val}" = "exit" ]; then
            echo "退出"
            exit 0
        fi
        if [ -n "${val}" ]; then
            kv_pairs+=("${k}=${val}")
        fi
    done

    if [ ${#kv_pairs[@]} -gt 0 ]; then
        write_to_vault "${path}" "${kv_pairs[@]}"
    else
        echo "  ⏭️  跳过 ${path}"
    fi
done

echo ""
echo "============================================"
echo "  Seed Secrets 完成！"
echo "============================================"
echo ""
echo "已写入 Vault 的路径："
for path in "${!COMPONENTS[@]}"; do
    echo "  📁 ${path}"
done | sort

echo ""
echo "下一步："
echo "  1. 打开 Vault UI 验证: kubectl port-forward -n vault svc/vault 8200:8200"
echo "  2. 创建 ExternalSecret: kubectl apply -f k8s/example-external-secret.yaml"
echo "  3. 验证同步: kubectl get secret -n oauth oauth2-proxy-secret"
echo "============================================"
