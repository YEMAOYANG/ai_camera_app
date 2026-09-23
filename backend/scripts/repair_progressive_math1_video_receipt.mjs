/** Exact local repair of one dropped Native video receipt; never dispatches. */
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync, existsSync, openSync, closeSync, fsyncSync, renameSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { parseEnv } from 'node:util';
import { spawnSync } from 'node:child_process';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const NATIVE = join(ROOT, 'openmaic-runtime/.runtime/OpenMAIC');
const OUT = join(ROOT, 'output/progressive-preview/math1-video-receipt');
const SCOPE = Object.freeze({
  jobId: 'omformal_34af2d1474d1a66e33914c9e',
  runtimeId: 'omfc_Lj-np0i1kYjXNy5-5xUmoQoAl6dDZjwprGuDUtNwJmU',
  requestId: 'mira-formal-runtime-catalog_build_item_6b26bea50f1cdd7acaf2dfb2-attempt-1',
  inputSha256: '4e9726d7fa5d43ea46a4fc9c791f7c06deddc361a7436778298546e2fd6ac255',
  itemId: 'catalog_build_item_6b26bea50f1cdd7acaf2dfb2',
  sessionId: 'miraformal_37689532ec47867cc836c15b1f582ea6fbd5663bd621b3be4097b2e1e9f692d2',
  ownerId: 'mira-formal-professional:37689532ec47867cc836c15b1f582ea6fbd5663bd621b3be4097b2e1e9f692d2',
  stageId: 'stage-93otEr42PB',
  authorizationId: '8c47463ffd66bd7b89c7a8a5fcb6b75ff5de8220c9bf4167c28355e516f6751e',
  qualitySnapshotSha256: 'bc9b3ddd6a2d4f5be67bd01575b3597377201fc0825dcfb47106450facae07ab',
  agentSnapshotSha256: '25fddd465d5eca2c709aa6f161193f0b37688c6e070a7e9c286db637080e31c6',
  audioClassroomSha256: '5807a2b9f635566095b3bc51452a08ad9995ab51baf8076a3e600ec67eb6216a',
  audioReceiptSha256: '8016116bbf2174e4964a21fb6afce51befad633e5c6bbe43dc55c9fa330e4d5e',
});
const JOB = join(NATIVE, 'data/classroom-jobs', SCOPE.jobId + '.json');
const CLASSROOM = join(NATIVE, 'data/classrooms', SCOPE.stageId + '.json');
const ATTEMPT = join(NATIVE, 'data/formal-video-attempts', SCOPE.sessionId + '.json');
const sha = raw => createHash('sha256').update(raw).digest('hex');
function canonical(v) {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (v && typeof v === 'object') return '{' + Object.entries(v).sort(([a], [b]) => a.localeCompare(b))
    .map(([k, x]) => JSON.stringify(k) + ':' + canonical(x)).join(',') + '}';
  return JSON.stringify(v);
}
const digest = v => sha(canonical(v));
function demand(ok, reason) { if (!ok) throw new Error(reason); }
function immutable(path, raw) {
  if (existsSync(path)) { demand(readFileSync(path).equals(Buffer.from(raw)), 'Immutable archive conflict'); return; }
  const fd = openSync(path, 'wx', 0o600);
  try { writeFileSync(fd, raw); fsyncSync(fd); } finally { closeSync(fd); }
}
const jsonBytes = v => JSON.stringify(v, null, 2) + '\n';
const attemptProof = () => existsSync(ATTEMPT) ? { path: ATTEMPT, raw: readFileSync(ATTEMPT, 'utf8') } : { path: ATTEMPT, raw: null };
function jobProof(raw) {
  const job = JSON.parse(raw);
  demand(job.id === SCOPE.jobId && job.status === 'succeeded' && job.step === 'completed'
    && !job.error && !job.dispatchAmbiguous && job.runtimeRequestId === SCOPE.requestId
    && job.formalInputSha256 === SCOPE.inputSha256 && digest(job.formalInput) === SCOPE.inputSha256,
  'Exact succeeded Native job/input required');
  demand('miraformal_' + sha(SCOPE.requestId + '\n' + canonical(job.formalInput)) === SCOPE.sessionId,
    'Derived session changed');
  const result = job.result, professional = result?.professionalCreation, audio = result?.formalAudio;
  demand(result?.classroomId === SCOPE.stageId && result.scenesCount === 9 && result.speechActionCount === 40,
    'Completed classroom identity/count changed');
  demand(professional?.sessionId === SCOPE.sessionId && professional.classroomId === SCOPE.stageId
    && professional.buildItemId === SCOPE.itemId && professional.runtimeRequestId === SCOPE.requestId
    && professional.videoGenerationEnabled === true && professional.videoPolicyId === 'mira-formal-happyhorse-video.v1'
    && professional.teachingQuality?.status === 'passed'
    && professional.teachingQuality.snapshotSha256 === SCOPE.qualitySnapshotSha256,
  'Existing professional/quality receipt changed');
  demand(audio?.receiptSha256 === SCOPE.audioReceiptSha256 && audio.status === 'succeeded'
    && audio.buildItemId === SCOPE.itemId && audio.classroomId === SCOPE.stageId
    && audio.classroomContentSha256 === SCOPE.audioClassroomSha256
    && audio.expectedSegmentCount === 40 && audio.ttsSucceededCount === 40 && audio.asrPassedCount === 40
    && audio.segments?.length === 40, 'Completed 40/40 audio receipt required');
  demand(job.formalInput.paidBudget?.authorizationId === SCOPE.authorizationId, 'Paid scope changed');
  return job;
}
function budgetProof() {
  const code = String.raw`
import json
from core.config import AppConfig
from core.database import Database
from scripts.generate_progressive_preview import preview_identities
item='catalog_build_item_6b26bea50f1cdd7acaf2dfb2'
auth='8c47463ffd66bd7b89c7a8a5fcb6b75ff5de8220c9bf4167c28355e516f6751e'
scope=next(x['scope'] for x in preview_identities('primary_6') if x['buildItemId']==item)
c=Database(AppConfig.from_env().DATABASE_URL).connect()
try:
 c.execute('START TRANSACTION READ ONLY')
 a=dict(c.execute('SELECT * FROM learning_budget_authorizations WHERE id=?',(auth,)).fetchone())
 assert json.loads(a['scope_json'])==scope,'authorization scope changed'
 same=[r['id'] for r in c.execute('SELECT id,scope_json FROM learning_budget_authorizations').fetchall() if json.loads(r['scope_json'])==scope]
 rows=[dict(r) for r in c.execute('SELECT * FROM learning_budget_reservations WHERE authorization_id=? ORDER BY id',(auth,)).fetchall()]
 assert len(rows)==181 and all(r['state']=='settled' for r in rows),'Expected precisely 181 settled calls'
 for aid in same:
  assert c.execute("SELECT COUNT(*) AS n FROM learning_budget_reservations WHERE authorization_id=? AND state IN ('reserved','dispatched','unknown')",(aid,)).fetchone()['n']==0,'Unresolved same-scope call'
 r=dict(c.execute('SELECT id,request_id,candidate_build_item_id,upstream_job_id,status,quality_status,error_code FROM learning_openmaic_runtime_classrooms WHERE id=?',('omfc_Lj-np0i1kYjXNy5-5xUmoQoAl6dDZjwprGuDUtNwJmU',)).fetchone())
 assert r['candidate_build_item_id']==item and r['upstream_job_id']=='omformal_34af2d1474d1a66e33914c9e'
 assert r['request_id']=='mira-formal-runtime-'+item+'-attempt-1'
 assert r['status']=='failed' and r['quality_status']=='quarantined' and r['error_code']=='openmaic_formal_generation_ambiguous'
 print(json.dumps({'authorization':a,'sameScopeAuthorizationIds':sorted(same),'reservations':rows,'runtime':r},default=str,ensure_ascii=False,sort_keys=True))
finally:
 c.rollback();c.close()
`;
  const result = spawnSync('/private/tmp/mira-progression-test-venv/bin/python', ['-c', code], {
    cwd: ROOT, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1', PYTHONPATH: join(ROOT, 'backend') }, encoding: 'utf8', timeout: 30000,
  });
  demand(result.status === 0, 'Readonly exact-budget verification failed: ' + String(result.stderr).slice(-900));
  return JSON.parse(result.stdout);
}
async function nativeProof(client, qualitySnapshot, qualitySha, audioClassroomSha) {
  await client.query('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY');
  try {
    const session = (await client.query(`SELECT id,owner_id,prompt,status,attempt,stage_id,active_stage_id,
      cancel_requested_at,deleted_at,lease_worker_id FROM agent_sessions WHERE id=$1`, [SCOPE.sessionId])).rows[0];
    demand(session?.owner_id === SCOPE.ownerId && session.status === 'succeeded' && session.attempt === 0
      && session.stage_id === 'stage-miraform' && !session.active_stage_id && !session.deleted_at
      && !session.cancel_requested_at && !session.lease_worker_id, 'Succeeded unchanged terminal session required');
    session.promptSha256 = sha(session.prompt); delete session.prompt;
    const stages = (await client.query('SELECT id,owner_id,data FROM document_stages WHERE id=$1', [SCOPE.stageId])).rows;
    demand(stages.length === 1 && stages[0].owner_id === SCOPE.ownerId, 'Stage owner changed');
    const scenes = (await client.query('SELECT data FROM document_scenes WHERE stage_id=$1 ORDER BY scene_order,id', [SCOPE.stageId])).rows.map(r => r.data);
    const agentSnapshot = qualitySnapshot(stages[0].data, scenes);
    demand(scenes.length === 9 && qualitySha(agentSnapshot) === SCOPE.agentSnapshotSha256,
      'Original terminal Agent document changed');
    const classroomRaw = readFileSync(CLASSROOM, 'utf8'), classroom = JSON.parse(classroomRaw);
    demand(classroom.id === SCOPE.stageId && classroom.stage?.id === SCOPE.stageId
      && qualitySha(qualitySnapshot(classroom.stage, classroom.scenes)) === SCOPE.qualitySnapshotSha256
      && audioClassroomSha(classroom.stage, classroom.scenes) === SCOPE.audioClassroomSha256,
    'Exact completed quality/audio classroom snapshot required');
    // Normal completion expanded two citation domains to their fetched source URL.
    // Prove this is the entire quality-projected delta; do not edit either source.
    const projected = structuredClone(agentSnapshot);
    for (const [scene, element] of [[1, 34], [8, 18]]) {
      const item = projected.scenes[scene].content.canvas.elements[element];
      demand(typeof item.content === 'string' && item.content.includes('（jyj.wuzhou.gov.cn）'), 'Original citation changed');
      item.content = item.content.replace('（jyj.wuzhou.gov.cn）', '（http://jyj.wuzhou.gov.cn/jydt/dyyd/t13204874.shtml）');
    }
    demand(qualitySha(projected) === SCOPE.qualitySnapshotSha256, 'Unexplained Agent/final document difference');
    const events = (await client.query(`SELECT seq,type,ts,attempt,encode(sha256(convert_to(data::text,'UTF8')),'hex') AS data_sha256
      FROM agent_session_events WHERE session_id=$1 ORDER BY seq`, [SCOPE.sessionId])).rows;
    const traces = (await client.query("SELECT seq,data FROM agent_session_events WHERE session_id=$1 AND type='mira_formal_video_generated' ORDER BY seq", [SCOPE.sessionId])).rows;
    return { session, agentStage: stages[0].data, agentScenes: scenes, events, traces, attempt: attemptProof(),
      classroomRaw, classroomFileSha256: sha(classroomRaw), stage: classroom.stage, scenes: classroom.scenes };
  } finally { await client.query('ROLLBACK'); }
}
async function main() {
  const [command, auditId] = process.argv.slice(2);
  demand(['prepare', 'apply'].includes(command) && (command !== 'apply' || /^[a-f0-9]{64}$/.test(auditId || '')),
    'Usage: node backend/scripts/repair_progressive_math1_video_receipt.mjs prepare | apply AUDIT_SHA256');
  mkdirSync(OUT, { recursive: true });
  const planPath = join(OUT, 'prepared.json'), intentPath = join(OUT, 'apply-intent.json'), outcomePath = join(OUT, 'applied.json');
  const currentRaw = readFileSync(JOB), current = jobProof(currentRaw);
  if (existsSync(outcomePath)) {
    const outcome = JSON.parse(readFileSync(outcomePath)), bytes = readFileSync(planPath), plan = JSON.parse(bytes);
    demand(outcome.auditSha256 === sha(bytes) && (command !== 'apply' || auditId === sha(bytes))
      && outcome.jobSha256 === sha(currentRaw) && digest(current.result.video) === digest(plan.video), 'Applied record conflict');
    console.log(JSON.stringify({ status: 'already_applied', ...outcome })); return;
  }
  demand(!current.result.video, 'Video already exists without this completed audit; stop');
  demand(!existsSync(intentPath), 'Previous apply intent exists; diagnose without retry');
  process.chdir(NATIVE);
  const require = createRequire(join(NATIVE, 'package.json'));
  require('tsx/cjs'); require(join(ROOT, 'openmaic-runtime/scripts/native-operator-esm-compat.cjs'));
  const { qualitySnapshot, qualitySha } = require(join(NATIVE, 'lib/server/mira-formal-quality-contract.ts'));
  const { miraFormalAudioClassroomContentSha256: audioClassroomSha } = require(join(NATIVE, 'lib/server/mira-formal-audio-lifecycle.ts'));
  const { buildMiraFormalVideoReceipt } = require(join(NATIVE, 'lib/server/mira-formal-video.ts'));
  const env = parseEnv(readFileSync(process.env.MIRA_OPENMAIC_PROVIDER_ENV_FILE || process.env.MIRA_BACKEND_ENV_FILE || join(ROOT, 'backend/.env'), 'utf8'));
  const { Client } = require('pg');
  const client = new Client({ connectionString: process.env.MIRA_OPENMAIC_AGENT_DATABASE_URL || env.MIRA_OPENMAIC_AGENT_DATABASE_URL });
  await client.connect();
  try {
    const budget = budgetProof(), native = await nativeProof(client, qualitySnapshot, qualitySha, audioClassroomSha);
    if (command === 'prepare') {
      if (existsSync(planPath)) {
        const bytes = readFileSync(planPath), old = JSON.parse(bytes);
        demand(old.originalJobSha256 === sha(currentRaw) && old.budgetSha256 === digest(budget)
          && old.nativeSha256 === digest(native), 'Prepared evidence changed; stop');
        console.log(JSON.stringify({ status: 'already_prepared', auditSha256: sha(bytes), path: planPath })); return;
      }
      // This official builder reads real video references, traces and attempt files.
      // It never creates an attempt or calls a Provider; no zero receipt is synthesized.
      const video = await buildMiraFormalVideoReceipt({ runtimeRequestId: SCOPE.requestId, buildItemId: SCOPE.itemId,
        classroomId: SCOPE.stageId, sessionId: SCOPE.sessionId, scenes: native.scenes, traces: native.traces.map(r => r.data) });
      demand(digest(attemptProof()) === digest(native.attempt) && sha(readFileSync(JOB)) === sha(currentRaw), 'Source changed during prepare');
      immutable(join(OUT, 'original-native-job.json'), currentRaw);
      immutable(join(OUT, 'native-evidence.json'), jsonBytes(native));
      immutable(join(OUT, 'budget-evidence.json'), jsonBytes(budget));
      const plan = { schemaVersion: 'mira.exact-math1-video-receipt-repair.v1', scope: SCOPE,
        originalJobSha256: sha(currentRaw), nativeSha256: digest(native), budgetSha256: digest(budget), video,
        permittedChange: 'add result.video only; retain every original field and status', providerCalls: 0,
        preparedAt: new Date().toISOString() };
      const bytes = jsonBytes(plan); immutable(planPath, bytes);
      console.log(JSON.stringify({ status: 'prepared_only', auditSha256: sha(bytes), path: planPath,
        originalJobSha256: plan.originalJobSha256, videoCount: video.videoCount, videoReceiptSha256: video.receiptSha256,
        applyCommand: `node backend/scripts/repair_progressive_math1_video_receipt.mjs apply ${sha(bytes)}` })); return;
    }
    const planBytes = readFileSync(planPath), plan = JSON.parse(planBytes);
    demand(sha(planBytes) === auditId && digest(plan.scope) === digest(SCOPE), 'Exact reviewed plan required');
    demand(sha(readFileSync(join(OUT, 'original-native-job.json'))) === plan.originalJobSha256
      && sha(currentRaw) === plan.originalJobSha256 && digest(native) === plan.nativeSha256
      && digest(budget) === plan.budgetSha256, 'Prepared source/session/events/budget changed');
    const { receiptSha256, ...unsignedVideo } = plan.video;
    demand(digest(unsignedVideo) === receiptSha256, 'Video receipt hash changed');
    // A durable exclusive intent is never removed or replayed after interruption.
    demand(!existsSync(intentPath), 'Existing apply intent');
    const fd = openSync(intentPath, 'wx', 0o600);
    try { writeFileSync(fd, jsonBytes({ auditSha256: auditId, sourceJobSha256: plan.originalJobSha256, at: new Date().toISOString() })); fsyncSync(fd); }
    finally { closeSync(fd); }
    demand(digest(await nativeProof(client, qualitySnapshot, qualitySha, audioClassroomSha)) === plan.nativeSha256
      && digest(budgetProof()) === plan.budgetSha256, 'Evidence changed after apply claim; no retry');
    const updated = JSON.parse(currentRaw); updated.result.video = plan.video;
    const check = structuredClone(updated); delete check.result.video;
    demand(canonical(check) === canonical(current), 'Repair would change an original field');
    const updatedRaw = jsonBytes(updated), temp = JOB + '.video-receipt-repair-' + auditId + '.tmp';
    immutable(temp, updatedRaw);
    demand(sha(readFileSync(JOB)) === plan.originalJobSha256, 'Source job CAS failed; no retry');
    renameSync(temp, JOB);
    const dirFd = openSync(dirname(JOB), 'r'); try { fsyncSync(dirFd); } finally { closeSync(dirFd); }
    const outcome = { status: 'applied', auditSha256: auditId, jobSha256: sha(updatedRaw),
      originalJobSha256: plan.originalJobSha256, videoReceiptSha256: receiptSha256, at: new Date().toISOString() };
    immutable(outcomePath, jsonBytes(outcome)); console.log(JSON.stringify(outcome));
  } finally { await client.end(); }
}
main().catch(error => { console.error(JSON.stringify({ status: 'stopped', reason: String(error.message), providerCalls: 0 })); process.exitCode = 1; });
