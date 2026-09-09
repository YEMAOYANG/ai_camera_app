#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_SCRIPT="${SCRIPT_DIR}/native-runtime.sh"
LOCAL_TEST_STACK_SCRIPT="${SCRIPT_DIR}/local-test-stack.sh"
COMPOSE_FILE="${SCRIPT_DIR}/../docker-compose.yml"
TMP_ROOT="$(mktemp -d)"
IDENTITY_TEST_PID=""
IDENTITY_TEST_OTHER_PID=""
fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}
cleanup() {
  [[ -z "${IDENTITY_TEST_PID}" ]] || kill "${IDENTITY_TEST_PID}" 2>/dev/null || true
  [[ -z "${IDENTITY_TEST_OTHER_PID}" ]] || kill "${IDENTITY_TEST_OTHER_PID}" 2>/dev/null || true
  rm -rf "${TMP_ROOT}"
}
trap cleanup EXIT

cat > "${TMP_ROOT}/backend.env" <<'EOF'
APP_AI_PROVIDER=kimi
APP_AI_MODEL=kimi-k2.6
APP_AI_API_KEY=test-secret-never-log
APP_AI_BASE_URL=https://example.invalid/v1
TTS_QWEN_API_KEY=test-qwen-tts-secret-never-log
TTS_QWEN_BASE_URL=https://dashscope.example.invalid/api/v1
ASR_QWEN_API_KEY=test-qwen-asr-secret-never-log
ASR_QWEN_BASE_URL=https://dashscope.example.invalid/api/v1
OPENMAIC_FULL_RUNTIME_PUBLIC_URL=http://192.168.228.95:3101
INTERNAL_API_TOKEN=test-internal-token-never-log
OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED=1
OPENMAIC_DETERMINISTIC_RECOVERY_SOURCE_JOB_ID=uKQl3vMr4d
OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED=1
OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID=uKQl3vMr4d
OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID=omrec_383729f8f7f637dc1cdc65d4
OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED=1
OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID=omformal_e6b6986c631a548c9756037e
EOF

cat > "${TMP_ROOT}/openmaic.env" <<'EOF'
MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1
MIRA_OPENMAIC_MODEL_PROVIDER=deepseek
MIRA_OPENMAIC_MODEL=deepseek-v4-pro
MIRA_OPENMAIC_VERIFIER_MODEL=deepseek-v4-flash
DEEPSEEK_API_KEY=test-deepseek-secret-never-log
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODELS=deepseek-v4-pro,deepseek-v4-flash
MIRA_OPENMAIC_ENABLE_HAPPYHORSE_VIDEO=1
VIDEO_HAPPYHORSE_API_KEY=test-video-secret-never-log
EOF

cat > "${TMP_ROOT}/student-web.env" <<'EOF'
MIRA_STUDENT_WEB_PUBLIC_URL=http://192.168.228.95:3000
EOF

# shellcheck source=native-runtime.sh
source "${RUNTIME_SCRIPT}"

# Production pins model credentials to openmaic-runtime/.env. This local unit
# harness replaces only that path resolver so it never reads an operator key.
model_provider_env_file() {
  printf '%s' "${TMP_ROOT}/openmaic.env"
}

MIRA_BACKEND_ENV_FILE="${TMP_ROOT}/backend.env"
MIRA_STUDENT_WEB_ENV_FILE="${TMP_ROOT}/student-web.env"
load_runtime_origin_env
[[ "${MIRA_RUNTIME_PUBLIC_ORIGIN}" == "http://192.168.228.95:3101" ]] || fail "runtime public origin was not loaded"
[[ "${MIRA_STUDENT_WEB_ORIGIN}" == "http://192.168.228.95:3000" ]] || fail "Student Web origin was not loaded"

# Production builds accept only the two validated public origins and the
# script-owned public feature flags. A clean child environment must discard
# caller/provider secrets and unrelated NEXT_PUBLIC values.
FAKE_SOURCE_DIR="${TMP_ROOT}/fake-openmaic"
mkdir -p "${FAKE_SOURCE_DIR}/scripts" "${FAKE_SOURCE_DIR}/node_modules/.bin" \
  "${FAKE_SOURCE_DIR}/node_modules/next/dist/bin"
FAKE_SOURCE_DIR="$(cd "${FAKE_SOURCE_DIR}" && pwd -P)"
cat > "${FAKE_SOURCE_DIR}/package.json" <<'EOF'
{"name":"fake-openmaic","version":"1.0.0"}
EOF
cat > "${FAKE_SOURCE_DIR}/node_modules/next/package.json" <<'EOF'
{"name":"next","version":"16.1.2"}
EOF
cat > "${FAKE_SOURCE_DIR}/scripts/assert-vendor-maic-importer.mjs" <<'EOF'
// Intentionally empty: native-runtime.sh must preserve the upstream pre-build check.
EOF
cat > "${FAKE_SOURCE_DIR}/node_modules/next/dist/bin/next" <<'EOF'
const reviewedModelRoutes = {
  "maic-agent-driver": { model: "deepseek:deepseek-v4-pro", api: "openai-completions", thinking: { mode: "enabled", enabled: true } },
  "generate-classroom": { model: "deepseek:deepseek-v4-pro", thinking: { mode: "disabled", enabled: false } },
  "mira-courseware-creator": { model: "deepseek:deepseek-v4-pro", thinking: { mode: "disabled", enabled: false } },
  "mira-courseware-verifier": { model: "deepseek:deepseek-v4-flash", thinking: { mode: "disabled", enabled: false } },
  "web-search-query-rewrite": { model: "deepseek:deepseek-v4-pro", thinking: { mode: "disabled", enabled: false } },
};
const state = {
  argv: process.argv.slice(2),
  nodeEnv: process.env.NODE_ENV,
  nativeBuild: process.env.MIRA_OPENMAIC_NATIVE_BUILD,
  allowedFrameAncestors: process.env.ALLOWED_FRAME_ANCESTORS,
  editor: process.env.NEXT_PUBLIC_MAIC_EDITOR_ENABLED,
  editorRenderer: process.env.NEXT_PUBLIC_MAIC_EDITOR_RENDERER_ENABLED,
  workbench: process.env.NEXT_PUBLIC_PRO_WORKBENCH_ENABLED,
  workbenchDocuments: process.env.NEXT_PUBLIC_MIRA_WORKBENCH_DOCUMENTS_ENABLED,
  globalPersistence: process.env.NEXT_PUBLIC_PERSISTENCE,
  pptxImport: process.env.NEXT_PUBLIC_ENABLE_PPTX_IMPORT,
  videoExport: process.env.NEXT_PUBLIC_ENABLE_VIDEO_EXPORT,
  playback: process.env.NEXT_PUBLIC_MAIC_PLAYBACK_RENDERER_ENABLED,
  piChat: process.env.NEXT_PUBLIC_PI_CHAT_ENABLED,
  providerSecretPresent: Boolean(process.env.APP_AI_API_KEY || process.env.DEEPSEEK_API_KEY),
  persistenceTokenPresent: Boolean(process.env.NEXT_PUBLIC_PERSISTENCE_TOKEN),
  serverPersistenceTokenPresent: Boolean(process.env.PERSISTENCE_DEV_TOKEN),
  internalTokenPresent: Boolean(process.env.MIRA_INTERNAL_API_TOKEN),
  strictModelPresent: Boolean(process.env.DEFAULT_MODEL),
  modelRoutesPresent: Boolean(process.env.MODEL_ROUTES),
  reviewedModelRoutes: require("node:util").isDeepStrictEqual(
    JSON.parse(process.env.MODEL_ROUTES || "null"), reviewedModelRoutes,
  ),
  structuredScenePolicy: process.env.MIRA_OPENMAIC_STRUCTURED_SCENE_POLICY,
  strictTtsPresent: Boolean(process.env.TTS_QWEN_API_KEY),
  strictAsrPresent: Boolean(process.env.ASR_QWEN_API_KEY),
  videoKeyPresent: Boolean(process.env.VIDEO_HAPPYHORSE_API_KEY),
  videoDefault: process.env.DEFAULT_VIDEO_PROVIDER,
  videoModel: process.env.VIDEO_HAPPYHORSE_MODELS,
  videoBase: process.env.VIDEO_HAPPYHORSE_BASE_URL,
  recoveryEnabled: process.env.MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED,
  ttsRecoveryEnabled: process.env.MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED,
  formalCitationRecoveryEnabled: process.env.MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED,
  formalCitationRecoverySourceJobId: process.env.MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID,
  formalCitationRecoveryPatchSha256: process.env.MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256,
  privatePort: process.env.MIRA_OPENMAIC_PRIVATE_PORT,
  qualityBase: process.env.MIRA_FORMAL_QA_BASE_URL,
  qualityBrowser: process.env.MIRA_FORMAL_QA_BROWSER_PATH,
};
process.stdout.write(JSON.stringify(state));
EOF
chmod +x "${FAKE_SOURCE_DIR}/node_modules/next/dist/bin/next"
touch "${FAKE_SOURCE_DIR}/node_modules/.bin/next"
chmod +x "${FAKE_SOURCE_DIR}/node_modules/.bin/next"

ORIGINAL_SOURCE_DIR="${SOURCE_DIR}"
SOURCE_DIR="${FAKE_SOURCE_DIR}"
bootstrap_openmaic_source() { :; }
APP_AI_API_KEY=test-build-provider-secret-never-log
NEXT_PUBLIC_PERSISTENCE_TOKEN=test-build-public-secret-never-log
printf 'APP_AI_API_KEY=dotenv-build-secret-never-log\n' > "${SOURCE_DIR}/.env.production.local"
if reject_openmaic_build_dotenv_files 2>/dev/null; then
  echo "production build unexpectedly accepted a Next.js dotenv file" >&2
  exit 1
fi
rm -f "${SOURCE_DIR}/.env.production.local"
reject_openmaic_build_dotenv_files
build_output="$(build_openmaic_production)"
[[ "${build_output}" == *'"argv":["build","--webpack"]'* ]] || fail "production build did not invoke the reviewed Next webpack build"
[[ "${build_output}" == *'"nodeEnv":"production"'* ]] || fail "production build did not set NODE_ENV=production"
[[ "${build_output}" == *'"nativeBuild":"1"'* ]] || fail "production build did not set native-build boundary"
[[ "${build_output}" == *'"allowedFrameAncestors":"http://192.168.228.95:3000"'* ]] || fail "production build did not constrain frame ancestors"
[[ "${build_output}" == *'"editor":"true"'* ]] || fail "production build did not enable the private editor"
[[ "${build_output}" == *'"editorRenderer":"true"'* ]] || fail "production build did not enable the official editor renderer"
[[ "${build_output}" == *'"workbench":"true"'* ]] || fail "production build did not enable the Pro workbench"
[[ "${build_output}" == *'"workbenchDocuments":"true"'* ]] || fail "production build did not enable scoped document persistence"
[[ "${build_output}" != *'"globalPersistence":'* ]] || fail "production build enabled global learner persistence"
[[ "${build_output}" == *'"pptxImport":"true"'* ]] || fail "production build did not enable PPTX import"
[[ "${build_output}" == *'"videoExport":"true"'* ]] || fail "production build did not enable the export entry"
[[ "${build_output}" == *'"playback":"true"'* ]] || fail "production build did not enable playback"
[[ "${build_output}" == *'"piChat":"true"'* ]] || fail "production build did not enable Pi chat"
[[ "${build_output}" == *'"providerSecretPresent":false'* ]] || fail "production build received a provider secret"
[[ "${build_output}" == *'"persistenceTokenPresent":false'* ]] || fail "production build received a persistence token"
[[ "${build_output}" == *'"serverPersistenceTokenPresent":false'* ]] || fail "production build received a private persistence token"
[[ "${build_output}" == *'"internalTokenPresent":false'* ]] || fail "production build received an internal token"
[[ "${build_output}" == *'"modelRoutesPresent":false'* ]] || fail "production build received runtime model routes"
[[ "${build_output}" == *'"videoKeyPresent":false'* ]] || fail "production build received video credential"
[[ "${build_output}" != *'secret-never-log'* ]] || fail "production build output leaked a secret"

if require_openmaic_production_build 2>/dev/null; then
  echo "missing .next/BUILD_ID unexpectedly passed production start gate" >&2
  exit 1
