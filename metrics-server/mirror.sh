#!/usr/bin/env bash
# Prepare metrics-server for this cluster WITHOUT touching it: fetch the official
# high-availability manifest at a pinned version, retarget its image at the
# private registry, and mirror that image across.
#
# Why v0.8.1 -- upstream's compatibility matrix, fetched from its README:
#   metrics-server 0.9.x -> Kubernetes 1.34+
#   metrics-server 0.8.x -> Kubernetes 1.31+
#   metrics-server 0.7.x -> Kubernetes 1.27+
# This cluster is v1.31.2 (cluster_config.sh), so 0.8.x is the only line that
# fits and v0.8.1 is its latest patch. Do not "upgrade" to 0.9.x without
# checking that matrix again -- it would not run.
#
# The manifest is used AS DOWNLOADED apart from the image registry. The three
# changes this cluster needs (--kubelet-insecure-tls, resource limits, the arm64
# nodeSelector) are applied by deploy.sh rather than here, so that everything
# this repo does differently from upstream stays visible in one place.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
MS_VERSION="${MS_VERSION:-v0.8.1}"
# The release asset is literally named "high-availability-1.21+.yaml"; the "+"
# has to be percent-encoded or the server reads it as a space.
ASSET="high-availability-1.21%2B.yaml"
BASE="https://github.com/kubernetes-sigs/metrics-server/releases/download/${MS_VERSION}"
UPSTREAM_IMAGE="registry.k8s.io/metrics-server/metrics-server"

# Where the image is pulled from, tried in order. registry.k8s.io is slow or
# unreachable from parts of this network -- debian_begin.sh pulls the kubeadm
# images from an Aliyun mirror for the same reason -- so this walks a list. The
# architecture assertion below is what makes the list safe to walk: whatever
# comes back, it must be arm64.
SOURCES=()
[[ -n "${MS_MIRROR:-}" ]] && SOURCES+=("${MS_MIRROR%/}/metrics-server")
SOURCES+=("${UPSTREAM_IMAGE}")
SOURCES+=("registry.aliyuncs.com/google_containers/metrics-server")
SOURCES+=("registry.cn-hangzhou.aliyuncs.com/google_containers/metrics-server")

command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }
for tool in curl sed python3; do
    command -v "$tool" >/dev/null || { echo "$tool is required." >&2; exit 1; }
done

mkdir -p rendered
echo "metrics-server ${MS_VERSION}, registry ${REGISTRY}"
echo

echo "=== 1. 抓官方 HA 清单 ==="
echo "  ${BASE}/${ASSET}"
curl -fsSL --retry 3 -m 60 "${BASE}/${ASSET}" -o rendered/metrics-server.yaml

echo
echo "=== 2. 把镜像地址改到私有 registry ==="
if ! grep -q "${UPSTREAM_IMAGE}:" rendered/metrics-server.yaml; then
    echo "  清单里找不到 ${UPSTREAM_IMAGE}，上游可能改了镜像路径——停下来人工确认。" >&2
    exit 1
fi
sed -i -E "s#registry\.k8s\.io/#${REGISTRY}/#g" rendered/metrics-server.yaml
if grep -n 'registry\.k8s\.io' rendered/metrics-server.yaml; then
    echo '  仍有 registry.k8s.io 残留，停止。' >&2
    exit 1
fi
echo "  ✓ 无 registry.k8s.io 残留"

echo
echo "=== 3. 镜像同步（断言 arm64） ==="
src=''
for candidate in "${SOURCES[@]}"; do
    echo "  --- ${candidate}:${MS_VERSION}"
    if docker pull --platform linux/arm64 "${candidate}:${MS_VERSION}"; then
        src="${candidate}:${MS_VERSION}"
        break
    fi
    echo '      拉不动，换下一个。'
done
if [[ -z "$src" ]]; then
    echo '  所有镜像源都失败。用 MS_MIRROR=<可达的 registry 前缀> 重跑。' >&2
    exit 1
fi
arch="$(docker image inspect "$src" --format '{{.Architecture}}')"
[[ "$arch" == arm64 ]] || { echo "  期望 arm64，得到 $arch" >&2; exit 1; }
dst="${REGISTRY}/${UPSTREAM_IMAGE#registry.k8s.io/}:${MS_VERSION}"
docker tag "$src" "$dst"
docker push "$dst"
echo "      -> $dst"

echo
echo "=== 4. 自查 ==="
python3 - <<'PY'
import glob, re, yaml
for f in sorted(glob.glob("rendered/*.yaml")):
    text = open(f, encoding="utf-8").read()
    docs = [d for d in yaml.safe_load_all(text) if d]
    imgs = sorted(set(re.findall(r"image:\s*'?\"?([^\s'\"]+)", text)))
    print(f"  {f}: {len(docs)} 文档, {len(imgs)} 个镜像")
    for i in imgs:
        print(f"      {i}")
    print("      对象：")
    for d in docs:
        print(f"        {d['kind']}/{d['metadata']['name']}")
PY

echo
echo '完成。下一步是 README.md 的「通过条件」，先 bash deploy.sh --dry-run 看渲染结果。'
