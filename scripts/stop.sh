#!/usr/bin/env bash
set -euo pipefail

# Stops the running Tk app by name (best-effort)
APP_NAME="wx_channels_helper"

# Kill by Python script path
pkill -f "app/main.py" 2>/dev/null || true

# Kill any named process tag if used later
pkill -f "$APP_NAME" 2>/dev/null || true

echo "Stopped (if running)."

