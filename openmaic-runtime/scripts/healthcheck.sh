#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=native-runtime.sh
source "${SCRIPT_DIR}/native-runtime.sh"

OPENMAIC_URL="${OPENMAIC_FULL_RUNTIME_INTERNAL_URL:-http://127.0.0.1:3100}"
GATEWAY_URL="${MIRA_RUNTIME_PUBLIC_ORIGIN:-http://127.0.0.1:3101}"
show_status
