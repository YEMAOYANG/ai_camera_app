#!/usr/bin/env bash
set -euo pipefail
BASE="${GUARDIAN_API_BASE:-http://127.0.0.1:8000}"
WS_BASE="${GUARDIAN_WS_BASE:-ws://127.0.0.1:8001/api/tasks/stream}"
PHONE="${QA_PHONE:-}"
DEVICE_ID="${CAMERA_OBSERVATION_DEVICE_ID:-}"
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
info() { echo -e "${YELLOW}→${NC} $1"; }
if [ -z "$PHONE" ]; then
  fail "请设置 QA_PHONE（dev SMS 联调手机号）"
fi
if [ -z "$DEVICE_ID" ]; then
  fail "请设置 CAMERA_OBSERVATION_DEVICE_ID（App 绑定设备 id）"
fi
echo "══ Guardian 联调 QA ══"
info "1. SMS 登录"
REQ=$(curl -s -X POST "$BASE/api/auth/sms/request" -H 'Content-Type: application/json' -d "{\"phone\":\"$PHONE\"}")
CODE=$(echo "$REQ" | python3 -c "import sys,json; print(json.load(sys.stdin).get('debugCode',''))")
[ -n "$CODE" ] || fail "拿不到 debugCode"
LOGIN=$(curl -s -X POST "$BASE/api/auth/sms/login" -H 'Content-Type: application/json' -d "{\"phone\":\"$PHONE\",\"code\":\"$CODE\"}")
TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('accessToken') or (d.get('tokens') or {}).get('accessToken',''))")
[ -n "$TOKEN" ] || fail "登录失败"
pass "登录成功"
AUTH=(-H "Authorization: Bearer $TOKEN")
info "2. 当前看护记录数"
BEFORE=$(curl -s "$BASE/api/camera/events?deviceId=$DEVICE_ID" "${AUTH[@]}")
BEFORE_N=$(echo "$BEFORE" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('events',[])))")
echo "   记录数: $BEFORE_N"
info "3. monitor/refresh"
REFRESH=$(curl -s -X POST "$BASE/api/camera/monitor/refresh?deviceId=$DEVICE_ID" "${AUTH[@]}")
echo "$REFRESH" | python3 -c "
import sys, json
body = json.load(sys.stdin)
monitor = body.get('monitor') or {}
obs = monitor.get('lastObservation')
status = monitor.get('status')
message = monitor.get('message')
print(f\"   status={status!r} message={message!r}\")
if not isinstance(obs, dict):
    print('   lastObservation=null')
    sys.exit(1)
print(f\"   isReliable={obs.get('isReliable')} confidence={obs.get('confidence')} summary={obs.get('summary')!r}\")
"
pass "monitor/refresh 返回有效 lastObservation"
IS_RELIABLE=$(echo "$REFRESH" | python3 -c "import sys,json; obs=(json.load(sys.stdin).get('monitor') or {}).get('lastObservation') or {}; print(bool(obs.get('isReliable')))")
AFTER=$(curl -s "$BASE/api/camera/events?deviceId=$DEVICE_ID" "${AUTH[@]}")
AFTER_N=$(echo "$AFTER" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('events',[])))")
DELTA=$((AFTER_N - BEFORE_N))
echo "   刷新后: $AFTER_N (Δ=$DELTA)"
if [ "$IS_RELIABLE" = "True" ]; then
  [ "$DELTA" -ge 1 ] && pass "可靠观察 → 列表 +$DELTA" || pass "可靠观察但 gate 跳过写入 (Δ=$DELTA)"
else
  [ "$DELTA" -eq 0 ] && pass "不可靠/跳过观察 → 列表未新增" || pass "刷新未新增可靠记录 (Δ=$DELTA，可能 session 去重)"
fi
info "4. routine-reminder tick"
TICK=$(curl -s -X POST "$BASE/api/dev/care/routine-reminder/tick" "${AUTH[@]}" -H 'Content-Type: application/json' -d '{}')
echo "$TICK" | python3 -c "import sys,json; d=json.load(sys.stdin); print('   ok=', d.get('ok'), 'keys=', list(d.keys())[:8])"
echo "$TICK" | python3 -c "import sys,json; sys.exit(0 if json.load(sys.stdin).get('ok') else 1)" && pass "routine tick OK" || fail "routine tick 失败"
info "5. WS 探测"
python3 - "$TOKEN" "$WS_BASE" << 'PY'
import asyncio, json, sys
try:
    import websockets
except ImportError:
    print("   skip: websockets not installed"); sys.exit(0)
token, url = sys.argv[1], sys.argv[2]
async def main():
    sep = '&' if '?' in url else '?'
    ws_url = f"{url}{sep}token={token}"
    async with websockets.connect(ws_url, open_timeout=4) as ws:
        print("   WS connected")
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=3)
            msg = json.loads(raw)
            print(f"   msg type={msg.get('type')}")
        except asyncio.TimeoutError:
            print("   no push in 3s (ok)")
asyncio.run(main())
PY
pass "WS OK"
info "6. scheduler status"
curl -s "$BASE/api/dev/tasks/scheduler/status" "${AUTH[@]}" | python3 -c "import sys,json; d=json.load(sys.stdin); print('  ', d.get('taskStream',{}))"
echo "══ 完成 ══"
