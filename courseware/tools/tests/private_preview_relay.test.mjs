import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile } from 'node:fs/promises';
import { request } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import { startPrivatePreviewRelay } from '../private_preview_relay.mjs';

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/3ioAAAAASUVORK5CYII=', 'base64');
const wav = Buffer.from('524946462400000057415645666d74201000000001000100401f0000803e0000020010006461746100000000', 'hex');
const alias = 'bound-lesson';
const source = 'original-lesson';
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const pngName = 'pic-' + sha(png) + '.png';
const wavName = 'tts-' + sha(wav) + '.wav';
const mediaPath = name => '/api/classroom-media/' + alias + '/media/' + name;
const audioPath = (name, room = alias) => '/api/classroom-media/' + room + '/audio/' + name;
const dataPath = '/api/classroom?id=' + alias;
const pagePath = '/classroom/' + alias + '?mira=1&textbook=1';
const accessStatusPath = '/api/access-code/status';
const progressPath = '/mira/runtime-events';
const accessReady = { success: true, enabled: false, authenticated: false };

async function fixture(t, { questionAudioUrl, html = '' } = {}) {
  const buildDir = await mkdtemp(join(tmpdir(), 'mira-private-relay-test-'));
  t.after(() => rm(buildDir, { recursive: true, force: true }));
  const bindingPath = join(buildDir, 'binding.json');
  const media = join(buildDir, 'media');
  await mkdir(media);
  await writeFile(join(media, pngName), png);
  await writeFile(join(media, wavName), wav);
  const body = { stage: { id: source, name: 'Frozen classroom' }, scenes: [{
    id: 'scene-one', stageId: source, content: {
      html: '<img src="' + mediaPath(pngName).replace(alias, source) + '">' + html,
      ...(questionAudioUrl ? { questions: [{ id: 'q1', questionAudioUrl }] } : {}),
    },
    actions: [{ audioUrl: mediaPath(wavName).replace(alias, source) }],
  }] };
  const raw = JSON.stringify(body);
  await writeFile(join(buildDir, 'body.json'), raw);
  const projection = JSON.parse(raw.replaceAll(source, alias));
  const binding = { schemaVersion: 'mira.courseware.preview-binding.v1', classroomId: alias,
    bodyFileSha256: sha(raw), bodySha256: 'b'.repeat(64), projection };
  await writeFile(bindingPath, JSON.stringify(binding), { mode: 0o600 });
  return { buildDir, bindingPath, binding, raw, media };
}

function get(relay, path, { method = 'GET', headers = {} } = {}) {
  return new Promise((resolve, reject) => {
    const outgoing = request(relay.origin, { path, method, headers, agent: false }, response => {
      const chunks = [];
      response.on('data', chunk => chunks.push(chunk));
      response.on('error', reject);
      response.on('end', () => resolve({ status: response.statusCode, headers: response.headers, body: Buffer.concat(chunks) }));
    });
    outgoing.on('error', reject);
    outgoing.end();
  });
}

async function start(t, input, fetchUpstream) {
  const relay = await startPrivatePreviewRelay({ ...input, alias, fetchUpstream(url, options) {
    if (url === 'http://127.0.0.1:3100' + accessStatusPath) {
      assert.equal(options.method, 'GET');
      assert.equal(options.redirect, 'manual');
      assert.deepEqual(options.headers, { accept: 'application/json' });
      return Response.json({ ...accessReady, unrelatedField: 'fixture-only' },
        { headers: { 'set-cookie': 'fixture-cookie=value' } });
    }
    return fetchUpstream(url, options);
  } });
  t.after(() => relay.close());
  assert.equal(new URL(relay.origin).hostname, '127.0.0.1');
  return relay;
}

test('serves exact bound projection and verified PNG/WAV over a real loopback listener', async t => {
  const input = await fixture(t);
  const relay = await start(t, input, () => assert.fail('No native media or classroom read is needed'));
  const status = await get(relay, accessStatusPath);
  assert.equal(status.status, 200);
  assert.deepEqual(JSON.parse(status.body), accessReady);
  assert.equal(status.headers['set-cookie'], undefined);
  const data = await get(relay, dataPath);
  assert.equal(data.status, 200);
  assert.deepEqual(JSON.parse(data.body), { success: true, classroom: { id: alias, ...input.binding.projection } });
  assert.equal(data.headers['set-cookie'], undefined);
  assert.equal(data.headers['cache-control'], 'no-store');
  for (const [file, bytes, mime] of [[pngName, png, 'image/png'], [wavName, wav, 'audio/wav']]) {
    const response = await get(relay, mediaPath(file), { headers: { origin: 'null' } });
    assert.equal(response.status, 200);
    assert.equal(response.headers['content-type'], mime);
    assert.equal(response.headers['access-control-allow-origin'], '*');
    assert.deepEqual(response.body, bytes);
    assert.deepEqual(relay.mediaEvidence().find(item => item.path === mediaPath(file)), {
      path: mediaPath(file), sha256: sha(bytes), bytes: bytes.length, mime, requests: 1, opaqueRequests: 1,
    });
  }
  assert.equal(await readFile(join(input.buildDir, 'body.json'), 'utf8'), input.raw);
  assert.deepEqual((await readdir(input.buildDir)).sort(), ['binding.json', 'body.json', 'media']);
});

