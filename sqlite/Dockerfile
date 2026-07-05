# ============================================================
#  SQLite Data Service — 持久化 SQLite + HTTP API
#  基于 Python http.server + sqlite3，零依赖
# ============================================================
ARG REGISTRY=arm-cluster-master:5000
FROM ${REGISTRY}/base:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 sqlite3 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server.py .

RUN mkdir -p /data && chmod 777 /data

ENV DB_PATH=/data/data.db
EXPOSE 8000

# 极简 HTTP API：GET/POST 直接操作 SQLite
CMD ["python3", "server.py"]
