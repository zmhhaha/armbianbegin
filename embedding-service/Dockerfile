FROM python:3.11-slim
WORKDIR /app

# 国内 pip 源（默认清华，可用 --build-arg PIP_INDEX_URL 覆盖）
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" --timeout 120 --retries 5 -r requirements.txt

COPY app.py .
COPY prepare_model.py .

# 国内模型源（默认 hf-mirror），SHA 可选做固定校验
ARG MODEL_BASE_URL=https://hf-mirror.com/Qdrant/bge-small-zh-v1.5/resolve/main
ARG MODEL_SHA256=""
ARG TOKENIZER_SHA256=""
RUN python prepare_model.py \
      --destination /models/fast-bge-small-zh-v1.5 \
      --base-url "${MODEL_BASE_URL}" \
      --sha256 "${MODEL_SHA256}" \
      --tokenizer-sha256 "${TOKENIZER_SHA256}"

ENV PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false
USER 10001:10001
ENV MODEL_DIR=/models/fast-bge-small-zh-v1.5
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
