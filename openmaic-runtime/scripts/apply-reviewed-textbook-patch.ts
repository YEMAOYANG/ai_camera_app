/** Local reviewed HTML and matching narration repairs. Run from Native cwd with Node24 + tsx/cjs +
 * native-operator-esm-compat.cjs and the managed persistence/registry env.
 * Usage: SCRIPT JOB_DIRECTORY REPAIR_JSON [--execute]. No model or HTTP PUT. */
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { buildDslCourseTools } from '../.runtime/OpenMAIC/lib/server/agent-runtime/dsl-tools';
import { getAgentSessionStore } from '../.runtime/OpenMAIC/lib/server/agent-runtime/store';
import { getOwnerScopedDocumentStore } from '../.runtime/OpenMAIC/lib/server/agent-runtime/owner-scoped-documents';
import { probeStageAccess } from '../.runtime/OpenMAIC/lib/server/agent-runtime/curriculum-tools';
import { getServerPersistenceProvider } from '../.runtime/OpenMAIC/lib/persistence/server-provider';
import { CLASSROOMS_DIR } from '../.runtime/OpenMAIC/lib/server/classroom-storage';
import { assertTextbookScene, createTextbookAuthoringGuard, textbookCanonical, textbookDigest, textbookContractFromPrompt, textbookContractFromFrozenFile } from '../.runtime/OpenMAIC/lib/server/mira-textbook-scene-contract';
import { enqueueSucceededStageArchives } from '../.runtime/OpenMAIC/lib/server/course-archive-events';

const sha = (value: string | Buffer) => createHash('sha256').update(value).digest('hex');
function need(ok: unknown, code: string): asserts ok { if (!ok) throw new Error(code); }
const decode = (value: any) => typeof value === 'string' ? JSON.parse(value) : value;
async function bytes(file: string) {
  const stat = await fs.lstat(file); need(stat.isFile() && !stat.isSymbolicLink() && stat.size <= 8 * 1024 * 1024, 'REPAIR_FILE_INVALID');
  return fs.readFile(file);
}
const defaults = { sessions: getAgentSessionStore, ownerStore: getOwnerScopedDocumentStore, access: probeStageAccess,
  pool: async () => (await getServerPersistenceProvider(process.env.DATABASE_URL ?? '')).pool, classrooms: CLASSROOMS_DIR };

