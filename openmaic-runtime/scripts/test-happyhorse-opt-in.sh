#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_ROOT="$(mktemp -d)"
trap 'rm -rf "${TMP_ROOT}"' EXIT
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
MIRA_OPENMAIC_LOG_DIR="${TMP_ROOT}/logs"
source "${SCRIPT_DIR}/native-runtime.sh"
model_provider_env_file() { printf '%s' "${TMP_ROOT}/runtime.env"; }
MIRA_OPENMAIC_PROVIDER_ENV_FILE="${TMP_ROOT}/provider.env"
printf '%s\n' 'DASHSCOPE_API_KEY=test-shared-video-secret' > "${TMP_ROOT}/provider.env"
printf '%s\n' 'MIRA_OPENMAIC_ENABLE_HAPPYHORSE_VIDEO=0' > "${TMP_ROOT}/runtime.env"
load_openmaic_happyhorse_env
[[ -z "${OPENMAIC_VIDEO_HAPPYHORSE_API_KEY}" ]] || fail 'default-off loaded key'
printf '%s\n' 'MIRA_OPENMAIC_ENABLE_HAPPYHORSE_VIDEO=1' > "${TMP_ROOT}/runtime.env"
VIDEO_HAPPYHORSE_BASE_URL=https://unreviewed.invalid
VIDEO_HAPPYHORSE_MODELS=unreviewed-model
load_openmaic_happyhorse_env
[[ "${OPENMAIC_VIDEO_HAPPYHORSE_API_KEY}" == test-shared-video-secret ]] || fail 'shared key not reused'
[[ "${OPENMAIC_DEFAULT_VIDEO_PROVIDER}" == happyhorse ]] || fail 'formal video default missing'
[[ "${OPENMAIC_VIDEO_HAPPYHORSE_BASE_URL}" == https://dashscope.aliyuncs.com ]] || fail 'endpoint not pinned'
[[ "${OPENMAIC_VIDEO_HAPPYHORSE_MODELS}" == happyhorse-1.0-t2v ]] || fail 'model not pinned'
printf '%s\n' 'VIDEO_HAPPYHORSE_API_KEY=test-dedicated-video-secret' >> "${TMP_ROOT}/runtime.env"
load_openmaic_happyhorse_env
[[ "${OPENMAIC_VIDEO_HAPPYHORSE_API_KEY}" == test-dedicated-video-secret ]] || fail 'dedicated key not preferred'
MIRA_OPENMAIC_ENABLE_HAPPYHORSE_VIDEO=0
load_openmaic_happyhorse_env
[[ -z "${OPENMAIC_VIDEO_HAPPYHORSE_API_KEY}" ]] || fail 'disable retained key'
MIRA_OPENMAIC_ENABLE_HAPPYHORSE_VIDEO=2
if load_openmaic_happyhorse_env 2>/dev/null; then fail 'invalid opt-in accepted'; fi
MIRA_OPENMAIC_ENABLE_HAPPYHORSE_VIDEO=1
printf '\n' > "${TMP_ROOT}/runtime.env"
printf '\n' > "${TMP_ROOT}/provider.env"
if load_openmaic_happyhorse_env 2>/dev/null; then fail 'missing key accepted'; fi
for field in API_KEY BASE_URL MODELS; do
  assignment='VIDEO_HAPPYHORSE_'"${field}"'="${OPENMAIC_VIDEO_HAPPYHORSE_'"${field}"'}"'
  [[ "$(rg -F -c "${assignment}" "${SCRIPT_DIR}/native-runtime.sh")" == 3 ]] || fail 'launch path omitted video configuration'
done
[[ "$(rg -F -c 'DEFAULT_VIDEO_PROVIDER="${OPENMAIC_DEFAULT_VIDEO_PROVIDER}"' "${SCRIPT_DIR}/native-runtime.sh")" == 3 ]] || fail 'launch path omitted video default'
printf 'HappyHorse independent opt-in and shared-key contract passed\n'
