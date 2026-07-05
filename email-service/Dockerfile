# ============================================================
#  Email Service — SMTP 发信微服务
#  build context: armbianbegin/email-service/
# ============================================================
ARG REGISTRY=arm-cluster-master:5000
FROM ${REGISTRY}/base:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY server.py .

ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1
CMD ["python3", "server.py"]
