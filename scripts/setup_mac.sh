#!/usr/bin/env bash
set -euo pipefail

echo "== WeChat Live Assistant: macOS setup =="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR" "$LOG_DIR/audio" "$LOG_DIR/frames" "$ROOT_DIR/tools" "$ROOT_DIR/scripts"

have() { command -v "$1" >/dev/null 2>&1; }

mac_ver_ok() {
  OSV=$(sw_vers -productVersion | awk -F. '{print $1"."$2}')
  # Require 12.0+
  awk -v v="$OSV" 'BEGIN{split(v,a,"."); if (a[1]>12 || (a[1]==12)) exit 0; exit 1}' || return 1
}

echo "- Checking macOS version >= 12..."
if ! mac_ver_ok; then
  echo "ERROR: macOS 12+ required. Current: $(sw_vers -productVersion)" >&2
  exit 2
fi

echo "- Checking Homebrew..."
if ! have brew; then
  echo "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv || true)"
fi

echo "- Installing core packages (ffmpeg jq)..."
brew install ffmpeg jq >/dev/null || true

echo "- Checking Xcode Command Line Tools..."
if ! have xcode-select || ! xcode-select -p >/dev/null 2>&1; then
  echo "Installing Xcode Command Line Tools..."
  xcode-select --install || true
  echo "Please complete Xcode CLT installation if prompted, then re-run setup if build fails."
fi

PY=$(command -v python3 || true)
if [[ -z "${PY}" ]]; then
  echo "- Installing Python3 via Homebrew..."
  brew install python >/dev/null
  PY=$(command -v python3)
fi

echo "- Installing Python deps (faster-whisper)..."
if have uv; then
  uv pip install "numpy<2" "faster-whisper[all]"
else
  "$PY" -m pip install --upgrade pip >/dev/null || true
  "$PY" -m pip install "numpy<2" "faster-whisper[all]"
fi

echo "- Verifying Python deps..."
if ! "$PY" - <<'PY'
import sys
try:
    import faster_whisper  # noqa
    import ctranslate2  # noqa
except Exception as e:
    print(f"VERIFY_FAILED: {e}")
    sys.exit(1)
print("OK")
PY
then
  echo "ERROR: Python deps verification failed. See above." >&2
  exit 3
fi

echo "- Building Swift clicker (wxclick)..."
bash "$ROOT_DIR/scripts/build_clicker.sh" || true

CFG="$ROOT_DIR/config.json"
if [[ ! -f "$CFG" ]]; then
  echo "- Creating local config.json (no secrets will be committed)"
  cat >"$CFG" <<'JSON'
{
  "input_position": [0, 0],
  "send_button_position": [0, 0],
  "comments_region": [0, 0, 0, 0],
  "openai_api_key": "",
  "openai_model": "gpt-4o",
  "deepseek_api_key": "",
  "deepseek_model": "deepseek-chat",
  "agent_interval": 10,
  "agent_auto_send": false,
  "agent_ignore_history": true,
  "agent_min_interval": 10,
  "agent_max_per_min": 4,
  "agent_random_interval": false,
  "agent_random_min": 8,
  "agent_random_max": 18,
  "agent_persona": "你是直播间的友好观众，用中文自然口吻简短回应，避免敏感内容。限制：不超过40字；可适度使用表情；没内容就返回空字符串。"
}
JSON
fi

echo "- Prompt for API keys (optional; can be set later in UI)"
read -r -p "OpenAI API Key (for OCR) [leave blank to skip]: " OAI || true
read -r -p "DeepSeek API Key (for agent) [leave blank to skip]: " DSK || true

if [[ -n "${OAI:-}" || -n "${DSK:-}" ]]; then
  "$PY" - <<PY
import json,sys
cfg=json.load(open("$CFG"))
oai="""${OAI:-}""".strip()
dsk="""${DSK:-}""".strip()
if oai: cfg["openai_api_key"]=oai
if dsk: cfg["deepseek_api_key"]=dsk
json.dump(cfg,open("$CFG","w"),ensure_ascii=False,indent=2)
print("- Keys saved to config.json")
PY
fi

echo "- Opening Privacy panes (grant permissions to your Terminal/Python):"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" || true
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture" || true
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone" || true
echo "Please ensure your Terminal (or IDE) is enabled for Accessibility, Screen Recording, and Microphone."

echo "== Setup completed. Next steps =="
echo "1) Launch app: scripts/start.sh"
echo "2) Calibrate: 输入框/发送按钮/评论区矩形"
echo "3) Fill keys in UI if you skipped here; edit 人设与频控"
echo "4) Click 一键开始"
