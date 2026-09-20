#!/usr/bin/env bash
# Mirror kube-router into the private registry.
#
# kube-router is a single static Go binary, so there is no Dockerfile here:
# pull the ARM64 image, assert the architecture, retag and push. The digest we
# resolved is written to rendered/ so deploy.sh can refuse to run against a
# moving tag.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
command -v docker >/dev/null || { echo 'Docker is required.' >&2; exit 1; }

if [[ -f build.local.env ]]; then
    # Trusted operator configuration only; this file is ignored by Git.
    source build.local.env
fi

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
# Optional registry prefix, e.g. your private Docker Hub pull-through cache.
# Empty prefix uses the Docker daemon's registry-mirrors on the server.
DOCKERHUB_MIRROR="${DOCKERHUB_MIRROR:-}"
KUBE_ROUTER_VERSION="${KUBE_ROUTER_VERSION:-v2.11.1}"

UPSTREAM="${DOCKERHUB_MIRROR:+${DOCKERHUB_MIRROR%/}/}cloudnativelabs/kube-router:${KUBE_ROUTER_VERSION}"
IMAGE="${REGISTRY}/kube-router:${KUBE_ROUTER_VERSION}"

echo "Pulling ARM64 upstream: $UPSTREAM"
docker pull --platform linux/arm64 "$UPSTREAM"

arch="$(docker image inspect "$UPSTREAM" --format '{{.Architecture}}')"
[[ "$arch" == arm64 ]] || { echo "Expected arm64, got $arch" >&2; exit 1; }

upstream_digest="$(docker image inspect "$UPSTREAM" --format '{{index .RepoDigests 0}}')"
[[ "$upstream_digest" == *@sha256:* ]] || { echo 'Could not resolve upstream digest.' >&2; exit 1; }

docker tag "$UPSTREAM" "$IMAGE"
docker push "$IMAGE"

mkdir -p rendered
docker image inspect "$IMAGE" --format '{{index .RepoDigests 0}}' > rendered/image.txt
printf '%s\n' "$upstream_digest" > rendered/upstream-image.txt

echo 'Build complete. Pinned image:'
cat rendered/image.txt
echo 'Run bash deploy.sh --dry-run to preview the rollout.'
