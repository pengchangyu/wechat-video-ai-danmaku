#!/usr/bin/env bash
set -euo pipefail

# Stops the running Tk app by name (best-effort)
APP_NAME="wx_channels_helper"

# Kill by Python script path
pkill -f "app/main.py" 2>/dev/null || true

# Kill any named process tag if used later
pkill -f "$APP_NAME" 2>/dev/null || true

# Stop cloud OCR remnants (screencapture) if any
pkill -f "screencapture -x -R" 2>/dev/null || true

# Stop ASR processes: recorder (ffmpeg via asr_mic.sh) and transcriber
pkill -f "scripts/asr_mic.sh" 2>/dev/null || true
pkill -f "ffmpeg -f avfoundation" 2>/dev/null || true
pkill -f "asr/transcribe.py" 2>/dev/null || true

# Aggressive kill: ffmpeg writing to logs/audio/seg-*
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
AUDIO_DIR="$ROOT_DIR/logs/audio"
if [[ -d "$AUDIO_DIR" ]]; then
  # TERM then KILL any ffmpeg whose cmdline references our segment output dir
  pkill -f "ffmpeg .*${AUDIO_DIR}/seg-" 2>/dev/null || true
  sleep 0.3
  pkill -9 -f "ffmpeg .*${AUDIO_DIR}/seg-" 2>/dev/null || true
fi

# Kill by pidfiles if present
PIDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)/logs/pids"
if [[ -d "$PIDS_DIR" ]]; then
  for pf in "$PIDS_DIR"/*.pid; do
    [[ -f "$pf" ]] || continue
    pid=$(cat "$pf" 2>/dev/null || true)
    if [[ -n "${pid:-}" ]]; then
      kill -TERM "$pid" 2>/dev/null || true
      sleep 0.5
      kill -KILL "$pid" 2>/dev/null || true
    fi
    rm -f "$pf" 2>/dev/null || true
  done
fi

echo "Stopped (if running)."
