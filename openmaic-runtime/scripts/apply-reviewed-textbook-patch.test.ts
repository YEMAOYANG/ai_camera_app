import test from 'node:test';
import assert from 'node:assert/strict';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { applyReviewedTextbookPatch } from './apply-reviewed-textbook-patch';
import { textbookCanonical, textbookDigest } from '../.runtime/OpenMAIC/lib/server/mira-textbook-scene-contract';

const sha = (s: string | Buffer) => createHash('sha256').update(s).digest('hex');
async function fixture() {
  const root = await fs.mkdtemp(path.join(process.env.MIRA_TASK_TMPDIR || os.tmpdir(), 'reviewed-patch-'));
  const job = path.join(root, 'authoring-job'), classrooms = path.join(root, 'classrooms');
  const uuid = '00000000-0000-4000-8000-000000000001', events: any[] = [];
  const scene = { id: 'scene-one', stageId: 'stage-fixture', order: 1, title: 'Synthetic task', type: 'interactive',
    content: { type: 'interactive', widgetType: 'simulation', html: '<html><head></head><body>before<script>window.syntheticTask=true;</script></body></html>' }, actions: [{ id: 'speech', type: 'speech', text: '观察再修改。' }] };
  let document: any = { stage: { id: scene.stageId, name: 'Synthetic', createdAt: 1, updatedAt: 1 }, scenes: [scene], outline: { producer: 'server-job', producerRef: 'session-fixture' } };
  const policy = { version: 1 }, contract = { schemaVersion: 'mira.textbook.scene-authoring-contract.v1',
    binding: { editionId: 'fixture', revisionId: 'revision', nodeId: 'lesson', unitId: 'unit', unitTitle: 'Unit', lessonTitle: 'Lesson', gradeCode: 'primary_3', subject: 'chinese', volume: 'upper', schoolSystem: 'six_year' },
    teacherContract: { subject: 'chinese', teacherProfileId: 'teacher', teacherProfileHash: 'a'.repeat(64), teacherProfileVersion: 1, teacherName: 'Teacher', voiceId: 'voice', languageCode: 'zh-CN' },
    catalogEvidence: { manifestSha256: 'a'.repeat(64), lessonScopeSha256: 'b'.repeat(64) }, interactionPolicy: { schemaVersion: 'mira.frozen-interaction-policy.v1', policy, sha256: textbookDigest(policy) },
    qualityRules: ['Preserve work'], scopeReview: { target: 'Observe and revise' }, pagePlan: [{ page: 1, title: scene.title, type: 'interactive', widgetType: 'simulation', move: 'Observe and revise' }], lockedAssessments: [] };
  const frozenContract = { schemaVersion: 'mira.frozen-textbook-scene-authoring.v1', contract, sha256: textbookDigest(contract) };
  const draft = JSON.stringify({ skillIds: ['fixture-skill'] });
  const session: any = { id: 'session-fixture', ownerId: 'anon:' + uuid, stageId: 'placeholder', status: 'cancelled', skillId: 'fixture-skill', prompt: '\nMIRA_TEXTBOOK_SCENE_AUTHORING_CONTRACT:\n' + JSON.stringify(frozenContract) + '\nEND_MIRA_TEXTBOOK_SCENE_AUTHORING_CONTRACT\nfixture' };
  const ledger: any = { schemaVersion: 'mira.textbook.authoring-candidate.v1', sessionId: session.id, stageId: scene.stageId, frozenContract, status: 'author_candidate', verification: 'static_contract_only_not_play_or_semantic_review', assetBindings: [], bindingHistory: [],
    scenes: [{ sceneId: scene.id, order: 1, sha256: textbookDigest(scene), canonicalJson: textbookCanonical(scene), contractSha256: frozenContract.sha256 }] };
  await fs.mkdir(job, { recursive: true }); await fs.mkdir(path.join(classrooms, scene.stageId), { recursive: true });
  const original = { 'frozen.json': JSON.stringify({ draftSha256: sha(draft), sceneContract: frozenContract }), 'draft.json': draft,
    'dispatch.json': JSON.stringify({ ownerFingerprint: sha(uuid), requestSha256: sha(session.prompt) }) };
  for (const [name, value] of Object.entries({ ...original, 'state.json': JSON.stringify({ sessionId: session.id }), 'owner.cookies': '# Netscape HTTP Cookie File\n127.0.0.1\tFALSE\t/\tFALSE\t0\tanonymous_id\t' + uuid + '\n' })) await fs.writeFile(path.join(job, name), value);
  const ledgerPath = path.join(classrooms, scene.stageId, 'textbook-authoring-candidate.json'); await fs.writeFile(ledgerPath, JSON.stringify({ ...ledger, sha256: textbookDigest(ledger) }));
  const repair = path.join(root, 'repair.json'); await fs.writeFile(repair, JSON.stringify({ expectedSceneSha256: textbookDigest(scene), target: '/scenes/1', ops: [{ op: 'str_replace', path: '/content/html', oldText: 'before', newText: 'after' }] }));
  let writes = 0, fenceStatus = 'cancelled', corruptBeforeCommit = false, failArchive = false;
  const archiveEvents: any[] = [];
  const pool: any = { query: async (sql: string, params?: any[]) => {
    if (sql.startsWith('WITH candidates')) {
      if (failArchive) throw new Error('synthetic archive failure');
      return { rows: [{ id: scene.stageId, data: document.stage, scenes: document.scenes, outline: document.outline, revision: 9 }] };
    }
    if (sql.includes('INSERT INTO mira_course_archive_events')) { archiveEvents.push(params); return { rows: [] }; }
    return { rows: sql.includes('agent_session_events') ? [{ data: { change: 'stage_created', stageId: scene.stageId } }]
      : sql.includes('FROM agent_sessions') ? [{ status: fenceStatus, lease_worker_id: null }] : [{ data: document.scenes[0] }] };
  } };
  const deps: any = { classrooms, pool: async () => pool, sessions: async () => ({ getSession: async () => session, appendControlEvent: async (_id: string, event: any) => { events.push(event); return events.length; } }),
    access: async () => ({ kind: 'owned' }), ownerStore: async (_owner: string, fence?: any) => ({ loadDocument: async (id: string) => id === scene.stageId ? structuredClone(document) : null,
      putScene: async (_id: string, next: any) => { const before = structuredClone(document); try {
        if (fence) await fence(pool); document.scenes = [structuredClone(next)];
        if (corruptBeforeCommit) document.scenes[0].title = 'Unexpected transaction write';
        if (fence) await fence(pool); writes++;
      } catch (error) { document = before; throw error; } } }) };
  return { root, job, repair, session, deps, original, events, ledgerPath, archiveEvents, get: () => document, writes: () => writes, activate: () => { fenceStatus = 'running'; }, deactivate: () => { fenceStatus = 'cancelled'; }, succeed: () => { session.status = fenceStatus = 'succeeded'; }, failArchive: () => { failArchive = true; }, corruptBeforeCommit: () => { corruptBeforeCommit = true; }, cleanup: () => fs.rm(root, { recursive: true, force: true }) };
}

