#!/usr/bin/env bash
# Prepare everything for the flannel -> Calico migration, without touching the
# cluster: fetch the two official manifests at a pinned version, retarget their
# images at the private registry, and mirror those images across.
#
# The manifests are used AS DOWNLOADED apart from the image registry. In
# particular the __CNI_MTU__ / __KUBERNETES_NODE_NAME__ / __KUBECONFIG_FILEPATH__
# tokens are NOT substituted here: Calico's own install-cni init container
# replaces them at pod start (calico.yaml, initContainers[install-cni]).
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
CALICO_VERSION="${CALICO_VERSION:-v3.32.2}"
# Optional registry prefix for quay.io, e.g. an internal pull-through cache.
QUAY_MIRROR="${QUAY_MIRROR:-}"
BASE="https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/flannel-migration"

if [[ -f build.local.env ]]; then source build.local.env; fi

command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }
for tool in curl sed python3; do
    command -v "$tool" >/dev/null || { echo "$tool is required." >&2; exit 1; }
done

mkdir -p rendered
echo "Calico ${CALICO_VERSION}, registry ${REGISTRY}"
echo

echo "=== 1. 抓官方清单 ==="
for f in calico migration-job; do
    echo "  ${BASE}/${f}.yaml"
    curl -fsSL --retry 3 -m 60 "${BASE}/${f}.yaml" -o "rendered/${f}.yaml"
done

echo
echo "=== 2. 把镜像地址改到私有 registry ==="
# Collect the image references BEFORE rewriting so we know exactly what to mirror.
mapfile -t IMAGES < <(grep -ohE 'quay\.io/[a-z0-9/_-]+:[A-Za-z0-9._-]+' rendered/*.yaml | sort -u)
if [[ ${#IMAGES[@]} -eq 0 ]]; then
    echo '  没找到 quay.io 镜像引用，清单可能变了——停下来人工确认。' >&2
    exit 1
fi
for img in "${IMAGES[@]}"; do
    echo "  ${img}  ->  ${REGISTRY}/${img#quay.io/}"
done
sed -i -E "s#quay\.io/#${REGISTRY}/#g" rendered/calico.yaml rendered/migration-job.yaml

if grep -n 'quay\.io' rendered/*.yaml; then
    echo '  仍有 quay.io 残留，停止。' >&2
    exit 1
fi
echo "  ✓ 无 quay.io 残留"

echo
echo "=== 3. 镜像同步（断言 arm64） ==="
for img in "${IMAGES[@]}"; do
    src="${QUAY_MIRROR:+${QUAY_MIRROR%/}/}${img}"
    dst="${REGISTRY}/${img#quay.io/}"
    echo "  --- $src"
    docker pull --platform linux/arm64 "$src"
    arch="$(docker image inspect "$src" --format '{{.Architecture}}')"
    [[ "$arch" == arm64 ]] || { echo "    期望 arm64，得到 $arch" >&2; exit 1; }
    docker tag "$src" "$dst"
    docker push "$dst"
    echo "      -> $dst"
done

echo
echo "=== 4. 自查 ==="
python3 - <<'PY'
import glob, re, sys, yaml
for f in sorted(glob.glob("rendered/*.yaml")):
    docs = [d for d in yaml.safe_load_all(open(f, encoding="utf-8")) if d]
    imgs = sorted({i for i in re.findall(r"image:\s*'?\"?([^\s'\"]+)", open(f, encoding="utf-8").read())})
    print(f"  {f}: {len(docs)} 文档, {len(imgs)} 个镜像")
    for i in imgs:
        print(f"      {i}")
PY

echo
echo '完成。下一步是 README.md 的「阶段 0 通过条件」，然后再动集群。'
echo '强烈建议先做 etcd 快照——本方案要重建 Pod，而集群目前没有备份。'
