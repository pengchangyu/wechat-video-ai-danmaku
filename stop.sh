#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$ROOT_DIR/data/run/ai_danmaku.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "No PID file. Service not running?"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if ! ps -p "$PID" >/dev/null 2>&1; then
  echo "Process $PID not found. Cleaning up PID file."
  rm -f "$PID_FILE"
  exit 0
fi

echo "Stopping process $PID..."
kill -TERM "$PID" || true

# Wait up to ~10s
for i in {1..20}; do
  if ! ps -p "$PID" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ps -p "$PID" >/dev/null 2>&1; then
  echo "Force killing $PID..."
  kill -KILL "$PID" || true
fi

rm -f "$PID_FILE"
echo "Stopped."

