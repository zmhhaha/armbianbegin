# Agent Portal — 静态首页（通过 ConfigMap + python http.server 部署）
# 实际部署使用 k8s.yaml（不从 Dockerfile 构建）
ARG REGISTRY=arm-cluster-master:5000
FROM ${REGISTRY}/base:latest
COPY index.html /www/index.html
EXPOSE 8080
CMD ["python3", "-m", "http.server", "8080", "--directory", "/www"]
