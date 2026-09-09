#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_SCRIPT="${SCRIPT_DIR}/local-test-stack.sh"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TMP_ROOT}"' EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

# shellcheck source=local-test-stack.sh
source "${STACK_SCRIPT}"

HASH_A="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
HASH_B="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
HASH_C="cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"

# The source/config fingerprint changes for application and dotenv inputs, but
# never follows mutable .next output and therefore cannot make itself stale.
(
  STUDENT_WEB_DIR="${TMP_ROOT}/fingerprint-student"
  mkdir -p "${STUDENT_WEB_DIR}/src" "${STUDENT_WEB_DIR}/.next"
  printf '{"name":"fixture"}\n' > "${STUDENT_WEB_DIR}/package.json"
  printf 'export const value = 1;\n' > "${STUDENT_WEB_DIR}/src/value.ts"
  printf 'MIRA_STUDENT_WEB_PUBLIC_URL=http://127.0.0.1:3000\n' > "${STUDENT_WEB_DIR}/.env.local"
  first="$(student_web_source_fingerprint)" || fail "initial source fingerprint failed"
  printf 'generated\n' > "${STUDENT_WEB_DIR}/.next/ignored"
  second="$(student_web_source_fingerprint)" || fail "fingerprint after .next output failed"
  [[ "${first}" == "${second}" ]] || fail ".next output changed the source fingerprint"
  printf 'export const value = 2;\n' > "${STUDENT_WEB_DIR}/src/value.ts"
  third="$(student_web_source_fingerprint)" || fail "fingerprint after source change failed"
  [[ "${third}" != "${second}" ]] || fail "source change did not invalidate the fingerprint"
  printf 'MIRA_STUDENT_WEB_PUBLIC_URL=http://127.0.0.1:3001\n' > "${STUDENT_WEB_DIR}/.env.local"
  fourth="$(student_web_source_fingerprint)" || fail "fingerprint after dotenv change failed"
  [[ "${fourth}" != "${third}" ]] || fail "production dotenv change did not invalidate the fingerprint"
)

# Production build records reject duplicate, unknown, and malformed fields.
(
  STUDENT_WEB_BUILD_RECORD="${TMP_ROOT}/student-build.identity"
  write_student_web_build_record 16.3.0 "${HASH_A}" "${HASH_B}" || fail "valid build record was not written"
  read_student_web_build_record || fail "valid build record was not read"
  printf 'next_version=16.3.0\n' >> "${STUDENT_WEB_BUILD_RECORD}"
  if read_student_web_build_record; then
    fail "duplicate build record field was accepted"
  fi
  cat > "${STUDENT_WEB_BUILD_RECORD}" <<EOF
version=1
next_version=16.3.0
source_fingerprint=${HASH_A}
build_id_sha256=${HASH_B}
unknown=value
EOF
  if read_student_web_build_record; then
    fail "unknown build record field was accepted"
  fi
)

# The strict v2 process identity rejects duplicate fields. The production
# commit must retain the exact start hash captured for the pending instance.
(
  STUDENT_WEB_PID_FILE="${TMP_ROOT}/student-v2.identity"
  mock_start_hash="${HASH_A}"
  process_start_hash() { printf '%s' "${mock_start_hash}"; }
  write_student_web_identity 43210 16.3.0 "${HASH_B}" pending "${HASH_A}" || fail "valid pending identity was not written"
  read_student_web_identity || fail "valid v2 identity was not read"
  [[ "${STUDENT_RECORD_MODE}" == "pending" ]] || fail "pending mode was not retained"
  mock_start_hash="${HASH_C}"
  if write_student_web_identity 43210 16.3.0 "${HASH_B}" production "${HASH_A}"; then
    fail "production commit accepted a recycled PID start hash"
  fi
  read_student_web_identity || fail "failed commit corrupted the pending identity"
  [[ "${STUDENT_RECORD_MODE}" == "pending" ]] || fail "failed commit replaced the pending identity"
  printf 'pid=43210\n' >> "${STUDENT_WEB_PID_FILE}"
  if read_student_web_identity; then
    fail "duplicate v2 identity field was accepted"
  fi
)

