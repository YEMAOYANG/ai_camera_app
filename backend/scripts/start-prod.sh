#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  BACKEND_PYTHON="${PYTHON_BIN}"
elif [[ -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
  BACKEND_PYTHON="${BACKEND_DIR}/.venv/bin/python"
elif [[ -x "${BACKEND_DIR}/venv/bin/python" ]]; then
  BACKEND_PYTHON="${BACKEND_DIR}/venv/bin/python"
else
  BACKEND_PYTHON="$(command -v python3)"
fi

THREADS="${MIRA_BACKEND_THREADS:-8}"
TIMEOUT_SECONDS="${MIRA_BACKEND_TIMEOUT_SECONDS:-300}"
BIND_ADDRESS="${MIRA_BACKEND_BIND:-127.0.0.1:8000}"
if [[ ! "${THREADS}" =~ ^[0-9]+$ ]] || (( THREADS < 2 || THREADS > 64 )); then
  echo "MIRA_BACKEND_THREADS must be an integer between 2 and 64." >&2
  exit 2
fi
if [[ ! "${TIMEOUT_SECONDS}" =~ ^[0-9]+$ ]] || (( TIMEOUT_SECONDS < 30 || TIMEOUT_SECONDS > 900 )); then
  echo "MIRA_BACKEND_TIMEOUT_SECONDS must be an integer between 30 and 900." >&2
  exit 2
fi
case "${BIND_ADDRESS}" in
  "127.0.0.1:8000"|"0.0.0.0:8000") ;;
  *)
    echo "MIRA_BACKEND_BIND must be 127.0.0.1:8000 or 0.0.0.0:8000." >&2
    exit 2
    ;;
esac

export APP_ENV="production"
export APP_DEBUG="0"
export APP_HOST="${BIND_ADDRESS%:*}"
export APP_PORT="8000"
export MIRA_PROCESS_ROLE="${MIRA_PROCESS_ROLE:-api}"
export PYTHONUNBUFFERED="1"

cd "${BACKEND_DIR}"
exec "${BACKEND_PYTHON}" -m gunicorn \
  --workers 1 \
  --worker-class gthread \
  --threads "${THREADS}" \
  --timeout "${TIMEOUT_SECONDS}" \
  --bind "${BIND_ADDRESS}" \
  --access-logfile - \
  --error-logfile - \
  app:app
