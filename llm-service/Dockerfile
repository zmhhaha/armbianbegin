FROM python:3.11-slim
WORKDIR /app

# 国内 pip 源（默认清华，可用 --build-arg PIP_INDEX_URL 覆盖）
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" --timeout 120 --retries 5 -r requirements.txt

COPY app.py config.py upstream.py ./

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10002:10002
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
