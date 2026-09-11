#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${RUNTIME_ROOT}/.." && pwd)"
SOURCE_DIR="${OPENMAIC_SOURCE_DIR:-${RUNTIME_ROOT}/.runtime/OpenMAIC}"
GATEWAY_DIR="${RUNTIME_ROOT}/gateway"
LOG_DIR="${MIRA_OPENMAIC_LOG_DIR:-/tmp/mira-openmaic-runtime}"
OPENMAIC_LOG="${LOG_DIR}/openmaic.log"
GATEWAY_LOG="${LOG_DIR}/gateway.log"
OPENMAIC_PID_FILE="${LOG_DIR}/openmaic.pid"
OPENMAIC_MODE_FILE="${LOG_DIR}/openmaic.mode"
GATEWAY_PID_FILE="${LOG_DIR}/gateway.pid"
GATEWAY_IDENTITY_FILE="${LOG_DIR}/gateway.identity"
OPENMAIC_PORT="${OPENMAIC_ADMIN_PORT:-3100}"
GATEWAY_PORT="${MIRA_RUNTIME_PORT:-3101}"
OPENMAIC_URL="http://127.0.0.1:${OPENMAIC_PORT}"
GATEWAY_URL="http://127.0.0.1:${GATEWAY_PORT}"
EXPECTED_OPENMAIC_VERSION="1.0.0"
OPENMAIC_STRUCTURED_SCENE_POLICY_ID="deepseek-v4-pro-flash-v1"
OPENMAIC_RECOVERY_POLICY_VERSION="mira-sample-deterministic-classroom.v1"
OPENMAIC_RECOVERY_CANONICAL_SPEC_SHA256="879040700d374f045058b09cbf6ed6e956ebf97d8c8d9008477063458c5ef7b6"
OPENMAIC_TTS_CREDENTIAL_RECOVERY_POLICY_VERSION="mira-sample-tts-credential-recovery.v1"
OPENMAIC_TTS_CREDENTIAL_RECOVERY_CANONICAL_SPEC_SHA256="879040700d374f045058b09cbf6ed6e956ebf97d8c8d9008477063458c5ef7b6"
OPENMAIC_TTS_CREDENTIAL_RECOVERY_FIXED_PARENT_ID="omrec_383729f8f7f637dc1cdc65d4"
OPENMAIC_FORMAL_CITATION_RECOVERY_POLICY_VERSION="mira-formal-citation-recovery.v1"
OPENMAIC_FORMAL_CITATION_RECOVERY_FIXED_SOURCE_JOB_ID="omformal_e6b6986c631a548c9756037e"
OPENMAIC_QWEN_IMAGE_BASE_URL_CONTRACT="https://dashscope.aliyuncs.com"
OPENMAIC_QWEN_IMAGE_MODEL_CONTRACT="qwen-image-max"
OPENMAIC_HAPPYHORSE_BASE_URL_CONTRACT="https://dashscope.aliyuncs.com"
OPENMAIC_HAPPYHORSE_MODEL_CONTRACT="happyhorse-1.0-t2v"
HEALTH_TIMEOUT_SECONDS="${MIRA_OPENMAIC_HEALTH_TIMEOUT_SECONDS:-3}"

mkdir -p "${LOG_DIR}"

read_backend_internal_token() {
  if [[ -n "${MIRA_INTERNAL_API_TOKEN:-}" ]]; then
    printf '%s' "${MIRA_INTERNAL_API_TOKEN}"
    return 0
  fi

  local env_file="${MIRA_BACKEND_ENV_FILE:-${REPO_ROOT}/backend/.env}"
  [[ -f "${env_file}" ]] || return 1
  local line value
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ "${line}" == INTERNAL_API_TOKEN=* ]] || continue
    value="${line#*=}"
    value="${value%\"}"; value="${value#\"}"
    value="${value%\'}"; value="${value#\'}"
    [[ -n "${value}" ]] || return 1
    printf '%s' "${value}"
    return 0
  done < "${env_file}"
  return 1
}

read_env_value() {
  local key="$1"
  local env_file="$2"
  [[ -f "${env_file}" ]] || return 1
  local line value
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ "${line}" == "${key}="* ]] || continue
    value="${line#*=}"
    value="${value%\"}"; value="${value#\"}"
    value="${value%\'}"; value="${value#\'}"
    printf '%s' "${value}"
    return 0
  done < "${env_file}"
  return 1
}

provider_env_file() {
  printf '%s' "${MIRA_OPENMAIC_PROVIDER_ENV_FILE:-${MIRA_BACKEND_ENV_FILE:-${REPO_ROOT}/backend/.env}}"
}

# Model credentials belong to the OpenMAIC wrapper, not the App backend. Keep
# this path fixed so an inherited backend dotenv cannot silently supply or
# override the paid courseware-provider key.
model_provider_env_file() {
  printf '%s' "${RUNTIME_ROOT}/.env"
}

read_first_env_value() {
  local env_file="$1"
  shift
  local key value
  for key in "$@"; do
    value="$(read_env_value "${key}" "${env_file}" || true)"
    if [[ -n "${value}" ]]; then
      printf '%s' "${value}"
      return 0
    fi
  done
  return 1
}

validate_opt_in() {
  local name="$1"
  local value="$2"
  case "${value}" in
    0|1) return 0 ;;
    *)
      echo "${name} must be exactly 0 or 1." >&2
      return 1
      ;;
  esac
}

validate_credential_free_http_url() {
  local label="$1"
  local value="$2"
  local node_bin
  node_bin="$(command -v node)" || {
    echo "Node.js is required to validate ${label}." >&2
    return 1
  }
  if ! "${node_bin}" -e '
    try {
      const url = new URL(process.argv[1]);
      if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) process.exit(1);
    } catch { process.exit(1); }
  ' "${value}" >/dev/null 2>&1; then
    echo "${label} must be a credential-free HTTP(S) URL." >&2
    return 1
  fi
}

normalize_credential_free_http_origin() {
  local label="$1"
  local value="$2"
  local node_bin
  node_bin="$(command -v node)" || {
    echo "Node.js is required to validate ${label}." >&2
    return 1
  }
  if ! "${node_bin}" -e '
    try {
      const url = new URL(process.argv[1]);
      const valid =
        ["http:", "https:"].includes(url.protocol) &&
        !url.username &&
        !url.password &&
        url.pathname === "/" &&
        !url.search &&
        !url.hash;
      if (!valid) process.exit(1);
      process.stdout.write(url.origin);
    } catch { process.exit(1); }
  ' "${value}" 2>/dev/null; then
    echo "${label} must be a credential-free HTTP(S) origin without a path, query, or fragment." >&2
    return 1
  fi
}

# Runtime origins are non-secret, but launchd still must not persist a stale LAN
# address in a plist. Read only the two allowlisted keys from their server-owned
# dotenv files and validate them as origins; never source either file.
load_runtime_origin_env() {
  local backend_env_file student_web_env_file runtime_origin student_web_origin
  backend_env_file="${MIRA_BACKEND_ENV_FILE:-${REPO_ROOT}/backend/.env}"
  student_web_env_file="${MIRA_STUDENT_WEB_ENV_FILE:-${REPO_ROOT}/student-web/.env.local}"

  runtime_origin="$(read_env_value OPENMAIC_FULL_RUNTIME_PUBLIC_URL "${backend_env_file}" || true)"
  [[ -n "${runtime_origin}" ]] || {
    echo "OPENMAIC_FULL_RUNTIME_PUBLIC_URL is required in ${backend_env_file}." >&2
    return 1
  }
  student_web_origin="$(read_env_value MIRA_STUDENT_WEB_PUBLIC_URL "${student_web_env_file}" || true)"
  [[ -n "${student_web_origin}" ]] || {
    echo "MIRA_STUDENT_WEB_PUBLIC_URL is required in ${student_web_env_file}." >&2
    return 1
  }

  MIRA_RUNTIME_PUBLIC_ORIGIN="$(normalize_credential_free_http_origin OPENMAIC_FULL_RUNTIME_PUBLIC_URL "${runtime_origin}")" || return 1
  MIRA_STUDENT_WEB_ORIGIN="$(normalize_credential_free_http_origin MIRA_STUDENT_WEB_PUBLIC_URL "${student_web_origin}")" || return 1
}

clear_openmaic_provider_env() {
  OPENMAIC_DEFAULT_MODEL=""
  OPENMAIC_DEEPSEEK_API_KEY=""
  OPENMAIC_DEEPSEEK_BASE_URL=""
  OPENMAIC_DEEPSEEK_MODELS=""
  OPENMAIC_COURSEWARE_VERIFIER_MODEL=""
  OPENMAIC_AGENT_RUNTIME_ENABLED="0"
  OPENMAIC_AGENT_DATABASE_URL=""
  OPENMAIC_PERSISTENCE_DEV_TOKEN=""
  OPENMAIC_MODEL_ROUTES=""
  OPENMAIC_WEB_SEARCH_ENABLED="0"
  OPENMAIC_WEB_SEARCH_PROVIDER=""
  OPENMAIC_BRAVE_BASE_URL=""
  OPENMAIC_BRAVE_API_KEY=""
  OPENMAIC_BRAVE_ENABLED="false"
  OPENMAIC_BAIDU_BASE_URL=""
  OPENMAIC_BAIDU_API_KEY=""
  OPENMAIC_BAIDU_ENABLED="false"
  OPENMAIC_TTS_QWEN_API_KEY=""
  OPENMAIC_TTS_QWEN_BASE_URL=""
  OPENMAIC_TTS_QWEN_MODELS=""
  OPENMAIC_TTS_QWEN_VOICE=""
  OPENMAIC_REQUIRE_QWEN_TTS="0"
  OPENMAIC_ASR_QWEN_API_KEY=""
  OPENMAIC_ASR_QWEN_BASE_URL=""
  OPENMAIC_ASR_QWEN_MODELS=""
  OPENMAIC_REQUIRE_QWEN_ASR="0"
  OPENMAIC_DEFAULT_IMAGE_PROVIDER=""
  OPENMAIC_IMAGE_QWEN_IMAGE_API_KEY=""
  OPENMAIC_IMAGE_QWEN_IMAGE_BASE_URL=""
  OPENMAIC_IMAGE_QWEN_IMAGE_MODELS=""
  OPENMAIC_DEFAULT_VIDEO_PROVIDER=""
  OPENMAIC_VIDEO_HAPPYHORSE_API_KEY=""
  OPENMAIC_VIDEO_HAPPYHORSE_BASE_URL=""
  OPENMAIC_VIDEO_HAPPYHORSE_MODELS=""
}

clear_openmaic_recovery_env() {
  OPENMAIC_RECOVERY_ENABLED="0"
  OPENMAIC_RECOVERY_SOURCE_JOB_ID=""
  OPENMAIC_RECOVERY_PATCH_SHA256=""
  OPENMAIC_RECOVERY_INTERNAL_TOKEN=""
  OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED="0"
  OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID=""
  OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID=""
  OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256=""
  OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED="0"
  OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID=""
  OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256=""
}

clear_openmaic_recovery_secret() {
  OPENMAIC_RECOVERY_INTERNAL_TOKEN=""
}

clear_openmaic_internal_token() {
  OPENMAIC_INTERNAL_API_TOKEN=""
}

load_openmaic_internal_token_env() {
  local internal_token
  internal_token="$(read_backend_internal_token)" || {
    echo "Formal audio requires the backend internal API token." >&2
    return 1
  }
  OPENMAIC_INTERNAL_API_TOKEN="${internal_token}"
}

