#!/usr/bin/env bash
# Prepare cert-manager for this cluster WITHOUT touching it: fetch the official
# install manifest at a pinned version, retarget its images at the private
# registry, and mirror those images across.
#
# Why v1.19.6 -- the cluster is Kubernetes v1.31.2, and the v1.19.6 manifest only
# uses v1 API groups (admissionregistration.k8s.io/v1, apiextensions.k8s.io/v1,
# apps/v1, rbac.authorization.k8s.io/v1). That was checked against the downloaded
# manifest rather than assumed from a support table. v1.19 is still inside
# cert-manager's security-support window. Since v1.15 the install no longer ships
# a startupapicheck Job, so three images are required, not four; the acmesolver
# image is synced as well because the controller pulls it later, at solve time.
#
# The manifest is used AS DOWNLOADED apart from the image registry. Everything
# this cluster does differently from upstream is applied by deploy.sh, so that it
# stays visible in one reviewable place.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
CM_VERSION="${CM_VERSION:-v1.19.6}"
BASE="https://github.com/cert-manager/cert-manager/releases/download/${CM_VERSION}"
UPSTREAM_REGISTRY="quay.io/jetstack"
IMAGES=(cert-manager-controller cert-manager-webhook cert-manager-cainjector cert-manager-acmesolver)

command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }
for tool in curl sed python3; do
    command -v "$tool" >/dev/null || { echo "$tool is required." >&2; exit 1; }
done

mkdir -p rendered
echo "cert-manager ${CM_VERSION}, registry ${REGISTRY}"
echo

echo "=== 1. 抓官方安装清单 ==="
echo "  ${BASE}/cert-manager.yaml"
curl -fsSL --retry 3 -m 120 "${BASE}/cert-manager.yaml" -o rendered/cert-manager.yaml
[ -s rendered/cert-manager.yaml ] || { echo '  清单为空，停止。' >&2; exit 1; }
echo "  ✓ $(wc -c < rendered/cert-manager.yaml) B"

echo
echo "=== 2. 把镜像地址改到私有 registry ==="
if ! grep -q "${UPSTREAM_REGISTRY}/" rendered/cert-manager.yaml; then
    echo "  清单里找不到 ${UPSTREAM_REGISTRY}/，上游可能改了镜像路径——停下来人工确认。" >&2
    exit 1
fi
sed -i -E "s#${UPSTREAM_REGISTRY}/#${REGISTRY}/jetstack/#g" rendered/cert-manager.yaml
if grep -n "${UPSTREAM_REGISTRY}" rendered/cert-manager.yaml; then
    echo '  仍有 quay.io 残留，停止。' >&2
    exit 1
fi
echo "  ✓ 无 ${UPSTREAM_REGISTRY} 残留"

echo
echo "=== 3. 镜像同步（断言 arm64） ==="
for img in "${IMAGES[@]}"; do
    # quay.io is the only upstream; a mirror prefix may be supplied via CM_MIRROR
    # (a reachable registry) when quay is slow from this network.
    SOURCES=()
    [[ -n "${CM_MIRROR:-}" ]] && SOURCES+=("${CM_MIRROR%/}/${img}")
    SOURCES+=("${UPSTREAM_REGISTRY}/${img}")
    src=''
    for candidate in "${SOURCES[@]}"; do
        echo "  --- ${candidate}:${CM_VERSION}"
        if docker pull --platform linux/arm64 "${candidate}:${CM_VERSION}" >/dev/null; then
            src="${candidate}:${CM_VERSION}"; break
        fi
        echo '      拉不动，换下一个。'
    done
    if [[ -z "$src" ]]; then
        echo "  ${img} 所有镜像源都失败。用 CM_MIRROR=<可达的 registry 前缀> 重跑。" >&2
        exit 1
    fi
    arch="$(docker image inspect "$src" --format '{{.Architecture}}')"
    [[ "$arch" == arm64 ]] || { echo "  ${img} 期望 arm64，得到 $arch" >&2; exit 1; }
    dst="${REGISTRY}/jetstack/${img}:${CM_VERSION}"
    docker tag "$src" "$dst"
    docker push "$dst" >/dev/null
    echo "      -> $dst ✓"
done

echo
echo "=== 4. 自查 ==="
python3 - <<'PY'
import re
text = open("rendered/cert-manager.yaml", encoding="utf-8").read()
docs = [d for d in text.split("\n---") if re.search(r"^kind:", d, re.M)]
imgs = sorted(set(re.findall(r"image:\s*'?\"?([^\s'\"]+)", text)))
print(f"  文档数: {len(docs)}")
for i in imgs:
    print(f"  镜像: {i}")
PY

echo
echo '完成。下一步：bash deploy.sh --dry-run'
