#!/usr/bin/env bash
# WMP 本地开发环境一键管理：PostgreSQL + RustFS + 后端 + 前端
# 用法：
#   ./scripts/dev-services.sh start    启动全部服务（已运行的自动跳过）
#   ./scripts/dev-services.sh stop     停止全部服务
#   ./scripts/dev-services.sh status   查看各服务状态
#   ./scripts/dev-services.sh logs     查看最近日志（按服务分文件，见 .cache/services/logs/）
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
SVC="$ROOT/.cache/services"
PG_BIN="$SVC/postgres/Postgres.app/Contents/Versions/17/bin"
PGDATA="$SVC/data/postgres"
RUSTFS_BIN="$SVC/rustfs/rustfs"
RUSTDATA="$SVC/data/rustfs"
LOGS="$SVC/logs"
PY="$ROOT/.venv/bin/python"
BACKEND_PID="$SVC/backend.pid"
FRONTEND_PID="$SVC/frontend.pid"

mkdir -p "$LOGS"

alive() { [[ -f "$1" ]] && kill -0 "$(cat "$1" 2>/dev/null)" 2>/dev/null; }

wait_for() { # wait_for <描述> <命令...>
  local desc="$1"; shift
  for _ in $(seq 1 60); do
    if "$@" >/dev/null 2>&1; then echo "  ✓ $desc"; return 0; fi
    sleep 1
  done
  echo "  ✗ $desc 超时，请查看 $LOGS 下对应日志" >&2; return 1
}

pg_running() { "$PG_BIN/pg_ctl" -D "$PGDATA" -s status >/dev/null 2>&1; }

do_start() {
  echo "==> 1/4 PostgreSQL"
  if pg_running; then echo "  ✓ 已在运行"; else
    "$PG_BIN/pg_ctl" -D "$PGDATA" -l "$LOGS/postgres.log" -w -t 60 start
    echo "  ✓ 已启动"
  fi

  echo "==> 2/4 RustFS（对象存储 :9000）"
  if alive "$SVC/rustfs.pid"; then echo "  ✓ 已在运行"; else
    RUSTFS_ACCESS_KEY=wmp RUSTFS_SECRET_KEY=wmp-secret \
      nohup "$RUSTFS_BIN" server "$RUSTDATA" >>"$LOGS/rustfs.log" 2>&1 &
    echo $! > "$SVC/rustfs.pid"
  fi
  wait_for "RustFS 就绪" curl -s -o /dev/null http://127.0.0.1:9000
  if [[ -f "$SVC/configure_storage.py" ]]; then
    "$PY" "$SVC/configure_storage.py" || echo "  ! 存储配置校验未通过（桶可能已存在则忽略）"
  fi

  echo "==> 3/4 后端（:8000）"
  if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then echo "  ✓ 已在运行"; else
    (cd backend && nohup "$ROOT/.venv/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 >>"$LOGS/backend.log" 2>&1 & echo $! > "$BACKEND_PID")
  fi
  wait_for "后端就绪" curl -sf http://127.0.0.1:8000/health

  echo "==> 4/4 前端（:7100）"
  if alive "$FRONTEND_PID"; then echo "  ✓ 已在运行"; else
    nohup npm run dev -- --host 127.0.0.1 --port 7100 >>"$LOGS/frontend.log" 2>&1 &
    echo $! > "$FRONTEND_PID"
  fi
  wait_for "前端就绪" curl -s -o /dev/null http://127.0.0.1:7100/login

  echo ""
  echo "全部就绪：前端 http://localhost:7100  后端 API http://127.0.0.1:8000  Swagger /docs"
}

do_stop() {
  for name in FRONTEND BACKEND; do
    pid_file_var="${name}_PID"; pid_file="${!pid_file_var}"
    if alive "$pid_file"; then kill "$(cat "$pid_file")" 2>/dev/null; echo "已停止 $name (PID $(cat "$pid_file"))"; fi
    rm -f "$pid_file"
  done
  pkill -f "uvicorn app.main:app" 2>/dev/null && echo "已停止后端残留进程" || true
  if alive "$SVC/rustfs.pid"; then kill "$(cat "$SVC/rustfs.pid")" 2>/dev/null; echo "已停止 RustFS"; fi
  rm -f "$SVC/rustfs.pid"
  if pg_running; then "$PG_BIN/pg_ctl" -D "$PGDATA" -m fast -w stop; echo "已停止 PostgreSQL"; fi
}

do_status() {
  pg_running && echo "PostgreSQL  : 运行中" || echo "PostgreSQL  : 未运行"
  alive "$SVC/rustfs.pid" && echo "RustFS      : 运行中 (PID $(cat "$SVC/rustfs.pid"))" || echo "RustFS      : 未运行"
  curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1 && echo "后端 :8000  : 运行中" || echo "后端 :8000  : 未运行"
  alive "$FRONTEND_PID" && echo "前端 :7100  : 运行中 (PID $(cat "$FRONTEND_PID"))" || echo "前端 :7100  : 未运行"
  curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1 && echo "健康检查    : /health 通过" || echo "健康检查    : 未通过"
}

case "${1:-}" in
  start)  do_start ;;
  stop)   do_stop ;;
  status) do_status ;;
  logs)   ls -lt "$LOGS" | head -10 ;;
  *) echo "用法: $0 {start|stop|status|logs}" >&2; exit 1 ;;
esac