fi
mkdir -p "${SOURCE_DIR}/.next"
printf 'fake-reviewed-build\n' > "${SOURCE_DIR}/.next/BUILD_ID"
require_openmaic_production_build
production_output="$(
  OPENMAIC_SOURCE_DIR="${FAKE_SOURCE_DIR}" \
  MIRA_BACKEND_ENV_FILE="${TMP_ROOT}/backend.env" \
  MIRA_STUDENT_WEB_ENV_FILE="${TMP_ROOT}/student-web.env" \
  MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1 \
  MIRA_OPENMAIC_ENABLE_QWEN_TTS=1 \
  MIRA_OPENMAIC_ENABLE_QWEN_ASR=1 \
  MIRA_OPENMAIC_AGENT_RUNTIME_ENABLED=1 \
  MIRA_OPENMAIC_AGENT_DATABASE_URL=postgresql://test.invalid/private-authoring \
  MODEL_ROUTES='{"scene-content":"attacker:model"}' \
  OPENMAIC_MODEL_ROUTES='{"scene-content":"attacker:model"}' \
  MIRA_OPENMAIC_STRUCTURED_SCENE_POLICY=attacker-controlled \
  bash -c 'source "$1"; MIRA_TEST_OPENMAIC_ENV="$2"; model_provider_env_file() { printf "%s" "${MIRA_TEST_OPENMAIC_ENV}"; }; run_openmaic_production_foreground' _ "${RUNTIME_SCRIPT}" "${TMP_ROOT}/openmaic.env"
)"
[[ "${production_output}" == *'"argv":["start","--hostname","127.0.0.1","--port","3100"]'* ]] || fail "production foreground did not invoke Next start on 3100"
[[ "${production_output}" == *'"nodeEnv":"production"'* ]] || fail "production foreground did not set NODE_ENV=production"
[[ "${production_output}" == *'"serverPersistenceTokenPresent":true'* ]] || fail "production foreground omitted the private document route prerequisite"
[[ "${production_output}" == *'"persistenceTokenPresent":false'* ]] || fail "production foreground exposed a public persistence token"
[[ "${production_output}" != *'"globalPersistence":'* ]] || fail "production foreground enabled learner HTTP persistence"
[[ "${production_output}" == *'"strictModelPresent":true'* ]] || fail "production foreground omitted the model contract"
[[ "${production_output}" == *'"reviewedModelRoutes":true'* ]] || fail "production foreground did not replace caller routes with the exact reviewed model routes"
[[ "${production_output}" == *'"structuredScenePolicy":"deepseek-v4-pro-flash-v1"'* ]] || fail "production foreground accepted a caller structured scene policy"
[[ "${production_output}" == *'"strictTtsPresent":true'* ]] || fail "production foreground omitted the TTS contract"
[[ "${production_output}" == *'"strictAsrPresent":true'* ]] || fail "production foreground omitted the ASR contract"
[[ "${production_output}" == *'"videoKeyPresent":true'* ]] || fail "production foreground omitted video credential"
[[ "${production_output}" == *'"videoDefault":"happyhorse"'* ]] || fail "production foreground omitted formal video default"
[[ "${production_output}" == *'"videoModel":"happyhorse-1.0-t2v"'* ]] || fail "production foreground omitted formal video model"
[[ "${production_output}" == *'"videoBase":"https://dashscope.aliyuncs.com"'* ]] || fail "production foreground omitted pinned video origin"
[[ "${production_output}" == *'"internalTokenPresent":true'* ]] || fail "production foreground omitted the internal token"
[[ "${production_output}" == *'"recoveryEnabled":"1"'* ]] || fail "production foreground omitted deterministic recovery"
[[ "${production_output}" == *'"ttsRecoveryEnabled":"1"'* ]] || fail "production foreground omitted TTS recovery"
[[ "${production_output}" == *'"formalCitationRecoveryEnabled":"1"'* ]] || fail "production foreground omitted formal citation recovery"
[[ "${production_output}" == *'"formalCitationRecoverySourceJobId":"omformal_e6b6986c631a548c9756037e"'* ]] || fail "production foreground forwarded the wrong formal citation recovery source"
[[ "${production_output}" == *'"formalCitationRecoveryPatchSha256":"'* ]] || fail "production foreground omitted the formal citation recovery patch hash"
[[ "${production_output}" == *'"privatePort":"3100"'* ]] || fail "production foreground omitted the private loopback port"
[[ "${production_output}" == *'"qualityBase":"http://127.0.0.1:3100"'* ]] || fail "quality renderer must use this private runtime"
[[ "${production_output}" == *'"qualityBrowser":"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"'* ]] || fail "quality browser path missing"
[[ "${production_output}" != *'secret-never-log'* ]] || fail "production foreground output leaked a provider secret"
[[ "${production_output}" != *'internal-token-never-log'* ]] || fail "production foreground output leaked the internal token"

# A healthy HTTP listener is never enough to claim production ownership. The
# v2 record binds the exact process start, cwd, Next production command, build,
# and listening process tree. This catches PID reuse and an old dev server that
# happens to answer the same health route.
IDENTITY_PORT_FILE="${TMP_ROOT}/identity-port"
(
  cd "${FAKE_SOURCE_DIR}"
  exec "$(command -v node)" -e '
    const fs = require("fs");
    const http = require("http");
    process.title = "next-server (v16.1.2)";
    const server = http.createServer((_req, res) => {
      res.writeHead(200, {"content-type": "application/json"});
      res.end("{\"status\":\"ok\"}");
    });
    server.listen(0, "127.0.0.1", () => fs.writeFileSync(process.argv[1], String(server.address().port)));
  ' "${IDENTITY_PORT_FILE}"
) &
IDENTITY_TEST_PID="$!"
for _ in $(seq 1 100); do
  [[ -s "${IDENTITY_PORT_FILE}" ]] && break
  sleep 0.05
done
[[ -s "${IDENTITY_PORT_FILE}" ]] || fail "identity test listener did not publish its port"

ORIGINAL_OPENMAIC_PORT="${OPENMAIC_PORT}"
ORIGINAL_OPENMAIC_URL="${OPENMAIC_URL}"
ORIGINAL_OPENMAIC_PID_FILE="${OPENMAIC_PID_FILE}"
ORIGINAL_OPENMAIC_MODE_FILE="${OPENMAIC_MODE_FILE}"
OPENMAIC_PORT="$(tr -d '[:space:]' < "${IDENTITY_PORT_FILE}")"
OPENMAIC_URL="http://127.0.0.1:${OPENMAIC_PORT}"
OPENMAIC_PID_FILE="${TMP_ROOT}/identity-openmaic.pid"
OPENMAIC_MODE_FILE="${TMP_ROOT}/identity-openmaic.mode"
printf '%s\n' "${IDENTITY_TEST_PID}" > "${OPENMAIC_PID_FILE}"
identity_start_hash="$(process_start_hash "${IDENTITY_TEST_PID}")"
identity_build_hash="$(openmaic_build_id_hash)"
write_openmaic_mode "${IDENTITY_TEST_PID}" "${identity_start_hash}" "${identity_build_hash}" "16.1.2"
openmaic_production_mode_is_current || fail "valid production identity was rejected"

cp "${OPENMAIC_MODE_FILE}" "${OPENMAIC_MODE_FILE}.valid"
sed 's/^pid=.*/pid=12x34/' "${OPENMAIC_MODE_FILE}.valid" > "${OPENMAIC_MODE_FILE}"
if read_openmaic_mode; then
  echo "non-numeric PID unexpectedly passed strict identity parsing" >&2
  exit 1
fi
printf 'version=1\nmode=production\npid=%s\n' "${IDENTITY_TEST_PID}" > "${OPENMAIC_MODE_FILE}"
if read_openmaic_mode; then
  echo "legacy v1 marker unexpectedly passed the production identity gate" >&2
  exit 1
fi
cp "${OPENMAIC_MODE_FILE}.valid" "${OPENMAIC_MODE_FILE}"

sed "s/^start_hash=.*/start_hash=$(printf '0%.0s' {1..64})/" \
  "${OPENMAIC_MODE_FILE}" > "${OPENMAIC_MODE_FILE}.bad"
mv "${OPENMAIC_MODE_FILE}.bad" "${OPENMAIC_MODE_FILE}"
if openmaic_production_mode_is_current; then
  echo "PID reuse simulation unexpectedly passed the production identity gate" >&2
  exit 1
fi
write_openmaic_mode "${IDENTITY_TEST_PID}" "${identity_start_hash}" "${identity_build_hash}" "16.1.2"

printf 'different-build\n' > "${SOURCE_DIR}/.next/BUILD_ID"
openmaic_recorded_process_identity_is_current || fail "build change invalidated process ownership identity"
if openmaic_production_mode_is_current; then
  echo "changed BUILD_ID unexpectedly passed the production identity gate" >&2
  exit 1
fi
printf 'fake-reviewed-build\n' > "${SOURCE_DIR}/.next/BUILD_ID"
write_openmaic_mode "${IDENTITY_TEST_PID}" "${identity_start_hash}" "$(openmaic_build_id_hash)" "16.1.2"
openmaic_production_mode_is_current || fail "restored production identity was rejected"

if prepare_openmaic_start 2>/dev/null; then
  echo "occupied OpenMAIC port unexpectedly passed the pre-start ownership gate" >&2
  exit 1
fi

(
  cd "${FAKE_SOURCE_DIR}"
  exec "$(command -v node)" -e 'process.title = "next-server (v16.1.2)"; setInterval(() => {}, 1000)'
) &
IDENTITY_TEST_OTHER_PID="$!"
other_start_hash="$(process_start_hash "${IDENTITY_TEST_OTHER_PID}")"
printf '%s\n' "${IDENTITY_TEST_OTHER_PID}" > "${OPENMAIC_PID_FILE}"
write_openmaic_mode "${IDENTITY_TEST_OTHER_PID}" "${other_start_hash}" "$(openmaic_build_id_hash)" "16.1.2"
if openmaic_production_mode_is_current; then
  echo "production-looking PID without listener ownership unexpectedly passed" >&2
  exit 1
fi

kill "${IDENTITY_TEST_OTHER_PID}" 2>/dev/null || true
wait "${IDENTITY_TEST_OTHER_PID}" 2>/dev/null || true
IDENTITY_TEST_OTHER_PID=""
kill "${IDENTITY_TEST_PID}" 2>/dev/null || true
wait "${IDENTITY_TEST_PID}" 2>/dev/null || true
IDENTITY_TEST_PID=""

