#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$ROOT_DIR/data"
LOG_DIR="$DATA_DIR/logs"
RUN_DIR="$DATA_DIR/run"
PID_FILE="$RUN_DIR/ai_danmaku.pid"
LOG_FILE="$LOG_DIR/app.log"

mkdir -p "$LOG_DIR" "$RUN_DIR"

if [[ -f "$PID_FILE" ]]; then
  if ps -p "$(cat "$PID_FILE")" >/dev/null 2>&1; then
    echo "Process already running with PID $(cat "$PID_FILE")."
    exit 0
  else
    rm -f "$PID_FILE"
  fi
fi

# Determine runner
if command -v uv >/dev/null 2>&1; then
  RUN_CMD=(uv run python -m ai_danmaku.cli)
elif command -v python3 >/dev/null 2>&1; then
  RUN_CMD=(python3 -m ai_danmaku.cli)
else
  RUN_CMD=(python -m ai_danmaku.cli)
fi

# Build args
ARGS=()
if [[ -n "${LIVE_URL:-}" ]]; then
  ARGS+=(--live-url "$LIVE_URL")
fi

# Default to semi-auto mode unless explicitly disabled
SEMI_ENABLED=0
if [[ -z "${SEMI:-}" || "$SEMI" == "1" || "$SEMI" == "true" || "$SEMI" == "TRUE" ]]; then
  ARGS+=(--semi)
  SEMI_ENABLED=1
fi

if [[ -n "${INTERVAL:-}" ]]; then
  ARGS+=(--interval "$INTERVAL")
fi

echo "Starting AI Danmaku..."
if [[ "$SEMI_ENABLED" == "1" ]]; then
  echo "Running in foreground (semi-auto). Use Ctrl+C to stop."
  "${RUN_CMD[@]}" "${ARGS[@]}"
else
  echo "Log: $LOG_FILE"
  nohup "${RUN_CMD[@]}" "${ARGS[@]}" >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  echo "Started with PID $(cat "$PID_FILE")."
fi