# Deterministic recovery is an exceptional, one-source control-plane action.
# It is disabled by default and reads only named values from the backend's
# server-owned dotenv. The patch digest is derived from the reviewed patch
# bytes; neither credentials nor the idempotency key are written or logged.
load_openmaic_recovery_env() {
  clear_openmaic_recovery_env
  local env_file enabled source_job_id internal_token patch_file patch_sha
  local child_enabled child_source_job_id child_parent_recovery_id child_patch_file child_patch_sha
  env_file="${MIRA_BACKEND_ENV_FILE:-${REPO_ROOT}/backend/.env}"
  enabled="${MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED:-}"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED "${env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED "${env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="0"
  validate_opt_in MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED "${enabled}" || return 1
  child_enabled="${MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED:-}"
  [[ -n "${child_enabled}" ]] || child_enabled="$(read_env_value MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED "${env_file}" || true)"
  [[ -n "${child_enabled}" ]] || child_enabled="$(read_env_value OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED "${env_file}" || true)"
  [[ -n "${child_enabled}" ]] || child_enabled="0"
  validate_opt_in MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED "${child_enabled}" || return 1
  if [[ "${enabled}" != "1" ]]; then
    [[ "${child_enabled}" != "1" ]] || {
      echo "TTS credential recovery requires the parent deterministic recovery gate." >&2
      return 1
    }
    return 0
  fi

  [[ "${OPENMAIC_REQUIRE_QWEN_TTS}" == "1" ]] || {
    echo "Deterministic recovery requires the strict Qwen3-TTS opt-in." >&2
    return 1
  }
  source_job_id="${MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_SOURCE_JOB_ID:-}"
  [[ -n "${source_job_id}" ]] || source_job_id="$(read_env_value MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_SOURCE_JOB_ID "${env_file}" || true)"
  [[ -n "${source_job_id}" ]] || source_job_id="$(read_env_value OPENMAIC_DETERMINISTIC_RECOVERY_SOURCE_JOB_ID "${env_file}" || true)"
  [[ "${source_job_id}" == "uKQl3vMr4d" ]] || {
    echo "Deterministic recovery source must be the reviewed failed third job." >&2
    return 1
  }
  internal_token="$(read_backend_internal_token)" || {
    echo "Deterministic recovery requires the backend internal API token." >&2
    return 1
  }
  patch_file="${RUNTIME_ROOT}/patches/0007-mira-sample-deterministic-recovery.patch"
  [[ -f "${patch_file}" ]] || {
    echo "Deterministic recovery patch 0007 is missing." >&2
    return 1
  }
  patch_sha="$(shasum -a 256 "${patch_file}" | awk '{print $1}')"
  [[ "${patch_sha}" =~ ^[a-f0-9]{64}$ ]] || {
    echo "Deterministic recovery patch checksum is invalid." >&2
    return 1
  }

  OPENMAIC_RECOVERY_ENABLED="1"
  OPENMAIC_RECOVERY_SOURCE_JOB_ID="${source_job_id}"
  OPENMAIC_RECOVERY_PATCH_SHA256="${patch_sha}"
  OPENMAIC_RECOVERY_INTERNAL_TOKEN="${internal_token}"

  [[ "${child_enabled}" == "1" ]] || return 0
  child_source_job_id="${MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID:-}"
  [[ -n "${child_source_job_id}" ]] || child_source_job_id="$(read_env_value MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID "${env_file}" || true)"
  [[ -n "${child_source_job_id}" ]] || child_source_job_id="$(read_env_value OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID "${env_file}" || true)"
  [[ "${child_source_job_id}" == "uKQl3vMr4d" ]] || {
    echo "TTS credential recovery source must be the reviewed failed third job." >&2
    return 1
  }
  child_parent_recovery_id="${MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID:-}"
  [[ -n "${child_parent_recovery_id}" ]] || child_parent_recovery_id="$(read_env_value MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID "${env_file}" || true)"
  [[ -n "${child_parent_recovery_id}" ]] || child_parent_recovery_id="$(read_env_value OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID "${env_file}" || true)"
  [[ "${child_parent_recovery_id}" == "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_FIXED_PARENT_ID}" ]] || {
    echo "TTS credential recovery parent must be the reviewed failed runtime recovery." >&2
    return 1
  }
  child_patch_file="${RUNTIME_ROOT}/patches/0008-mira-sample-tts-credential-recovery.patch"
  [[ -f "${child_patch_file}" ]] || {
    echo "TTS credential recovery patch 0008 is missing." >&2
    return 1
  }
  child_patch_sha="$(shasum -a 256 "${child_patch_file}" | awk '{print $1}')"
  [[ "${child_patch_sha}" =~ ^[a-f0-9]{64}$ ]] || {
    echo "TTS credential recovery patch checksum is invalid." >&2
    return 1
  }
  OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED="1"
  OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID="${child_source_job_id}"
  OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID="${child_parent_recovery_id}"
  OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256="${child_patch_sha}"
}

# A formal citation recovery never re-enters the Agent or web-search path. It
# is a one-source, loopback-only continuation of an already-succeeded Agent
# session whose original job stopped at the exact citation gate. The reviewed
# patch hash and source id are passed into the isolated Next process so the
# route can freeze both in its durable sidecar receipt.
load_openmaic_formal_citation_recovery_env() {
  OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED="0"
  OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID=""
  OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256=""

  local env_file enabled source_job_id patch_file patch_sha
  env_file="${MIRA_BACKEND_ENV_FILE:-${REPO_ROOT}/backend/.env}"
  enabled="${MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED:-}"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED "${env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED "${env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="0"
  validate_opt_in MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED "${enabled}" || return 1
  [[ "${enabled}" == "1" ]] || return 0

  source_job_id="${MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID:-}"
  [[ -n "${source_job_id}" ]] || source_job_id="$(read_env_value MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID "${env_file}" || true)"
  [[ -n "${source_job_id}" ]] || source_job_id="$(read_env_value OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID "${env_file}" || true)"
  [[ "${source_job_id}" == "${OPENMAIC_FORMAL_CITATION_RECOVERY_FIXED_SOURCE_JOB_ID}" ]] || {
    echo "Formal citation recovery source must be the reviewed failed formal job." >&2
    return 1
  }
  patch_file="${RUNTIME_ROOT}/patches/0043-mira-formal-citation-recovery.patch"
  [[ -f "${patch_file}" ]] || {
    echo "Formal citation recovery patch 0043 is missing." >&2
    return 1
  }
  patch_sha="$(shasum -a 256 "${patch_file}" | awk '{print $1}')"
  [[ "${patch_sha}" =~ ^[a-f0-9]{64}$ ]] || {
    echo "Formal citation recovery patch checksum is invalid." >&2
    return 1
  }

  OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED="1"
  OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID="${source_job_id}"
  OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256="${patch_sha}"
}

# Provider credentials are deliberately excluded from the default native
# runtime. A trusted operator must opt in to each capability for every process
# start. Values are read without sourcing dotenv and are passed only to the
# private OpenMAIC process. Scalar slots intentionally replace optional arrays:
# Bash 3.2 treats an empty-array expansion as an unbound variable under `set -u`.
clear_openmaic_provider_env
clear_openmaic_recovery_env
clear_openmaic_internal_token

load_openmaic_model_env() {
  OPENMAIC_DEFAULT_MODEL=""
  OPENMAIC_DEEPSEEK_API_KEY=""
  OPENMAIC_DEEPSEEK_BASE_URL=""
  OPENMAIC_DEEPSEEK_MODELS=""
  OPENMAIC_COURSEWARE_VERIFIER_MODEL=""

  local enabled env_file provider model verifier_model api_key base_url configured_models normalized_models service
  env_file="$(model_provider_env_file)"
  enabled="${MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER:-}"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER "${env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="0"
  validate_opt_in MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER "${enabled}" || return 1
  [[ "${enabled}" == "1" ]] || return 0

  provider="${MIRA_OPENMAIC_MODEL_PROVIDER:-}"
  [[ -n "${provider}" ]] || provider="$(read_env_value MIRA_OPENMAIC_MODEL_PROVIDER "${env_file}" || true)"
  provider="$(printf '%s' "${provider}" | tr '[:upper:]' '[:lower:]')"

  case "${provider}" in
    deepseek)
      model="${MIRA_OPENMAIC_MODEL:-}"
      [[ -n "${model}" ]] || model="$(read_env_value MIRA_OPENMAIC_MODEL "${env_file}" || true)"
      verifier_model="${MIRA_OPENMAIC_VERIFIER_MODEL:-}"
      [[ -n "${verifier_model}" ]] || verifier_model="$(read_env_value MIRA_OPENMAIC_VERIFIER_MODEL "${env_file}" || true)"
      api_key="$(read_env_value DEEPSEEK_API_KEY "${env_file}" || true)"
      base_url="$(read_env_value DEEPSEEK_BASE_URL "${env_file}" || true)"
      [[ -n "${base_url}" ]] || base_url="https://api.deepseek.com/v1"
      service="$(read_env_value DEEPSEEK_SERVICE "${env_file}" || true)"
      case "${service:-official}" in
        official) ;;
        bailian)
          api_key="$(read_env_value BAILIAN_DEEPSEEK_API_KEY "${env_file}" || true)"
          base_url="$(read_env_value BAILIAN_DEEPSEEK_BASE_URL "${env_file}" || true)"
          [[ -n "${base_url}" ]] || base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
          # Only the reviewed Beijing pay-as-you-go service is eligible for
          # this free-quota profile; never send its key to a custom endpoint.
          if ! node -e '
            const u = new URL(process.argv[1]);
            const host = u.hostname === "dashscope.aliyuncs.com" || /^[a-z0-9-]+\.cn-beijing\.maas\.aliyuncs\.com$/.test(u.hostname);
            process.exit(u.protocol === "https:" && host && !u.username && !u.password && !u.port && !u.search && !u.hash && /^\/compatible-mode\/v1\/?$/.test(u.pathname) ? 0 : 1);
          ' "${base_url}"; then
            echo "BAILIAN_DEEPSEEK_BASE_URL must be a Beijing pay-as-you-go compatible endpoint." >&2
            return 1
          fi
          [[ "$(read_env_value BAILIAN_DEEPSEEK_FREE_TIER_ONLY_CONFIRMED "${env_file}" || true)" == "1" ]] || {
            echo "Enable free-quota-only for Pro 0813 and Flash 0731 in the console before selecting Bailian." >&2
            return 1
          }
          ;;
        *) echo "DEEPSEEK_SERVICE must be official or bailian." >&2; return 1 ;;
      esac
      configured_models="$(read_env_value DEEPSEEK_MODELS "${env_file}" || true)"
      [[ -n "${model}" && -n "${verifier_model}" && -n "${api_key}" ]] || {
        echo "OpenMAIC DeepSeek mode requires MIRA_OPENMAIC_MODEL, MIRA_OPENMAIC_VERIFIER_MODEL, and DEEPSEEK_API_KEY in ${env_file}." >&2
        return 1
      }
      [[ "${model}" == "deepseek-v4-pro" ]] || {
        echo "OpenMAIC professional creation requires deepseek-v4-pro." >&2
        return 1
      }
      [[ "${verifier_model}" == "deepseek-v4-flash" ]] || {
        echo "OpenMAIC independent verification requires deepseek-v4-flash." >&2
        return 1
      }
      normalized_models="$(printf '%s' "${configured_models}" | tr -d '[:space:]')"
      [[ -n "${normalized_models}" ]] || normalized_models="${model},${verifier_model}"
      case ",${normalized_models}," in
        *",${model},"*) ;;
        *) echo "DEEPSEEK_MODELS must include ${model}." >&2; return 1 ;;
      esac
      case ",${normalized_models}," in
        *",${verifier_model},"*) ;;
        *) echo "DEEPSEEK_MODELS must include ${verifier_model}." >&2; return 1 ;;
      esac
      validate_credential_free_http_url DEEPSEEK_BASE_URL "${base_url}" || return 1
      OPENMAIC_DEFAULT_MODEL="deepseek:${model}"
      OPENMAIC_DEEPSEEK_API_KEY="${api_key}"
      OPENMAIC_DEEPSEEK_BASE_URL="${base_url}"
      OPENMAIC_DEEPSEEK_MODELS="${normalized_models}"
      OPENMAIC_COURSEWARE_VERIFIER_MODEL="${verifier_model}"
      ;;
    *)
      echo "Native OpenMAIC professional courseware accepts only the server-owned DeepSeek provider." >&2
      return 1
      ;;
  esac
}

validate_postgresql_database_url() {
  local label="$1"
  local value="$2"
  local node_bin
  node_bin="$(command -v node)" || {
    echo "Node.js is required to validate ${label}." >&2
    return 1
  }
  if ! "${node_bin}" -e '
    try {
      const url = new URL(process.argv[1]);
      const valid =
        ["postgres:", "postgresql:"].includes(url.protocol) &&
        Boolean(url.hostname) &&
        url.pathname.length > 1 &&
        !url.hash;
      if (!valid) process.exit(1);
    } catch { process.exit(1); }
  ' "${value}" >/dev/null 2>&1; then
    echo "${label} must be a PostgreSQL URL with a host and database name." >&2
    return 1
  fi
}

# Professional generation is a durable, server-owned Agent Runtime. Its
# connection URL is read without sourcing dotenv, never logged, and crosses
# only the clean OpenMAIC child-process boundary. The driver route is locked to
# the reviewed DeepSeek Pro model used for professional courseware creation.
load_openmaic_agent_runtime_env() {
  OPENMAIC_AGENT_RUNTIME_ENABLED="0"
  OPENMAIC_AGENT_DATABASE_URL=""
  OPENMAIC_PERSISTENCE_DEV_TOKEN=""
  OPENMAIC_MODEL_ROUTES=""

  local env_file enabled database_url
  env_file="$(provider_env_file)"
  enabled="${MIRA_OPENMAIC_AGENT_RUNTIME_ENABLED:-}"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value MIRA_OPENMAIC_AGENT_RUNTIME_ENABLED "${env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="0"
  validate_opt_in MIRA_OPENMAIC_AGENT_RUNTIME_ENABLED "${enabled}" || return 1
  [[ "${enabled}" == "1" ]] || return 0

  [[ "${OPENMAIC_DEFAULT_MODEL}" == "deepseek:deepseek-v4-pro" ]] || {
    echo "Professional Agent Runtime requires the reviewed deepseek-v4-pro model provider." >&2
    return 1
  }
  database_url="${MIRA_OPENMAIC_AGENT_DATABASE_URL:-${DATABASE_URL:-}}"
  [[ -n "${database_url}" ]] || database_url="$(read_env_value MIRA_OPENMAIC_AGENT_DATABASE_URL "${env_file}" || true)"
  [[ -n "${database_url}" ]] || database_url="$(read_env_value DATABASE_URL "${env_file}" || true)"
  [[ -n "${database_url}" ]] || {
    echo "MIRA_OPENMAIC_AGENT_DATABASE_URL (or DATABASE_URL) is required for professional Agent Runtime." >&2
    return 1
  }
  validate_postgresql_database_url MIRA_OPENMAIC_AGENT_DATABASE_URL "${database_url}" || return 1

  OPENMAIC_AGENT_RUNTIME_ENABLED="1"
  OPENMAIC_AGENT_DATABASE_URL="${database_url}"
  # Upstream persistence requires a server token even for its owner-cookie
  # document branch. Keep it private and process-local: authoring never sends
  # this token and learner/runtime persistence remains disabled in the browser.
  OPENMAIC_PERSISTENCE_DEV_TOKEN="$(node -e 'process.stdout.write(require("node:crypto").randomBytes(32).toString("hex"))')"
  OPENMAIC_MODEL_ROUTES='{"maic-agent-driver":{"model":"deepseek:deepseek-v4-pro","api":"openai-completions","thinking":{"mode":"enabled","enabled":true}},"generate-classroom":{"model":"deepseek:deepseek-v4-pro","thinking":{"mode":"disabled","enabled":false}},"mira-courseware-creator":{"model":"deepseek:deepseek-v4-pro","thinking":{"mode":"disabled","enabled":false}},"mira-courseware-verifier":{"model":"deepseek:deepseek-v4-flash","thinking":{"mode":"disabled","enabled":false}},"web-search-query-rewrite":{"model":"deepseek:deepseek-v4-pro","thinking":{"mode":"disabled","enabled":false}}}'
}

# Search credentials and the selected provider belong to OpenMAIC. The legacy
# backend switch remains a fallback for existing installations only.
load_openmaic_web_search_env() {
  OPENMAIC_WEB_SEARCH_ENABLED="0"
  OPENMAIC_WEB_SEARCH_PROVIDER=""
  OPENMAIC_BRAVE_BASE_URL=""
  OPENMAIC_BRAVE_API_KEY=""
  OPENMAIC_BRAVE_ENABLED="false"
  OPENMAIC_BAIDU_BASE_URL=""
  OPENMAIC_BAIDU_API_KEY=""
  OPENMAIC_BAIDU_ENABLED="false"

  local env_file own_env_file enabled provider base_url api_key
  env_file="$(provider_env_file)"
  own_env_file="$(model_provider_env_file)"
  enabled="${MIRA_OPENMAIC_ENABLE_WEB_SEARCH:-}"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value MIRA_OPENMAIC_ENABLE_WEB_SEARCH "${own_env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value MIRA_OPENMAIC_ENABLE_WEB_SEARCH "${env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="0"
  validate_opt_in MIRA_OPENMAIC_ENABLE_WEB_SEARCH "${enabled}" || return 1
  [[ "${enabled}" == "1" ]] || return 0

  provider="${MIRA_OPENMAIC_WEB_SEARCH_PROVIDER:-}"
  [[ -n "${provider}" ]] || provider="$(read_env_value MIRA_OPENMAIC_WEB_SEARCH_PROVIDER "${own_env_file}" || true)"
  [[ -n "${provider}" ]] || provider="$(read_env_value MIRA_OPENMAIC_WEB_SEARCH_PROVIDER "${env_file}" || true)"
  [[ -n "${provider}" ]] || provider="brave"
  provider="$(printf '%s' "${provider}" | tr '[:upper:]' '[:lower:]')"
  [[ "${provider}" == "brave" || "${provider}" == "baidu" ]] || {
    echo "Professional courseware requires the server-managed brave or baidu search provider." >&2
    return 1
  }

  if [[ "${provider}" == "baidu" ]]; then
    base_url="${MIRA_OPENMAIC_BAIDU_BASE_URL:-${BAIDU_BASE_URL:-}}"
    [[ -n "${base_url}" ]] || base_url="$(read_env_value BAIDU_BASE_URL "${own_env_file}" || true)"
    [[ -n "${base_url}" ]] || base_url="https://qianfan.baidubce.com"
    base_url="$(normalize_credential_free_http_origin BAIDU_BASE_URL "${base_url}")" || return 1
    [[ "${base_url}" == "https://qianfan.baidubce.com" ]] || {
      echo "BAIDU_BASE_URL must be the official https://qianfan.baidubce.com origin." >&2
      return 1
    }
    api_key="${MIRA_OPENMAIC_BAIDU_API_KEY:-${BAIDU_API_KEY:-}}"
    [[ -n "${api_key}" ]] || api_key="$(read_env_value BAIDU_API_KEY "${own_env_file}" || true)"
    if [[ -n "${api_key}" && ( "${api_key}" == *$'\n'* || "${api_key}" == *$'\r'* || "${api_key}" == *' '* || "${api_key}" == *$'\t'* ) ]]; then
      echo "BAIDU_API_KEY must be a single credential without whitespace." >&2
      return 1
    fi
    OPENMAIC_WEB_SEARCH_ENABLED="1"
    OPENMAIC_WEB_SEARCH_PROVIDER="baidu"
    OPENMAIC_BAIDU_BASE_URL="${base_url}"
    OPENMAIC_BAIDU_API_KEY="${api_key}"
    OPENMAIC_BAIDU_ENABLED="true"
    return 0
  fi

  base_url="${MIRA_OPENMAIC_BRAVE_BASE_URL:-${BRAVE_BASE_URL:-}}"
  [[ -n "${base_url}" ]] || base_url="$(read_env_value BRAVE_BASE_URL "${own_env_file}" || true)"
  [[ -n "${base_url}" ]] || base_url="$(read_env_value MIRA_OPENMAIC_BRAVE_BASE_URL "${env_file}" || true)"
  [[ -n "${base_url}" ]] || base_url="$(read_env_value BRAVE_BASE_URL "${env_file}" || true)"
  [[ -n "${base_url}" ]] || base_url="https://search.brave.com"
  base_url="$(normalize_credential_free_http_origin BRAVE_BASE_URL "${base_url}")" || return 1
  [[ "${base_url}" == "https://search.brave.com" ]] || {
    echo "BRAVE_BASE_URL must be the official https://search.brave.com origin." >&2
    return 1
  }

  # Keep search credentials with OpenMAIC, never in a client or the App API.
  api_key="${MIRA_OPENMAIC_BRAVE_API_KEY:-${BRAVE_API_KEY:-}}"
  [[ -n "${api_key}" ]] || api_key="$(read_env_value BRAVE_API_KEY "$(model_provider_env_file)" || true)"
  if [[ -n "${api_key}" && ( "${api_key}" == *$'\n'* || "${api_key}" == *$'\r'* || "${api_key}" == *' '* || "${api_key}" == *$'\t'* ) ]]; then
    echo "BRAVE_API_KEY must be a single credential without whitespace." >&2
    return 1
  fi

  OPENMAIC_WEB_SEARCH_ENABLED="1"
  OPENMAIC_WEB_SEARCH_PROVIDER="brave"
  OPENMAIC_BRAVE_BASE_URL="${base_url}"
  OPENMAIC_BRAVE_API_KEY="${api_key}"
  OPENMAIC_BRAVE_ENABLED="true"
}

load_openmaic_qwen_tts_env() {
  OPENMAIC_TTS_QWEN_API_KEY=""
  OPENMAIC_TTS_QWEN_BASE_URL=""
  OPENMAIC_TTS_QWEN_MODELS=""
  OPENMAIC_TTS_QWEN_VOICE=""
  OPENMAIC_REQUIRE_QWEN_TTS="0"

  local enabled env_file
  env_file="$(provider_env_file)"
  enabled="${MIRA_OPENMAIC_ENABLE_QWEN_TTS:-}"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value MIRA_OPENMAIC_ENABLE_QWEN_TTS "${env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="0"
  validate_opt_in MIRA_OPENMAIC_ENABLE_QWEN_TTS "${enabled}" || return 1
  [[ "${enabled}" == "1" ]] || return 0

  local api_key base_url model voice
  api_key="${MIRA_OPENMAIC_QWEN_TTS_API_KEY:-${TTS_QWEN_API_KEY:-${MIRA_OPENMAIC_QWEN_API_KEY:-${DASHSCOPE_API_KEY:-${QWEN_API_KEY:-}}}}}"
  [[ -n "${api_key}" ]] || api_key="$(read_first_env_value "${env_file}" TTS_QWEN_API_KEY DASHSCOPE_API_KEY QWEN_API_KEY || true)"
  [[ -n "${api_key}" ]] || {
    echo "Qwen3-TTS opt-in requires MIRA_OPENMAIC_QWEN_TTS_API_KEY, MIRA_OPENMAIC_QWEN_API_KEY, or TTS_QWEN_API_KEY/DASHSCOPE_API_KEY/QWEN_API_KEY in ${env_file}." >&2
    return 1
  }

  base_url="${MIRA_OPENMAIC_QWEN_TTS_BASE_URL:-${TTS_QWEN_BASE_URL:-}}"
  [[ -n "${base_url}" ]] || base_url="$(read_first_env_value "${env_file}" TTS_QWEN_BASE_URL DASHSCOPE_BASE_URL || true)"
  [[ -n "${base_url}" ]] || base_url="https://dashscope.aliyuncs.com/api/v1"
  validate_credential_free_http_url TTS_QWEN_BASE_URL "${base_url}" || return 1

  model="${MIRA_OPENMAIC_QWEN_TTS_MODEL:-qwen3-tts-flash}"
  case "${model}" in
    qwen3-tts-flash) ;;
    *)
      echo "MIRA_OPENMAIC_QWEN_TTS_MODEL must be qwen3-tts-flash for the Mira classroom contract." >&2
      return 1
      ;;
  esac

  voice="${MIRA_OPENMAIC_QWEN_TTS_VOICE:-Serena}"
  case "${voice}" in
    Serena) ;;
    *)
      echo "MIRA_OPENMAIC_QWEN_TTS_VOICE must be Serena for the Mira classroom contract." >&2
      return 1
      ;;
  esac

  OPENMAIC_TTS_QWEN_API_KEY="${api_key}"
  OPENMAIC_TTS_QWEN_BASE_URL="${base_url}"
  OPENMAIC_TTS_QWEN_MODELS="${model}"
  OPENMAIC_TTS_QWEN_VOICE="${voice}"
  OPENMAIC_REQUIRE_QWEN_TTS="1"
}

