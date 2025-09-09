#!/usr/bin/env bash
set -euo pipefail

# List avfoundation devices (macOS)
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found. Please install via brew: brew install ffmpeg" >&2
  exit 2
fi

ffmpeg -f avfoundation -list_devices true -i "" 2>&1 | sed -n 's/^\[AVFoundation.*\] //p'