test('preserves bound formal audio routes in questions and embedded content', async t => {
  const cue = Buffer.concat([wav, Buffer.from([1, 0])]);
  cue.writeUInt32LE(cue.length - 8, 4);
  cue.writeUInt32LE(2, 40);
  const questionFile = sha(wav) + '.wav';
  const cueFile = sha(cue) + '.wav';
  const unlistedFile = sha(png) + '.wav';
  const input = await fixture(t, {
    questionAudioUrl: audioPath(questionFile, source),
    html: '<script>const cue = "' + audioPath(cueFile, source) + '";'
      + 'const external = "https://external.example' + audioPath(unlistedFile, source) + '";</script>',
  });
  await writeFile(join(input.media, questionFile), wav);
  await writeFile(join(input.media, cueFile), cue);
  await writeFile(join(input.media, unlistedFile), png);
  const upstream = [];
  const relay = await start(t, input, (url, options) => {
    upstream.push({ url, method: options.method });
    return new Response('<html>fixture</html>', { headers: { 'content-type': 'text/html' } });
  });
  const data = JSON.parse((await get(relay, dataPath)).body).classroom;
  assert.equal(data.scenes[0].content.questions[0].questionAudioUrl, audioPath(questionFile));
  assert.ok(data.scenes[0].content.html.includes('"' + audioPath(cueFile) + '"'));

  for (const [name, bytes] of [[questionFile, wav], [cueFile, cue]]) {
    const path = audioPath(name);
    const response = await get(relay, path, { headers: { origin: 'null' } });
    assert.equal(response.status, 200);
    assert.equal(response.headers['content-type'], 'audio/wav');
    assert.equal(response.headers['access-control-allow-origin'], '*');
    assert.deepEqual(response.body, bytes);
    assert.deepEqual(relay.mediaEvidence().find(item => item.path === path), {
      path, sha256: sha(bytes), bytes: bytes.length, mime: 'audio/wav', requests: 1, opaqueRequests: 1,
    });
  }
  for (const path of [audioPath(unlistedFile), mediaPath(questionFile), audioPath(questionFile, source),
    audioPath(questionFile) + '?cache=1', audioPath('%2e%2e/' + questionFile)])
    assert.equal((await get(relay, path)).status, 404, path);
  for (const method of ['POST', 'HEAD'])
    assert.equal((await get(relay, audioPath(questionFile), { method })).status, 405);
  assert.equal((await get(relay, audioPath(questionFile), { headers: { cookie: 'fixture=value' } })).status, 403);
  assert.deepEqual(upstream, []);

  const shell = await get(relay, pagePath);
  const csp = shell.headers['content-security-policy'].split('; ');
  assert.ok(csp.includes('media-src blob: ' + relay.origin + mediaPath('') + ' ' + relay.origin + audioPath('')));
  assert.deepEqual(csp.filter(directive => directive.includes('/audio/')), csp.filter(directive => directive.startsWith('media-src ')));
  assert.deepEqual(upstream, [{ url: 'http://127.0.0.1:3100' + pagePath, method: 'GET' }]);
});

test('rejects malformed or cross-room audio in the frozen projection', async t => {
  const name = sha(wav) + '.wav';
  for (const questionAudioUrl of [
    audioPath(name, 'another-room'), audioPath('tts-' + name, source), audioPath(name + '?x=1', source),
    audioPath(name + '#fragment', source), audioPath(sha(wav) + '.png', source),
  ]) {
    const input = await fixture(t, { questionAudioUrl });
    await assert.rejects(startPrivatePreviewRelay({
      ...input, alias, fetchUpstream: () => assert.fail('Unexpected native fetch'),
    }), /Invalid frozen preview audio reference/);
  }
});

