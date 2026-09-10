FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY prepare_model.py .
ARG MODEL_SHA256
RUN python prepare_model.py --sha256 "$MODEL_SHA256" --destination /models/fast-bge-small-zh-v1.5
ENV PYTHONDONTWRITEBYTECODE=1 TOKENIZERS_PARALLELISM=false
USER 10001:10001
ENV MODEL_DIR=/models/fast-bge-small-zh-v1.5
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
