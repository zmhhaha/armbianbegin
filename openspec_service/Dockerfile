FROM arm64v8/node:22-bookworm-slim
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY src ./src
RUN useradd --uid 10001 --create-home app
USER 10001
ENV NODE_ENV=production PORT=8080 WORKSPACE_ROOT=/data/workspaces
EXPOSE 8080
CMD ["node","src/server.mjs"]
