#!/usr/bin/env bash
set -euo pipefail

# Durable local test stack for macOS development.
#
# Unlike managed-dev-stack.sh, this script does not install or rely on
# LaunchAgents. Backend and Student Web are detached with nohup; the student
# OpenMAIC runtime is always the reviewed production build, while its gateway
# keeps using native-runtime.sh so provider and credential handling remain in
# one place.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${RUNTIME_ROOT}/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
STUDENT_WEB_DIR="${REPO_ROOT}/student-web"
OPENMAIC_DIR="${RUNTIME_ROOT}/.runtime/OpenMAIC"
GATEWAY_DIR="${RUNTIME_ROOT}/gateway"
NATIVE_RUNTIME_SCRIPT="${SCRIPT_DIR}/native-runtime.sh"
LEGACY_STACK_SCRIPT="${SCRIPT_DIR}/managed-dev-stack.sh"

STATE_DIR="${MIRA_LOCAL_TEST_STACK_STATE_DIR:-/tmp/mira-local-test-stack}"
NATIVE_STATE_DIR="${STATE_DIR}/native-runtime"
BACKEND_LOG="${STATE_DIR}/backend.log"
STUDENT_WEB_LOG="${STATE_DIR}/student-web.log"
BACKEND_PID_FILE="${STATE_DIR}/backend.pid"
CURRICULUM_WORKER_PID_FILE="${STATE_DIR}/curriculum-worker.pid"
CURRICULUM_WORKER_LOG="${STATE_DIR}/curriculum-worker.log"
CURRICULUM_WORKER_COMMAND_TOKEN="workers.learning_curriculum_preparation_worker"
REPAIR_MODE="${MIRA_LOCAL_TEST_REPAIR_MODE:-0}"
STUDENT_WEB_PID_FILE="${STATE_DIR}/student-web.pid"
STUDENT_WEB_LAUNCH_PID_FILE="${STATE_DIR}/student-web.launch.pid"
STUDENT_WEB_BUILD_RECORD="${STATE_DIR}/student-web-build.identity"
OPENMAIC_NATIVE_PID_FILE="${NATIVE_STATE_DIR}/openmaic.pid"
GATEWAY_NATIVE_PID_FILE="${NATIVE_STATE_DIR}/gateway.pid"
OPENMAIC_IDENTITY_FILE="${STATE_DIR}/openmaic.identity"
GATEWAY_IDENTITY_FILE="${STATE_DIR}/gateway.identity"

BACKEND_PORT="${MIRA_LOCAL_TEST_BACKEND_PORT:-8000}"
STUDENT_WEB_PORT="${MIRA_LOCAL_TEST_STUDENT_WEB_PORT:-3000}"
OPENMAIC_PORT="${MIRA_LOCAL_TEST_OPENMAIC_PORT:-3100}"
GATEWAY_PORT="${MIRA_LOCAL_TEST_GATEWAY_PORT:-3101}"
HEALTH_ATTEMPTS="${MIRA_LOCAL_TEST_HEALTH_ATTEMPTS:-60}"

BACKEND_HEALTH_URL="http://127.0.0.1:${BACKEND_PORT}/api/health"
STUDENT_WEB_HEALTH_URL="http://127.0.0.1:${STUDENT_WEB_PORT}/"
OPENMAIC_HEALTH_URL="http://127.0.0.1:${OPENMAIC_PORT}/api/health"
GATEWAY_HEALTH_URL="http://127.0.0.1:${GATEWAY_PORT}/health"
OPENMAIC_PRODUCTION_COMMAND_TOKEN="next-server (v16.1.2)"
OPENMAIC_LEGACY_DEV_COMMAND_TOKEN="next/dist/bin/next dev"
STUDENT_WEB_LEGACY_DEV_COMMAND_TOKEN="next/dist/bin/next dev"

RECORD_SERVICE=""
RECORD_PID=""
RECORD_START_HASH=""
STUDENT_RECORD_MODE=""
STUDENT_RECORD_PID=""
STUDENT_RECORD_START_HASH=""
STUDENT_RECORD_NEXT_VERSION=""
STUDENT_RECORD_BUILD_ID_SHA256=""
STUDENT_BUILD_NEXT_VERSION=""
STUDENT_BUILD_SOURCE_FINGERPRINT=""
STUDENT_BUILD_ID_SHA256=""
LEGACY_STUDENT_RECORD_PID=""
LEGACY_STUDENT_RECORD_START_HASH=""

usage() {
  cat <<'EOF'
Usage: local-test-stack.sh [start|stop|restart|status|start-curriculum-worker|stop-curriculum-worker|build-student-web-production]

  start    Start backend:8000, student-web:3000, OpenMAIC:3100, gateway:3101 and curriculum worker.
  stop     Stop only processes whose strict PID identity belongs to this script.
  restart  Safely stop, then start, the local test stack.
  status   Report ownership and HTTP readiness without printing environments.
  start-curriculum-worker / stop-curriculum-worker
            Manage generation independently of the API and student classroom.
  build-student-web-production
            Build Student Web only when its source/config fingerprint is stale.

State and logs default to /tmp/mira-local-test-stack.
This script never kills an unknown process merely because it owns a port.
MIRA_LOCAL_TEST_REPAIR_MODE=1 starts a passive API without background workers.
Generation uses backend/.env gates and the existing single-call concurrency.
Student Web is served with Next.js production `next start`; `next dev` is
recognized only for safe migration of an older identity created by this script.
EOF
}

validate_positive_integer() {
  local label="$1"
  local value="$2"
  if [[ ! "${value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "${label} must be a positive integer." >&2
    return 1
  fi
}

validate_configuration() {
  [[ "${REPAIR_MODE}" == "0" || "${REPAIR_MODE}" == "1" ]] || {
    echo "MIRA_LOCAL_TEST_REPAIR_MODE must be 0 or 1." >&2
    return 1
  }
  validate_positive_integer MIRA_LOCAL_TEST_BACKEND_PORT "${BACKEND_PORT}"
  validate_positive_integer MIRA_LOCAL_TEST_STUDENT_WEB_PORT "${STUDENT_WEB_PORT}"
  validate_positive_integer MIRA_LOCAL_TEST_OPENMAIC_PORT "${OPENMAIC_PORT}"
  validate_positive_integer MIRA_LOCAL_TEST_GATEWAY_PORT "${GATEWAY_PORT}"
  validate_positive_integer MIRA_LOCAL_TEST_HEALTH_ATTEMPTS "${HEALTH_ATTEMPTS}"

  local ports
  ports="${BACKEND_PORT} ${STUDENT_WEB_PORT} ${OPENMAIC_PORT} ${GATEWAY_PORT}"
  if [[ "$(printf '%s\n' ${ports} | sort -u | wc -l | tr -d ' ')" != "4" ]]; then
    echo "The four local test services must use distinct ports." >&2
    return 1
  fi
}

prepare_state_dir() {
  umask 077
  mkdir -p "${STATE_DIR}" "${NATIVE_STATE_DIR}"
  chmod 700 "${STATE_DIR}" "${NATIVE_STATE_DIR}"
  touch "${BACKEND_LOG}" "${STUDENT_WEB_LOG}"
  chmod 600 "${BACKEND_LOG}" "${STUDENT_WEB_LOG}"
}

hash_text() {
  shasum -a 256 | awk '{print $1}'
}

process_start_hash() {
  local pid="$1"
  local started
  # `ps lstart` is locale-sensitive on macOS. Pin it so a process started from
  # Terminal and later checked from Codex/another shell keeps the same identity.
  started="$(LC_ALL=C ps -p "${pid}" -o lstart= 2>/dev/null | awk '{$1=$1; print}')"
  [[ -n "${started}" ]] || return 1
  printf '%s' "${started}" | hash_text
}

process_cwd() {
  local pid="$1"
  lsof -a -p "${pid}" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1
}

process_command_contains() {
  local pid="$1"
  local expected_token="$2"
  local command_line
  command_line="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
  [[ -n "${command_line}" && "${command_line}" == *"${expected_token}"* ]]
}

process_is_alive() {
  local pid="$1"
  local state
  kill -0 "${pid}" 2>/dev/null || return 1
  state="$(ps -p "${pid}" -o stat= 2>/dev/null | awk '{print $1}')"
  [[ -n "${state}" && "${state}" != Z* ]]
}

write_identity_record() {
  local file="$1"
  local service="$2"
  local pid="$3"
  local start_hash tmp_file
  start_hash="$(process_start_hash "${pid}")" || return 1
  tmp_file="${file}.tmp.$$"
  {
    printf 'version=1\n'
    printf 'service=%s\n' "${service}"
    printf 'pid=%s\n' "${pid}"
    printf 'start_hash=%s\n' "${start_hash}"
  } > "${tmp_file}"
  chmod 600 "${tmp_file}"
  mv "${tmp_file}" "${file}"
}

read_identity_record() {
  local file="$1"
  local expected_service="$2"
  local line key value version
  RECORD_SERVICE=""
  RECORD_PID=""
  RECORD_START_HASH=""
  version=""
  [[ -f "${file}" ]] || return 1
  while IFS= read -r line || [[ -n "${line}" ]]; do
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      version) version="${value}" ;;
      service) RECORD_SERVICE="${value}" ;;
      pid) RECORD_PID="${value}" ;;
      start_hash) RECORD_START_HASH="${value}" ;;
      *) return 1 ;;
    esac
  done < "${file}"
  [[ "${version}" == "1" ]] || return 1
  [[ "${RECORD_SERVICE}" == "${expected_service}" ]] || return 1
  [[ "${RECORD_PID}" =~ ^[1-9][0-9]*$ ]] || return 1
  [[ "${RECORD_START_HASH}" =~ ^[a-f0-9]{64}$ ]] || return 1
}

