#!/usr/bin/env bash
set -euo pipefail

MSG="${1:-}"
if [[ -z "$MSG" ]]; then
  echo "Usage: scripts/send_once.sh 'your message'"
  exit 1
fi

echo -n "$MSG" | pbcopy

# Activate WeChat and paste+Return via AppleScript
osascript -e 'tell application "WeChat" to activate'
osascript -e 'tell application "System Events" to keystroke "v" using {command down}'
osascript -e 'tell application "System Events" to key code 36'

echo "Sent."

