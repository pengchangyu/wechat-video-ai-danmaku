#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
SRC="${ROOT_DIR}/tools/wxocr.swift"
OUT="${ROOT_DIR}/scripts/wxocr"

if ! command -v xcrun >/dev/null 2>&1; then
  echo "xcrun not found. Please install Xcode command line tools: xcode-select --install" >&2
  exit 2
fi

echo "Compiling wxocr (Vision OCR)..."
SDK="$(xcrun --sdk macosx --show-sdk-path)"
# Use explicit SDK and frameworks for robustness across setups
xcrun --sdk macosx swiftc \
  -sdk "$SDK" -O \
  -framework Vision -framework AppKit -framework CoreGraphics \
  -o "$OUT" "$SRC"
chmod +x "$OUT"
echo "Built: $OUT"

