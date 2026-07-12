# Casdoor 支付宝 OAuth 修复补丁

## 问题描述

支付宝 OAuth 绑定时报错：
```
asn1: syntax error: sequence truncated
```

## 根因

Casdoor 的 `idp/alipay.go` 中 `rsaSignWithRSA256` 函数只尝试用 `x509.ParsePKCS8PrivateKey()` 解析私钥。

阿里官方密钥工具生成的应用私钥符合 **PKCS#8 标准（RFC5208）**（ASN.1 DER 编码的 PrivateKeyInfo，无 PEM 头）。Casdoor 的 `formatPrivateKey()` 会对其格式化并添加 `-----BEGIN PRIVATE KEY-----`（PKCS#8 PEM 头），然后调用 `x509.ParsePKCS8PrivateKey()` 解析。

问题在于：部分环境下 `x509.ParsePKCS8PrivateKey()` 解析失败直接返回错误，没有回退到 `x509.ParsePKCS1PrivateKey()` 重试，导致 `asn1: syntax error: sequence truncated`。

## 修复方法

修改 `idp/alipay.go` 中 `rsaSignWithRSA256` 函数，PKCS#8 解析失败后回退到 PKCS#1：

```go
// 修复前（第 310 行）
privateKeyRSA, err := x509.ParsePKCS8PrivateKey(block.Bytes)
if err != nil {
    return "", err
}

// 修复后
privateKeyRSA, err := x509.ParsePKCS8PrivateKey(block.Bytes)
if err != nil {
    privateKeyRSA, err = x509.ParsePKCS1PrivateKey(block.Bytes)
    if err != nil {
        return "", fmt.Errorf("failed to parse private key (tried PKCS8 and PKCS1): %w", err)
    }
}
if privateKeyRSA == nil {
    return "", err
}
```

⚠️ **`formatPrivateKey` 函数不改动**，保持 `-----BEGIN PRIVATE KEY-----`（PKCS#8 头）。因为阿里工具生成的是 PKCS#8 格式（RFC5208），不是 PKCS#1。

---

## 编译 & 部署

需要在服务器上编译 arm64 静态链接的 Casdoor 二进制，然后打包成 Docker 镜像部署。

### 前置条件

- 服务器能访问 GitHub（git clone）
- Docker 已安装
- kubectl 可操作 K8s 集群
- Go 编译使用 Docker golang:1.25 镜像（无需宿主机安装 Go）

### 完整流程

#### Step 1：克隆源码并打补丁

```bash
# 克隆 Casdoor 源码
git clone git@github.com:casdoor/casdoor.git /tmp/casdoor
cd /tmp/casdoor

# 打补丁（只修改 rsaSignWithRSA256，不改 formatPrivateKey）
sed -i '/privateKeyRSA, err := x509.ParsePKCS8PrivateKey(block.Bytes)/{
    N
    s/if err != nil {\n\t\treturn "", err/if err != nil {\n\t\tprivateKeyRSA, err = x509.ParsePKCS1PrivateKey(block.Bytes)\n\t\tif err != nil {\n\t\t\treturn "", fmt.Errorf("failed to parse private key (tried PKCS8 and PKCS1): %w", err)\n\t\t}\n\t}\n\tif privateKeyRSA == nil {
}' idp/alipay.go
```

#### Step 2：编译静态链接的 arm64 二进制

```bash
docker run --rm -v "$(pwd):/src" -w /src golang:1.25 \
  /bin/sh -c "CGO_ENABLED=0 GOOS=linux GOARCH=arm64 \
    GOPROXY=https://mirrors.aliyun.com/goproxy \
    go build -ldflags='-s -w' -o /src/casdoor-fix ."

# 验证二进制架构
file casdoor-fix
# 应输出: ELF 64-bit LSB executable, ARM aarch64, statically linked
```

#### Step 3：将二进制打包到 Casdoor 镜像中

```bash
# 拉取原始 Casdoor 镜像
docker pull arm-cluster-master:5000/casdoor:latest

# 创建临时容器
docker run -d --name casdoor-tmp \
  arm-cluster-master:5000/casdoor:latest \
  sh -c "sleep 9999"

# 复制修复后的二进制
docker cp casdoor-fix casdoor-tmp:/server
docker exec casdoor-tmp chmod +x /server
docker exec casdoor-tmp file /server  # 确认是 aarch64

# 提交为新镜像
docker commit casdoor-tmp arm-cluster-master:5000/casdoor:fix-alipay

# 清理临时容器
docker rm -f casdoor-tmp

# 推送到私有仓库
docker push arm-cluster-master:5000/casdoor:fix-alipay
```

#### Step 4：部署到 K8s

```bash
# 更新 Deployment 使用新镜像
kubectl set image deploy/casdoor -n oauth \
  casdoor=arm-cluster-master:5000/casdoor:fix-alipay

# 等待滚动更新完成
kubectl rollout status deploy/casdoor -n oauth --watch

# 确认运行正常
kubectl get pods -n oauth | grep casdoor
kubectl logs -n oauth deploy/casdoor --tail=5
# 应显示正常访问日志，无 asn1 错误
```

### 快速部署（使用已有二进制）

如果已经编译好了 `casdoor-fix` 二进制，可以直接执行 `deploy-fix.sh`：

```bash
cd ~/armbianbegin/oauth/casdoor_fix
bash deploy-fix.sh
```

### 一键编译 + 部署

```bash
cd ~/armbianbegin/oauth/casdoor_fix
bash build-fix.sh
```

> `build-fix.sh` 会自动完成 Step 1-4。

---

## 验证

绑定支付宝后，应该不再报 `asn1` 错误。如果仍然报 `failed to parse private key (tried PKCS8 and PKCS1): asn1: syntax error: sequence truncated`，说明私钥格式有问题，需要用 OpenSSL 重新生成：

```bash
openssl genrsa -out alipay_private.pem 2048
openssl rsa -in alipay_private.pem -pubout -out alipay_public.pem
```

然后将公钥上传到支付宝开放平台替换旧的公钥，私钥写入 Casdoor。

---

## 文件清单

| 文件 | 说明 |
|------|------|
| `build-fix.sh` | 一键编译 + 镜像制作 + 部署（推荐） |
| `deploy-fix.sh` | 仅部署（编译好的二进制存在时使用） |
| `alipay.go.patch` | Git diff 格式的补丁文件（仅供参考） |
| `README.md` | 本文件 |
