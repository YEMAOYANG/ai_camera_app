#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${RUNTIME_ROOT}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
NATIVE_RUNTIME_SCRIPT="${SCRIPT_DIR}/native-runtime.sh"
LAUNCHD_HOME="${MIRA_LAUNCHD_HOME:-${HOME}/Library/LaunchAgents}"
LOG_DIR="${MIRA_MANAGED_STACK_LOG_DIR:-/tmp/mira-managed-dev-stack}"
DOMAIN="gui/$(id -u)"
LABEL_PREFIX="chat.mira.dev"
SERVICES=(backend openmaic gateway)

usage() {
  cat <<'EOF'
Usage: managed-dev-stack.sh [install|start|status|stop|restart|uninstall]

  install    Write three secret-free LaunchAgent plists; do not start services.
  start      Install missing plists and load the three services idempotently.
  status     Report launchd state and HTTP health without printing environments.
  stop       Unload all three services; keep plists installed.
  restart    Stop and start the managed stack.
  uninstall  Stop services and remove the three generated plists.
EOF
}

label_for() {
  printf '%s.%s' "${LABEL_PREFIX}" "$1"
}

plist_for() {
  printf '%s/%s.plist' "${LAUNCHD_HOME}" "$(label_for "$1")"
}

xml_escape() {
  local value="$1"
  value="${value//&/&amp;}"
  value="${value//</&lt;}"
  value="${value//>/&gt;}"
  value="${value//\"/&quot;}"
  value="${value//\'/&apos;}"
  printf '%s' "${value}"
}

service_log() {
  printf '%s/%s.log' "${LOG_DIR}" "$1"
}

render_plist() {
  local service="$1"
  local label plist tmp_file launch_path node_bin
  label="$(label_for "${service}")"
  plist="$(plist_for "${service}")"
  node_bin="$(command -v node)"
  launch_path="$(dirname "${node_bin}"):/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
  tmp_file="${plist}.tmp.$$"

  mkdir -p "${LAUNCHD_HOME}" "${LOG_DIR}"
  chmod 700 "${LOG_DIR}"
  if [[ ! -e "$(service_log "${service}")" ]]; then
    : > "$(service_log "${service}")"
  fi
  chmod 600 "$(service_log "${service}")"
  umask 077
  {
    printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>'
    printf '%s\n' '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    printf '%s\n' '<plist version="1.0">'
    printf '%s\n' '<dict>'
    printf '  <key>Label</key><string>%s</string>\n' "$(xml_escape "${label}")"
    printf '%s\n' '  <key>ProgramArguments</key>'
    printf '%s\n' '  <array>'
    printf '%s\n' '    <string>/bin/bash</string>'
    printf '    <string>%s</string>\n' "$(xml_escape "${SCRIPT_DIR}/managed-dev-stack.sh")"
    printf '%s\n' '    <string>run</string>'
    printf '    <string>%s</string>\n' "$(xml_escape "${service}")"
    printf '%s\n' '  </array>'
    printf '  <key>WorkingDirectory</key><string>%s</string>\n' "$(xml_escape "${REPO_ROOT}")"
    printf '%s\n' '  <key>EnvironmentVariables</key>'
    printf '%s\n' '  <dict>'
    printf '    <key>PATH</key><string>%s</string>\n' "$(xml_escape "${launch_path}")"
    printf '%s\n' '  </dict>'
    printf '%s\n' '  <key>RunAtLoad</key><true/>'
    printf '%s\n' '  <key>KeepAlive</key><true/>'
    printf '%s\n' '  <key>ProcessType</key><string>Interactive</string>'
    printf '%s\n' '  <key>ThrottleInterval</key><integer>5</integer>'
    printf '  <key>StandardOutPath</key><string>%s</string>\n' "$(xml_escape "$(service_log "${service}")")"
    printf '  <key>StandardErrorPath</key><string>%s</string>\n' "$(xml_escape "$(service_log "${service}")")"
    printf '%s\n' '</dict>'
    printf '%s\n' '</plist>'
  } > "${tmp_file}"
  chmod 600 "${tmp_file}"
  mv "${tmp_file}" "${plist}"
}

install_plists() {
  local service
  for service in "${SERVICES[@]}"; do
    render_plist "${service}"
  done
  echo "Installed secret-free LaunchAgents in ${LAUNCHD_HOME}; services were not started."
}

is_loaded() {
  launchctl print "${DOMAIN}/$(label_for "$1")" >/dev/null 2>&1
}

