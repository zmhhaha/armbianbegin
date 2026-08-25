#!/bin/sh
# 把各 agent 的 Vault api 路径配置为 DeepSeek only
# （DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL），
# 移除 OPENAI_API_KEY / CUSTOM_API_KEY。
set -e

# 先读现有真实 key（从 research-agent 取，各 agent 共享同一 key）
MASTER_KEY=$(vault kv get -field=DEEPSEEK_API_KEY secret/research-agent/api 2>/dev/null || true)
if [ -z "$MASTER_KEY" ]; then
  MASTER_KEY=$(vault kv get -field=OPENAI_API_KEY secret/research-agent/api 2>/dev/null || true)
fi
if [ -z "$MASTER_KEY" ]; then
  echo "ERROR: 无法获取现有 API key"; exit 1
fi
echo "使用 key: $(echo $MASTER_KEY | cut -c1-6)..."

for ns in research-agent scientific-agent daofaziran-agent fofawubian-agent \
          yimaneili-agent zhenzhuzhida-agent zhongkuifumo-agent \
          zhougongjiemeng-agent xiaotanrenjian-agent game-review-agent; do
  echo "=== $ns ==="
  # 覆盖写为 deepseek only（先 metadata 版本递增，再 put 替换全部字段）
  kubectl exec -n vault vault-0 -- vault kv put "secret/$ns/api" \
    DEEPSEEK_API_KEY="$MASTER_KEY" \
    DEEPSEEK_BASE_URL="https://api.deepseek.com" \
    DEEPSEEK_MODEL="deepseek-v4-flash"
  echo "$ns: 已配置 DeepSeek only"
done
echo "=== done ==="