# The legacy v1 parser is intentionally separate and strict. Only the exact
# script-owned root `next dev` PID can be selected for first-run migration.
(
  STUDENT_WEB_DIR="${TMP_ROOT}/legacy-student"
  STUDENT_WEB_PID_FILE="${TMP_ROOT}/legacy.identity"
  mkdir -p "${STUDENT_WEB_DIR}"
  cat > "${STUDENT_WEB_PID_FILE}" <<EOF
version=1
service=student-web
pid=54321
start_hash=${HASH_A}
EOF
  process_is_alive() { [[ "$1" == "54321" ]]; }
  process_start_hash() { printf '%s' "${HASH_A}"; }
  process_cwd() { printf '%s' "${STUDENT_WEB_DIR}"; }
  process_command_contains() { [[ "$1" == "54321" && "$2" == "next/dist/bin/next dev" ]]; }
  legacy_student_web_identity_matches_process || fail "valid legacy dev identity was not recognized"
  printf 'pid=54321\n' >> "${STUDENT_WEB_PID_FILE}"
  if read_legacy_student_web_identity; then
    fail "duplicate legacy identity field was accepted"
  fi
)

# BUILD_ID/source drift blocks healthy status, while the recorded production
# identity remains sufficient for a safe stop. No current-build check is used
# in the stop path.
(
  STUDENT_WEB_DIR="${TMP_ROOT}/owned-student"
  STUDENT_WEB_PID_FILE="${TMP_ROOT}/owned.identity"
  STUDENT_WEB_LAUNCH_PID_FILE="${TMP_ROOT}/owned.launch.pid"
  STUDENT_WEB_PORT=53990
  mkdir -p "${STUDENT_WEB_DIR}"
  cat > "${STUDENT_WEB_PID_FILE}" <<EOF
version=2
service=student-web
mode=production
pid=65432
start_hash=${HASH_A}
next_version=16.3.0
build_id_sha256=${HASH_B}
EOF
  alive=1
  killed=0
  process_is_alive() { [[ "${alive}" == "1" ]]; }
  process_start_hash() { printf '%s' "${HASH_A}"; }
  process_cwd() { printf '%s' "${STUDENT_WEB_DIR}"; }
  process_command_contains() { [[ "$2" == "next-server (v16.3.0)" ]]; }
  port_is_listening() { return 1; }
  student_web_production_build_is_current() { return 1; }
  kill() { killed=1; alive=0; }
  student_web_original_instance_is_gone() { [[ "${alive}" == "0" ]]; }
  sleep() { :; }
  stop_student_web >/dev/null || fail "stale-build process could not be stopped by ownership identity"
  [[ "${killed}" == "1" ]] || fail "stale-build process was not stopped"
  [[ ! -e "${STUDENT_WEB_PID_FILE}" ]] || fail "successful safe stop left a process identity"
)

# An unknown listener cannot be adopted or killed, and build/launch are never
# reached after that failure.
(
  STUDENT_WEB_PID_FILE="${TMP_ROOT}/unknown.identity"
  STUDENT_WEB_LAUNCH_PID_FILE="${TMP_ROOT}/unknown.launch.pid"
  STUDENT_WEB_PORT=53991
  rm -f "${STUDENT_WEB_PID_FILE}" "${STUDENT_WEB_LAUNCH_PID_FILE}"
  student_web_runtime_is_healthy() { return 1; }
  port_is_listening() { return 0; }
  ensure_student_web_production_build() { fail "unknown port reached build"; }
  launch_student_web_production() { fail "unknown port reached launch"; }
  if start_student_web >/dev/null 2>&1; then
    fail "unknown Student Web listener was accepted"
  fi
)

# TERM failure and a still-live exact instance both preserve ownership state,
# even when port 3000 is not listening yet.
for stop_case in term-fails still-live; do
  (
    STUDENT_WEB_DIR="${TMP_ROOT}/${stop_case}-student"
    STUDENT_WEB_PID_FILE="${TMP_ROOT}/${stop_case}.identity"
    STUDENT_WEB_LAUNCH_PID_FILE="${TMP_ROOT}/${stop_case}.launch.pid"
    STUDENT_WEB_PORT=53993
    mkdir -p "${STUDENT_WEB_DIR}"
    cat > "${STUDENT_WEB_PID_FILE}" <<EOF
version=2
service=student-web
mode=pending
pid=76543
start_hash=${HASH_A}
next_version=16.3.0
build_id_sha256=${HASH_B}
EOF
    process_is_alive() { return 0; }
    process_start_hash() { printf '%s' "${HASH_A}"; }
    process_cwd() { printf '%s' "${STUDENT_WEB_DIR}"; }
    process_command_contains() { [[ "$2" == "node_modules/next/dist/bin/next start" ]]; }
    port_is_listening() { return 1; }
    sleep() { :; }
    student_web_original_instance_is_gone() { return 1; }
    if [[ "${stop_case}" == "term-fails" ]]; then
      kill() { return 1; }
    else
      kill() { return 0; }
    fi
    if stop_student_web >/dev/null 2>&1; then
      fail "${stop_case} unexpectedly reported a stopped process"
    fi
    [[ -f "${STUDENT_WEB_PID_FILE}" ]] || fail "${stop_case} removed identity without proving the instance dead"
  )
