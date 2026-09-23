/** Prepare/apply one early narration steer for the registered English second set.
 * Prepared as source only: no command runs on import. Uses the existing audited
 * PgAgentSessionStore hook and permanent intent pattern from English first-set steering. */
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync, mkdirSync, existsSync, openSync, fsyncSync, closeSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { parseEnv } from 'node:util';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const NATIVE = join(ROOT, 'openmaic-runtime/.runtime/OpenMAIC');
const OUT = join(ROOT, 'output/progressive-preview/steering');
const ITEM = 'catalog_build_item_d5a6b286d326400b49241b5d';
const BODY = `这是 EN6A01.01《常见主宾形式》第二组正式课堂的一次早期旁白要求，请在当前 session 中纳入正常页面编写和完成前自查，不新建任务或课堂，不更改被冻结的 formalInput、teachingBrief、runtimeAuthoringScope、课程提纲、难度、题库、题目顺序及答案。
1.本课所有实际需要的新词、常见主格与宾格形式仍应先教后练。释词的 speech 请使用完整、自足的自然说明，不把“一个英文词＋一两个中文字义”拆成独立音频；例如不要单独写“ask，问。”或“help，帮助。”。若本课实际需要 ask，可用“这里的 ask 表示询问。使用这个词时，要说清楚谁在询问，以及询问谁。”这类带语境的完整说明；示例只示意旁白形式，不要求新增该词或照抄。只使用已允许、已教的词汇和语法，保持简单现在时，不添加新教学目标。
2.保持英文单词和常见代词的正确拼写、发音及语义，不用中文谐音代替英文，不跳过必要词汇教学，不靠堆叠无意义文字拉长音频。需要朗读英语例句时，使用本课允许且语境明确的完整例句。可将相邻短释义合并为自然讲解，但保留必要的 spotlight→speech 对应和每页正式旁白数量约束。
3.六道冻结正式题只能在原登记 quiz 阶段逐字使用。示范、旁白、3D、游戏、讨论和反馈不得补全或演练这些题的具体句子、核心材料或答案；正常教学主宾配对知识不受此限制。第二组按本课目标继续循序渐进，不新增篇章改写、复杂指代或其他时态。
4.正式完成前 read_stage 检查本课堂所有 speech：清理仍存在的短双语词义碎片，核对画面和动作引用、语义、词汇先教后练及冻结题保护；已完整清楚的旁白不必泛化重写。之后照常完成真实浏览器、独立质量审核、正式 TTS 和 ASR。保持原验收阈值、身份与费用回执要求，不伪造通过，不更换教师或音频策略，不自行调用语音生成工具。`;
let SCOPE, AUDIT_ID, MARKER, TEXT, auditPath;

