import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { lstat, open, readFile, realpath } from 'node:fs/promises';
import { createServer, request as httpRequest } from 'node:http';
import { join } from 'node:path';
import { Readable } from 'node:stream';
import { isDeepStrictEqual } from 'node:util';
import { readPreviewBinding } from './student_playback.mjs';

const loopback = '127.0.0.1';
const upstreamOrigin = 'http://127.0.0.1:3100';
const accessStatusPath = '/api/access-code/status';
const progressPath = '/mira/runtime-events';
const emptyProgress = JSON.stringify({
  ok: true,
  schemaVersion: 'mira.openmaic.student-runtime-event-receipt.v1',
  runtimeSessionId: 'private-courseware-preview',
  lastSequence: 0,
  nextSequence: 1,
  completed: false,
  completionReady: false,
  answeredQuestionIds: [],
});
const maxAssetBytes = 32 * 1024 * 1024;
const staticPaths = ['/_next/static/', '/images/', '/avatars/', '/icons/', '/teachers/', '/fonts/'];
const staticNames = new Set(['/favicon.ico', '/mira-classroom-icon.svg', '/openmaic-mark.png']);
const staticTypes = /^(?:application\/(?:javascript|x-javascript|font-woff|octet-stream)|text\/(?:javascript|css)|font\/(?:woff2?|ttf|otf)|image\/(?:png|jpeg|webp|gif|svg\+xml|x-icon|vnd\.microsoft\.icon))$/;
const imageSignature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

function sha256(bytes) {
  return createHash('sha256').update(bytes).digest('hex');
}

function project(value, source, alias) {
  if (Array.isArray(value)) return value.map(item => project(item, source, alias));
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [
      key, key === 'stageId' && item === source ? alias : project(item, source, alias),
    ]));
  }
  return typeof value === 'string'
    ? value.replaceAll('/api/classroom-media/' + source + '/', '/api/classroom-media/' + alias + '/') : value;
}

