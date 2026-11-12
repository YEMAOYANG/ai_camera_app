import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { installPrivatePreviewProgress, observeDirectoryCourse, observePlayback, observePreviewClassroom, readPreviewBinding,
  validateDirectoryLaunch } from '../student_playback.mjs';

const contentKey = 'a'.repeat(64);
const directoryQuery = 'editionId=pep-chinese-g1&revisionId=review-1&unitId=unit-1';
const contentsUrl = 'http://localhost:3000/api/learning/textbooks/pep-chinese-g1/contents?alignmentRevisionId=review-1';
const coursePath = '/learning/textbooks/courses/' + contentKey;

function contents(selected = true) {
  const course = { contentKey, delivery: 'fixed_textbook' };
  return {
    ok: true,
    schemaVersion: 'mira.learning.textbooks.v1',
    book: { editionId: 'pep-chinese-g1', revisionId: 'review-1' },
    selected,
    accessMode: 'published',
    units: [
      { unitId: 'unit-1', lessons: [
        { nodeId: 'part-a', status: 'ready', course: { ...course, entry: 'part-a' } },
        { nodeId: 'part-b', status: 'ready', course: { ...course, entry: 'part-b' } },
        { nodeId: 'whole-lesson', status: 'ready', course },
      ] },
    ],
  };
}

function response(url, payload, { method = 'GET', status = 200 } = {}) {
  return { url: () => url, request: () => ({ method: () => method }), status: () => status,
    json: async () => payload };
}

function pageWith(...responses) {
  return { async waitForResponse(matches) {
    const found = responses.find(matches);
    assert.ok(found, 'No matching directory response');
    return found;
  } };
}

function observe(detail, nodeId = 'part-b') {
  return observeDirectoryCourse(pageWith(response(contentsUrl, detail)), directoryQuery, nodeId, contentKey);
}

test('uses the exact directory response and section link even when sibling lessons share a content key', async () => {
  const page = pageWith(
    response(contentsUrl.replace(':3000', ':3100'), {}),
    response(contentsUrl.replace('review-1', 'review-2'), {}),
    response(contentsUrl + '&alignmentRevisionId=review-1', {}),
    response(contentsUrl, {}, { method: 'POST' }),
    response(contentsUrl, contents()),
  );
  const proof = await observeDirectoryCourse(page, directoryQuery, 'part-b', contentKey);
  assert.deepEqual(proof.directoryIdentity, { editionId: 'pep-chinese-g1', revisionId: 'review-1', nodeId: 'part-b', selected: true });
  assert.equal(proof.href, coursePath + '?entry=part-b');
  assert.equal((await observe(contents(), 'whole-lesson')).href, coursePath);
});

test('records the observed selection without substituting true', async () => {
  assert.equal((await observe(contents(false))).directoryIdentity.selected, false);
  const detail = contents();
  delete detail.selected;
  assert.equal(Object.hasOwn((await observe(detail)).directoryIdentity, 'selected'), false);
  await assert.rejects(observe(contents('true')), /selection is not a boolean/);
});

test('rejects the wrong edition, revision, unit, lesson or course key', async () => {
  const detail = contents();
  await assert.rejects(observe({ ...detail, book: { ...detail.book, editionId: 'other' } }), /edition and revision/);
  await assert.rejects(observe({ ...detail, book: { ...detail.book, revisionId: 'other' } }), /edition and revision/);
  await assert.rejects(observe({ ...detail, units: [] }), /requested unit/);
  await assert.rejects(observe(detail, 'other'), /requested lesson/);
  detail.units[0].lessons[1].course.contentKey = 'b'.repeat(64);
  await assert.rejects(observe(detail), /requested classroom/);
});

test('rejects a launch that does not bind the same directory and section', async () => {
  const proof = await observe(contents());
  const launch = { ok: true, contentKey, editionId: 'pep-chinese-g1', revisionId: 'review-1', unitId: 'unit-1', entry: 'part-b' };
  validateDirectoryLaunch(launch, proof, contentKey);
  for (const field of ['contentKey', 'editionId', 'revisionId', 'unitId', 'entry']) {
    assert.throws(() => validateDirectoryLaunch({ ...launch, [field]: 'other' }, proof, contentKey),
      /does not match the verified directory lesson/);
  }
});

