#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${VOXCPM_BASE_URL:-http://127.0.0.1:8000}"
MODEL="${VOXCPM_MODEL:-openbmb/VoxCPM2}"
OUTPUT="$(mktemp -t mira-voxcpm2-smoke.XXXXXX.wav)"

curl --fail --silent --show-error \
  -X POST "${BASE_URL%/}/v1/audio/speech" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"${MODEL}\",\"input\":\"你好，欢迎来到 Mira 学习空间。\",\"voice\":\"default\",\"response_format\":\"wav\",\"stream\":false}" \
  --output "${OUTPUT}"

if [[ ! -s "${OUTPUT}" ]]; then
  echo "VoxCPM2 returned an empty audio file" >&2
  exit 1
fi

echo "VoxCPM2 smoke audio: ${OUTPUT}"
echo "Listen to it before approving any production voice or pronunciation."
