#!/usr/bin/env bash
set -euo pipefail

# Build the OpenSpec Service image from any working directory.
# Defaults match the ARM64 cluster registry used by armbianbegin.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE_NAME="${IMAGE_NAME:-openspec-service}"
IMAGE_TAG="${IMAGE_TAG:-0.1.0}"
PLATFORM="${PLATFORM:-linux/arm64}"
IMAGE="${IMAGE:-${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}}"
PUSH=1

usage() {
  cat <<'EOF'
Usage: ./scripts/build.sh [options]

Build and push the OpenSpec Service image.

Options:
  --no-push       Build only; do not push to the registry
  --platform VAL  Override the Docker platform (default: linux/arm64)
  --tag VAL       Override the image tag (default: 0.1.0)
  --image VAL     Use a complete image reference
  -h, --help      Show this help

Environment overrides: REGISTRY, IMAGE_NAME, IMAGE_TAG, PLATFORM, IMAGE
EOF
}

while (($# > 0)); do
  case "$1" in
    --no-push)
      PUSH=0
      ;;
    --platform)
      (($# >= 2)) || { echo "ERROR: --platform requires a value" >&2; exit 2; }
      PLATFORM="$2"
      shift
      ;;
    --tag)
      (($# >= 2)) || { echo "ERROR: --tag requires a value" >&2; exit 2; }
      IMAGE_TAG="$2"
      IMAGE="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
      shift
      ;;
    --image)
      (($# >= 2)) || { echo "ERROR: --image requires a value" >&2; exit 2; }
      IMAGE="$2"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

command -v docker >/dev/null 2>&1 || { echo "ERROR: docker command not found" >&2; exit 1; }

echo "=== Building ${IMAGE} for ${PLATFORM} ==="
docker build --platform "${PLATFORM}" -t "${IMAGE}" "${SERVICE_DIR}"

if ((PUSH)); then
  echo "=== Pushing ${IMAGE} ==="
  docker push "${IMAGE}"
  echo "Image published: ${IMAGE}"
else
  echo "Image built locally: ${IMAGE}"
fi