async function loadPreview(bindingPath, buildDir, alias) {
  if (!/^[A-Za-z0-9_-]{1,120}$/.test(alias) || /^(?:tbpub_|tbprev_|omclass_)/.test(alias))
    throw new Error('A direct private preview alias is required');
  const binding = await readPreviewBinding(bindingPath, alias);
  const build = await realpath(buildDir);
  const raw = await readFile(join(build, 'body.json'));
  if (sha256(raw) !== binding.bodyFileSha256) throw new Error('Frozen preview body hash mismatch');
  const body = JSON.parse(raw.toString('utf8'));
  const source = body?.stage?.id;
  if (typeof source !== 'string' || !/^[A-Za-z0-9_-]+$/.test(source) || source === alias)
    throw new Error('Invalid frozen preview source identity');
  const expected = project({ stage: { ...body.stage, id: alias }, scenes: body.scenes }, source, alias);
  if (!isDeepStrictEqual(expected, binding.projection)) throw new Error('Frozen preview projection mismatch');

  const mediaRoot = join(build, 'media');
  const media = new Map();
  const encoded = JSON.stringify(expected);
  for (const [path, id, name] of encoded.matchAll(/\/api\/classroom-media\/([A-Za-z0-9_-]+)\/media\/([A-Za-z0-9_.-]+)/g)) {
    const match = name.match(/([a-f0-9]{64})\.(png|wav)$/);
    if (id !== alias || !match || name.length > 255) throw new Error('Invalid frozen preview media reference');
    media.set(path, { name, sha256: match[1], mime: match[2] === 'png' ? 'image/png' : 'audio/wav' });
  }
  // The formal renderer needs the original audio route. Match whole quoted
  // paths, including the escaped quotes around literals in embedded HTML.
  let hasBoundAudio = false;
  for (const [, , path, id, name] of encoded.matchAll(/(\\?"|')(\/api\/classroom-media\/([A-Za-z0-9_-]+)\/audio\/([^"'\\]*))\1/g)) {
    const match = /^([a-f0-9]{64})\.wav$/.exec(name);
    if (id !== alias || !match) throw new Error('Invalid frozen preview audio reference');
    media.set(path, { name, sha256: match[1], mime: 'audio/wav' });
    hasBoundAudio = true;
  }
  if (media.size && (!(await lstat(mediaRoot)).isDirectory() || await realpath(mediaRoot) !== mediaRoot))
    throw new Error('Invalid frozen preview media directory');
  return { binding, mediaRoot, media, hasBoundAudio };
}

function publicStaticPath(target) {
  if (staticNames.has(target)) return true;
  const path = target.replace(/%5b/gi, '[').replace(/%5d/gi, ']');
  return staticPaths.some(prefix => path.startsWith(prefix))
    && /^\/[A-Za-z0-9_.~[\]/-]+\.(?:css|js|mjs|woff2?|ttf|otf|png|jpe?g|webp|gif|svg|ico)$/.test(path)
    && path.slice(1).split('/').every(part => part && part !== '..' && part !== '.');
}

function contentSecurityPolicy(origin, alias, hasBoundAudio) {
  const classroomMedia = origin + '/api/classroom-media/' + alias;
  return [
    "default-src 'none'", "base-uri 'none'", "form-action 'none'",
    "worker-src 'none'", "object-src 'none'",
    "script-src 'unsafe-inline' " + origin + '/_next/static/',
    "style-src 'unsafe-inline' " + origin + '/_next/static/',
    'font-src data: ' + origin + '/fonts/ ' + origin + '/_next/static/',
    'img-src data: blob: ' + classroomMedia + '/media/ '
      + [...staticPaths, ...staticNames].map(path => origin + path).join(' '),
    "frame-src 'self' about:",
    'media-src blob: ' + classroomMedia + '/media/' + (hasBoundAudio ? ' ' + classroomMedia + '/audio/' : ''),
    'connect-src ' + origin + '/api/classroom ' + origin + accessStatusPath + ' ' + origin + progressPath,
  ].join('; ');
}

async function readBoundMedia(mediaRoot, asset) {
  if (await realpath(mediaRoot) !== mediaRoot) throw new Error('Preview media directory moved');
  const file = await open(join(mediaRoot, asset.name), constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const info = await file.stat();
    if (!info.isFile() || info.size < 8 || info.size > maxAssetBytes) throw new Error('Invalid media file');
    const body = await file.readFile();
    const validType = asset.mime === 'image/png'
      ? body.subarray(0, 8).equals(imageSignature)
      : body.toString('ascii', 0, 4) === 'RIFF' && body.toString('ascii', 8, 12) === 'WAVE';
    if (body.length !== info.size || sha256(body) !== asset.sha256 || !validType) throw new Error('Media mismatch');
    return body;
  } finally {
    await file.close();
  }
}

async function readUpstream(response) {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Missing upstream body');
  const chunks = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) return Buffer.concat(chunks, length);
      length += value.byteLength;
      if (length > maxAssetBytes) throw new Error('Upstream body limit exceeded');
      chunks.push(value);
    }
  } finally {
    await reader.cancel().catch(() => {});
  }
}

function fetchLocalRuntime(url, { method, headers, signal }) {
  // A one-request direct agent avoids browser headers, proxy environment and redirects.
  return new Promise((resolve, reject) => {
    const request = httpRequest(url, { method, headers, signal, agent: false }, response => {
      resolve({ status: response.statusCode, headers: { get: key => response.headers[key] },
        body: Readable.toWeb(response), redirected: false });
    });
    request.on('error', reject);
    request.end();
  });
}

async function getLocal(fetchUpstream, path, accept) {
  return fetchUpstream(upstreamOrigin + path, {
    method: 'GET', redirect: 'manual', signal: AbortSignal.timeout(15000), headers: { accept },
  });
}

function upstreamType(response) {
  return response.headers.get('content-type')?.split(';', 1)[0].trim().toLowerCase() ?? '';
}

