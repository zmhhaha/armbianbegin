FROM arm64v8/node:22-bookworm-slim
# OpenSpec Service spawns git for clone/commit/merge; the slim node image
# does not include it. Use the USTC apt mirror (same approach as base/Dockerfile)
# because the cluster cannot reach deb.debian.org reliably for apt.
RUN sed -i -e "s/deb.debian.org/mirrors.ustc.edu.cn/g" \
           -e "s/security.debian.org/mirrors.ustc.edu.cn/g" \
           /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y --no-install-recommends git ca-certificates && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY src ./src
RUN useradd --uid 10001 --create-home app
USER 10001
ENV NODE_ENV=production PORT=8080 WORKSPACE_ROOT=/data/workspaces
EXPOSE 8080
CMD ["node","src/server.mjs"]
