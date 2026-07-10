#!/bin/bash
# ============================================================
#  Static 静态资源部署脚本
#  将 static_resource/ 中的图片同步到 PVC，供 Portal/Gradio 使用
#
#  用法:
#    bash deploy.sh              # 同步到所有命名空间
#    bash deploy.sh <ns>         # 仅同步到指定命名空间
#
#  在 static_resource/ 新增图片后：
#    1. git add / git commit / git push
#    2. ssh 到服务器 git pull
#    3. bash deploy.sh
#
#  访问地址: https://agent.panghuer.top/static/<图片名>
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"

K="${KUBECONFIG:---kubeconfig=/etc/kubernetes/super-admin.conf}"

# 目标命名空间（默认全部）
if [ $# -ge 1 ]; then
    TARGET_NS=("$1")
else
    TARGET_NS=("main-portal")
fi

echo "=== 同步 static_resource/ 到 PVC ==="

# 先把图片传到集群节点（Job 通过 hostPath 读取）
echo "  📤 同步图片到集群节点..."
rsync -av --delete *.jpg root@arm-cluster-master:/root/armbianbegin/static_resource/ 2>/dev/null || \
    scp *.jpg root@arm-cluster-master:/root/armbianbegin/static_resource/

for ns in "${TARGET_NS[@]}"; do
    echo ""
    echo "  ── ${ns} ──"

    # 删除旧的 Job（触发重新复制）
    kubectl delete job init-static -n "${ns}" $K --ignore-not-found --wait=true 2>/dev/null || true
    echo "  🗑️  旧 Job 已清理"

    # 重新 apply（PVC 幂等，Job 重建后自动复制最新图片）
    kubectl apply $K -f k8s/static-pvc.yaml
    echo "  ✅ Job 已重建"
done

echo ""
echo "============================================"
echo "  同步完成！"
echo ""
echo "  等待 Job 完成..."
for ns in "${TARGET_NS[@]}"; do
    kubectl wait --for=condition=complete job/init-static -n "${ns}" --timeout=60s 2>/dev/null || true
done
echo ""
echo "  验证图片:"
echo "    curl -s -o /dev/null -w '%{http_code}' https://agent.panghuer.top/static/alipay0.1.jpg"
echo "      → 应返回 200"
echo ""
echo "  如果 Portal 需要重启读取新图片:"
echo "    kubectl rollout restart deploy/portal -n agent-portal"
echo "============================================"
