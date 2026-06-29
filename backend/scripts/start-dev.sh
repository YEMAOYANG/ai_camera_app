#!/usr/bin/env bash
# 一键启动本地联调栈：
#   ai_camera_test 媒体层（可选：go2rtc + speaker/task，不含 voice worker）
#   Guardian 后端（app.py：API + WS + 作息调度）
#   Guardian 观察 worker + 本地 voice worker（mock/ASR）
#
# 用法（在 backend 目录）：
#   ./scripts/start-dev.sh              # 启动后在终端实时输出 API 日志
#   ./scripts/start-dev.sh --quiet      # 仅写日志文件，终端不跟日志
#   ./scripts/start-dev.sh --logs all   # 同时跟 app + worker 日志
#
# Ctrl+C 会停止本脚本拉起的所有进程。
#
# 语音提醒完整播放：在 ai_camera_test 的 .env 中建议设置
#   CAMERA_SPEAKER_GO2RTC_PACED_HTTP=1
#   CAMERA_SPEAKER_STREAM_CHUNK_MS=40
#   CAMERA_SPEAKER_TRANSPORT_TAIL_SECONDS=0.8
#   CAMERA_SPEAKER_PLAYBACK_BUFFER_SECONDS=1.2
#   CAMERA_SPEAKER_TAIL_SECONDS=0.5
# 详见 backend/.env.example

set -euo pipefail

FOLLOW_LOGS=app
while [ $# -gt 0 ]; do
  case "$1" in
    --quiet)
      FOLLOW_LOGS=none
      shift
      ;;
    --logs=*)
      FOLLOW_LOGS="${1#*=}"
      shift
      ;;
    --logs)
      FOLLOW_LOGS="${2:-app}"
      shift 2
      ;;
    --help|-h)
      echo "用法: ./scripts/start-dev.sh [--quiet] [--logs app|worker|all]"
      exit 0
      ;;
    *)
      echo "未知参数: $1（可用 --help）" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$BACKEND_DIR/.env"
LOG_DIR="${GUARDIAN_DEV_LOG_DIR:-/tmp/guardian-dev}"
PID_DIR="$LOG_DIR/pids"

CAMERA_PORT=8767
GO2RTC_PORT=1984
GUARDIAN_PORT=8000
GUARDIAN_WS_PORT=8001

PIDS=()
CLEANED=0

mkdir -p "$LOG_DIR" "$PID_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "$1"; }
ok() { log "${GREEN}✓${NC} $1"; }
warn() { log "${YELLOW}!${NC} $1"; }
err() { log "${RED}✗${NC} $1"; }

load_env_file() {
  local file="$1"
  [ -f "$file" ] || return 0
  while IFS= read -r raw_line || [ -n "$raw_line" ]; do
    line="${raw_line%%#*}"
    line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -n "$line" ] || continue
    case "$line" in *=*) ;; *) continue ;; esac
    key="${line%%=*}"
    value="${line#*=}"
    key="$(echo "$key" | sed 's/[[:space:]]*$//')"
    value="$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    value="${value%\"}"; value="${value#\"}"
    value="${value%\'}"; value="${value#\'}"
    if [ -n "$key" ] && [ -z "${!key+x}" ]; then
      export "$key=$value"
    fi
  done < "$file"
}

url_ok() {
  local url="$1"
  local code
  code="$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$url" 2>/dev/null || echo 000)"
  [ "$code" = "200" ] || [ "$code" = "404" ]
}

