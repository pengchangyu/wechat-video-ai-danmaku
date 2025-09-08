#!/usr/bin/env bash
set -euo pipefail
set -x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Prefer system python3 (more stable Tk), fallback to venv python
PYTHON_BIN="python3"
if [[ -x "${ROOT_DIR}/.venv/bin/python3" ]]; then
  # Use venv python only if explicitly requested
  if [[ "${USE_VENV:-0}" == "1" ]]; then
    PYTHON_BIN="${ROOT_DIR}/.venv/bin/python3"
  fi
fi

export PYTHONWARNINGS=ignore
export PYTHON_BIN

exec "$PYTHON_BIN" "${ROOT_DIR}/app/main.py"
