# ============================================================
#  Cloudflare Tunnel Operator
#  基于自建 base 镜像 + kopf 框架
# ============================================================
ARG REGISTRY=arm-cluster-master:5000
FROM ${REGISTRY}/base:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip && \
    rm -rf /var/lib/apt/lists/* && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3 1

WORKDIR /app
COPY requirements.txt .
RUN pip install --break-system-packages --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r requirements.txt

COPY controller.py .

CMD ["kopf", "run", "controller.py", "--all-namespaces", "--verbose"]