port_listening() {
  lsof -tiTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

wait_for_guardian() {
  local pid="$1"
  local attempts="${2:-20}"
  local i=0
  while [ "$i" -lt "$attempts" ]; do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 1
    fi
    if port_listening "$GUARDIAN_PORT" && url_ok "http://127.0.0.1:${GUARDIAN_PORT}/api/health"; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  return 1
}

show_startup_errors() {
  local log_file="$1"
  [ -f "$log_file" ] || return 0
  if grep -qE 'Traceback|Error:|OSError|Address already in use|Exception|SyntaxError' "$log_file" 2>/dev/null; then
    warn "最近错误片段:"
    grep -E 'Traceback|Error:|OSError|Address already in use|Exception|SyntaxError|File "' "$log_file" | tail -15 || true
  else
    tail -15 "$log_file" || true
  fi
}

record_pid() {
  local name="$1"
  local pid="$2"
  PIDS+=("$pid")
  echo "$pid" > "$PID_DIR/$name.pid"
}

stop_pid_file() {
  local name="$1"
  local file="$PID_DIR/$name.pid"
  if [ -f "$file" ]; then
    local pid
    pid="$(cat "$file" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
    rm -f "$file"
  fi
}

stop_listeners_on_port() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  [ -n "$pids" ] || return 0
  warn "停止占用端口 ${port} 的进程: $(echo "$pids" | tr '\n' ' ' | sed 's/ $//')"
  for pid in $pids; do
    kill "$pid" 2>/dev/null || true
  done
  sleep 1
  for pid in $pids; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
  for pid in $pids; do
    wait "$pid" 2>/dev/null || true
  done
}

stop_guardian_processes() {
  stop_pid_file guardian-app
  stop_pid_file guardian-worker
  stop_pid_file guardian-voice-worker
  stop_listeners_on_port "$GUARDIAN_PORT"
  stop_listeners_on_port "$GUARDIAN_WS_PORT"
}

verify_guardian_import() {
  if ! env PYTHONPATH="$BACKEND_DIR" "$GUARDIAN_PYTHON" -c "from app import create_app" >/dev/null 2>&1; then
    err "Guardian 代码无法加载（请检查 app.py 语法/导入错误）"
    env PYTHONPATH="$BACKEND_DIR" "$GUARDIAN_PYTHON" -c "from app import create_app" 2>&1 | tail -8 || true
    return 1
  fi
  return 0
}

verify_worker_import() {
  if ! env PYTHONPATH="$BACKEND_DIR" "$GUARDIAN_PYTHON" -c "
from workers.camera_observation_worker import build_worker_from_env
" >/dev/null 2>&1; then
    err "camera_observation_worker 无法加载（常见原因：缺少 pymysql 等依赖）"
    env PYTHONPATH="$BACKEND_DIR" "$GUARDIAN_PYTHON" -c "
from workers.camera_observation_worker import build_worker_from_env
" 2>&1 | tail -12 || true
    return 1
  fi
  return 0
}

verify_voice_worker_import() {
  if ! env PYTHONPATH="$BACKEND_DIR" "$GUARDIAN_PYTHON" -c "
from workers.camera_voice_worker import build_worker_from_env
" >/dev/null 2>&1; then
    err "camera_voice_worker 无法加载"
    env PYTHONPATH="$BACKEND_DIR" "$GUARDIAN_PYTHON" -c "
from workers.camera_voice_worker import build_worker_from_env
" 2>&1 | tail -12 || true
    return 1
  fi
  return 0
}

ensure_prefilter_model() {
  if [ -f "$BACKEND_DIR/assets/vision/yolov8n.onnx" ]; then
    ok "YOLO prefilter model present"
    return 0
  fi
  warn "YOLO prefilter model missing; exporting once (needs ultralytics: pip install ultralytics)"
  if ! env PYTHONPATH="$BACKEND_DIR" "$GUARDIAN_PYTHON" -c "
from services.vision_prefilter_service import ensure_prefilter_model
ensure_prefilter_model()
"; then
    err "无法准备 YOLO 模型。请执行: cd backend && pip install ultralytics && python scripts/export_yolov8n_onnx.py"
    return 1
  fi
  ok "YOLO prefilter model ready"
  return 0
}

begin_worker_log_session() {
  local ts
  ts="$(date '+%Y-%m-%d %H:%M:%S %z')"
  {
    echo "===== Guardian worker session started ${ts} ====="
    echo "python=${GUARDIAN_PYTHON}"
  } > "$LOG_DIR/guardian-worker.log"
}

cleanup() {
  [ "$CLEANED" -eq 1 ] && return 0
  CLEANED=1
  echo ""
  warn "正在停止 Guardian 进程…"
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  for name in guardian-app guardian-worker guardian-voice-worker; do
    stop_pid_file "$name"
  done
  ok "已停止（ai_camera_test 媒体层仍保持运行；如需停止请在其目录运行 supervisor stop-all）"
}

