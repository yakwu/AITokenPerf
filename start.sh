#!/bin/bash
# 一键启动前端(Vite dev) + 后端(Python)
# 前端 http://localhost:5180 (含 HMR)
# 后端 http://localhost:8080

set -e
cd "$(dirname "$0")"

# 启动后端
./venv/bin/python3 -m uvicorn server:app --host 127.0.0.1 --port 8080 "$@" &
BACKEND_PID=$!

# 启动前端 dev server
cd frontend
bun run dev &
FRONTEND_PID=$!

# Ctrl-C 同时关掉两个
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM

echo ""
echo "前端: http://localhost:5180"
echo "后端: http://localhost:8080"
echo ""

wait