load_openmaic_qwen_asr_env() {
  OPENMAIC_ASR_QWEN_API_KEY=""
  OPENMAIC_ASR_QWEN_BASE_URL=""
  OPENMAIC_ASR_QWEN_MODELS=""
  OPENMAIC_REQUIRE_QWEN_ASR="0"

  local enabled env_file
  env_file="$(provider_env_file)"
  enabled="${MIRA_OPENMAIC_ENABLE_QWEN_ASR:-}"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value MIRA_OPENMAIC_ENABLE_QWEN_ASR "${env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="0"
  validate_opt_in MIRA_OPENMAIC_ENABLE_QWEN_ASR "${enabled}" || return 1
  [[ "${enabled}" == "1" ]] || return 0

  local api_key base_url model
  api_key="${MIRA_OPENMAIC_QWEN_ASR_API_KEY:-${ASR_QWEN_API_KEY:-${MIRA_OPENMAIC_QWEN_API_KEY:-${DASHSCOPE_API_KEY:-${QWEN_API_KEY:-}}}}}"
  [[ -n "${api_key}" ]] || api_key="$(read_first_env_value "${env_file}" ASR_QWEN_API_KEY DASHSCOPE_API_KEY QWEN_API_KEY || true)"
  [[ -n "${api_key}" ]] || {
    echo "Qwen ASR opt-in requires MIRA_OPENMAIC_QWEN_ASR_API_KEY, MIRA_OPENMAIC_QWEN_API_KEY, or ASR_QWEN_API_KEY/DASHSCOPE_API_KEY/QWEN_API_KEY in ${env_file}." >&2
    return 1
  }

  base_url="${MIRA_OPENMAIC_QWEN_ASR_BASE_URL:-${ASR_QWEN_BASE_URL:-}}"
  [[ -n "${base_url}" ]] || base_url="$(read_first_env_value "${env_file}" ASR_QWEN_BASE_URL DASHSCOPE_BASE_URL || true)"
  [[ -n "${base_url}" ]] || base_url="https://dashscope.aliyuncs.com/api/v1"
  validate_credential_free_http_url ASR_QWEN_BASE_URL "${base_url}" || return 1

  model="${MIRA_OPENMAIC_QWEN_ASR_MODEL:-qwen3-asr-flash}"
  [[ "${model}" == "qwen3-asr-flash" ]] || {
    echo "MIRA_OPENMAIC_QWEN_ASR_MODEL must be qwen3-asr-flash for OpenMAIC 1.0.0." >&2
    return 1
  }

  OPENMAIC_ASR_QWEN_API_KEY="${api_key}"
  OPENMAIC_ASR_QWEN_BASE_URL="${base_url}"
  OPENMAIC_ASR_QWEN_MODELS="${model}"
  OPENMAIC_REQUIRE_QWEN_ASR="1"
}

# Image generation has its own explicit billing opt-in. Reuse of an existing
# server-side DashScope key is permitted, but TTS/ASR enablement never turns
# image generation on implicitly. The endpoint and model are contract-owned so
# neither a client nor an inherited shell variable can redirect image traffic.
load_openmaic_qwen_image_env() {
  OPENMAIC_DEFAULT_IMAGE_PROVIDER=""
  OPENMAIC_IMAGE_QWEN_IMAGE_API_KEY=""
  OPENMAIC_IMAGE_QWEN_IMAGE_BASE_URL=""
  OPENMAIC_IMAGE_QWEN_IMAGE_MODELS=""

  local enabled env_file api_key
  env_file="$(provider_env_file)"
  enabled="${MIRA_OPENMAIC_ENABLE_QWEN_IMAGE:-}"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value MIRA_OPENMAIC_ENABLE_QWEN_IMAGE "${env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="0"
  validate_opt_in MIRA_OPENMAIC_ENABLE_QWEN_IMAGE "${enabled}" || return 1
  [[ "${enabled}" == "1" ]] || return 0

  api_key="${IMAGE_QWEN_IMAGE_API_KEY:-${MIRA_OPENMAIC_QWEN_IMAGE_API_KEY:-${DASHSCOPE_API_KEY:-${QWEN_API_KEY:-}}}}"
  [[ -n "${api_key}" ]] || api_key="$(read_first_env_value "${env_file}" IMAGE_QWEN_IMAGE_API_KEY DASHSCOPE_API_KEY QWEN_API_KEY || true)"
  [[ -n "${api_key}" ]] || {
    echo "Qwen Image opt-in requires IMAGE_QWEN_IMAGE_API_KEY or DASHSCOPE_API_KEY/QWEN_API_KEY in ${env_file}." >&2
    return 1
  }

  OPENMAIC_DEFAULT_IMAGE_PROVIDER="qwen-image"
  OPENMAIC_IMAGE_QWEN_IMAGE_API_KEY="${api_key}"
  OPENMAIC_IMAGE_QWEN_IMAGE_BASE_URL="${OPENMAIC_QWEN_IMAGE_BASE_URL_CONTRACT}"
  OPENMAIC_IMAGE_QWEN_IMAGE_MODELS="${OPENMAIC_QWEN_IMAGE_MODEL_CONTRACT}"
}

# Video is independently enabled by the operator. The existing server-owned
# DashScope key may be reused, while model and endpoint stay contract-owned.
load_openmaic_happyhorse_env() {
  OPENMAIC_DEFAULT_VIDEO_PROVIDER=""
  OPENMAIC_VIDEO_HAPPYHORSE_API_KEY=""
  OPENMAIC_VIDEO_HAPPYHORSE_BASE_URL=""
  OPENMAIC_VIDEO_HAPPYHORSE_MODELS=""
  local enabled env_file runtime_env_file api_key
  env_file="$(provider_env_file)"
  runtime_env_file="$(model_provider_env_file)"
  enabled="${MIRA_OPENMAIC_ENABLE_HAPPYHORSE_VIDEO:-}"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value MIRA_OPENMAIC_ENABLE_HAPPYHORSE_VIDEO "${runtime_env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="$(read_env_value MIRA_OPENMAIC_ENABLE_HAPPYHORSE_VIDEO "${env_file}" || true)"
  [[ -n "${enabled}" ]] || enabled="0"
  validate_opt_in MIRA_OPENMAIC_ENABLE_HAPPYHORSE_VIDEO "${enabled}" || return 1
  [[ "${enabled}" == "1" ]] || return 0
  api_key="${VIDEO_HAPPYHORSE_API_KEY:-${DASHSCOPE_API_KEY:-${QWEN_API_KEY:-}}}"
  [[ -n "${api_key}" ]] || api_key="$(read_first_env_value "${runtime_env_file}" VIDEO_HAPPYHORSE_API_KEY DASHSCOPE_API_KEY QWEN_API_KEY || true)"
  [[ -n "${api_key}" ]] || api_key="$(read_first_env_value "${env_file}" VIDEO_HAPPYHORSE_API_KEY DASHSCOPE_API_KEY QWEN_API_KEY IMAGE_QWEN_IMAGE_API_KEY || true)"
  [[ -n "${api_key}" ]] || {
    echo "HappyHorse video requires a server-owned Beijing DashScope API key." >&2
    return 1
  }
  OPENMAIC_DEFAULT_VIDEO_PROVIDER="happyhorse"
  OPENMAIC_VIDEO_HAPPYHORSE_API_KEY="${api_key}"
  OPENMAIC_VIDEO_HAPPYHORSE_BASE_URL="${OPENMAIC_HAPPYHORSE_BASE_URL_CONTRACT}"
  OPENMAIC_VIDEO_HAPPYHORSE_MODELS="${OPENMAIC_HAPPYHORSE_MODEL_CONTRACT}"
}

load_openmaic_provider_env() {
  clear_openmaic_provider_env
  load_openmaic_model_env || { clear_openmaic_provider_env; return 1; }
  load_openmaic_agent_runtime_env || { clear_openmaic_provider_env; return 1; }
  load_openmaic_web_search_env || { clear_openmaic_provider_env; return 1; }
  load_openmaic_qwen_tts_env || { clear_openmaic_provider_env; return 1; }
  load_openmaic_qwen_asr_env || { clear_openmaic_provider_env; return 1; }
  load_openmaic_qwen_image_env || { clear_openmaic_provider_env; return 1; }
  load_openmaic_happyhorse_env || { clear_openmaic_provider_env; return 1; }
}

show_provider_status() {
  load_openmaic_provider_env || return 1
  if [[ -n "${OPENMAIC_DEFAULT_MODEL}" ]]; then
    echo "LLM: enabled (deepseek, ${OPENMAIC_DEEPSEEK_MODELS})"
    local model_service
    model_service="$(read_env_value DEEPSEEK_SERVICE "$(model_provider_env_file)" || true)"
    echo "LLM service: ${model_service:-official} (no automatic fallback)"
    if [[ "${model_service}" == "bailian" ]]; then
      echo "LLM wire models: deepseek-v4-pro-0813,deepseek-v4-flash-0731"
    fi
    echo "LLM professional creation: DeepSeek V4 Pro"
    echo "LLM independent verification: ${OPENMAIC_COURSEWARE_VERIFIER_MODEL}"
    echo "LLM structured scenes: enforced (DeepSeek V4 Pro thinking disabled)"
  else
    echo "LLM: disabled (set MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1 to opt in)"
  fi
  if [[ "${OPENMAIC_AGENT_RUNTIME_ENABLED}" == "1" ]]; then
    echo "Agent Runtime: enabled (PostgreSQL connection configured; URL redacted)"
    echo "Agent driver: deepseek:deepseek-v4-pro (openai-completions, high thinking)"
  else
    echo "Agent Runtime: disabled (set MIRA_OPENMAIC_AGENT_RUNTIME_ENABLED=1 to opt in)"
  fi
  if [[ "${OPENMAIC_WEB_SEARCH_ENABLED}" == "1" ]]; then
    if [[ "${OPENMAIC_WEB_SEARCH_PROVIDER}" == "baidu" ]]; then
      if [[ -n "${OPENMAIC_BAIDU_API_KEY}" ]]; then
        echo "Web search: Baidu official API (server credential configured; connectivity not checked)"
      else
        echo "Web search: Baidu selected, API key missing (formal production blocked)"
      fi
    elif [[ -n "${OPENMAIC_BRAVE_API_KEY}" ]]; then
      echo "Web search: Brave official API (server credential configured; connectivity not checked)"
    else
      echo "Web search: Brave public HTML (formal production blocked without API key)"
    fi
  else
    echo "Web search: disabled"
  fi
  if [[ -n "${OPENMAIC_TTS_QWEN_API_KEY}" ]]; then
    echo "TTS: enabled (qwen-tts, ${OPENMAIC_TTS_QWEN_MODELS}, voice=${OPENMAIC_TTS_QWEN_VOICE})"
  else
    echo "TTS: disabled (set MIRA_OPENMAIC_ENABLE_QWEN_TTS=1 to opt in)"
  fi
  if [[ -n "${OPENMAIC_ASR_QWEN_API_KEY}" ]]; then
    echo "ASR: enabled (qwen-asr, ${OPENMAIC_ASR_QWEN_MODELS})"
  else
    echo "ASR: no server provider (OpenMAIC browser-native ASR may still be available client-side)"
  fi
  if [[ -n "${OPENMAIC_IMAGE_QWEN_IMAGE_API_KEY}" ]]; then
    echo "Image: enabled (qwen-image, ${OPENMAIC_IMAGE_QWEN_IMAGE_MODELS})"
  else
    echo "Image: disabled (set MIRA_OPENMAIC_ENABLE_QWEN_IMAGE=1 to opt in)"
  fi
  if [[ -n "${OPENMAIC_VIDEO_HAPPYHORSE_API_KEY}" ]]; then
    echo "Video: enabled (happyhorse, ${OPENMAIC_VIDEO_HAPPYHORSE_MODELS})"
  else
    echo "Video: disabled (set MIRA_OPENMAIC_ENABLE_HAPPYHORSE_VIDEO=1 to opt in)"
  fi
  clear_openmaic_provider_env
}

