FROM python:3.11-slim
WORKDIR /app

# 国内 pip 源（默认清华，可用 --build-arg PIP_INDEX_URL 覆盖）
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" --timeout 120 --retries 5 -r requirements.txt

# 显式列出模块：新增 .py 时必须同步加进这一行，否则镜像里 import 不到
COPY app.py auth.py config.py guard.py upstream.py ./
# 日报脚本：由 llm-report 命名空间的 CronJob 复用本镜像执行（见 report/k8s.yaml）
COPY report/report.py ./report.py

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10002:10002
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