launchd_running_pid() {
  local service="$1" output state pid
  output="$(launchctl print "${DOMAIN}/$(label_for "${service}")" 2>/dev/null)" || return 1
  state="$(printf '%s\n' "${output}" | sed -n 's/^[[:space:]]*state = //p' | head -1)"
  pid="$(printf '%s\n' "${output}" | sed -n 's/^[[:space:]]*pid = //p' | head -1)"
  [[ "${state}" == "running" ]] || return 1
  [[ "${pid}" =~ ^[1-9][0-9]*$ ]] || return 1
  printf '%s' "${pid}"
}

listener_pids() {
  local port="$1"
  lsof -nP -t -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | sort -u
}

is_descendant_or_self() {
  local candidate="$1" root_pid="$2" current parent i
  current="${candidate}"
  for ((i = 0; i < 64; i += 1)); do
    [[ "${current}" == "${root_pid}" ]] && return 0
    [[ "${current}" =~ ^[1-9][0-9]*$ ]] || return 1
    parent="$(ps -p "${current}" -o ppid= 2>/dev/null | awk '{$1=$1; print}')"
    [[ "${parent}" =~ ^[1-9][0-9]*$ ]] || return 1
    [[ "${parent}" != "${current}" ]] || return 1
    current="${parent}"
  done
  return 1
}

port_is_owned_by_tree() {
  local port="$1" root_pid="$2" listeners listener
  listeners="$(listener_pids "${port}")"
  [[ -n "${listeners}" ]] || return 1
  for listener in ${listeners}; do
    is_descendant_or_self "${listener}" "${root_pid}" || return 1
  done
}

managed_service_owns_port() {
  local service="$1" port="$2" pid
  pid="$(launchd_running_pid "${service}")" || return 1
  port_is_owned_by_tree "${port}" "${pid}"
}

load_service() {
  local service="$1"
  if is_loaded "${service}"; then
    echo "${service}: already loaded"
    return 0
  fi
  launchctl bootstrap "${DOMAIN}" "$(plist_for "${service}")"
  echo "${service}: loaded"
}

port_for() {
  case "$1" in
    backend) printf '8000' ;;
    openmaic) printf '3100' ;;
    gateway) printf '3101' ;;
    *) return 2 ;;
  esac
}

ensure_unmanaged_port_is_free() {
  local service="$1" port
  port="$(port_for "${service}")"
  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    if managed_service_owns_port "${service}" "${port}"; then
      return 0
    fi
    echo "${service}: port ${port} is occupied by a process not managed by this LaunchAgent; stop the legacy process first." >&2
    return 1
  fi
}

unload_service() {
  local service="$1"
  if ! is_loaded "${service}"; then
    echo "${service}: already stopped"
    return 0
  fi
  launchctl bootout "${DOMAIN}/$(label_for "${service}")"
  echo "${service}: stopped"
}

probe() {
  local url="$1"
  curl --fail --silent --show-error --max-time 3 "${url}" >/dev/null 2>&1
}

wait_for_probe() {
  local service="$1" url="$2" attempts="${3:-60}" i
  local port
  port="$(port_for "${service}")"
  for ((i = 0; i < attempts; i += 1)); do
    if managed_service_owns_port "${service}" "${port}" && probe "${url}"; then
      echo "${service}: healthy at ${url}"
      return 0
    fi
    sleep 1
  done
  echo "${service}: did not become healthy; inspect $(service_log "${service}")" >&2
  return 1
}

start_stack() {
  local openmaic_pid gateway_pid
  install_plists >/dev/null
  ensure_unmanaged_port_is_free backend
  load_service backend
  wait_for_probe backend http://127.0.0.1:8000/api/health
  ensure_unmanaged_port_is_free openmaic
  load_service openmaic
  wait_for_probe openmaic http://127.0.0.1:3100/api/health
  ensure_unmanaged_port_is_free gateway
  load_service gateway
  wait_for_probe gateway http://127.0.0.1:3101/health
  openmaic_pid="$(launchd_running_pid openmaic)" || {
    echo "openmaic: LaunchAgent is not running with a verifiable PID." >&2
    return 1
  }
  gateway_pid="$(launchd_running_pid gateway)" || {
    echo "gateway: LaunchAgent is not running with a verifiable PID." >&2
    return 1
  }
  MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1 \
    MIRA_OPENMAIC_ENABLE_QWEN_TTS=1 \
    MIRA_OPENMAIC_ENABLE_QWEN_ASR=1 \
    MIRA_OPENMAIC_EXPECTED_PID="${openmaic_pid}" \
    MIRA_GATEWAY_EXPECTED_PID="${gateway_pid}" \
    "${NATIVE_RUNTIME_SCRIPT}" contract-status >/dev/null
  echo "runtime contract: OpenMAIC 1.0.0 with exact Kimi/Qwen TTS/Qwen ASR policy"
}