identity_matches_process() {
  local file="$1"
  local service="$2"
  local expected_cwd="$3"
  local command_token="$4"
  local current_hash current_cwd
  read_identity_record "${file}" "${service}" || return 1
  process_is_alive "${RECORD_PID}" || return 1
  current_hash="$(process_start_hash "${RECORD_PID}")" || return 1
  [[ "${current_hash}" == "${RECORD_START_HASH}" ]] || return 1
  current_cwd="$(process_cwd "${RECORD_PID}")"
  [[ "${current_cwd}" == "${expected_cwd}" ]] || return 1
  process_command_contains "${RECORD_PID}" "${command_token}"
}

listener_pids() {
  local port="$1"
  lsof -nP -t -iTCP:"${port}" -sTCP:LISTEN 2>/dev/null | sort -u
}

port_is_listening() {
  [[ -n "$(listener_pids "$1")" ]]
}

is_descendant_or_self() {
  local candidate="$1"
  local root_pid="$2"
  local current parent i
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
  local port="$1"
  local root_pid="$2"
  local listeners listener
  listeners="$(listener_pids "${port}")"
  [[ -n "${listeners}" ]] || return 1
  for listener in ${listeners}; do
    is_descendant_or_self "${listener}" "${root_pid}" || return 1
  done
}

probe() {
  curl --fail --silent --show-error --max-time 3 "$1" >/dev/null 2>&1
}

wait_for_probe() {
  local label="$1"
  local url="$2"
  local pid="$3"
  local log_file="$4"
  local i
  for ((i = 0; i < HEALTH_ATTEMPTS; i += 1)); do
    process_is_alive "${pid}" || {
      echo "${label} exited before it became ready; inspect ${log_file}." >&2
      return 1
    }
    if probe "${url}"; then
      return 0
    fi
    sleep 1
  done
  echo "${label} did not become ready at ${url}; inspect ${log_file}." >&2
  return 1
}

assert_unknown_port_is_free() {
  local label="$1"
  local port="$2"
  if port_is_listening "${port}"; then
    echo "${label}: port ${port} is owned by an unmanaged process; it was not stopped." >&2
    return 1
  fi
}