test('default preflight is read-only; execute uses guarded ledger and durable traces, preserving frozen bytes', async () => {
  const f = await fixture(); try {
    const ledgerBefore = await fs.readFile(f.ledgerPath);
    assert.equal((await applyReviewedTextbookPatch(f.job, f.repair, false, f.deps)).status, 'validated_not_applied');
    assert.equal(f.writes(), 0); assert.deepEqual(await fs.readFile(f.ledgerPath), ledgerBefore); assert.deepEqual(f.events, []);
    const applied = await applyReviewedTextbookPatch(f.job, f.repair, true, f.deps);
    assert.equal(applied.status, 'applied'); assert.equal(f.writes(), 1); assert.match(f.get().scenes[0].content.html, /after/);
    assert.deepEqual(f.events.map(event => event.type), ['mira_textbook_authoring_candidate', 'mira_textbook_reviewed_patch']);
    assert.equal(JSON.parse(await fs.readFile(f.ledgerPath, 'utf8')).scenes[0].sha256, applied.afterSceneSha256);
    for (const [name, value] of Object.entries(f.original)) assert.equal(await fs.readFile(path.join(f.job, name), 'utf8'), value);
    await assert.rejects(() => applyReviewedTextbookPatch(f.job, f.repair, true, f.deps), /SOURCE_SCENE_CHANGED/); assert.equal(f.writes(), 1);
  } finally { await f.cleanup(); }
});
test('running sessions and a reactivation at the write fence cannot execute', async () => {
  for (const duringFence of [false, true]) { const f = await fixture(); try {
    if (duringFence) f.activate(); else f.session.status = 'running';
    await assert.rejects(() => applyReviewedTextbookPatch(f.job, f.repair, true, f.deps), duringFence ? /PATCH_EXECUTION_REJECTED/ : /SESSION_NOT_TERMINAL/);
    assert.equal(f.writes(), 0);
  } finally { await f.cleanup(); } }
});
test('changed owner, frozen input, source SHA or unmatched oldText fail without writes', async () => {
  for (const change of ['owner', 'draft', 'sha', 'oldText']) { const f = await fixture(); try {
    if (change === 'owner') f.session.ownerId = 'anon:other';
    else if (change === 'draft') await fs.writeFile(path.join(f.job, 'draft.json'), '{}');
    else { const repair = JSON.parse(await fs.readFile(f.repair, 'utf8')); if (change === 'sha') repair.expectedSceneSha256 = '0'.repeat(64); else repair.ops[0].oldText = 'absent'; await fs.writeFile(f.repair, JSON.stringify(repair)); }
    await assert.rejects(() => applyReviewedTextbookPatch(f.job, f.repair, true, f.deps)); assert.equal(f.writes(), 0); assert.equal(f.events.length, 0);
  } finally { await f.cleanup(); } }
});
test('an explicit confirmed-unapplied attempt retains the original intent and links its bytes', async () => {
  const f = await fixture(); try {
    f.activate(); await assert.rejects(() => applyReviewedTextbookPatch(f.job, f.repair, true, f.deps), /PATCH_EXECUTION_REJECTED/);
    const folder = path.join(f.job, 'reviewed-patches', sha(await fs.readFile(f.repair))), prior = path.join(folder, 'intent.json'), raw = await fs.readFile(prior);
    f.deactivate(); const result = await applyReviewedTextbookPatch(f.job, f.repair, true, f.deps, { attemptId: 'confirmed-2', retryOf: prior });
    assert.equal(result.status, 'applied'); assert.equal(result.confirmedUnapplied, true); assert.equal(result.retryOfSha256, sha(raw));
    assert.deepEqual(await fs.readFile(prior), raw); assert.equal(f.writes(), 1);
    assert.ok(await fs.stat(path.join(folder, 'attempts', 'confirmed-2', 'receipt.json')));
  } finally { await f.cleanup(); }
});
test('the second transaction fence requires the exact planned result and rolls unexpected writes back', async () => {
  const f = await fixture(); try {
    const before = textbookDigest(f.get()), ledgerBefore = await fs.readFile(f.ledgerPath);
    f.corruptBeforeCommit();
    await assert.rejects(() => applyReviewedTextbookPatch(f.job, f.repair, true, f.deps), error => (error as any).reason.includes('SOURCE_SCENE_CHANGED'));
    assert.equal(textbookDigest(f.get()), before); assert.equal(f.writes(), 0);
    assert.deepEqual(await fs.readFile(f.ledgerPath), ledgerBefore); assert.deepEqual(f.events, []);
  } finally { await f.cleanup(); }
});
test('successful repair enqueues the exact new native snapshot inside its second mutation fence', async () => {
  const f = await fixture(); try {
    f.succeed(); const result = await applyReviewedTextbookPatch(f.job, f.repair, true, f.deps);
    assert.equal(result.archiveStatus, 'queued_current_revision'); assert.equal(f.archiveEvents.length, 1);
    const event = f.archiveEvents[0]; assert.equal(event[0], f.session.id); assert.equal(event[1], f.get().stage.id); assert.equal(event[2], '9');
    const snapshot = JSON.parse(event[4]); assert.deepEqual(snapshot.scenes, f.get().scenes); assert.match(snapshot.scenes[0].content.html, /after/);
    assert.equal(snapshot.outline.producerRef, undefined); assert.equal(snapshot.ownerId, undefined); assert.equal(snapshot.prompt, undefined);
  } finally { await f.cleanup(); }
});
test('archive producer failure rolls the repair transaction back and leaves the candidate ledger unchanged', async () => {
  const f = await fixture(); try {
    const before = textbookDigest(f.get()), ledgerBefore = await fs.readFile(f.ledgerPath);
    f.succeed(); f.failArchive();
    await assert.rejects(() => applyReviewedTextbookPatch(f.job, f.repair, true, f.deps), error => (error as any).reason.includes('synthetic archive failure'));
    assert.equal(f.writes(), 0); assert.equal(textbookDigest(f.get()), before); assert.equal(f.archiveEvents.length, 0);
    assert.deepEqual(await fs.readFile(f.ledgerPath), ledgerBefore); assert.deepEqual(f.events, []);
  } finally { await f.cleanup(); }
});
test('reviewed narration can correct text and append speech without changing existing identities', async () => {
  const f = await fixture(); try {
    const repair = JSON.parse(await fs.readFile(f.repair, 'utf8'));
    repair.ops.push({ op: 'set', path: '/actions', value: [
      { ...f.get().scenes[0].actions[0], text: '观察不同的位置，再修改。' },
      { id: 'speech-help', type: 'speech', text: '需要帮助时，再听一次。' },
    ] });
    await fs.writeFile(f.repair, JSON.stringify(repair));
    assert.equal((await applyReviewedTextbookPatch(f.job, f.repair, true, f.deps)).status, 'applied');
    assert.equal(f.get().scenes[0].actions[0].id, 'speech');
    assert.equal(f.get().scenes[0].actions.length, 2);
  } finally { await f.cleanup(); }
});
test('narration repair rejects removed, reordered, renamed or executable actions before writing', async () => {
  for (const change of ['remove', 'rename', 'reorder', 'execute', 'metadata']) {
    const f = await fixture(); try {
      const action = f.get().scenes[0].actions[0];
      const next = change === 'remove' ? [] : change === 'rename' ? [{ ...action, id: 'other' }]
        : change === 'reorder' ? [{ id: 'new', type: 'speech', text: '新语音。' }, action]
        : change === 'execute' ? [action, { id: 'run', type: 'code', code: 'unsafe()' }]
        : [{ ...action, voiceId: 'different' }];
      const repair = JSON.parse(await fs.readFile(f.repair, 'utf8'));
      repair.ops.push({ op: 'set', path: '/actions', value: next });
      await fs.writeFile(f.repair, JSON.stringify(repair));
      await assert.rejects(() => applyReviewedTextbookPatch(f.job, f.repair, true, f.deps), /NARRATION_REPAIR_SCOPE_INVALID/);
      assert.equal(f.writes(), 0); assert.deepEqual(f.events, []);
    } finally { await f.cleanup(); }
  }
});
test('explicit pre-audio normalization only permits deterministic scene-prefixed speech IDs', async () => {
  for (const change of ['valid', 'text', 'arbitrary-id', 'mixed-html', 'audio']) {
    const f = await fixture(); try {
      const action = f.get().scenes[0].actions[0];
      const next = { ...action, id: 'scene-one-' + action.id };
      if (change === 'text') next.text = 'Changed text';
      if (change === 'arbitrary-id') next.id = 'chosen-id';
      if (change === 'audio') (next as any).audioUrl = '/audio.wav';
      const repair = JSON.parse(await fs.readFile(f.repair, 'utf8'));
      repair.normalization = 'scene-prefixed-speech-ids-v1';
      repair.ops = [{ op: 'set', path: '/actions', value: [next] }, ...(change === 'mixed-html' ? repair.ops : [])];
      await fs.writeFile(f.repair, JSON.stringify(repair));
      if (change === 'valid') {
        assert.equal((await applyReviewedTextbookPatch(f.job, f.repair, true, f.deps)).status, 'applied');
        assert.equal(f.get().scenes[0].actions[0].id, 'scene-one-speech');
      } else {
        await assert.rejects(() => applyReviewedTextbookPatch(f.job, f.repair, true, f.deps), /SPEECH_ID_NORMALIZATION_INVALID/);
        assert.equal(f.writes(), 0);
      }
    } finally { await f.cleanup(); }
  }
});
test('v4 repairs use the exact compact opening contract and verify its full-source link', async () => {
  const f = await fixture(); try {
    const source = JSON.parse(await fs.readFile(path.join(f.job, 'frozen.json'), 'utf8')).sceneContract;
    const compactBody = {
      schemaVersion: 'mira.textbook.author-dispatch-contract.v1', sourceSceneContractSha256: source.sha256,
      binding: source.contract.binding, catalogEvidence: source.contract.catalogEvidence,
      teacherContract: source.contract.teacherContract,
      policyRef: { schemaVersion: 'mira.frozen-interaction-policy.v1', policyId: 'fixture', version: 1, sha256: source.contract.interactionPolicy.sha256 },
      authoringRules: [{ id: 'preserve-work', requirement: 'Preserve work' }], qualityRules: source.contract.qualityRules,
      courseScope: source.contract.scopeReview, pagePlan: source.contract.pagePlan, lockedAssessments: [],
      officialResourceSummary: { schemaVersion: 'fixture', sha256: 'c'.repeat(64), officialTextbook: { title: 'Synthetic' },
        classHours: [{ classHourId: 'one', title: 'Synthetic', learningObjectives: ['Observe'],
          resources: { video: { status: 'reviewed', locations: ['fixture'], findings: ['Synthetic only'] } } }], adaptation: {} },
    };
    const compact = { schemaVersion: 'mira.frozen-textbook-author-dispatch.v1', contract: compactBody, sha256: textbookDigest(compactBody) };
    f.session.prompt = '\nMIRA_TEXTBOOK_AUTHOR_DISPATCH_CONTRACT:\n' + JSON.stringify(compact) + '\nEND_MIRA_TEXTBOOK_AUTHOR_DISPATCH_CONTRACT\nfixture';
    const frozen = JSON.parse(await fs.readFile(path.join(f.job, 'frozen.json'), 'utf8'));
    frozen.schemaVersion = 'mira.operator.workbench-authoring.v4'; frozen.authorDispatchContract = compact;
    await fs.writeFile(path.join(f.job, 'frozen.json'), JSON.stringify(frozen));
    const dispatch = JSON.parse(await fs.readFile(path.join(f.job, 'dispatch.json'), 'utf8'));
    dispatch.requestSha256 = sha(f.session.prompt);
    await fs.writeFile(path.join(f.job, 'dispatch.json'), JSON.stringify(dispatch));
    const ledger = JSON.parse(await fs.readFile(f.ledgerPath, 'utf8'));
    ledger.frozenContract = compact; ledger.scenes[0].contractSha256 = compact.sha256;
    delete ledger.sha256; ledger.sha256 = textbookDigest(ledger);
    await fs.writeFile(f.ledgerPath, JSON.stringify(ledger));
    assert.equal((await applyReviewedTextbookPatch(f.job, f.repair, false, f.deps)).status, 'validated_not_applied');
    frozen.sceneContract.sha256 = '0'.repeat(64);
    await fs.writeFile(path.join(f.job, 'frozen.json'), JSON.stringify(frozen));
    await assert.rejects(() => applyReviewedTextbookPatch(f.job, f.repair, true, f.deps));
    assert.equal(f.writes(), 0);
  } finally { await f.cleanup(); }
});
