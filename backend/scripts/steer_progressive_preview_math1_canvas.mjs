/** Audited same-session math first-lesson scope and protected-assessment repair. */
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
  nativeJobId: 'omformal_34af2d1474d1a66e33914c9e',
  runtimeRequestId: 'mira-formal-runtime-catalog_build_item_6b26bea50f1cdd7acaf2dfb2-attempt-1',
  formalInputSha256: '4e9726d7fa5d43ea46a4fc9c791f7c06deddc361a7436778298546e2fd6ac255',
  sessionId: 'miraformal_37689532ec47867cc836c15b1f582ea6fbd5663bd621b3be4097b2e1e9f692d2',
  ownerId: 'mira-formal-professional:37689532ec47867cc836c15b1f582ea6fbd5663bd621b3be4097b2e1e9f692d2',
  stageId: 'stage-93otEr42PB',
  sessionSeedStageId: 'stage-miraform',
});
const BODY = `当前反复出现的patch_stage错误已由工具实现和实际源数据定位，请采用下述精确修复，不要继续整页重生成。
根因：现有slide的type=line元素带rotate:0，但patch_stage的LineElementPatch不允许rotate。工具每执行一个JSON pointer操作就校验整页，因此逐条remove rotate时，其他line仍带rotate，第一步立即失败，后续删除永远不执行。错误中的height/content/defaultFontName/type等大多是union分支噪音，不能给line补文字字段。
请先read_stage detail=source重读当前scene-p2、scene-p9（若其他页也同类错误，同理处理；已重新生成的页必须重读新elements，不能拿旧数组覆盖）。每页仅用【一个】set操作：path=/content/canvas/elements，value为刚读到的完整现有elements数组；在这一个数组内部同时删除全部type=line元素的rotate字段，并同时落实已确认必要的文字top/height位置调整。保留所有元素id、type、数量、顺序与教学内容；不得新造id/重排/删除教学图形。一次操作使整页线条同时符合schema，仍走正常完整校验，不降低门槛。不要逐条remove rotate，不要给line补height/content等文字属性，不改actions/锁定题；也不要重建整页来掩盖该问题。
p4白名单、p5真实3D预设、p6游戏和p9新讨论已经完成的内容保持。修好以上少量页面格式后继续正常review_course_quality、浏览器/交互及音频流程，不新增教学范围，不再次询问用户。`;
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
    'Usage: node backend/scripts/steer_progressive_preview_math1_canvas.mjs prepare | apply <exact audit ID>');
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
        applyCommand: `node backend/scripts/steer_progressive_preview_math1_canvas.mjs apply ${AUDIT_ID}` }));
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
