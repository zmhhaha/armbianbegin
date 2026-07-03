# ============================================================
#  FastAPI Agent 服务 — ARM64 K8s 部署
#  基于自建 base 镜像（Debian + 国内源）
# ============================================================
ARG REGISTRY=arm-cluster-master:5000
FROM ${REGISTRY}/base:latest

LABEL maintainer="zmhhaha"
LABEL description="CrewAI Agent — FastAPI REST API"

# 安装 Python 全家桶（base 镜像已配好国内源）
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/* && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3 1

WORKDIR /app

# 分层安装依赖（利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --break-system-packages --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r requirements.txt

# 复制源码（build context 为工程根目录，来自 panghu_agent submodule）
COPY panghu_agent/crewai/ ./crewai/
COPY panghu_agent/api/    ./api/

ENV PYTHONUNBUFFERED=1 \
    API_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:${API_PORT}/health || exit 1

CMD ["sh", "-c", "python -m uvicorn api.server:app --host 0.0.0.0 --port ${API_PORT:-8000}"]
