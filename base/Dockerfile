#docker build -t base:latest .

FROM arm64v8/debian:latest

RUN sed -i "s/deb.debian.org/mirrors.ustc.edu.cn/g" /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y wget curl ssh net-tools telnet iputils-ping dnsutils which