stop_stack() {
  local i
  for ((i = ${#SERVICES[@]} - 1; i >= 0; i -= 1)); do
    unload_service "${SERVICES[$i]}"
  done
}

launchd_state() {
  local service="$1" output state
  if ! output="$(launchctl print "${DOMAIN}/$(label_for "${service}")" 2>/dev/null)"; then
    printf 'not loaded'
    return 0
  fi
  state="$(printf '%s\n' "${output}" | sed -n 's/^[[:space:]]*state = //p' | head -1)"
  printf '%s' "${state:-loaded}"
}

show_status() {
  local service url port openmaic_pid gateway_pid openmaic_listener_ready=0 failed=0
  for service in "${SERVICES[@]}"; do
    case "${service}" in
      backend) url=http://127.0.0.1:8000/api/health ;;
      openmaic) url=http://127.0.0.1:3100/api/health ;;
      gateway) url=http://127.0.0.1:3101/health ;;
    esac
    port="$(port_for "${service}")"
    if managed_service_owns_port "${service}" "${port}" && probe "${url}"; then
      if [[ "${service}" == "openmaic" ]]; then
        openmaic_listener_ready=1
      else
        echo "${service}: $(launchd_state "${service}"), healthy at ${url}"
      fi
    else
      echo "${service}: $(launchd_state "${service}"), unavailable at ${url}"
      failed=1
    fi
  done
  if [[ "${openmaic_listener_ready}" == "1" ]]; then
    openmaic_pid="$(launchd_running_pid openmaic)" || failed=1
    gateway_pid="$(launchd_running_pid gateway)" || failed=1
    if [[ -n "${openmaic_pid}" && -n "${gateway_pid}" ]] && \
      MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1 \
      MIRA_OPENMAIC_ENABLE_QWEN_TTS=1 \
      MIRA_OPENMAIC_ENABLE_QWEN_ASR=1 \
      MIRA_OPENMAIC_EXPECTED_PID="${openmaic_pid}" \
      MIRA_GATEWAY_EXPECTED_PID="${gateway_pid}" \
      "${NATIVE_RUNTIME_SCRIPT}" contract-status >/dev/null; then
      echo "openmaic: running, production identity and runtime contract healthy at http://127.0.0.1:3100/api/health"
    else
      echo "openmaic: listener is not a verified production runtime"
      failed=1
    fi
  fi
  echo "Logs: ${LOG_DIR}"
  return "${failed}"
}

run_service() {
  local service="$1" python_bin
  case "${service}" in
    backend)
      if [[ -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
        python_bin="${BACKEND_DIR}/.venv/bin/python"
      elif [[ -x "${BACKEND_DIR}/venv/bin/python" ]]; then
        python_bin="${BACKEND_DIR}/venv/bin/python"
      else
        python_bin="$(command -v python3)"
      fi
      cd "${BACKEND_DIR}"
      exec env PYTHONPATH="${BACKEND_DIR}" "${python_bin}" app.py
      ;;
    openmaic)
      export MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1
      export MIRA_OPENMAIC_ENABLE_QWEN_TTS=1
      export MIRA_OPENMAIC_ENABLE_QWEN_ASR=1
      exec "${NATIVE_RUNTIME_SCRIPT}" foreground-openmaic-production
      ;;
    gateway)
      exec "${NATIVE_RUNTIME_SCRIPT}" foreground-gateway
      ;;
    *)
      echo "Unknown managed service: ${service}" >&2
      return 2
      ;;
  esac
}

main() {
  case "${1:-status}" in
    install)
      install_plists
      ;;
    start)
      start_stack
      ;;
    status)
      show_status
      ;;
    stop)
      stop_stack
      ;;
    restart)
      stop_stack
      start_stack
      ;;
    uninstall)
      stop_stack
      local service
      for service in "${SERVICES[@]}"; do
        rm -f "$(plist_for "${service}")"
      done
      echo "Removed managed LaunchAgent plists from ${LAUNCHD_HOME}."
      ;;
    run)
      [[ $# -eq 2 ]] || { usage >&2; return 2; }
      run_service "$2"
      ;;
    --help|-h|help)
      usage
      ;;
    *)
      usage >&2
      return 2
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
