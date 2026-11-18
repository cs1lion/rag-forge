#!/usr/bin/env bash
# 一键冷启动脚本：检查/安装依赖 → 初始化目录 → 启动 FastAPI 后端与 Vite 前端。
# 用法：
#   bash start.sh                # 前台运行（Ctrl-C 同时停前后端）
#   bash start.sh --daemon       # 后台运行，日志写到 logs/backend.log / logs/frontend.log
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
DAEMON="${1:-}"

echo "=============================================="
echo " 知识库问答与自动问答视频生成工作台 · 一键启动"
echo "=============================================="

# ── 0. 环境检查 ────────────────────────────────────────────────
command -v python >/dev/null 2>&1 || { echo "[FATAL] 未找到 python"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "[FATAL] 未找到 node"; exit 1; }
command -v ffmpeg >/dev/null 2>&1 || echo "[WARN] 未找到 ffmpeg（视频合成需要）"

PY_VER=$(python -c 'import sys; print(sys.version_info.major * 10 + sys.version_info.minor)')
if [ "$PY_VER" -lt 311 ]; then
  echo "[FATAL] 需要 Python 3.11+，当前 $(python --version)"
  exit 1
fi

# ── 1. .env 检查（LLM Key 必须真实配置，严禁 Mock）──────────────
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo "[INIT] 已复制 .env.example → .env，请填写 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 后重跑"
  else
    echo "[FATAL] 缺少 .env（且无 .env.example 可复制）"
    exit 1
  fi
fi
# 提醒：Key 为空时问答会降级为安全拒答（非 Mock），但无法产出真实回答
if ! grep -qE '^LLM_API_KEY=.+' .env 2>/dev/null; then
  echo "[WARN] .env 中 LLM_API_KEY 为空 —— 问答将全部降级为安全拒答（仍非 Mock）"
fi

# ── 2. 后端依赖 ────────────────────────────────────────────────
echo "[DEPS] 检查后端依赖 ..."
if ! python -c "import fastapi, uvicorn, httpx, edge_tts, PIL" >/dev/null 2>&1; then
  echo "[DEPS] 安装 backend/requirements.txt ..."
  python -m pip install -q -r backend/requirements.txt
fi

# ── 3. 前端依赖 ────────────────────────────────────────────────
echo "[DEPS] 检查前端依赖 ..."
if [ ! -d frontend/node_modules ]; then
  echo "[DEPS] 安装前端依赖 (npm ci/install) ..."
  ( cd frontend && npm install --no-audit --no-fund )
fi

# ── 4. 初始化目录与数据库 ──────────────────────────────────────
echo "[INIT] 初始化存储目录 ..."
mkdir -p backend/storage/uploads backend/storage/videos logs
# SQLite 表结构由后端 lifespan 幂等创建（init_db）；语料在知识库非空时自动入库。

# ── 5. 端口占用处理 ────────────────────────────────────────────
for PORT in 8000 5173; do
  if command -v netstat >/dev/null 2>&1; then
    PIDS=$(netstat -ano 2>/dev/null | grep ":$PORT " | grep LISTENING | awk '{print $NF}' | sort -u)
    if [ -n "$PIDS" ]; then
      echo "[PORT] 端口 $PORT 被占用（PID: $PIDS），尝试释放 ..."
      for P in $PIDS; do taskkill //PID "$P" //F >/dev/null 2>&1 || true; done
      sleep 2
    fi
  fi
done

# ── 6. 启动 ────────────────────────────────────────────────────
start_backend() {
  echo "[START] 后端 FastAPI → http://localhost:8000 ..."
  ( cd backend && nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
      > "$ROOT/logs/backend.log" 2>&1 & echo $! > "$ROOT/logs/backend.pid" )
  # 等 /health 就绪
  for i in $(seq 1 30); do
    if curl -sf -m 3 http://localhost:8000/health >/dev/null 2>&1; then
      echo "[READY] 后端已就绪：$(curl -s -m 3 http://localhost:8000/health)"
      return 0
    fi
    sleep 1
  done
  echo "[FATAL] 后端 30s 内未就绪，见 logs/backend.log"
  tail -20 logs/backend.log || true
  return 1
}

start_frontend() {
  echo "[START] 前端 Vite → http://localhost:5173 ..."
  ( cd frontend && nohup npm run dev -- --host 0.0.0.0 --port 5173 \
      > "$ROOT/logs/frontend.log" 2>&1 & echo $! > "$ROOT/logs/frontend.pid" )
  for i in $(seq 1 60); do
    if curl -sf -m 3 http://localhost:5173/ >/dev/null 2>&1; then
      echo "[READY] 前端已就绪：http://localhost:5173"
      return 0
    fi
    sleep 1
  done
  echo "[WARN] 前端 60s 内未就绪（可能仍在安装依赖），见 logs/frontend.log"
  return 0
}

if [ "$DAEMON" = "--daemon" ]; then
  start_backend
  start_frontend
  echo "----------------------------------------------"
  echo " 后端 API  : http://localhost:8000  (logs/backend.log)"
  echo " 前端页面  : http://localhost:5173  (logs/frontend.log)"
  echo " 停止服务  : kill \$(cat logs/backend.pid) \$(cat logs/frontend.pid)"
  echo "----------------------------------------------"
else
  # 前台模式：子进程随 Ctrl-C 退出
  cleanup() {
    echo ""
    echo "[STOP] 停止前后端 ..."
    [ -f logs/backend.pid ]  && kill "$(cat logs/backend.pid)"  2>/dev/null || true
    [ -f logs/frontend.pid ] && kill "$(cat logs/frontend.pid)" 2>/dev/null || true
    exit 0
  }
  trap cleanup INT TERM
  start_backend &
  BACKEND_JOB=$!
  start_frontend &
  FRONTEND_JOB=$!
  echo "----------------------------------------------"
  echo " 后端 API  : http://localhost:8000  (logs/backend.log)"
  echo " 前端页面  : http://localhost:5173  (logs/frontend.log)"
  echo " Ctrl-C 停止全部服务"
  echo "----------------------------------------------"
  wait $BACKEND_JOB $FRONTEND_JOB
fi
