// Courseware acceptance through the authorized, local grade-one browser fixture.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFile, stat } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { isDeepStrictEqual } from 'node:util';
import { chromium } from '../../student-web/node_modules/playwright/index.mjs';

const student = 'http://localhost:3000';
const runtime = 'http://localhost:3100';
const textbookId = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$/;
const sha256Hex = /^[a-f0-9]{64}$/;
const previewBindingSchema = 'mira.courseware.preview-binding.v1';
const verifiedPreviewSchema = 'mira.courseware.verified-preview-playback.v1';
const verifiedLoopbackPreviewSchema = 'mira.courseware.verified-loopback-preview-projection.v1';
const fixture = fileURLToPath(new URL(
  '../../.local_backups/student-learning-demo-v1/courseware-acceptance.storage.json', import.meta.url));

function pathOf(url) {
  return new URL(url).pathname;
}

function textbookCoursePath(contentKey, entry) {
  const path = '/learning/textbooks/courses/' + contentKey;
  return entry === undefined ? path : path + '?' + new URLSearchParams({ entry });
}

function directoryId(query, name) {
  const values = query.getAll(name);
  assert.ok(values.length === 1 && textbookId.test(values[0]), 'Invalid directory ' + name);
  return values[0];
}

export async function observeDirectoryCourse(page, directoryQuery, nodeId, contentKey) {
  const query = new URLSearchParams(directoryQuery);
  const editionId = directoryId(query, 'editionId');
  const revisionId = directoryId(query, 'revisionId');
  const unitId = directoryId(query, 'unitId');
  assert.ok(typeof nodeId === 'string' && textbookId.test(nodeId), 'Invalid directory nodeId');
  const contentsPath = '/api/learning/textbooks/' + encodeURIComponent(editionId) + '/contents';
  const response = await page.waitForResponse(response => {
    const url = new URL(response.url());
    return response.request().method() === 'GET' && url.origin === student && url.pathname === contentsPath
      && url.searchParams.size === 1 && url.searchParams.get('alignmentRevisionId') === revisionId;
  }, { timeout: 30000 });
  assert.equal(response.status(), 200, 'Textbook directory request failed');
  const detail = await response.json();
  assert.ok(detail?.ok === true && detail.schemaVersion === 'mira.learning.textbooks.v1'
    && detail.book?.editionId === editionId && detail.book.revisionId === revisionId,
  'Textbook directory does not match the requested edition and revision');
  const units = Array.isArray(detail.units) ? detail.units.filter(unit => unit.unitId === unitId) : [];
  assert.equal(units.length, 1, 'Textbook directory does not identify the requested unit');
  const lessons = Array.isArray(units[0].lessons) ? units[0].lessons.filter(lesson => lesson.nodeId === nodeId) : [];
  assert.equal(lessons.length, 1, 'Textbook unit does not identify the requested lesson');
  const { status, course } = lessons[0];
  assert.ok(status === 'ready' && course?.delivery === 'fixed_textbook' && course.contentKey === contentKey,
    'Textbook lesson does not offer the requested classroom');
  const directoryIdentity = { editionId, revisionId, nodeId };
  if (Object.hasOwn(detail, 'selected')) {
    assert.equal(typeof detail.selected, 'boolean', 'Textbook selection is not a boolean');
    directoryIdentity.selected = detail.selected;
  }
  const entry = course.entry;
  assert.ok(entry === undefined || (typeof entry === 'string' && textbookId.test(entry)),
    'Invalid textbook lesson entry');
  return { directoryIdentity, unitId, entry, href: textbookCoursePath(contentKey, entry) };
}

export function validateDirectoryLaunch(launch, directory, contentKey) {
  const { directoryIdentity: { editionId, revisionId }, unitId, entry } = directory;
  assert.ok(launch?.ok === true && launch.editionId === editionId && launch.revisionId === revisionId
    && launch.unitId === unitId && launch.contentKey === contentKey
    && (entry === undefined || launch.entry === entry), 'Student launch does not match the verified directory lesson');
}

/** Read the private binding produced when staging this direct preview alias. */
export async function readPreviewBinding(path, stage) {
  let binding;
  try {
    const info = await stat(path);
    if (!info.isFile() || (info.mode & 0o077)) throw new Error();
    binding = JSON.parse(await readFile(path, 'utf8'));
  } catch {
    throw new Error('Could not read a private preview binding');
  }
  assert.ok(binding?.schemaVersion === previewBindingSchema && binding.classroomId === stage
    && [binding.bodyFileSha256, binding.bodySha256].every(hash => typeof hash === 'string' && sha256Hex.test(hash))
    && binding.projection?.stage?.id === stage && Array.isArray(binding.projection.scenes),
  'Invalid preview binding');
  return binding;
}

function previewRuntimeOrigin(origin) {
  assert.ok(origin === runtime || (typeof origin === 'string'
    && /^http:\/\/127\.0\.0\.1:[1-9]\d{0,4}$/.test(origin) && URL.canParse(origin)
    && new URL(origin).origin === origin), 'Invalid private preview runtime origin');
  return origin;
}

