script_dir="$(cd "$(dirname "$0")" && pwd)"
[ -f "${script_dir}/../cluster_config.sh" ] && source "${script_dir}/../cluster_config.sh"
docker build -f Dockerfile_gitea -t gitea_base:latest .
docker tag gitea_base:latest ${REGISTRY}/gitea_base:latest
docker push ${REGISTRY}/gitea_base:latest

# docker pull arm64v8/mysql:latest
# docker tag arm64v8/mysql:latest ${REGISTRY}/mysql:latest
# docker push ${REGISTRY}/mysql:latest

kubectl apply -f gitea-namespace.yaml
kubectl apply -f gitea-env.yaml
kubectl apply -f gitea.yaml

# https://docs.drone.io/
docker pull drone/drone:2.21
docker tag drone/drone:2.21 ${REGISTRY}/drone:2.21
docker push ${REGISTRY}/drone:2.21

kubectl edit configmap coredns -n kube-system
# 这部分是要修改的
# hosts {
#   192.168.137.101 gitea.zmh.com
#   192.168.137.101 drone.zmh.com
#   fallthrough
# }
kubectl rollout restart deployment/coredns -n kube-system

# https://hub.docker.com/r/drone/drone-runner-kube
git clone https://github.com/drone-runners/drone-runner-kube.git
wget https://dl.google.com/go/go1.16.4.linux-arm64.tar.gz
tar -C /usr/local -xzf go1.16.4.linux-arm64.tar.gz

cat >> /etc/profile << EOF
export GOROOT=/usr/local/go  
export GOPATH=\$HOME/go  
export PATH=\$PATH:\$GOROOT/bin:\$GOPATH/bin
EOF

export GOPROXY=https://mirrors.aliyun.com/goproxy,direct
bash ./scripts/build.sh
docker build -t drone/drone-runner-kube:latest-linux-arm64 -f docker/Dockerfile.linux.arm64 .
docker tag drone/drone-runner-kube:latest-linux-arm64 ${REGISTRY}/drone-runner-kube:latest-linux-arm64
docker push ${REGISTRY}/drone-runner-kube:latest-linux-arm64

# gcc_compiler
docker build -f Dockerfile_gcc -t gcc_compiler:latest .
docker tag gcc_compiler:latest ${REGISTRY}/gcc_compiler:latest
docker push ${REGISTRY}/gcc_compiler:latest

# bison_flex_compiler
docker build -f Dockerfile_bison_flex -t bison_flex_compiler:latest .
docker tag bison_flex_compiler:latest ${REGISTRY}/bison_flex_compiler:latest
docker push ${REGISTRY}/bison_flex_compiler:latest