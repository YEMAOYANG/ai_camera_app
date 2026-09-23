/** Audited running-only English first-set review steering. */
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
  nativeJobId: 'omformal_35329ccda267db6155963636',
  runtimeRequestId: 'mira-formal-runtime-catalog_build_item_4b59d735f1373e60196aa25a-attempt-1',
  formalInputSha256: 'ec788e0b8393230e870a2f221cfe1329d1b40263ab814485c9d8b1671f6c414e',
  sessionId: 'miraformal_232f8120d6c3b73196ccc60b06740e695fe52d97db911af5ca282f05fb4f645e',
  ownerId: 'mira-formal-professional:232f8120d6c3b73196ccc60b06740e695fe52d97db911af5ca282f05fb4f645e',
  stageId: 'stage-McsF1obUqo',
  sessionSeedStageId: 'stage-miraform',
});
const BODY = `本次对当前stage-McsF1obUqo六页实际保存内容审读，快照SHA256=6a83c375fa928fbae312b0ce83081c2e851888ead3e5d14f63be53cf79710161。先读回当前文档，只改仍存在问题，保留已经自行修正部分，继续同session，不新建课堂或更改冻结formalInput/runtimeAuthoringScope。
1.p6 text_203zAt3K/action_dqS0im3V将“Lily thanks ___”直接断为“所以用her”，没有交代感谢对象或限定配对，不能只凭动词后位置推出her。请在自编示例里明确代词所指对象和必要信息，或明确仅在she/her一对中辨认形式；先解释句意和主语/动作所指对象，再说明选择理由，不能凭姓名猜性别。
2.p1/p2/p6与p3反馈存在“句首=主格”“She在句首所以用主格”的一般化。请统一以“代词作主语用主格；本课示例作动词宾语用宾格”为依据；可说本例主语位于句首，但不能把任何句首词/仅排在动词后作为充分定义。不要为了纠正口诀扩展到介词、复杂从句、其他时态。
3.六页尚未教call/calls、invite、homework、party及游戏watches/follows等词义。请在练习之前，用单词/短语释义或另编明确且简单的语境先教课堂实际需要的词义；把主宾常见配对和简单现在时的语义讲清，不退回字母启蒙。释词不能补全/演练六道正式题。
4.p3代码“再来一局”onclick resetGame()使currentStateIndex永远回0，nextState虽定义却没被调用，另外四关不可达；选错后currentSlotFilled=true而chooseCard入口直接return，不能按提示点另一卡纠错。请使全部已声明游戏关卡通过真实可见操作可达，答错可重试，下一关/新局/重置语义明确，计分与目标一致，键盘和SET_WIDGET_STATE路径也不能绕开状态规则；保留真实可玩反馈与完整重置。action_az3MUqgp 的widget_setState传sentence/reason，HTML监听只处理start/reset，导致声明的示范操作不生效。请让动作参数、HTML合法有限关卡、widgetConfig和可见结果一致，不能靠仅写收到消息冒充状态变化。另.pronoun-card的text-transform:lowercase会把I显示成i，必须保持代词I大写。所有关卡语境要明确所指，不能仅靠姓名推断性别，不得加入六道正式题或换名复刻。
5.当前仅p3一个game互动，尚无独立3D教学场景。请依照冻结v2互动要求补真正独立的3D教学互动：有三维对象/相机或顶点面投影、学生操作、可观察结果和重置，服务于本课主语/宾语作用与代词形式；不能用静态框或CSS样式冒充3D，也不加方向介词/复杂指代或其他知识。可用另编简单情境展示动作执行者与动作所指对象，所指明确；不能用3D把句子词语物理先后误说成语法规则。新增页置于评估前，保留现有quiz scene IDs和题内容，同步正常interaction/widget声明、旁白、高亮及实际控件。
冻结六题必须逐字保留题号、题面、选项、顺序，不改答题键，尤其不能在非quiz提前报选项位置。具体受保护材料：guided_1“My brother likes ____.”；independent_1“She calls ____ every day.”；independent_2“They invite ____ to the party.”；independent_3“He helps ____ with homework.”；independent_4“I see ____ at the park.”；independent_5“The teacher asks ____ a question.”。主宾配对本身允许正常教学，保护的是这些具体作答材料，不要误封通用知识。
完成以上修改后继续真实浏览器、独立质量审核和TTS/ASR，不降低门槛、不伪造通过。用户已授权继续，不需再询问。`;
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
  demand(typeof BODY === 'string' && BODY.trim().length > 0,
    'Consolidated review text has not been prepared; no database connection or delivery is allowed');
  const [command, suppliedAudit] = process.argv.slice(2);
  demand(['prepare', 'apply'].includes(command) && (command !== 'apply' || suppliedAudit === AUDIT_ID),
    'Usage: node backend/scripts/steer_progressive_preview_english1_review.mjs prepare | apply <exact audit ID>');
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
        applyCommand: `node backend/scripts/steer_progressive_preview_english1_review.mjs apply ${AUDIT_ID}` }));
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