test('rejects missing, changed and mislabelled WAV files on bound audio routes', async t => {
  const name = sha(wav) + '.wav';
  const wrongMimeName = sha(png) + '.wav';
  const input = await fixture(t, {
    questionAudioUrl: audioPath(name, source),
    html: "<script>const cue = '" + audioPath(wrongMimeName, source) + "';</script>",
  });
  const relay = await start(t, input, () => assert.fail('Unexpected native fetch'));
  assert.equal((await get(relay, audioPath(name))).status, 404);
  await writeFile(join(input.media, name), Buffer.concat([wav, Buffer.from([1, 0])]));
  assert.equal((await get(relay, audioPath(name))).status, 422);
  await writeFile(join(input.media, wrongMimeName), png);
  assert.equal((await get(relay, audioPath(wrongMimeName))).status, 422);
  assert.deepEqual(relay.mediaEvidence(), []);
});

test('only forwards GET of the exact shell and same-origin public static paths', async t => {
  const input = await fixture(t);
  const upstream = [];
  const relay = await start(t, input, async (url, options) => {
    upstream.push({ url, ...options });
    if (url.endsWith('/redirect.js')) return new Response(null, { status: 307, headers: { location: 'https://external.example' } });
    if (url.endsWith('/wrong-mime.js')) return new Response('untrusted page', { headers: { 'content-type': 'text/html' } });
    const shell = url.endsWith(pagePath);
    return new Response(shell ? '<html>real shell</html>' : 'console.log(1)', {
      headers: { 'content-type': shell ? 'text/html; charset=utf-8' : 'application/javascript',
        'set-cookie': 'fixture-cookie=value', 'access-control-allow-origin': 'https://external.example' },
    });
  });
  const shell = await get(relay, pagePath, { headers: { referer: 'https://ignored.example', 'x-private-marker': 'discard' } });
  assert.equal(shell.status, 200);
  assert.equal(shell.body.toString(), '<html>real shell</html>');
  assert.equal(shell.headers['set-cookie'], undefined);
  assert.equal(shell.headers['access-control-allow-origin'], undefined);
  assert.ok(shell.headers['content-security-policy'].includes("default-src 'none'"));
  assert.ok(shell.headers['content-security-policy'].includes("worker-src 'none'"));
  assert.ok(shell.headers['content-security-policy'].includes("form-action 'none'"));
  assert.ok(shell.headers['content-security-policy'].includes(relay.origin + mediaPath('')));
  assert.ok(!shell.headers['content-security-policy'].includes(relay.origin + audioPath('')));
  assert.doesNotMatch(shell.headers['content-security-policy'], /external|ignored|https:/);
  assert.equal(relay.previewUrl, relay.origin + pagePath);
  const allowedChunk = '/_next/static/chunks/app/classroom/%5Bid%5D/page-a.js';
  assert.equal((await get(relay, allowedChunk)).status, 200);
  assert.equal((await get(relay, '/_next/static/chunks/redirect.js')).status, 502);
  assert.equal((await get(relay, '/_next/static/chunks/wrong-mime.js')).status, 502);
  assert.deepEqual(upstream.map(({ url, method, redirect, headers }) => ({ url, method, redirect, headers })), [
    { url: 'http://127.0.0.1:3100' + pagePath, method: 'GET', redirect: 'manual', headers: { accept: 'text/html' } },
    ...[allowedChunk, '/_next/static/chunks/redirect.js', '/_next/static/chunks/wrong-mime.js'].map(path => ({
      url: 'http://127.0.0.1:3100' + path, method: 'GET', redirect: 'manual', headers: { accept: '*/*' },
    })),
  ]);
});

test('rejects credentials, mismatched host, writes, unknown routes and media paths before forwarding', async t => {
  const relay = await start(t, await fixture(t), () => assert.fail('Request reached native runtime'));
  for (const headers of [{ host: 'external.example' }, { host: 'localhost:3100' },
    { cookie: 'fixture=value' }, { authorization: 'Bearer fixture' }, { 'proxy-authorization': 'Basic fixture' }])
    assert.equal((await get(relay, pagePath, { headers })).status, 403);
  for (const [path, method] of [['/api/classroom', 'POST'], ['/mira/runtime-events', 'POST'],
    [dataPath, 'PUT'], [mediaPath(pngName), 'HEAD']])
    assert.equal((await get(relay, path, { method })).status, 405);
  for (const path of ['/api/classroom?id=other', dataPath + '&id=' + alias, accessStatusPath + '?extra=1',
    pagePath + '&entry=other', '/classroom/other?mira=1&textbook=1', mediaPath('unregistered.png'),
    mediaPath(pngName) + '?extra=1', '/_next/image?url=https://external.example',
    '/_next/static/%2e%2e/stolen.js', '/_next/static//chunk.js', '//external.example/images/a.png',
    'http://external.example/images/a.png'])
    assert.equal((await get(relay, path)).status, 404, path);
  assert.deepEqual(relay.mediaEvidence(), []);
});

