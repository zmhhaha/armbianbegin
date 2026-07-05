# ============================================================
#  Generic Agent API Runtime — FastAPI
#  build context: armbianbegin/ (工程根目录)
#  AGENT_NAME 对应 panghu_agent 中的 agent 目录名
# ============================================================
ARG REGISTRY=arm-cluster-master:5000
ARG AGENT_NAME=panghu_agent
FROM ${REGISTRY}/base:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip && \
    rm -rf /var/lib/apt/lists/* && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3 1

WORKDIR /app

COPY panghu_agent/crewai/requirements.txt ./requirements-crewai.txt
COPY fastapi/requirements.txt                ./requirements-fastapi.txt
RUN pip install --break-system-packages --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r requirements-fastapi.txt \
    -r requirements-crewai.txt

COPY panghu_agent/crewai/       ./crewai/
COPY panghu_agent/api/          ./api/
COPY panghu_agent/api_server/main.py   ./api_server/main.py

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1
CMD ["python", "-m", "uvicorn", "api_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
