#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

env_file="${ENV_FILE:-.env.development}"
if [[ ! -f "$env_file" ]]; then
  echo "Missing environment file: ${env_file}"
  exit 1
fi

device_id="${ANDROID_SERIAL:-${DEVICE_ID:-}}"
args=("$@")

for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[$i]}" in
    -d|--device-id)
      if ((i + 1 < ${#args[@]})); then
        device_id="${args[$((i + 1))]}"
      fi
      ;;
  esac
done

if [[ -z "$device_id" ]]; then
  android_devices=()
  while IFS= read -r detected_device; do
    android_devices+=("$detected_device")
  done < <(
    adb devices \
      | awk 'NR > 1 && $2 == "device" { print $1 }'
  )
  if [[ ${#android_devices[@]} -eq 1 ]]; then
    device_id="${android_devices[0]}"
    args+=("-d" "$device_id")
  else
    echo "Expected one Android device, found ${#android_devices[@]}."
    echo "Run 'adb devices', then pass one explicitly, for example:"
    echo "scripts/run_android_usb.sh -d <device-id>"
    exit 1
  fi
fi

adb -s "$device_id" get-state >/dev/null
adb -s "$device_id" reverse tcp:8000 tcp:8000 >/dev/null
adb -s "$device_id" reverse tcp:8001 tcp:8001 >/dev/null

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

echo "Android USB reverse is ready for device ${device_id}."
echo "Using API_BASE_URL from ${env_file}: ${api_base_url}"
echo "Using TASK_WS_BASE_URL from ${env_file}: ${task_ws_base_url}"

exec flutter run \
  --dart-define-from-file="${env_file}" \
  "${args[@]}"