pid_is_running() {
  local pid_file="$1"
  [[ -f "${pid_file}" ]] || return 1
  local pid
  pid="$(tr -cd '0-9' < "${pid_file}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

hash_text() {
  shasum -a 256 | awk '{print $1}'
}

process_start_hash() {
  local pid="$1"
  local started
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

openmaic_build_id_hash() {
  [[ -s "${SOURCE_DIR}/.next/BUILD_ID" ]] || return 1
  shasum -a 256 "${SOURCE_DIR}/.next/BUILD_ID" | awk '{print $1}'
}

openmaic_next_version() {
  local node_bin next_version
  node_bin="$(command -v node)" || return 1
  next_version="$(cd "${SOURCE_DIR}" && "${node_bin}" -p 'require("./node_modules/next/package.json").version' 2>/dev/null)" || return 1
  [[ "${next_version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([+-][A-Za-z0-9._-]+)?$ ]] || return 1
  printf '%s' "${next_version}"
}

openmaic_production_command_token() {
  local next_version="${1:-}"
  [[ -n "${next_version}" ]] || next_version="$(openmaic_next_version)" || return 1
  printf 'next-server (v%s)' "${next_version}"
}

write_openmaic_mode() {
  local pid="$1"
  local start_hash="$2"
  local build_id_sha256="$3"
  local next_version="$4"
  local mode="${5:-production}"
  [[ "${mode}" == "pending" || "${mode}" == "production" ]] || return 1
  local tmp_file="${OPENMAIC_MODE_FILE}.tmp.$$"
  umask 077
  {
    printf 'version=2\n'
    printf 'service=openmaic\n'
    printf 'mode=%s\n' "${mode}"
    printf 'pid=%s\n' "${pid}"
    printf 'start_hash=%s\n' "${start_hash}"
    printf 'next_version=%s\n' "${next_version}"
    printf 'build_id_sha256=%s\n' "${build_id_sha256}"
  } > "${tmp_file}"
  chmod 600 "${tmp_file}"
  mv "${tmp_file}" "${OPENMAIC_MODE_FILE}"
}

read_openmaic_mode() {
  local line key value version service
  local seen_version=0 seen_service=0 seen_mode=0 seen_pid=0
  local seen_start_hash=0 seen_next_version=0 seen_build_id=0
  OPENMAIC_RECORD_MODE=""
  OPENMAIC_RECORD_PID=""
  OPENMAIC_RECORD_START_HASH=""
  OPENMAIC_RECORD_NEXT_VERSION=""
  OPENMAIC_RECORD_BUILD_ID_SHA256=""
  version=""
  service=""
  [[ -f "${OPENMAIC_MODE_FILE}" ]] || return 1
  while IFS= read -r line || [[ -n "${line}" ]]; do
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      version) [[ "${seen_version}" == "0" ]] || return 1; seen_version=1; version="${value}" ;;
      service) [[ "${seen_service}" == "0" ]] || return 1; seen_service=1; service="${value}" ;;
      mode) [[ "${seen_mode}" == "0" ]] || return 1; seen_mode=1; OPENMAIC_RECORD_MODE="${value}" ;;
      pid) [[ "${seen_pid}" == "0" ]] || return 1; seen_pid=1; OPENMAIC_RECORD_PID="${value}" ;;
      start_hash) [[ "${seen_start_hash}" == "0" ]] || return 1; seen_start_hash=1; OPENMAIC_RECORD_START_HASH="${value}" ;;
      next_version) [[ "${seen_next_version}" == "0" ]] || return 1; seen_next_version=1; OPENMAIC_RECORD_NEXT_VERSION="${value}" ;;
      build_id_sha256) [[ "${seen_build_id}" == "0" ]] || return 1; seen_build_id=1; OPENMAIC_RECORD_BUILD_ID_SHA256="${value}" ;;
      *) return 1 ;;
    esac
  done < "${OPENMAIC_MODE_FILE}"
  [[ "${version}" == "2" ]] || return 1
  [[ "${service}" == "openmaic" ]] || return 1
  [[ "${OPENMAIC_RECORD_MODE}" == "pending" || "${OPENMAIC_RECORD_MODE}" == "production" ]] || return 1
  [[ "${OPENMAIC_RECORD_PID}" =~ ^[1-9][0-9]*$ ]] || return 1
  [[ "${OPENMAIC_RECORD_START_HASH}" =~ ^[a-f0-9]{64}$ ]] || return 1
  [[ "${OPENMAIC_RECORD_NEXT_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([+-][A-Za-z0-9._-]+)?$ ]] || return 1
  [[ "${OPENMAIC_RECORD_BUILD_ID_SHA256}" =~ ^[a-f0-9]{64}$ ]] || return 1
}

openmaic_process_instance_matches() {
  local pid="$1"
  local expected_start_hash="$2"
  local current_start_hash
  process_is_alive "${pid}" || return 1
  current_start_hash="$(process_start_hash "${pid}")" || return 1
  [[ "${current_start_hash}" == "${expected_start_hash}" ]]
}

openmaic_production_process_is_current() {
  local pid="$1"
  local expected_start_hash="$2"
  local expected_build_id_sha256="$3"
  local current_cwd command_token current_build_id_sha256
  openmaic_process_instance_matches "${pid}" "${expected_start_hash}" || return 1
  current_cwd="$(process_cwd "${pid}")"
  [[ "${current_cwd}" == "${SOURCE_DIR}" ]] || return 1
  command_token="$(openmaic_production_command_token)" || return 1
  process_command_contains "${pid}" "${command_token}" || return 1
  current_build_id_sha256="$(openmaic_build_id_hash)" || return 1
  [[ "${current_build_id_sha256}" == "${expected_build_id_sha256}" ]] || return 1
  port_is_owned_by_tree "${OPENMAIC_PORT}" "${pid}"
}

openmaic_recorded_process_identity_is_current() {
  local pid_file_pid command_token
  [[ -f "${OPENMAIC_PID_FILE}" ]] || return 1
  pid_file_pid="$(tr -d '[:space:]' < "${OPENMAIC_PID_FILE}")"
  [[ "${pid_file_pid}" =~ ^[1-9][0-9]*$ ]] || return 1
  read_openmaic_mode || return 1
  [[ "${OPENMAIC_RECORD_PID}" == "${pid_file_pid}" ]] || return 1
  openmaic_process_instance_matches "${OPENMAIC_RECORD_PID}" "${OPENMAIC_RECORD_START_HASH}" || return 1
  [[ "$(process_cwd "${OPENMAIC_RECORD_PID}")" == "${SOURCE_DIR}" ]] || return 1
  command_token="$(openmaic_production_command_token "${OPENMAIC_RECORD_NEXT_VERSION}")" || return 1
  process_command_contains "${OPENMAIC_RECORD_PID}" "${command_token}" || return 1
}

openmaic_production_mode_is_current() {
  openmaic_recorded_process_identity_is_current || return 1
  [[ "${OPENMAIC_RECORD_MODE}" == "production" ]] || return 1
  [[ "$(openmaic_next_version)" == "${OPENMAIC_RECORD_NEXT_VERSION}" ]] || return 1
  [[ "$(openmaic_build_id_hash)" == "${OPENMAIC_RECORD_BUILD_ID_SHA256}" ]] || return 1
  port_is_owned_by_tree "${OPENMAIC_PORT}" "${OPENMAIC_RECORD_PID}"
}

prepare_openmaic_start() {
  local stale_pid=""
  if port_is_listening "${OPENMAIC_PORT}"; then
    echo "OpenMAIC port ${OPENMAIC_PORT} is already occupied by an unverified process; refusing to start or claim it." >&2
    return 1
  fi
  if [[ -f "${OPENMAIC_PID_FILE}" ]]; then
    stale_pid="$(tr -d '[:space:]' < "${OPENMAIC_PID_FILE}")"
    if [[ "${stale_pid}" =~ ^[1-9][0-9]*$ ]] && process_is_alive "${stale_pid}"; then
      echo "OpenMAIC has a live but unverified recorded PID ${stale_pid}; refusing to replace it." >&2
      return 1
    fi
  fi
  rm -f "${OPENMAIC_PID_FILE}" "${OPENMAIC_MODE_FILE}"
}

cleanup_failed_openmaic_start() {
  local pid="$1"
  local start_hash="$2"
  local i
  if openmaic_process_instance_matches "${pid}" "${start_hash}"; then
    kill "${pid}" 2>/dev/null || true
    for ((i = 0; i < 20; i += 1)); do
      openmaic_process_instance_matches "${pid}" "${start_hash}" || break
      sleep 0.25
    done
  fi
  if openmaic_process_instance_matches "${pid}" "${start_hash}"; then
    echo "OpenMAIC PID ${pid} did not stop within 5 seconds; its startup identity was preserved." >&2
    return 1
  fi
  if ! failed_start_target_can_be_forgotten "${pid}" "${start_hash}"; then
    echo "OpenMAIC PID ${pid} could not be proven stopped; its startup identity was preserved." >&2
    return 1
  fi
  if ! remove_openmaic_start_records_if_matching "${pid}" "${start_hash}"; then
    echo "OpenMAIC startup identity changed during cleanup; the current records were preserved." >&2
    return 1
  fi
}

failed_start_target_can_be_forgotten() {
  local pid="$1" start_hash="$2" current_start_hash

  # Without a valid expected identity (for example, if the first ps probe
  # failed immediately after spawn), a live PID cannot be classified as PID
  # reuse and must remain recorded for a later safe stop/review.
  if [[ ! "${start_hash}" =~ ^[a-f0-9]{64}$ ]]; then
    process_is_alive "${pid}" && return 1
    return 0
  fi

  # A still-live process with the exact recorded start identity is never safe
  # to forget, even if it has not bound its port yet.
  openmaic_process_instance_matches "${pid}" "${start_hash}" && return 1
  process_is_alive "${pid}" || return 0

  # A different start hash proves the original process is gone (PID reuse).
  # A live PID whose start identity is temporarily unreadable remains unsafe:
  # an empty port is not enough because that process may bind it later.
  current_start_hash="$(process_start_hash "${pid}" 2>/dev/null)" || return 1
  [[ "${current_start_hash}" != "${start_hash}" ]]
}

remove_openmaic_start_records_if_matching() {
  local pid="$1" start_hash="$2" recorded_pid=""

  if [[ -f "${OPENMAIC_PID_FILE}" ]]; then
    recorded_pid="$(tr -d '[:space:]' < "${OPENMAIC_PID_FILE}")"
    [[ "${recorded_pid}" == "${pid}" ]] || return 1
  fi
  if [[ -f "${OPENMAIC_MODE_FILE}" ]]; then
    read_openmaic_mode || return 1
    [[ "${OPENMAIC_RECORD_PID}" == "${pid}" ]] || return 1
    [[ "${OPENMAIC_RECORD_START_HASH}" == "${start_hash}" ]] || return 1
  fi
  rm -f "${OPENMAIC_PID_FILE}" "${OPENMAIC_MODE_FILE}"
}

write_gateway_identity() {
  local pid="$1" start_hash="$2" tmp_file
  tmp_file="${GATEWAY_IDENTITY_FILE}.tmp.$$"
  umask 077
  {
    printf 'version=1\n'
    printf 'service=gateway\n'
    printf 'pid=%s\n' "${pid}"
    printf 'start_hash=%s\n' "${start_hash}"
  } > "${tmp_file}"
  chmod 600 "${tmp_file}"
  mv "${tmp_file}" "${GATEWAY_IDENTITY_FILE}"
}

read_gateway_identity() {
  local line key value version service
  local seen_version=0 seen_service=0 seen_pid=0 seen_start_hash=0
  GATEWAY_RECORD_PID=""
  GATEWAY_RECORD_START_HASH=""
  version=""
  service=""
  [[ -f "${GATEWAY_IDENTITY_FILE}" ]] || return 1
  while IFS= read -r line || [[ -n "${line}" ]]; do
    key="${line%%=*}"
    value="${line#*=}"
    case "${key}" in
      version) [[ "${seen_version}" == "0" ]] || return 1; seen_version=1; version="${value}" ;;
      service) [[ "${seen_service}" == "0" ]] || return 1; seen_service=1; service="${value}" ;;
      pid) [[ "${seen_pid}" == "0" ]] || return 1; seen_pid=1; GATEWAY_RECORD_PID="${value}" ;;
      start_hash) [[ "${seen_start_hash}" == "0" ]] || return 1; seen_start_hash=1; GATEWAY_RECORD_START_HASH="${value}" ;;
      *) return 1 ;;
    esac
  done < "${GATEWAY_IDENTITY_FILE}"
  [[ "${version}" == "1" ]] || return 1
  [[ "${service}" == "gateway" ]] || return 1
  [[ "${GATEWAY_RECORD_PID}" =~ ^[1-9][0-9]*$ ]] || return 1
  [[ "${GATEWAY_RECORD_START_HASH}" =~ ^[a-f0-9]{64}$ ]] || return 1
}

gateway_process_identity_matches() {
  local pid="$1" start_hash="$2"
  openmaic_process_instance_matches "${pid}" "${start_hash}" || return 1
  [[ "$(process_cwd "${pid}")" == "${GATEWAY_DIR}" ]] || return 1
  process_command_contains "${pid}" "src/server.mjs"
}

gateway_process_is_current() {
  local pid="$1" start_hash="$2"
  gateway_process_identity_matches "${pid}" "${start_hash}" || return 1
  port_is_owned_by_tree "${GATEWAY_PORT}" "${pid}"
}

gateway_recorded_process_identity_is_current() {
  local pid_file_pid
  [[ -f "${GATEWAY_PID_FILE}" ]] || return 1
  pid_file_pid="$(tr -d '[:space:]' < "${GATEWAY_PID_FILE}")"
  [[ "${pid_file_pid}" =~ ^[1-9][0-9]*$ ]] || return 1
  read_gateway_identity || return 1
  [[ "${GATEWAY_RECORD_PID}" == "${pid_file_pid}" ]] || return 1
  gateway_process_identity_matches "${GATEWAY_RECORD_PID}" "${GATEWAY_RECORD_START_HASH}"
}

gateway_runtime_is_current() {
  gateway_recorded_process_identity_is_current || return 1
  gateway_process_is_current "${GATEWAY_RECORD_PID}" "${GATEWAY_RECORD_START_HASH}"
}

prepare_gateway_start() {
  local stale_pid=""
  if port_is_listening "${GATEWAY_PORT}"; then
    echo "Gateway port ${GATEWAY_PORT} is already occupied by an unverified process; refusing to start or claim it." >&2
    return 1
  fi
  if [[ -f "${GATEWAY_PID_FILE}" ]]; then
    stale_pid="$(tr -d '[:space:]' < "${GATEWAY_PID_FILE}")"
    if [[ "${stale_pid}" =~ ^[1-9][0-9]*$ ]] && process_is_alive "${stale_pid}"; then
      echo "Gateway has a live but unverified recorded PID ${stale_pid}; refusing to replace it." >&2
      return 1
    fi
  fi
  rm -f "${GATEWAY_PID_FILE}" "${GATEWAY_IDENTITY_FILE}"
}

cleanup_failed_gateway_start() {
  local pid="$1" start_hash="$2" i
  if openmaic_process_instance_matches "${pid}" "${start_hash}"; then
    kill "${pid}" 2>/dev/null || true
    for ((i = 0; i < 20; i += 1)); do
      openmaic_process_instance_matches "${pid}" "${start_hash}" || break
      sleep 0.25
    done
  fi
  if openmaic_process_instance_matches "${pid}" "${start_hash}"; then
    echo "Gateway PID ${pid} did not stop within 5 seconds; its startup identity was preserved." >&2
    return 1
  fi
  if ! failed_start_target_can_be_forgotten "${pid}" "${start_hash}"; then
    echo "Gateway PID ${pid} could not be proven stopped; its startup identity was preserved." >&2
    return 1
  fi
  if ! remove_gateway_start_records_if_matching "${pid}" "${start_hash}"; then
    echo "Gateway startup identity changed during cleanup; the current records were preserved." >&2
    return 1
  fi
}

remove_gateway_start_records_if_matching() {
  local pid="$1" start_hash="$2" recorded_pid=""

  if [[ -f "${GATEWAY_PID_FILE}" ]]; then
    recorded_pid="$(tr -d '[:space:]' < "${GATEWAY_PID_FILE}")"
    [[ "${recorded_pid}" == "${pid}" ]] || return 1
  fi
  if [[ -f "${GATEWAY_IDENTITY_FILE}" ]]; then
    read_gateway_identity || return 1
    [[ "${GATEWAY_RECORD_PID}" == "${pid}" ]] || return 1
    [[ "${GATEWAY_RECORD_START_HASH}" == "${start_hash}" ]] || return 1
  fi
  rm -f "${GATEWAY_PID_FILE}" "${GATEWAY_IDENTITY_FILE}"
}

