/** One audited interaction repair of the existing second Chinese classroom. No new run. */
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync, existsSync, openSync, fsyncSync, closeSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { parseEnv } from 'node:util';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const NATIVE = join(ROOT, 'openmaic-runtime/.runtime/OpenMAIC');
const OUT = join(ROOT, 'output/progressive-preview/steering');
const SCOPE = Object.freeze({
  nativeJobId: 'omformal_d961effd180ea347e6b1b0bf',
  runtimeRequestId: 'mira-formal-runtime-catalog_build_item_8c465a74b18ef347a19f52b7-attempt-1',
  formalInputSha256: '8b47d84758d45e60c369b11bf4ff5d092edea1ff49e46c2adadc3f609b213f5b',
  sessionId: 'miraformal_b70ae221b3382f39cd1ff5bde07bef6dcba3f59bd205cb6c4e8278706ea7a0f3',
  ownerId: 'mira-formal-professional:b70ae221b3382f39cd1ff5bde07bef6dcba3f59bd205cb6c4e8278706ea7a0f3',
  stageId: 'stage-ZlKdLz74QS',
  sessionSeedStageId: 'stage-miraform',
  sessionAttempt: 1,
  promptSha256: '67d0a9b423c123fb273bf04543e94ba65cd13df59c3923fba5dd00c2a209f56f',
  buildItemId: 'catalog_build_item_8c465a74b18ef347a19f52b7',
  courseId: 'progressive_b651e7b1bd7621f188e7b80f',
  authorizationId: '278b0a430b952da40501b054c3eb91c9f2c92f092570cc16af9b1d6271194f5e',
  budgetScope: {
    purpose: 'production', gradeCode: 'primary_6', subject: 'chinese',
    courseId: 'catalog-item:catalog_build_item_8c465a74b18ef347a19f52b7',
    courseVersion: '6871f5fd296bbe0293055ee9d9af80e740b9c66a1d23e5266d80d0c2d4496e67',
    productionJobId: 'catalog_build_item_8c465a74b18ef347a19f52b7',
    userId: null, sessionId: null,
    approvalReference: 'grade-build:c3adfddc5fa5884ff594667f3cb56e131d6ce19a15e41d2d7fe7ce27961e98dd',
  },
});
const BODY = `这是当前第二份课堂的第二条明确审读反馈。只修 scene-p3/scene-p5 已定位的实际交互错误及对应声明，不重写整页；先读取当前精确源代码，若某项已自行修好则保留，不重复替换。
1. scene-p3 的 judge(chosenType) 中现有 var label=correct?'事实':'观点'; 把“是否答对”当成句子类别。正确点击第2/4句的“观点”时，实际标签和反馈仍显示“事实”，与正确语义及 exploration 的 state-b/state-d 都不一致。应改为按当前句子自身类型映射，例如 var label=cur.type==='fact'?'事实':'观点';。correct 只决定判断对错，chosenType 只表示用户所选；检查正确和错误两条反馈分支都准确。已修好的 cur.reason 逐卡解释保持不动。
2. scene-p3 当前 exploration.reset 指向 state-a，但 state-a 是首句已经判对；实际 resetGame() 则清空全部标签并显示“先点一句话选中它，再点‘这是事实’或‘这是观点’”的开始提示。这两者不是同一个图形/反馈状态，必须统一。保留孩子正常的“重新开始=全部未答”行为，不把重来改成替孩子答对首题。可新增一个真实全未答的 baseline 状态放在 states 开头，operations 只点 #reset，resultText/explanationText 精确对应实际开始提示，reset.stateId 指向这个 baseline；现有四句判断状态保留，总共5态符合当前合同。baseline 和最终reset的选中卡片、全部标签、按钮文字、图形和反馈均应完全一致。所有状态仍必须通过真实控件操作到达，不仅改声明；重复点击应可重现同样的真实反馈，不能禁用正确按钮或凭已答状态直接忽略操作。
3. scene-p5 没有本页 objective probe，当前 auto-click 只识别到原生 #reset/#next，第一个是 #reset；页面刚初始化时按重来当然不会改变状态，故真实审核的 changed 检查超时。核心句子 #sen-1/#sen-2 虽绑定 click，却只是普通 div，未作为原生可操作控件呈现。请把这两个真正的学习操作改为 type=button 的原生按钮，保留原ID、文字、点击处理、可读样式及足够触控尺寸；让正文的句子操作在 DOM 的自然操作顺序位于 reset/next 导航之前，沿用布局样式，避免整页重排。这样正常探测和键盘操作能触发真实的句子选择及 #resultText/箭头反馈，而不是初始状态下的无变化重置。保留真实reset行为，不靠虚假字符、隐藏标志、专门探测分支或修改审核器制造“变化”；不要复制或挪走 p3 已有目标合同以跳过其多状态审核。
第一条反馈已修好的 p5 招领箱/慢跑用语、真实引用页脚，以及其他教学内容全部保持。六道锁定评估题的全部内容、解释、身份、顺序不动；所有 speech 动作、教师和同学台词、TTS/ASR 文本及音频配置全部不动。只在当前 session、Runtime 和 stage 内按这些具体JS/局部HTML/声明绑定修正，不新建任务，不改变课程范围，不降低任何审核门槛。修改后正常执行 review_course_quality，按实际浏览器与独立审核结果继续；无需询问用户。`;
function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(',')}}`;
  return JSON.stringify(value);
}
const sha = value => createHash('sha256').update(value).digest('hex');
const AUDIT_ID = sha(canonical({ scope: SCOPE, body: BODY }));
const MARKER = `[mira-formal-operator-revision:${AUDIT_ID}]`;
const TEXT = `${MARKER}\n${BODY}`;
const auditPath = join(OUT, `${AUDIT_ID}.json`);
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
  demand(spec.buildItemId === SCOPE.buildItemId && spec.course?.id === SCOPE.courseId,
    'Frozen course/build item changed');
  const expectedBudget = { schemaVersion: 'mira.learning.paid-budget-binding.v1',
    required: true, authorizationId: SCOPE.authorizationId };
  const binding = JSON.parse(readFileSync(join(NATIVE, 'data/formal-paid-budget-bindings', SCOPE.sessionId + '.json'), 'utf8'));
  demand(canonical(job.formalInput.paidBudget) === canonical(expectedBudget)
    && canonical(binding) === canonical(expectedBudget), 'Existing paid authorization binding changed');
  const policy = JSON.parse(readFileSync(process.env.LEARNING_BUDGET_POLICY_PATH
    || join(ROOT, 'backend/content/learning_classroom_policy.json'), 'utf8'));
  const window = policy.productionAuthorizationWindow;
  demand(policy.enabled === true && window && window.startsAt <= Date.now() && Date.now() < window.expiresAt
    && Array.isArray(window.scopes) && window.scopes.length === 6
    && window.scopes.filter(scope => canonical(scope) === canonical(SCOPE.budgetScope)).length === 1,
    'Exact previously authorized production scope is not active');
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
  demand(sha(row.prompt) === SCOPE.promptSha256 && row.attempt === SCOPE.sessionAttempt,
    'Original session prompt or attempt changed');
  demand(row.stage_id === SCOPE.sessionSeedStageId && (!row.active_stage_id || row.active_stage_id === SCOPE.stageId),
    'Existing session stage identity changed');
  const stage = await db.query('SELECT id, owner_id FROM document_stages WHERE id=$1', [SCOPE.stageId]);
  demand(stage.rows.length === 1 && stage.rows[0].owner_id === SCOPE.ownerId, 'Existing classroom document owner changed');
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
  const [command, suppliedAudit] = process.argv.slice(2);
  demand(['prepare', 'apply'].includes(command) && (command !== 'apply' || suppliedAudit === AUDIT_ID),
    'Usage: node backend/scripts/steer_progressive_preview_slot2_interaction.mjs prepare | apply <exact audit ID>');
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
        applyCommand: `node backend/scripts/steer_progressive_preview_slot2_interaction.mjs apply ${AUDIT_ID}` }));
      return;
    }
    const audit = JSON.parse(readFileSync(auditPath, 'utf8'));
    demand(audit.auditId === AUDIT_ID && audit.text === TEXT && audit.textSha256 === sha(TEXT)
      && canonical(audit.scope) === canonical(SCOPE), 'Prepared audit changed');
    stillRunning(session, audit);
    const intentPath = join(OUT, `${AUDIT_ID}.dispatch-intent.json`);
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
main().catch(error => {
  console.error(JSON.stringify({ status: 'stopped', code: error?.code || null,
    reason: error?.code ? 'Operation could not complete; no automatic retry' : String(error?.message || 'Unknown failure') }));
  process.exitCode = 1;
});
