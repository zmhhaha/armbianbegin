#!/usr/bin/env bash
# First deployment: run "build", then deploy-gitea.sh, configure OAuth, and
# finally deploy-drone.sh. "all" assumes both Vault paths are already ready.
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "${script_dir}"
[ -f "../cluster_config.sh" ] && source "../cluster_config.sh"
: "${REGISTRY:?REGISTRY must be set by cluster_config.sh}"

build_images() {
    docker build -f Dockerfile_gitea -t gitea_base:latest .
    docker tag gitea_base:latest "${REGISTRY}/gitea_base:latest"
    docker push "${REGISTRY}/gitea_base:latest"

    docker pull drone/drone:2.21
    docker tag drone/drone:2.21 "${REGISTRY}/drone:2.21"
    docker push "${REGISTRY}/drone:2.21"

    if [ ! -d drone-runner-kube ]; then
        git clone https://github.com/drone-runners/drone-runner-kube.git
    fi
    pushd drone-runner-kube >/dev/null
    # Aliyun's mirror currently serves a checksum-mismatched docker/distribution
    # module for this legacy runner; use the Chinese Go proxy with sumdb checks.
    export GOPROXY=https://goproxy.cn,direct
    export GOSUMDB=sum.golang.org
    go clean -modcache
    bash ./scripts/build.sh
    docker build -t drone/drone-runner-kube:latest-linux-arm64 -f ../Dockerfile_drone_runner_kube .
    docker tag drone/drone-runner-kube:latest-linux-arm64 "${REGISTRY}/drone-runner-kube:latest-linux-arm64"
    docker push "${REGISTRY}/drone-runner-kube:latest-linux-arm64"
    popd >/dev/null

    docker build -f gcc_compiler/Dockerfile_gcc -t gcc_compiler:latest .
    docker tag gcc_compiler:latest "${REGISTRY}/gcc_compiler:latest"
    docker push "${REGISTRY}/gcc_compiler:latest"

    docker build -f bison_flex_compiler/Dockerfile_bison_flex -t bison_flex_compiler:latest .
    docker tag bison_flex_compiler:latest "${REGISTRY}/bison_flex_compiler:latest"
    docker push "${REGISTRY}/bison_flex_compiler:latest"
}

deploy_all() {
    kubectl apply -f gitops-namespace.yaml
    kubectl apply -f drone-builds-namespace.yaml
    kubectl apply -f external-secrets.yaml
    for secret in gitea-secrets drone-server-secrets drone-runner-secrets; do
        kubectl wait --for=condition=Ready "externalsecret/${secret}" -n gitops --timeout=120s
    done
    kubectl apply -f gitea-env.yaml
    kubectl apply -f gitea.yaml
    kubectl apply -f drone-env.yaml
    kubectl apply -f drone.yaml
    kubectl apply -f ../cloudflare-tunnel/operator/gitops-routes.yaml
}

case "${1:-build}" in
    build) build_images ;;
    deploy) deploy_all ;;
    all) build_images; deploy_all ;;
    *) echo "Usage: $0 [build|deploy|all]" >&2; exit 2 ;;
esac