async function privateAccessStatus(fetchUpstream) {
  const response = await getLocal(fetchUpstream, accessStatusPath, 'application/json');
  if (response.status !== 200 || response.redirected || upstreamType(response) !== 'application/json') {
    await response.body?.cancel().catch(() => {});
    throw new Error('Could not verify local runtime access status');
  }
  let status;
  try {
    status = JSON.parse((await readUpstream(response)).toString('utf8'));
  } catch {
    throw new Error('Could not verify local runtime access status');
  }
  if (status?.success !== true || status.enabled !== false || status.authenticated !== false)
    throw new Error('Local runtime access gate is enabled or unverified');
  return JSON.stringify({ success: true, enabled: false, authenticated: false });
}

function send(response, status, body = '', headers = {}) {
  response.writeHead(status, {
    'cache-control': 'no-store', 'referrer-policy': 'no-referrer', 'x-content-type-options': 'nosniff',
    'content-type': 'text/plain; charset=utf-8', 'content-length': Buffer.byteLength(body), ...headers,
  });
  response.end(body);
}

/** A local read-only candidate transport with an optional empty progress response for preview boot. */
export async function startPrivatePreviewRelay({
  bindingPath, buildDir, alias, serveEmptyProgress = false, fetchUpstream = fetchLocalRuntime,
}) {
  if (typeof alias !== 'string') throw new Error('A direct private preview alias is required');
  const { binding, mediaRoot, media, hasBoundAudio } = await loadPreview(bindingPath, buildDir, alias);
  const accessStatus = await privateAccessStatus(fetchUpstream);
  const pagePath = '/classroom/' + alias + '?mira=1&textbook=1';
  const dataPath = '/api/classroom?id=' + alias;
  const classroom = JSON.stringify({ success: true, classroom: { id: alias, ...binding.projection } });
  const evidence = new Map();
  let host;
  let origin;

  const server = createServer(async (request, response) => {
    if (request.socket.remoteAddress !== loopback || request.headers.host !== host
        || ['cookie', 'authorization', 'proxy-authorization'].some(key => key in request.headers))
      return send(response, 403);
    if (request.method !== 'GET') return send(response, 405, '', { allow: 'GET' });
    const path = request.url;
    if (path === accessStatusPath) return send(response, 200, accessStatus, { 'content-type': 'application/json' });
    if (path === dataPath) return send(response, 200, classroom, { 'content-type': 'application/json' });
    if (path === progressPath && serveEmptyProgress === true)
      return send(response, 200, emptyProgress, { 'content-type': 'application/json' });
    const asset = media.get(path);
    if (asset) {
      try {
        const bytes = await readBoundMedia(mediaRoot, asset);
        response.once('finish', () => {
          const previous = evidence.get(path);
          evidence.set(path, { path, sha256: asset.sha256, bytes: bytes.length, mime: asset.mime,
            requests: (previous?.requests ?? 0) + 1,
            opaqueRequests: (previous?.opaqueRequests ?? 0) + Number(request.headers.origin === 'null') });
        });
        return send(response, 200, bytes, { 'content-type': asset.mime, 'access-control-allow-origin': '*' });
      } catch (error) {
        return send(response, error.code === 'ENOENT' ? 404 : 422);
      }
    }
    const shell = path === pagePath;
    if (!shell && !publicStaticPath(path)) return send(response, 404);
    try {
      const upstream = await getLocal(fetchUpstream, path, shell ? 'text/html' : '*/*');
      const mime = upstreamType(upstream);
      if (upstream.status !== 200 || upstream.redirected
          || (shell ? mime !== 'text/html' : !staticTypes.test(mime))) {
        await upstream.body?.cancel().catch(() => {});
        return send(response, 502);
      }
      const body = await readUpstream(upstream);
      return send(response, 200, body, {
        'content-type': upstream.headers.get('content-type'),
        ...(shell ? { 'content-security-policy': contentSecurityPolicy(origin, alias, hasBoundAudio) } : {}),
      });
    } catch {
      return send(response, 502);
    }
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, loopback, resolve);
  });
  host = loopback + ':' + server.address().port;
  origin = 'http://' + host;
  return {
    origin, previewUrl: origin + pagePath, classroomId: alias,
    mediaEvidence: () => Array.from(evidence.values(), item => ({ ...item })),
    close: () => new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve())),
  };
}