resolve_python_bin() {
  if [[ -n "${MIRA_LOCAL_TEST_PYTHON_BIN:-}" ]]; then
    [[ -x "${MIRA_LOCAL_TEST_PYTHON_BIN}" ]] || {
      echo "MIRA_LOCAL_TEST_PYTHON_BIN is not executable." >&2
      return 1
    }
    printf '%s' "${MIRA_LOCAL_TEST_PYTHON_BIN}"
  elif [[ -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
    printf '%s' "${BACKEND_DIR}/.venv/bin/python"
  elif [[ -x "${BACKEND_DIR}/venv/bin/python" ]]; then
    printf '%s' "${BACKEND_DIR}/venv/bin/python"
  else
    command -v python3
  fi
}

resolve_node_bin() {
  command -v node
}

student_node_options() {
  local node_bin="$1"
  local node_major
  node_major="$(${node_bin} -p 'Number(process.versions.node.split(".")[0])')" || return 1
  [[ "${node_major}" =~ ^[0-9]+$ ]] || return 1
  if ((node_major >= 25)); then
    printf '%s' '--no-experimental-webstorage'
  fi
}

student_web_next_version() {
  local node_bin
  node_bin="$(resolve_node_bin)" || return 1
  (
    cd "${STUDENT_WEB_DIR}" || exit 1
    "${node_bin}" -p 'require("next/package.json").version' || exit 1
  )
}

student_web_source_fingerprint() {
  local relative_path file_hash
  (
    cd "${STUDENT_WEB_DIR}" || exit 1
    # This fixed local-only mode is part of the production artifact contract.
    # Changing it must invalidate the build even if application files do not.
    printf 'build_env=MIRA_LOCAL_LAN_PRODUCTION_MODE=1\n' || exit 1
    for relative_path in \
      package.json package-lock.json pnpm-lock.yaml yarn.lock bun.lock bun.lockb \
      next.config.js next.config.mjs next.config.ts \
      tsconfig.json jsconfig.json \
      postcss.config.js postcss.config.mjs postcss.config.cjs postcss.config.ts \
      tailwind.config.js tailwind.config.mjs tailwind.config.cjs tailwind.config.ts \
      instrumentation.js instrumentation.ts middleware.js middleware.ts \
      .env .env.local .env.production .env.production.local; do
      if [[ -f "${relative_path}" ]]; then
        file_hash="$(shasum -a 256 "${relative_path}" | awk '{print $1}')" || exit 1
        printf 'file=%s\nsha256=%s\n' "${relative_path}" "${file_hash}" || exit 1
      fi
    done
    for relative_path in src app pages public; do
      [[ -d "${relative_path}" ]] || continue
      find "${relative_path}" -type f -print | LC_ALL=C sort | while IFS= read -r source_file; do
        file_hash="$(shasum -a 256 "${source_file}" | awk '{print $1}')" || exit 1
        printf 'file=%s\nsha256=%s\n' "${source_file}" "${file_hash}" || exit 1
      done || exit 1
    done
  ) | hash_text
}

student_web_build_id_sha256() {
  local build_id_file="${STUDENT_WEB_DIR}/.next/BUILD_ID"
  local build_id
  [[ -f "${build_id_file}" ]] || return 1
  build_id="$(tr -d '\r\n' < "${build_id_file}")"
  [[ -n "${build_id}" && "${build_id}" =~ ^[A-Za-z0-9_-]+$ ]] || return 1
  shasum -a 256 "${build_id_file}" | awk '{print $1}'
}

write_student_web_build_record() {
  local next_version="$1"
  local source_fingerprint="$2"
  local build_id_sha256="$3"
  local tmp_file="${STUDENT_WEB_BUILD_RECORD}.tmp.$$"
  [[ "${next_version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?$ ]] || return 1
  [[ "${source_fingerprint}" =~ ^[a-f0-9]{64}$ ]] || return 1
  [[ "${build_id_sha256}" =~ ^[a-f0-9]{64}$ ]] || return 1
  {
    printf 'version=1\n'
    printf 'next_version=%s\n' "${next_version}"
    printf 'source_fingerprint=%s\n' "${source_fingerprint}"
    printf 'build_id_sha256=%s\n' "${build_id_sha256}"
  } > "${tmp_file}" || return 1
  chmod 600 "${tmp_file}" || {
    rm -f "${tmp_file}" || true
    return 1
  }
  mv "${tmp_file}" "${STUDENT_WEB_BUILD_RECORD}" || {
    rm -f "${tmp_file}" || true
    return 1
  }
}

read_student_web_build_record() {
  local line key value version
  local seen_version=0
  local seen_next_version=0
  local seen_source_fingerprint=0
  local seen_build_id_sha256=0
  STUDENT_BUILD_NEXT_VERSION=""
  STUDENT_BUILD_SOURCE_FINGERPRINT=""
  STUDENT_BUILD_ID_SHA256=""
  version=""
  [[ -f "${STUDENT_WEB_BUILD_RECORD}" ]] || return 1
  while IFS= read -r line || [[ -n "${line}" ]]; do
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      version)
        [[ "${seen_version}" == "0" ]] || return 1
        seen_version=1
        version="${value}"
        ;;
      next_version)
        [[ "${seen_next_version}" == "0" ]] || return 1
        seen_next_version=1
        STUDENT_BUILD_NEXT_VERSION="${value}"
        ;;
      source_fingerprint)
        [[ "${seen_source_fingerprint}" == "0" ]] || return 1
        seen_source_fingerprint=1
        STUDENT_BUILD_SOURCE_FINGERPRINT="${value}"
        ;;
      build_id_sha256)
        [[ "${seen_build_id_sha256}" == "0" ]] || return 1
        seen_build_id_sha256=1
        STUDENT_BUILD_ID_SHA256="${value}"
        ;;
      *) return 1 ;;
    esac
  done < "${STUDENT_WEB_BUILD_RECORD}"
  [[ "${version}" == "1" ]] || return 1
  [[ "${seen_next_version}" == "1" && "${STUDENT_BUILD_NEXT_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?$ ]] || return 1
  [[ "${seen_source_fingerprint}" == "1" && "${STUDENT_BUILD_SOURCE_FINGERPRINT}" =~ ^[a-f0-9]{64}$ ]] || return 1
  [[ "${seen_build_id_sha256}" == "1" && "${STUDENT_BUILD_ID_SHA256}" =~ ^[a-f0-9]{64}$ ]] || return 1
}

student_web_production_build_is_current() {
  local current_next_version current_source_fingerprint current_build_id_sha256
  read_student_web_build_record || return 1
  current_next_version="$(student_web_next_version)" || return 1
  current_source_fingerprint="$(student_web_source_fingerprint)" || return 1
  current_build_id_sha256="$(student_web_build_id_sha256)" || return 1
  [[ "${STUDENT_BUILD_NEXT_VERSION}" == "${current_next_version}" ]] || return 1
  [[ "${STUDENT_BUILD_SOURCE_FINGERPRINT}" == "${current_source_fingerprint}" ]] || return 1
  [[ "${STUDENT_BUILD_ID_SHA256}" == "${current_build_id_sha256}" ]] || return 1
}

build_student_web_production() {
  local node_bin node_options next_version source_fingerprint
  local post_build_source_fingerprint build_id_sha256
  [[ -x "${STUDENT_WEB_DIR}/node_modules/.bin/next" ]] || {
    echo "Student Web dependencies are missing in ${STUDENT_WEB_DIR}." >&2
    return 1
  }
  node_bin="$(resolve_node_bin)" || {
    echo "Student Web: Node.js is unavailable." >&2
    return 1
  }
  next_version="$(student_web_next_version)" || {
    echo "Student Web: installed Next.js version is unreadable." >&2
    return 1
  }
  source_fingerprint="$(student_web_source_fingerprint)" || {
    echo "Student Web: source/config fingerprint could not be calculated." >&2
    return 1
  }
  node_options="$(student_node_options "${node_bin}")" || {
    echo "Student Web: Node.js version could not be validated." >&2
    return 1
  }
  echo "Student Web: production build is missing or stale; building Next.js ${next_version}."
  (
    cd "${STUDENT_WEB_DIR}" || exit 1
    env -i \
      PATH="${PATH}" \
      HOME="${HOME}" \
      TMPDIR="${TMPDIR:-/tmp}" \
      LANG="${LANG:-en_US.UTF-8}" \
      NODE_OPTIONS="${node_options}" \
      NODE_ENV=production \
      NEXT_TELEMETRY_DISABLED=1 \
      MIRA_LOCAL_LAN_PRODUCTION_MODE=1 \
      "${node_bin}" node_modules/next/dist/bin/next build --webpack
  ) || {
    echo "Student Web: production build failed; no build identity was published." >&2
    return 1
  }
  post_build_source_fingerprint="$(student_web_source_fingerprint)" || return 1
  [[ "${post_build_source_fingerprint}" == "${source_fingerprint}" ]] || {
    echo "Student Web: source/config changed during the build; refusing to publish it." >&2
    return 1
  }
  build_id_sha256="$(student_web_build_id_sha256)" || {
    echo "Student Web: production build did not create a valid .next/BUILD_ID." >&2
    return 1
  }
  mkdir -p "$(dirname "${STUDENT_WEB_BUILD_RECORD}")" || return 1
  write_student_web_build_record "${next_version}" "${source_fingerprint}" "${build_id_sha256}" || {
    echo "Student Web: production build identity could not be written." >&2
    return 1
  }
  student_web_production_build_is_current || {
    echo "Student Web: production build identity failed its final verification." >&2
    return 1
  }
  echo "Student Web: production build is current (Next.js ${next_version})."
}

ensure_student_web_production_build() {
  if student_web_production_build_is_current; then
    echo "Student Web: reusing the current production build."
    return 0
  fi
  build_student_web_production
}

write_student_web_identity() {
  local pid="$1"
  local next_version="$2"
  local build_id_sha256="$3"
  local mode="$4"
  local start_hash="$5"
  local current_start_hash tmp_file
  [[ "${mode}" == "pending" || "${mode}" == "production" ]] || return 1
  [[ "${next_version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?$ ]] || return 1
  [[ "${build_id_sha256}" =~ ^[a-f0-9]{64}$ ]] || return 1
  [[ "${start_hash}" =~ ^[a-f0-9]{64}$ ]] || return 1
  current_start_hash="$(process_start_hash "${pid}")" || return 1
  [[ "${current_start_hash}" == "${start_hash}" ]] || return 1
  tmp_file="${STUDENT_WEB_PID_FILE}.tmp.$$"
  {
    printf 'version=2\n'
    printf 'service=student-web\n'
    printf 'mode=%s\n' "${mode}"
    printf 'pid=%s\n' "${pid}"
    printf 'start_hash=%s\n' "${start_hash}"
    printf 'next_version=%s\n' "${next_version}"
    printf 'build_id_sha256=%s\n' "${build_id_sha256}"
  } > "${tmp_file}" || return 1
  chmod 600 "${tmp_file}" || {
    rm -f "${tmp_file}" || true
    return 1
  }
  mv "${tmp_file}" "${STUDENT_WEB_PID_FILE}" || {
    rm -f "${tmp_file}" || true
    return 1
  }
}

read_student_web_identity() {
  local line key value version service
  local seen_version=0
  local seen_service=0
  local seen_mode=0
  local seen_pid=0
  local seen_start_hash=0
  local seen_next_version=0
  local seen_build_id_sha256=0
  STUDENT_RECORD_MODE=""
  STUDENT_RECORD_PID=""
  STUDENT_RECORD_START_HASH=""
  STUDENT_RECORD_NEXT_VERSION=""
  STUDENT_RECORD_BUILD_ID_SHA256=""
  version=""
  service=""
  [[ -f "${STUDENT_WEB_PID_FILE}" ]] || return 1
  while IFS= read -r line || [[ -n "${line}" ]]; do
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      version)
        [[ "${seen_version}" == "0" ]] || return 1
        seen_version=1
        version="${value}"
        ;;
      service)
        [[ "${seen_service}" == "0" ]] || return 1
        seen_service=1
        service="${value}"
        ;;
      mode)
        [[ "${seen_mode}" == "0" ]] || return 1
        seen_mode=1
        STUDENT_RECORD_MODE="${value}"
        ;;
      pid)
        [[ "${seen_pid}" == "0" ]] || return 1
        seen_pid=1
        STUDENT_RECORD_PID="${value}"
        ;;
      start_hash)
        [[ "${seen_start_hash}" == "0" ]] || return 1
        seen_start_hash=1
        STUDENT_RECORD_START_HASH="${value}"
        ;;
      next_version)
        [[ "${seen_next_version}" == "0" ]] || return 1
        seen_next_version=1
        STUDENT_RECORD_NEXT_VERSION="${value}"
        ;;
      build_id_sha256)
        [[ "${seen_build_id_sha256}" == "0" ]] || return 1
        seen_build_id_sha256=1
        STUDENT_RECORD_BUILD_ID_SHA256="${value}"
        ;;
      *) return 1 ;;
    esac
  done < "${STUDENT_WEB_PID_FILE}"
  [[ "${version}" == "2" && "${service}" == "student-web" ]] || return 1
  [[ "${STUDENT_RECORD_MODE}" == "pending" || "${STUDENT_RECORD_MODE}" == "production" ]] || return 1
  [[ "${STUDENT_RECORD_PID}" =~ ^[1-9][0-9]*$ ]] || return 1
  [[ "${STUDENT_RECORD_START_HASH}" =~ ^[a-f0-9]{64}$ ]] || return 1
  [[ "${STUDENT_RECORD_NEXT_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.][A-Za-z0-9.]+)?$ ]] || return 1
  [[ "${STUDENT_RECORD_BUILD_ID_SHA256}" =~ ^[a-f0-9]{64}$ ]] || return 1
}

student_web_identity_matches_process() {
  local current_start_hash current_cwd
  read_student_web_identity || return 1
  process_is_alive "${STUDENT_RECORD_PID}" || return 1
  current_start_hash="$(process_start_hash "${STUDENT_RECORD_PID}")" || return 1
  [[ "${current_start_hash}" == "${STUDENT_RECORD_START_HASH}" ]] || return 1
  current_cwd="$(process_cwd "${STUDENT_RECORD_PID}")" || return 1
  [[ "${current_cwd}" == "${STUDENT_WEB_DIR}" ]] || return 1
  if process_command_contains "${STUDENT_RECORD_PID}" "next-server (v${STUDENT_RECORD_NEXT_VERSION})"; then
    return 0
  fi
  if [[ "${STUDENT_RECORD_MODE}" == "pending" ]]; then
    if process_command_contains "${STUDENT_RECORD_PID}" "node_modules/next/dist/bin/next start"; then
      return 0
    fi
    process_command_contains "${STUDENT_RECORD_PID}" "mira-student-launch"
    return
  fi
  return 1
}

student_web_identity_is_current_production() {
  local current_next_version current_build_id_sha256
  student_web_identity_matches_process || return 1
  [[ "${STUDENT_RECORD_MODE}" == "production" ]] || return 1
  current_next_version="$(student_web_next_version)" || return 1
  current_build_id_sha256="$(student_web_build_id_sha256)" || return 1
  [[ "${STUDENT_RECORD_NEXT_VERSION}" == "${current_next_version}" ]] || return 1
  [[ "${STUDENT_RECORD_BUILD_ID_SHA256}" == "${current_build_id_sha256}" ]] || return 1
  student_web_production_build_is_current || return 1
  port_is_owned_by_tree "${STUDENT_WEB_PORT}" "${STUDENT_RECORD_PID}" || return 1
}

read_legacy_student_web_identity() {
  local line key value version service
  local seen_version=0
  local seen_service=0
  local seen_pid=0
  local seen_start_hash=0
  LEGACY_STUDENT_RECORD_PID=""
  LEGACY_STUDENT_RECORD_START_HASH=""
  version=""
  service=""
  [[ -f "${STUDENT_WEB_PID_FILE}" ]] || return 1
  while IFS= read -r line || [[ -n "${line}" ]]; do
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      version)
        [[ "${seen_version}" == "0" ]] || return 1
        seen_version=1
        version="${value}"
        ;;
      service)
        [[ "${seen_service}" == "0" ]] || return 1
        seen_service=1
        service="${value}"
        ;;
      pid)
        [[ "${seen_pid}" == "0" ]] || return 1
        seen_pid=1
        LEGACY_STUDENT_RECORD_PID="${value}"
        ;;
      start_hash)
        [[ "${seen_start_hash}" == "0" ]] || return 1
        seen_start_hash=1
        LEGACY_STUDENT_RECORD_START_HASH="${value}"
        ;;
      *) return 1 ;;
    esac
  done < "${STUDENT_WEB_PID_FILE}"
  [[ "${version}" == "1" && "${service}" == "student-web" ]] || return 1
  [[ "${LEGACY_STUDENT_RECORD_PID}" =~ ^[1-9][0-9]*$ ]] || return 1
  [[ "${LEGACY_STUDENT_RECORD_START_HASH}" =~ ^[a-f0-9]{64}$ ]] || return 1
}

