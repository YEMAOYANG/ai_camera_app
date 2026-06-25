#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

env_file="${ENV_FILE:-.env.development}"
if [[ ! -f "$env_file" ]]; then
  echo "Missing environment file: ${env_file}"
  exit 1
fi

env_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $0 !~ /^[[:space:]]*#/ && $1 == key {
      sub(/^[^=]*=/, "")
      print
      exit
    }
  ' "$env_file"
}

api_base_url="$(env_value API_BASE_URL)"
task_ws_base_url="$(env_value TASK_WS_BASE_URL)"

if [[ -z "$api_base_url" || -z "$task_ws_base_url" ]]; then
  echo "Missing API_BASE_URL or TASK_WS_BASE_URL in ${env_file}."
  exit 1
fi

echo "Using API_BASE_URL from ${env_file}: ${api_base_url}"
echo "Using TASK_WS_BASE_URL from ${env_file}: ${task_ws_base_url}"

exec flutter run \
  --dart-define-from-file="${env_file}" \
  "$@"
