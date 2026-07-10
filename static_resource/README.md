# Static 资源管理

存放静态图片资源（收款码、Logo 等），通过 PVC 挂载到 Portal 和 Gradio 服务。

所有静态图片统一通过 main-portal 提供，各门户通过 URL 引用：

```
https://panghuer.top/static/xxx.jpg
```

## 添加新图片

```bash
# 1. 把图片放到这个目录
cp /path/to/logo.jpg d:\github\armbianbegin\static_resource/

# 2. 提交到 Git
git add .
git commit -m "add static: logo.jpg"
git push

# 3. SSH 到服务器拉取
ssh root@192.168.137.101
cd ~/armbianbegin
git pull

# 4. 同步到 PVC
bash static_resource/deploy.sh

# 5. 验证（等待 init-static Job 完成）
kubectl wait --for=condition=complete job/init-static -n agent-portal --timeout=30s

# 6. 如果 Portal 需要重启加载新图片：
kubectl rollout restart deploy/portal -n agent-portal
```

## 文件结构

```
static_resource/
├── deploy.sh                  # 同步脚本
├── README.md                  # 本文件
├── k8s/
│   └── static-pvc.yaml        # PVC + init-static Job 定义
├── alipay0.1.jpg              # 支付宝 1 毛收款码
├── alipay0.2.jpg              # 支付宝 2 毛收款码
├── alipay0.5.jpg              # 支付宝 5 毛收款码
├── wchatpay0.1.jpg            # 微信 1 毛收款码
├── wchatpay0.2.jpg            # 微信 2 毛收款码
└── wchatpay0.5.jpg            # 微信 5 毛收款码
```
