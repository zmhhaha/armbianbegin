# ============================================================
#  Generic Agent UI Runtime — Gradio
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

COPY gradio/requirements.txt               ./requirements-gradio.txt
COPY panghu_agent/crewai/requirements.txt ./requirements-crewai.txt
RUN pip install --break-system-packages --no-cache-dir \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    -r requirements-gradio.txt \
    -r requirements-crewai.txt

COPY panghu_agent/crewai/       ./crewai/
COPY panghu_agent/gradio_app.py ./app.py

ENV PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME="0.0.0.0" \
    GRADIO_SERVER_PORT="7860"
EXPOSE 7860
CMD ["python", "app.py"]
