#!/bin/bash
# Casdoor 支付宝修复 — 快速部署脚本
# 使用已编译好的 casdoor-fix 二进制，基于当前 casdoor:latest 制作修复镜像

set -euo pipefail

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"

echo "=== 1. 创建临时容器 ==="
docker rm -f casdoor-tmp 2>/dev/null || true
docker run -d --name casdoor-tmp ${REGISTRY}/casdoor:latest sh -c "sleep 9999"

echo "=== 2. 复制修复后的二进制 ==="
docker cp /tmp/casdoor/casdoor-fix casdoor-tmp:/server
docker exec casdoor-tmp chmod +x /server
docker exec casdoor-tmp file /server

echo "=== 3. 提交为新镜像 ==="
docker commit casdoor-tmp ${REGISTRY}/casdoor:fix-alipay
docker rm -f casdoor-tmp

echo "=== 4. 推送镜像 ==="
docker push ${REGISTRY}/casdoor:fix-alipay

echo "=== 5. 更新 K8s 部署 ==="
kubectl set image deploy/casdoor -n oauth casdoor=${REGISTRY}/casdoor:fix-alipay
kubectl rollout status deploy/casdoor -n oauth --watch

echo ""
echo "=== 部署完成！==="
echo "检查 Casdoor 日志：kubectl logs -n oauth deploy/casdoor --tail=10"
