#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEARCH_TEST_DIR="$(mktemp -d)"
trap 'rm -rf "${SEARCH_TEST_DIR}"' EXIT
# No real credentials or network requests in this configuration check.
source "${SCRIPT_DIR}/native-runtime.sh"
model_provider_env_file() { printf '%s' "${SEARCH_TEST_DIR}/runtime.env"; }
provider_env_file() { printf '%s' "${SEARCH_TEST_DIR}/backend.env"; }
unset MIRA_OPENMAIC_ENABLE_WEB_SEARCH MIRA_OPENMAIC_WEB_SEARCH_PROVIDER \
  MIRA_OPENMAIC_BAIDU_API_KEY BAIDU_API_KEY MIRA_OPENMAIC_BAIDU_BASE_URL BAIDU_BASE_URL \
  MIRA_OPENMAIC_BRAVE_API_KEY BRAVE_API_KEY MIRA_OPENMAIC_BRAVE_BASE_URL BRAVE_BASE_URL
cat > "${SEARCH_TEST_DIR}/backend.env" <<'EOF'
MIRA_OPENMAIC_ENABLE_WEB_SEARCH=1
MIRA_OPENMAIC_WEB_SEARCH_PROVIDER=brave
BAIDU_API_KEY=backend-key-must-not-be-used
EOF
cat > "${SEARCH_TEST_DIR}/runtime.env" <<'EOF'
MIRA_OPENMAIC_ENABLE_WEB_SEARCH=1
MIRA_OPENMAIC_WEB_SEARCH_PROVIDER=baidu
BAIDU_API_KEY=bce-v3/test-only/not-a-secret
EOF
load_openmaic_web_search_env
[[ "${OPENMAIC_WEB_SEARCH_PROVIDER}" == baidu ]]
[[ "${OPENMAIC_BAIDU_API_KEY}" == bce-v3/test-only/not-a-secret ]]
[[ "${OPENMAIC_BAIDU_BASE_URL}" == https://qianfan.baidubce.com ]]
[[ "${OPENMAIC_BAIDU_ENABLED}" == true && "${OPENMAIC_BRAVE_ENABLED}" == false ]]
[[ -z "${OPENMAIC_BRAVE_API_KEY}" ]]

MIRA_OPENMAIC_ENABLE_WEB_SEARCH=0
load_openmaic_web_search_env
[[ -z "${OPENMAIC_BAIDU_API_KEY}" && "${OPENMAIC_BAIDU_ENABLED}" == false ]]
unset MIRA_OPENMAIC_ENABLE_WEB_SEARCH

cat > "${SEARCH_TEST_DIR}/runtime.env" <<'EOF'
MIRA_OPENMAIC_ENABLE_WEB_SEARCH=1
MIRA_OPENMAIC_WEB_SEARCH_PROVIDER=baidu
EOF
load_openmaic_web_search_env
[[ -z "${OPENMAIC_BAIDU_API_KEY}" ]]

MIRA_OPENMAIC_BAIDU_BASE_URL=https://example.invalid
if load_openmaic_web_search_env 2>/dev/null; then
  echo 'FAIL: unofficial credential destination accepted' >&2; exit 1
fi
[[ -z "${OPENMAIC_BAIDU_API_KEY}" && "${OPENMAIC_BAIDU_ENABLED}" == false ]]
unset MIRA_OPENMAIC_BAIDU_BASE_URL

MIRA_OPENMAIC_BAIDU_API_KEY=$'invalid\ncredential'
if load_openmaic_web_search_env 2>/dev/null; then
  echo 'FAIL: multiline credential accepted' >&2; exit 1
fi
unset MIRA_OPENMAIC_BAIDU_API_KEY

MIRA_OPENMAIC_WEB_SEARCH_PROVIDER=brave
MIRA_OPENMAIC_BRAVE_API_KEY=test-brave-key
load_openmaic_web_search_env
[[ "${OPENMAIC_WEB_SEARCH_PROVIDER}" == brave && "${OPENMAIC_BRAVE_ENABLED}" == true ]]
[[ "${OPENMAIC_BRAVE_API_KEY}" == test-brave-key && -z "${OPENMAIC_BAIDU_API_KEY}" ]]
[[ "${OPENMAIC_BAIDU_ENABLED}" == false ]]
echo 'Search configuration checks passed (Baidu, Brave, disabled, missing key, invalid origin/key).'