legacy_student_web_identity_matches_process() {
  local current_start_hash current_cwd
  read_legacy_student_web_identity || return 1
  process_is_alive "${LEGACY_STUDENT_RECORD_PID}" || return 1
  current_start_hash="$(process_start_hash "${LEGACY_STUDENT_RECORD_PID}")" || return 1
  [[ "${current_start_hash}" == "${LEGACY_STUDENT_RECORD_START_HASH}" ]] || return 1
  current_cwd="$(process_cwd "${LEGACY_STUDENT_RECORD_PID}")" || return 1
  [[ "${current_cwd}" == "${STUDENT_WEB_DIR}" ]] || return 1
  process_command_contains "${LEGACY_STUDENT_RECORD_PID}" "${STUDENT_WEB_LEGACY_DEV_COMMAND_TOKEN}"
}

student_web_identity_candidate_pid() {
  local count candidate
  [[ -f "${STUDENT_WEB_PID_FILE}" ]] || return 1
  count="$(awk -F= '$1 == "pid" { count += 1 } END { print count + 0 }' "${STUDENT_WEB_PID_FILE}")" || return 1
  [[ "${count}" == "1" ]] || return 1
  candidate="$(awk -F= '$1 == "pid" { print $2 }' "${STUDENT_WEB_PID_FILE}")" || return 1
  [[ "${candidate}" =~ ^[1-9][0-9]*$ ]] || return 1
  printf '%s' "${candidate}"
}

read_student_web_launch_pid() {
  local pid
  [[ -f "${STUDENT_WEB_LAUNCH_PID_FILE}" ]] || return 1
  pid="$(tr -d '[:space:]' < "${STUDENT_WEB_LAUNCH_PID_FILE}")"
  [[ "${pid}" =~ ^[1-9][0-9]*$ ]] || return 1
  printf '%s' "${pid}"
}

student_web_recorded_identity_matches_kind() {
  local kind="$1"
  case "${kind}" in
    production) student_web_identity_matches_process ;;
    legacy-dev) legacy_student_web_identity_matches_process ;;
    *) return 1 ;;
  esac
}

student_web_original_instance_is_gone() {
  local pid="$1"
  local expected_start_hash="$2"
  local state current_start_hash
  if ! kill -0 "${pid}" 2>/dev/null; then
    return 0
  fi
  state="$(ps -p "${pid}" -o stat= 2>/dev/null | awk '{print $1}')"
  [[ -n "${state}" ]] || return 1
  [[ "${state}" == Z* ]] && return 0
  current_start_hash="$(process_start_hash "${pid}")" || return 1
  [[ "${current_start_hash}" != "${expected_start_hash}" ]]
}

terminate_student_web_owned_process() {
  local kind="$1"
  local pid="$2"
  local expected_start_hash i
  student_web_recorded_identity_matches_kind "${kind}" || {
    echo "Student Web: recorded ${kind} identity is no longer valid; refusing to stop it." >&2
    return 1
  }
  case "${kind}" in
    production) expected_start_hash="${STUDENT_RECORD_START_HASH}" ;;
    legacy-dev) expected_start_hash="${LEGACY_STUDENT_RECORD_START_HASH}" ;;
    *) return 1 ;;
  esac
  if port_is_listening "${STUDENT_WEB_PORT}" && ! port_is_owned_by_tree "${STUDENT_WEB_PORT}" "${pid}"; then
    echo "Student Web: port ${STUDENT_WEB_PORT} is not owned by the recorded process tree; nothing was stopped." >&2
    return 1
  fi
  kill "${pid}" || {
    echo "Student Web: TERM failed; identity was preserved." >&2
    return 1
  }
  for ((i = 0; i < 40; i += 1)); do
    process_is_alive "${pid}" || break
    sleep 0.25
  done
  if process_is_alive "${pid}"; then
    student_web_recorded_identity_matches_kind "${kind}" || {
      echo "Student Web: PID changed identity while stopping; refusing to send SIGKILL." >&2
      return 1
    }
    kill -KILL "${pid}" || {
      echo "Student Web: SIGKILL failed; identity was preserved." >&2
      return 1
    }
  fi
  for ((i = 0; i < 40; i += 1)); do
    student_web_original_instance_is_gone "${pid}" "${expected_start_hash}" && break
    sleep 0.25
  done
  if ! student_web_original_instance_is_gone "${pid}" "${expected_start_hash}"; then
    echo "Student Web: the recorded process instance cannot be proven stopped; identity was preserved." >&2
    return 1
  fi
  for ((i = 0; i < 40; i += 1)); do
    port_is_listening "${STUDENT_WEB_PORT}" || break
    sleep 0.25
  done
  if port_is_listening "${STUDENT_WEB_PORT}"; then
    echo "Student Web: port ${STUDENT_WEB_PORT} remains occupied; the remaining listener was not killed." >&2
    return 1
  fi
  rm -f "${STUDENT_WEB_PID_FILE}" "${STUDENT_WEB_LAUNCH_PID_FILE}" || {
    echo "Student Web: process stopped, but identity cleanup failed." >&2
    return 1
  }
  echo "Student Web: stopped ${kind} process"
}