// This child only SELECTs the exact registered item in an explicit read-only
// transaction. It never constructs an app, repository, worker or schema store.
const READ_HOST = String.raw`
import json, os, sys
from pathlib import Path
from dotenv import dotenv_values
sys.path.insert(0, str(Path.cwd() / 'backend'))
from core.database import Database
from core.config import AppConfig
from content.learning_budget_policy import digest
from scripts.generate_progressive_preview import preview_identities, assert_preview_policy
item_id = 'catalog_build_item_d5a6b286d326400b49241b5d'
def require(value, message):
    if not value: raise RuntimeError(message)
identities = preview_identities('primary_6')
identity = next((row for row in identities if row['buildItemId'] == item_id), None)
require(identity and identity['slot']['subject'] == 'english' and identity['slot']['lessonId'] == 'EN6A01.01' and identity['slot']['variantOrdinal'] == 2, 'registered English slot changed')
env = dotenv_values(os.environ.get('MIRA_BACKEND_ENV_FILE') or 'backend/.env')
assert_preview_policy(os.environ.get('LEARNING_BUDGET_POLICY_PATH') or 'backend/content/learning_classroom_policy.json', identities)
conn = Database(AppConfig.from_env().DATABASE_URL).connect()
try:
    conn.execute('START TRANSACTION READ ONLY')
    item = conn.execute('SELECT * FROM learning_catalog_build_items WHERE id=?', (item_id,)).fetchone()
    require(item and item['grade_code']=='primary_6' and item['subject']=='english' and item['skill_id']=='EN6A01.01' and item['variant_ordinal']==2 and item['content_phase']=='course_ready' and item['content_gate_status']=='passed', 'exact accepted English slot missing')
    rows = conn.execute('SELECT * FROM learning_openmaic_runtime_classrooms WHERE candidate_build_item_id=? AND retired_at IS NULL', (item_id,)).fetchall()
    require(len(rows)==1, 'expected exactly one current Runtime for the approved slot')
    row = rows[0]
    require(row['status']=='generating' and row.get('upstream_job_id') and row['course_id']==item['course_id'] and row['course_version']==item['course_version'] and row['candidate_release_id']==item['release_id'] and row['candidate_target_fingerprint']==identity['targetFingerprint'], 'Runtime is not the exact live accepted course')
    manifest = json.loads(row['feature_manifest_json'])
    generation = manifest['generationContract']
    course = generation['course']
    brief = generation['teachingBrief']
    require(generation['buildItemId']==item_id and course['id']==row['course_id'] and course['version']==row['course_version'] and brief['course']['gradeCode']=='primary_6' and brief['course']['subject']=='english' and brief['progressiveLesson']['lessonId']=='EN6A01.01', 'formal generation course identity mismatch')
    authorization = digest({'schema':'mira.catalog-paid-budget.v1','scope':identity['scope']})
    require(manifest.get('paidBudget')=={'schemaVersion':'mira.learning.paid-budget-binding.v1','required':True,'authorizationId':authorization}, 'paid authorization differs from the exact approved slot')
    print(json.dumps({'buildItemId':item_id,'runtimeId':row['id'],'runtimeRequestId':row['request_id'],'nativeJobId':row['upstream_job_id'],'courseId':row['course_id'],'courseVersion':row['course_version'],'generationContractSha256':digest(generation),'authorizationId':authorization}))
finally:
    conn.rollback()
    conn.close()
`;
function hostSnapshot() {
  const python = process.env.MIRA_STEERING_PYTHON || join(ROOT, 'backend/.venv/bin/python');
  try { return JSON.parse(execFileSync(python, ['-c', READ_HOST], {
    cwd: ROOT, env: process.env, encoding: 'utf8', timeout: 20000, stdio: ['ignore', 'pipe', 'pipe'],
  })); } catch { throw new Error('Exact English second-set Host read-only identity/policy check failed; no delivery'); }
}
function discoverScope() {
  const host = hostSnapshot();
  demand(/^omformal_[a-f0-9]{24}$/.test(host.nativeJobId), 'Invalid stored Native job id');
  const job = JSON.parse(readFileSync(join(NATIVE, 'data/classroom-jobs', host.nativeJobId + '.json'), 'utf8'));
  const digest = sha(host.runtimeRequestId + '\n' + canonical(job.formalInput));
  return {...host, formalInputSha256: sha(canonical(job.formalInput)),
    sessionId: 'miraformal_' + digest, ownerId: 'mira-formal-professional:' + digest,
    sessionSeedStageId: 'stage-miraform'};
}
function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(',')}}`;
  return JSON.stringify(value);
}
const sha = value => createHash('sha256').update(value).digest('hex');
function demand(ok, message) { if (!ok) throw new Error(message); }
function immutable(path, value) {
  const fd = openSync(path, 'wx', 0o600);
  try { writeFileSync(fd, JSON.stringify(value, null, 2) + '\n'); fsyncSync(fd); }
  finally { closeSync(fd); }
}
function nativeSnapshot(requireRunning) {
  const raw = readFileSync(join(NATIVE, 'data/classroom-jobs', SCOPE.nativeJobId + '.json'));
  const job = JSON.parse(raw);
  const input = canonical(job.formalInput);
  const sessionDigest = sha(`${SCOPE.runtimeRequestId}\n${input}`);
  demand(job.id === SCOPE.nativeJobId && job.runtimeRequestId === SCOPE.runtimeRequestId, 'Native job identity changed');
  demand(job.formalInput?.runtimeRequestId === SCOPE.runtimeRequestId && sha(input) === SCOPE.formalInputSha256
    && job.formalInputSha256 === SCOPE.formalInputSha256, 'Immutable formal input changed');
  demand(`miraformal_${sessionDigest}` === SCOPE.sessionId && `mira-formal-professional:${sessionDigest}` === SCOPE.ownerId,
    'Derived formal session/owner mismatch');
  demand(`omformal_${sha(SCOPE.runtimeRequestId).slice(0, 24)}` === SCOPE.nativeJobId, 'Derived job mismatch');
  const spec = JSON.parse(job.formalInput.requirement);
  demand(spec.buildItemId === ITEM && sha(canonical(spec)) === SCOPE.generationContractSha256,
    'Native input differs from the exact Host generation contract');
  const expectedBudget = {schemaVersion: 'mira.learning.paid-budget-binding.v1', required: true, authorizationId: SCOPE.authorizationId};
  const budget = JSON.parse(readFileSync(join(NATIVE, 'data/formal-paid-budget-bindings', SCOPE.sessionId + '.json'), 'utf8'));
  demand(canonical(job.formalInput.paidBudget) === canonical(expectedBudget) && canonical(budget) === canonical(expectedBudget), 'Existing paid authorization binding changed');
  if (requireRunning) demand(job.status === 'running' && !job.error && !job.result, 'Native job is no longer running; do not steer');
  return { fileSha256: sha(raw), status: job.status, step: job.step, updatedAt: job.updatedAt, formalInputSha256: sha(input) };
}
function databaseUrl() {
  const envPath = process.env.MIRA_OPENMAIC_PROVIDER_ENV_FILE || process.env.MIRA_BACKEND_ENV_FILE || join(ROOT, 'backend/.env');
  const env = parseEnv(readFileSync(envPath, 'utf8'));
  const url = process.env.MIRA_OPENMAIC_AGENT_DATABASE_URL || env.MIRA_OPENMAIC_AGENT_DATABASE_URL;
  demand(url && /^postgres(?:ql)?:/.test(url), 'Native PostgreSQL configuration unavailable');
  return url;
}
async function readSession(db) {
  const { rows } = await db.query(`SELECT id, owner_id, prompt, stage_id, active_stage_id, status, attempt,
    delivered_user_message_seq, cancel_requested_at, deleted_at FROM agent_sessions WHERE id=$1`, [SCOPE.sessionId]);
  demand(rows.length === 1, 'Exact existing session is missing');
  const row = rows[0];
  demand(row.owner_id === SCOPE.ownerId && !row.deleted_at, 'Existing session owner changed');
  demand(row.stage_id === SCOPE.sessionSeedStageId, 'Existing session seed stage changed');
  if (row.active_stage_id) {
    const stage = await db.query('SELECT id, owner_id FROM document_stages WHERE id=$1', [row.active_stage_id]);
    demand(stage.rows.length === 1 && stage.rows[0].owner_id === SCOPE.ownerId, 'Current document owner changed');
  }
  const reviewed = await db.query(`SELECT EXISTS (SELECT 1 FROM agent_session_events WHERE session_id=$1
    AND type IN ('tool_execution_start','tool_execution_end') AND data->>'toolName'='review_course_quality') AS started`, [SCOPE.sessionId]);
  demand(reviewed.rows[0].started === false, 'Quality review has started; this early narration steer is no longer allowed');
  const pending = await db.query(`SELECT EXISTS (SELECT 1 FROM agent_session_events q WHERE q.session_id=$1
    AND q.type='user_question' AND NOT EXISTS (SELECT 1 FROM agent_session_events a WHERE a.session_id=q.session_id
    AND a.seq>q.seq AND a.type='user_message' AND length(btrim(COALESCE(a.data->>'text','')))>0)) AS pending`, [SCOPE.sessionId]);
  return { id: row.id, ownerId: row.owner_id, promptSha256: sha(row.prompt), stageId: row.stage_id,
    activeStageId: row.active_stage_id, status: row.status, attempt: row.attempt,
    deliveredUserMessageSeq: row.delivered_user_message_seq, cancelRequestedAt: row.cancel_requested_at,
    awaitingUser: pending.rows[0].pending };
}
function stillRunning(session, audit) {
  demand(session.status === 'running' && !session.awaitingUser && !session.cancelRequestedAt,
    'Session is terminal, awaiting input, cancelling or not running; do not post');
  if (audit) demand(session.promptSha256 === audit.session.promptSha256 && session.attempt === audit.session.attempt,
    'Original prompt or run attempt changed');
}
async function existingMessage(db) {
  const { rows } = await db.query(`SELECT seq, ts, data FROM agent_session_events
    WHERE session_id=$1 AND type='user_message' AND position($2 in COALESCE(data->>'text',''))>0 ORDER BY seq`, [SCOPE.sessionId, MARKER]);
  demand(rows.length <= 1, 'Duplicate audit marker already exists; stop');
  if (!rows.length) return null;
  demand(rows[0].data.text === TEXT, 'Audit marker exists with different text');
  return { seq: rows[0].seq, ts: rows[0].ts, delivery: rows[0].data.delivery, textSha256: sha(rows[0].data.text) };
}
async function main() {
  demand(typeof BODY === 'string' && BODY.trim().length > 0,
    'Consolidated review text has not been prepared; no database connection or delivery is allowed');
  const [command, suppliedAudit] = process.argv.slice(2);
  demand(['prepare', 'apply'].includes(command),
    'Usage: node backend/scripts/steer_progressive_preview_english2_narration.mjs prepare | apply <exact audit ID>');
  demand(process.argv.slice(2).length === (command === 'apply' ? 2 : 1), 'Unexpected arguments');
  SCOPE = Object.freeze(discoverScope());
  AUDIT_ID = sha(canonical({scope: SCOPE, body: BODY}));
  MARKER = '[mira-formal-operator-revision:' + AUDIT_ID + ']';
  TEXT = MARKER + '\n' + BODY;
  auditPath = join(OUT, AUDIT_ID + '.json');
  demand(command !== 'apply' || suppliedAudit === AUDIT_ID, 'Exact prepared audit id required');
  const require = createRequire(join(NATIVE, 'package.json'));
  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: databaseUrl(), max: 1, connectionTimeoutMillis: 10000 });
  try {
    const native = nativeSnapshot(false);
    const client = await pool.connect();
    let session, prior;
    try {
      await client.query('BEGIN READ ONLY');
      session = await readSession(client);
      prior = await existingMessage(client);
      await client.query('ROLLBACK');
    } catch (error) { await client.query('ROLLBACK'); throw error; }
    finally { client.release(); }
    if (prior) {
      console.log(JSON.stringify({ status: 'already_posted', auditId: AUDIT_ID, message: prior, session, native }));
      return;
    }
    nativeSnapshot(true);
    stillRunning(session);
    mkdirSync(OUT, { recursive: true });
    if (command === 'prepare') {
      if (!existsSync(auditPath)) immutable(auditPath, { schema: 'mira.formal-steering-audit.v1', auditId: AUDIT_ID,
        scope: SCOPE, text: TEXT, textSha256: sha(TEXT), session, native, preparedAt: new Date().toISOString() });
      const saved = JSON.parse(readFileSync(auditPath, 'utf8'));
      demand(saved.auditId === AUDIT_ID && saved.text === TEXT && canonical(saved.scope) === canonical(SCOPE), 'Audit conflict');
      stillRunning(session, saved);
      console.log(JSON.stringify({ status: 'prepared_only', auditId: AUDIT_ID, auditPath, textSha256: sha(TEXT), session, native,
        applyCommand: `node backend/scripts/steer_progressive_preview_english2_narration.mjs apply ${AUDIT_ID}` }));
      return;
    }
    const audit = JSON.parse(readFileSync(auditPath, 'utf8'));
    demand(audit.auditId === AUDIT_ID && audit.text === TEXT && audit.textSha256 === sha(TEXT)
      && canonical(audit.scope) === canonical(SCOPE), 'Prepared audit changed');
    stillRunning(session, audit);
    const intentPath = join(OUT, 'EN6A01.01-slot2-narration.dispatch-intent.json');
    if (existsSync(intentPath)) {
      console.log(JSON.stringify({ status: 'previous_dispatch_intent_without_receipt', auditId: AUDIT_ID,
        instruction: 'Do not repost. Inspect the exact event and prior local outcome.', intentPath }));
      process.exitCode = 2;
      return;
    }
    // Exclusive, durable, permanent intent: concurrent/restarted operators never call twice.
    immutable(intentPath, { auditId: AUDIT_ID, textSha256: sha(TEXT), session, native: nativeSnapshot(true),
      attemptedAt: new Date().toISOString(), method: 'PgAgentSessionStore.postUserMessage' });
    const outcomePath = join(OUT, `${AUDIT_ID}.outcome.json`);
    try {
      const { PgAgentSessionStore } = await import(pathToFileURL(join(NATIVE, 'node_modules/@openmaic/storage/dist/agent-session/pg.js')).href);
      const store = new PgAgentSessionStore(pool, {
        withTransaction: async (body) => {
          const tx = await pool.connect();
          try { await tx.query('BEGIN'); const result = await body(tx); await tx.query('COMMIT'); return result; }
          catch (error) { await tx.query('ROLLBACK'); throw error; }
          finally { tx.release(); }
        },
        onUserMessagePosted: async (tx, input) => {
          // Official veto hook runs with the parent row locked, before any requeue.
          demand(input.delivery === 'steer', 'Non-steer delivery vetoed; no requeue and no further post');
          demand(canonical(hostSnapshot()) === canonical(Object.fromEntries(Object.entries(SCOPE).filter(([key]) => !['formalInputSha256','sessionId','ownerId','sessionSeedStageId'].includes(key)))), 'Host Runtime identity changed before delivery');
          nativeSnapshot(true);
          stillRunning(await readSession(tx), audit);
          demand(input.text === TEXT && input.session.id === SCOPE.sessionId, 'Posted message identity mismatch');
        },
      });
      // The only mutation entry point. No schema initialization, raw writes or retry loop.
      const result = await store.postUserMessage(SCOPE.sessionId, { text: TEXT }, { expectedOwnerId: SCOPE.ownerId });
      const outcome = { status: result.delivery === 'steer' ? 'posted' : 'non_steer_stop', auditId: AUDIT_ID,
        textSha256: sha(TEXT), result, completedAt: new Date().toISOString() };
      immutable(outcomePath, outcome);
      console.log(JSON.stringify(outcome));
      if (result.delivery !== 'steer') process.exitCode = 2;
    } catch (error) {
      immutable(outcomePath, { status: 'failed_or_unknown_do_not_repost', auditId: AUDIT_ID,
        errorCode: error?.code || null, reason: error?.code ? 'Database operation did not confirm delivery' : String(error?.message || 'Unconfirmed operation'),
        completedAt: new Date().toISOString() });
      throw error;
    }
  } finally { await pool.end(); }
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main().catch(error => {
  console.error(JSON.stringify({ status: 'stopped', code: error?.code || null,
    reason: error?.code ? 'Operation could not complete; no automatic retry' : String(error?.message || 'Unknown failure') }));
  process.exitCode = 1;
});
