#docker build -t ${REGISTRY}/base:latest .
#docker tag ${REGISTRY}/base:latest ${REGISTRY}/base:latest
#docker push ${REGISTRY}/base:latest

ARG REGISTRY=arm-cluster-master:5000
FROM arm64v8/debian:latest

RUN sed -i "s/deb.debian.org/mirrors.ustc.edu.cn/g" /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y wget curl ssh net-tools telnet iputils-ping dnsutils which