stop_student_web() {
  local pid
  if [[ -e "${STUDENT_WEB_LAUNCH_PID_FILE}" && ! -e "${STUDENT_WEB_PID_FILE}" ]]; then
    pid="$(read_student_web_launch_pid 2>/dev/null || true)"
    if [[ -z "${pid}" ]]; then
      echo "Student Web: malformed launch PID record; preserving it for inspection." >&2
      return 1
    fi
    if process_is_alive "${pid}"; then
      echo "Student Web: launch PID ${pid} has no durable start hash; refusing to stop or replace it." >&2
      return 1
    fi
    if port_is_listening "${STUDENT_WEB_PORT}"; then
      echo "Student Web: recorded launch PID is gone but port ${STUDENT_WEB_PORT} is occupied; unknown listener was not stopped." >&2
      return 1
    fi
    rm -f "${STUDENT_WEB_LAUNCH_PID_FILE}"
  fi
  if [[ ! -e "${STUDENT_WEB_PID_FILE}" ]]; then
    if port_is_listening "${STUDENT_WEB_PORT}"; then
      echo "Student Web: port ${STUDENT_WEB_PORT} is owned by an unmanaged process; it was not stopped." >&2
      return 1
    fi
    echo "Student Web: already stopped"
    return 0
  fi

  if student_web_identity_matches_process; then
    pid="${STUDENT_RECORD_PID}"
    terminate_student_web_owned_process production "${pid}"
    return
  fi
  if legacy_student_web_identity_matches_process; then
    pid="${LEGACY_STUDENT_RECORD_PID}"
    terminate_student_web_owned_process legacy-dev "${pid}"
    return
  fi

  if port_is_listening "${STUDENT_WEB_PORT}"; then
    echo "Student Web: identity is stale or invalid while port ${STUDENT_WEB_PORT} is occupied; refusing to take ownership." >&2
    return 1
  fi
  pid="$(student_web_identity_candidate_pid 2>/dev/null || true)"
  if [[ -z "${pid}" ]]; then
    echo "Student Web: malformed identity has no unique readable PID; preserving it for inspection." >&2
    return 1
  fi
  if process_is_alive "${pid}"; then
    echo "Student Web: live PID failed strict identity validation; it was not stopped and its identity was preserved." >&2
    return 1
  fi
  rm -f "${STUDENT_WEB_PID_FILE}" "${STUDENT_WEB_LAUNCH_PID_FILE}"
  echo "Student Web: removed a stale identity for a process that is no longer alive"
}

cleanup_just_started_student_web() {
  local pid="$1"
  local expected_start_hash="$2"
  local current_start_hash i
  current_start_hash="$(process_start_hash "${pid}" 2>/dev/null || true)"
  if [[ -z "${current_start_hash}" || "${current_start_hash}" != "${expected_start_hash}" ]]; then
    echo "Student Web: failed launch changed or lost its start identity; it was left untouched." >&2
    return 1
  fi
  kill "${pid}" 2>/dev/null || {
    echo "Student Web: failed launch could not be terminated; launch PID record was preserved." >&2
    return 1
  }
  for ((i = 0; i < 40; i += 1)); do
    process_is_alive "${pid}" || break
    sleep 0.25
  done
  if process_is_alive "${pid}"; then
    current_start_hash="$(process_start_hash "${pid}" 2>/dev/null || true)"
    if [[ -z "${current_start_hash}" || "${current_start_hash}" != "${expected_start_hash}" ]]; then
      echo "Student Web: failed launch changed identity before cleanup; refusing SIGKILL." >&2
      return 1
    fi
    kill -KILL "${pid}" 2>/dev/null || {
      echo "Student Web: failed launch could not be force-stopped; launch PID record was preserved." >&2
      return 1
    }
  fi
  for ((i = 0; i < 40; i += 1)); do
    student_web_original_instance_is_gone "${pid}" "${expected_start_hash}" && break
    sleep 0.25
  done
  if ! student_web_original_instance_is_gone "${pid}" "${expected_start_hash}" || port_is_listening "${STUDENT_WEB_PORT}"; then
    echo "Student Web: failed launch could not be proven stopped; launch PID record was preserved." >&2
    return 1
  fi
  rm -f "${STUDENT_WEB_LAUNCH_PID_FILE}" "${STUDENT_WEB_PID_FILE}" || return 1
}

student_web_runtime_is_healthy() {
  local pid
  student_web_identity_is_current_production || return 1
  pid="${STUDENT_RECORD_PID}"
  probe "${STUDENT_WEB_HEALTH_URL}" || return 1
  student_web_identity_is_current_production || return 1
  [[ "${STUDENT_RECORD_PID}" == "${pid}" ]] || return 1
}

wait_for_student_web_command() {
  local pid="$1"
  local next_version="$2"
  local i
  for ((i = 0; i < 100; i += 1)); do
    process_is_alive "${pid}" || return 1
    if process_command_contains "${pid}" "next-server (v${next_version})"; then
      return 0
    fi
    sleep 0.05
  done
  return 1
}

launch_student_web_production() {
  local node_bin node_options next_version build_id_sha256
  local pid launch_recorded_pid started_start_hash i
  student_web_production_build_is_current || {
    echo "Student Web: refusing to start without a current production build." >&2
    return 1
  }
  next_version="${STUDENT_BUILD_NEXT_VERSION}"
  build_id_sha256="${STUDENT_BUILD_ID_SHA256}"
  node_bin="$(resolve_node_bin)" || {
    echo "Student Web: Node.js is unavailable." >&2
    return 1
  }
  node_options="$(student_node_options "${node_bin}")" || {
    echo "Student Web: Node.js version could not be validated." >&2
    return 1
  }
  assert_unknown_port_is_free "Student Web" "${STUDENT_WEB_PORT}" || return 1

  (
    cd "${STUDENT_WEB_DIR}" || exit 1
    nohup /bin/bash -c '
      launch_pid_file="$1"
      shift
      umask 077
      printf "%s\n" "$$" > "${launch_pid_file}" || exit 111
      chmod 600 "${launch_pid_file}" || exit 112
      exec "$@"
    ' mira-student-launch "${STUDENT_WEB_LAUNCH_PID_FILE}" \
      env -i \
        PATH="${PATH}" \
        HOME="${HOME}" \
        TMPDIR="${TMPDIR:-/tmp}" \
        LANG="${LANG:-en_US.UTF-8}" \
        NODE_OPTIONS="${node_options}" \
        NODE_ENV=production \
        NEXT_TELEMETRY_DISABLED=1 \
        MIRA_LOCAL_LAN_PRODUCTION_MODE=1 \
        "${node_bin}" node_modules/next/dist/bin/next start \
          --hostname 0.0.0.0 --port "${STUDENT_WEB_PORT}" \
        > "${STUDENT_WEB_LOG}" 2>&1 < /dev/null &
    pid="$!"
    launch_recorded_pid=""
    for ((i = 0; i < 100; i += 1)); do
      launch_recorded_pid="$(read_student_web_launch_pid 2>/dev/null || true)"
      [[ "${launch_recorded_pid}" == "${pid}" ]] && break
      process_is_alive "${pid}" || break
      sleep 0.05
    done
    [[ "${launch_recorded_pid}" == "${pid}" ]] || {
      echo "Student Web: launcher did not publish its exact PID before exec; no process was adopted." >&2
      exit 1
    }
    started_start_hash="$(process_start_hash "${pid}")" || {
      echo "Student Web: started PID has no readable start identity; its launch PID record was preserved and it was left untouched." >&2
      exit 1
    }
    write_student_web_identity "${pid}" "${next_version}" "${build_id_sha256}" pending "${started_start_hash}" || {
      cleanup_just_started_student_web "${pid}" "${started_start_hash}" >/dev/null 2>&1 || true
      exit 1
    }
    rm -f "${STUDENT_WEB_LAUNCH_PID_FILE}" || exit 1
    if ! wait_for_student_web_command "${pid}" "${next_version}"; then
      echo "Student Web: production process did not establish the expected Next.js ${next_version} identity." >&2
      exit 1
    fi
  ) || {
    if [[ -e "${STUDENT_WEB_PID_FILE}" ]]; then
      stop_student_web >/dev/null 2>&1 || true
    fi
    return 1
  }

  read_student_web_identity || return 1
  pid="${STUDENT_RECORD_PID}"
  started_start_hash="${STUDENT_RECORD_START_HASH}"
  if ! wait_for_probe "Student Web" "${STUDENT_WEB_HEALTH_URL}" "${pid}" "${STUDENT_WEB_LOG}"; then
    stop_student_web >/dev/null 2>&1 || true
    return 1
  fi
  if ! student_web_identity_matches_process || \
    ! port_is_owned_by_tree "${STUDENT_WEB_PORT}" "${pid}" || \
    ! student_web_production_build_is_current; then
    echo "Student Web: ownership or build changed during readiness; refusing to publish a healthy identity." >&2
    stop_student_web >/dev/null 2>&1 || true
    return 1
  fi
  [[ "${STUDENT_RECORD_PID}" == "${pid}" ]] || {
    echo "Student Web: PID changed during readiness; refusing to publish a healthy identity." >&2
    stop_student_web >/dev/null 2>&1 || true
    return 1
  }
  write_student_web_identity "${pid}" "${next_version}" "${build_id_sha256}" production "${started_start_hash}" || {
    stop_student_web >/dev/null 2>&1 || true
    return 1
  }
  if ! student_web_runtime_is_healthy; then
    echo "Student Web: final production identity verification failed." >&2
    stop_student_web >/dev/null 2>&1 || true
    return 1
  fi
  echo "Student Web: started with Next.js ${next_version} production at ${STUDENT_WEB_HEALTH_URL} (log: ${STUDENT_WEB_LOG})"
}

build_student_web_production_offline() {
  if student_web_production_build_is_current; then
    echo "Student Web: reusing the current production build."
    return 0
  fi
  if [[ -e "${STUDENT_WEB_PID_FILE}" || -e "${STUDENT_WEB_LAUNCH_PID_FILE}" ]] || \
    port_is_listening "${STUDENT_WEB_PORT}"; then
    echo "Student Web: stop the service and clear its strict identity before replacing a stale production build." >&2
    return 1
  fi
  ensure_student_web_production_build
}