/** Arm before navigating the direct preview page. The proof identifies its loaded version. */
export async function observePreviewClassroom(page, binding, { runtimeOrigin = runtime } = {}) {
  const origin = previewRuntimeOrigin(runtimeOrigin);
  const response = await page.waitForResponse(candidate => {
    const url = new URL(candidate.url());
    return candidate.request().method() === 'GET' && url.origin === origin && url.pathname === '/api/classroom'
      && !url.username && !url.password && !url.hash
      && url.searchParams.size === 1 && url.searchParams.get('id') === binding.classroomId
      && candidate.frame() === page.mainFrame();
  }, { timeout: 30000 }).catch(() => assert.fail('Verified preview classroom response missing'));
  assert.ok(response.status() === 200, 'Verified preview classroom request failed');
  const detail = await response.json().catch(() => assert.fail('Invalid verified preview response'));
  const classroom = detail?.classroom;
  assert.ok(detail?.success === true && classroom?.id === binding.classroomId,
    'Invalid verified preview response');
  // The direct runtime adds an outer id and creation time, but returns the
  // same stage and scenes that the player hydrates. Compare every nested field.
  const projection = { stage: classroom.stage, scenes: classroom.scenes };
  assert.ok(isDeepStrictEqual(projection, binding.projection), 'Verified preview classroom content mismatch');
  const canonical = JSON.stringify(projection, (_key, value) => value && typeof value === 'object' && !Array.isArray(value)
    ? Object.fromEntries(Object.keys(value).sort().map(key => [key, value[key]])) : value);
  return { schemaVersion: origin === runtime ? verifiedPreviewSchema : verifiedLoopbackPreviewSchema,
    ...(origin === runtime ? {} : { runtimeOrigin: origin }), classroomId: classroom.id,
    bodyFileSha256: binding.bodyFileSha256, bodySha256: binding.bodySha256,
    runtimeProjectionSha256: createHash('sha256').update(canonical).digest('hex') };
}

export async function installPrivatePreviewProgress(context, { runtimeOrigin = runtime } = {}) {
  const origin = previewRuntimeOrigin(runtimeOrigin);
  // Unpublished rooms have no student session. Supply fresh progress only
  // to the local browser preview, without writing any learning events.
  let lastSequence = 0;
  await context.route(origin + '/mira/runtime-events', async route => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ json: { ok: true,
        schemaVersion: 'mira.openmaic.student-runtime-event-receipt.v1', runtimeSessionId: 'private-courseware-preview',
        lastSequence, nextSequence: lastSequence + 1, completed: false, completionReady: false,
        answeredQuestionIds: [] } });
    }
    const event = route.request().postDataJSON();
    lastSequence = event.sequence;
    return route.fulfill({ json: { ok: true, sequence: lastSequence,
      receiptSha256: createHash('sha256').update(JSON.stringify(event)).digest('hex') } });
  });
}

