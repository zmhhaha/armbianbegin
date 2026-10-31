#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

case "${1:-}" in
  --no-push) PUSH=false ;;
  --push|"") PUSH=true ;;
  --help|-h)
    cat <<'EOF'
Usage: bash speech-service/build.sh [--no-push]

Builds linux/arm64 and uses only the application tag :latest.
Prepare the verified source, runtime and English frontend cache first.
REGISTRY defaults to arm-cluster-master:5000.
SOURCE_REVISION defaults to the local Git commit and is required without Git.
CONTAINER_CLI may be docker or nerdctl (default: docker).
PYTHON defaults to python3; BASE_IMAGE may pin a reviewed base-image digest.
EOF
    exit 0 ;;
  *) echo "Unsupported argument: $1" >&2; exit 2 ;;
esac

REGISTRY="${REGISTRY:-arm-cluster-master:5000}"
IMAGE="${IMAGE:-${REGISTRY}/speech-service:latest}"
if [[ "${IMAGE}" != *:latest ]]; then
  echo "Application image must use the :latest tag" >&2
  exit 2
fi
SOURCE_REVISION="${SOURCE_REVISION:-$(git -C "${SCRIPT_DIR}" rev-parse HEAD 2>/dev/null || true)}"
if [[ ! "${SOURCE_REVISION}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "A full Git SOURCE_REVISION is required for release identity" >&2
  exit 2
fi
PYTHON="${PYTHON:-python3}"
read -r -a ENGINE <<< "${CONTAINER_CLI:-docker}"
"${PYTHON}" "${SCRIPT_DIR}/scripts/prepare_image.py" --root "${SCRIPT_DIR}"

"${ENGINE[@]}" build --platform linux/arm64 \
  --build-arg "BASE_IMAGE=${BASE_IMAGE:-python:3.11-slim-bookworm}" \
  --build-arg "PIP_INDEX_URL=${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}" \
  --build-arg "SOURCE_REVISION=${SOURCE_REVISION}" \
  --build-arg "BUILD_CREATED=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  -t "${IMAGE}" "${SCRIPT_DIR}"
if [[ "${PUSH}" == true ]]; then
  "${ENGINE[@]}" push "${IMAGE}"
fi
echo "Image ready: ${IMAGE}; source revision: ${SOURCE_REVISION}"