validate_health_payload() {
  local kind="$1"
  local payload="$2"
  local node_bin
  node_bin="$(command -v node)" || return 1
  printf '%s' "${payload}" | "${node_bin}" -e '
    const kind = process.argv[1];
    const expectedRecovery = {
      enabled: process.argv[2] === "1",
      sourceJobId: process.argv[3],
      policyVersion: process.argv[4],
      canonicalSpecSha256: process.argv[5],
      patchSha256: process.argv[6],
    };
    const expectedTtsCredentialRecovery = {
      enabled: process.argv[7] === "1",
      sourceJobId: process.argv[8],
      parentRecoveryId: process.argv[9],
      policyVersion: process.argv[10],
      canonicalSpecSha256: process.argv[11],
      patchSha256: process.argv[12],
    };
    const expectedFormalCitationRecovery = {
      enabled: process.argv[13] === "1",
      sourceJobId: process.argv[14],
      policyVersion: process.argv[15],
      patchSha256: process.argv[16],
    };
    let raw = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => { raw += chunk; });
    process.stdin.on("end", () => {
      try {
        const body = JSON.parse(raw);
        const expectedStructuredScene = {
          enforced: true,
          policyId: "deepseek-v4-pro-flash-v1",
          providerId: "deepseek",
          modelId: "deepseek-v4-pro",
          stages: [
            "scene-content",
            "scene-content:slide",
            "scene-content:quiz",
            "scene-content:interactive",
            "scene-content:pbl",
            "scene-actions",
          ],
          thinking: { mode: "disabled", enabled: false },
        };
        const expectedModelPolicy = {
          schemaVersion: "mira.openmaic.professional-model-policy.v1",
          policyId: "deepseek-v4-pro-flash-v1",
          agentDriver: {
            providerId: "deepseek",
            modelId: "deepseek-v4-pro",
            thinking: { mode: "enabled", enabled: true, effort: "high" },
          },
          coursewareCreator: {
            providerId: "deepseek",
            modelId: "deepseek-v4-pro",
            thinking: { mode: "disabled", enabled: false },
          },
          coursewareVerifier: {
            providerId: "deepseek",
            modelId: "deepseek-v4-flash",
            thinking: { mode: "disabled", enabled: false },
          },
          structuredScene: {
            policyId: "deepseek-v4-pro-flash-v1",
            providerId: "deepseek",
            modelId: "deepseek-v4-pro",
            thinking: { mode: "disabled", enabled: false },
          },
          fallbackAllowed: false,
        };
        const expectedTts = {
          enforced: true,
          providerId: "qwen-tts",
          modelId: "qwen3-tts-flash",
          voiceId: "Serena",
        };
        const expectedAsr = {
          enforced: true,
          providerId: "qwen-asr",
          modelId: "qwen3-asr-flash",
          fallbackAllowed: false,
        };
        const expectedStudentChrome = {
          enforced: true,
          policyVersion: "mira-student-chrome.v6",
          marker: "mira=1",
          locale: "zh-CN",
          theme: "light",
          autoPlayDefault: true,
          autoPlayPersistence: "student-session",
          audioStartPersistence: "classroom-tab-session",
          manualAutoPlayToggleEnabled: true,
          asrEnabled: true,
          asrPersistence: "student-session",
          manualAsrToggleEnabled: false,
          operatorAsrPreferencePreserved: true,
          operatorChromePreserved: true,
          headerControlsHidden: true,
          exportsHidden: true,
          teacherIdentity: {
            agentId: "mira-sample-teacher",
            avatar: "/avatars/teacher-2.png",
          },
        };
        const expectedFormalGeneration = {
          enforced: true,
          policyId: "mira.openmaic.formal-runtime.v4-deepseek-professional",
          idempotencyKey: "runtimeRequestId",
          queryByRuntimeRequestId: true,
          speechAudioGenerated: true,
          coursewareAuthority: {
            schemaVersion: "mira.openmaic.courseware-authority.v2-professional",
            generationOwner: "openmaic",
            providerInvocation: "professional_agent",
            classroomCompilation: "professional_skill_workflow",
            backendProviderCredentialsAccepted: false,
          },
          professionalCreation: {
            schemaVersion: "mira.openmaic.professional-creation.v1",
            mode: "professional_skill",
            workflowVersion: "openmaic-pro-agent.v1",
            skillId: "mira-primary-courseware",
            supportingSkillIds: ["k12-core-literacy-planning", "deep-interactive"],
            userPromptRequired: false,
            webSearch: {
              enabled: true,
              providerManaged: true,
              maxCalls: 4,
              citationsRequired: true,
              primarySourcesPreferred: true,
              minimumFetchedSources: 1,
            },
            image: {
              schemaVersion: "mira.openmaic.formal-image-policy.v1",
              policyId: "mira-formal-qwen-image.v1",
              enabled: true,
              providerManaged: true,
              providerId: "qwen-image",
              modelId: "qwen-image-max",
              usage: "teaching_need",
              assetValidationRequired: true,
            },
            skillOrchestration: {
              schemaVersion: "mira.openmaic.skill-orchestration.v2",
              profileId: "mira-primary-adaptive.v2",
              registryId: "openmaic-builtin-skills.v1-23",
              baseSkillIds: ["mira-primary-courseware", "stage-design", "k12-core-literacy-planning", "deep-interactive", "slide-craft", "learning-to-learn"],
              selectionMode: "server_rules",
              mainMethodMax: 1,
              decisionCoverageRequired: true,
              sceneContextRequired: true,
              gradeBoundaryRequired: true,
            },
            video: {"schemaVersion":"mira.openmaic.formal-video-policy.v1","policyId":"mira-formal-happyhorse-video.v1","enabled":true,"providerManaged":true,"providerId":"happyhorse","modelId":"happyhorse-1.0-t2v","usage":"teaching_need","maxCalls":1,"maxVideos":1,"durationSec":5,"resolution":"720p","aspectRatio":"16:9","assetValidationRequired":true},
            teachingQuality: {
              schemaVersion: "mira.openmaic.teaching-quality-policy.v1",
              policyId: "mira-primary-quality.v1",
              gradeBoundaryRequired: true,
              finalSnapshotRequired: true,
              independentReviewRequired: true,
              renderedScenesRequired: true,
              maxReviewAttempts: 3,
            },
            interactionDesignPolicy: {"schemaVersion":"mira.openmaic.interaction-design.v2","policyId":"mira-primary-multistate-interaction.v2","enabled":true,"profile":"primary-adaptive","objectiveCoverageRequired":true,"demonstrationRequired":true,"learnerOperationRequired":true,"explanatoryFeedbackRequired":true,"independentJudgmentRequired":true,"finalSnapshotRequired":true,"renderedInteractionRequired":true,"explorationPolicy":{"schemaVersion":"mira.openmaic.multistate-exploration.v1","minimumStates":3,"maximumStates":5,"resetRequired":true,"inputModes":["pointer","touch"],"mechanismRegistry":["fraction-ratio-percentage.v1","semantic-state-model.v1"]},"visualRubricVersion":"mira.primary-teaching-visual.v1","visualReviewRequired":true},
            studentToolsEnabled: false,
          },
          studentRuntimeEvents: {
            enforced: true,
            schemaVersion: "mira.openmaic.student-runtime-events.v1",
            classroomAuthoritySchema: "mira.openmaic.runtime-event-authority.v1",
            endpoint: "/mira/runtime-events",
            authority: "mira-backend",
            clientIdentityAccepted: false,
            clientScoreAccepted: false,
          },
          contract: {
            schemaVersion: "mira.openmaic.formal-runtime.v4-deepseek-professional",
            scenePlanning: {
              mode: "adaptive",
              authority: "openmaic_professional_agent",
              exactCountRequired: false,
              allowedSceneTypes: ["slide", "quiz", "interactive", "pbl"],
              requiredSceneTypes: ["slide", "quiz", "interactive"],
              defaultDurationMinutes: { min: 15, max: 30 },
              scenesPerMinute: { min: 1, max: 2 },
              maxSceneCount: 60,
            },
            roster: { teacherCount: 1, peerCount: 4 },
            speechRequiredForEveryScene: true,
            speechActions: {
              perScene: { min: 1, max: 20 },
              total: { min: 1, max: 240 },
              interactiveSpotlightRequired: false,
            },
            distinctPeerDiscussions: 2,
            teacherEvidence: ["spotlight", "widget_highlight"],
            slideSpotlight: {
              minimumPerSlide: 1,
              targetMustBeRenderable: true,
              focusExplanationSequenceRequired: true,
              consecutiveSpotlightsAllowed: true,
            },
            interactive: {
              allowedWidgetTypes: ["simulation", "diagram", "code", "game", "visualization3d"],
              widgetConfigRequired: true,
              productiveScriptRequired: true,
              noopRejected: true,
              fake3dRejected: true,
            },
            whiteboardRequired: false,
          },
        };
        const expectedProfessionalResearch = {
          schemaVersion: "mira.openmaic.professional-research.v1",
          professionalWorkbench: {
            upstreamVersion: "1.0.0",
            primarySkillId: "mira-primary-courseware",
            proModeAvailableToOperators: true,
            availableToStudentRuntime: false,
          },
          webSearch: {
            defaultEnabled: true,
            operatorOnly: false,
            formalGenerationEnabled: true,
            studentRuntimeEnabled: false,
            maxCallsPerCourse: 4,
            citationsRequired: true,
            primarySourcesPreferred: true,
          },
        };
        const expectedFormalAudio = {
          enforced: true,
          schemaVersion: "mira.openmaic.formal-audio.v1",
          segmentCount: { mode: "per_speech_action", min: 1, max: 240 },
          requestIdempotency: "requestId+canonicalBodySha256",
          providerAttemptRecordedBeforeFetch: true,
          staleRunningOutcome: "ambiguous",
          retryAllowed: false,
          providerTimeoutMs: 120000,
          maxAudioBytes: 16777216,
          audioMimeType: "audio/wav",
          tts: {
            providerId: "qwen-tts",
            modelId: "qwen3-tts-flash",
            fallbackAllowed: false,
          },
          asr: {
            providerId: "qwen-asr",
            modelId: "qwen3-asr-flash",
            fallbackAllowed: false,
            inputAuthority: "matching-local-tts-wav",
            transcriptPersisted: false,
          },
          subjects: {
            chinese: {
              teacherProfileId: "mira_chinese_gentle",
              teacherProfileVersion: 2,
              teacherProfileSha256: "a5fd163af249705bda4bb0be5448f65d275eb423285557727f9c50ea442f01f8",
              teacherName: "小语老师",
              teacherGender: "female",
              voiceGender: "female",
              voiceId: "Serena",
              languageCode: "zh-CN",
              instructionLanguageCode: "zh-CN",
              qwenLanguageType: "Chinese",
              qwenAsrLanguage: "zh",
            },
            math: {
              teacherProfileId: "mira_math_clear",
              teacherProfileVersion: 2,
              teacherProfileSha256: "4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb",
              teacherName: "小数老师",
              teacherGender: "male",
              voiceGender: "male",
              voiceId: "Ethan",
              languageCode: "zh-CN",
              instructionLanguageCode: "zh-CN",
              qwenLanguageType: "Chinese",
              qwenAsrLanguage: "zh",
            },
            english: {
              teacherProfileId: "mira_english_standard",
              teacherProfileVersion: 2,
              teacherProfileSha256: "4725f27c5438c0f68fe8923ac977fa1dd01452b990ac58912b880320750ee040",
              teacherName: "Mia 老师",
              teacherGender: "female",
              voiceGender: "female",
              voiceId: "Jennifer",
              languageCode: "en-US",
              instructionLanguageCode: "zh-CN",
              qwenLanguageType: "Chinese",
              qwenAsrLanguage: "zh",
            },
          },
        };
        const expectedFormalProviderReadiness = {
          enforced: true,
          schemaVersion: "mira.openmaic.formal-provider-readiness.v2",
          requestIdempotency: "requestId+canonicalBodySha256",
          providerAttemptRecordedBeforeFetch: true,
          expectedProviderCallCount: 5,
          retryAllowed: false,
          staleRunningOutcome: "ambiguous",
          providerTimeoutMs: 120000,
          routeSessionProof: {
            schemaVersion: "mira.openmaic.conversation-proof.v1",
            providerCall: false,
            publicationAuthority: false,
          },
          providerProof: {
            schemaVersion: "mira.openmaic.formal-provider-readiness.v2",
            providerCall: true,
            publicationAuthority: true,
            rawResponsePersisted: false,
            transcriptPersisted: false,
            audioPersisted: false,
          },
          providers: {
            deepseek: { providerId: "deepseek", modelId: "deepseek-v4-pro", callCount: 1 },
            asr: {
              providerId: "qwen-asr",
              modelId: "qwen3-asr-flash",
              callCount: 1,
              inputAuthority: "task14-local-validation-wav",
            },
            tts: {
              chinese: {
                providerId: "qwen-tts",
                modelId: "qwen3-tts-flash",
                voiceId: "Serena",
                languageCode: "zh-CN",
              },
              math: {
                providerId: "qwen-tts",
                modelId: "qwen3-tts-flash",
                voiceId: "Ethan",
                languageCode: "zh-CN",
              },
              english: {
                providerId: "qwen-tts",
                modelId: "qwen3-tts-flash",
                voiceId: "Jennifer",
                languageCode: "en-US",
              },
            },
          },
        };
        const structuredSceneReady =
          JSON.stringify(body.runtimePolicy?.structuredScene) ===
          JSON.stringify(expectedStructuredScene);
        const modelPolicyReady =
          JSON.stringify(body.runtimePolicy?.modelPolicy) ===
          JSON.stringify(expectedModelPolicy);
        const ttsReady =
          body.capabilities?.tts === true &&
          JSON.stringify(body.runtimePolicy?.tts) === JSON.stringify(expectedTts);
        const asrReady =
          body.capabilities?.asr === true &&
          JSON.stringify(body.runtimePolicy?.asr) === JSON.stringify(expectedAsr);
        const studentChromeReady =
          JSON.stringify(body.runtimePolicy?.studentChrome) ===
          JSON.stringify(expectedStudentChrome);
        const formalGenerationReady =
          require("node:util").isDeepStrictEqual(
            body.runtimePolicy?.formalGeneration, expectedFormalGeneration,
          );
        const professionalResearchReady =
          body.capabilities?.webSearch === true &&
          JSON.stringify(body.runtimePolicy?.professionalResearch) ===
          JSON.stringify(expectedProfessionalResearch);
        const expectedInstrumentationBoundary = {
          nodeRuntimeOnly: true,
          edgeBundle: "excluded",
          collector: "asset-collector-schedule",
          serverExternalPackages: ["@openmaic/storage", "pg"],
        };
        const instrumentationBoundaryReady =
          JSON.stringify(body.runtimePolicy?.instrumentationBoundary) ===
          JSON.stringify(expectedInstrumentationBoundary);
        const deterministicRecovery = body.runtimePolicy?.deterministicRecovery;
        const deterministicRecoveryReady =
          deterministicRecovery?.enabled === expectedRecovery.enabled &&
          deterministicRecovery?.sourceJobId === expectedRecovery.sourceJobId &&
          deterministicRecovery?.policyVersion === expectedRecovery.policyVersion &&
          deterministicRecovery?.canonicalSpecSha256 === expectedRecovery.canonicalSpecSha256 &&
          deterministicRecovery?.patchSha256 === expectedRecovery.patchSha256;
        const ttsCredentialRecovery = body.runtimePolicy?.ttsCredentialRecovery;
        const ttsCredentialRecoveryReady =
          ttsCredentialRecovery?.enabled === expectedTtsCredentialRecovery.enabled &&
          ttsCredentialRecovery?.sourceJobId === expectedTtsCredentialRecovery.sourceJobId &&
          ttsCredentialRecovery?.parentRecoveryId === expectedTtsCredentialRecovery.parentRecoveryId &&
          ttsCredentialRecovery?.policyVersion === expectedTtsCredentialRecovery.policyVersion &&
          ttsCredentialRecovery?.canonicalSpecSha256 === expectedTtsCredentialRecovery.canonicalSpecSha256 &&
          ttsCredentialRecovery?.patchSha256 === expectedTtsCredentialRecovery.patchSha256;
        const formalCitationRecovery = body.runtimePolicy?.formalCitationRecovery;
        const formalCitationRecoveryReady =
          JSON.stringify(formalCitationRecovery) ===
          JSON.stringify(expectedFormalCitationRecovery);
        const ok = kind === "openmaic"
          ? body.success === true &&
            body.status === "ok" &&
            body.version === "1.0.0" &&
            ttsReady &&
            asrReady &&
            structuredSceneReady &&
            modelPolicyReady &&
            studentChromeReady &&
            formalGenerationReady &&
            professionalResearchReady &&
            instrumentationBoundaryReady &&
            deterministicRecoveryReady &&
            ttsCredentialRecoveryReady &&
            formalCitationRecoveryReady
          : kind === "formal-audio"
            ? body.success === true &&
              body.status === "ok" &&
              body.version === "1.0.0" &&
              body.capabilities?.formalAudio === true &&
              body.capabilities?.tts === true &&
              body.capabilities?.asr === true &&
              JSON.stringify(body.runtimePolicy?.formalAudio) === JSON.stringify(expectedFormalAudio)
            : kind === "formal-provider-readiness"
              ? body.success === true &&
                body.status === "ok" &&
                body.version === "1.0.0" &&
                body.capabilities?.formalProviderReadiness === true &&
                JSON.stringify(body.runtimePolicy?.formalProviderReadiness) ===
                  JSON.stringify(expectedFormalProviderReadiness) &&
                modelPolicyReady
            : body.ok === true && body.service === "mira-openmaic-runtime-gateway" && body.sourceVersion === "openmaic@1.0.0";
        process.exit(ok ? 0 : 1);
      } catch { process.exit(1); }
    });
  ' "${kind}" \
    "${OPENMAIC_RECOVERY_ENABLED:-0}" \
    "${OPENMAIC_RECOVERY_SOURCE_JOB_ID:-}" \
    "${OPENMAIC_RECOVERY_POLICY_VERSION}" \
    "${OPENMAIC_RECOVERY_CANONICAL_SPEC_SHA256}" \
    "${OPENMAIC_RECOVERY_PATCH_SHA256:-}" \
    "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED:-0}" \
    "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID:-}" \
    "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID:-}" \
    "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_POLICY_VERSION}" \
    "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_CANONICAL_SPEC_SHA256}" \
    "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256:-}" \
    "${OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED:-0}" \
    "${OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID:-}" \
    "${OPENMAIC_FORMAL_CITATION_RECOVERY_POLICY_VERSION}" \
    "${OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256:-}" >/dev/null 2>&1
}

