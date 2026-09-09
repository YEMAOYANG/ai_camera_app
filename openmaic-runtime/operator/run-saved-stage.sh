#!/usr/bin/env bash
set -euo pipefail
OPERATOR_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPERATOR_MODE="${1:?inspect or complete required}"
OPERATOR_MANIFEST="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "${2:?manifest required}")"
export MIRA_OPENMAIC_ENABLE_MODEL_PROVIDER=1
export MIRA_OPENMAIC_ENABLE_QWEN_TTS=1
export MIRA_OPENMAIC_ENABLE_QWEN_ASR=1
source "${OPERATOR_ROOT}/scripts/native-runtime.sh"
load_runtime_origin_env
load_openmaic_provider_env
load_openmaic_internal_token_env
cd "${SOURCE_DIR}"
node - <<'JS'
const { createRequire } = require('node:module');
const esbuild = createRequire(require.resolve('tsx'))('esbuild');
const pkg = require('./package.json');
esbuild.buildSync({ entryPoints: ['scripts/recover-formal-saved-stage.ts'],
  outfile: 'data/operators/recover-formal-saved-stage.mjs', bundle: true,
  platform: 'node', format: 'esm', loader: { '.css': 'empty' },
  external: Object.keys({ ...pkg.dependencies, ...pkg.devDependencies }).filter(name => !name.startsWith('@openmaic/')),
  banner: { js: "import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);" } });
JS
exec env \
  NODE_OPTIONS=--no-experimental-webstorage \
  DEFAULT_MODEL="${OPENMAIC_DEFAULT_MODEL}" \
  OPENMAIC_AGENT_RUNTIME_ENABLED=1 \
  DATABASE_URL="${OPENMAIC_AGENT_DATABASE_URL}" \
  PERSISTENCE_DEV_TOKEN="${OPENMAIC_PERSISTENCE_DEV_TOKEN}" \
  MODEL_ROUTES="${OPENMAIC_MODEL_ROUTES}" \
  DEEPSEEK_API_KEY="${OPENMAIC_DEEPSEEK_API_KEY}" \
  DEEPSEEK_BASE_URL="${OPENMAIC_DEEPSEEK_BASE_URL}" \
  DEEPSEEK_MODELS="${OPENMAIC_DEEPSEEK_MODELS}" \
  TTS_QWEN_API_KEY="${OPENMAIC_TTS_QWEN_API_KEY}" \
  TTS_QWEN_BASE_URL="${OPENMAIC_TTS_QWEN_BASE_URL}" \
  TTS_QWEN_MODELS="${OPENMAIC_TTS_QWEN_MODELS}" \
  ASR_QWEN_API_KEY="${OPENMAIC_ASR_QWEN_API_KEY}" \
  ASR_QWEN_BASE_URL="${OPENMAIC_ASR_QWEN_BASE_URL}" \
  ASR_QWEN_MODELS="${OPENMAIC_ASR_QWEN_MODELS}" \
  MIRA_OPENMAIC_REQUIRE_QWEN_TTS=1 \
  MIRA_OPENMAIC_REQUIRE_QWEN_ASR=1 \
  MIRA_OPENMAIC_QWEN_TTS_MODEL="${OPENMAIC_TTS_QWEN_MODELS}" \
  MIRA_OPENMAIC_QWEN_TTS_VOICE="${OPENMAIC_TTS_QWEN_VOICE}" \
  MIRA_OPENMAIC_QWEN_ASR_MODEL="${OPENMAIC_ASR_QWEN_MODELS}" \
  MIRA_INTERNAL_API_TOKEN="${OPENMAIC_INTERNAL_API_TOKEN}" \
  MIRA_FORMAL_QA_BASE_URL=http://127.0.0.1:3100 \
  MIRA_FORMAL_QA_BROWSER_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  node data/operators/recover-formal-saved-stage.mjs "${OPERATOR_MODE}" "${OPERATOR_MANIFEST}"
