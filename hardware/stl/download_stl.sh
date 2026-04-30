#!/usr/bin/env bash
# SO-ARM101 STL 다운로드 스크립트 (Linux / macOS / Git Bash)
#
# 사용법: bash download_stl.sh
#
# 주의: LeRobot 저장소 구조 변경 시 SOURCE_REPO/SOURCE_PATH를 수정해야 한다.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SOURCE_REPO="huggingface/lerobot"
# TODO: 실제 STL 경로 확인 후 수정 (예: lerobot/common/robot_devices/.../so_arm101/)
SOURCE_PATH="docs/source/_static/img/so100"

echo "[*] Cloning sparse checkout from $SOURCE_REPO ..."
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

git clone --depth 1 --filter=blob:none --sparse \
  "https://github.com/${SOURCE_REPO}.git" "$TMP_DIR"

(
  cd "$TMP_DIR"
  git sparse-checkout set "$SOURCE_PATH" || {
    echo "[!] sparse-checkout 실패. 저장소 구조를 확인하라."
    exit 1
  }
)

echo "[*] Copying STL files ..."
find "$TMP_DIR/$SOURCE_PATH" -type f -name "*.stl" -exec cp {} "$SCRIPT_DIR/" \; || {
  echo "[!] STL 파일을 찾지 못함. README.md의 수동 다운로드 절차를 따르라."
  exit 1
}

echo "[✓] Done. 다음 파일이 다운로드됨:"
ls -la "$SCRIPT_DIR/"*.stl 2>/dev/null || echo "  (없음 — SOURCE_PATH 재확인 필요)"
