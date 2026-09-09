#!/bin/bash
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

cd "${REPO_ROOT}"
if "${SCRIPT_DIR}/local-test-stack.sh" start; then
  echo "Mira 课堂服务已启动；Student Web 和 OpenMAIC 均使用生产构建。"
  exit 0
fi

echo "Mira 课堂服务启动失败，请查看 /tmp/mira-local-test-stack 下的日志。" >&2
exit 1
