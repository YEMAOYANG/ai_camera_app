/** One audited HTML-feedback correction of the second Chinese classroom. No new run. */
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
const BODY = `这是当前第二份正式课堂的一次审读反馈，仅处理 scene-p5 两处实际 HTML/脚本反馈中的过度推论，以及现有来源页脚的引用精度。请在当前会话、当前 stage 内处理并沿用正常质量审核流程。
1. scene-p5 的 passages[1].reason 含“用来证明招领箱确实有用”，请改为“作者引用这条可核实的记录，用来支持设置招领箱的看法”；passages[2].reason 含“说明大家需要先慢跑适应”，请改为“作者把这条记录作为材料，用来支持前面的慢跑建议”。请同步这两处实际 HTML/脚本的可见反馈，说明作者如何使用材料，不据此判定建议成立或推断因果。保留当前给定上下文，不添加新材料，不扩展到判断证据是否充分或寻找对应证据。
2. scene-p1、scene-p2、scene-p7 的现有来源页脚只有 renrendoc.com 和通用的课程标准标题，不能准确对应本次真实获取的页面。请在这些现有来源页脚中清楚标明已经获取的实际页面题名“2022语文课程标准解读与学习心得体会:思辨性阅读探讨”及完整 URL：https://www.renrendoc.com/paper/216244912.html 。明确这是课程标准的解读文章，不能把它写成直接获取或阅读了官方课程标准原文；不要编造新来源或重新搜索获取资料。引用只说明课程设计参考，不把自编校园材料说成来自该网页。
scene-p3 已自行修好的逐卡反馈保持原样。六道锁定评估题的题干、选项、答案、解释、身份及顺序全部原样保留，不把题目内容搬到教学反馈中。所有现有 speech 动作、教师和同学台词、TTS/ASR 文本与音频设置保持原样。本次只修改上述 scene-p5 两处 HTML 反馈和既有来源页脚，不改课程范围，不新建 Agent、Runtime 或 stage。不得降低审核标准、伪造审核通过或更改探测器；按正常流程重新审查实际修改后的页面并继续当前任务，无需询问用户。`;
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
    'Usage: node backend/scripts/steer_progressive_preview_slot2.mjs prepare | apply <exact audit ID>');
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
        applyCommand: `node backend/scripts/steer_progressive_preview_slot2.mjs apply ${AUDIT_ID}` }));
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