export async function applyReviewedTextbookPatch(jobPath: string, repairPath: string, execute = false, deps = defaults, retry?: { attemptId: string; retryOf: string }) {
  const job = path.resolve(jobPath), repairBytes = await bytes(path.resolve(repairPath)), repair = JSON.parse(repairBytes.toString());
  need(/^[a-f0-9]{64}$/.test(repair.expectedSceneSha256) && /^\/scenes\/(?:[1-9]\d*|scene[-_][A-Za-z0-9_-]+)$/.test(repair.target)
    && Array.isArray(repair.ops) && repair.ops.length > 0 && repair.ops.length <= 128
    && repair.ops.every((op: any) =>
      (op.op === 'str_replace' && op.path === '/content/html' && typeof op.oldText === 'string' && op.oldText && typeof op.newText === 'string' && !op.replaceAll)
      || (op.op === 'set' && op.path === '/actions' && Array.isArray(op.value) && op.value.length <= 120))
    && repair.ops.filter((op: any) => op.path === '/actions').length <= 1, 'REPAIR_INPUT_INVALID');
  const originals = Object.fromEntries(await Promise.all(['frozen.json', 'draft.json', 'dispatch.json'].map(async name => [name, await bytes(path.join(job, name))])));
  const frozen = JSON.parse(originals['frozen.json'].toString()), marker = JSON.parse(originals['dispatch.json'].toString()), draft = JSON.parse(originals['draft.json'].toString());
  need(sha(originals['draft.json']) === frozen.draftSha256, 'FROZEN_DRAFT_CHANGED');
  const state = JSON.parse((await bytes(path.join(job, 'state.json'))).toString());
  const cookies = (await bytes(path.join(job, 'owner.cookies'))).toString().split(/\r?\n/).map(line => line.replace(/^#HttpOnly_/, '')).filter(line => !line.startsWith('#')).map(line => line.split('\t')).filter(parts => parts[5] === 'anonymous_id');
  need(cookies.length === 1 && /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(cookies[0][6]), 'ORIGINAL_OWNER_REQUIRED');
  const ownerId = 'anon:' + cookies[0][6], sessions = await deps.sessions(), session = await sessions.getSession(state.sessionId);
  need(session && session.ownerId === ownerId && session.skillId === draft.skillIds?.[0] && marker.ownerFingerprint === sha(cookies[0][6]) && marker.requestSha256 === sha(session.prompt), 'SESSION_IDENTITY_CHANGED');
  const contract = textbookContractFromPrompt(session.prompt);
  need(contract && textbookDigest(contract) === textbookDigest(textbookContractFromFrozenFile(frozen)), 'FROZEN_CONTRACT_CHANGED');
  const pool = await deps.pool(), base = await deps.ownerStore(ownerId);
  const rows = await pool.query('SELECT data FROM agent_session_events WHERE session_id=$1 AND type=$2 ORDER BY seq LIMIT 65', [session.id, 'library_changed']);
  need(rows.rows.length <= 64, 'STAGE_DISCOVERY_LIMIT');
  const ids = new Set<string>([session.stageId, ...rows.rows.map((row: any) => decode(row.data)).filter((data: any) => data.change === 'stage_created').map((data: any) => data.stageId)]);
  const documents = [];
  for (const id of ids) { need(typeof id === 'string' && /^[A-Za-z0-9_-]{1,160}$/.test(id), 'STAGE_ID_INVALID'); const doc = await base.loadDocument(id);
    if (doc?.scenes.length && (doc.outline as any)?.producer === 'server-job' && (doc.outline as any)?.producerRef === session.id && (await deps.access(ownerId, id)).kind === 'owned') documents.push(doc); }
  need(documents.length === 1, 'SAVED_STAGE_AMBIGUOUS');
  const doc = documents[0], token = repair.target.split('/')[2], before = doc.scenes.find((scene: any) => /^\d+$/.test(token) ? scene.order === Number(token) : scene.id === token);
  need(before && textbookDigest(before) === repair.expectedSceneSha256, 'SOURCE_SCENE_CHANGED');
  const narrationOp = repair.ops.find((op: any) => op.path === '/actions');
  if (repair.normalization !== undefined) {
    // Adoption requires lesson-wide speech IDs. This explicit normalization
    // changes only IDs, before audio exists; ordinary repairs still cannot rename.
    need(repair.normalization === 'scene-prefixed-speech-ids-v1' && repair.ops.length === 1 && narrationOp,
      'SPEECH_ID_NORMALIZATION_INVALID');
    const expected = (before.actions ?? []).map((action: any) => {
      if (action.type !== 'speech') return action;
      need(!action.audioUrl && !action.audioId && !action.audio, 'SPEECH_ID_NORMALIZATION_HAS_AUDIO');
      return { ...action, id: action.id.startsWith(before.id + '-') ? action.id : before.id + '-' + action.id };
    });
    need(textbookDigest(narrationOp.value) === textbookDigest(expected), 'SPEECH_ID_NORMALIZATION_INVALID');
    const otherIds = new Set(doc.scenes.filter((scene: any) => scene.id !== before.id)
      .flatMap((scene: any) => (scene.actions ?? []).filter((action: any) => action.type === 'speech').map((action: any) => action.id)));
    const ids = expected.filter((action: any) => action.type === 'speech').map((action: any) => action.id);
    need(new Set(ids).size === ids.length && ids.every((id: string) => !otherIds.has(id)), 'SPEECH_ID_NORMALIZATION_COLLISION');
  } else if (narrationOp) {
    const originalActions = before.actions ?? [], nextActions = narrationOp.value;
    // A reviewed narration repair cannot remove/reorder existing actions,
    // change their identities/metadata, or introduce executable action types.
    need(nextActions.length >= originalActions.length && nextActions.every((action: any, index: number) => {
      if (!action || typeof action !== 'object') return false;
      const original = originalActions[index];
      if (!original) return action.type === 'speech' && typeof action.id === 'string' && action.id.length > 0
        && typeof action.text === 'string' && action.text.trim().length > 0
        && Object.keys(action).every(key => ['id', 'type', 'text'].includes(key));
      if (original.type !== 'speech') return textbookDigest(action) === textbookDigest(original);
      const { text: oldText, ...oldIdentity } = original;
      const { text: newText, ...newIdentity } = action;
      return typeof newText === 'string' && newText.trim().length > 0
        && textbookDigest(oldIdentity) === textbookDigest(newIdentity);
    }), 'NARRATION_REPAIR_SCOPE_INVALID');
  }
  const candidate = JSON.parse((await bytes(path.join(deps.classrooms, doc.stage.id, 'textbook-authoring-candidate.json'))).toString());
  const { sha256: candidateSha, ...body } = candidate;
  need(candidateSha === textbookDigest(body) && candidate.sessionId === session.id && candidate.stageId === doc.stage.id && candidate.status === 'author_candidate'
    && candidate.verification === 'static_contract_only_not_play_or_semantic_review' && textbookDigest(candidate.frozenContract) === textbookDigest(contract)
    && candidate.scenes.length === doc.scenes.length && doc.scenes.every((scene: any) => candidate.scenes.some((entry: any) => entry.sceneId === scene.id && entry.sha256 === textbookDigest(scene) && sha(entry.canonicalJson) === entry.sha256)), 'CANDIDATE_CHANGED');
  let after: any;
  const tool = (store: any) => buildDslCourseTools({ store, stageAccess: id => deps.access(ownerId, id), sessionId: session.id, onCheckpoint: () => {} }).find(item => item.name === 'patch_stage')!;
  const parameters = { stageId: doc.stage.id, target: repair.target, intent: 'Apply explicitly reviewed exact HTML and narration repair', ops: repair.ops };
  const preflight = await tool({ loadDocument: async () => structuredClone(doc), putScene: async (_id: string, scene: any) => { assertTextbookScene(scene, contract, candidate.assetBindings); after = scene; } }).execute('reviewed-preflight', parameters as never);
  if (preflight.isError || !after) throw Object.assign(new Error('PATCH_PREFLIGHT_REJECTED'), { details: preflight, reason: preflight.content.map((item: any) => item.text ?? '').join('').slice(0, 500) });
  let identity: Record<string, any> = { sessionId: session.id, stageId: doc.stage.id, sceneId: before.id, beforeSceneSha256: textbookDigest(before), afterSceneSha256: textbookDigest(after), opsSha256: sha(repairBytes), frozenFileSha256: sha(originals['frozen.json']) };
  if (!execute) return { status: 'validated_not_applied', ...identity };
  need(['succeeded', 'failed', 'cancelled'].includes(session.status) && !session.lease, 'SESSION_NOT_TERMINAL');
  const baseFolder = path.join(job, 'reviewed-patches', identity.opsSha256), lock = path.join(job, 'reviewed-patches', 'operation.lock');
  if (retry) {
    need(/^[A-Za-z0-9_-]{1,60}$/.test(retry.attemptId) && path.resolve(retry.retryOf) === path.join(baseFolder, 'intent.json'), 'RETRY_AUDIT_INVALID');
    const prior = await bytes(path.resolve(retry.retryOf));
    need(textbookDigest(JSON.parse(prior.toString())) === textbookDigest(identity), 'RETRY_IDENTITY_CHANGED');
    need(!(await fs.stat(path.join(baseFolder, 'receipt.json')).catch(() => null)), 'RETRY_ALREADY_SETTLED');
    identity = { ...identity, attemptId: retry.attemptId, retryOf: path.resolve(retry.retryOf), retryOfSha256: sha(prior), confirmedUnapplied: true, confirmedCandidateSha256: candidateSha };
  }
  const folder = retry ? path.join(baseFolder, 'attempts', retry.attemptId) : baseFolder;
  await fs.mkdir(folder, { recursive: true, mode: 0o700 });
  const handle = await fs.open(lock, 'wx', 0o600);
  try {
    await fs.writeFile(path.join(folder, 'intent.json'), JSON.stringify(identity), { flag: 'wx', mode: 0o600 });
    await fs.writeFile(path.join(folder, 'before.json'), textbookCanonical(before), { flag: 'wx', mode: 0o600 });
    await fs.writeFile(path.join(folder, 'ops.json'), repairBytes, { flag: 'wx', mode: 0o600 });
    const fencedTransactions = new WeakSet<object>();
    let archiveStatus = 'not_succeeded';
    const writable = await deps.ownerStore(ownerId, async tx => {
      const row = (await tx.query('SELECT status,lease_worker_id FROM agent_sessions WHERE id=$1 AND owner_id=$2 AND deleted_at IS NULL FOR UPDATE', [session.id, ownerId])).rows[0];
      need(row && row.status === session.status && ['succeeded', 'failed', 'cancelled'].includes(row.status) && !row.lease_worker_id, 'SESSION_BECAME_ACTIVE');
      const current = (await tx.query('SELECT data FROM document_scenes WHERE stage_id=$1 AND id=$2 FOR UPDATE', [doc.stage.id, before.id])).rows[0];
      // OwnerBoundDocumentStore fences both before mutation and before COMMIT.
      const expected = fencedTransactions.has(tx) ? identity.afterSceneSha256 : identity.beforeSceneSha256;
      need(current && textbookDigest(decode(current.data)) === expected, 'SOURCE_SCENE_CHANGED');
      if (fencedTransactions.has(tx) && session.status === 'succeeded') {
        // The existing producer snapshots this revision in the same transaction
        // as the repair, after exact result validation and before COMMIT.
        await enqueueSucceededStageArchives(tx as any, session);
        archiveStatus = 'queued_current_revision';
      }
      fencedTransactions.add(tx);
    });
    const guard = createTextbookAuthoringGuard(contract, session.id, { classroomsDir: deps.classrooms,
      ownsStage: async id => (await deps.access(ownerId, id)).kind === 'owned',
      onCandidate: async trace => { need(await sessions.appendControlEvent(session.id, { type: 'mira_textbook_authoring_candidate', ts: Date.now(), data: trace }) !== null, 'CANDIDATE_TRACE_FAILED'); } });
    const result = await tool(guard.wrapStore(writable as any)).execute('reviewed-' + identity.opsSha256, parameters as never);
    if (result.isError) {
      const failure = { error: 'PATCH_EXECUTION_REJECTED', reason: result.content.map((item: any) => item.text ?? '').join('').slice(0, 1000), details: result.details };
      await fs.writeFile(path.join(folder, 'rejected-tool-result.json'), JSON.stringify(failure), { flag: 'wx', mode: 0o600 });
      throw Object.assign(new Error(failure.error), failure);
    }
    const saved = await writable.loadDocument(doc.stage.id);
    need(saved?.scenes.some((scene: any) => scene.id === before.id && textbookDigest(scene) === identity.afterSceneSha256), 'PATCH_SAVE_UNCONFIRMED');
    for (const [name, raw] of Object.entries(originals)) need(sha(await bytes(path.join(job, name))) === sha(raw), 'FROZEN_FILES_CHANGED');
    await fs.writeFile(path.join(folder, 'after.json'), textbookCanonical(after), { flag: 'wx', mode: 0o600 });
    const eventSeq = await sessions.appendControlEvent(session.id, { type: 'mira_textbook_reviewed_patch', ts: Date.now(), data: identity });
    need(eventSeq !== null, 'REPAIR_TRACE_FAILED');
    const receipt = { status: 'applied', ...identity, eventSeq, archiveStatus };
    await fs.writeFile(path.join(folder, 'receipt.json'), JSON.stringify(receipt), { flag: 'wx', mode: 0o600 });
    return receipt;
  } finally { await handle.close(); await fs.unlink(lock); }
}

if (require.main === module) {
  const [job, repair, ...flags] = process.argv.slice(2); let pool: Awaited<ReturnType<typeof defaults.pool>> | undefined;
  (async () => { need(job && repair && (flags.length === 0 || flags[0] === '--execute' && (flags.length === 1 || flags.length === 5 && flags[1] === '--attempt-id' && flags[3] === '--retry-of')), 'USAGE_JOB_REPAIR_EXECUTE');
    const retry = flags.length === 5 ? { attemptId: flags[2], retryOf: flags[4] } : undefined;
    console.log(JSON.stringify(await applyReviewedTextbookPatch(job, repair, flags[0] === '--execute', { ...defaults, pool: async () => (pool = await defaults.pool()) }, retry)));
  })().catch(error => { console.error(JSON.stringify({ error: /^[A-Z_]+$/.test(error.message) ? error.message : 'REVIEWED_PATCH_FAILED', ...(error.reason ? { reason: error.reason } : {}) })); process.exitCode = 1; }).finally(async () => { await pool?.end(); });
}