probe_health() {
  local kind="$1"
  local url="$2"
  local payload
  payload="$(curl --fail --silent --show-error --max-time "${HEALTH_TIMEOUT_SECONDS}" "${url}" 2>/dev/null)" || return 1
  validate_health_payload "${kind}" "${payload}"
}

probe_formal_audio_health() {
  local url="$1"
  local internal_token="$2"
  local payload
  [[ -n "${internal_token}" ]] || return 1
  payload="$(curl --fail --silent --show-error --max-time "${HEALTH_TIMEOUT_SECONDS}" \
    --header "X-Mira-Internal-Token: ${internal_token}" \
    --header "Host: 127.0.0.1:${OPENMAIC_PORT}" \
    --header "X-Forwarded-Host: 127.0.0.1:${OPENMAIC_PORT}" \
    --header "X-Forwarded-For: 127.0.0.1" \
    --header "X-Forwarded-Proto: http" \
    --header "X-Forwarded-Port: ${OPENMAIC_PORT}" \
    "${url}" 2>/dev/null)" || return 1
  validate_health_payload formal-audio "${payload}"
}

probe_formal_provider_readiness_health() {
  local url="$1"
  local internal_token="$2"
  local payload
  [[ -n "${internal_token}" ]] || return 1
  payload="$(curl --fail --silent --show-error --max-time "${HEALTH_TIMEOUT_SECONDS}" \
    --header "X-Mira-Internal-Token: ${internal_token}" \
    --header "Host: 127.0.0.1:${OPENMAIC_PORT}" \
    --header "X-Forwarded-Host: 127.0.0.1:${OPENMAIC_PORT}" \
    --header "X-Forwarded-For: 127.0.0.1" \
    --header "X-Forwarded-Proto: http" \
    --header "X-Forwarded-Port: ${OPENMAIC_PORT}" \
    "${url}" 2>/dev/null)" || return 1
  validate_health_payload formal-provider-readiness "${payload}"
}

wait_for_health() {
  local kind="$1"
  local url="$2"
  local attempts="${3:-60}"
  local i
  for ((i = 0; i < attempts; i += 1)); do
    if probe_health "${kind}" "${url}"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_for_owned_openmaic_health() {
  local pid="$1"
  local start_hash="$2"
  local build_id_sha256="$3"
  local attempts="${4:-60}"
  local i
  for ((i = 0; i < attempts; i += 1)); do
    openmaic_process_instance_matches "${pid}" "${start_hash}" || return 1
    if openmaic_production_process_is_current "${pid}" "${start_hash}" "${build_id_sha256}" && \
      probe_health openmaic "${OPENMAIC_URL}/api/health"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_for_owned_gateway_health() {
  local pid="$1"
  local start_hash="$2"
  local attempts="${3:-60}"
  local i
  for ((i = 0; i < attempts; i += 1)); do
    openmaic_process_instance_matches "${pid}" "${start_hash}" || return 1
    if gateway_runtime_is_current && probe_health gateway "${GATEWAY_URL}/health"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_for_formal_audio_health() {
  local url="$1"
  local internal_token="$2"
  local attempts="${3:-60}"
  local i
  for ((i = 0; i < attempts; i += 1)); do
    if probe_formal_audio_health "${url}" "${internal_token}"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_for_formal_provider_readiness_health() {
  local url="$1"
  local internal_token="$2"
  local attempts="${3:-60}"
  local i
  for ((i = 0; i < attempts; i += 1)); do
    if probe_formal_provider_readiness_health "${url}" "${internal_token}"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

# Foreground entry points are intentionally separate from the legacy nohup
# helpers below. macOS launchd must own the actual service process so it can
# survive the terminal/Codex session that requested the start and restart a
# crashed service. Credentials are still read from the existing server-owned
# dotenv file, passed only through the child process environment, and never
# written to a plist or command line.
bootstrap_openmaic_source() {
  "${SCRIPT_DIR}/bootstrap-upstream.sh"
}

require_openmaic_dependencies() {
  [[ -x "${SOURCE_DIR}/node_modules/.bin/next" ]] || {
    echo "OpenMAIC dependencies are missing. Run pnpm install --frozen-lockfile in ${SOURCE_DIR}." >&2
    return 1
  }
}

require_openmaic_production_build() {
  [[ -s "${SOURCE_DIR}/.next/BUILD_ID" ]] || {
    echo "OpenMAIC production build is missing. Run $0 build-openmaic-production first." >&2
    return 1
  }
}

reject_openmaic_build_dotenv_files() {
  local dotenv_name
  for dotenv_name in .env .env.local .env.production .env.production.local; do
    [[ ! -e "${SOURCE_DIR}/${dotenv_name}" ]] || {
      echo "Refusing production build while ${SOURCE_DIR}/${dotenv_name} exists; Next.js could load secrets from it." >&2
      return 1
    }
  done
}

# Build in a clean environment so a Provider credential or an unrelated
# NEXT_PUBLIC value inherited from the operator shell cannot be persisted in
# .next or exposed by build output. Only validated public origins, fixed public
# feature flags, and non-secret process basics cross this boundary.
build_openmaic_production() {
  bootstrap_openmaic_source || return 1
  reject_openmaic_build_dotenv_files || return 1
  require_openmaic_dependencies || return 1
  load_runtime_origin_env || return 1

  local node_bin node_major node_options openmaic_version
  node_bin="$(command -v node)"
  node_major="$(${node_bin} -p 'Number(process.versions.node.split(".")[0])')"
  openmaic_version="$(cd "${SOURCE_DIR}" && "${node_bin}" -p 'require("./package.json").version')"
  node_options=""
  if ((node_major >= 25)); then
    node_options="--no-experimental-webstorage"
  fi

  cd "${SOURCE_DIR}"
  # Next 16 defaults to Turbopack, which can leave every SWC/tokio worker
  # asleep indefinitely on this native macOS build.  The production runtime
  # does not depend on Turbopack output, so use Next's supported webpack
  # builder for a bounded, repeatable artifact.
  env -i \
    PATH="${PATH}" \
    HOME="${HOME}" \
    TMPDIR="${TMPDIR:-/tmp}" \
    LANG="${LANG:-en_US.UTF-8}" \
    NODE_OPTIONS="${node_options}" \
    NODE_ENV=production \
    npm_package_version="${openmaic_version}" \
    NEXT_PUBLIC_PRO_WORKBENCH_ENABLED=true \
    NEXT_PUBLIC_MIRA_WORKBENCH_DOCUMENTS_ENABLED=true \
    NEXT_PUBLIC_MAIC_EDITOR_ENABLED=true \
    NEXT_PUBLIC_MAIC_EDITOR_RENDERER_ENABLED=true \
    NEXT_PUBLIC_MAIC_PLAYBACK_RENDERER_ENABLED=true \
    NEXT_PUBLIC_PI_CHAT_ENABLED=true \
    NEXT_PUBLIC_ENABLE_VIDEO_EXPORT=true \
    NEXT_PUBLIC_ENABLE_PPTX_IMPORT=true \
    ALLOWED_FRAME_ANCESTORS="${MIRA_STUDENT_WEB_ORIGIN}" \
    "${node_bin}" scripts/assert-vendor-maic-importer.mjs
  env -i \
    PATH="${PATH}" \
    HOME="${HOME}" \
    TMPDIR="${TMPDIR:-/tmp}" \
    LANG="${LANG:-en_US.UTF-8}" \
    NODE_OPTIONS="${node_options}" \
    NODE_ENV=production \
    npm_package_version="${openmaic_version}" \
    MIRA_OPENMAIC_NATIVE_BUILD=1 \
    NEXT_PUBLIC_PRO_WORKBENCH_ENABLED=true \
    NEXT_PUBLIC_MIRA_WORKBENCH_DOCUMENTS_ENABLED=true \
    NEXT_PUBLIC_MAIC_EDITOR_ENABLED=true \
    NEXT_PUBLIC_MAIC_EDITOR_RENDERER_ENABLED=true \
    NEXT_PUBLIC_MAIC_PLAYBACK_RENDERER_ENABLED=true \
    NEXT_PUBLIC_PI_CHAT_ENABLED=true \
    NEXT_PUBLIC_ENABLE_VIDEO_EXPORT=true \
    NEXT_PUBLIC_ENABLE_PPTX_IMPORT=true \
    ALLOWED_FRAME_ANCESTORS="${MIRA_STUDENT_WEB_ORIGIN}" \
    "${node_bin}" node_modules/next/dist/bin/next build --webpack
}

# Production uses the exact same strict runtime credential and policy loaders
# as the reviewed development foreground command. Secrets cross only the clean
# child environment at process start; the already-built .next tree never sees
# them. The existing status/health probes remain the readiness authority.
run_openmaic_production_foreground() {
  require_openmaic_dependencies || return 1
  reject_openmaic_build_dotenv_files || return 1
  require_openmaic_production_build || return 1

  local node_bin node_major node_options openmaic_version
  node_bin="$(command -v node)"
  node_major="$(${node_bin} -p 'Number(process.versions.node.split(".")[0])')"
  openmaic_version="$(cd "${SOURCE_DIR}" && "${node_bin}" -p 'require("./package.json").version')"
  node_options=""
  if ((node_major >= 25)); then
    node_options="--no-experimental-webstorage"
  fi
  load_runtime_origin_env || return 1
  load_openmaic_provider_env || return 1
  load_openmaic_recovery_env || return 1
  load_openmaic_formal_citation_recovery_env || return 1
  load_openmaic_internal_token_env || return 1

  cd "${SOURCE_DIR}"
  exec env -i \
    PATH="${PATH}" \
    HOME="${HOME}" \
    TMPDIR="${TMPDIR:-/tmp}" \
    LANG="${LANG:-en_US.UTF-8}" \
    NODE_OPTIONS="${node_options}" \
    NODE_ENV=production \
    MIRA_OPENMAIC_NATIVE_BUILD=1 \
    MIRA_OPENMAIC_PRIVATE_PORT="${OPENMAIC_PORT}" \
    MIRA_FORMAL_QA_BASE_URL="${OPENMAIC_URL}" \
    MIRA_FORMAL_QA_BROWSER_PATH="${MIRA_FORMAL_QA_BROWSER_PATH:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}" \
    npm_package_version="${openmaic_version}" \
    NEXT_PUBLIC_PRO_WORKBENCH_ENABLED=true \
    NEXT_PUBLIC_MIRA_WORKBENCH_DOCUMENTS_ENABLED=true \
    NEXT_PUBLIC_MAIC_EDITOR_ENABLED=true \
    NEXT_PUBLIC_MAIC_EDITOR_RENDERER_ENABLED=true \
    NEXT_PUBLIC_MAIC_PLAYBACK_RENDERER_ENABLED=true \
    NEXT_PUBLIC_PI_CHAT_ENABLED=true \
    NEXT_PUBLIC_ENABLE_VIDEO_EXPORT=true \
    NEXT_PUBLIC_ENABLE_PPTX_IMPORT=true \
    ALLOWED_FRAME_ANCESTORS="${MIRA_STUDENT_WEB_ORIGIN}" \
    DEFAULT_MODEL="${OPENMAIC_DEFAULT_MODEL}" \
    OPENMAIC_AGENT_RUNTIME_ENABLED="${OPENMAIC_AGENT_RUNTIME_ENABLED}" \
    DATABASE_URL="${OPENMAIC_AGENT_DATABASE_URL}" \
    PERSISTENCE_DEV_TOKEN="${OPENMAIC_PERSISTENCE_DEV_TOKEN}" \
    MODEL_ROUTES="${OPENMAIC_MODEL_ROUTES}" \
    MIRA_OPENMAIC_ENABLE_WEB_SEARCH="${OPENMAIC_WEB_SEARCH_ENABLED}" \
    MIRA_OPENMAIC_WEB_SEARCH_PROVIDER="${OPENMAIC_WEB_SEARCH_PROVIDER}" \
    BRAVE_BASE_URL="${OPENMAIC_BRAVE_BASE_URL}" \
    BRAVE_API_KEY="${OPENMAIC_BRAVE_API_KEY}" \
    BRAVE_ENABLED="${OPENMAIC_BRAVE_ENABLED}" \
    BAIDU_BASE_URL="${OPENMAIC_BAIDU_BASE_URL}" \
    BAIDU_API_KEY="${OPENMAIC_BAIDU_API_KEY}" \
    BAIDU_ENABLED="${OPENMAIC_BAIDU_ENABLED}" \
    MIRA_OPENMAIC_STRUCTURED_SCENE_POLICY="${OPENMAIC_STRUCTURED_SCENE_POLICY_ID}" \
    DEEPSEEK_API_KEY="${OPENMAIC_DEEPSEEK_API_KEY}" \
    DEEPSEEK_BASE_URL="${OPENMAIC_DEEPSEEK_BASE_URL}" \
    DEEPSEEK_MODELS="${OPENMAIC_DEEPSEEK_MODELS}" \
    TTS_QWEN_API_KEY="${OPENMAIC_TTS_QWEN_API_KEY}" \
    TTS_QWEN_BASE_URL="${OPENMAIC_TTS_QWEN_BASE_URL}" \
    TTS_QWEN_MODELS="${OPENMAIC_TTS_QWEN_MODELS}" \
    MIRA_OPENMAIC_REQUIRE_QWEN_TTS="${OPENMAIC_REQUIRE_QWEN_TTS}" \
    MIRA_OPENMAIC_QWEN_TTS_MODEL="${OPENMAIC_TTS_QWEN_MODELS}" \
    MIRA_OPENMAIC_QWEN_TTS_VOICE="${OPENMAIC_TTS_QWEN_VOICE}" \
    ASR_QWEN_API_KEY="${OPENMAIC_ASR_QWEN_API_KEY}" \
    ASR_QWEN_BASE_URL="${OPENMAIC_ASR_QWEN_BASE_URL}" \
    ASR_QWEN_MODELS="${OPENMAIC_ASR_QWEN_MODELS}" \
    MIRA_OPENMAIC_REQUIRE_QWEN_ASR="${OPENMAIC_REQUIRE_QWEN_ASR}" \
    MIRA_OPENMAIC_QWEN_ASR_MODEL="${OPENMAIC_ASR_QWEN_MODELS}" \
    DEFAULT_IMAGE_PROVIDER="${OPENMAIC_DEFAULT_IMAGE_PROVIDER}" \
    IMAGE_QWEN_IMAGE_API_KEY="${OPENMAIC_IMAGE_QWEN_IMAGE_API_KEY}" \
    IMAGE_QWEN_IMAGE_BASE_URL="${OPENMAIC_IMAGE_QWEN_IMAGE_BASE_URL}" \
    IMAGE_QWEN_IMAGE_MODELS="${OPENMAIC_IMAGE_QWEN_IMAGE_MODELS}" \
    DEFAULT_VIDEO_PROVIDER="${OPENMAIC_DEFAULT_VIDEO_PROVIDER}" \
    VIDEO_HAPPYHORSE_API_KEY="${OPENMAIC_VIDEO_HAPPYHORSE_API_KEY}" \
    VIDEO_HAPPYHORSE_BASE_URL="${OPENMAIC_VIDEO_HAPPYHORSE_BASE_URL}" \
    VIDEO_HAPPYHORSE_MODELS="${OPENMAIC_VIDEO_HAPPYHORSE_MODELS}" \
    MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED="${OPENMAIC_RECOVERY_ENABLED}" \
    MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_RECOVERY_SOURCE_JOB_ID}" \
    MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_PATCH_SHA256="${OPENMAIC_RECOVERY_PATCH_SHA256}" \
    MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED}" \
    MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID}" \
    MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID}" \
    MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256}" \
    MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED="${OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED}" \
    MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID}" \
    MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256="${OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256}" \
    MIRA_BACKEND_INTERNAL_URL="${MIRA_BACKEND_INTERNAL_URL:-http://127.0.0.1:8000}" \
    MIRA_INTERNAL_API_TOKEN="${OPENMAIC_INTERNAL_API_TOKEN}" \
    "${node_bin}" node_modules/next/dist/bin/next start \
      --hostname 127.0.0.1 --port "${OPENMAIC_PORT}"
}

run_openmaic_foreground() {
  bootstrap_openmaic_source
  require_openmaic_dependencies

  local node_bin node_major node_options openmaic_version
  node_bin="$(command -v node)"
  node_major="$(${node_bin} -p 'Number(process.versions.node.split(".")[0])')"
  openmaic_version="$(cd "${SOURCE_DIR}" && "${node_bin}" -p 'require("./package.json").version')"
  node_options=""
  if ((node_major >= 25)); then
    node_options="--no-experimental-webstorage"
  fi
  load_runtime_origin_env
  load_openmaic_provider_env
  load_openmaic_recovery_env
  load_openmaic_formal_citation_recovery_env
  load_openmaic_internal_token_env

  cd "${SOURCE_DIR}"
  exec env -i \
    PATH="${PATH}" \
    HOME="${HOME}" \
    TMPDIR="${TMPDIR:-/tmp}" \
    LANG="${LANG:-en_US.UTF-8}" \
    NODE_OPTIONS="${node_options}" \
    NODE_ENV=development \
    MIRA_OPENMAIC_LOW_DISK_DEV=1 \
    MIRA_OPENMAIC_PRIVATE_PORT="${OPENMAIC_PORT}" \
    MIRA_FORMAL_QA_BASE_URL="${OPENMAIC_URL}" \
    MIRA_FORMAL_QA_BROWSER_PATH="${MIRA_FORMAL_QA_BROWSER_PATH:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}" \
    npm_package_version="${openmaic_version}" \
    NEXT_PUBLIC_PRO_WORKBENCH_ENABLED=true \
    NEXT_PUBLIC_MIRA_WORKBENCH_DOCUMENTS_ENABLED=true \
    NEXT_PUBLIC_MAIC_EDITOR_ENABLED=true \
    NEXT_PUBLIC_MAIC_EDITOR_RENDERER_ENABLED=true \
    NEXT_PUBLIC_MAIC_PLAYBACK_RENDERER_ENABLED=true \
    NEXT_PUBLIC_PI_CHAT_ENABLED=true \
    NEXT_PUBLIC_ENABLE_VIDEO_EXPORT=true \
    NEXT_PUBLIC_ENABLE_PPTX_IMPORT=true \
    ALLOWED_FRAME_ANCESTORS="${MIRA_STUDENT_WEB_ORIGIN}" \
    DEFAULT_MODEL="${OPENMAIC_DEFAULT_MODEL}" \
    OPENMAIC_AGENT_RUNTIME_ENABLED="${OPENMAIC_AGENT_RUNTIME_ENABLED}" \
    DATABASE_URL="${OPENMAIC_AGENT_DATABASE_URL}" \
    PERSISTENCE_DEV_TOKEN="${OPENMAIC_PERSISTENCE_DEV_TOKEN}" \
    MODEL_ROUTES="${OPENMAIC_MODEL_ROUTES}" \
    MIRA_OPENMAIC_ENABLE_WEB_SEARCH="${OPENMAIC_WEB_SEARCH_ENABLED}" \
    MIRA_OPENMAIC_WEB_SEARCH_PROVIDER="${OPENMAIC_WEB_SEARCH_PROVIDER}" \
    BRAVE_BASE_URL="${OPENMAIC_BRAVE_BASE_URL}" \
    BRAVE_API_KEY="${OPENMAIC_BRAVE_API_KEY}" \
    BRAVE_ENABLED="${OPENMAIC_BRAVE_ENABLED}" \
    BAIDU_BASE_URL="${OPENMAIC_BAIDU_BASE_URL}" \
    BAIDU_API_KEY="${OPENMAIC_BAIDU_API_KEY}" \
    BAIDU_ENABLED="${OPENMAIC_BAIDU_ENABLED}" \
    MIRA_OPENMAIC_STRUCTURED_SCENE_POLICY="${OPENMAIC_STRUCTURED_SCENE_POLICY_ID}" \
    DEEPSEEK_API_KEY="${OPENMAIC_DEEPSEEK_API_KEY}" \
    DEEPSEEK_BASE_URL="${OPENMAIC_DEEPSEEK_BASE_URL}" \
    DEEPSEEK_MODELS="${OPENMAIC_DEEPSEEK_MODELS}" \
    TTS_QWEN_API_KEY="${OPENMAIC_TTS_QWEN_API_KEY}" \
    TTS_QWEN_BASE_URL="${OPENMAIC_TTS_QWEN_BASE_URL}" \
    TTS_QWEN_MODELS="${OPENMAIC_TTS_QWEN_MODELS}" \
    MIRA_OPENMAIC_REQUIRE_QWEN_TTS="${OPENMAIC_REQUIRE_QWEN_TTS}" \
    MIRA_OPENMAIC_QWEN_TTS_MODEL="${OPENMAIC_TTS_QWEN_MODELS}" \
    MIRA_OPENMAIC_QWEN_TTS_VOICE="${OPENMAIC_TTS_QWEN_VOICE}" \
    ASR_QWEN_API_KEY="${OPENMAIC_ASR_QWEN_API_KEY}" \
    ASR_QWEN_BASE_URL="${OPENMAIC_ASR_QWEN_BASE_URL}" \
    ASR_QWEN_MODELS="${OPENMAIC_ASR_QWEN_MODELS}" \
    MIRA_OPENMAIC_REQUIRE_QWEN_ASR="${OPENMAIC_REQUIRE_QWEN_ASR}" \
    MIRA_OPENMAIC_QWEN_ASR_MODEL="${OPENMAIC_ASR_QWEN_MODELS}" \
    DEFAULT_IMAGE_PROVIDER="${OPENMAIC_DEFAULT_IMAGE_PROVIDER}" \
    IMAGE_QWEN_IMAGE_API_KEY="${OPENMAIC_IMAGE_QWEN_IMAGE_API_KEY}" \
    IMAGE_QWEN_IMAGE_BASE_URL="${OPENMAIC_IMAGE_QWEN_IMAGE_BASE_URL}" \
    IMAGE_QWEN_IMAGE_MODELS="${OPENMAIC_IMAGE_QWEN_IMAGE_MODELS}" \
    DEFAULT_VIDEO_PROVIDER="${OPENMAIC_DEFAULT_VIDEO_PROVIDER}" \
    VIDEO_HAPPYHORSE_API_KEY="${OPENMAIC_VIDEO_HAPPYHORSE_API_KEY}" \
    VIDEO_HAPPYHORSE_BASE_URL="${OPENMAIC_VIDEO_HAPPYHORSE_BASE_URL}" \
    VIDEO_HAPPYHORSE_MODELS="${OPENMAIC_VIDEO_HAPPYHORSE_MODELS}" \
    MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED="${OPENMAIC_RECOVERY_ENABLED}" \
    MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_RECOVERY_SOURCE_JOB_ID}" \
    MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_PATCH_SHA256="${OPENMAIC_RECOVERY_PATCH_SHA256}" \
    MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED}" \
    MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID}" \
    MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID}" \
    MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256}" \
    MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED="${OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED}" \
    MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID}" \
    MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256="${OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256}" \
    MIRA_BACKEND_INTERNAL_URL="${MIRA_BACKEND_INTERNAL_URL:-http://127.0.0.1:8000}" \
    MIRA_INTERNAL_API_TOKEN="${OPENMAIC_INTERNAL_API_TOKEN}" \
    "${node_bin}" node_modules/next/dist/bin/next dev --webpack \
      --hostname 127.0.0.1 --port "${OPENMAIC_PORT}"
}

