# ============================================================
#  Generic Gradio Runtime — ARM64
#  基于自建 base 镜像，预装 Gradio
#  用户 app.py 通过 COPY 或 volume 挂载到 /app
# ============================================================
#  构建: docker build --build-arg REGISTRY=arm-cluster-master:5000 -t gradio-runtime .
#  使用: docker run -v ./myapp:/app -p 7860:7860 gradio-runtime
# ============================================================
ARG REGISTRY=arm-cluster-master:5000
FROM ${REGISTRY}/base:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip && \
    rm -rf /var/lib/apt/lists/* && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3 1 && \
    pip install --break-system-packages --no-cache-dir \
      -i https://mirrors.aliyun.com/pypi/simple/ \
      --trusted-host mirrors.aliyun.com \
      gradio python-dotenv

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME="0.0.0.0" \
    GRADIO_SERVER_PORT="7860"

EXPOSE 7860

CMD ["python", "app.py"]
