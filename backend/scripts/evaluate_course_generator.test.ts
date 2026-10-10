import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import test from 'node:test';
import { CANDIDATES, ENDPOINT, MAX_CALLS, MAX_INPUT_BYTES, MAX_OUTPUT_TOKENS, MAX_USD, NATIVE, PaidRunner, PaidStopped, inputBytes, reservedUsd, validateRaw, validateSpec } from './evaluate_course_generator.ts';

const messages = [{ role: 'system', content: 'Generate native content.' }, { role: 'user', content: '原创图像任务' }];
const identity = { courseId: 'original', phase: 'content', page: 1 };
async function temp(run: (dir: string) => Promise<void>) {
  const dir = await mkdtemp(join(tmpdir(), 'mira-course-eval-test-'));
  try { await run(dir); } finally { await rm(dir, { recursive: true, force: true }); }
}
test('conservative full 68-call scope remains bounded by eight dollars', () => {
  assert.equal(MAX_CALLS, 68); assert.equal(MAX_OUTPUT_TOKENS, 16_000);
  const worst = 34 * reservedUsd(CANDIDATES[0], MAX_INPUT_BYTES) + 34 * reservedUsd(CANDIDATES[1], MAX_INPUT_BYTES);
  assert.ok(worst < MAX_USD); assert.ok(worst > 7);
  assert.equal(inputBytes(messages), Buffer.byteLength(JSON.stringify(messages), 'utf8'));
});
test('journal exists before network dispatch; receipt is durable before caller parses malformed output', async () => temp(async dir => {
  let called = 0;
  const runner = new PaidRunner(dir, 'synthetic-key', async (url, init) => {
    called++; assert.equal(url, ENDPOINT); assert.equal(init.redirect, 'error');
    const row = JSON.parse((await readFile(join(dir, 'dispatch.ndjson'), 'utf8')).trim());
    assert.equal(row.status, 'dispatched');
    const body = JSON.parse(String(init.body));
    assert.equal(body.model, 'deepseek-v4-pro'); assert.deepEqual(body.thinking, { type: 'disabled' });
    assert.equal(body.max_tokens, MAX_OUTPUT_TOKENS); assert.equal(body.response_format, undefined);
    return new Response(JSON.stringify({ choices: [{ finish_reason: 'stop', message: { content: '{invalid}' } }], usage: { prompt_tokens: 42, completion_tokens: 5 } }), { status: 200 });
  });
  await runner.ready(); const reply = await runner.call(CANDIDATES[0], identity, messages);
  assert.throws(() => validateRaw(reply, 'content', 'slide'));
  const row = JSON.parse((await readFile(join(dir, 'dispatch.ndjson'), 'utf8')).split('\n')[0]);
  const saved = JSON.parse(await readFile(join(dir, row.requestId + '.receipt.json'), 'utf8'));
  assert.equal(saved.httpStatus, 200); assert.ok(saved.rawBody.includes('{invalid}'));
  assert.equal((await stat(join(dir, row.requestId + '.receipt.json'))).mode & 0o777, 0o600);
  assert.equal(called, 1); await assert.rejects(runner.call(CANDIDATES[0], identity, messages), /existing_receipt/);
  assert.equal(called, 1);
}));
test('unknown transport stops all further dispatches and a new runner cannot replay the journal', async () => temp(async dir => {
  let called = 0;
  const runner = new PaidRunner(dir, 'synthetic-key', async () => { called++; throw new Error('connection interrupted'); });
  await assert.rejects(runner.call(CANDIDATES[0], identity, messages), PaidStopped);
  await assert.rejects(runner.call(CANDIDATES[1], { ...identity, page: 2 }, messages), PaidStopped);
  assert.equal(called, 1); assert.equal(runner.stopped, true);
  await assert.rejects(new PaidRunner(dir, 'synthetic-key').ready(), /cannot_be_replayed/);
}));
test('input-byte and dollar guards reject before journaling or sending', async () => temp(async dir => {
  let called = 0; const runner = new PaidRunner(dir, 'synthetic-key', async () => { called++; return new Response('{}'); });
  await assert.rejects(runner.call(CANDIDATES[0], identity, [{ role: 'user', content: '中'.repeat(MAX_INPUT_BYTES) }]), /80000/);
  runner.reserveUsd = 7.999;
  await assert.rejects(runner.call(CANDIDATES[0], identity, messages), /budget_exhausted/);
  assert.equal(called, 0); await assert.rejects(readFile(join(dir, 'dispatch.ndjson')), /ENOENT/);
}));
test('strict native output validation rejects truncated JSON, empty actions, PBL and >8 pages without fallback', () => {
  assert.throws(() => validateRaw('[{"type":"text","content":"unfinished"}', 'actions'));
  assert.throws(() => validateRaw('[]', 'actions'), /speech/);
  const outline = { type: 'slide', title: '看图', description: '原创情境', keyPoints: [] };
  assert.throws(() => validateRaw(JSON.stringify({ outlines: Array(9).fill(outline) }), 'plan'), /count/);
  assert.throws(() => validateRaw(JSON.stringify({ outlines: [outline, outline, { ...outline, type: 'quiz' }, { ...outline, type: 'interactive', widgetType: 'game', widgetOutline: {} }, outline, { ...outline, type: 'pbl' }] }), 'plan'), /scene_invalid/);
  validateRaw('[{"type":"text","content":"看看这幅图。"}]', 'actions');
  validateRaw('<!doctype html><html><body><button>原创互动</button></body></html>', 'content', 'interactive');
});
test('HTTP rejection and truncated replies are recorded once, with no automatic retry', async () => temp(async dir => {
  let called = 0;
  const runner = new PaidRunner(dir, 'synthetic-key', async () => { called++; return new Response(JSON.stringify({ choices: [{ finish_reason: 'length', message: { content: '{"elements":[' } }] }), { status: 200 }); });
  await assert.rejects(runner.call(CANDIDATES[1], identity, messages), /incomplete/);
  assert.equal(called, 1); assert.equal(runner.stopped, false);
  await assert.rejects(runner.call(CANDIDATES[1], identity, messages), /existing_receipt/);
  assert.equal(called, 1);
}));
test('only two bounded low-grade subjects are accepted and no research dispatch is possible', () => {
  const spec = { courses: ['chinese', 'math'].map(subject => ({ id: subject, gradeCode: 'primary_1', subject, requirements: { requirement: '原创课件', webSearch: false } })) };
  validateSpec(spec);
  assert.throws(() => validateSpec({ courses: [spec.courses[0]] }), /two_courses/);
  assert.throws(() => validateSpec({ courses: spec.courses.map(c => ({ ...c, requirements: { ...c.requirements, webSearch: true } })) }), /disabled/);
});
test('native planner/content/actions/assembly seam emits renderer-compatible slide, quiz and interactive scenes offline', async () => {
  const generation = await import(pathToFileURL(join(NATIVE, 'packages/@openmaic/generation/dist/index.js')).href);
  const outlines = Array.from({ length: 6 }, (_, i) => ({ id: 'p' + (i + 1), order: i + 1, title: '原创课件' + i,
    type: ['slide', 'quiz', 'interactive'][i % 3], description: '本页用具体图形学习数量。', keyPoints: [],
    ...(i % 3 === 2 ? { widgetType: 'game', widgetOutline: { concept: '点图数量', gameType: 'puzzle' } } : {}) }));
  const plan = await generation.generateSceneOutlinesFromRequirements({ requirement: '原创6页课件' }, undefined, undefined,
    async () => JSON.stringify({ languageDirective: '中文短句', courseTitle: '离线合约核对', outlines }), { imageGenerationEnabled: false, videoGenerationEnabled: false });
  assert.equal(plan.success, true); assert.equal(plan.data.outlines.length, 6);
  for (const outline of plan.data.outlines.slice(0, 3)) {
    let contentCalls = 0; let actionCalls = 0;
    const content = await generation.generateSceneContent(outline, async () => {
      contentCalls++;
      if (outline.type === 'interactive') return '<!doctype html><html><head><script type="application/json" id="widget-config">{"type":"game"}</script></head><body><button id="choice">点图</button><script>document.getElementById("choice").onclick=()=>document.body.dataset.clicked="yes"</script></body></html>';
      if (outline.type === 'quiz') return JSON.stringify([{ id: 'original-question', type: 'single', question: '图中有几个？', options: [{ id: 'A', text: '1' }, { id: 'B', text: '2' }], correctAnswer: 'A', explanation: '只有一个。' }]);
      return JSON.stringify({ elements: [{ type: 'text', left: 50, top: 50, width: 300, height: 60, content: '<p>看图数一数</p>' }], background: { type: 'solid', color: '#fcf6ec' } });
    }, { interactiveIncludeKatex: false, visionEnabled: false });
    assert.ok(content);
    const actions = await generation.generateSceneActions(outline, content, async () => { actionCalls++; return '[{"type":"text","content":"看一看，再点一点。"}]'; }, { languageDirective: '中文短句' });
    const scene = generation.buildCompleteScene(outline, content, actions, 'om_eval_offline', { sceneId: 'om_eval_offline_' + outline.id });
    assert.equal(contentCalls, 1); assert.equal(actionCalls, 1); assert.equal(scene.stageId, 'om_eval_offline');
    assert.equal(scene.type, outline.type); assert.ok(scene.actions.some((a: any) => a.type === 'speech'));
    if (scene.type === 'slide') assert.ok(Array.isArray(scene.content.canvas.elements));
    if (scene.type === 'quiz') assert.ok(Array.isArray(scene.content.questions));
    if (scene.type === 'interactive') { assert.ok(scene.content.html.includes('choice')); assert.equal(scene.content.widgetType, 'game'); }
  }
});
