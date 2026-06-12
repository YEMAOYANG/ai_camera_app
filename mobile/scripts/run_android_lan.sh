#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

env_file="${ENV_FILE:-.env.development}"
if [[ ! -f "$env_file" ]]; then
  echo "Missing environment file: ${env_file}"
  exit 1
fi

host_ip="${MIRA_HOST_IP:-}"
if [[ -z "$host_ip" ]]; then
  host_ip="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [[ -z "$host_ip" ]]; then
  host_ip="$(ipconfig getifaddr en1 2>/dev/null || true)"
fi
if [[ -z "$host_ip" ]]; then
  host_ip="$(
    ifconfig 2>/dev/null \
      | awk '/inet / && $2 != "127.0.0.1" { print $2; exit }'
  )"
fi
if [[ -z "$host_ip" ]]; then
  echo "Cannot detect a LAN IP. Set MIRA_HOST_IP manually, for example:"
  echo "MIRA_HOST_IP=192.168.1.23 mobile/scripts/run_android_lan.sh"
  exit 1
fi

api_base_url="${API_BASE_URL:-http://${host_ip}:8000/api}"
task_ws_base_url="${TASK_WS_BASE_URL:-ws://${host_ip}:8001/api}"

echo "Using API_BASE_URL=${api_base_url}"
echo "Using TASK_WS_BASE_URL=${task_ws_base_url}"

exec flutter run \
  --dart-define-from-file="${env_file}" \
  --dart-define="API_BASE_URL=${api_base_url}" \
  --dart-define="TASK_WS_BASE_URL=${task_ws_base_url}" \
  "$@"