run_gateway_foreground() {
  local internal_token node_bin
  load_runtime_origin_env
  internal_token="$(read_backend_internal_token)" || {
    echo "MIRA_INTERNAL_API_TOKEN is required (or provide backend/.env with INTERNAL_API_TOKEN)." >&2
    return 1
  }
  node_bin="$(command -v node)"

  cd "${GATEWAY_DIR}"
  exec env -i \
    PATH="${PATH}" \
    HOME="${HOME}" \
    TMPDIR="${TMPDIR:-/tmp}" \
    LANG="${LANG:-en_US.UTF-8}" \
    NODE_ENV=development \
    PORT="${GATEWAY_PORT}" \
    OPENMAIC_UPSTREAM_URL="${OPENMAIC_URL}" \
    MIRA_BACKEND_INTERNAL_URL="${MIRA_BACKEND_INTERNAL_URL:-http://127.0.0.1:8000}" \
    MIRA_RUNTIME_PUBLIC_ORIGIN="${MIRA_RUNTIME_PUBLIC_ORIGIN}" \
    MIRA_STUDENT_WEB_ORIGIN="${MIRA_STUDENT_WEB_ORIGIN}" \
    MIRA_LOCAL_LAN_PRODUCTION_MODE="${MIRA_LOCAL_LAN_PRODUCTION_MODE:-0}" \
    MIRA_INTERNAL_API_TOKEN="${internal_token}" \
    "${node_bin}" src/server.mjs
}

start_openmaic() {
  # Resolve the recovery expectation before accepting an already-running
  # process. A stale process without patch 0007 or with a different source/hash
  # must never be reported as healthy for this opt-in.
  load_openmaic_provider_env
  load_openmaic_recovery_env
  load_openmaic_formal_citation_recovery_env
  load_openmaic_internal_token_env
  if openmaic_production_mode_is_current && \
    probe_health openmaic "${OPENMAIC_URL}/api/health" && \
    probe_formal_audio_health "${OPENMAIC_URL}/api/health?scope=formal-audio" "${OPENMAIC_INTERNAL_API_TOKEN}" && \
    probe_formal_provider_readiness_health "${OPENMAIC_URL}/api/health?scope=formal-provider-readiness" "${OPENMAIC_INTERNAL_API_TOKEN}" && \
    openmaic_production_mode_is_current; then
    clear_openmaic_provider_env
    clear_openmaic_recovery_secret
    clear_openmaic_internal_token
    echo "OpenMAIC already healthy at ${OPENMAIC_URL}"
    return 0
  fi

  if ! reject_openmaic_build_dotenv_files || \
    ! require_openmaic_dependencies || \
    ! require_openmaic_production_build || \
    ! prepare_openmaic_start; then
    clear_openmaic_provider_env
    clear_openmaic_recovery_secret
    clear_openmaic_internal_token
    return 1
  fi

  local node_bin node_major node_options openmaic_version next_version
  local started_pid started_start_hash build_id_sha256 health_internal_token
  node_bin="$(command -v node)"
  node_major="$(${node_bin} -p 'Number(process.versions.node.split(".")[0])')"
  openmaic_version="$(cd "${SOURCE_DIR}" && "${node_bin}" -p 'require("./package.json").version')"
  next_version="$(openmaic_next_version)"
  node_options=""
  if ((node_major >= 25)); then
    node_options="--no-experimental-webstorage"
  fi
  load_runtime_origin_env

  (
    cd "${SOURCE_DIR}"
    nohup env -i \
      PATH="${PATH}" \
      HOME="${HOME}" \
      TMPDIR="${TMPDIR:-/tmp}" \
      LANG="${LANG:-en_US.UTF-8}" \
      NODE_OPTIONS="${node_options}" \
      NODE_ENV=production \
      MIRA_OPENMAIC_NATIVE_BUILD=1 \
      MIRA_OPENMAIC_PRIVATE_PORT="${OPENMAIC_PORT}" \
    MIRA_FORMAL_QA_BASE_URL="${OPENMAIC_URL}" \
    MIRA_FORMAL_QA_BROWSER_PATH="${MIRA_FORMAL_QA_BROWSER_PATH:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}" \
      npm_package_version="${openmaic_version}" \
      NEXT_PUBLIC_PRO_WORKBENCH_ENABLED=true \
      NEXT_PUBLIC_MIRA_WORKBENCH_DOCUMENTS_ENABLED=true \
      NEXT_PUBLIC_MAIC_EDITOR_ENABLED=true \
      NEXT_PUBLIC_MAIC_EDITOR_RENDERER_ENABLED=true \
      NEXT_PUBLIC_MAIC_PLAYBACK_RENDERER_ENABLED=true \
      NEXT_PUBLIC_PI_CHAT_ENABLED=true \
      NEXT_PUBLIC_ENABLE_VIDEO_EXPORT=true \
      NEXT_PUBLIC_ENABLE_PPTX_IMPORT=true \
      ALLOWED_FRAME_ANCESTORS="${MIRA_STUDENT_WEB_ORIGIN}" \
      DEFAULT_MODEL="${OPENMAIC_DEFAULT_MODEL}" \
      OPENMAIC_AGENT_RUNTIME_ENABLED="${OPENMAIC_AGENT_RUNTIME_ENABLED}" \
      DATABASE_URL="${OPENMAIC_AGENT_DATABASE_URL}" \
      PERSISTENCE_DEV_TOKEN="${OPENMAIC_PERSISTENCE_DEV_TOKEN}" \
      MODEL_ROUTES="${OPENMAIC_MODEL_ROUTES}" \
      MIRA_OPENMAIC_ENABLE_WEB_SEARCH="${OPENMAIC_WEB_SEARCH_ENABLED}" \
      MIRA_OPENMAIC_WEB_SEARCH_PROVIDER="${OPENMAIC_WEB_SEARCH_PROVIDER}" \
      BRAVE_BASE_URL="${OPENMAIC_BRAVE_BASE_URL}" \
    BRAVE_API_KEY="${OPENMAIC_BRAVE_API_KEY}" \
      BRAVE_ENABLED="${OPENMAIC_BRAVE_ENABLED}" \
    BAIDU_BASE_URL="${OPENMAIC_BAIDU_BASE_URL}" \
    BAIDU_API_KEY="${OPENMAIC_BAIDU_API_KEY}" \
    BAIDU_ENABLED="${OPENMAIC_BAIDU_ENABLED}" \
      MIRA_OPENMAIC_STRUCTURED_SCENE_POLICY="${OPENMAIC_STRUCTURED_SCENE_POLICY_ID}" \
      DEEPSEEK_API_KEY="${OPENMAIC_DEEPSEEK_API_KEY}" \
      DEEPSEEK_BASE_URL="${OPENMAIC_DEEPSEEK_BASE_URL}" \
      DEEPSEEK_MODELS="${OPENMAIC_DEEPSEEK_MODELS}" \
      TTS_QWEN_API_KEY="${OPENMAIC_TTS_QWEN_API_KEY}" \
      TTS_QWEN_BASE_URL="${OPENMAIC_TTS_QWEN_BASE_URL}" \
      TTS_QWEN_MODELS="${OPENMAIC_TTS_QWEN_MODELS}" \
      MIRA_OPENMAIC_REQUIRE_QWEN_TTS="${OPENMAIC_REQUIRE_QWEN_TTS}" \
      MIRA_OPENMAIC_QWEN_TTS_MODEL="${OPENMAIC_TTS_QWEN_MODELS}" \
      MIRA_OPENMAIC_QWEN_TTS_VOICE="${OPENMAIC_TTS_QWEN_VOICE}" \
      ASR_QWEN_API_KEY="${OPENMAIC_ASR_QWEN_API_KEY}" \
      ASR_QWEN_BASE_URL="${OPENMAIC_ASR_QWEN_BASE_URL}" \
      ASR_QWEN_MODELS="${OPENMAIC_ASR_QWEN_MODELS}" \
      MIRA_OPENMAIC_REQUIRE_QWEN_ASR="${OPENMAIC_REQUIRE_QWEN_ASR}" \
      MIRA_OPENMAIC_QWEN_ASR_MODEL="${OPENMAIC_ASR_QWEN_MODELS}" \
      DEFAULT_IMAGE_PROVIDER="${OPENMAIC_DEFAULT_IMAGE_PROVIDER}" \
      IMAGE_QWEN_IMAGE_API_KEY="${OPENMAIC_IMAGE_QWEN_IMAGE_API_KEY}" \
      IMAGE_QWEN_IMAGE_BASE_URL="${OPENMAIC_IMAGE_QWEN_IMAGE_BASE_URL}" \
      IMAGE_QWEN_IMAGE_MODELS="${OPENMAIC_IMAGE_QWEN_IMAGE_MODELS}" \
      DEFAULT_VIDEO_PROVIDER="${OPENMAIC_DEFAULT_VIDEO_PROVIDER}" \
    VIDEO_HAPPYHORSE_API_KEY="${OPENMAIC_VIDEO_HAPPYHORSE_API_KEY}" \
      VIDEO_HAPPYHORSE_BASE_URL="${OPENMAIC_VIDEO_HAPPYHORSE_BASE_URL}" \
      VIDEO_HAPPYHORSE_MODELS="${OPENMAIC_VIDEO_HAPPYHORSE_MODELS}" \
      MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED="${OPENMAIC_RECOVERY_ENABLED}" \
      MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_RECOVERY_SOURCE_JOB_ID}" \
      MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_PATCH_SHA256="${OPENMAIC_RECOVERY_PATCH_SHA256}" \
      MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED}" \
      MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID}" \
      MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID}" \
      MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256}" \
      MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED="${OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED}" \
      MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID}" \
      MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256="${OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256}" \
      MIRA_BACKEND_INTERNAL_URL="${MIRA_BACKEND_INTERNAL_URL:-http://127.0.0.1:8000}" \
    MIRA_INTERNAL_API_TOKEN="${OPENMAIC_INTERNAL_API_TOKEN}" \
      "${node_bin}" node_modules/next/dist/bin/next start \
        --hostname 127.0.0.1 --port "${OPENMAIC_PORT}" \
        > "${OPENMAIC_LOG}" 2>&1 &
    echo "$!" > "${OPENMAIC_PID_FILE}"
  )
  started_pid="$(tr -d '[:space:]' < "${OPENMAIC_PID_FILE}")"
  if [[ ! "${started_pid}" =~ ^[1-9][0-9]*$ ]] || \
    ! started_start_hash="$(process_start_hash "${started_pid}")" || \
    ! build_id_sha256="$(openmaic_build_id_hash)"; then
    clear_openmaic_provider_env
    clear_openmaic_recovery_secret
    clear_openmaic_internal_token
    [[ "${started_pid}" =~ ^[1-9][0-9]*$ ]] && cleanup_failed_openmaic_start "${started_pid}" "${started_start_hash:-invalid}"
    echo "OpenMAIC failed to publish a verifiable process identity; inspect ${OPENMAIC_LOG}." >&2
    return 1
  fi
  write_openmaic_mode "${started_pid}" "${started_start_hash}" "${build_id_sha256}" "${next_version}" pending
  clear_openmaic_provider_env
  # Clear the credential immediately, while retaining only the non-secret
  # expected policy values for the exact health attestation below.
  clear_openmaic_recovery_secret
  health_internal_token="${OPENMAIC_INTERNAL_API_TOKEN}"
  clear_openmaic_internal_token

  if ! wait_for_owned_openmaic_health "${started_pid}" "${started_start_hash}" "${build_id_sha256}"; then
    cleanup_failed_openmaic_start "${started_pid}" "${started_start_hash}"
    echo "OpenMAIC failed to start; inspect ${OPENMAIC_LOG}." >&2
    return 1
  fi
  if ! openmaic_production_process_is_current "${started_pid}" "${started_start_hash}" "${build_id_sha256}" || \
    ! wait_for_formal_audio_health "${OPENMAIC_URL}/api/health?scope=formal-audio" "${health_internal_token}" || \
    ! openmaic_production_process_is_current "${started_pid}" "${started_start_hash}" "${build_id_sha256}"; then
    unset health_internal_token
    cleanup_failed_openmaic_start "${started_pid}" "${started_start_hash}"
    echo "OpenMAIC formal audio health failed; inspect ${OPENMAIC_LOG}." >&2
    return 1
  fi
  if ! openmaic_production_process_is_current "${started_pid}" "${started_start_hash}" "${build_id_sha256}" || \
    ! wait_for_formal_provider_readiness_health "${OPENMAIC_URL}/api/health?scope=formal-provider-readiness" "${health_internal_token}" || \
    ! openmaic_production_process_is_current "${started_pid}" "${started_start_hash}" "${build_id_sha256}"; then
    unset health_internal_token
    cleanup_failed_openmaic_start "${started_pid}" "${started_start_hash}"
    echo "OpenMAIC formal Provider readiness health failed; inspect ${OPENMAIC_LOG}." >&2
    return 1
  fi
  unset health_internal_token
  write_openmaic_mode "${started_pid}" "${started_start_hash}" "${build_id_sha256}" "${next_version}"
  if ! openmaic_production_mode_is_current; then
    cleanup_failed_openmaic_start "${started_pid}" "${started_start_hash}"
    echo "OpenMAIC identity changed before production mode was committed; inspect ${OPENMAIC_LOG}." >&2
    return 1
  fi
  echo "OpenMAIC started at ${OPENMAIC_URL} (log: ${OPENMAIC_LOG})"
}