cleanup_stale_identity_if_safe() {
  local label="$1"
  local port="$2"
  local identity_file="$3"
  local service="$4"
  local expected_cwd="$5"
  local command_token="$6"

  [[ -e "${identity_file}" ]] || return 0
  if identity_matches_process "${identity_file}" "${service}" "${expected_cwd}" "${command_token}"; then
    return 0
  fi
  if port_is_listening "${port}"; then
    echo "${label}: PID identity is stale or invalid while port ${port} is occupied; refusing to take ownership." >&2
    return 1
  fi
  if read_identity_record "${identity_file}" "${service}" && process_is_alive "${RECORD_PID}"; then
    echo "${label}: PID identity does not match the expected command; refusing to stop or replace it." >&2
    return 1
  fi
  rm -f "${identity_file}"
}

stop_managed_service() {
  local label="$1"
  local service="$2"
  local port="$3"
  local identity_file="$4"
  local expected_cwd="$5"
  local command_token="$6"
  local pid i

  if [[ ! -e "${identity_file}" ]]; then
    if port_is_listening "${port}"; then
      echo "${label}: port ${port} is owned by an unmanaged process; it was not stopped." >&2
      return 1
    fi
    echo "${label}: already stopped"
    return 0
  fi

  if ! read_identity_record "${identity_file}" "${service}"; then
    echo "${label}: malformed PID identity file ${identity_file}; refusing to stop anything." >&2
    return 1
  fi
  pid="${RECORD_PID}"
  if ! process_is_alive "${pid}"; then
    if port_is_listening "${port}"; then
      echo "${label}: recorded process is gone but port ${port} is occupied; unknown listener was not stopped." >&2
      return 1
    fi
    rm -f "${identity_file}"
    echo "${label}: removed stale PID identity"
    return 0
  fi
  if ! identity_matches_process "${identity_file}" "${service}" "${expected_cwd}" "${command_token}"; then
    echo "${label}: live PID failed strict identity validation; it was not stopped." >&2
    return 1
  fi
  if port_is_listening "${port}" && ! port_is_owned_by_tree "${port}" "${pid}"; then
    echo "${label}: port ${port} is not owned by the recorded process tree; no listener was stopped." >&2
    return 1
  fi

  kill "${pid}"
  for ((i = 0; i < 40; i += 1)); do
    process_is_alive "${pid}" || break
    sleep 0.25
  done
  if process_is_alive "${pid}"; then
    if ! identity_matches_process "${identity_file}" "${service}" "${expected_cwd}" "${command_token}"; then
      echo "${label}: PID changed identity while stopping; refusing to send SIGKILL." >&2
      return 1
    fi
    kill -KILL "${pid}"
  fi
  for ((i = 0; i < 40; i += 1)); do
    port_is_listening "${port}" || break
    sleep 0.25
  done
  if port_is_listening "${port}"; then
    echo "${label}: port ${port} remains occupied; remaining listener was not killed." >&2
    return 1
  fi
  rm -f "${identity_file}"
  echo "${label}: stopped"
}

curriculum_worker_status() {
  if identity_matches_process "${CURRICULUM_WORKER_PID_FILE}" curriculum-worker \
    "${BACKEND_DIR}" "${CURRICULUM_WORKER_COMMAND_TOKEN}"; then
    echo "Curriculum worker: running (PID ${RECORD_PID}, log: ${CURRICULUM_WORKER_LOG})"
    return 0
  fi
  if [[ "${REPAIR_MODE}" == "1" && ! -e "${CURRICULUM_WORKER_PID_FILE}" ]]; then
    echo "Curriculum worker: disabled by explicit repair mode"
    return 0
  fi
  echo "Curriculum worker: stopped or identity invalid" >&2
  return 1
}

start_curriculum_worker() {
  local python_bin pid candidate_pid i
  if [[ "${REPAIR_MODE}" == "1" ]]; then
    stop_curriculum_worker || return 1
    echo "Curriculum worker: disabled by explicit repair mode"
    return 0
  fi
  if identity_matches_process "${CURRICULUM_WORKER_PID_FILE}" curriculum-worker \
    "${BACKEND_DIR}" "${CURRICULUM_WORKER_COMMAND_TOKEN}"; then
    curriculum_worker_status
    return
  fi
  if [[ -e "${CURRICULUM_WORKER_PID_FILE}" ]]; then
    if ! read_identity_record "${CURRICULUM_WORKER_PID_FILE}" curriculum-worker || \
      process_is_alive "${RECORD_PID}"; then
      echo "Curriculum worker: invalid live identity; refusing to start a duplicate." >&2
      return 1
    fi
    rm -f "${CURRICULUM_WORKER_PID_FILE}"
  fi
  for candidate_pid in $(pgrep -f "[w]orkers[.]learning_curriculum_preparation_worker" || true); do
    if [[ "$(process_cwd "${candidate_pid}")" == "${BACKEND_DIR}" ]]; then
      echo "Curriculum worker: an unmanaged worker already exists; refusing to start a duplicate." >&2
      return 1
    fi
  done
  probe "${BACKEND_HEALTH_URL}" && probe "${OPENMAIC_HEALTH_URL}" && \
    probe "${GATEWAY_HEALTH_URL}" || {
      echo "Curriculum worker: backend, OpenMAIC and gateway must be healthy before generation starts." >&2
      return 1
    }
  python_bin="$(resolve_python_bin)" || return 1
  (
    cd "${BACKEND_DIR}" || exit 1
    umask 077
    nohup env -i \
      PATH="${PATH}" HOME="${HOME}" TMPDIR="${TMPDIR:-/tmp}" \
      LANG="${LANG:-en_US.UTF-8}" PYTHONUNBUFFERED=1 APP_DEBUG=0 \
      "${python_bin}" -c 'import os, sys; os.setsid(); os.execv(sys.executable, [sys.executable, "-m", "workers.learning_curriculum_preparation_worker"])' \
      > "${CURRICULUM_WORKER_LOG}" 2>&1 < /dev/null &
    pid="$!"
    write_identity_record "${CURRICULUM_WORKER_PID_FILE}" curriculum-worker "${pid}" || {
      kill "${pid}" 2>/dev/null || true
      exit 1
    }
  ) || return 1
  for ((i = 0; i < 40; i += 1)); do
    if ! identity_matches_process "${CURRICULUM_WORKER_PID_FILE}" curriculum-worker \
      "${BACKEND_DIR}" "${CURRICULUM_WORKER_COMMAND_TOKEN}"; then
      echo "Curriculum worker: startup failed; inspect ${CURRICULUM_WORKER_LOG}." >&2
      return 1
    fi
    if grep -q 'curriculum worker ready' "${CURRICULUM_WORKER_LOG}"; then
      curriculum_worker_status
      return
    fi
    sleep 1
  done
  echo "Curriculum worker: preflight has not completed; process and identity preserved (log: ${CURRICULUM_WORKER_LOG})." >&2
  return 1
}

stop_curriculum_worker() {
  local pid i
  [[ -e "${CURRICULUM_WORKER_PID_FILE}" ]] || return 0
  if ! read_identity_record "${CURRICULUM_WORKER_PID_FILE}" curriculum-worker; then
    echo "Curriculum worker: malformed identity; refusing to stop anything." >&2
    return 1
  fi
  pid="${RECORD_PID}"
  if ! process_is_alive "${pid}"; then
    rm -f "${CURRICULUM_WORKER_PID_FILE}"
    return 0
  fi
  if ! identity_matches_process "${CURRICULUM_WORKER_PID_FILE}" curriculum-worker \
    "${BACKEND_DIR}" "${CURRICULUM_WORKER_COMMAND_TOKEN}"; then
    echo "Curriculum worker: live identity mismatch; process left untouched." >&2
    return 1
  fi
  kill -TERM "${pid}" || return 1
  for ((i = 0; i < 40; i += 1)); do
    if ! process_is_alive "${pid}"; then
      rm -f "${CURRICULUM_WORKER_PID_FILE}"
      echo "Curriculum worker: stopped after completing its current work unit"
      return 0
    fi
    sleep 1
  done
  echo "Curriculum worker: finishing its current work unit; no SIGKILL sent. Retry stop after it exits." >&2
  return 1
}

