/** Audited same-session math second-set scope and protected-assessment repair. */
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
  nativeJobId: 'omformal_6cddfc21f47d63291444dfab',
  runtimeRequestId: 'mira-formal-runtime-catalog_build_item_c38581679912c102b1d91061-attempt-2',
  formalInputSha256: '6e5b4d06023f3ca30d997d6efb088f19d31e446ae05a5fb6985a322b40551dcb',
  sessionId: 'miraformal_0669fb604cef3bcc29a0605e5da607f49a8c4fb3e51b8506ab33242e5a7cb3ff',
  ownerId: 'mira-formal-professional:0669fb604cef3bcc29a0605e5da607f49a8c4fb3e51b8506ab33242e5a7cb3ff',
  stageId: 'stage-NjgpUvNeOs',
  sessionSeedStageId: 'stage-miraform',
});
const BODY = `这是对当前六年级数学 M6A01.01 第二份修订后正式课堂（attempt-2，stage-NjgpUvNeOs）真实已保存内容的单次汇总审读。审读基于2026-09-17T03:44:18.750Z场景快照，SHA256为b6eb4afd76e0e9866a902a968c27119dd7793251c9db5ebff8e7314d582c9c8d。请先读回当前文档，保留已自行修正的部分，只修本session非评估互动和对应教学说明，不创建新任务，不修改冻结formalInput或六道quiz。
1. scene-p3 分子numerator和分母denominator仍可自由输入1..1000，copies可输入1..9，readInputsToState与SET_WIDGET_STATE也允许任意组合，六道锁定题全部能被提前演练。请改成有限完整教学预设，例如(分子,分母,份数)仅(2,5,1)、(2,5,2)、(2,5,3)、(4,9,2)、(4,9,3)。以整组切换，不能拆为可任意交叉组合的独立字段。所有输入、初始化、重置、消息设参、setState及widgetConfig共用同一有限集合；拒绝非法或不完整组合，不能先显示其结果再纠正。保留真正可操作、有结果、有反馈、可重置的分数条教学，同步旁白与高亮目标。
2. scene-p3实际显示“小数”“百分数”、#decimal、#percent及总量1.2，updateDisplay仍做小数/百分数转换。这超出本课“相同分数连加→分数乘整数意义”。删除可见小数和百分数转换及教学输出，总量使用分数；不要把CSS宽度百分比或绘图内部小数误删。图示应真实展示相同每份量被取几份及总量，保持绘图和文字一致。
3. scene-p4现脚本先调用initCups(DEFAULT_CUPS)，它调用updateReadouts，但cupCountEl等const随后才初始化，存在确定的ReferenceError。请修初始化次序，并实际检查加减杯、合并、旋转、重置可用。drawMeasuringCylinder又以topY+heightPx*i/5标注i/5，使0在顶端、1升在底端，刻度倒置；6/5升用满筒叠色不能准确表达。请保持当前每杯2/5升、1..4杯的有限教学范围，使用能容纳全部水的明确容量与从下往上递增的分数刻度，水面位置、杯内减少量、筒内增加量、文本总量一致；不引入体积公式、小数或百分数教学。所有程序设参只接受合法整数杯数，避免小数/NaN引发错误。
4. scene-p5仅可选每份量1/7、2/7、3/7，份数1..4；handleRestart却随机取1..7/7，其中5/7、7/7用现有按钮不可达。请只从真实合法教学组合的结果中取新目标，保证每局至少一个合法解，保留现有游戏反馈和重置。用每份量×份数解释合计，不扩大成分数除法或复杂逆推，不新增任意输入。本页所有可达教学组合也必须避开下述六道锁定题。
5. scene-p2目前action_5qHlR1pD“每份是1/4，这是每份量。”、action_pqIVEszz“取3份，份数就是3。”、action_3baGDWqa“三个1/4连加，得3/4。”是孤立短片段。请仅把这三条改成完整自足的自然中文说明，例如明确“四分之一”代表每份量、同样的量取三份即份数三、三个四分之一相加得四分之三，并保持与画面对应。其他已完整旁白无需泛化重写。后续按正常TTS与ASR校验，不降低阈值、不复用不匹配旧音频。
本次修订后六道冻结题的核心计算明确为：guided_1=3/10乘4；independent_1=5/9乘2；independent_2=3/8乘5；independent_3=4/7乘2；independent_4=5/12乘3；independent_5=4/13乘3。这是当前attempt-2的保护清单，不能照抄旧attempt-1题目。非评估HTML、可达互动状态、讲解、反馈和讨论不得提前演练这些计算或换物品复述原题。已导入六道quiz的题号、顺序、题干、选项、答案、解释保持逐字不变；不要修改formalInput、authoringScope、difficultyPolicy或原审核结论。
完成上述实际修正后继续当前课堂正常的浏览器交互与质量检查、音频流程，不绕过门禁，不伪造通过，不添加检测专用分支。无需另行询问用户。`;
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
  const [command, suppliedAudit] = process.argv.slice(2);
  demand(['prepare', 'apply'].includes(command) && (command !== 'apply' || suppliedAudit === AUDIT_ID),
    'Usage: node backend/scripts/steer_progressive_preview_math2_revision_scope.mjs prepare | apply <exact audit ID>');
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
        applyCommand: `node backend/scripts/steer_progressive_preview_math2_revision_scope.mjs apply ${AUDIT_ID}` }));
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
