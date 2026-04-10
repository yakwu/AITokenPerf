# ---- 前端构建阶段 ----
FROM oven/bun:1 AS builder

WORKDIR /app/frontend

# 先复制依赖声明，利用 Docker 层缓存
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile

# 再复制源码（源码变更不会使 install 层失效）
COPY frontend/ ./
RUN bun run build

# ---- 运行阶段 ----
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends tzdata && \
    ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖（使用 BuildKit 缓存挂载加速）
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# 复制后端代码
COPY app/ app/
COPY main.py .

# 复制前端构建产物
COPY --from=builder /app/static/ static/

# 复制其他必要文件
COPY start.sh build.sh ./

EXPOSE 8080

CMD ["python3", "main.py", "--host", "0.0.0.0", "--port", "8080"]