const previewStage = 'lesson-exact';
const previewApi = `http://localhost:3100/api/classroom?id=${previewStage}`;
const audioBytes = Buffer.from('fixture audio');
const audioSha = createHash('sha256').update(audioBytes).digest('hex');
const audioPath = `/api/classroom-media/${previewStage}/media/tts-first-${audioSha}.wav`;
const projection = {
  stage: { id: previewStage, name: '精确课堂' },
  scenes: [
    { id: 'a', content: { html: '<h1>Exact teaching content</h1>' }, actions: [{ audioUrl: audioPath }] },
    { id: 'b', content: { questions: [{ id: 'quiz', answer: ['picture'] }] } },
  ],
};

async function privateBinding(t) {
  const dir = await mkdtemp(join(tmpdir(), 'mira-preview-binding-test-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const path = join(dir, 'binding.json');
  await writeFile(path, JSON.stringify({ schemaVersion: 'mira.courseware.preview-binding.v1',
    classroomId: previewStage, bodyFileSha256: 'a'.repeat(64), bodySha256: 'b'.repeat(64), projection }),
  { mode: 0o600 });
  return path;
}

function mockPreview(responses, { played = true } = {}) {
  const frame = {};
  const listeners = [];
  const trace = [];
  const audio = { ...response('http://localhost:3100' + audioPath, null), body: async () => audioBytes };
  const page = {
    on() {}, mainFrame: () => frame,
    waitForResponse: match => new Promise((resolve, reject) => listeners.push({ match, resolve, reject })),
    async goto() {
      assert.ok(listeners.length > 0, 'Response observers must be active before navigation');
      for (const { match, resolve, reject } of listeners) {
        const found = [...responses.map(item => ({ frame: () => frame, ...item })), audio].find(match);
        if (found) resolve(found);
        else reject(new Error('No matching response'));
      }
      return { status: () => 200 };
    },
    getByRole: () => ({ click: async () => trace.push('start') }),
    locator: () => ({ evaluate: async () => {
      if (!played) throw new Error('Audio did not play');
      trace.push('played');
    } }),
  };
  return { trace, launchBrowser: async () => ({
    newContext: async () => ({ route: async () => {}, addInitScript: async () => {}, newPage: async () => page }),
    close: async () => trace.push('close'),
  }) };
}

function previewResponse(value = projection, url = previewApi, options) {
  return response(url, { success: true, classroom: { ...value, id: previewStage, createdAt: 'runtime-created' } }, options);
}

test('natural playback callers can bind the direct preview before navigation', async t => {
  const path = await privateBinding(t);
  await assert.rejects(readPreviewBinding(path, 'other-preview'), /Invalid preview binding/);
  const binding = await readPreviewBinding(path, previewStage);
  const mainFrame = {};
  let matches;
  let deliver;
  const page = {
    mainFrame: () => mainFrame,
    waitForResponse(match) {
      matches = match;
      return new Promise(resolve => { deliver = resolve; });
    },
  };
  const candidate = (value, frame = mainFrame) => ({ ...value, frame: () => frame });
  const proof = observePreviewClassroom(page, binding);
  for (const unrelated of [
    candidate(previewResponse(projection, previewApi.replace('/api/classroom', '/api/classrooms'))),
    candidate(previewResponse(projection, previewApi.replace(previewStage, 'other-preview'))),
    candidate(previewResponse(), {}),
  ]) assert.equal(matches(unrelated), false);
  const exact = candidate(previewResponse());
  assert.equal(matches(exact), true);
  deliver(exact);
  const verified = await proof;
  assert.equal(verified.classroomId, previewStage);
  assert.equal(verified.bodyFileSha256, binding.bodyFileSha256);
  assert.equal(verified.bodySha256, binding.bodySha256);
  assert.match(verified.runtimeProjectionSha256, /^[a-f0-9]{64}$/);

  const mismatch = observePreviewClassroom(page, binding);
  const different = structuredClone(projection);
  different.scenes[0].content.html = '<h1>Different lesson</h1>';
  const wrongBody = candidate(previewResponse(different));
  assert.equal(matches(wrongBody), true);
  deliver(wrongBody);
  await assert.rejects(mismatch, /Verified preview classroom content mismatch/);
});

test('private preview progress registers only the local runtime route and stays in its context', async () => {
  async function install() {
    const registrations = [];
    await installPrivatePreviewProgress({
      route: async (url, handler) => registrations.push({ url, handler }),
    });
    assert.deepEqual(registrations.map(({ url }) => url), ['http://localhost:3100/mira/runtime-events']);
    return (method, event) => registrations[0].handler({
      request: () => ({ method: () => method, postDataJSON: () => event }),
      fulfill: async ({ json }) => json,
    });
  }

  const first = await install();
  const second = await install();
  const fresh = { ok: true, schemaVersion: 'mira.openmaic.student-runtime-event-receipt.v1',
    runtimeSessionId: 'private-courseware-preview', lastSequence: 0, nextSequence: 1,
    completed: false, completionReady: false, answeredQuestionIds: [] };
  assert.deepEqual(await first('GET'), fresh);
  const event = { sequence: 1, eventType: 'scene-entered' };
  assert.deepEqual(await first('POST', event), {
    ok: true, sequence: 1, receiptSha256: createHash('sha256').update(JSON.stringify(event)).digest('hex'),
  });
  assert.deepEqual(await first('GET'), { ...fresh, lastSequence: 1, nextSequence: 2 });
  assert.deepEqual(await second('GET'), fresh);
});

test('private preview helpers only accept the original or a canonical IPv4 loopback origin', async () => {
  const page = { waitForResponse: () => assert.fail('An invalid origin must fail before observing') };
  const context = { route: () => assert.fail('An invalid origin must fail before installing progress') };
  for (const runtimeOrigin of [
    'https://127.0.0.1:5000', 'http://127.0.0.1:5000/', 'http://127.0.0.1:5000/path',
    'http://127.0.0.1:5000?query=1', 'http://operator:fixture@127.0.0.1:5000',
    'http://127.0.0.1.example:5000', 'http://127.0.0.1:05000', 'http://127.0.0.1:65536',
    'http://localhost:5000', 'http://192.0.2.1:5000', 'http://[::1]:5000',
  ]) {
    await assert.rejects(observePreviewClassroom(page, {}, { runtimeOrigin }), /Invalid private preview runtime origin/);
    await assert.rejects(installPrivatePreviewProgress(context, { runtimeOrigin }), /Invalid private preview runtime origin/);
  }
});

test('an exact isolated loopback projection and progress use only the selected relay origin', async t => {
  const runtimeOrigin = 'http://127.0.0.1:5000';
  const api = runtimeOrigin + '/api/classroom?id=' + previewStage;
  const binding = await readPreviewBinding(await privateBinding(t), previewStage);
  const frame = {};
  const candidates = [
    previewResponse(),
    previewResponse(projection, api.replace(':5000', ':5001')),
    previewResponse(projection, api.replace('://', '://fixture:credential@')),
    previewResponse(projection, api.replace('/api/classroom', '/api/classroom/sibling')),
    previewResponse(projection, api),
  ].map(item => ({ ...item, frame: () => frame }));
  const page = { mainFrame: () => frame, waitForResponse: async matches => {
    assert.deepEqual(candidates.map(matches), [false, false, false, false, true]);
    return candidates.at(-1);
  } };
  const result = await observePreviewClassroom(page, binding, { runtimeOrigin });
  assert.equal(result.schemaVersion, 'mira.courseware.verified-loopback-preview-projection.v1');
  assert.equal(result.runtimeOrigin, runtimeOrigin);
  assert.equal(result.bodyFileSha256, binding.bodyFileSha256);

  const handlers = new Map();
  const makeContext = expected => ({ route: async (url, handler) => {
    assert.equal(url, expected + '/mira/runtime-events');
    handlers.set(expected, handler);
  } });
  const nativeOrigin = 'http://localhost:3100';
  await installPrivatePreviewProgress(makeContext(nativeOrigin));
  await installPrivatePreviewProgress(makeContext(runtimeOrigin), { runtimeOrigin });
  const call = (origin, method, event) => handlers.get(origin)({
    request: () => ({ method: () => method, postDataJSON: () => event }),
    fulfill: async ({ json }) => json,
  });
  assert.equal((await call(runtimeOrigin, 'GET')).nextSequence, 1);
  assert.equal((await call(runtimeOrigin, 'POST', { sequence: 1 })).sequence, 1);
  assert.equal((await call(runtimeOrigin, 'GET')).nextSequence, 2);
  assert.equal((await call(nativeOrigin, 'GET')).nextSequence, 1);
});

test('binds the actual browser response only after successful recorded playback', async t => {
  const previewBindingPath = await privateBinding(t);
  const responseProjection = { scenes: projection.scenes, stage: { name: projection.stage.name, id: previewStage } };
  const browser = mockPreview([
    previewResponse(projection, previewApi.replace(':3100', ':3000')),
    previewResponse(projection, previewApi + '&id=' + previewStage),
    previewResponse(projection, previewApi, { method: 'POST' }),
    { ...previewResponse(), frame: () => ({ other: true }) },
    previewResponse(responseProjection),
  ]);
  const result = await observePlayback({ previewStage, previewBindingPath }, browser);
  assert.deepEqual(browser.trace, ['start', 'played', 'close']);
  assert.deepEqual(result.verifiedPreview, {
    schemaVersion: 'mira.courseware.verified-preview-playback.v1', classroomId: previewStage,
    bodyFileSha256: 'a'.repeat(64), bodySha256: 'b'.repeat(64),
    runtimeProjectionSha256: result.verifiedPreview.runtimeProjectionSha256,
  });
  assert.match(result.verifiedPreview.runtimeProjectionSha256, /^[a-f0-9]{64}$/);
  assert.equal(result.openedFromDirectory, false);
  await assert.rejects(observePlayback({ previewStage, previewBindingPath }, mockPreview([previewResponse()], { played: false })),
    /playing recorded audio/);
});

test('rejects the same preview alias with different HTML, order or audio before play', async t => {
  const previewBindingPath = await privateBinding(t);
  for (const change of [
    value => { value.scenes[0].content.html = 'private different classroom'; },
    value => value.scenes.reverse(),
    value => { value.scenes[0].actions[0].audioUrl += '-different'; },
  ]) {
    const altered = structuredClone(projection);
    change(altered);
    const browser = mockPreview([previewResponse(altered)]);
    await assert.rejects(observePlayback({ previewStage, previewBindingPath }, browser), {
      message: 'verifying the preview classroom: Verified preview classroom content mismatch',
    });
    assert.deepEqual(browser.trace, ['close']);
  }
});

test('requires the exact successful runtime response and private expected binding', async t => {
  const previewBindingPath = await privateBinding(t);
  const observed = [
    previewResponse(projection, previewApi.replace(':3100', ':3000')),
    previewResponse(projection, previewApi.replace(previewStage, 'other-preview')),
  ];
  await assert.rejects(observePlayback({ previewStage, previewBindingPath }, mockPreview(observed)),
    /Verified preview classroom response missing/);
  await assert.rejects(observePlayback({ previewStage, previewBindingPath }, mockPreview([previewResponse(projection, previewApi, { status: 404 })])),
    /Verified preview classroom request failed/);
  await assert.rejects(observePlayback({ previewStage, previewBindingPath }, mockPreview([response(previewApi, { success: false })])),
    /Invalid verified preview response/);
  await assert.rejects(observePlayback({ previewStage, previewBindingPath: previewBindingPath + '.missing' }, {
    launchBrowser: async () => assert.fail('Missing binding must fail before starting Chrome'),
  }), /Could not read a private preview binding/);
});

test('legacy preview playback stays diagnostic without a version proof', async () => {
  const result = await observePlayback({ previewStage }, mockPreview([]));
  assert.equal(result.mode, 'student-chrome-preview');
  assert.equal(result.recordedAudioPlayed, true);
  assert.equal(Object.hasOwn(result, 'verifiedPreview'), false);
});

test('verified playback rejects published, frozen and registered runtime aliases before Chrome', async () => {
  for (const reserved of ['tbpub_release', 'tbprev_frozen', 'omclass_existing']) {
    await assert.rejects(observePlayback({ previewStage: reserved, previewBindingPath: 'unused' }, {
      launchBrowser: async () => assert.fail('Reserved alias must fail before starting Chrome'),
    }), /A preview binding requires a direct preview/);
  }
});