trap cleanup INT TERM

if [ ! -f "$ENV_FILE" ]; then
  err "未找到 $ENV_FILE，请先配置 backend/.env"
  exit 1
fi

load_env_file "$ENV_FILE"

AI_CAMERA_TEST_DIR="${AI_CAMERA_TEST_WORKSPACE:-}"
AI_CAMERA_TEST_AVAILABLE=0
if [ -n "$AI_CAMERA_TEST_DIR" ] && [ -d "$AI_CAMERA_TEST_DIR" ]; then
  AI_CAMERA_TEST_AVAILABLE=1
else
  warn "未配置 AI_CAMERA_TEST_WORKSPACE，跳过 ai_camera_test 媒体层（语音仍可用 Guardian voice worker）"
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
GUARDIAN_PYTHON="$PYTHON_BIN"
if [ -x "$BACKEND_DIR/.venv/bin/python" ]; then
  GUARDIAN_PYTHON="$BACKEND_DIR/.venv/bin/python"
elif [ -x "$BACKEND_DIR/venv/bin/python" ]; then
  GUARDIAN_PYTHON="$BACKEND_DIR/venv/bin/python"
fi
if ! command -v "$GUARDIAN_PYTHON" >/dev/null 2>&1; then
  err "未找到 python3"
  exit 1
fi
if ! "$GUARDIAN_PYTHON" -c "import pymysql" >/dev/null 2>&1; then
  warn "Guardian Python 缺少依赖，正在安装 requirements.txt …"
  "$GUARDIAN_PYTHON" -m pip install -r "$BACKEND_DIR/requirements.txt"
fi
if ! "$GUARDIAN_PYTHON" -c "import pymysql" >/dev/null 2>&1; then
  err "依赖安装后仍无法 import pymysql，请手动执行: $GUARDIAN_PYTHON -m pip install -r $BACKEND_DIR/requirements.txt"
  exit 1
fi

echo "╔══════════════════════════════════════════════════════╗"
echo "║  Mira Guardian 本地联调 — 一键启动                    ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. ai_camera_test 媒体层（可选）─────────────────────────
if [ "$AI_CAMERA_TEST_AVAILABLE" -eq 1 ]; then
log "── 1/4 ai_camera_test 媒体层 ──"

CAMERA_HEALTH="http://127.0.0.1:${CAMERA_PORT}/api/health"
GO2RTC_HEALTH="http://127.0.0.1:${GO2RTC_PORT}/api/streams"
RESTART_CMD="$AI_CAMERA_TEST_DIR/重启服务.command"

if url_ok "$CAMERA_HEALTH" && url_ok "$GO2RTC_HEALTH"; then
  ok "ai_camera_test 已在运行 (${CAMERA_PORT} / go2rtc ${GO2RTC_PORT})"
else
  warn "ai_camera_test 未就绪，正在启动…"
  if [ ! -x "$RESTART_CMD" ]; then
    err "未找到 $RESTART_CMD"
    exit 1
  fi
  (
    cd "$AI_CAMERA_TEST_DIR"
    bash ./重启服务.command
  ) </dev/null || {
    err "ai_camera_test 启动失败，请查看 $AI_CAMERA_TEST_DIR 下日志"
    exit 1
  }
  sleep 2
  if ! url_ok "$CAMERA_HEALTH"; then
    err "ai_camera_test 后端仍未响应: $CAMERA_HEALTH"
    exit 1
  fi
  ok "ai_camera_test 已启动"
fi

