#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "══ Vision 回归用例 ══"
python3 -m unittest tests.test_vision_regression -v
echo "══ 完成 ══"
