#!/usr/bin/env bash
# Exact English1 frozen-snapshot audio recovery; official per-segment protocols only.
set -euo pipefail
mode="${1:-}"; asr_id="${2:-}"; diagnostic_sha="${3:-}"
[[ "$asr_id" =~ ^formal_asr_[a-f0-9]{48}$ ]] || exit 2
case "$mode" in
  adopt-english-repair) [[ $# == 3 && "$diagnostic_sha" =~ ^[a-f0-9]{64}$ ]] || exit 2 ;;
  diagnose-audio|repair-audio|complete-audio-tail|prepare-english-repair-diagnostic|diagnose-english-repair-audio|prepare-english-language-repair|repair-english-language-audio) [[ $# == 2 ]] || exit 2 ;;
  *) exit 2 ;;
esac
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
manifest="${repo}/output/progressive-preview/saved-stage-english-slot1/audio-${asr_id}-${mode}.json"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${repo}/backend" \
 "${repo}/backend/.venv/bin/python" - "$repo" "$mode" "$asr_id" "$diagnostic_sha" <<'PYCHECK'
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
from integrations.openmaic_formal_quality import quality_sha
root=Path(sys.argv[1]); mode=sys.argv[2]; asr_id=sys.argv[3]; diagnostic_sha=sys.argv[4]
expected='ce327bcb84a0836065def3bc20fcfe62ede100a099be5194df5b4c8014c2d8a9'
base=root/'output/progressive-preview/saved-stage-english-slot1'
native=root/'openmaic-runtime/.runtime/OpenMAIC'
sha=lambda b:hashlib.sha256(b).hexdigest()
def require(ok,reason):
    if not ok: raise SystemExit('ENGLISH1_SAVED_STAGE_STOP: '+reason)
audit=json.loads((base/'source-audit.json').read_bytes())
proposal_audit=json.loads((base/'repair-audit.json').read_bytes())
manifest=json.loads((base/'manifest.json').read_bytes())
expected_audit=(base/'reviewed-repair-audit.sha256').read_text().strip()
require(len(expected_audit)==64 and sha((base/'repair-audit.json').read_bytes())==expected_audit,'reviewed proposal audit changed')
require(sha((base/'repair-proposal.json').read_bytes())==proposal_audit['proposalSha256'],'proposal changed')
require(sha((base/'source-document.json').read_bytes())==audit['sourceDocumentSha256'],'original archive changed')
require(manifest=={k:audit[k] for k in ('jobId','sourceJobSha256','sessionId','stageId','sourceSnapshotSha256')}|{'repairPath':'repair-proposal.json'},'manifest changed')
require(audit['jobId']=='omformal_35329ccda267db6155963636'
    and audit['runtimeId']=='omfc__9FoaAfdhcHc5krhoDgSXbI9u6R3hoPXemPj3cQMr9o'
    and audit['stageId']=='stage-McsF1obUqo'
    and audit['sourceJobSha256']=='9229b9a216abfaa5e7b30a87140e758a7b2d67186843f5fef1c06d8b7f0e1ab1','exact English source required')
raw=(native/'data/classroom-jobs'/(audit['jobId']+'.json')).read_bytes(); job=json.loads(raw)
require(raw==(base/'original-native-job.json').read_bytes() and sha(raw)==audit['sourceJobSha256']
    and job['status']=='failed' and job.get('error','').startswith('FORMAL_QUALITY_FINAL_SNAPSHOT_REJECTED:')
    and job['formalInputSha256']==audit['formalInputSha256'],'terminal Native source changed')
wrapper=(root/'openmaic-runtime/scripts/native-runtime.sh').read_text()
f=wrapper[wrapper.index('run_openmaic_production_foreground() {'):]
s=f.index('  exec env -i '+chr(92)+'\n');e=f.index('    "${node_bin}" node_modules/next/dist/bin/next start',s)
require(sha(f[s:e].encode())=='394cda52d9b7f36ffab52e8cdcfb010f41fa00fedc1ac8c22617c940e2df74a9','production environment projection changed')
if True:
    folder=native/'data/formal-saved-stage-recoveries'/audit['jobId']
    require(not (folder/'completion.json').exists(),'already completed: do not dispatch')
    prepared=json.loads((folder/'prepared-snapshot.json').read_bytes())
    require(quality_sha(prepared)==expected,'reviewed snapshot changed')
    preflight=json.loads((folder/'browser-preflight.json').read_bytes())
    identity={k:manifest[k] for k in ('sourceJobSha256','sourceSnapshotSha256','sessionId','stageId')}
    identity['repairSnapshotSha256']=expected
    require(preflight.get('passed') is True and all(preflight.get(k)==v for k,v in identity.items()),'successful exact browser inspection required')
    checks=preflight.get('checks',[]);scenes={s['id'] for s in prepared['scenes']}
    require(len(checks)==len(scenes)*2 and all(c.get('passed') is True for c in checks)
        and {(c['sceneId'],c['viewport']['width'],c['viewport']['height']) for c in checks}
        =={(s,w,h) for s in scenes for w,h in ((1280,720),(1024,768))},'all pages must pass both viewports')
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(preflight['checkedAt'].replace('Z','+00:00'))).total_seconds()
    require(0<=age<=86400,'browser inspection expired')
    from core.config import AppConfig
    from core.database import Database
    from scripts.generate_progressive_preview import preview_identities
    identity=next(i for i in preview_identities('primary_6') if i['buildItemId']==audit['buildItemId'])
    c=Database(AppConfig.from_env().DATABASE_URL).connect()
    try:
        c.execute('START TRANSACTION READ ONLY')
        rows=c.execute('SELECT * FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=?',(audit['buildItemId'],)).fetchall()
        require(len(rows)==1,'exactly one original Runtime required')
        r=dict(rows[0])
        require(r['id']==audit['runtimeId'] and r['upstream_job_id']==audit['jobId']
            and r['request_id']==audit['runtimeRequestId'] and r['course_id']==audit['courseId']
            and r['package_id']==audit['packageId'] and r['status']=='failed' and not r.get('retired_at'),'Runtime changed')
        require(c.execute('SELECT COUNT(*) AS n FROM learning_curriculum_classroom_item_receipts WHERE build_item_id=?',(audit['buildItemId'],)).fetchone()['n']==0,'Host receipt already exists')
        auth_id=job['formalInput']['paidBudget']['authorizationId']
        auth=c.execute('SELECT * FROM learning_budget_authorizations WHERE id=?',(auth_id,)).fetchone()
        require(auth and not auth['revoked_at'] and json.loads(auth['scope_json'])==identity['scope'],'production scope changed')
        for other in c.execute('SELECT id,scope_json FROM learning_budget_authorizations').fetchall():
            if json.loads(other['scope_json'])==identity['scope']:
                require(c.execute("SELECT COUNT(*) AS n FROM learning_budget_reservations WHERE authorization_id=? AND state IN ('reserved','dispatched','unknown')",(other['id'],)).fetchone()['n']==0,'same-scope request unresolved')
    finally:
        c.rollback();c.close()
require(expected_audit=='cf3d84b08a9c0fe1061510b8a39e3f0f6a0ee7efb8f66841993f2c4ff7bceabe','exact reviewed audit required')
audio=native/'data/formal-audio'
asr_path=audio/'jobs/asr'/(sha(asr_id.encode())+'.json')
asr=json.loads(asr_path.read_bytes())
tts=json.loads((audio/'jobs/tts'/(sha(asr['ttsRequestId'].encode())+'.json')).read_bytes())
action=next((a for scene in prepared['scenes'] if scene['id']==asr.get('sceneId') for a in scene.get('actions',[]) if a.get('id')==asr.get('actionId')),None)
require(action and action['type']=='speech' and sha(action['text'].strip().encode())==tts['textSha256'],'exact frozen speech required')
require(asr['requestId']==asr_id and asr['classroomId']==audit['stageId'] and asr['subject']=='english' and asr['classroomContentSha256']=='ab21e3cb9f0c0c9ca51084f261f2c06c49dce8fad640c8064ac1a280f20bc19f','exact audio identity required')
require(asr['state']=='succeeded' and tts['state']=='succeeded' and asr['audioSha256']==tts['audioSha256'],'terminal bound audio required')
asset=audio/'assets'/tts['assetFileName']
require(asset.parent==audio/'assets' and sha(asset.read_bytes())==tts['audioSha256'],'original WAV changed')
if mode in ('diagnose-audio','repair-audio'):
    require(asr.get('similarityBps',10000)<8500 and 'operatorRepair' not in asr,'a proven uncorrected rejection is required')
    suffix='.diagnostic1' if mode=='diagnose-audio' else '.repair1'
    require(not (audio/'jobs/asr'/(sha((asr_id+suffix).encode())+'.json')).exists(),'operation already attempted: diagnose saved outcome')
    if mode=='repair-audio':
        require(not (audio/'jobs/tts'/(sha((tts['requestId']+'.repair1').encode())+'.json')).exists(),'repair TTS already attempted')
elif mode in ('prepare-english-repair-diagnostic','diagnose-english-repair-audio','adopt-english-repair','prepare-english-language-repair','repair-english-language-audio'):
    require(asr.get('similarityBps',10000)<8500 and 'operatorRepair' not in asr,'uncorrected original rejection required')
    repair=json.loads((audio/'jobs/asr'/(sha((asr_id+'.repair1').encode())+'.json')).read_bytes())
    require(repair['state']=='succeeded' and repair.get('similarityBps',10000)<8500,'terminal rejected repair required')
    if mode=='diagnose-english-repair-audio':
        require(not (audio/'jobs/asr'/(sha((asr_id+'.repair1.diagnostic1').encode())+'.json')).exists(),'auto-language diagnosis already attempted')
    if mode=='adopt-english-repair':
        receipt=json.loads((audio/'repairs'/sha(asr_id.encode())/'english-asr-diagnostic1/receipt.json').read_bytes())
        require(quality_sha(receipt)==diagnostic_sha and receipt['asr']['state']=='succeeded'
            and receipt['asr'].get('similarityBps',0)>=8500,'exact successful diagnostic required')
        manifest['englishRepairAsrDiagnostic']={'receiptSha256':diagnostic_sha}
    if mode in ('prepare-english-language-repair','repair-english-language-audio'):
        diagnostic=json.loads((audio/'jobs/asr'/(sha((asr_id+'.repair1.diagnostic1').encode())+'.json')).read_bytes())
        require(diagnostic['state']=='succeeded' and diagnostic.get('similarityBps',10000)<8500,'failed auto-language diagnostic required')
        require(not (audio/'jobs/tts'/(sha((tts['requestId']+'.language1').encode())+'.json')).exists()
            and not (audio/'jobs/asr'/(sha((asr_id+'.language1').encode())+'.json')).exists(),'language repair already attempted')
else:
    require(asr.get('similarityBps',0)>=8500 and 'operatorRepair' in asr,'verified audio repair required')
    require(not (folder/('complete-'+expected+'-audio-'+quality_sha(asr)+'.claim')).exists(),'audio tail already attempted: diagnose saved outcome')
manifest['asrSourceRequestId']=asr_id
manifest_path=base/('audio-'+asr_id+'-'+mode+'.json')
raw=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
if manifest_path.exists(): require(manifest_path.read_bytes()==raw,'audio manifest changed')
else:
    with manifest_path.open('xb') as f: manifest_path.chmod(0o600); f.write(raw)
print(json.dumps({'status':'local_guards_passed','mode':mode,'jobId':audit['jobId'],'snapshot':expected,'asrRequestId':asr_id,'manifestSha256':sha(raw),'providerCalls':0}))
PYCHECK
if [[ "$mode" == adopt-english-repair ]]; then mode=repair-audio; fi
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