CAMERA_PY="$AI_CAMERA_TEST_DIR/venv/bin/python"
if [ -x "$CAMERA_PY" ]; then
  # 禁止 monitor_worker 双写；speaker/task 仍用于播报；voice 唤醒可单独关闭
  AI_CAMERA_TEST_VOICE_ENABLED="${AI_CAMERA_TEST_VOICE_ENABLED:-1}"
  (
    cd "$AI_CAMERA_TEST_DIR"
    "$CAMERA_PY" -m runtime.supervisor stop monitor >/dev/null 2>&1 || true
    for worker in speaker voice task; do
      "$CAMERA_PY" -m runtime.supervisor stop "$worker" >/dev/null 2>&1 || true
    done
    sleep 1
    for worker in speaker task; do
      if ! "$CAMERA_PY" -m runtime.supervisor start "$worker" >/dev/null 2>&1; then
        warn "ai_camera_test worker 启动失败: $worker（请在 $AI_CAMERA_TEST_DIR 查看日志）"
      fi
    done
    if [ "$AI_CAMERA_TEST_VOICE_ENABLED" = "0" ] || [ "$AI_CAMERA_TEST_VOICE_ENABLED" = "false" ]; then
      "$CAMERA_PY" -m runtime.supervisor stop voice >/dev/null 2>&1 || true
      ok "ai_camera_test workers: speaker / task（AI_CAMERA_TEST_VOICE_ENABLED=0，已关闭语音唤醒）"
    elif "$CAMERA_PY" -m runtime.supervisor start voice >/dev/null 2>&1; then
      if "$CAMERA_PY" -m runtime.supervisor status voice 2>/dev/null | grep -q "'running': True"; then
        ok "ai_camera_test workers: speaker / voice / task（voice 已桥接 Guardian）"
      else
        warn "ai_camera_test voice worker 未在监听，语音唤醒不可用（请在其目录运行: venv/bin/python -m runtime.supervisor start voice）"
      fi
    else
      warn "ai_camera_test voice worker 启动失败（请在 $AI_CAMERA_TEST_DIR 查看日志）"
    fi
  )
else
  warn "未找到 ai_camera_test venv，跳过 runtime workers"
fi
else
  warn "跳过 ai_camera_test 媒体层"
fi

# ── 2. Guardian 后端 ─────────────────────────────────────
log ""
log "── 2/4 Guardian 后端 (app.py) ──"

GUARDIAN_HEALTH="http://127.0.0.1:${GUARDIAN_PORT}/api/health"
GUARDIAN_STARTED_BY_US=0

if port_listening "$GUARDIAN_PORT" || port_listening "$GUARDIAN_WS_PORT"; then
  warn "检测到 Guardian 端口 ${GUARDIAN_PORT}/${GUARDIAN_WS_PORT} 已占用，先停止旧进程…"
  stop_guardian_processes
  sleep 1
else
  stop_pid_file guardian-app
  stop_pid_file guardian-worker
fi

cd "$BACKEND_DIR"
set -a
load_env_file "$ENV_FILE"
set +a

if ! verify_guardian_import; then
  exit 1
fi

if ! port_listening "$GUARDIAN_PORT"; then
  nohup env PYTHONPATH="$BACKEND_DIR" "$GUARDIAN_PYTHON" app.py \
    >> "$LOG_DIR/guardian-app.log" 2>&1 &
  APP_PID=$!
  record_pid guardian-app "$APP_PID"
  GUARDIAN_STARTED_BY_US=1

  if ! wait_for_guardian "$APP_PID" 20; then
    err "Guardian 后端启动失败（20s 内未就绪），日志: $LOG_DIR/guardian-app.log"
    show_startup_errors "$LOG_DIR/guardian-app.log"
    cleanup
    exit 1
  fi
fi

ok "Guardian API + WS + 调度  →  http://127.0.0.1:${GUARDIAN_PORT}  (WS :${GUARDIAN_WS_PORT})"
if [ "$GUARDIAN_STARTED_BY_US" -eq 1 ]; then
  ok "日志: $LOG_DIR/guardian-app.log"
else
  ok "复用已有进程（新日志仍追加到 $LOG_DIR/guardian-app.log 若由本脚本启动过）"
fi

# ── 3. Guardian 观察 worker ──────────────────────────────
log ""
log "── 3/4 Guardian 观察 worker ──"

stop_pid_file guardian-worker
for pid in $(pgrep -f "workers\.camera_observation_worker" 2>/dev/null || true); do
  kill "$pid" 2>/dev/null || true
done
sleep 1
if ! ensure_prefilter_model; then
  exit 1
fi
if ! verify_worker_import; then
  exit 1
fi
begin_worker_log_session
nohup env PYTHONPATH="$BACKEND_DIR" "$GUARDIAN_PYTHON" -m workers.camera_observation_worker \
  >> "$LOG_DIR/guardian-worker.log" 2>&1 &