start_backend() {
  local python_bin pid process_role=api
  [[ "${REPAIR_MODE}" == "1" ]] && process_role=api-passive
  cleanup_stale_identity_if_safe Backend "${BACKEND_PORT}" "${BACKEND_PID_FILE}" backend "${BACKEND_DIR}" "app.py"
  if identity_matches_process "${BACKEND_PID_FILE}" backend "${BACKEND_DIR}" "app.py"; then
    pid="${RECORD_PID}"
    if probe "${BACKEND_HEALTH_URL}"; then
      echo "Backend: already healthy at ${BACKEND_HEALTH_URL}"
      return 0
    fi
    stop_managed_service Backend backend "${BACKEND_PORT}" "${BACKEND_PID_FILE}" "${BACKEND_DIR}" "app.py"
  fi
  assert_unknown_port_is_free Backend "${BACKEND_PORT}"
  python_bin="$(resolve_python_bin)" || {
    echo "Backend: Python 3 is unavailable." >&2
    return 1
  }
  (
    cd "${BACKEND_DIR}"
    nohup env -i \
      PATH="${PATH}" \
      HOME="${HOME}" \
      TMPDIR="${TMPDIR:-/tmp}" \
      LANG="${LANG:-en_US.UTF-8}" \
      PYTHONUNBUFFERED=1 \
      APP_DEBUG=0 \
      APP_PORT="${BACKEND_PORT}" \
      MIRA_PROCESS_ROLE="${process_role}" \
      "${python_bin}" -c 'import os, sys; os.setsid(); os.execv(sys.executable, [sys.executable, "app.py"])' \
      > "${BACKEND_LOG}" 2>&1 < /dev/null &
    pid="$!"
    write_identity_record "${BACKEND_PID_FILE}" backend "${pid}" || {
      kill "${pid}" 2>/dev/null || true
      exit 1
    }
  )
  read_identity_record "${BACKEND_PID_FILE}" backend
  pid="${RECORD_PID}"
  wait_for_probe Backend "${BACKEND_HEALTH_URL}" "${pid}" "${BACKEND_LOG}"
  echo "Backend: started at ${BACKEND_HEALTH_URL} (log: ${BACKEND_LOG})"
  echo "Backend: role=${process_role}; curriculum generation is managed by the separate worker."
}

start_student_web() {
  if student_web_runtime_is_healthy; then
    echo "Student Web: already healthy with the current production build at ${STUDENT_WEB_HEALTH_URL}"
    return 0
  fi

  if [[ -e "${STUDENT_WEB_PID_FILE}" || -e "${STUDENT_WEB_LAUNCH_PID_FILE}" ]] || port_is_listening "${STUDENT_WEB_PORT}"; then
    stop_student_web || return 1
  fi
  assert_unknown_port_is_free "Student Web" "${STUDENT_WEB_PORT}" || return 1
  ensure_student_web_production_build || return 1
  launch_student_web_production
}

native_invoke() {
  env -i \
    PATH="${PATH}" \
    HOME="${HOME}" \
    TMPDIR="${TMPDIR:-/tmp}" \
    LANG="${LANG:-en_US.UTF-8}" \
    MIRA_OPENMAIC_LOG_DIR="${NATIVE_STATE_DIR}" \
    OPENMAIC_ADMIN_PORT="${OPENMAIC_PORT}" \
    MIRA_RUNTIME_PORT="${GATEWAY_PORT}" \
    MIRA_BACKEND_INTERNAL_URL="http://127.0.0.1:${BACKEND_PORT}" \
    MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1 \
    MIRA_OPENMAIC_ENABLE_QWEN_TTS=1 \
    MIRA_OPENMAIC_ENABLE_QWEN_ASR=1 \
    MIRA_LOCAL_LAN_PRODUCTION_MODE=1 \
    "${NATIVE_RUNTIME_SCRIPT}" "$@"
}

read_native_pid() {
  local file="$1"
  local pid
  [[ -f "${file}" ]] || return 1
  pid="$(tr -d '[:space:]' < "${file}")"
  [[ "${pid}" =~ ^[1-9][0-9]*$ ]] || return 1
  printf '%s' "${pid}"
}

validate_native_service_safety() {
  local label="$1"
  local service="$2"
  local port="$3"
  local native_pid_file="$4"
  local identity_file="$5"
  local expected_cwd="$6"
  local command_token="$7"
  local fallback_command_token="${8:-}"
  local native_pid

  if [[ ! -e "${native_pid_file}" && ! -e "${identity_file}" ]]; then
    assert_unknown_port_is_free "${label}" "${port}"
    return 0
  fi
  if [[ ! -e "${native_pid_file}" || ! -e "${identity_file}" ]]; then
    if ! port_is_listening "${port}"; then
      local possible_pid=""
      possible_pid="$(read_native_pid "${native_pid_file}" 2>/dev/null || true)"
      if [[ -z "${possible_pid}" ]] || ! process_is_alive "${possible_pid}"; then
        rm -f "${native_pid_file}" "${identity_file}"
        return 0
      fi
    fi
    echo "${label}: incomplete native PID identity; refusing to stop or replace any process." >&2
    return 1
  fi
  native_pid="$(read_native_pid "${native_pid_file}")" || {
    echo "${label}: malformed native PID file; refusing to stop any process." >&2
    return 1
  }
  read_identity_record "${identity_file}" "${service}" || {
    echo "${label}: malformed companion identity; refusing to stop any process." >&2
    return 1
  }
  [[ "${RECORD_PID}" == "${native_pid}" ]] || {
    echo "${label}: native PID and companion identity disagree; refusing to stop any process." >&2
    return 1
  }
  if ! process_is_alive "${native_pid}"; then
    if port_is_listening "${port}"; then
      echo "${label}: recorded process is gone but port ${port} has an unknown listener; it was not stopped." >&2
      return 1
    fi
    rm -f "${native_pid_file}" "${identity_file}"
    return 0
  fi
  if ! identity_matches_process "${identity_file}" "${service}" "${expected_cwd}" "${command_token}"; then
    if [[ -z "${fallback_command_token}" ]] || \
      ! identity_matches_process "${identity_file}" "${service}" "${expected_cwd}" "${fallback_command_token}"; then
      echo "${label}: live process failed strict native identity validation; it was not stopped." >&2
      return 1
    fi
  fi
  if port_is_listening "${port}" && ! port_is_owned_by_tree "${port}" "${native_pid}"; then
    echo "${label}: port ${port} is not owned by the recorded native process tree." >&2
    return 1
  fi
}

validate_native_stack_safety() {
  validate_native_service_safety OpenMAIC openmaic "${OPENMAIC_PORT}" \
    "${OPENMAIC_NATIVE_PID_FILE}" "${OPENMAIC_IDENTITY_FILE}" \
    "${OPENMAIC_DIR}" "${OPENMAIC_PRODUCTION_COMMAND_TOKEN}" \
    "${OPENMAIC_LEGACY_DEV_COMMAND_TOKEN}" || return 1
  validate_native_service_safety Gateway gateway "${GATEWAY_PORT}" \
    "${GATEWAY_NATIVE_PID_FILE}" "${GATEWAY_IDENTITY_FILE}" \
    "${GATEWAY_DIR}" "src/server.mjs" || return 1
}

adopt_native_identity() {
  local label="$1"
  local service="$2"
  local native_pid_file="$3"
  local identity_file="$4"
  local expected_cwd="$5"
  local command_token="$6"
  local pid
  pid="$(read_native_pid "${native_pid_file}")" || {
    echo "${label}: native runtime did not write a valid PID file." >&2
    return 1
  }
  process_is_alive "${pid}" || {
    echo "${label}: native runtime PID is not alive." >&2
    return 1
  }
  [[ "$(process_cwd "${pid}")" == "${expected_cwd}" ]] || {
    echo "${label}: native runtime PID has an unexpected working directory." >&2
    return 1
  }
  process_command_contains "${pid}" "${command_token}" || {
    echo "${label}: native runtime PID has an unexpected command." >&2
    return 1
  }
  write_identity_record "${identity_file}" "${service}" "${pid}"
}

adopt_native_stack() {
  adopt_native_identity OpenMAIC openmaic "${OPENMAIC_NATIVE_PID_FILE}" \
    "${OPENMAIC_IDENTITY_FILE}" "${OPENMAIC_DIR}" "${OPENMAIC_PRODUCTION_COMMAND_TOKEN}"
  adopt_native_identity Gateway gateway "${GATEWAY_NATIVE_PID_FILE}" \
    "${GATEWAY_IDENTITY_FILE}" "${GATEWAY_DIR}" "src/server.mjs"
}

disable_legacy_launchd_stack() {
  command -v launchctl >/dev/null 2>&1 || return 0
  local domain service loaded
  domain="gui/$(id -u)"
  loaded=0
  for service in backend openmaic gateway; do
    if launchctl print "${domain}/chat.mira.dev.${service}" >/dev/null 2>&1; then
      loaded=1
    fi
  done
  [[ "${loaded}" == "0" ]] && return 0
  echo "Stopping the exact legacy Mira LaunchAgents before starting the nohup stack."
  "${LEGACY_STACK_SCRIPT}" stop
  for service in backend openmaic gateway; do
    if launchctl print "${domain}/chat.mira.dev.${service}" >/dev/null 2>&1; then
      echo "Legacy LaunchAgent chat.mira.dev.${service} is still loaded; local stack was not started." >&2
      return 1
    fi
  done
}

