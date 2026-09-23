#!/usr/bin/env bash
# Exact EN2 paid-ASR replay, then cached-quality audio continuation. No scene/review regeneration.
set -euo pipefail
mode="${1:-}"
[[ $# == 1 ]] || exit 2
case "$mode" in
  revalidate-audio-comparison|complete-audio-comparison-tail) ;;
  *) echo 'Usage: run_progressive_english2_audio_tail.sh revalidate-audio-comparison|complete-audio-comparison-tail' >&2; exit 2 ;;
esac
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
manifest="${repo}/output/progressive-preview/saved-stage-english-slot2/audio-${mode}.json"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${repo}/backend" \
 "${repo}/backend/.venv/bin/python" - "$repo" "$mode" 'f678e29bd3954cca3db49820fda9a58974677259e5913e7d2a262b98a5f93904' <<'PYCHECK'
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
if True:
    folder=native/'data/formal-saved-stage-recoveries'/ids['job']
    require(not (folder/'completion.json').exists(),'already completed: no further operation')
    require(sha((folder/('complete-'+expected+'.claim')).read_bytes())=='7b06b234c7606fd618074f1f7465d3a533fe70303496cc26e420947ce089a40a','original failed complete claim changed')
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
        require(c.execute("SELECT COUNT(*) AS n FROM learning_budget_reservations WHERE state IN ('reserved','dispatched')").fetchone()['n']==0,'a Provider call is active')
        budget_rows=[dict(x) for x in c.execute('SELECT * FROM learning_budget_reservations WHERE authorization_id=? ORDER BY created_at,id',(auth_id,)).fetchall()]
        original_by_id={x['id']:x for x in saved['reservations']};current_by_id={x['id']:x for x in budget_rows}
        require(all(current_by_id.get(k)==v for k,v in original_by_id.items()),'original 86 financial rows changed')
        new_rows=[x for x in budget_rows if x['id'] not in original_by_id]
        require(len(budget_rows)==96 and len(new_rows)==10 and all(x['state']=='settled' for x in new_rows),'exact initial quality/audio accounting changed')

    finally:c.rollback();c.close()

# The original passed quality and original audio stay frozen. Only the separately
# versioned comparator may reinterpret the one exact paid transcript.
comparator_sha='ca4e93f89f56b430c4e69854a00a77abded04f9818622d229b6e67499df7237c'
require(sha((native/'lib/server/mira-formal-english-asr-orthography.ts').read_bytes())==comparator_sha,'English comparator changed')
quality_path=native/'data/formal-quality-reviews/a59955f9861134c626c71c5e1c3e722b9c9ac3d5b0760b84ebe9018540501a49'/(expected+'.json')
quality_raw=quality_path.read_bytes();quality=json.loads(quality_raw)
require(sha(quality_raw)=='d8e81cc99a8339270023069ecac84407cfbaf020b3fb1743e090d3b51ca17ed3'
    and quality['status']=='passed' and quality['receipt']['receiptSha256']=='b9cd8b4c8577e06f32b99d0a7e61cb5ab9d4508d273de07f05f54796f91569fa'
    and quality_sha({k:v for k,v in quality['receipt'].items() if k!='receiptSha256'})==quality['receipt']['receiptSha256'],'original quality receipt changed')
asr_id='formal_asr_6041228c0db83966b76f926f2cf20ff85d75cb1a1c9e97f1'
audio=native/'data/formal-audio';asr_key=sha(asr_id.encode())
asr=json.loads((audio/'jobs/asr'/(asr_key+'.json')).read_bytes())
tts=json.loads((audio/'jobs/tts'/(sha(asr['ttsRequestId'].encode())+'.json')).read_bytes())
transcript=json.loads((audio/'transcripts'/(asr_key+'.json')).read_bytes())
require(quality_sha(asr)=='fc3923c725aeb480d89235f728f153a75416c97fe5bfb43cce7586c253381e48'
    and quality_sha(tts)=='cd3b0d0558f82a3f6a2b7b7b608b148efcfd3b3bfa3c2153688f339be9fd7e5c'
    and quality_sha(transcript)=='9f7c2a3bc223afc855339e8d9452a2f12d26b05894bf52bc89032fa719fc586b','original paid audio/transcript changed')
require(tts['assetFileName']=='mirawav_7ba1de66c4286d00d752d170.wav'
    and sha((audio/'assets'/tts['assetFileName']).read_bytes())==tts['audioSha256'],'original WAV changed')
require({p.name for p in folder.glob('complete*.claim')}=={'complete-'+expected+'.claim'},
    'another completion or audio continuation already started; inspect its saved outcome')
manifest['asrSourceRequestId']=asr_id
financial={'schemaVersion':'mira.english2.audio-comparison-financial-source.v1',
    'sourceJobSha256':audit['sourceJobSha256'],'snapshotSha256':expected,
    'originalCompleteClaimSha256':'7b06b234c7606fd618074f1f7465d3a533fe70303496cc26e420947ce089a40a',
    'authorizationId':auth_id,'reservations':budget_rows}
financial_path=base/'audio-comparison-financial-source.json'
if financial_path.exists():require(json.loads(financial_path.read_bytes())==financial,'audio continuation financial source changed')
elif mode=='revalidate-audio-comparison':
    with financial_path.open('x') as f:financial_path.chmod(0o600);json.dump(financial,f,ensure_ascii=False,indent=2);f.write('\n')
else:require(False,'the original financial evidence has not been recorded')
if mode=='complete-audio-comparison-tail':
    receipt=json.loads((audio/'comparison-revalidations'/asr_key/(expected+'-'+comparator_sha+'.json')).read_bytes())
    from integrations.openmaic_asr_revalidation import validate_asr_comparison_revalidation
    lifecycle={k:tts[k] for k in ('classroomId','classroomContentSha256','subject')}
    lifecycle['buildItemId']=ids['item'];lifecycle['teacherProfile']={'id':tts['teacherProfileId'],'version':tts['teacherProfileVersion'],'sha256':tts['teacherProfileSha256'],'gender':tts['teacherGender']}
    segment={k:asr[k] for k in ('sceneId','sceneOrder','actionId','narrationSegmentId')}
    segment.update(textSha256=tts['textSha256'],tts=tts,asr={**asr,'similarityBps':receipt['comparison']['similarityBps'],'normalizedTranscriptSha256':receipt['comparison']['normalizedTranscriptSha256']})
    validate_asr_comparison_revalidation(receipt,lifecycle=lifecycle,segment=segment,
        professional_creation={'sessionId':ids['session'],'classroomId':ids['stage'],'buildItemId':ids['item'],'teachingQuality':quality['receipt']})
    manifest['asrComparisonRevalidation']={**receipt['binding'],'receiptSha256':receipt['receiptSha256']}
manifest_path=base/('audio-'+mode+'.json');raw=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
if manifest_path.exists():require(manifest_path.read_bytes()==raw,'audio operation manifest changed')
else:
    with manifest_path.open('xb') as f:manifest_path.chmod(0o600);f.write(raw)
print(json.dumps({'status':'local_guards_passed','mode':mode,'jobId':ids['job'],'snapshot':expected,
    'asrRequestId':asr_id,'manifestSha256':sha(raw),'providerCalls':0,'originalScore':8095}))
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
