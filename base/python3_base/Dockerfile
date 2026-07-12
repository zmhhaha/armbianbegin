# docker build -t ${REGISTRY}/python3_base:latest .
# docker tag python3_base:latest ${REGISTRY}/python3_base:latest
# docker push ${REGISTRY}/python3_base:latest

ARG REGISTRY=arm-cluster-master:5000
FROM ${REGISTRY}/base:latest

RUN apt-get install -y python3 python3-pip python3-venv python3-dev && \
    rm -rf /var/lib/apt/lists/* && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3 1 && \
    pip3 config set global.index-url https://mirrors.aliyun.com/pypi/simple/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_BREAK_SYSTEM_PACKAGES=1
