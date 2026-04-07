FROM python:3.12-slim AS builder

# 安装 bun 用于构建前端
RUN apt-get update && apt-get install -y --no-install-recommends curl unzip \
    && curl -fsSL https://bun.sh/install | bash \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.bun/bin:${PATH}"

WORKDIR /app
COPY frontend/ frontend/
RUN cd frontend && bun install && bun run build

# ---- 运行阶段 ----
FROM python:3.12-slim

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY app/ app/
COPY main.py .

# 复制前端构建产物
COPY --from=builder /app/static/ static/

# 复制其他必要文件
COPY start.sh build.sh ./

EXPOSE 8080

CMD ["python3", "main.py", "--host", "0.0.0.0", "--port", "8080"]