WORKER_PID=$!
record_pid guardian-worker "$WORKER_PID"
sleep 2
if ! kill -0 "$WORKER_PID" 2>/dev/null; then
  err "camera_observation_worker 启动后立即退出，日志: $LOG_DIR/guardian-worker.log"
  show_startup_errors "$LOG_DIR/guardian-worker.log"
  exit 1
fi
ok "camera_observation_worker 已启动（PID ${WORKER_PID}，间隔 ${CAMERA_OBSERVATION_INTERVAL_SECONDS:-60}s）"
ok "日志: $LOG_DIR/guardian-worker.log"

# ── 4. Guardian voice worker ─────────────────────────────
log ""
log "── 4/4 Guardian voice worker ──"

VOICE_WORKER_ENABLED="${VOICE_WORKER_ENABLED:-0}"
if [ "$VOICE_WORKER_ENABLED" = "0" ] || [ "$VOICE_WORKER_ENABLED" = "false" ]; then
  warn "VOICE_WORKER_ENABLED=0，跳过 Guardian mock camera_voice_worker（测试摄像头请用 ai_camera_test voice worker）"
else
  stop_pid_file guardian-voice-worker
  for pid in $(pgrep -f "workers\.camera_voice_worker" 2>/dev/null || true); do
    kill "$pid" 2>/dev/null || true
  done
  sleep 1
  if [ -z "${VOICE_WORKER_FAMILY_ID:-}" ]; then
    warn "未设置 VOICE_WORKER_FAMILY_ID，跳过 camera_voice_worker（可在 backend/.env 配置）"
  elif ! verify_voice_worker_import; then
    exit 1
  else
    nohup env PYTHONPATH="$BACKEND_DIR" "$GUARDIAN_PYTHON" -m workers.camera_voice_worker       >> "$LOG_DIR/guardian-voice-worker.log" 2>&1 &
    VOICE_PID=$!
    record_pid guardian-voice-worker "$VOICE_PID"
    sleep 2
    if ! kill -0 "$VOICE_PID" 2>/dev/null; then
      err "camera_voice_worker 启动后立即退出，日志: $LOG_DIR/guardian-voice-worker.log"
      show_startup_errors "$LOG_DIR/guardian-voice-worker.log"
      exit 1
    fi
    ok "camera_voice_worker 已启动（PID ${VOICE_PID}，mock 模式）"
    ok "日志: $LOG_DIR/guardian-voice-worker.log"
  fi
fi

# ── 汇总 ────────────────────────────────────────────────
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  全部就绪 — 按 Ctrl+C 停止 Guardian 进程              ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Guardian API    http://127.0.0.1:${GUARDIAN_PORT}/api"
echo "║  Guardian WS     ws://127.0.0.1:${GUARDIAN_WS_PORT}/api/tasks/stream"
if [ -n "$LAN_IP" ]; then
echo "║  手机调试 API    http://${LAN_IP}:${GUARDIAN_PORT}/api"
echo "║  手机调试 WS     ws://${LAN_IP}:${GUARDIAN_WS_PORT}/api/tasks/stream"
fi
echo "║  摄像头媒体      http://127.0.0.1:${CAMERA_PORT}/"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
warn "Flutter: cd mobile && flutter run"
echo ""

case "$FOLLOW_LOGS" in
  none)
    warn "日志仅写入 $LOG_DIR/（可用 tail -f $LOG_DIR/guardian-app.log 查看请求）"
    wait
    ;;
  worker)
    warn "实时日志: worker（Ctrl+C 停止全部）"
    tail -f "$LOG_DIR/guardian-worker.log"
    ;;
  all)
    warn "实时日志: app + worker + voice（Ctrl+C 停止全部）"
    tail -f "$LOG_DIR/guardian-app.log" "$LOG_DIR/guardian-worker.log" "$LOG_DIR/guardian-voice-worker.log"
    ;;
  app|*)
    warn "实时日志: API 请求（Ctrl+C 停止全部）"
    warn "Worker 日志: tail -f $LOG_DIR/guardian-worker.log"
    tail -f "$LOG_DIR/guardian-app.log"
    ;;
esac
