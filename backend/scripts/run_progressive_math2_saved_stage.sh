#!/usr/bin/env bash
# Exact saved-stage recovery of math slot two's audited editorial attempt two.
# Native prepare/inspect remain local; complete is an explicit paid operation.
set -euo pipefail
mode="${1:-}"; expected_snapshot="${2:-}"
case "$mode" in
  prepare|inspect) [[ $# == 1 ]] || exit 2 ;;
  complete) [[ $# == 2 && "$expected_snapshot" =~ ^[a-f0-9]{64}$ ]] || exit 2 ;;
  *) echo 'Usage: run_progressive_math2_saved_stage.sh prepare|inspect|complete [REVIEWED_SNAPSHOT_SHA256]' >&2; exit 2 ;;
esac
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
manifest="${repo}/output/progressive-preview/saved-stage-math-slot2-attempt2/manifest.json"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${repo}/backend" \
 /private/tmp/mira-progression-test-venv/bin/python - "$repo" "$mode" "$expected_snapshot" <<'PYCHECK'
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
from integrations.openmaic_formal_quality import quality_sha
root=Path(sys.argv[1]); mode=sys.argv[2]; expected=sys.argv[3]
base=root/'output/progressive-preview/saved-stage-math-slot2-attempt2'
native=root/'openmaic-runtime/.runtime/OpenMAIC'
sha=lambda b:hashlib.sha256(b).hexdigest()
def require(ok,reason):
    if not ok: raise SystemExit('MATH2_SAVED_STAGE_STOP: '+reason)
audit=json.loads((base/'source-audit.json').read_bytes())
proposal_audit=json.loads((base/'repair-audit.json').read_bytes())
manifest=json.loads((base/'manifest.json').read_bytes())
require(sha((base/'repair-audit.json').read_bytes())=='a5818c2847c44dc35d1edddc1027350af1369c801228b10cc2a10e28bd0af9d1','reviewed proposal audit changed')
require(sha((base/'repair-proposal.json').read_bytes())==proposal_audit['proposalSha256'],'proposal changed')
require(sha((base/'source-document.json').read_bytes())==audit['sourceDocumentSha256'],'original document archive changed')
require(manifest=={k:audit[k] for k in ('jobId','sourceJobSha256','sessionId','stageId','sourceSnapshotSha256')}|{'repairPath':'repair-proposal.json'},'manifest identity changed')
require(audit['jobId']=='omformal_6cddfc21f47d63291444dfab'
    and audit['runtimeId']=='omfc_QpzBHjJGUFhjAOYID7WAW7MNmD3lfDejGJuPv31Ku90'
    and audit['stageId']=='stage-NjgpUvNeOs','only editorial attempt two is authorized')
raw=(native/'data/classroom-jobs'/(audit['jobId']+'.json')).read_bytes(); job=json.loads(raw)
require(raw==(base/'original-native-job.json').read_bytes() and sha(raw)==audit['sourceJobSha256']
    and job['status']=='failed' and job.get('error')=='FORMAL_AUDIO_ASR_INCOMPLETE:17:succeeded'
    and job['formalInputSha256']==audit['formalInputSha256'],'original failed Native job changed')
wrapper=(root/'openmaic-runtime/scripts/native-runtime.sh').read_text()
f=wrapper[wrapper.index('run_openmaic_production_foreground() {'):]
s=f.index('  exec env -i '+chr(92)+'\n');e=f.index('    "${node_bin}" node_modules/next/dist/bin/next start',s)
require(sha(f[s:e].encode())=='394cda52d9b7f36ffab52e8cdcfb010f41fa00fedc1ac8c22617c940e2df74a9','production environment projection changed')
if mode=='complete':
    folder=native/'data/formal-saved-stage-recoveries'/audit['jobId']
    require(not (folder/'completion.json').exists() and not list(folder.glob('complete*.claim')),
        'previous completion/claim exists: retain it and diagnose, never replay')
    prepared=json.loads((folder/'prepared-snapshot.json').read_bytes())
    require(quality_sha(prepared)==expected,'expected reviewed snapshot differs')
    preflight=json.loads((folder/'browser-preflight.json').read_bytes())
    identity={k:manifest[k] for k in ('sourceJobSha256','sourceSnapshotSha256','sessionId','stageId')}
    identity['repairSnapshotSha256']=expected
    require(preflight.get('passed') is True and all(preflight.get(k)==v for k,v in identity.items()),'exact successful browser inspect required')
    checks=preflight.get('checks',[]);scenes={s['id'] for s in prepared['scenes']}
    require(len(checks)==len(scenes)*2 and all(c.get('passed') is True for c in checks)
        and {(c['sceneId'],c['viewport']['width'],c['viewport']['height']) for c in checks}
        =={(s,w,h) for s in scenes for w,h in ((1280,720),(1024,768))},'all two-viewport checks required')
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(preflight['checkedAt'].replace('Z','+00:00'))).total_seconds()
    require(0<=age<=86400,'browser inspection expired')
    from core.config import AppConfig
    from core.database import Database
    from services.progressive_math2_revision import activated_revision,formal_package_identity,select_revision_runtimes
    c=Database(AppConfig.from_env().DATABASE_URL).connect()
    try:
        c.execute('START TRANSACTION READ ONLY')
        revision=activated_revision(c);require(bool(revision),'audited editorial activation missing')
        identity=revision['audit']['identity']
        history=[dict(r) for r in c.execute('SELECT * FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=?',(identity['buildItemId'],)).fetchall()]
        current,historical=select_revision_runtimes(c,identity,history)
        require(len(current)==1 and len(historical)==1 and current[0]['id']==audit['runtimeId']
            and current[0]['upstream_job_id']==audit['jobId'] and current[0]['request_id']==audit['runtimeRequestId']
            and current[0]['status'] in {'generating','failed'},'current editable recovery Runtime changed')
        ids=formal_package_identity(c,build_item_id=identity['buildItemId'],course_id=current[0]['course_id'],course_version=current[0]['course_version'])
        require(ids['packageId']==audit['packageId']==current[0]['package_id'],'editorial package identity changed')
        require(c.execute('SELECT COUNT(*) AS n FROM learning_curriculum_classroom_item_receipts WHERE build_item_id=?',(identity['buildItemId'],)).fetchone()['n']==0,'Host receipt already exists')
        auth_id=job['formalInput']['paidBudget']['authorizationId']
        auth=c.execute('SELECT * FROM learning_budget_authorizations WHERE id=?',(auth_id,)).fetchone()
        require(auth and json.loads(auth['scope_json'])==identity['scope'],'exact production scope changed')
        for other in c.execute('SELECT id,scope_json FROM learning_budget_authorizations').fetchall():
            if json.loads(other['scope_json'])==identity['scope']:
                require(c.execute("SELECT COUNT(*) AS n FROM learning_budget_reservations WHERE authorization_id=? AND state IN ('reserved','dispatched','unknown')",(other['id'],)).fetchone()['n']==0,'same-scope call unresolved')
    finally:
        c.rollback();c.close()
print(json.dumps({'status':'local_guards_passed','mode':mode,'jobId':audit['jobId'],'expectedSnapshot':expected or None,'providerCalls':0}))
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