start_native_stack() {
  validate_native_stack_safety
  if identity_matches_process "${OPENMAIC_IDENTITY_FILE}" openmaic \
    "${OPENMAIC_DIR}" "${OPENMAIC_PRODUCTION_COMMAND_TOKEN}" && \
    native_invoke status >/dev/null 2>&1; then
    echo "OpenMAIC/Gateway: already healthy"
    return 0
  fi

  # A managed-but-unhealthy native process must be stopped before native-runtime
  # starts a replacement. Safety was proven above, so this cannot target an
  # unrelated listener even if a PID was recycled.
  native_invoke stop >/dev/null
  rm -f "${OPENMAIC_IDENTITY_FILE}" "${GATEWAY_IDENTITY_FILE}"
  assert_unknown_port_is_free OpenMAIC "${OPENMAIC_PORT}"
  assert_unknown_port_is_free Gateway "${GATEWAY_PORT}"

  if ! native_invoke start; then
    # Preserve strict ownership metadata for a process that started but failed
    # a later health gate, so a subsequent stop remains safe.
    adopt_native_stack >/dev/null 2>&1 || true
    echo "OpenMAIC/Gateway failed; inspect ${NATIVE_STATE_DIR}/openmaic.log and ${NATIVE_STATE_DIR}/gateway.log." >&2
    return 1
  fi
  adopt_native_stack
  echo "OpenMAIC/Gateway: detached with strict PID identities"
}

stop_native_stack() {
  local failed=0
  if ! validate_native_stack_safety; then
    return 1
  fi
  if ! native_invoke stop; then
    failed=1
  fi
  if port_is_listening "${OPENMAIC_PORT}" || port_is_listening "${GATEWAY_PORT}"; then
    echo "OpenMAIC/Gateway: a listener remains; no unknown process was killed." >&2
    failed=1
  else
    rm -f "${OPENMAIC_IDENTITY_FILE}" "${GATEWAY_IDENTITY_FILE}"
  fi
  return "${failed}"
}

service_status() {
  local label="$1"
  local service="$2"
  local port="$3"
  local health_url="$4"
  local identity_file="$5"
  local expected_cwd="$6"
  local command_token="$7"
  local pid

  if identity_matches_process "${identity_file}" "${service}" "${expected_cwd}" "${command_token}"; then
    pid="${RECORD_PID}"
    if port_is_owned_by_tree "${port}" "${pid}" && probe "${health_url}"; then
      echo "${label}: managed and healthy at ${health_url}"
      return 0
    fi
    echo "${label}: managed process is alive but unavailable at ${health_url}"
    return 1
  fi
  if port_is_listening "${port}"; then
    echo "${label}: unmanaged listener on port ${port} (will not be killed)"
  elif [[ -e "${identity_file}" ]]; then
    echo "${label}: stale or invalid PID identity at ${identity_file}"
  else
    echo "${label}: stopped"
  fi
  return 1
}

student_web_status() {
  local pid
  if student_web_runtime_is_healthy; then
    echo "Student Web: managed Next.js ${STUDENT_RECORD_NEXT_VERSION} production and healthy at ${STUDENT_WEB_HEALTH_URL}"
    return 0
  fi
  if student_web_identity_matches_process; then
    pid="${STUDENT_RECORD_PID}"
    if port_is_listening "${STUDENT_WEB_PORT}" && ! port_is_owned_by_tree "${STUDENT_WEB_PORT}" "${pid}"; then
      echo "Student Web: managed PID is alive but does not own every listener on port ${STUDENT_WEB_PORT}"
    elif [[ "${STUDENT_RECORD_MODE}" != "production" ]]; then
      echo "Student Web: managed production start is pending or failed readiness"
    elif ! student_web_production_build_is_current; then
      echo "Student Web: managed process is serving an old or changed production build"
    else
      echo "Student Web: managed production process is alive but HTTP readiness failed"
    fi
    return 1
  fi
  if legacy_student_web_identity_matches_process; then
    pid="${LEGACY_STUDENT_RECORD_PID}"
    if port_is_owned_by_tree "${STUDENT_WEB_PORT}" "${pid}"; then
      echo "Student Web: managed legacy next dev is running; start/restart will migrate it to production"
    else
      echo "Student Web: legacy identity is alive but does not own every listener on port ${STUDENT_WEB_PORT}"
    fi
    return 1
  fi
  if port_is_listening "${STUDENT_WEB_PORT}"; then
    echo "Student Web: unmanaged listener on port ${STUDENT_WEB_PORT} (will not be killed)"
  elif [[ -e "${STUDENT_WEB_PID_FILE}" ]]; then
    echo "Student Web: stale or invalid strict identity at ${STUDENT_WEB_PID_FILE}"
  else
    echo "Student Web: stopped"
  fi
  return 1
}

native_service_status() {
  local label="$1"
  local service="$2"
  local port="$3"
  local health_url="$4"
  local native_pid_file="$5"
  local identity_file="$6"
  local expected_cwd="$7"
  local command_token="$8"
  local native_pid

  native_pid="$(read_native_pid "${native_pid_file}" 2>/dev/null || true)"
  if [[ -n "${native_pid}" ]] && \
    read_identity_record "${identity_file}" "${service}" && \
    [[ "${RECORD_PID}" == "${native_pid}" ]] && \
    identity_matches_process "${identity_file}" "${service}" "${expected_cwd}" "${command_token}" && \
    port_is_owned_by_tree "${port}" "${native_pid}" && probe "${health_url}"; then
    echo "${label}: managed and healthy at ${health_url}"
    return 0
  fi
  if port_is_listening "${port}"; then
    echo "${label}: listener is unhealthy or not owned by this stack (will not be killed)"
  elif [[ -e "${native_pid_file}" || -e "${identity_file}" ]]; then
    echo "${label}: stale or invalid native PID identity"
  else
    echo "${label}: stopped"
  fi
  return 1
}

show_status() {
  local failed=0
  service_status Backend backend "${BACKEND_PORT}" "${BACKEND_HEALTH_URL}" \
    "${BACKEND_PID_FILE}" "${BACKEND_DIR}" "app.py" || failed=1
  curriculum_worker_status || failed=1
  student_web_status || failed=1
  native_service_status OpenMAIC openmaic "${OPENMAIC_PORT}" "${OPENMAIC_HEALTH_URL}" \
    "${OPENMAIC_NATIVE_PID_FILE}" "${OPENMAIC_IDENTITY_FILE}" \
    "${OPENMAIC_DIR}" "${OPENMAIC_PRODUCTION_COMMAND_TOKEN}" || failed=1
  native_service_status Gateway gateway "${GATEWAY_PORT}" "${GATEWAY_HEALTH_URL}" \
    "${GATEWAY_NATIVE_PID_FILE}" "${GATEWAY_IDENTITY_FILE}" \
    "${GATEWAY_DIR}" "src/server.mjs" || failed=1
  echo "Logs: ${BACKEND_LOG} ${CURRICULUM_WORKER_LOG} ${STUDENT_WEB_LOG} ${NATIVE_STATE_DIR}/openmaic.log ${NATIVE_STATE_DIR}/gateway.log"
  return "${failed}"
}

start_stack() {
  disable_legacy_launchd_stack
  start_backend
  start_native_stack
  start_student_web
  start_curriculum_worker
  show_status
}

stop_stack() {
  local failed=0
  # Keep dependencies alive until the paid work unit reaches a persisted result.
  stop_curriculum_worker || return 1
  stop_student_web || failed=1
  stop_native_stack || failed=1
  stop_managed_service Backend backend "${BACKEND_PORT}" \
    "${BACKEND_PID_FILE}" "${BACKEND_DIR}" "app.py" || failed=1
  return "${failed}"
}

main() {
  validate_configuration
  prepare_state_dir
  case "${1:-status}" in
    start)
      [[ $# -eq 1 ]] || { usage >&2; return 2; }
      start_stack
      ;;
    stop)
      [[ $# -eq 1 ]] || { usage >&2; return 2; }
      stop_stack
      ;;
    restart)
      [[ $# -eq 1 ]] || { usage >&2; return 2; }
      stop_stack
      start_stack
      ;;
    status)
      [[ $# -eq 1 ]] || { usage >&2; return 2; }
      show_status
      ;;
    start-curriculum-worker)
      [[ $# -eq 1 ]] || { usage >&2; return 2; }
      start_curriculum_worker
      ;;
    stop-curriculum-worker)
      [[ $# -eq 1 ]] || { usage >&2; return 2; }
      stop_curriculum_worker
      ;;
    build-student-web-production)
      [[ $# -eq 1 ]] || { usage >&2; return 2; }
      build_student_web_production_offline
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