export async function observePlayback({ contentKey, classroomId, previewStage, directoryQuery, nodeId, previewBindingPath },
  { launchBrowser = options => chromium.launch(options) } = {}) {
  assert.ok(previewStage ? /^[\w-]+$/.test(previewStage)
    : /^[a-f0-9]{64}$/.test(contentKey) && classroomId === 'tbpub_' + contentKey.slice(0, 24),
  'Invalid classroom identity');
  assert.ok(nodeId === undefined || (!previewStage && directoryQuery), 'A lesson node requires a directory query');
  assert.ok(previewBindingPath === undefined || (previewStage && !/^(?:tbpub_|tbprev_|omclass_)/.test(previewStage)),
    'A preview binding requires a direct preview');
  const previewBinding = previewBindingPath === undefined ? null : await readPreviewBinding(previewBindingPath, previewStage);
  const storageState = previewStage ? undefined : JSON.parse(await readFile(fixture, 'utf8'));
  if (storageState) assert.equal((await stat(fixture)).mode & 0o077, 0, 'Fixture must be private');
  const browser = await launchBrowser({ channel: 'chrome' });
  let phase = 'opening classroom';
  try {
    const context = await browser.newContext({ storageState, viewport: { width: 1280, height: 800 } });
    if (previewStage) await installPrivatePreviewProgress(context);
    await context.addInitScript(() => {
      window.__miraRecordedPlayback = [];
      const play = HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play = function (...args) {
        const audio = this;
        const playback = play.apply(audio, args);
        playback.then(() => {
          window.__miraRecordedPlayback.push({ duration: audio.duration, scheme: audio.currentSrc.split(':')[0] });
        }, () => {});
        return playback;
      };
    });
    const page = await context.newPage();
    const pageErrors = [];
    page.on('pageerror', error => pageErrors.push(error.message.includes('Minified React error #418')
      ? 'React hydration #418' : error.name));
    const coursePath = textbookCoursePath(contentKey);
    const entry = previewStage ? runtime + '/classroom/' + previewStage + '?mira=1&textbook=1'
      : student + (directoryQuery ? '/learning/textbooks?' + directoryQuery : coursePath);
    const room = previewStage || classroomId;
    const audioResponse = page.waitForResponse(response =>
      pathOf(response.url()).startsWith('/api/classroom-media/' + room + '/')
      && /\.(wav|mp3|ogg|m4a)$/.test(pathOf(response.url())) && response.status() === 200, { timeout: 60000 });
    // A failed route may leave the independent audio wait pending until the browser closes.
    audioResponse.catch(() => {});
    const launchResponse = previewStage ? null : page.waitForResponse(response =>
      response.request().method() === 'POST'
      && (nodeId === undefined || new URL(response.url()).origin === student)
      && pathOf(response.url()) === '/api' + coursePath + '/launch', { timeout: 45000 });
    launchResponse?.catch(() => {});
    const directoryResponse = nodeId === undefined ? null : observeDirectoryCourse(page, directoryQuery, nodeId, contentKey);
    directoryResponse?.catch(() => {});
    const classroomResponse = previewBinding ? observePreviewClassroom(page, previewBinding) : null;
    classroomResponse?.catch(() => {});
    assert.equal((await page.goto(entry, { waitUntil: 'domcontentloaded', timeout: 30000 }))?.status(), 200);
    if (classroomResponse) phase = 'verifying the preview classroom';
    const verifiedPreview = classroomResponse ? await classroomResponse : null;
    let classroom = page;
    let directory;
    if (launchResponse) {
      if (directoryQuery) {
        if (directoryResponse) {
          phase = 'verifying the textbook directory response';
          directory = await directoryResponse;
          assert.equal(directory.directoryIdentity.selected, true, 'This textbook is not selected for the student');
        }
        phase = 'opening lesson from the directory';
        // The picture view only renders one screen of cards. The full
        // directory exposes every lesson link in the selected unit.
        const fullDirectory = page.getByRole('button', { name: '完整目录', exact: true });
        if (await fullDirectory.count() || await fullDirectory.waitFor({ state: 'visible', timeout: 12000 }).then(() => true, () => false)) {
          await fullDirectory.click({ timeout: 5000 });
        }
        const courseLink = directory
          ? page.getByRole('region', { name: '完整目录', exact: true }).locator(`a[href="${directory.href}"]`).first()
          : page.locator(`a[href="${coursePath}"], a[href^="${coursePath}?"]`).first();
        await courseLink.click({ timeout: 30000 });
      }
      phase = 'student launch';
      const launch = await launchResponse;
      assert.equal(launch.status(), 200, 'Student launch failed');
      if (directory) validateDirectoryLaunch(await launch.json(), directory, contentKey);
      phase = 'classroom frame';
      const iframe = page.locator(`iframe.textbook-classroom-frame[src*="/classroom/${room}"]`);
      await iframe.waitFor({ state: 'attached', timeout: 30000 });
      classroom = iframe.contentFrame();
    }
    phase = 'starting narration';
    const start = classroom.getByRole('button', { name: '开始上课', exact: true });
    await start.click({ timeout: 30000 });
    phase = 'loading audio bytes';
    const response = await audioResponse;
    const audioPath = pathOf(response.url());
    const raw = await response.body();
    const sha256 = createHash('sha256').update(raw).digest('hex');
    assert.ok(audioPath.includes(sha256) && raw.length > 0, 'Student audio hash did not match');
    const body = classroom.locator('body');
    phase = 'playing recorded audio';
    await body.evaluate(el => new Promise((resolve, reject) => {
      const deadline = Date.now() + 20000;
      function check() {
        if (el.ownerDocument.defaultView.__miraRecordedPlayback.some(item =>
          Number.isFinite(item.duration) && item.duration > 0)) return resolve();
        if (Date.now() >= deadline) return reject(new Error('Recorded audio did not play'));
        setTimeout(check, 100);
      }
      check();
    }));
    assert.ok(pageErrors.every(error => error === 'React hydration #418'), 'Classroom browser error: ' + pageErrors.join(', '));
    return { ok: true, classroomId: room, mode: previewStage ? 'student-chrome-preview' : 'student-launch',
      openedFromDirectory: Boolean(directoryQuery), recordedAudioPlayed: true,
      ...(directory ? { directoryIdentity: directory.directoryIdentity } : {}),
      ...(verifiedPreview ? { verifiedPreview } : {}),
      audioPath, audioSha256: sha256, audioBytes: raw.length, pageErrors };
  } catch (error) {
    throw new Error(`${phase}: ${error instanceof assert.AssertionError ? error.message : error.name}`);
  } finally {
    await browser.close();
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [key, id, directoryQuery, nodeId] = process.argv.slice(2);
  try {
    if (key === '--preview' && directoryQuery !== undefined) {
      assert.ok(directoryQuery === '--binding' && nodeId && process.argv.length === 6,
        'Use --preview <stage> [--binding <private binding file>]');
    }
    console.log(JSON.stringify(await observePlayback(key === '--preview'
      ? { previewStage: id, previewBindingPath: nodeId } : { contentKey: key, classroomId: id, directoryQuery, nodeId })));
  } catch (error) {
    // Playwright diagnostics can contain authenticated URLs. Keep the receipt private
    // and report only a simple classification for browser transport exceptions.
    console.error('Student playback failed: ' + error.message);
    process.exitCode = 1;
  }
}