done

# A candidate whose start hash was never captured is never killed or replaced.
(
  STUDENT_WEB_PID_FILE="${TMP_ROOT}/candidate.identity"
  STUDENT_WEB_LAUNCH_PID_FILE="${TMP_ROOT}/candidate.launch.pid"
  STUDENT_WEB_PORT=53994
  printf '87654\n' > "${STUDENT_WEB_LAUNCH_PID_FILE}"
  process_is_alive() { return 0; }
  port_is_listening() { return 1; }
  if stop_student_web >/dev/null 2>&1; then
    fail "hashless live launch candidate was stopped"
  fi
  [[ -f "${STUDENT_WEB_LAUNCH_PID_FILE}" ]] || fail "hashless launch candidate record was removed"
)

# Explicit build refuses even a non-listening identity; it never mutates .next
# concurrently with a pending or otherwise recorded process.
(
  STUDENT_WEB_PID_FILE="${TMP_ROOT}/offline-build.identity"
  STUDENT_WEB_LAUNCH_PID_FILE="${TMP_ROOT}/offline-build.launch.pid"
  printf 'recorded\n' > "${STUDENT_WEB_PID_FILE}"
  student_web_production_build_is_current() { return 1; }
  port_is_listening() { return 1; }
  ensure_student_web_production_build() { fail "offline build ignored an existing identity"; }
  if build_student_web_production_offline >/dev/null 2>&1; then
    fail "offline build accepted an existing process identity"
  fi
)

# A bad project cwd must propagate as a failure even when the helper is called
# from an if/! conditional where Bash disables implicit errexit.
(
  STUDENT_WEB_DIR="${TMP_ROOT}/does-not-exist"
  resolve_node_bin() { printf '/usr/bin/false'; }
  if student_web_next_version >/dev/null 2>&1; then
    fail "next version helper masked a bad cwd"
  fi
  if student_web_source_fingerprint >/dev/null 2>&1; then
    fail "source fingerprint masked a bad cwd"
  fi
)

# A known legacy identity is stopped before any build, then production launch
# occurs. This protects .next from concurrent next-dev/build mutation.
(
  STUDENT_WEB_PID_FILE="${TMP_ROOT}/ordered-legacy.identity"
  STUDENT_WEB_LAUNCH_PID_FILE="${TMP_ROOT}/ordered-legacy.launch.pid"
  order_file="${TMP_ROOT}/student-start-order"
  : > "${STUDENT_WEB_PID_FILE}"
  student_web_runtime_is_healthy() { return 1; }
  port_is_listening() { return 1; }
  stop_student_web() { printf 'stop\n' >> "${order_file}"; rm -f "${STUDENT_WEB_PID_FILE}"; }
  assert_unknown_port_is_free() { return 0; }
  ensure_student_web_production_build() { printf 'build\n' >> "${order_file}"; }
  launch_student_web_production() { printf 'launch\n' >> "${order_file}"; }
  start_student_web || fail "ordered legacy migration failed"
  expected="$(printf 'stop\nbuild\nlaunch')"
  actual="$(cat "${order_file}")"
  [[ "${actual}" == "${expected}" ]] || fail "legacy migration order was ${actual}"
)

grep -Fq 'node_modules/next/dist/bin/next start' "${STACK_SCRIPT}" || fail "Student Web does not use next start"
if grep -Eq 'node_modules/next/dist/bin/next dev.*--hostname.*STUDENT_WEB_PORT' "${STACK_SCRIPT}"; then
  fail "normal Student Web launch still uses next dev"
fi
grep -Fq 'MIRA_LOCAL_LAN_PRODUCTION_MODE=1' "${STACK_SCRIPT}" || fail "local LAN production boundary is missing"

echo "local test stack Student Web production tests passed"
