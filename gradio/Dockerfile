# ============================================================
#  Gradio Agent UI — ARM64 K8s 部署
#  提供 Web 聊天界面，后台调用 CrewAI Agent
# ============================================================
ARG REGISTRY=arm-cluster-master:5000
FROM ${REGISTRY}/base:latest

LABEL maintainer="zmhhaha"
LABEL description="CrewAI Agent — Gradio Web UI"

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

# 复制 Agent 代码（来自 panghu_agent submodule）+ Gradio app
COPY panghu_agent/crewai/ ./crewai/
COPY gradio/app.py .

ENV PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME="0.0.0.0" \
    GRADIO_SERVER_PORT="7860"

EXPOSE 7860

CMD ["python", "app.py"]
