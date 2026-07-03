# ============================================================
#  CrewAI Agent — FastAPI 服务
#  build context: armbianbegin/ (工程根目录)
# ============================================================
#  构建: cd armbianbegin && docker build -f fastapi/Dockerfile -t agent-api .
# ============================================================
ARG REGISTRY=arm-cluster-master:5000
FROM ${REGISTRY}/base:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip && \
    rm -rf /var/lib/apt/lists/* && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3 1

WORKDIR /app

# 分层：先装依赖（利用 Docker 缓存）
COPY fastapi/requirements.txt          ./requirements-fastapi.txt
COPY panghu_agent/crewai/requirements.txt  ./requirements-crewai.txt
RUN pip install --break-system-packages --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r requirements-fastapi.txt \
    -r requirements-crewai.txt

# 复制源码
COPY panghu_agent/crewai/ ./crewai/
COPY fastapi/app/         ./app/

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