start_gateway() {
  if gateway_runtime_is_current && \
    probe_health gateway "${GATEWAY_URL}/health" && \
    gateway_runtime_is_current; then
    echo "Gateway already healthy at ${GATEWAY_URL}"
    return 0
  fi

  prepare_gateway_start || return 1

  local internal_token node_bin started_pid started_start_hash
  load_runtime_origin_env
  internal_token="$(read_backend_internal_token)" || {
    echo "MIRA_INTERNAL_API_TOKEN is required (or provide backend/.env with INTERNAL_API_TOKEN)." >&2
    return 1
  }
  node_bin="$(command -v node)"

  (
    cd "${GATEWAY_DIR}"
    nohup env -i \
      PATH="${PATH}" \
      HOME="${HOME}" \
      TMPDIR="${TMPDIR:-/tmp}" \
      LANG="${LANG:-en_US.UTF-8}" \
      NODE_ENV=development \
      PORT="${GATEWAY_PORT}" \
      OPENMAIC_UPSTREAM_URL="${OPENMAIC_URL}" \
      MIRA_BACKEND_INTERNAL_URL="${MIRA_BACKEND_INTERNAL_URL:-http://127.0.0.1:8000}" \
      MIRA_RUNTIME_PUBLIC_ORIGIN="${MIRA_RUNTIME_PUBLIC_ORIGIN}" \
      MIRA_STUDENT_WEB_ORIGIN="${MIRA_STUDENT_WEB_ORIGIN}" \
      MIRA_LOCAL_LAN_PRODUCTION_MODE="${MIRA_LOCAL_LAN_PRODUCTION_MODE:-0}" \
      MIRA_INTERNAL_API_TOKEN="${internal_token}" \
      "${node_bin}" src/server.mjs > "${GATEWAY_LOG}" 2>&1 &
    echo "$!" > "${GATEWAY_PID_FILE}"
  )
  unset internal_token
  started_pid="$(tr -d '[:space:]' < "${GATEWAY_PID_FILE}")"
  if [[ ! "${started_pid}" =~ ^[1-9][0-9]*$ ]] || \
    ! started_start_hash="$(process_start_hash "${started_pid}")"; then
    [[ "${started_pid}" =~ ^[1-9][0-9]*$ ]] && cleanup_failed_gateway_start "${started_pid}" "${started_start_hash:-invalid}"
    echo "Gateway failed to publish a verifiable process identity; inspect ${GATEWAY_LOG}." >&2
    return 1
  fi
  write_gateway_identity "${started_pid}" "${started_start_hash}"

  if ! wait_for_owned_gateway_health "${started_pid}" "${started_start_hash}" || \
    ! gateway_runtime_is_current; then
    cleanup_failed_gateway_start "${started_pid}" "${started_start_hash}"
    echo "Gateway failed to start; inspect ${GATEWAY_LOG}." >&2
    return 1
  fi
  echo "Gateway started at ${GATEWAY_URL} (log: ${GATEWAY_LOG})"
}

stop_pid() {
  local label="$1"
  local pid_file="$2"
  local pid i
  if [[ "${pid_file}" == "${OPENMAIC_PID_FILE}" ]]; then
    if [[ ! -e "${OPENMAIC_PID_FILE}" && ! -e "${OPENMAIC_MODE_FILE}" ]]; then
      if port_is_listening "${OPENMAIC_PORT}"; then
        echo "OpenMAIC has an unmanaged listener on port ${OPENMAIC_PORT}; it was not stopped." >&2
        return 1
      fi
      echo "${label} is not managed by this script"
      return 0
    fi
    if ! openmaic_recorded_process_identity_is_current; then
      if ! port_is_listening "${OPENMAIC_PORT}" && ! pid_is_running "${OPENMAIC_PID_FILE}"; then
        rm -f "${OPENMAIC_PID_FILE}" "${OPENMAIC_MODE_FILE}"
        echo "${label} removed stale process identity"
        return 0
      fi
      echo "OpenMAIC recorded identity is invalid; refusing to stop any live process." >&2
      return 1
    fi
    if port_is_listening "${OPENMAIC_PORT}" && \
      ! port_is_owned_by_tree "${OPENMAIC_PORT}" "${OPENMAIC_RECORD_PID}"; then
      echo "OpenMAIC port ${OPENMAIC_PORT} is not owned by the recorded production process; nothing was stopped." >&2
      return 1
    fi
    pid="${OPENMAIC_RECORD_PID}"
  elif [[ "${pid_file}" == "${GATEWAY_PID_FILE}" ]]; then
    if [[ ! -e "${GATEWAY_PID_FILE}" && ! -e "${GATEWAY_IDENTITY_FILE}" ]]; then
      if port_is_listening "${GATEWAY_PORT}"; then
        echo "Gateway has an unmanaged listener on port ${GATEWAY_PORT}; it was not stopped." >&2
        return 1
      fi
      echo "${label} is not managed by this script"
      return 0
    fi
    if ! gateway_recorded_process_identity_is_current; then
      if ! port_is_listening "${GATEWAY_PORT}" && ! pid_is_running "${GATEWAY_PID_FILE}"; then
        rm -f "${GATEWAY_PID_FILE}" "${GATEWAY_IDENTITY_FILE}"
        echo "${label} removed stale process identity"
        return 0
      fi
      echo "Gateway recorded identity is invalid; refusing to stop any live process." >&2
      return 1
    fi
    if port_is_listening "${GATEWAY_PORT}" && \
      ! port_is_owned_by_tree "${GATEWAY_PORT}" "${GATEWAY_RECORD_PID}"; then
      echo "Gateway port ${GATEWAY_PORT} is not owned by the recorded process; nothing was stopped." >&2
      return 1
    fi
    pid="${GATEWAY_RECORD_PID}"
  else
    if ! pid_is_running "${pid_file}"; then
      echo "${label} is not managed by this script"
      return 0
    fi
    pid="$(tr -cd '0-9' < "${pid_file}")"
  fi
  kill "${pid}"
  for ((i = 0; i < 20; i += 1)); do
    kill -0 "${pid}" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "${pid}" 2>/dev/null; then
    echo "${label} did not stop within 5 seconds; its identity record was preserved." >&2
    return 1
  fi
  rm -f "${pid_file}"
  if [[ "${pid_file}" == "${OPENMAIC_PID_FILE}" ]]; then
    rm -f "${OPENMAIC_MODE_FILE}"
  elif [[ "${pid_file}" == "${GATEWAY_PID_FILE}" ]]; then
    rm -f "${GATEWAY_IDENTITY_FILE}"
  fi
  echo "${label} stopped"
}

show_status() {
  local failed=0
  load_openmaic_provider_env
  load_openmaic_recovery_env
  load_openmaic_formal_citation_recovery_env
  load_openmaic_internal_token_env
  clear_openmaic_provider_env
  clear_openmaic_recovery_secret
  if openmaic_production_mode_is_current && \
    probe_health openmaic "${OPENMAIC_URL}/api/health" && \
    probe_formal_audio_health "${OPENMAIC_URL}/api/health?scope=formal-audio" "${OPENMAIC_INTERNAL_API_TOKEN}" && \
    probe_formal_provider_readiness_health "${OPENMAIC_URL}/api/health?scope=formal-provider-readiness" "${OPENMAIC_INTERNAL_API_TOKEN}" && \
    openmaic_production_mode_is_current; then
    echo "OpenMAIC 1.0.0 production runtime healthy at ${OPENMAIC_URL}"
  else
    echo "OpenMAIC unavailable at ${OPENMAIC_URL}"
    failed=1
  fi
  clear_openmaic_internal_token
  if gateway_runtime_is_current && \
    probe_health gateway "${GATEWAY_URL}/health" && \
    gateway_runtime_is_current; then
    echo "Gateway healthy at ${GATEWAY_URL} (openmaic@1.0.0)"
  else
    echo "Gateway unavailable at ${GATEWAY_URL}"
    failed=1
  fi
  echo "Logs: ${OPENMAIC_LOG} ${GATEWAY_LOG}"
  return "${failed}"
}

resolve_openmaic_contract_identity() {
  local expected_pid="${MIRA_OPENMAIC_EXPECTED_PID:-}"
  CONTRACT_OPENMAIC_PID=""
  CONTRACT_OPENMAIC_START_HASH=""
  CONTRACT_OPENMAIC_BUILD_ID_SHA256=""
  if [[ -n "${expected_pid}" ]]; then
    [[ "${expected_pid}" =~ ^[1-9][0-9]*$ ]] || return 1
    CONTRACT_OPENMAIC_PID="${expected_pid}"
    CONTRACT_OPENMAIC_START_HASH="$(process_start_hash "${expected_pid}")" || return 1
    CONTRACT_OPENMAIC_BUILD_ID_SHA256="$(openmaic_build_id_hash)" || return 1
  else
    openmaic_production_mode_is_current || return 1
    CONTRACT_OPENMAIC_PID="${OPENMAIC_RECORD_PID}"
    CONTRACT_OPENMAIC_START_HASH="${OPENMAIC_RECORD_START_HASH}"
    CONTRACT_OPENMAIC_BUILD_ID_SHA256="${OPENMAIC_RECORD_BUILD_ID_SHA256}"
  fi
  openmaic_production_process_is_current \
    "${CONTRACT_OPENMAIC_PID}" \
    "${CONTRACT_OPENMAIC_START_HASH}" \
    "${CONTRACT_OPENMAIC_BUILD_ID_SHA256}"
}

resolve_gateway_contract_identity() {
  local expected_pid="${MIRA_GATEWAY_EXPECTED_PID:-}"
  CONTRACT_GATEWAY_PID=""
  CONTRACT_GATEWAY_START_HASH=""
  if [[ -n "${expected_pid}" ]]; then
    [[ "${expected_pid}" =~ ^[1-9][0-9]*$ ]] || return 1
    CONTRACT_GATEWAY_PID="${expected_pid}"
    CONTRACT_GATEWAY_START_HASH="$(process_start_hash "${expected_pid}")" || return 1
  else
    gateway_runtime_is_current || return 1
    CONTRACT_GATEWAY_PID="${GATEWAY_RECORD_PID}"
    CONTRACT_GATEWAY_START_HASH="${GATEWAY_RECORD_START_HASH}"
  fi
  gateway_process_is_current "${CONTRACT_GATEWAY_PID}" "${CONTRACT_GATEWAY_START_HASH}"
}

show_runtime_contract_status() {
  local gateway_identity_ready=0 failed=0
  load_openmaic_provider_env
  load_openmaic_recovery_env
  load_openmaic_formal_citation_recovery_env
  load_openmaic_internal_token_env
  if resolve_gateway_contract_identity; then
    gateway_identity_ready=1
  fi
  clear_openmaic_provider_env
  clear_openmaic_recovery_secret
  if resolve_openmaic_contract_identity && \
    probe_health openmaic "${OPENMAIC_URL}/api/health" && \
    probe_formal_audio_health "${OPENMAIC_URL}/api/health?scope=formal-audio" "${OPENMAIC_INTERNAL_API_TOKEN}" && \
    probe_formal_provider_readiness_health "${OPENMAIC_URL}/api/health?scope=formal-provider-readiness" "${OPENMAIC_INTERNAL_API_TOKEN}" && \
    openmaic_production_process_is_current \
      "${CONTRACT_OPENMAIC_PID}" \
      "${CONTRACT_OPENMAIC_START_HASH}" \
      "${CONTRACT_OPENMAIC_BUILD_ID_SHA256}"; then
    echo "OpenMAIC 1.0.0 runtime contract healthy at ${OPENMAIC_URL}"
  else
    echo "OpenMAIC runtime contract unavailable at ${OPENMAIC_URL}"
    failed=1
  fi
  clear_openmaic_internal_token
  if [[ "${gateway_identity_ready}" == "1" ]] && \
    probe_health gateway "${GATEWAY_URL}/health" && \
    gateway_process_is_current "${CONTRACT_GATEWAY_PID}" "${CONTRACT_GATEWAY_START_HASH}"; then
    echo "Gateway healthy at ${GATEWAY_URL} (openmaic@1.0.0)"
  else
    echo "Gateway unavailable at ${GATEWAY_URL}"
    failed=1
  fi
  return "${failed}"
}

main() {
  case "${1:-start}" in
    start)
      start_openmaic
      start_gateway
      show_status
      ;;
    stop)
      stop_pid "Gateway" "${GATEWAY_PID_FILE}"
      stop_pid "OpenMAIC" "${OPENMAIC_PID_FILE}"
      ;;
    restart)
      stop_pid "Gateway" "${GATEWAY_PID_FILE}"
      stop_pid "OpenMAIC" "${OPENMAIC_PID_FILE}"
      start_openmaic
      start_gateway
      show_status
      ;;
    status)
      show_status
      ;;
    contract-status)
      show_runtime_contract_status
      ;;
    provider-status)
      show_provider_status
      ;;
    build-openmaic-production)
      build_openmaic_production
      ;;
    foreground-openmaic-production)
      run_openmaic_production_foreground
      ;;
    foreground-openmaic)
      run_openmaic_foreground
      ;;
    foreground-gateway)
      run_gateway_foreground
      ;;
    *)
      echo "Usage: $0 [start|stop|restart|status|contract-status|provider-status|build-openmaic-production|foreground-openmaic-production|foreground-openmaic|foreground-gateway]" >&2
      exit 2
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
