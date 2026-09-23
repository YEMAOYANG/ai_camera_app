#!/usr/bin/env bash
# Exact saved English second-set recovery; never starts an Agent or regenerates scenes.
set -euo pipefail
mode="${1:-}"; expected_snapshot="${2:-}"
case "$mode" in
  prepare|inspect) [[ $# == 1 ]] || exit 2 ;;
  complete) [[ $# == 2 && "$expected_snapshot" =~ ^[a-f0-9]{64}$ ]] || exit 2 ;;
  *) echo 'Usage: run_progressive_english2_saved_stage.sh prepare|inspect|complete [REVIEWED_SNAPSHOT_SHA256]' >&2; exit 2 ;;
esac
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
manifest="${repo}/output/progressive-preview/saved-stage-english-slot2/manifest.json"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${repo}/backend" \
 "${repo}/backend/.venv/bin/python" - "$repo" "$mode" "$expected_snapshot" <<'PYCHECK'
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
from integrations.openmaic_formal_quality import quality_sha
root=Path(sys.argv[1]);mode=sys.argv[2];expected=sys.argv[3]
base=root/'output/progressive-preview/saved-stage-english-slot2';native=root/'openmaic-runtime/.runtime/OpenMAIC'
sha=lambda b:hashlib.sha256(b).hexdigest()
def require(ok,reason):
    if not ok:raise SystemExit('ENGLISH2_SAVED_STAGE_STOP: '+reason)
audit=json.loads((base/'source-audit.json').read_bytes());ids=audit['identity']
require(sha((base/'source-audit.json').read_bytes())=='889a83532086a9ae6ea29ba637d5b7988e1b6ccd0bd821e05220526ff82fa5b1','source audit changed')
require(sha((base/'repair-audit.json').read_bytes())=='b388b8e6583adddf0d322fc598381a9a70e89d13462d92b0e86fc3ccbd9a6479','reviewable repair audit changed')
repair=json.loads((base/'repair-audit.json').read_bytes());manifest=json.loads((base/'manifest.json').read_bytes())
require(sha((base/'repair-proposal.json').read_bytes())==repair['proposalSha256']=='a3cc72a68de2a806bc6d7ce93a5ae6a3c98d88e5234ef18ce33d9f4ed8bd9618','proposal changed')
require(sha((base/'source-document.json').read_bytes())==audit['sourceDocumentSha256'],'source document changed')
require(manifest=={'jobId':ids['job'],'sourceJobSha256':audit['sourceJobSha256'],'sessionId':ids['session'],
    'stageId':ids['stage'],'sourceSnapshotSha256':audit['sourceSnapshotSha256'],'repairPath':'repair-proposal.json'},'manifest changed')
require(ids['job']=='omformal_90ed56f8cb07a09d6c51296a' and ids['runtime']=='omfc_8EsR81VIt_yHr1YpuYYAA5Jbyt3HkBfHiNuQgt4SlP4'
    and ids['stage']=='stage-FC2nTYOIET' and ids['item']=='catalog_build_item_d5a6b286d326400b49241b5d','exact EN2 identity required')
raw=(native/'data/classroom-jobs'/(ids['job']+'.json')).read_bytes();job=json.loads(raw)
require(raw==(base/'original-native-job.json').read_bytes() and sha(raw)==audit['sourceJobSha256']
    and job['status']=='failed' and job['error']=='FORMAL_PROFESSIONAL_SESSION_FAILED:Insufficient Balance'
    and job['formalInputSha256']==ids['inputSha'],'original failed Native source changed')
require(quality_sha(job['formalInput'])==ids['inputSha'],'formal input changed')
spec=json.loads(job['formalInput']['requirement'])
require(spec['buildItemId']==ids['item'] and spec['course']['id']==ids['course'],'source course changed')
wrapper=(root/'openmaic-runtime/scripts/native-runtime.sh').read_text()
f=wrapper[wrapper.index('run_openmaic_production_foreground() {'):]
s=f.index('  exec env -i '+chr(92)+'\n');e=f.index('    "${node_bin}" node_modules/next/dist/bin/next start',s)
require(sha(f[s:e].encode())=='394cda52d9b7f36ffab52e8cdcfb010f41fa00fedc1ac8c22617c940e2df74a9','production environment projection changed')
if mode=='complete':
    folder=native/'data/formal-saved-stage-recoveries'/ids['job']
    require(not (folder/'completion.json').exists() and not list(folder.glob('complete*.claim')),'existing completion attempt: do not replay')
    prepared=json.loads((folder/'prepared-snapshot.json').read_bytes())
    require(quality_sha(prepared)==expected,'reviewed snapshot changed')
    preflight=json.loads((folder/'browser-preflight.json').read_bytes())
    identity={k:manifest[k] for k in ('sourceJobSha256','sourceSnapshotSha256','sessionId','stageId')};identity['repairSnapshotSha256']=expected
    require(preflight.get('passed') is True and all(preflight.get(k)==v for k,v in identity.items()),'exact successful browser inspection required')
    checks=preflight.get('checks',[]);scenes={s['id'] for s in prepared['scenes']}
    require(len(scenes)==8 and len(checks)==16 and all(c.get('passed') is True for c in checks)
        and {(c['sceneId'],c['viewport']['width'],c['viewport']['height']) for c in checks}
        =={(s,w,h) for s in scenes for w,h in ((1280,720),(1024,768))},'all eight pages must pass both viewports')
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(preflight['checkedAt'].replace('Z','+00:00'))).total_seconds()
    require(0<=age<=86400,'browser inspection expired')
    from core.config import AppConfig
    from core.database import Database
    from scripts.generate_progressive_preview import preview_identities,assert_preview_policy
    from services.learning_transport_terminal_reconciliation import verified_transport_terminal_reservation_ids
    identities=preview_identities('primary_6');identity=next(i for i in identities if i['buildItemId']==ids['item'])
    assert_preview_policy(root/'backend/content/learning_classroom_policy.json',identities)
    c=Database(AppConfig.from_env().DATABASE_URL).connect()
    try:
        c.execute('START TRANSACTION READ ONLY')
        rows=c.execute('SELECT * FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=?',(ids['item'],)).fetchall()
        require(len(rows)==1,'exactly one original Runtime required');r=dict(rows[0])
        require(r['id']==ids['runtime'] and r['upstream_job_id']==ids['job'] and r['request_id']==job['runtimeRequestId']
            and r['course_id']==ids['course'] and r['course_version']==spec['course']['version']
            and r['package_id']==spec['course']['packageId'] and r['package_version']==spec['course']['packageVersion']
            and r['status'] in {'generating','failed'} and not r.get('retired_at'),'original Runtime changed')
        require(c.execute('SELECT COUNT(*) AS n FROM learning_curriculum_classroom_item_receipts WHERE build_item_id=?',(ids['item'],)).fetchone()['n']==0,'Host receipt already exists')
        auth_id=job['formalInput']['paidBudget']['authorizationId'];auth=c.execute('SELECT * FROM learning_budget_authorizations WHERE id=?',(auth_id,)).fetchone()
        require(auth and not auth['revoked_at'] and json.loads(auth['scope_json'])==identity['scope'],'production scope changed')
        pending=[dict(r) for r in c.execute("SELECT * FROM learning_budget_reservations WHERE authorization_id=? AND state IN ('reserved','dispatched','unknown')",(auth_id,)).fetchall()]
        budget_raw=(base/'six-scope-budget-audit.json').read_bytes()
        require(sha(budget_raw)=='b5f57f930ba5bc6905b01a82380fc91056b0987b514afb0fcf3a797bb462fcf8','original budget archive changed')
        old=json.loads(budget_raw);saved=next(x for x in old['details'] if x['authorization']['id']==auth_id)
        old_unknown=next(r for r in saved['reservations'] if r['id']=='a5d229086206479a8cf2937c92b3aec2d3962999cfd975bd5851af58325ef070')
        require(pending==[old_unknown],'only the exact preserved 402 unknown may remain; no active or other unknown calls')
        require(old_unknown['id'] in verified_transport_terminal_reservation_ids(c,pending_rows=pending),'exact 402 local transport terminal receipt required; financial hold must remain unchanged')
    finally:c.rollback();c.close()
print(json.dumps({'status':'local_guards_passed','mode':mode,'jobId':ids['job'],'expectedSnapshot':expected or None,'providerCalls':0}))
PYCHECK
source "${repo}/openmaic-runtime/scripts/native-runtime.sh"
[[ "$SOURCE_DIR" == "${repo}/openmaic-runtime/.runtime/OpenMAIC" ]] || exit 2
load_runtime_origin_env
load_openmaic_provider_env
load_openmaic_recovery_env
load_openmaic_formal_citation_recovery_env
load_openmaic_internal_token_env
node_bin="$(command -v node)"
node_major="$(${node_bin} -p 'Number(process.versions.node.split(".")[0])')"
openmaic_version="$(cd "${SOURCE_DIR}" && "${node_bin}" -p 'require("./package.json").version')"
node_options=''
if ((node_major >= 25)); then node_options='--no-experimental-webstorage'; fi
cd "${SOURCE_DIR}"
  exec env -i \
    PATH="${PATH}" \
    HOME="${HOME}" \
    TMPDIR="${TMPDIR:-/tmp}" \
    LANG="${LANG:-en_US.UTF-8}" \
    NODE_OPTIONS="${node_options}" \
    NODE_ENV=production \
    MIRA_OPENMAIC_NATIVE_BUILD=1 \
    MIRA_OPENMAIC_PRIVATE_PORT="${OPENMAIC_PORT}" \
    MIRA_FORMAL_QA_BASE_URL="${OPENMAIC_URL}" \
    MIRA_FORMAL_QA_BROWSER_PATH="${MIRA_FORMAL_QA_BROWSER_PATH:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}" \
    npm_package_version="${openmaic_version}" \
    NEXT_PUBLIC_PRO_WORKBENCH_ENABLED=true \
    NEXT_PUBLIC_MIRA_WORKBENCH_DOCUMENTS_ENABLED=true \
    NEXT_PUBLIC_MAIC_EDITOR_ENABLED=true \
    NEXT_PUBLIC_MAIC_EDITOR_RENDERER_ENABLED=true \
    NEXT_PUBLIC_MAIC_PLAYBACK_RENDERER_ENABLED=true \
    NEXT_PUBLIC_PI_CHAT_ENABLED=true \
    NEXT_PUBLIC_ENABLE_VIDEO_EXPORT=true \
    NEXT_PUBLIC_ENABLE_PPTX_IMPORT=true \
    ALLOWED_FRAME_ANCESTORS="${MIRA_STUDENT_WEB_ORIGIN}" \
    DEFAULT_MODEL="${OPENMAIC_DEFAULT_MODEL}" \
    OPENMAIC_AGENT_RUNTIME_ENABLED="${OPENMAIC_AGENT_RUNTIME_ENABLED}" \
    DATABASE_URL="${OPENMAIC_AGENT_DATABASE_URL}" \
    PERSISTENCE_DEV_TOKEN="${OPENMAIC_PERSISTENCE_DEV_TOKEN}" \
    MODEL_ROUTES="${OPENMAIC_MODEL_ROUTES}" \
    MIRA_OPENMAIC_ENABLE_WEB_SEARCH="${OPENMAIC_WEB_SEARCH_ENABLED}" \
    MIRA_OPENMAIC_WEB_SEARCH_PROVIDER="${OPENMAIC_WEB_SEARCH_PROVIDER}" \
    BRAVE_BASE_URL="${OPENMAIC_BRAVE_BASE_URL}" \
    BRAVE_API_KEY="${OPENMAIC_BRAVE_API_KEY}" \
    BRAVE_ENABLED="${OPENMAIC_BRAVE_ENABLED}" \
    BAIDU_BASE_URL="${OPENMAIC_BAIDU_BASE_URL}" \
    BAIDU_API_KEY="${OPENMAIC_BAIDU_API_KEY}" \
    BAIDU_ENABLED="${OPENMAIC_BAIDU_ENABLED}" \
    MIRA_OPENMAIC_STRUCTURED_SCENE_POLICY="${OPENMAIC_STRUCTURED_SCENE_POLICY_ID}" \
    DEEPSEEK_API_KEY="${OPENMAIC_DEEPSEEK_API_KEY}" \
    DEEPSEEK_BASE_URL="${OPENMAIC_DEEPSEEK_BASE_URL}" \
    DEEPSEEK_MODELS="${OPENMAIC_DEEPSEEK_MODELS}" \
    TTS_QWEN_API_KEY="${OPENMAIC_TTS_QWEN_API_KEY}" \
    TTS_QWEN_BASE_URL="${OPENMAIC_TTS_QWEN_BASE_URL}" \
    TTS_QWEN_MODELS="${OPENMAIC_TTS_QWEN_MODELS}" \
    MIRA_OPENMAIC_REQUIRE_QWEN_TTS="${OPENMAIC_REQUIRE_QWEN_TTS}" \
    MIRA_OPENMAIC_QWEN_TTS_MODEL="${OPENMAIC_TTS_QWEN_MODELS}" \
    MIRA_OPENMAIC_QWEN_TTS_VOICE="${OPENMAIC_TTS_QWEN_VOICE}" \
    ASR_QWEN_API_KEY="${OPENMAIC_ASR_QWEN_API_KEY}" \
    ASR_QWEN_BASE_URL="${OPENMAIC_ASR_QWEN_BASE_URL}" \
    ASR_QWEN_MODELS="${OPENMAIC_ASR_QWEN_MODELS}" \
    MIRA_OPENMAIC_REQUIRE_QWEN_ASR="${OPENMAIC_REQUIRE_QWEN_ASR}" \
    MIRA_OPENMAIC_QWEN_ASR_MODEL="${OPENMAIC_ASR_QWEN_MODELS}" \
    DEFAULT_IMAGE_PROVIDER="${OPENMAIC_DEFAULT_IMAGE_PROVIDER}" \
    IMAGE_QWEN_IMAGE_API_KEY="${OPENMAIC_IMAGE_QWEN_IMAGE_API_KEY}" \
    IMAGE_QWEN_IMAGE_BASE_URL="${OPENMAIC_IMAGE_QWEN_IMAGE_BASE_URL}" \
    IMAGE_QWEN_IMAGE_MODELS="${OPENMAIC_IMAGE_QWEN_IMAGE_MODELS}" \
    DEFAULT_VIDEO_PROVIDER="${OPENMAIC_DEFAULT_VIDEO_PROVIDER}" \
    VIDEO_HAPPYHORSE_API_KEY="${OPENMAIC_VIDEO_HAPPYHORSE_API_KEY}" \
    VIDEO_HAPPYHORSE_BASE_URL="${OPENMAIC_VIDEO_HAPPYHORSE_BASE_URL}" \
    VIDEO_HAPPYHORSE_MODELS="${OPENMAIC_VIDEO_HAPPYHORSE_MODELS}" \
    MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED="${OPENMAIC_RECOVERY_ENABLED}" \
    MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_RECOVERY_SOURCE_JOB_ID}" \
    MIRA_OPENMAIC_DETERMINISTIC_RECOVERY_PATCH_SHA256="${OPENMAIC_RECOVERY_PATCH_SHA256}" \
    MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED}" \
    MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_SOURCE_JOB_ID}" \
    MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PARENT_RECOVERY_ID}" \
    MIRA_OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256="${OPENMAIC_TTS_CREDENTIAL_RECOVERY_PATCH_SHA256}" \
    MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED="${OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED}" \
    MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID="${OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID}" \
    MIRA_OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256="${OPENMAIC_FORMAL_CITATION_RECOVERY_PATCH_SHA256}" \
    MIRA_BACKEND_INTERNAL_URL="${MIRA_BACKEND_INTERNAL_URL:-http://127.0.0.1:8000}" \
    MIRA_INTERNAL_API_TOKEN="${OPENMAIC_INTERNAL_API_TOKEN}" \
    "${node_bin}" --require tsx/cjs --require "${repo}/openmaic-runtime/scripts/native-operator-esm-compat.cjs" \
      scripts/recover-formal-saved-stage.ts "${mode}" "${manifest}"
