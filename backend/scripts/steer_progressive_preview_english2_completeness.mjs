/** Prepare/apply one completeness steer for the exact active English second set.
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
const EXPECTED = Object.freeze({
  courseId: 'progressive_5ff2c7f7f0cddfc8f8bcf012',
  runtimeId: 'omfc_8EsR81VIt_yHr1YpuYYAA5Jbyt3HkBfHiNuQgt4SlP4',
  nativeJobId: 'omformal_90ed56f8cb07a09d6c51296a',
  activeStageId: 'stage-FC2nTYOIET',
});
const BODY = `这是 EN6A01.01《常见主宾形式》第二组当前正式课堂的一次完整性补充，请继续当前 session 和 stage-FC2nTYOIET，不另建 session、stage 或任务，不修改 formalInput、teachingBrief、runtimeAuthoringScope、课程提纲、难度、题库、答案或任何验收门槛。新增教学页需要的 interactionPlan 应按真实控件同步登记，不删除既有有效教学目标或降低门槛。
本次针对首次已完成的 review_course_quality（seq3831/3832，snapshot acfc2677992c82aabcbf61d899555c07261ca42601eea7e9417f0bd1c54b13a9）返回 needs_revision 后的修订。此前已保存的 p1 至 p6 快照 fc597b372e195dc856c8ed120090c8132c951336ea3f5bf229c1f426b53d28b6 还缺独立真实 3D 教学页和练习前的必要词义教学。先 read_stage 核对最新页面；如部分内容已正常补齐，只补剩余缺项，不重复建页。必须保留当前六道冻结正式题及其 guided→independent 相对顺序。
0.先修首次浏览器检查的实际问题：p3 操作成功且出现 They greet the girl.，但反馈选择器 #result 只有结果，解释在兄弟节点 #reason。让 #result 成为包住结果子节点与 #reason 的共同反馈容器，JS 仅更新新结果子节点；同步实际DOM和脚本，不删解释或降低验收要求。另外 resetToInitial 目前清空结果，但计划声明 reset 恢复已完成 state-a；重置按钮应恢复 A 的完整结果与解释，首次进入页面仍可未作答。如果最新页面已正确修复，请保留正确结果。
1.补一页独立的、真正使用 3D 场景的教学互动。它应有实际三维人物/物体及空间关系，可由学生旋转、缩放并 reset 恢复初始视角/状态；不要用普通二维图、仅 CSS 透视卡片或改 metadata 冒充 3D，也不要把它塞进原游戏替代独立 3D 页。使用游客与女孩相互 greet/join 等语境明确的新材料讲清谁作主语、谁作宾语，保持本课常见主宾形式及简单现在时；先教这些新词的必要词义。不得用任何冻结 quiz 题干、补全句、核心作答材料或答案作 3D/示范/旁白/反馈材料。
2.在正式 guided 和 independent quiz 前补齐本课实际使用的词义教学，逐项核对 blue、bag、have、sister、eat、apple、friend、share、desk、cousin、grandma、know、brother、visit、after school、work、together、teacher、praise；新增教学示例如果实际使用 greet/join，也先解释必要词义。可按人物、物品、动作和时间短语合理合并讲解，只解释本课实际用词，不新增语法目标。词义用清楚、独立的新语境说明；不要把冻结题干补全成词汇例句或提前说出题目答案。
3.继续遵守此前完整自然释词音频要求：每段 speech 必须是完整、自足、自然的讲解，不使用“ask，问。”这类一个英文词加一两个中文字义的孤立短双语音频，不用中文谐音替代英文，不靠无意义填充拉长。可以自然合并相邻词义，但保留每页正式旁白数量约束以及 spotlight、speech、可见元素之间有效的引用。英语例句语义、代词角色和发音须正确，不引入复杂指代、其他时态或超出本课目标的题型。
4.词义页和 3D 教学页必须排在 guided/independent quiz 之前，不能追加到课堂末尾再让学生先练后学。保持讲解→示范/探索→引导练习→独立练习→小结的实际学习顺序，保持六道正式题各自的逐字段公开内容完全不变；只有教学页可以按需要前置。核对实际 scene order、对应场景 id 与动作引用，不能只修改文字声明顺序。
5.完成正常编写后 read_stage 核对全部必要词义已在实际用到前解释、独立 3D 页可操作、游戏仍可操作、六道 frozen public questions 逐字段未变且无提前泄漏。然后正常通过全套既有正式质量审核、真实浏览器审核和正式 TTS/ASR；不放宽或伪造质量结果，不改 interaction plan 门槛、冻结输入或费用/身份回执，不另起课堂，不自行绕过正式音频完成流程。`;
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
  demand(host.courseId === EXPECTED.courseId && host.runtimeId === EXPECTED.runtimeId
    && host.nativeJobId === EXPECTED.nativeJobId, 'The exact completeness-review course or Runtime changed');
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
  demand(!row.active_stage_id || row.active_stage_id === EXPECTED.activeStageId, 'The exact completeness-review document changed');
  {
    const stage = await db.query('SELECT id, owner_id FROM document_stages WHERE id=$1', [EXPECTED.activeStageId]);
    demand(stage.rows.length === 1 && stage.rows[0].owner_id === SCOPE.ownerId, 'Current document owner changed');
  }
  // A seed-stage session may leave active_stage_id null. Prove the actual
  // classroom through this session's successful structured creation event,
  // not through the nullable field or matching owner alone.
  const creation = await db.query(`SELECT seq, type, data FROM agent_session_events
    WHERE session_id=$1 AND seq IN (1570,1571,1572,1573) ORDER BY seq`, [SCOPE.sessionId]);
  const [start, changed, linked, end] = creation.rows;
  const creationCall = 'call_00_9bjGEiDYBjm0eMO0nXB78813';
  demand(creation.rows.length === 4 && Number(start.seq) === 1570
    && start.type === 'tool_execution_start' && start.data.toolName === 'create_stage'
    && start.data.toolCallId === creationCall
    && changed.type === 'library_changed' && changed.data.change === 'stage_created'
    && changed.data.stageId === EXPECTED.activeStageId
    && linked.type === 'stage_link' && linked.data.stageId === EXPECTED.activeStageId
    && end.type === 'tool_execution_end' && end.data.toolName === 'create_stage'
    && end.data.toolCallId === creationCall && end.data.isError === false
    && end.data.result?.details?.stageId === EXPECTED.activeStageId
    && end.data.result?.details?.url === '/classroom/' + EXPECTED.activeStageId,
  'The exact session did not successfully create this classroom');
  const latestLink = await db.query(`SELECT data FROM agent_session_events
    WHERE session_id=$1 AND type='stage_link' ORDER BY seq DESC LIMIT 1`, [SCOPE.sessionId]);
  demand(latestLink.rows[0]?.data.stageId === EXPECTED.activeStageId,
    'This session subsequently linked a different classroom');
  const outline = await db.query('SELECT data FROM document_outlines WHERE stage_id=$1', [EXPECTED.activeStageId]);
  demand(outline.rows.length === 1 && outline.rows[0].data.producer === 'server-job'
    && outline.rows[0].data.producerRef === SCOPE.sessionId,
  'Current classroom producer is not this exact generation session');
  // The original failure stays fixed. Later completed rejections are allowed,
  // but any unmatched quality call or successful latest review blocks delivery.
  const reviewed = await db.query(`SELECT seq, type, data FROM agent_session_events WHERE session_id=$1
    AND type IN ('tool_execution_start','tool_execution_end')
    AND data->>'toolName'='review_course_quality' ORDER BY seq`, [SCOPE.sessionId]);
  const reviewStart = reviewed.rows.find(event => Number(event.seq) === 3831);
  const reviewEnd = reviewed.rows.find(event => Number(event.seq) === 3832);
  const reviewCall = 'call_00_0GvF9zsXOa93miHd68td9278';
  demand(reviewStart && reviewEnd
    && reviewStart.type === 'tool_execution_start' && reviewEnd.type === 'tool_execution_end'
    && reviewStart.data.toolCallId === reviewCall && reviewEnd.data.toolCallId === reviewCall
    && reviewStart.data.args?.stageId === EXPECTED.activeStageId
    && reviewEnd.data.isError === true && reviewEnd.data.result?.terminate === false
    && reviewEnd.data.result?.details?.status === 'needs_revision'
    && reviewEnd.data.result?.details?.stageId === EXPECTED.activeStageId,
  'The exact completed nonterminal quality rejection changed');
  const qualityStarts = reviewed.rows.filter(event => event.type === 'tool_execution_start');
  const qualityEnds = reviewed.rows.filter(event => event.type === 'tool_execution_end');
  demand(qualityStarts.length === qualityEnds.length && qualityStarts.every(start =>
    start.data.args?.stageId === EXPECTED.activeStageId && qualityEnds.some(end =>
      end.data.toolCallId === start.data.toolCallId && Number(end.seq) > Number(start.seq)))
    && qualityEnds.at(-1)?.data.result?.details?.status === 'needs_revision'
    && qualityEnds.at(-1)?.data.result?.terminate === false,
  'Another quality review is active or the latest review no longer requests revision');
  const pending = await db.query(`SELECT EXISTS (SELECT 1 FROM agent_session_events q WHERE q.session_id=$1
    AND q.type='user_question' AND NOT EXISTS (SELECT 1 FROM agent_session_events a WHERE a.session_id=q.session_id
    AND a.seq>q.seq AND a.type='user_message' AND length(btrim(COALESCE(a.data->>'text','')))>0)) AS pending`, [SCOPE.sessionId]);
  return { id: row.id, ownerId: row.owner_id, promptSha256: sha(row.prompt), stageId: row.stage_id,
    activeStageId: row.active_stage_id, status: row.status, attempt: row.attempt,
    createdClassroomId: EXPECTED.activeStageId, creationStartSeq: Number(start.seq), creationEndSeq: Number(end.seq),
    producerSessionId: outline.rows[0].data.producerRef, completedRevisionReviewSeq: Number(reviewEnd.seq),
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
    'Usage: node backend/scripts/steer_progressive_preview_english2_completeness.mjs prepare | apply <exact audit ID>');
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
        applyCommand: `node backend/scripts/steer_progressive_preview_english2_completeness.mjs apply ${AUDIT_ID}` }));
      return;
    }
    const audit = JSON.parse(readFileSync(auditPath, 'utf8'));
    demand(audit.auditId === AUDIT_ID && audit.text === TEXT && audit.textSha256 === sha(TEXT)
      && canonical(audit.scope) === canonical(SCOPE), 'Prepared audit changed');
    stillRunning(session, audit);
    const intentPath = join(OUT, 'EN6A01.01-slot2-completeness.dispatch-intent.json');
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
