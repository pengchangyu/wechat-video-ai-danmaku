#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
SRC="${ROOT_DIR}/tools/wxclick.swift"
OUT="${ROOT_DIR}/scripts/wxclick"

if ! command -v xcrun >/dev/null 2>&1; then
  echo "xcrun not found. Please install Xcode command line tools: xcode-select --install" >&2
  exit 2
fi

echo "Compiling wxclick..."
xcrun swiftc -O -o "$OUT" "$SRC"
chmod +x "$OUT"
echo "Built: $OUT"