# Exercise the real detached start function far enough to commit a production
# marker. Process/network probes are replaced with deterministic test doubles;
# this specifically catches unbound locals or marker-order regressions that a
# source-string assertion cannot see.
(
  SOURCE_DIR="${FAKE_SOURCE_DIR}"
  LOG_DIR="${TMP_ROOT}/mock-detached"
  mkdir -p "${LOG_DIR}"
  START_ORDER_LOG="${LOG_DIR}/start-order.log"
  : > "${START_ORDER_LOG}"
  OPENMAIC_LOG="${LOG_DIR}/openmaic.log"
  OPENMAIC_PID_FILE="${LOG_DIR}/openmaic.pid"
  OPENMAIC_MODE_FILE="${LOG_DIR}/openmaic.mode"
  OPENMAIC_PORT=53991
  OPENMAIC_URL="http://127.0.0.1:${OPENMAIC_PORT}"
  MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1
  MIRA_OPENMAIC_ENABLE_QWEN_TTS=1
  MIRA_OPENMAIC_ENABLE_QWEN_ASR=1
  MIRA_OPENMAIC_AGENT_RUNTIME_ENABLED=1
  MIRA_OPENMAIC_AGENT_DATABASE_URL=postgresql://test.invalid/private-authoring
  export MODEL_ROUTES='{"scene-content":"attacker:model"}'
  export OPENMAIC_MODEL_ROUTES='{"scene-content":"attacker:model"}'
  export MIRA_OPENMAIC_STRUCTURED_SCENE_POLICY=attacker-controlled
  process_start_hash() { printf '%064d' 0 | tr '0' 'a'; }
  prepare_openmaic_start() { rm -f "${OPENMAIC_PID_FILE}" "${OPENMAIC_MODE_FILE}"; }
  write_openmaic_mode() {
    local pid="$1"
    local start_hash="$2"
    local build_id_sha256="$3"
    local next_version="$4"
    local mode="${5:-production}"
    case "${mode}" in
      pending)
        [[ ! -e "${OPENMAIC_MODE_FILE}" ]] || fail "pending identity was not the first marker commit"
        printf 'pending-commit\n' >> "${START_ORDER_LOG}"
        ;;
      production)
        grep -Fxq 'provider-health-complete' "${START_ORDER_LOG}" || fail "production identity was committed before Provider readiness"
        printf 'production-commit\n' >> "${START_ORDER_LOG}"
        ;;
      *)
        fail "detached start wrote unexpected identity mode: ${mode}"
        ;;
    esac
    {
      printf 'version=2\n'
      printf 'service=openmaic\n'
      printf 'mode=%s\n' "${mode}"
      printf 'pid=%s\n' "${pid}"
      printf 'start_hash=%s\n' "${start_hash}"
      printf 'next_version=%s\n' "${next_version}"
      printf 'build_id_sha256=%s\n' "${build_id_sha256}"
    } > "${OPENMAIC_MODE_FILE}"
  }
  assert_pending_marker() {
    grep -Fq 'mode=pending' "${OPENMAIC_MODE_FILE}" || fail "$1 ran before the pending identity was committed"
    if grep -Fq 'mode=production' "${OPENMAIC_MODE_FILE}"; then
      fail "$1 ran after production identity was committed"
    fi
  }
  wait_for_owned_openmaic_health() {
    assert_pending_marker "owned health"
    printf 'owned-health-complete\n' >> "${START_ORDER_LOG}"
  }
  wait_for_formal_audio_health() {
    assert_pending_marker "formal audio health"
    grep -Fxq 'owned-health-complete' "${START_ORDER_LOG}" || fail "formal audio health ran before owned health"
    printf 'audio-health-complete\n' >> "${START_ORDER_LOG}"
  }
  wait_for_formal_provider_readiness_health() {
    assert_pending_marker "Provider readiness health"
    grep -Fxq 'audio-health-complete' "${START_ORDER_LOG}" || fail "Provider readiness ran before formal audio health"
    printf 'provider-health-complete\n' >> "${START_ORDER_LOG}"
  }
  openmaic_production_process_is_current() { return 0; }
  openmaic_production_mode_is_current() {
    [[ -f "${OPENMAIC_MODE_FILE}" ]] && grep -Fq 'mode=production' "${OPENMAIC_MODE_FILE}"
  }
  start_openmaic || fail "mock detached production start failed"
  grep -Fq 'version=2' "${OPENMAIC_MODE_FILE}" || fail "detached start did not write a v2 identity"
  grep -Fq 'mode=production' "${OPENMAIC_MODE_FILE}" || fail "detached start did not finish with a production identity"
  grep -Fq 'next_version=16.1.2' "${OPENMAIC_MODE_FILE}" || fail "detached start identity has the wrong Next version"
  expected_start_order="$(printf '%s\n' pending-commit owned-health-complete audio-health-complete provider-health-complete production-commit)"
  actual_start_order="$(cat "${START_ORDER_LOG}")"
  [[ "${actual_start_order}" == "${expected_start_order}" ]] || fail "detached start identity/health order was incorrect: ${actual_start_order}"
  for _ in $(seq 1 100); do
    grep -Fq '"reviewedModelRoutes":true' "${OPENMAIC_LOG}" 2>/dev/null && break
    sleep 0.05
  done
  grep -Fq '"reviewedModelRoutes":true' "${OPENMAIC_LOG}" || fail "detached start did not replace caller routes with the exact reviewed model routes"
  grep -Fq '"structuredScenePolicy":"deepseek-v4-pro-flash-v1"' "${OPENMAIC_LOG}" || fail "detached start accepted a caller structured scene policy"
)

# The two native-service safety checks are an explicit AND even when the
# aggregate is called inside `if ! ...`, where Bash disables implicit errexit.
(
  # shellcheck source=local-test-stack.sh
  source "${LOCAL_TEST_STACK_SCRIPT}"
  safety_call_count=0
  validate_native_service_safety() {
    safety_call_count=$((safety_call_count + 1))
    [[ "${safety_call_count}" != "1" ]]
  }
  if validate_native_stack_safety; then
    echo "OpenMAIC safety failure was masked by the later Gateway check" >&2
    exit 1
  fi
  [[ "${safety_call_count}" == "1" ]] || fail "native safety aggregate continued after the first failure"
)

# A recycled Gateway PID must never be killed from a stale numeric pid file.
(
  GATEWAY_PID_FILE="${TMP_ROOT}/stale-gateway.pid"
  GATEWAY_IDENTITY_FILE="${TMP_ROOT}/stale-gateway.identity"
  GATEWAY_PORT=53992
  sleep 30 &
  unrelated_pid="$!"
  trap 'kill "${unrelated_pid}" 2>/dev/null || true' EXIT
  printf '%s\n' "${unrelated_pid}" > "${GATEWAY_PID_FILE}"
  if stop_pid Gateway "${GATEWAY_PID_FILE}" 2>/dev/null; then
    echo "stale Gateway PID unexpectedly authorized a stop" >&2
    exit 1
  fi
  kill -0 "${unrelated_pid}" || fail "stale Gateway stop killed an unrelated process"
  kill "${unrelated_pid}"
  wait "${unrelated_pid}" 2>/dev/null || true
  trap - EXIT
)

OPENMAIC_PORT="${ORIGINAL_OPENMAIC_PORT}"
OPENMAIC_URL="${ORIGINAL_OPENMAIC_URL}"
OPENMAIC_PID_FILE="${ORIGINAL_OPENMAIC_PID_FILE}"
OPENMAIC_MODE_FILE="${ORIGINAL_OPENMAIC_MODE_FILE}"
SOURCE_DIR="${ORIGINAL_SOURCE_DIR}"
unset ORIGINAL_SOURCE_DIR APP_AI_API_KEY NEXT_PUBLIC_PERSISTENCE_TOKEN

printf 'OPENMAIC_FULL_RUNTIME_PUBLIC_URL=http://user:pass@192.168.228.95:3101\n' > "${TMP_ROOT}/bad-backend.env"
MIRA_BACKEND_ENV_FILE="${TMP_ROOT}/bad-backend.env"
if load_runtime_origin_env 2>/dev/null; then
  echo "credential-bearing runtime origin unexpectedly passed" >&2
  exit 1
fi
MIRA_BACKEND_ENV_FILE="${TMP_ROOT}/backend.env"
unset MIRA_RUNTIME_PUBLIC_ORIGIN MIRA_STUDENT_WEB_ORIGIN

MIRA_BACKEND_ENV_FILE="${TMP_ROOT}/backend.env"
MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=0
MIRA_OPENMAIC_ENABLE_QWEN_TTS=0
MIRA_OPENMAIC_ENABLE_QWEN_ASR=0
load_openmaic_provider_env
[[ -z "${OPENMAIC_DEFAULT_MODEL}" ]]
[[ -z "${OPENMAIC_TTS_QWEN_API_KEY}" ]]
[[ -z "${OPENMAIC_ASR_QWEN_API_KEY}" ]]

MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1
MIRA_OPENMAIC_ENABLE_QWEN_TTS=1
MIRA_OPENMAIC_ENABLE_QWEN_ASR=1
load_openmaic_provider_env
[[ "${OPENMAIC_DEFAULT_MODEL}" == "deepseek:deepseek-v4-pro" ]]
[[ "${OPENMAIC_DEEPSEEK_API_KEY}" == "test-deepseek-secret-never-log" ]]
[[ "${OPENMAIC_DEEPSEEK_BASE_URL}" == "https://api.deepseek.com/v1" ]]
[[ "${OPENMAIC_DEEPSEEK_MODELS}" == "deepseek-v4-pro,deepseek-v4-flash" ]]
[[ "${OPENMAIC_COURSEWARE_VERIFIER_MODEL}" == "deepseek-v4-flash" ]]
# Switching services keeps official credentials intact and fails closed when
# free-tier protection or a trusted Bailian endpoint is missing.
(
  cp "${TMP_ROOT}/openmaic.env" "${TMP_ROOT}/bailian.env"
  model_provider_env_file() { printf '%s' "${TMP_ROOT}/bailian.env"; }
  cat >> "${TMP_ROOT}/bailian.env" <<'EOF'
DEEPSEEK_SERVICE=bailian
BAILIAN_DEEPSEEK_API_KEY=test-bailian-key-never-log
BAILIAN_DEEPSEEK_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EOF
  if load_openmaic_model_env 2>/dev/null; then fail 'missing free-tier protection accepted'; fi
  printf '%s\n' 'BAILIAN_DEEPSEEK_FREE_TIER_ONLY_CONFIRMED=1' >> "${TMP_ROOT}/bailian.env"
  load_openmaic_model_env
  [[ "${OPENMAIC_DEEPSEEK_API_KEY}" == test-bailian-key-never-log ]] || fail 'Bailian key not selected'
  [[ "${OPENMAIC_DEEPSEEK_BASE_URL}" == https://dashscope.aliyuncs.com/compatible-mode/v1 ]] || fail 'Bailian base not selected'
  [[ "$(read_env_value DEEPSEEK_API_KEY "${TMP_ROOT}/bailian.env")" == test-deepseek-secret-never-log ]] || fail 'official key overwritten'
  sed -i.bak 's|DEEPSEEK_SERVICE=bailian|DEEPSEEK_SERVICE=official|' "${TMP_ROOT}/bailian.env"
  load_openmaic_model_env
  [[ "${OPENMAIC_DEEPSEEK_API_KEY}" == test-deepseek-secret-never-log ]] || fail 'official rollback lost key'
  sed -i.bak 's|DEEPSEEK_SERVICE=official|DEEPSEEK_SERVICE=bailian|; s|https://dashscope.aliyuncs.com/compatible-mode/v1|https://untrusted.invalid/compatible-mode/v1|' "${TMP_ROOT}/bailian.env"
  if load_openmaic_model_env 2>/dev/null; then fail 'untrusted Bailian endpoint accepted'; fi
)

[[ "${OPENMAIC_TTS_QWEN_API_KEY}" == "test-qwen-tts-secret-never-log" ]]
[[ "${OPENMAIC_TTS_QWEN_MODELS}" == "qwen3-tts-flash" ]]
[[ "${OPENMAIC_TTS_QWEN_VOICE}" == "Serena" ]]
[[ "${OPENMAIC_REQUIRE_QWEN_TTS}" == "1" ]]
[[ "${OPENMAIC_ASR_QWEN_API_KEY}" == "test-qwen-asr-secret-never-log" ]]
[[ "${OPENMAIC_ASR_QWEN_MODELS}" == "qwen3-asr-flash" ]]
[[ "${OPENMAIC_REQUIRE_QWEN_ASR}" == "1" ]]

# Authoring documents retain the existing server route guard. Its private token
# is process-local and distinct from the internal bridge and browser identity.
(
  MIRA_OPENMAIC_AGENT_RUNTIME_ENABLED=1
  MIRA_OPENMAIC_AGENT_DATABASE_URL=postgresql://test.invalid/private-authoring
  load_openmaic_agent_runtime_env
  [[ "${OPENMAIC_PERSISTENCE_DEV_TOKEN}" =~ ^[a-f0-9]{64}$ ]] || fail "private persistence token was not generated"
  first_private_token="${OPENMAIC_PERSISTENCE_DEV_TOKEN}"
  load_openmaic_agent_runtime_env
  [[ "${OPENMAIC_PERSISTENCE_DEV_TOKEN}" != "${first_private_token}" ]] || fail "private persistence token was reused"
  clear_openmaic_provider_env
  [[ -z "${OPENMAIC_PERSISTENCE_DEV_TOKEN}" ]] || fail "private persistence token survived provider cleanup"
)

load_openmaic_internal_token_env
[[ "${OPENMAIC_INTERNAL_API_TOKEN}" == "test-internal-token-never-log" ]]
clear_openmaic_internal_token
[[ -z "${OPENMAIC_INTERNAL_API_TOKEN}" ]]

load_openmaic_recovery_env
load_openmaic_formal_citation_recovery_env
[[ "${OPENMAIC_RECOVERY_ENABLED}" == "1" ]]
[[ "${OPENMAIC_RECOVERY_SOURCE_JOB_ID}" == "uKQl3vMr4d" ]]
[[ "${OPENMAIC_RECOVERY_PATCH_SHA256}" =~ ^[a-f0-9]{64}$ ]]
[[ "${OPENMAIC_RECOVERY_INTERNAL_TOKEN}" == "test-internal-token-never-log" ]]
[[ "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED}" == "1" ]]
[[ "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID}" == "uKQl3vMr4d" ]]
[[ "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID}" == "omrec_383729f8f7f637dc1cdc65d4" ]]
[[ "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256}" =~ ^[a-f0-9]{64}$ ]]
[[ "${OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED}" == "1" ]]
[[ "${OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID}" == "omformal_e6b6986c631a548c9756037e" ]]
[[ "${OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256}" =~ ^[a-f0-9]{64}$ ]]
expected_recovery_patch_sha="$(shasum -a 256 "${SCRIPT_DIR}/../patches/0007-mira-sample-deterministic-recovery.patch" | awk '{print $1}')"
[[ "${OPENMAIC_RECOVERY_PATCH_SHA256}" == "${expected_recovery_patch_sha}" ]]
expected_tts_credential_patch_sha="$(shasum -a 256 "${SCRIPT_DIR}/../patches/0008-mira-sample-tts-credential-recovery.patch" | awk '{print $1}')"
[[ "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256}" == "${expected_tts_credential_patch_sha}" ]]
expected_formal_citation_recovery_patch_sha="$(shasum -a 256 "${SCRIPT_DIR}/../patches/0043-mira-formal-citation-recovery.patch" | awk '{print $1}')"
[[ "${OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256}" == "${expected_formal_citation_recovery_patch_sha}" ]]
formal_audio_patch="${SCRIPT_DIR}/../patches/0013-mira-formal-subject-qwen-audio.patch"
[[ "$(basename "${formal_audio_patch}")" == "0013-mira-formal-subject-qwen-audio.patch" ]]
formal_audio_patch_sha="$(shasum -a 256 "${formal_audio_patch}" | awk '{print $1}')"
[[ "${formal_audio_patch_sha}" == "32004a0523b9e44b115315952a6da700aa6656b0ebafb523634dd629c7f31eb9" ]]
provider_readiness_patch="${SCRIPT_DIR}/../patches/0014-mira-formal-provider-readiness.patch"
[[ "$(basename "${provider_readiness_patch}")" == "0014-mira-formal-provider-readiness.patch" ]]
provider_readiness_patch_sha="$(shasum -a 256 "${provider_readiness_patch}" | awk '{print $1}')"
[[ "${provider_readiness_patch_sha}" == "89d51bcdba36902f7cfdbf6aece59ccb72ee3d5c61142a23a6005b99cb56071c" ]]
runtime_events_patch="${SCRIPT_DIR}/../patches/0015-mira-student-runtime-events.patch"
[[ "$(basename "${runtime_events_patch}")" == "0015-mira-student-runtime-events.patch" ]]
runtime_events_patch_sha="$(shasum -a 256 "${runtime_events_patch}" | awk '{print $1}')"
[[ "${runtime_events_patch_sha}" == "1ee9fa1bf18a0c930599e43eb058ca4010dad4164d42aa996ac053301317af34" ]]
student_asr_patch="${SCRIPT_DIR}/../patches/0016-mira-student-asr-isolation.patch"
[[ "$(basename "${student_asr_patch}")" == "0016-mira-student-asr-isolation.patch" ]]
student_asr_patch_sha="$(shasum -a 256 "${student_asr_patch}" | awk '{print $1}')"
[[ "${student_asr_patch_sha}" == "8bba5ee6354474a74666dfcc770ba75a60ca749ec0cf19eadd89786bdbe9ab91" ]]
student_asr_events_patch="${SCRIPT_DIR}/../patches/0017-mira-student-asr-learning-events.patch"
[[ "$(basename "${student_asr_events_patch}")" == "0017-mira-student-asr-learning-events.patch" ]]
student_asr_events_patch_sha="$(shasum -a 256 "${student_asr_events_patch}" | awk '{print $1}')"
[[ "${student_asr_events_patch_sha}" == "eb342174f248b743d0b53143439fae319612bf6aa0c88ef6e4545f1e0c8f0a37" ]]
student_runtime_hardening_patch="${SCRIPT_DIR}/../patches/0018-mira-student-runtime-hardening.patch"
[[ "$(basename "${student_runtime_hardening_patch}")" == "0018-mira-student-runtime-hardening.patch" ]]
student_runtime_hardening_patch_sha="$(shasum -a 256 "${student_runtime_hardening_patch}" | awk '{print $1}')"
[[ "${student_runtime_hardening_patch_sha}" == "8cf94811d2e30b4df47df5443178213f62aa4e9fa5187273689f4d5f37a8aa7c" ]]
grep -Fq "title: 'Mira 互动课堂'" "${student_runtime_hardening_patch}"
grep -Fq "await flushPending();" "${student_runtime_hardening_patch}"
node_persistence_boundary_patch="${SCRIPT_DIR}/../patches/0019-mira-node-persistence-instrumentation-boundary.patch"
[[ "$(basename "${node_persistence_boundary_patch}")" == "0019-mira-node-persistence-instrumentation-boundary.patch" ]]
node_persistence_boundary_patch_sha="$(shasum -a 256 "${node_persistence_boundary_patch}" | awk '{print $1}')"
[[ "${node_persistence_boundary_patch_sha}" == "709afd384a1fc647249c58f487f634d7abdbe82a17934e6d7bfb69f6a4b7966c" ]]
grep -Fq "await import('./instrumentation.node')" "${node_persistence_boundary_patch}"
webpack_production_boundary_patch="${SCRIPT_DIR}/../patches/0020-mira-webpack-production-boundaries.patch"
[[ "$(basename "${webpack_production_boundary_patch}")" == "0020-mira-webpack-production-boundaries.patch" ]]
webpack_production_boundary_patch_sha="$(shasum -a 256 "${webpack_production_boundary_patch}" | awk '{print $1}')"
[[ "${webpack_production_boundary_patch_sha}" == "47d3e7e7afa4f693e0ef0bdf283a318ec8e79d593b8b8d3853b723afd43a49ad" ]]
grep -Fq "nextRuntime === 'edge'" "${webpack_production_boundary_patch}"
grep -Fq "@openmaic/generation/generation-retry" "${webpack_production_boundary_patch}"
grep -Fq "@/lib/persistence/route-handler" "${webpack_production_boundary_patch}"
formal_generation_stability_patch="${SCRIPT_DIR}/../patches/0021-mira-formal-generation-stability.patch"
[[ "$(basename "${formal_generation_stability_patch}")" == "0021-mira-formal-generation-stability.patch" ]]
formal_generation_stability_patch_sha="$(shasum -a 256 "${formal_generation_stability_patch}" | awk '{print $1}')"
[[ "${formal_generation_stability_patch_sha}" == "a3575ab053e1026900e25b3fa0acc200d90a203d62c7827f3044c3cb40d7d22f" ]]
grep -Fq 'MIRA FORMAL OUTLINE CONTRACT' "${formal_generation_stability_patch}"
grep -Fq 'attempt === 1' "${formal_generation_stability_patch}"
grep -Fq 'MIRA_FORMAL_LLM_TIMEOUT_MS' "${formal_generation_stability_patch}"
single_courseware_authority_patch="${SCRIPT_DIR}/../patches/0022-mira-openmaic-single-courseware-authority.patch"
[[ "$(basename "${single_courseware_authority_patch}")" == "0022-mira-openmaic-single-courseware-authority.patch" ]]
single_courseware_authority_patch_sha="$(shasum -a 256 "${single_courseware_authority_patch}" | awk '{print $1}')"
[[ "${single_courseware_authority_patch_sha}" == "e27b96713877054977e053f12b66cc4dce0bf8011b548f08cc523c5343f3b593" ]]
grep -Fq 'mira.openmaic.courseware-authority.v1' "${single_courseware_authority_patch}"
grep -Fq 'courseware_generation_only' "${single_courseware_authority_patch}"
grep -Fq 'deterministic_no_llm' "${single_courseware_authority_patch}"
qwen_tts_https_upgrade_patch="${SCRIPT_DIR}/../patches/0023-mira-qwen-tts-https-upgrade.patch"
[[ "$(basename "${qwen_tts_https_upgrade_patch}")" == "0023-mira-qwen-tts-https-upgrade.patch" ]]
qwen_tts_https_upgrade_patch_sha="$(shasum -a 256 "${qwen_tts_https_upgrade_patch}" | awk '{print $1}')"
[[ "${qwen_tts_https_upgrade_patch_sha}" == "29530db4b6fb0ffe2dc100bfa27f3ff91fdc26f2f053d2f994d371b704e85ac6" ]]
grep -Fq "url.protocol = 'https:'" "${qwen_tts_https_upgrade_patch}"
grep -Fq 'dashscope-result-bj.oss-cn-beijing.aliyuncs.com' "${qwen_tts_https_upgrade_patch}"
english_chinese_instruction_audio_patch="${SCRIPT_DIR}/../patches/0024-mira-english-chinese-instruction-audio.patch"
[[ "$(basename "${english_chinese_instruction_audio_patch}")" == "0024-mira-english-chinese-instruction-audio.patch" ]]
english_chinese_instruction_audio_patch_sha="$(shasum -a 256 "${english_chinese_instruction_audio_patch}" | awk '{print $1}')"
[[ "${english_chinese_instruction_audio_patch_sha}" == "871dd75333ff8b54beaa5da51d70c149be387184161be27e0da552c3ef703570" ]]
grep -Fq "instructionLanguageCode: 'zh-CN'" "${english_chinese_instruction_audio_patch}"
grep -Fq "qwenAsrLanguage: 'zh'" "${english_chinese_instruction_audio_patch}"
grep -Fq "qwenLanguageType: 'Chinese'" "${english_chinese_instruction_audio_patch}"
nanoid_formal_audio_identity_patch="${SCRIPT_DIR}/../patches/0025-mira-nanoid-formal-audio-identity.patch"
[[ "$(basename "${nanoid_formal_audio_identity_patch}")" == "0025-mira-nanoid-formal-audio-identity.patch" ]]
nanoid_formal_audio_identity_patch_sha="$(shasum -a 256 "${nanoid_formal_audio_identity_patch}" | awk '{print $1}')"
[[ "${nanoid_formal_audio_identity_patch_sha}" == "b307be032dd99913afccfbaa71e354d3485a283ad55a815ccbbd3e4913a7947c" ]]
grep -Fq 'const IDENTIFIER = /^[A-Za-z0-9_-]' "${nanoid_formal_audio_identity_patch}"
grep -Fq "classroomId: '-omclass_english_001'" "${nanoid_formal_audio_identity_patch}"
native_next_build_boundary_patch="${SCRIPT_DIR}/../patches/0026-mira-native-next-build-boundary.patch"
[[ "$(basename "${native_next_build_boundary_patch}")" == "0026-mira-native-next-build-boundary.patch" ]]
native_next_build_boundary_patch_sha="$(shasum -a 256 "${native_next_build_boundary_patch}" | awk '{print $1}')"
[[ "${native_next_build_boundary_patch_sha}" == "fdfc9696bdae1d71b67aaa142e007ec512e61e5b16bf961b46de635f0f91f1cb" ]]
grep -Fq 'MIRA_OPENMAIC_NATIVE_BUILD' "${native_next_build_boundary_patch}"
grep -Fq 'node_modules/next/dist/bin/next dev --webpack' "${RUNTIME_SCRIPT}"
grep -Fq "'standalone'" "${native_next_build_boundary_patch}"
start_openmaic_source="$(declare -f start_openmaic)"
[[ "${start_openmaic_source}" == *'NODE_ENV=production'* ]] || fail "detached OpenMAIC start does not set NODE_ENV=production"
[[ "${start_openmaic_source}" == *'MIRA_OPENMAIC_NATIVE_BUILD=1'* ]] || fail "detached OpenMAIC start omits the native-build boundary"
[[ "${start_openmaic_source}" == *'node_modules/next/dist/bin/next start'* ]] || fail "detached OpenMAIC start does not use Next production start"
[[ "${start_openmaic_source}" != *'node_modules/next/dist/bin/next dev'* ]] || fail "detached OpenMAIC start still uses Next development mode"
[[ "${start_openmaic_source}" == *'write_openmaic_mode "${started_pid}" "${started_start_hash}" "${build_id_sha256}" "${next_version}" pending'* ]] || fail "detached OpenMAIC start omits the pending identity commit"
[[ "${start_openmaic_source}" == *'wait_for_formal_provider_readiness_health'* ]] || fail "detached OpenMAIC start omits Provider readiness health"
grep -Fq 'version=2' "${RUNTIME_SCRIPT}" || fail "native runtime does not use v2 OpenMAIC identity"
grep -Fq 'port_is_owned_by_tree "${OPENMAIC_PORT}"' "${RUNTIME_SCRIPT}" || fail "native runtime does not bind identity to listener ownership"
production_foreground_source="$(declare -f run_openmaic_production_foreground)"
[[ "${production_foreground_source}" == *'MIRA_OPENMAIC_NATIVE_BUILD=1'* ]] || fail "production foreground omits the native-build boundary"
grep -Fq 'OPENMAIC_PRODUCTION_COMMAND_TOKEN="next-server (v16.1.2)"' "${LOCAL_TEST_STACK_SCRIPT}" || fail "local stack does not recognize the production Next process"
grep -Fq 'OPENMAIC_LEGACY_DEV_COMMAND_TOKEN="next/dist/bin/next dev"' "${LOCAL_TEST_STACK_SCRIPT}" || fail "local stack lacks the legacy dev migration guard"
provider_readiness_qwen_recovery_patch="${SCRIPT_DIR}/../patches/0027-mira-provider-readiness-qwen-url-recovery.patch"
provider_readiness_qwen_recovery_patch_sha="$(shasum -a 256 "${provider_readiness_qwen_recovery_patch}" | awk '{print $1}')"
[[ "${provider_readiness_qwen_recovery_patch_sha}" == "0b53d8c139095a3b67a9d84afc4cf907a521bbb2a65fc3c8d6e313a26edd2040" ]]
grep -Fq 'normalizeQwenAudioUrl' "${provider_readiness_qwen_recovery_patch}"
grep -Fq 'recoverMiraFormalProviderReadinessQwenUrl' "${provider_readiness_qwen_recovery_patch}"
student_runtime_audio_playback_patch="${SCRIPT_DIR}/../patches/0028-mira-student-runtime-audio-playback.patch"
student_runtime_audio_playback_patch_sha="$(shasum -a 256 "${student_runtime_audio_playback_patch}" | awk '{print $1}')"
[[ "${student_runtime_audio_playback_patch_sha}" == "19c327574914d7d98cde6a266836873cfe1b01e37f0f0267af9e6b3712f21272" ]]
grep -Fq 'hasPreGeneratedSpeechAudio' "${student_runtime_audio_playback_patch}"
grep -Fq 'onAudioPlaybackIssue' "${student_runtime_audio_playback_patch}"
grep -Fq 'audioPlaybackAvailable' "${student_runtime_audio_playback_patch}"
provider_readiness_patch_completion="${SCRIPT_DIR}/../patches/0029-mira-provider-readiness-patch-completion.patch"
provider_readiness_patch_completion_sha="$(shasum -a 256 "${provider_readiness_patch_completion}" | awk '{print $1}')"
[[ "${provider_readiness_patch_completion_sha}" == "6e5be00f759a52c98d9b64ff4651dcbf8513fb9cf3ad44d4def8ef7631873a9f" ]]
grep -Fq 'expect(healthy.status).toBe(200)' "${provider_readiness_patch_completion}"
grep -Fq 'expectedProviderCallCount' "${provider_readiness_patch_completion}"
provider_readiness_type_safety_patch="${SCRIPT_DIR}/../patches/0030-mira-provider-readiness-type-safety.patch"
provider_readiness_type_safety_patch_sha="$(shasum -a 256 "${provider_readiness_type_safety_patch}" | awk '{print $1}')"
grep -Fq 'const providerProof = proofFor(record)' "${provider_readiness_type_safety_patch}"
grep -Fq "import { createHash } from 'node:crypto'" "${provider_readiness_type_safety_patch}"
low_disk_runtime_cache_patch="${SCRIPT_DIR}/../patches/0031-mira-low-disk-runtime-cache.patch"
low_disk_runtime_cache_patch_sha="$(shasum -a 256 "${low_disk_runtime_cache_patch}" | awk '{print $1}')"
[[ "${low_disk_runtime_cache_patch_sha}" == "ad17039de8b0788e9e333828f0105be6112de3f478749dbe884b9a59dc81f9a5" ]]
grep -Fq 'MIRA_OPENMAIC_LOW_DISK_DEV' "${low_disk_runtime_cache_patch}"
grep -Fq 'config.cache = false' "${low_disk_runtime_cache_patch}"
grep -Fq 'MIRA_OPENMAIC_LOW_DISK_DEV=1' "${RUNTIME_SCRIPT}"
student_authoritative_audio_patch="${SCRIPT_DIR}/../patches/0032-mira-student-authoritative-audio-refresh.patch"
student_authoritative_audio_patch_sha="$(shasum -a 256 "${student_authoritative_audio_patch}" | awk '{print $1}')"
[[ "${student_authoritative_audio_patch_sha}" == "d718d4f29f4e4f143c015c4d12494faca7a1fb31309da0b7645b25c9d5035321" ]]
grep -Fq 'requireServerClassroom: studentMode' "${student_authoritative_audio_patch}"
grep -Fq 'persist: !studentMode' "${student_authoritative_audio_patch}"
formal_audio_lifecycle_patch="${SCRIPT_DIR}/../patches/0033-mira-openmaic-formal-audio-lifecycle-v2.patch"
formal_audio_lifecycle_patch_sha="$(shasum -a 256 "${formal_audio_lifecycle_patch}" | awk '{print $1}')"
[[ "${formal_audio_lifecycle_patch_sha}" == "e32a828d1b5362cd994eb694a726a1bb5143d9a20c2a94d8bd500e3e7a5a2dee" ]]
grep -Fq 'mira.openmaic.formal-audio-lifecycle.v2' "${formal_audio_lifecycle_patch}"
grep -Fq 'shouldShowMiraStudentStartGate' "${formal_audio_lifecycle_patch}"
student_audible_output_patch="${SCRIPT_DIR}/../patches/0034-mira-student-audible-output.patch"
student_audible_output_patch_sha="$(shasum -a 256 "${student_audible_output_patch}" | awk '{print $1}')"
[[ "${student_audible_output_patch_sha}" == "2c2978f0f01da95e9cdf074a876779d161eef1b5fcd34d2b85ba203dc9966387" ]]
grep -Fq 'MIRA_STUDENT_AUDIO_GAIN' "${student_audible_output_patch}"
grep -Fq 'prepareStudentPlayback' "${student_audible_output_patch}"
grep -Fq 'rewinds the same referenced narration when paused audio cannot resume' "${student_audible_output_patch}"
student_playback_stability_patch="${SCRIPT_DIR}/../patches/0035-mira-student-playback-stability.patch"
student_playback_stability_patch_sha="$(shasum -a 256 "${student_playback_stability_patch}" | awk '{print $1}')"
[[ "${student_playback_stability_patch_sha}" == "4bd0934dc0083984726d47199c87c4373f8fb041f101bd0bd8141b39f7ca9cf7" ]]
grep -Fq 'audioStartAccepted' "${student_playback_stability_patch}"
student_refresh_resume_patch="${SCRIPT_DIR}/../patches/0036-mira-student-refresh-resume.patch"
student_refresh_resume_patch_sha="$(shasum -a 256 "${student_refresh_resume_patch}" | awk '{print $1}')"
[[ "${student_refresh_resume_patch_sha}" == "af08ac390e150c143461821096b8402c3e4f8ecfd782864b72417ebabca8b9d2" ]]
grep -Fq 'mira-student-chrome.v6' "${student_refresh_resume_patch}"
grep -Fq "audioStartPersistence: 'classroom-tab-session'" "${student_refresh_resume_patch}"
student_completion_resume_patch="${SCRIPT_DIR}/../patches/0037-mira-student-completion-resume.patch"
student_completion_resume_patch_sha="$(shasum -a 256 "${student_completion_resume_patch}" | awk '{print $1}')"
[[ "${student_completion_resume_patch_sha}" == "27bd5d381c3064c45662e21b27c2fcd10b238890cac209f0650716c815b99c21" ]]
grep -Fq 'shouldAutoStartMiraStudentSelectedScene' "${student_completion_resume_patch}"
grep -Fq 'armSelectedSceneAutoStart(targetSceneId)' "${student_completion_resume_patch}"
formal_professional_agent_patch="${SCRIPT_DIR}/../patches/0038-mira-formal-professional-agent.patch"
formal_professional_agent_patch_sha="$(shasum -a 256 "${formal_professional_agent_patch}" | awk '{print $1}')"
[[ "${formal_professional_agent_patch_sha}" == "dd73b85c250dae6e764d253f2dc54fd8fb81eb61748c13dfe28c3e1937561756" ]]
grep -Fq 'generateMiraFormalProfessionalClassroom' "${formal_professional_agent_patch}"
grep -Fq 'MIRA_FORMAL_RESEARCH_SEARCH_EVENT_TYPE' "${formal_professional_agent_patch}"
adaptive_professional_classroom_patch="${SCRIPT_DIR}/../patches/0039-mira-adaptive-professional-classroom.patch"
adaptive_professional_classroom_patch_sha="$(shasum -a 256 "${adaptive_professional_classroom_patch}" | awk '{print $1}')"
[[ "${adaptive_professional_classroom_patch_sha}" == "74f49cf4baa47e21aa73f9fee3078d44eb8a3beab3150b72728b38c9e32f2d7e" ]]
grep -Fq 'mira.openmaic.formal-runtime.v3-adaptive' "${adaptive_professional_classroom_patch}"
grep -Fq "authority: 'openmaic_professional_agent'" "${adaptive_professional_classroom_patch}"
grep -Fq "segmentCount: { mode: 'per_speech_action', min: 1, max: 240 }" "${adaptive_professional_classroom_patch}"
grep -Fq 'Number(input.sceneOrder) > 239' "${adaptive_professional_classroom_patch}"
grep -Fq 'Number(validation.sceneOrder) > 239' "${adaptive_professional_classroom_patch}"
grep -Fq 'focusExplanationSequenceRequired: true' "${adaptive_professional_classroom_patch}"
grep -Fq 'manifest.speechActionCount !== speechCount' "${SCRIPT_DIR}/../gateway/src/server.mjs"
grep -Fq 'sceneSpeechCount > 20' "${SCRIPT_DIR}/../gateway/src/server.mjs"
courseware_rate_limit_patch="${SCRIPT_DIR}/../patches/0040-mira-courseware-provider-rate-limit-retry.patch"
courseware_rate_limit_patch_sha="$(shasum -a 256 "${courseware_rate_limit_patch}" | awk '{print $1}')"
grep -Fq 'providerStatus(error) === 429' "${courseware_rate_limit_patch}"
grep -Fq 'RATE_LIMIT_RETRY_COUNT = 1' "${courseware_rate_limit_patch}"
grep -Fq 'mocks.callLLM).toHaveBeenCalledTimes(2)' "${courseware_rate_limit_patch}"
[[ "${courseware_rate_limit_patch_sha}" == "9770fcc72a845d76feba69a1cd45d172e4396dfdc9ff7871ff663545ca6fc92d" ]]
brave_search_rate_limit_patch="${SCRIPT_DIR}/../patches/0041-mira-brave-search-rate-limit.patch"
brave_search_rate_limit_patch_sha="$(shasum -a 256 "${brave_search_rate_limit_patch}" | awk '{print $1}')"
[[ "${brave_search_rate_limit_patch_sha}" == "2c8999f25980bb566a6b89b835f8f77c0eaa4ea0956697125618aa304fd0ccff" ]]
grep -Fq 'runSerializedBraveScrape' "${brave_search_rate_limit_patch}"
grep -Fq 'BRAVE_SCRAPE_MIN_REQUEST_INTERVAL_MS = 1_000' "${brave_search_rate_limit_patch}"
grep -Fq "res.status === 429 && attempt === 0" "${brave_search_rate_limit_patch}"
deepseek_courseware_routing_patch="${SCRIPT_DIR}/../patches/0042-mira-deepseek-courseware-routing.patch"
deepseek_courseware_routing_patch_sha="$(shasum -a 256 "${deepseek_courseware_routing_patch}" | awk '{print $1}')"
[[ "${deepseek_courseware_routing_patch_sha}" == "c98d1c98edabb76ab63651d35a2d9361e5581bcb3c39491a069d8a96777ba0f3" ]]
grep -Fq "MIRA_PROFESSIONAL_MODEL_POLICY_ID = 'deepseek-v4-pro-flash-v1'" "${deepseek_courseware_routing_patch}"
grep -Fq "stage: 'mira-courseware-verifier'" "${deepseek_courseware_routing_patch}"
grep -Fq 'mira.openmaic.formal-runtime.v4-deepseek-professional' "${deepseek_courseware_routing_patch}"
formal_citation_recovery_patch="${SCRIPT_DIR}/../patches/0043-mira-formal-citation-recovery.patch"
formal_citation_recovery_patch_sha="$(shasum -a 256 "${formal_citation_recovery_patch}" | awk '{print $1}')"
[[ "${formal_citation_recovery_patch_sha}" =~ ^[a-f0-9]{64}$ ]]
grep -Fq 'mira-formal-citation-recovery.v1' "${formal_citation_recovery_patch}"
grep -Fq 'formal_citation_recovery' "${formal_citation_recovery_patch}"
grep -Fq 'canonicalizeMiraFormalResearchFooters' "${formal_citation_recovery_patch}"
pro_live_edit_sync_patch="${SCRIPT_DIR}/../patches/0047-mira-pro-live-edit-sync.patch"
pro_live_edit_sync_patch_sha="$(shasum -a 256 "${pro_live_edit_sync_patch}" | awk '{print $1}')"
integrated_skills_patch="${SCRIPT_DIR}/../patches/0048-mira-integrated-skills-discussion-completion.patch"
integrated_skills_patch_sha="$(shasum -a 256 "${integrated_skills_patch}" | awk '{print $1}')"
adaptive_quality_patch="${SCRIPT_DIR}/../patches/0049-mira-adaptive-skills-teaching-quality.patch"
adaptive_quality_patch_sha="$(shasum -a 256 "${adaptive_quality_patch}" | awk '{print $1}')"
thinking_focus_patch="${SCRIPT_DIR}/../patches/0050-mira-thinking-context-and-focus-evidence.patch"
thinking_focus_patch_sha="$(shasum -a 256 "${thinking_focus_patch}" | awk '{print $1}')"
video_patch="${SCRIPT_DIR}/../patches/0051-mira-formal-happyhorse-video.patch"
video_patch_sha="$(shasum -a 256 "${video_patch}" | awk '{print $1}')"
video_duration_patch="${SCRIPT_DIR}/../patches/0052-mira-formal-video-stream-duration.patch"
video_duration_patch_sha="$(shasum -a 256 "${video_duration_patch}" | awk '{print $1}')"
formal_interactive_patch="${SCRIPT_DIR}/../patches/0053-mira-formal-self-contained-interactive.patch"
formal_interactive_patch_sha="$(shasum -a 256 "${formal_interactive_patch}" | awk '{print $1}')"
grep -Fq '"count": 54' "${SCRIPT_DIR}/../upstream.lock.json"
grep -Fq '"latest": "0054-mira-bailian-deepseek-service.patch"' "${SCRIPT_DIR}/../upstream.lock.json"
bailian_patch_sha="$(shasum -a 256 "${SCRIPT_DIR}/../patches/0054-mira-bailian-deepseek-service.patch" | awk '{print $1}')"
grep -Fq "\"latestSha256\": \"${bailian_patch_sha}\"" "${SCRIPT_DIR}/../upstream.lock.json"
grep -Fq 'interactiveIncludeKatex' "${formal_interactive_patch}"
grep -Fq 'video_stream' "${video_duration_patch}"
grep -Fq 'mira-formal-happyhorse-video.v1' "${video_patch}"
grep -Fq 'buildMiraFormalSkillPreload' "${integrated_skills_patch}"
grep -Fq 'prepareMiraFormalAdaptiveSkillBundle' "${adaptive_quality_patch}"
grep -Fq 'review_course_quality' "${adaptive_quality_patch}"
grep -Fq 'FORMAL_QUALITY_FINAL_SNAPSHOT_REJECTED' "${adaptive_quality_patch}"
grep -Fq 'finishGuidedDiscussionPlayback' "${integrated_skills_patch}"
grep -Fq 'verify_patch_manifest' "${SCRIPT_DIR}/bootstrap-upstream.sh"
clear_openmaic_recovery_env
[[ "${OPENMAIC_RECOVERY_ENABLED}" == "0" ]]
[[ -z "${OPENMAIC_RECOVERY_INTERNAL_TOKEN}" ]]
[[ "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED}" == "0" ]]
[[ -z "${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256}" ]]
[[ "${OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED}" == "0" ]]
[[ -z "${OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID}" ]]
[[ -z "${OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256}" ]]

MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED=1
MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_SOURCE_JOB_ID=wrong-job
if load_openmaic_recovery_env 2>/dev/null; then
  echo "unreviewed deterministic recovery source unexpectedly passed" >&2
  exit 1
fi
unset MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_SOURCE_JOB_ID

MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED=1
MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID=wrong-formal-job
if load_openmaic_formal_citation_recovery_env 2>/dev/null; then
  echo "unreviewed formal citation recovery source unexpectedly passed" >&2
  exit 1
fi
unset MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID

provider_status="$(show_provider_status 2>&1)"
[[ "${provider_status}" == *"LLM: enabled (deepseek, deepseek-v4-pro,deepseek-v4-flash)"* ]]
[[ "${provider_status}" == *"LLM professional creation: DeepSeek V4 Pro"* ]]
[[ "${provider_status}" == *"LLM independent verification: deepseek-v4-flash"* ]]
[[ "${provider_status}" == *"LLM structured scenes: enforced (DeepSeek V4 Pro thinking disabled)"* ]]
[[ "${provider_status}" == *"TTS: enabled (qwen-tts, qwen3-tts-flash, voice=Serena)"* ]]
[[ "${provider_status}" == *"ASR: enabled (qwen-asr, qwen3-asr-flash)"* ]]
[[ "${provider_status}" != *"secret-never-log"* ]]
[[ "${provider_status}" != *"internal-token-never-log"* ]]

# The launch policy is script-owned. Hostile caller variables are neither
# trusted as a route nor forwarded through the clean `env -i` boundary.
MIRA_OPENMAIC_STRUCTURED_SCENE_POLICY=attacker-controlled
MODEL_ROUTES='{"scene-content":"attacker:model"}'
[[ "${OPENMAIC_STRUCTURED_SCENE_POLICY_ID}" == "deepseek-v4-pro-flash-v1" ]]
grep -Fq 'MIRA_OPENMAIC_STRUCTURED_SCENE_POLICY="${OPENMAIC_STRUCTURED_SCENE_POLICY_ID}"' "${RUNTIME_SCRIPT}"
grep -Fq 'MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED="${OPENMAIC_RECOVERY_ENABLED}"' "${RUNTIME_SCRIPT}"
grep -Fq 'MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED}"' "${RUNTIME_SCRIPT}"
grep -Fq 'MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED="${OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED}"' "${RUNTIME_SCRIPT}"
grep -Fq 'MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID}"' "${RUNTIME_SCRIPT}"
grep -Fq 'MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256="${OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256}"' "${RUNTIME_SCRIPT}"
grep -Fq 'MIRA_OPENMAIC_PRIVATE_PORT="${OPENMAIC_PORT}"' "${RUNTIME_SCRIPT}"
grep -Fq 'MIRA_INTERNAL_API_TOKEN="${OPENMAIC_INTERNAL_API_TOKEN}"' "${RUNTIME_SCRIPT}"
grep -Fq 'probe_formal_audio_health' "${RUNTIME_SCRIPT}"
grep -Fq 'probe_formal_provider_readiness_health' "${RUNTIME_SCRIPT}"
if grep -E '^[[:space:]]*MODEL_ROUTES=' "${RUNTIME_SCRIPT}" | sed 's/^[[:space:]]*//' | grep -Fxv 'MODEL_ROUTES="${OPENMAIC_MODEL_ROUTES}" \'; then
  echo "native runtime unexpectedly forwards arbitrary MODEL_ROUTES" >&2
  exit 1
fi
[[ "$(grep -Ec '^[[:space:]]*MODEL_ROUTES=' "${RUNTIME_SCRIPT}")" == "3" ]] || fail "native runtime model route boundary is missing from a launch path"
grep -Fq 'DEFAULT_MODEL: deepseek:deepseek-v4-pro' "${COMPOSE_FILE}"
grep -Fq 'MIRA_OPENMAIC_STRUCTURED_SCENE_POLICY: deepseek-v4-pro-flash-v1' "${COMPOSE_FILE}"
grep -Fq '"mira-courseware-creator":{"model":"deepseek:deepseek-v4-pro","thinking":{"mode":"disabled","enabled":false}}' "${COMPOSE_FILE}"
grep -Fq '"mira-courseware-verifier":{"model":"deepseek:deepseek-v4-flash","thinking":{"mode":"disabled","enabled":false}}' "${COMPOSE_FILE}"
grep -Fq '"web-search-query-rewrite":{"model":"deepseek:deepseek-v4-pro","thinking":{"mode":"disabled","enabled":false}}' "${COMPOSE_FILE}"
grep -Fq 'MIRA_OPENMAIC_REQUIRE_QWEN_ASR: ${MIRA_OPENMAIC_ENABLE_QWEN_ASR:-0}' "${COMPOSE_FILE}"
grep -Fq 'MIRA_OPENMAIC_QWEN_ASR_MODEL: qwen3-asr-flash' "${COMPOSE_FILE}"
grep -Fq 'MIRA_INTERNAL_API_TOKEN: ${MIRA_INTERNAL_API_TOKEN:?MIRA_INTERNAL_API_TOKEN is required}' "${COMPOSE_FILE}"
grep -Fq 'MODEL_ROUTES:' "${COMPOSE_FILE}"
[[ "${provider_status}" != *"attacker-controlled"* ]]
[[ "${provider_status}" != *"attacker:model"* ]]
unset MIRA_OPENMAIC_STRUCTURED_SCENE_POLICY MODEL_ROUTES

MIRA_OPENMAIC_MODEL_PROVIDER=openai
if load_openmaic_model_env 2>/dev/null; then
  echo "unsupported provider unexpectedly passed" >&2
  exit 1
fi
unset MIRA_OPENMAIC_MODEL_PROVIDER

MIRA_OPENMAIC_MODEL=deepseek-v4-flash
if load_openmaic_model_env 2>/dev/null; then
  echo "non-contract DeepSeek creator model unexpectedly passed" >&2
  exit 1
fi
unset MIRA_OPENMAIC_MODEL

MIRA_OPENMAIC_VERIFIER_MODEL=deepseek-v4-pro
if load_openmaic_model_env 2>/dev/null; then
  echo "non-contract DeepSeek verifier model unexpectedly passed" >&2
  exit 1
fi
unset MIRA_OPENMAIC_VERIFIER_MODEL

MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=0
MIRA_OPENMAIC_ENABLE_QWEN_TTS=1
MIRA_OPENMAIC_ENABLE_QWEN_ASR=0
MIRA_BACKEND_ENV_FILE="${TMP_ROOT}/missing.env"
printf 'APP_AI_PROVIDER=kimi\n' > "${MIRA_BACKEND_ENV_FILE}"
if load_openmaic_provider_env 2>/dev/null; then
  echo "missing Qwen3-TTS key unexpectedly passed" >&2
  exit 1
fi

MIRA_BACKEND_ENV_FILE="${TMP_ROOT}/backend.env"
MIRA_OPENMAIC_QWEN_TTS_VOICE=Cherry
if load_openmaic_provider_env 2>/dev/null; then
  echo "non-Serena Qwen3-TTS voice unexpectedly passed" >&2
  exit 1
fi
unset MIRA_OPENMAIC_QWEN_TTS_VOICE

MIRA_OPENMAIC_QWEN_TTS_MODEL=qwen3-tts-instruct-flash
if load_openmaic_provider_env 2>/dev/null; then
  echo "non-contract Qwen3-TTS model unexpectedly passed" >&2
  exit 1
fi
unset MIRA_OPENMAIC_QWEN_TTS_MODEL

MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1
MIRA_OPENMAIC_ENABLE_QWEN_TTS=1
MIRA_OPENMAIC_ENABLE_QWEN_ASR=1
MIRA_BACKEND_ENV_FILE="${TMP_ROOT}/backend.env"
load_openmaic_provider_env
load_openmaic_recovery_env
load_openmaic_formal_citation_recovery_env
clear_openmaic_provider_env
clear_openmaic_recovery_secret
[[ -z "${OPENMAIC_RECOVERY_INTERNAL_TOKEN}" ]]
structured_health_payload='{"success":true,"status":"ok","version":"1.0.0","capabilities":{"webSearch":true,"tts":true,"asr":true},"runtimePolicy":{"tts":{"enforced":true,"providerId":"qwen-tts","modelId":"qwen3-tts-flash","voiceId":"Serena"},"asr":{"enforced":true,"providerId":"qwen-asr","modelId":"qwen3-asr-flash","fallbackAllowed":false},"structuredScene":{"enforced":true,"policyId":"kimi-k2.6-thinking-disabled-v1","providerId":"kimi","modelId":"kimi-k2.6","stages":["scene-content","scene-content:slide","scene-content:quiz","scene-content:interactive","scene-content:pbl","scene-actions"],"thinking":{"mode":"disabled","enabled":false}},"studentChrome":{"enforced":true,"policyVersion":"mira-student-chrome.v6","marker":"mira=1","locale":"zh-CN","theme":"light","autoPlayDefault":true,"autoPlayPersistence":"student-session","audioStartPersistence":"classroom-tab-session","manualAutoPlayToggleEnabled":true,"asrEnabled":true,"asrPersistence":"student-session","manualAsrToggleEnabled":false,"operatorAsrPreferencePreserved":true,"operatorChromePreserved":true,"headerControlsHidden":true,"exportsHidden":true,"teacherIdentity":{"agentId":"mira-sample-teacher","avatar":"/avatars/teacher-2.png"}},"professionalResearch":{"schemaVersion":"mira.openmaic.professional-research.v1","professionalWorkbench":{"upstreamVersion":"1.0.0","primarySkillId":"mira-primary-courseware","proModeAvailableToOperators":true,"availableToStudentRuntime":false},"webSearch":{"defaultEnabled":true,"operatorOnly":false,"formalGenerationEnabled":true,"studentRuntimeEnabled":false,"maxCallsPerCourse":4,"citationsRequired":true,"primarySourcesPreferred":true}},"formalGeneration":{"enforced":true,"policyId":"mira.openmaic.formal-runtime.v3-adaptive","idempotencyKey":"runtimeRequestId","queryByRuntimeRequestId":true,"speechAudioGenerated":true,"coursewareAuthority":{"schemaVersion":"mira.openmaic.courseware-authority.v2-professional","generationOwner":"openmaic","providerInvocation":"professional_agent","classroomCompilation":"professional_skill_workflow","backendProviderCredentialsAccepted":false},"professionalCreation":{"schemaVersion":"mira.openmaic.professional-creation.v1","mode":"professional_skill","workflowVersion":"openmaic-pro-agent.v1","skillId":"mira-primary-courseware","supportingSkillIds":["k12-core-literacy-planning","deep-interactive"],"userPromptRequired":false,"webSearch":{"enabled":true,"providerManaged":true,"maxCalls":4,"citationsRequired":true,"primarySourcesPreferred":true,"minimumFetchedSources":1},"image":{"schemaVersion":"mira.openmaic.formal-image-policy.v1","policyId":"mira-formal-qwen-image.v1","enabled":true,"providerManaged":true,"providerId":"qwen-image","modelId":"qwen-image-max","usage":"teaching_need","assetValidationRequired":true},"studentToolsEnabled":false},"studentRuntimeEvents":{"enforced":true,"schemaVersion":"mira.openmaic.student-runtime-events.v1","classroomAuthoritySchema":"mira.openmaic.runtime-event-authority.v1","endpoint":"/mira/runtime-events","authority":"mira-backend","clientIdentityAccepted":false,"clientScoreAccepted":false},"contract":{"schemaVersion":"mira.openmaic.formal-runtime.v3-adaptive","scenePlanning":{"mode":"adaptive","authority":"openmaic_professional_agent","exactCountRequired":false,"allowedSceneTypes":["slide","quiz","interactive","pbl"],"requiredSceneTypes":["slide","quiz","interactive"],"defaultDurationMinutes":{"min":15,"max":30},"scenesPerMinute":{"min":1,"max":2},"maxSceneCount":60},"roster":{"teacherCount":1,"peerCount":4},"speechRequiredForEveryScene":true,"speechActions":{"perScene":{"min":1,"max":20},"total":{"min":1,"max":240},"interactiveSpotlightRequired":false},"distinctPeerDiscussions":2,"teacherEvidence":["spotlight","widget_highlight"],"slideSpotlight":{"minimumPerSlide":1,"targetMustBeRenderable":true,"focusExplanationSequenceRequired":true,"consecutiveSpotlightsAllowed":true},"interactive":{"allowedWidgetTypes":["simulation","diagram","code","game","visualization3d"],"widgetConfigRequired":true,"productiveScriptRequired":true,"noopRejected":true,"fake3dRejected":true},"whiteboardRequired":false}},"deterministicRecovery":{"enabled":true,"sourceJobId":"uKQl3vMr4d","policyVersion":"mira-sample-deterministic-classroom.v1","canonicalSpecSha256":"'"${OPENMAIC_RECOVERY_CANONICAL_SPEC_SHA256}"'","patchSha256":"'"${OPENMAIC_RECOVERY_PATCH_SHA256}"'"},"ttsCredentialRecovery":{"enabled":true,"sourceJobId":"uKQl3vMr4d","parentRecoveryId":"omrec_383729f8f7f637dc1cdc65d4","policyVersion":"mira-sample-tts-credential-recovery.v1","canonicalSpecSha256":"'"${OPENMAIC_TTS_CREDENTIAL_RECOVERY_CANONICAL_SPEC_SHA256}"'","patchSha256":"'"${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256}"'"}}}'
structured_health_payload="${structured_health_payload//kimi-k2.6-thinking-disabled-v1/deepseek-v4-pro-flash-v1}"
structured_health_payload="${structured_health_payload//\"providerId\":\"kimi\"/\"providerId\":\"deepseek\"}"
structured_health_payload="${structured_health_payload//\"modelId\":\"kimi-k2.6\"/\"modelId\":\"deepseek-v4-pro\"}"
structured_health_payload="${structured_health_payload//mira.openmaic.formal-runtime.v3-adaptive/mira.openmaic.formal-runtime.v4-deepseek-professional}"
model_policy_json='"modelPolicy":{"schemaVersion":"mira.openmaic.professional-model-policy.v1","policyId":"deepseek-v4-pro-flash-v1","agentDriver":{"providerId":"deepseek","modelId":"deepseek-v4-pro","thinking":{"mode":"enabled","enabled":true,"effort":"high"}},"coursewareCreator":{"providerId":"deepseek","modelId":"deepseek-v4-pro","thinking":{"mode":"disabled","enabled":false}},"coursewareVerifier":{"providerId":"deepseek","modelId":"deepseek-v4-flash","thinking":{"mode":"disabled","enabled":false}},"structuredScene":{"policyId":"deepseek-v4-pro-flash-v1","providerId":"deepseek","modelId":"deepseek-v4-pro","thinking":{"mode":"disabled","enabled":false}},"fallbackAllowed":false}'
structured_health_payload="${structured_health_payload/\"studentChrome\":/${model_policy_json},\"studentChrome\":}"
instrumentation_boundary_json='"instrumentationBoundary":{"nodeRuntimeOnly":true,"edgeBundle":"excluded","collector":"asset-collector-schedule","serverExternalPackages":["@openmaic/storage","pg"]}'
structured_health_payload="${structured_health_payload/\"formalGeneration\":/${instrumentation_boundary_json},\"formalGeneration\":}"
formal_citation_recovery_json='"formalCitationRecovery":{"enabled":true,"sourceJobId":"'"${OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID}"'","policyVersion":"mira-formal-citation-recovery.v1","patchSha256":"'"${OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256}"'"}'
structured_health_payload="${structured_health_payload/\"formalGeneration\":/${formal_citation_recovery_json},\"formalGeneration\":}"
# Runtime appends the image policy to the unchanged legacy policy. JSON object
# key order must not change exact policy validity, while added fields must fail.
structured_health_payload="$(printf '%s' "${structured_health_payload}" | node -e '
  let raw = "";
  process.stdin.on("data", chunk => { raw += chunk; });
  process.stdin.on("end", () => {
    const body = JSON.parse(raw);
    const { image, ...legacy } = body.runtimePolicy.formalGeneration.professionalCreation;
    body.runtimePolicy.formalGeneration.professionalCreation = { ...legacy, image,
      skillOrchestration: {
        schemaVersion: "mira.openmaic.skill-orchestration.v2",
        profileId: "mira-primary-adaptive.v2",
        registryId: "openmaic-builtin-skills.v1-23",
        baseSkillIds: ["mira-primary-courseware", "stage-design", "k12-core-literacy-planning", "deep-interactive", "slide-craft", "learning-to-learn"],
        selectionMode: "server_rules", mainMethodMax: 1, decisionCoverageRequired: true,
        sceneContextRequired: true, gradeBoundaryRequired: true,
      },
      video: {"schemaVersion":"mira.openmaic.formal-video-policy.v1","policyId":"mira-formal-happyhorse-video.v1","enabled":true,"providerManaged":true,"providerId":"happyhorse","modelId":"happyhorse-1.0-t2v","usage":"teaching_need","maxCalls":1,"maxVideos":1,"durationSec":5,"resolution":"720p","aspectRatio":"16:9","assetValidationRequired":true},
      teachingQuality: {
        schemaVersion: "mira.openmaic.teaching-quality-policy.v1", policyId: "mira-primary-quality.v1",
        gradeBoundaryRequired: true, finalSnapshotRequired: true, independentReviewRequired: true,
        renderedScenesRequired: true, maxReviewAttempts: 3,
      },
    };
    process.stdout.write(JSON.stringify(body));
  });
')"
validate_health_payload openmaic "${structured_health_payload}"
if validate_health_payload openmaic "${structured_health_payload/mira-primary-adaptive.v2/unknown-skill-profile}"; then
  fail "unreviewed skill profile unexpectedly passed formal generation health"
fi
if validate_health_payload openmaic "${structured_health_payload/\"sceneContextRequired\":true/\"sceneContextRequired\":false}"; then
  fail "disabled scene skill context unexpectedly passed formal generation health"
fi
if validate_health_payload openmaic "${structured_health_payload/mira-formal-qwen-image.v1/unreviewed-image-policy}"; then
  fail "unreviewed image policy unexpectedly passed formal generation health"
fi
if validate_health_payload openmaic "${structured_health_payload/\"assetValidationRequired\":true/\"assetValidationRequired\":true,\"unexpected\":true}"; then
  fail "non-exact image policy unexpectedly passed formal generation health"
fi
if validate_health_payload openmaic "${structured_health_payload/\"finalSnapshotRequired\":true/\"finalSnapshotRequired\":false}"; then
  fail "disabled final quality snapshot unexpectedly passed formal generation health"
fi
formal_audio_health_payload='{"success":true,"status":"ok","version":"1.0.0","capabilities":{"formalAudio":true,"tts":true,"asr":true},"runtimePolicy":{"formalAudio":{"enforced":true,"schemaVersion":"mira.openmaic.formal-audio.v1","segmentCount":{"mode":"per_speech_action","min":1,"max":240},"requestIdempotency":"requestId+canonicalBodySha256","providerAttemptRecordedBeforeFetch":true,"staleRunningOutcome":"ambiguous","retryAllowed":false,"providerTimeoutMs":120000,"maxAudioBytes":16777216,"audioMimeType":"audio/wav","tts":{"providerId":"qwen-tts","modelId":"qwen3-tts-flash","fallbackAllowed":false},"asr":{"providerId":"qwen-asr","modelId":"qwen3-asr-flash","fallbackAllowed":false,"inputAuthority":"matching-local-tts-wav","transcriptPersisted":false},"subjects":{"chinese":{"teacherProfileId":"mira_chinese_gentle","teacherProfileVersion":2,"teacherProfileSha256":"a5fd163af249705bda4bb0be5448f65d275eb423285557727f9c50ea442f01f8","teacherName":"小语老师","teacherGender":"female","voiceGender":"female","voiceId":"Serena","languageCode":"zh-CN","qwenLanguageType":"Chinese"},"math":{"teacherProfileId":"mira_math_clear","teacherProfileVersion":2,"teacherProfileSha256":"4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb","teacherName":"小数老师","teacherGender":"male","voiceGender":"male","voiceId":"Ethan","languageCode":"zh-CN","qwenLanguageType":"Chinese"},"english":{"teacherProfileId":"mira_english_standard","teacherProfileVersion":2,"teacherProfileSha256":"4725f27c5438c0f68fe8923ac977fa1dd01452b990ac58912b880320750ee040","teacherName":"Mia 老师","teacherGender":"female","voiceGender":"female","voiceId":"Jennifer","languageCode":"en-US","qwenLanguageType":"English"}}}}}'
formal_audio_health_payload="${formal_audio_health_payload//\"languageCode\":\"zh-CN\",\"qwenLanguageType\":\"Chinese\"/\"languageCode\":\"zh-CN\",\"instructionLanguageCode\":\"zh-CN\",\"qwenLanguageType\":\"Chinese\",\"qwenAsrLanguage\":\"zh\"}"
formal_audio_health_payload="${formal_audio_health_payload/\"languageCode\":\"en-US\",\"qwenLanguageType\":\"English\"/\"languageCode\":\"en-US\",\"instructionLanguageCode\":\"zh-CN\",\"qwenLanguageType\":\"Chinese\",\"qwenAsrLanguage\":\"zh\"}"
validate_health_payload formal-audio "${formal_audio_health_payload}"
if validate_health_payload formal-audio "${formal_audio_health_payload/\"voiceId\":\"Ethan\"/\"voiceId\":\"Serena\"}"; then
  echo "wrong formal math voice unexpectedly passed formal-audio health" >&2
  exit 1
fi
formal_provider_readiness_health_payload='{"success":true,"status":"ok","version":"1.0.0","capabilities":{"formalProviderReadiness":true},"runtimePolicy":{"formalProviderReadiness":{"enforced":true,"schemaVersion":"mira.openmaic.formal-provider-readiness.v1","requestIdempotency":"requestId+canonicalBodySha256","providerAttemptRecordedBeforeFetch":true,"expectedProviderCallCount":5,"retryAllowed":false,"staleRunningOutcome":"ambiguous","providerTimeoutMs":120000,"routeSessionProof":{"schemaVersion":"mira.openmaic.conversation-proof.v1","providerCall":false,"publicationAuthority":false},"providerProof":{"schemaVersion":"mira.openmaic.formal-provider-readiness.v1","providerCall":true,"publicationAuthority":true,"rawResponsePersisted":false,"transcriptPersisted":false,"audioPersisted":false},"providers":{"kimi":{"providerId":"kimi","modelId":"kimi-k2.6","callCount":1},"asr":{"providerId":"qwen-asr","modelId":"qwen3-asr-flash","callCount":1,"inputAuthority":"task14-local-validation-wav"},"tts":{"chinese":{"providerId":"qwen-tts","modelId":"qwen3-tts-flash","voiceId":"Serena","languageCode":"zh-CN"},"math":{"providerId":"qwen-tts","modelId":"qwen3-tts-flash","voiceId":"Ethan","languageCode":"zh-CN"},"english":{"providerId":"qwen-tts","modelId":"qwen3-tts-flash","voiceId":"Jennifer","languageCode":"en-US"}}}}}}'
formal_provider_readiness_health_payload="${formal_provider_readiness_health_payload//mira.openmaic.formal-provider-readiness.v1/mira.openmaic.formal-provider-readiness.v2}"
formal_provider_readiness_health_payload="${formal_provider_readiness_health_payload/\"kimi\":{\"providerId\":\"kimi\",\"modelId\":\"kimi-k2.6\"/\"deepseek\":{\"providerId\":\"deepseek\",\"modelId\":\"deepseek-v4-pro\"}"
formal_provider_readiness_health_payload="${formal_provider_readiness_health_payload/\"runtimePolicy\":{/\"runtimePolicy\":{${model_policy_json},}"
validate_health_payload formal-provider-readiness "${formal_provider_readiness_health_payload}"
if validate_health_payload formal-provider-readiness "${formal_provider_readiness_health_payload/\"providerCall\":true/\"providerCall\":false}"; then
  echo "providerCall=false unexpectedly passed formal Provider readiness health" >&2
  exit 1
fi
validate_health_payload gateway '{"ok":true,"service":"mira-openmaic-runtime-gateway","sourceVersion":"openmaic@1.0.0"}'
if validate_health_payload openmaic '{"success":true,"status":"ok","version":"1.0.0","runtimePolicy":{"structuredScene":{"enforced":true,"policyId":"kimi-k2.6-thinking-disabled-v1","providerId":"kimi","modelId":"kimi-k2.6","stages":["scene-content","scene-content:slide","scene-content:quiz","scene-content:interactive","scene-content:pbl","scene-actions"],"thinking":{"mode":"disabled","enabled":false}}}}'; then
  echo "missing deterministic TTS policy unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/\"tts\":true/\"tts\":false}"; then
  echo "disabled TTS capability unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/\"asr\":true/\"asr\":false}"; then
  echo "disabled ASR capability unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/qwen3-asr-flash/other-asr}"; then
  echo "wrong deterministic ASR policy unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/mira-student-chrome.v6/mira-student-chrome.wrong}"; then
  echo "wrong student chrome policy unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/classroom-tab-session/wrong-persistence}"; then
  echo "wrong classroom audio-start persistence unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/\"autoPlayDefault\":true/\"autoPlayDefault\":false}"; then
  echo "wrong student classroom auto-play default unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/\"asrEnabled\":true/\"asrEnabled\":false}"; then
  echo "disabled student classroom ASR unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/\"operatorAsrPreferencePreserved\":true/\"operatorAsrPreferencePreserved\":false}"; then
  echo "mutating operator ASR preference unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/\"theme\":\"light\"/\"theme\":\"dark\"}"; then
  echo "wrong student classroom theme unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/\"idempotencyKey\":\"runtimeRequestId\"/\"idempotencyKey\":\"jobId\"}"; then
  echo "wrong formal generation idempotency policy unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/mira.openmaic.student-runtime-events.v1/mira.openmaic.student-runtime-events.wrong}"; then
  echo "wrong student Runtime event bridge unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic '{"success":true,"status":"ok","version":"1.0.0"}'; then
  echo "missing structured scene policy unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/,\"scene-actions\"/}"; then
  echo "missing scene-actions thinking policy unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/deepseek-v4-pro-flash-v1/wrong-policy}"; then
  echo "wrong structured scene policy unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/\"enabled\":true/\"enabled\":false}"; then
  echo "disabled deterministic recovery unexpectedly passed enabled health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/uKQl3vMr4d/wrong-source}"; then
  echo "wrong deterministic recovery source unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/${OPENMAIC_RECOVERY_CANONICAL_SPEC_SHA256}/0000000000000000000000000000000000000000000000000000000000000000}"; then
  echo "wrong deterministic recovery canonical spec unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/${OPENMAIC_RECOVERY_PATCH_SHA256}/ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff}"; then
  echo "wrong deterministic recovery patch unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/omrec_383729f8f7f637dc1cdc65d4/omrec_wrongparent000000000000}"; then
  echo "wrong TTS credential recovery parent unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256}/eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee}"; then
  echo "wrong TTS credential recovery patch unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/mira-formal-citation-recovery.v1/mira-formal-citation-recovery.wrong}"; then
  echo "wrong formal citation recovery policy unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/\"policyVersion\":\"mira-formal-citation-recovery.v1\"/\"policyVersion\":\"mira-formal-citation-recovery.v1\",\"unexpected\":true}"; then
  echo "non-exact formal citation recovery policy unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/${OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256}/dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd}"; then
  echo "wrong formal citation recovery patch unexpectedly passed health validation" >&2
  exit 1
fi
if validate_health_payload openmaic "${structured_health_payload/1.0.0/0.3.1}"; then
  echo "wrong OpenMAIC version unexpectedly passed health validation" >&2
  exit 1
fi
clear_openmaic_recovery_env

# A failed start cleanup may send TERM only after matching the exact process
# start identity. If that same process survives the full grace period, both
# services must preserve their PID and identity records and return failure.
(
  cleanup_pid=424242
  cleanup_start_hash="$(printf 'a%.0s' {1..64})"
  cleanup_build_hash="$(printf 'b%.0s' {1..64})"
  OPENMAIC_PID_FILE="${TMP_ROOT}/term-timeout-openmaic.pid"
  OPENMAIC_MODE_FILE="${TMP_ROOT}/term-timeout-openmaic.mode"
  GATEWAY_PID_FILE="${TMP_ROOT}/term-timeout-gateway.pid"
  GATEWAY_IDENTITY_FILE="${TMP_ROOT}/term-timeout-gateway.identity"
  printf '%s\n' "${cleanup_pid}" > "${OPENMAIC_PID_FILE}"
  write_openmaic_mode "${cleanup_pid}" "${cleanup_start_hash}" "${cleanup_build_hash}" "16.1.2" pending
  printf '%s\n' "${cleanup_pid}" > "${GATEWAY_PID_FILE}"
  write_gateway_identity "${cleanup_pid}" "${cleanup_start_hash}"

  term_calls=0
  openmaic_process_instance_matches() { return 0; }
  sleep() { :; }
  kill() {
    if [[ "$#" != "1" || "$1" != "${cleanup_pid}" ]]; then
      echo "failed-start cleanup attempted an unverified or non-TERM signal" >&2
      return 1
    fi
    term_calls=$((term_calls + 1))
  }

  if cleanup_failed_openmaic_start "${cleanup_pid}" "${cleanup_start_hash}" 2>/dev/null; then
    echo "live OpenMAIC failed-start identity was unexpectedly discarded" >&2
    exit 1
  fi
  [[ -f "${OPENMAIC_PID_FILE}" && -f "${OPENMAIC_MODE_FILE}" ]] || fail "live OpenMAIC cleanup removed its identity records"
  if cleanup_failed_gateway_start "${cleanup_pid}" "${cleanup_start_hash}" 2>/dev/null; then
    echo "live Gateway failed-start identity was unexpectedly discarded" >&2
    exit 1
  fi
  [[ -f "${GATEWAY_PID_FILE}" && -f "${GATEWAY_IDENTITY_FILE}" ]] || fail "live Gateway cleanup removed its identity records"
  [[ "${term_calls}" == "2" ]] || fail "failed-start cleanup did not send exactly one verified TERM per service"
)

# Once the exact target is confirmed dead, matching failed-start records are
# safe to remove. An unverifiable live PID remains fail closed and is never
# signalled, even while its port is still empty (it may bind that port later).
(
  cleanup_pid=434343
  cleanup_start_hash="$(printf 'c%.0s' {1..64})"
  cleanup_build_hash="$(printf 'd%.0s' {1..64})"
  OPENMAIC_PID_FILE="${TMP_ROOT}/dead-openmaic.pid"
  OPENMAIC_MODE_FILE="${TMP_ROOT}/dead-openmaic.mode"
  GATEWAY_PID_FILE="${TMP_ROOT}/dead-gateway.pid"
  GATEWAY_IDENTITY_FILE="${TMP_ROOT}/dead-gateway.identity"
  printf '%s\n' "${cleanup_pid}" > "${OPENMAIC_PID_FILE}"
  write_openmaic_mode "${cleanup_pid}" "${cleanup_start_hash}" "${cleanup_build_hash}" "16.1.2" pending
  printf '%s\n' "${cleanup_pid}" > "${GATEWAY_PID_FILE}"
  write_gateway_identity "${cleanup_pid}" "${cleanup_start_hash}"

  openmaic_process_instance_matches() { return 1; }
  process_is_alive() { return 1; }
  kill() {
    echo "failed-start cleanup signalled a process without a matching identity" >&2
    return 1
  }
  cleanup_failed_openmaic_start "${cleanup_pid}" "${cleanup_start_hash}"
  cleanup_failed_gateway_start "${cleanup_pid}" "${cleanup_start_hash}"
  [[ ! -e "${OPENMAIC_PID_FILE}" && ! -e "${OPENMAIC_MODE_FILE}" ]] || fail "dead OpenMAIC records were not removed"
  [[ ! -e "${GATEWAY_PID_FILE}" && ! -e "${GATEWAY_IDENTITY_FILE}" ]] || fail "dead Gateway records were not removed"

  OPENMAIC_PID_FILE="${TMP_ROOT}/uncertain-openmaic.pid"
  OPENMAIC_MODE_FILE="${TMP_ROOT}/uncertain-openmaic.mode"
  printf '%s\n' "${cleanup_pid}" > "${OPENMAIC_PID_FILE}"
  write_openmaic_mode "${cleanup_pid}" "${cleanup_start_hash}" "${cleanup_build_hash}" "16.1.2" pending
  process_is_alive() { return 0; }
  process_start_hash() { return 1; }
  port_is_listening() { return 1; }
  if cleanup_failed_openmaic_start "${cleanup_pid}" "${cleanup_start_hash}" 2>/dev/null; then
    echo "unverifiable live OpenMAIC PID on an empty port was unexpectedly forgotten" >&2
    exit 1
  fi
  [[ -f "${OPENMAIC_PID_FILE}" && -f "${OPENMAIC_MODE_FILE}" ]] || fail "uncertain OpenMAIC identity was not preserved"

  process_start_hash() { printf '%s' "${cleanup_start_hash}"; }
  if cleanup_failed_openmaic_start "${cleanup_pid}" invalid 2>/dev/null; then
    echo "live OpenMAIC PID with no usable expected start hash was unexpectedly forgotten" >&2
    exit 1
  fi
  [[ -f "${OPENMAIC_PID_FILE}" && -f "${OPENMAIC_MODE_FILE}" ]] || fail "live PID without a usable expected hash lost its records"
)

OPENMAIC_URL="http://127.0.0.1:1"
GATEWAY_URL="http://127.0.0.1:2"
HEALTH_TIMEOUT_SECONDS=1
if show_status >/dev/null 2>&1; then
  echo "unavailable runtime unexpectedly passed status" >&2
  exit 1
fi

echo "native runtime provider opt-in and health tests passed"
