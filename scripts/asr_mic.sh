#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${ROOT_DIR}/logs/audio"
mkdir -p "$LOG_DIR"

DEVICE_SPEC=${DEVICE_SPEC:-":0"}  # default microphone
SEG_SECS=${SEG_SECS:-6}
SR=${SR:-16000}

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found. Install via brew install ffmpeg" >&2
  exit 2
fi

echo "Recording from avfoundation device ${DEVICE_SPEC} in ${SEG_SECS}s segments... (Ctrl+C to stop)"

# High-pass + normalizer to help with external speaker capture
ffmpeg -hide_banner -f avfoundation -i "$DEVICE_SPEC" \
  -ac 1 -ar "$SR" \
  -af "highpass=f=150, dynaudnorm=f=150:g=15" \
  -f segment -segment_time "$SEG_SECS" -reset_timestamps 1 \
  -c:a pcm_s16le "$LOG_DIR/seg-%03d.wav"