test('serves identical empty progress on exact GET only when explicitly enabled', async t => {
  const input = await fixture(t);
  const forwarded = [];
  const upstream = (url, options) => {
    forwarded.push({ url, method: options.method });
    return new Response(null, { status: 404 });
  };
  const defaultRelay = await start(t, input, upstream);
  assert.equal((await get(defaultRelay, progressPath)).status, 404);

  const relay = await start(t, { ...input, serveEmptyProgress: true }, upstream);
  const initial = await get(relay, progressPath);
  assert.equal(initial.status, 200);
  assert.equal(initial.headers['content-type'], 'application/json');
  assert.equal(initial.headers['cache-control'], 'no-store');
  assert.deepEqual(JSON.parse(initial.body), {
    ok: true, schemaVersion: 'mira.openmaic.student-runtime-event-receipt.v1',
    runtimeSessionId: 'private-courseware-preview', lastSequence: 0, nextSequence: 1,
    completed: false, completionReady: false, answeredQuestionIds: [],
  });

  for (const method of ['POST', 'HEAD']) {
    const response = await get(relay, progressPath, { method });
    assert.equal(response.status, 405, method);
    assert.equal(response.headers.allow, 'GET');
  }
  for (const path of [progressPath + '?', progressPath + '?classroomId=' + alias, progressPath + '/'])
    assert.equal((await get(relay, path)).status, 404, path);
  for (const headers of [{ host: 'external.example' }, { cookie: 'fixture=value' },
    { authorization: 'Bearer fixture' }, { 'proxy-authorization': 'Basic fixture' }])
    assert.equal((await get(relay, progressPath, { headers })).status, 403);

  const later = await get(relay, progressPath);
  assert.equal(later.status, 200);
  assert.deepEqual(later.body, initial.body);
  assert.deepEqual(forwarded, []);
});

test('rejects mismatched frozen bytes, projection and reserved alias before opening a port', async t => {
  const input = await fixture(t);
  const options = { ...input, alias, fetchUpstream: () => assert.fail('Unexpected native fetch') };
  await assert.rejects(startPrivatePreviewRelay({ ...options, alias: 'tbpub_existing' }), /direct private preview alias/);
  await writeFile(join(input.buildDir, 'body.json'), input.raw + ' ');
  await assert.rejects(startPrivatePreviewRelay(options), /body hash mismatch/);
  await writeFile(join(input.buildDir, 'body.json'), input.raw);
  input.binding.projection.scenes[0].content.html += ' different frozen HTML';
  await writeFile(input.bindingPath, JSON.stringify(input.binding));
  await assert.rejects(startPrivatePreviewRelay(options), /projection mismatch/);
});

test('fails closed when the actual local access gate is enabled, redirects or cannot be verified', async t => {
  const input = await fixture(t);
  for (const response of [
    Response.json({ ...accessReady, enabled: true }),
    Response.json({ success: true }),
    new Response(null, { status: 307, headers: { location: 'https://external.example' } }),
    new Response('not-json', { headers: { 'content-type': 'application/json' } }),
  ]) {
    const urls = [];
    await assert.rejects(startPrivatePreviewRelay({ ...input, alias, fetchUpstream(url) {
      urls.push(url);
      return response;
    } }), /runtime access/);
    assert.deepEqual(urls, ['http://127.0.0.1:3100' + accessStatusPath]);
  }
});

test('checks media on every GET and refuses a changed or symlinked source', async t => {
  const input = await fixture(t);
  const relay = await start(t, input, () => assert.fail('Unexpected native fetch'));
  const path = join(input.media, pngName);
  await writeFile(path, Buffer.concat([png, Buffer.from('changed')]));
  assert.equal((await get(relay, mediaPath(pngName))).status, 422);
  await rm(path);
  const outside = join(input.buildDir, 'outside.png');
  await writeFile(outside, png);
  await symlink(outside, path);
  assert.equal((await get(relay, mediaPath(pngName))).status, 422);
  assert.deepEqual(relay.mediaEvidence(), []);
  assert.deepEqual(await readFile(outside), png);
});
