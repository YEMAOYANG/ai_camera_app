#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_SCRIPT="${SCRIPT_DIR}/native-runtime.sh"
TMP_ROOT="$(mktemp -d)"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  rm -rf "${TMP_ROOT}"
}
trap cleanup EXIT

printf '%s\n' \
  'IMAGE_QWEN_IMAGE_API_KEY=test-dedicated-image-secret-never-log' \
  'DASHSCOPE_API_KEY=test-shared-image-secret-never-log' \
  > "${TMP_ROOT}/provider.env"
printf '%s\n' 'DASHSCOPE_API_KEY=test-shared-image-secret-never-log' > "${TMP_ROOT}/fallback.env"

MIRA_OPENMAIC_LOG_DIR="${TMP_ROOT}/logs"
# shellcheck source=native-runtime.sh
source "${RUNTIME_SCRIPT}"

MIRA_OPENMAIC_PROVIDER_ENV_FILE="${TMP_ROOT}/provider.env"
MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=0
MIRA_OPENMAIC_AGENT_RUNTIME_ENABLED=0
MIRA_OPENMAIC_ENABLE_WEB_SEARCH=0
MIRA_OPENMAIC_ENABLE_QWEN_TTS=0
MIRA_OPENMAIC_ENABLE_QWEN_ASR=0

# Image generation is inert unless its independent opt-in is exact.
MIRA_OPENMAIC_ENABLE_QWEN_IMAGE=0
load_openmaic_provider_env
[[ -z "${OPENMAIC_DEFAULT_IMAGE_PROVIDER}" ]] || fail "default-off selected an image provider"
[[ -z "${OPENMAIC_IMAGE_QWEN_IMAGE_API_KEY}" ]] || fail "default-off loaded an image key"

MIRA_OPENMAIC_ENABLE_QWEN_IMAGE=1
load_openmaic_provider_env
[[ "${OPENMAIC_DEFAULT_IMAGE_PROVIDER}" == "qwen-image" ]] || fail "Qwen Image was not selected"
[[ "${OPENMAIC_IMAGE_QWEN_IMAGE_API_KEY}" == "test-dedicated-image-secret-never-log" ]] || fail "dedicated Qwen Image key was not preferred"
[[ "${OPENMAIC_IMAGE_QWEN_IMAGE_BASE_URL}" == "https://dashscope.aliyuncs.com" ]] || fail "Qwen Image root URL is not pinned"
[[ "${OPENMAIC_IMAGE_QWEN_IMAGE_MODELS}" == "qwen-image-max" ]] || fail "Qwen Image model is not pinned"

MIRA_OPENMAIC_PROVIDER_ENV_FILE="${TMP_ROOT}/fallback.env"
load_openmaic_provider_env
[[ "${OPENMAIC_IMAGE_QWEN_IMAGE_API_KEY}" == "test-shared-image-secret-never-log" ]] || fail "DashScope fallback was not loaded"

provider_status="$(show_provider_status)"
[[ "${provider_status}" == *'Image: enabled (qwen-image, qwen-image-max)'* ]] || fail "provider status omitted Qwen Image"
[[ "${provider_status}" != *'secret-never-log'* ]] || fail "provider status leaked the image key"

printf '\n' > "${TMP_ROOT}/missing-key.env"
MIRA_OPENMAIC_PROVIDER_ENV_FILE="${TMP_ROOT}/missing-key.env"
if load_openmaic_provider_env 2>/dev/null; then
  fail "image opt-in without a server key unexpectedly passed"
fi

MIRA_OPENMAIC_PROVIDER_ENV_FILE="${TMP_ROOT}/provider.env"
MIRA_OPENMAIC_ENABLE_QWEN_IMAGE=2
if load_openmaic_provider_env 2>/dev/null; then
  fail "non-binary image opt-in unexpectedly passed"
fi

# The three OpenMAIC runtime launches (production foreground, development
# foreground, detached production) must all cross the clean env boundary.
for assignment in \
  'DEFAULT_IMAGE_PROVIDER="${OPENMAIC_DEFAULT_IMAGE_PROVIDER}"' \
  'IMAGE_QWEN_IMAGE_API_KEY="${OPENMAIC_IMAGE_QWEN_IMAGE_API_KEY}"' \
  'IMAGE_QWEN_IMAGE_BASE_URL="${OPENMAIC_IMAGE_QWEN_IMAGE_BASE_URL}"' \
  'IMAGE_QWEN_IMAGE_MODELS="${OPENMAIC_IMAGE_QWEN_IMAGE_MODELS}"'; do
  count="$(grep -Fc "${assignment}" "${RUNTIME_SCRIPT}")"
  [[ "${count}" == "3" ]] || fail "${assignment} was not forwarded by all three runtime launch paths"
done

printf 'Qwen Image opt-in contract passed\n'
