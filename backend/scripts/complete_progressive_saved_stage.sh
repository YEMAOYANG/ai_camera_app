#!/usr/bin/env bash
# One explicit completion of the reviewed, saved Chinese classroom. Never retry.
set -euo pipefail
[[ $# == 1 && "$1" =~ ^[a-f0-9]{64}$ ]] || {
  echo 'Usage: complete_progressive_saved_stage.sh REVIEWED_REPAIR_SNAPSHOT_SHA256' >&2
  exit 2
}
expected_repair_sha="$1"
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
python_bin='/private/tmp/mira-progression-test-venv/bin/python'
source "${repo}/openmaic-runtime/scripts/native-runtime.sh"
[[ "${SOURCE_DIR}" == "${repo}/openmaic-runtime/.runtime/OpenMAIC" ]] || {
  echo 'The exact original Native source directory is required.' >&2; exit 2;
}
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
manifest="${repo}/output/progressive-preview/saved-stage/manifest.json"
MIRA_INTERNAL_API_TOKEN="${OPENMAIC_INTERNAL_API_TOKEN}" \
MIRA_BACKEND_INTERNAL_URL="${MIRA_BACKEND_INTERNAL_URL:-http://127.0.0.1:8000}" \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="${repo}/backend" \
  "${python_bin}" - "${repo}" "${expected_repair_sha}" <<'PYCHECK'
import hashlib,json,os,re,sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request,build_opener,HTTPRedirectHandler
from integrations.openmaic_formal_quality import quality_sha

root=Path(sys.argv[1]); expected=sys.argv[2]
base=root/'output/progressive-preview/saved-stage'
manifest_path=base/'manifest.json'; proposal_path=base/'repair-proposal.json'
sha=lambda value:hashlib.sha256(value).hexdigest()
def require(ok,reason):
    if not ok: raise SystemExit('SAVED_STAGE_COMPLETE_STOP: '+reason)
require(re.fullmatch('[a-f0-9]{64}',expected) is not None,'reviewed snapshot SHA is required')
require(expected=='4c22173c009c946c1275bd83312978165ec68a94e32452ba5edaf0b63dea0d32',
    'only the successfully prepared repair snapshot is authorized by this launcher')
require(sha(manifest_path.read_bytes())=='69850aac0c54a0312ccf4a9b135b864fa5e7d74a009e0b058d6c107bfa756517','manifest changed; review a new proposal')
require(sha(proposal_path.read_bytes())=='74fe68dddf5f97c43d8c7f232eb59c85693b570808fa34cad102a1db31278a88','repair proposal changed')
manifest=json.loads(manifest_path.read_bytes())
require(manifest['jobId']=='omformal_6b040dfb4816e69ae333dbc4' and manifest['stageId']=='stage-tYYCDS_mnS'
    and manifest['sessionId']=='miraformal_ab60c22962408c704878b698c03f3df1914826c6619fcd3b794c0ec8614daee6','original classroom scope changed')
native=root/'openmaic-runtime/.runtime/OpenMAIC'; folder=native/'data/formal-saved-stage-recoveries'/manifest['jobId']
source=(native/'data/classroom-jobs'/(manifest['jobId']+'.json')).read_bytes(); job=json.loads(source)
require(sha(source)==manifest['sourceJobSha256'] and job['status']=='failed'
    and job.get('error')=='FORMAL_PROFESSIONAL_RESEARCH_CITATION_MISSING','original failed job changed')
require(not job.get('formalSavedStageRecovery') and not job.get('formalCitationRecovery'),'recovery already recorded')
prepared=json.loads((folder/'prepared-snapshot.json').read_bytes())
require(quality_sha(prepared)==expected,'prepared snapshot differs from the reviewed SHA')
identity={key:manifest[key] for key in ('sourceJobSha256','sourceSnapshotSha256','sessionId','stageId')}
identity['repairSnapshotSha256']=expected
preflight=json.loads((folder/'browser-preflight.json').read_bytes())
require(preflight.get('passed') is True and all(preflight.get(k)==v for k,v in identity.items()),'matching browser preflight pass is required')
checks=preflight.get('checks',[])
scenes={s['id'] for s in prepared['scenes']}
require(len(checks)==len(scenes)*2 and all(c.get('passed') is True for c in checks)
    and {(c['sceneId'],c['viewport']['width'],c['viewport']['height']) for c in checks}
        =={(s,w,h) for s in scenes for w,h in ((1280,720),(1024,768))},'complete two-viewport checks are required')
checked=datetime.fromisoformat(preflight['checkedAt'].replace('Z','+00:00'))
require(0 <= (datetime.now(timezone.utc)-checked).total_seconds() <= 86400,'browser preflight has expired')
require(not (folder/'completion.json').exists() and not list(folder.glob('complete*.claim')),
    'existing completion or claim; preserve it and diagnose, never replay')
intent_path=base/('complete-launch-'+expected+'.json')
require(not intent_path.exists(),'prior launch intent exists; no automatic retry')
wrapper=(root/'openmaic-runtime/scripts/native-runtime.sh').read_text()
function=wrapper[wrapper.index('run_openmaic_production_foreground() {'):]
start=function.index('  exec env -i '+chr(92)+'\n')
end=function.index('    "${node_bin}" node_modules/next/dist/bin/next start',start)
require(sha(function[start:end].encode())=='394cda52d9b7f36ffab52e8cdcfb010f41fa00fedc1ac8c22617c940e2df74a9','production environment mapping changed')
budget=job['formalInput']['paidBudget']; require(budget.get('required') is True,'original paid budget is missing')
base_url=os.environ.get('MIRA_BACKEND_INTERNAL_URL',''); parsed=urlparse(base_url)
require(parsed.scheme=='http' and parsed.hostname in {'127.0.0.1','localhost'} and not parsed.username and not parsed.password,'loopback budget authority required')
token=os.environ.get('MIRA_INTERNAL_API_TOKEN'); require(bool(token),'internal authority credential missing')
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None
request=Request(base_url.rstrip('/')+'/internal/learning/budget/context',
    data=json.dumps({'authorizationId':budget['authorizationId']}).encode(),method='POST',
    headers={'Content-Type':'application/json','X-Mira-Internal-Token':token,'X-Mira-Internal-Source':'openmaic-runtime-gateway'})
try:
    with build_opener(NoRedirect).open(request,timeout=15) as response:
        reply=json.load(response)
except Exception:
    raise SystemExit('SAVED_STAGE_COMPLETE_STOP: trusted budget context unavailable')
context=reply.get('budget') or {}
require(reply.get('ok') is True and context.get('authorizationId')==budget['authorizationId']
    and context.get('aggregateLimitsEnabled') is False and context.get('unsettledReservationCount')==0,
    'authorization inactive, capped or has an unsettled/unknown Provider outcome')
intent={'schemaVersion':'mira.progressive-saved-stage-completion-launch.v1',**identity,
    'manifestSha256':sha(manifest_path.read_bytes()),'repairFileSha256':sha(proposal_path.read_bytes()),
    'productionEnvMappingSha256':'394cda52d9b7f36ffab52e8cdcfb010f41fa00fedc1ac8c22617c940e2df74a9','reviewGrantUsed':False,
    'authorizationId':budget['authorizationId'],'aggregateLimitsEnabled':False,'unsettledReservationCount':0,
    'sourceJobArchive':str(base/'original-native-job.json'),'startedAt':datetime.now(timezone.utc).isoformat(),
    'retryAllowed':False}
require(sha((base/'original-native-job.json').read_bytes())==manifest['sourceJobSha256'],'original local job archive changed')
fd=os.open(intent_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as output:
    json.dump(intent,output,indent=2);output.write('\n');output.flush();os.fsync(output.fileno())
print(json.dumps({'status':'first_completion_authorized','jobId':manifest['jobId'],'repairSnapshotSha256':expected,'intentPath':str(intent_path)}))
PYCHECK
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
      scripts/recover-formal-saved-stage.ts complete "${manifest}"
