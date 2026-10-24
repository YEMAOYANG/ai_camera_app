import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import http from "node:http";
import { afterEach, test } from "node:test";
import { gzipSync } from "node:zlib";
import vm from "node:vm";
import { parse } from "parse5";

import {
  authorizeRuntimeRequest,
  authorizeTextbookRequest,
  bindTextbookActivityPersistence,
  bindTextbookPageNarration,
  createGateway,
  embedTextbookSceneMedia,
  injectRuntimeAudioBindings,
  mergeContentSecurityPolicy,
  prepareRuntimeEvent,
  sanitizeRuntimeJson,
} from "../src/server.mjs";

const servers = [];

function narrationFixture() {
  const classroomId = 'tbpub_' + 'a'.repeat(24);
  const audioPath = `/api/classroom-media/${classroomId}/audio/correct.mp3`;
  const bytes = Buffer.from('reviewed prerecorded response');
  const cues = [{ id: 'correct', text: '你找到了。' }];
  const html = '<script type="application/json" id="mira-narration-cues">'
    + JSON.stringify({ schemaVersion: 'mira.interactive.narration-cues.v1', cues }) + '</script>'
    + '<script id="mira-pre-recorded-audio">(()=>{const clips='
    + JSON.stringify({ correct: audioPath }) + ';let active=null;})();</script>';
  const scene = { id: 'scene', stageId: classroomId, type: 'interactive', content: { type: 'interactive', html },
    actions: [{ id: 'speech-correct', type: 'speech', text: cues[0].text, audioUrl: audioPath }] };
  const runtime = { purpose: 'fixed_textbook', classroomId, media: [{ path: audioPath,
    mimeType: 'audio/mpeg', byteSize: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') }] };
  return { scene, runtime, bytes, audioPath };
}

test('gateway derives page speech ownership before data URI and blob embedding', () => {
  for (const large of [false, true]) {
    const {scene, runtime, bytes, audioPath} = narrationFixture();
    const assets = [{path: audioPath, mimeType:'audio/mpeg', base64:bytes.toString('base64')}];
    if (large) {
      const path = `/api/classroom-media/${runtime.classroomId}/media/atlas.png`;
      scene.content.html += `<img src="${path}">`.repeat(3);
      assets.push({path, mimeType:'image/png', base64:Buffer.alloc(1024*1024).toString('base64')});
    }
    scene.miraPageNarration = {bindings:[{speechId:'forged'}]};
    bindTextbookPageNarration(scene, runtime, new Set(assets.map(asset => asset.path)));
    assert.deepEqual(scene.miraPageNarration, { schemaVersion:'mira.textbook.page-narration.v1',
      classroomId:runtime.classroomId,sceneId:scene.id,
      bindings:[{speechId:'speech-correct',cueId:'correct',text:'你找到了。',audioPath}] });
    scene.content.html = embedTextbookSceneMedia(scene.content.html,assets);
    assert.equal(scene.content.html.includes('document.write(page)'),large);
    assert.equal(scene.miraPageNarration.bindings[0].audioPath,audioPath);
  }
});

test('activity continuity metadata uses only the authenticated immutable source identity', () => {
  const {scene, runtime, bytes, audioPath} = narrationFixture();
  const sourceSha = createHash('sha256').update(scene.content.html).digest('hex');
  runtime.releaseSha256 = 'c'.repeat(64);
  runtime.activityPersistence = [{sceneId:scene.id,sceneIndex:2,contentSha256:sourceSha}];
  scene.miraActivityPersistence = {releaseSha256:'forged',contentSha256:'forged'};
  bindTextbookActivityPersistence(scene,runtime);
  assert.deepEqual(scene.miraActivityPersistence, {schemaVersion:'mira.textbook.activity-state.v1',
    releaseSha256:runtime.releaseSha256,contentSha256:sourceSha});
  scene.content.html = embedTextbookSceneMedia(scene.content.html,
    [{path:audioPath,mimeType:'audio/mpeg',base64:bytes.toString('base64')}]);
  assert.notEqual(createHash('sha256').update(scene.content.html).digest('hex'),sourceSha);
  assert.equal(scene.miraActivityPersistence.contentSha256,sourceSha);
  for (const change of [
    (s,r)=>{r.purpose='learning';}, (s,r)=>{r.releaseSha256='invalid';},
    (s,r)=>{r.activityPersistence=[];}, (s,r)=>{r.activityPersistence.push({...r.activityPersistence[0]});},
    s=>{s.stageId='other';}, s=>{s.type='quiz';}, s=>{s.miraActivity={section:'games'};},
    s=>{s.content.html='';},
  ]) {
    const s=structuredClone(scene),r=structuredClone(runtime);
    change(s,r);bindTextbookActivityPersistence(s,r);
    assert.equal(Object.hasOwn(s,'miraActivityPersistence'),false);
  }
});

test('gateway clears authored claims and rejects invalid cue, action and media bindings', () => {
  const cases = {
    ordinary: (s,r) => { r.purpose='learning'; },
    quiz: s => { s.type='quiz'; },
    otherClassroom: s => { s.stageId='tbpub_'+'b'.repeat(24); },
    missingClip: s => { s.content.html=s.content.html.replace('"correct":"/api/', '"missing":"/api/'); },
    duplicateManifest: s => { s.content.html+=s.content.html; },
    inertTemplate: s => { s.content.html='<template>'+s.content.html+'</template>'; },
    attributeCollision: s => { s.content.html=s.content.html.replace('id="mira-narration-cues"','id="mira-narration-cues" id="other"'); },
    changedText: s => { s.actions[0].text='不是这句话。'; },
    changedPath: s => { s.actions[0].audioUrl=s.actions[0].audioUrl.replace('correct','other'); },
    duplicateAction: s => { s.actions.push({...s.actions[0]}); },
    missingMedia: (_s,r) => {r.media=[];},
    wrongMime: (_s,r) => {r.media[0].mimeType='text/plain';},
    wrongDigest: (_s,r) => {r.media[0].sha256='invalid';},
  };
  for(const [name, change] of Object.entries(cases)) {
    const {scene,runtime}=narrationFixture();
    scene.miraPageNarration={schemaVersion:'mira.textbook.page-narration.v1',bindings:[{speechId:'forged'}]};
    change(scene,runtime);bindTextbookPageNarration(scene,runtime,new Set(runtime.media.map(m=>m.path)));
    assert.equal(Object.hasOwn(scene,'miraPageNarration'),false,name);
  }
});

test('escaped or unverified media cannot acquire gateway narration ownership', () => {
  const {scene,runtime,audioPath}=narrationFixture();
  scene.content.html=scene.content.html.split(audioPath).join(audioPath.replaceAll('/', '\\/'));
  assert.equal(scene.content.html.includes(audioPath),false);
  bindTextbookPageNarration(scene,runtime,new Set());
  assert.equal(Object.hasOwn(scene,'miraPageNarration'),false);
});

test('large media preserves only a real unambiguous responsive head marker', () => {
  const marker = '<meta name="mira-responsive-activity" content="low-reading-v1">';
  const path = '/api/classroom-media/tbpub_' + 'a'.repeat(24) + '/media/atlas.png';
  const asset = { path, mimeType: 'image/png', base64: Buffer.alloc(1024 * 1024).toString('base64') };
  for (const [head, body, expected] of [
    [marker, '', 1],
    ["<META CONTENT=' low-reading-v1 ' NAME=' MIRA-RESPONSIVE-ACTIVITY '>", '', 1],
    ['', '', 0],
    ['', marker, 0],
    ['<template>' + marker + '</template>', '', 0],
    ['<!--' + marker + '-->', '', 0],
    ['<script>const marker=' + JSON.stringify(marker) + ';</script>', '', 0],
    [marker + marker, '', 0],
    [marker.replace('low-reading-v1', 'unreviewed-profile'), '', 0],
  ]) {
    const bundled = embedTextbookSceneMedia('<!doctype html><html><head>' + head + '</head><body>'
      + body + `<img src="${path}">`.repeat(2) + '</body></html>', [asset]);
    const outerHead = parse(bundled).childNodes.find(node => node.tagName === 'html').childNodes
      .find(node => node.tagName === 'head');
    const responsiveMarkers = outerHead.childNodes.filter(node => node.tagName === 'meta'
      && node.attrs.some(attr => attr.name === 'name' && attr.value === 'mira-responsive-activity'));
    assert.equal(responsiveMarkers.length, expected, `head=${head}, body=${body}`);
  }
});

test('large repeated textbook atlases remain single-copy and reconstruct exact approved HTML', async () => {
  const path = '/api/classroom-media/tbpub_' + 'a'.repeat(24) + '/media/atlas.png';
  const audioPath = path.replace('media/atlas.png', 'audio/teacher.wav');
  const atlas = Buffer.alloc(2 * 1024 * 1024, 39);
  const audio = Buffer.from('reviewed narration bytes');
  const original = '<!doctype html><html><body>' + `<img src="${path}">`.repeat(200)
    + `<script>const picture=${JSON.stringify(path)};const audio=${JSON.stringify(audioPath)};</script></body></html>`;
  const bundled = embedTextbookSceneMedia(original, [
    {path, mimeType:'image/png', base64:atlas.toString('base64')},
    {path:audioPath, mimeType:'audio/wav', base64:audio.toString('base64')},
  ]);
  assert.ok(Buffer.byteLength(bundled) < 3 * 1024 * 1024);
  assert.equal((bundled.match(/<script>/g) || []).length, 1);
  assert.equal((bundled.match(/<\/script>/g) || []).length, 1);
  let restored = '';
  const blobs = [];
  vm.runInNewContext(bundled.split('<script>')[1].split('</script>')[0], {
    atob, Uint8Array, Blob,
    URL: {createObjectURL(blob) {blobs.push(blob);return 'blob:verified-' + blobs.length;}},
    document: {open() {}, write(value) {restored += value;}, close() {}},
  });
  assert.equal(restored, original.split(path).join('blob:verified-1').split(audioPath).join('blob:verified-2'));
  assert.deepEqual(Buffer.from(await blobs[0].arrayBuffer()), atlas);
  assert.deepEqual(Buffer.from(await blobs[1].arrayBuffer()), audio);
  assert.deepEqual(blobs.map(blob => blob.type), ['image/png','audio/wav']);
});

test('fixed textbook permits only its published snapshot and exact archived media', () => {
  const runtime = { purpose: 'fixed_textbook', classroomId: 'tbpub_one',
    media: [{ path: '/api/classroom-media/tbpub_one/audio/one.wav' }] };
  const allowed = (method, path) => authorizeTextbookRequest({ method }, new URL(path, 'https://classroom.example'), runtime).allowed;
  assert.equal(allowed('GET', '/api/classroom?id=tbpub_one'), true);
  assert.equal(allowed('GET', '/api/classroom?id=tbpub_other'), false);
  assert.equal(allowed('GET', '/api/classroom?id=tbpub_one&id=tbpub_other'), false);
  assert.equal(allowed('GET', '/api/classroom-media/tbpub_one/audio/one.wav'), true);
  assert.equal(allowed('GET', '/api/classroom-media/tbpub_one/audio/not-published.wav'), false);
  assert.equal(allowed('GET', '/api/classroom-media/tbpub_other/audio/one.wav'), false);
  assert.equal(allowed('POST', '/mira/textbook-quiz'), true);
  assert.equal(allowed('GET', '/mira/textbook-play'), true);
  assert.equal(allowed('POST', '/mira/textbook-play'), true);
  assert.equal(allowed('GET', '/mira/activity-state'), true);
  assert.equal(allowed('POST', '/mira/activity-state'), true);
  assert.equal(allowed('GET', '/mira/activity-state?scene=other'), false);
  assert.equal(allowed('DELETE', '/mira/activity-state'), false);
  assert.equal(allowed('DELETE', '/mira/textbook-play'), false);
  assert.equal(allowed('GET', '/mira/textbook-audio/' + 'a'.repeat(24) + '.wav'), true);
  assert.equal(allowed('GET', '/mira/textbook-audio/other.wav'), false);
  assert.equal(allowed('POST', '/mira/textbook-audio/' + 'a'.repeat(24) + '.wav'), false);
  assert.equal(allowed('GET', '/mira/textbook-audio/' + 'a'.repeat(24) + '.wav?child=other'), false);
  assert.equal(allowed('GET', '/mira/textbook-play?session=other'), false);
  for (const path of ['/api/chat', '/api/chat/pi', '/api/generate/tts', '/api/transcription']) {
    assert.equal(allowed('POST', path), true);
    assert.equal(allowed('GET', path), false);
    assert.equal(allowed('POST', path + '?id=other'), false);
  }
  assert.equal(allowed('POST', '/api/generate-classroom'), false);
  assert.equal(allowed('POST', '/api/classroom'), false);
  assert.equal(allowed('GET', '/settings'), false);
});
const legacyBrandAssetPaths = [
  "/logo-horizontal.png",
  "/openmaic-mark.png",
  "/openmaic-favicon.ico",
  "/openmaic-apple-icon.png",
];

test('fixed textbook delivery uses private backend snapshot, verified media and server grading', async () => {
  const classroomId = 'tbpub_' + 'a'.repeat(24);
  const mediaPath = `/api/classroom-media/${classroomId}/audio/frozen.wav`;
  const frozenBytes = Buffer.from('archived-audio');
  let corrupt = false;
  let submitted;
  let paidCalls = 0;
  const backend = await listen(http.createServer(async (request, response) => {
    assert.equal(request.headers['x-mira-internal-token'], 'test-internal-token');
    if (request.url.endsWith('/exchange')) {
      assert.equal((await jsonBody(request)).ticket, 'tbpt_reviewed-release');
      return reply(response, { ok: true, runtimeToken: 'tbpr_student-session', classroomId, expiresAt: Date.now() + 60000 });
    }
    if (request.url.endsWith('/validate')) {
      assert.equal((await jsonBody(request)).runtimeToken, 'tbpr_student-session');
      return reply(response, { ok: true, purpose: 'fixed_textbook', classroomId, runtimeSessionId: 'session',
        learningSessionId: 'session', expiresAt: Date.now() + 60000,
        media: [{ path: mediaPath, sha256: createHash('sha256').update(frozenBytes).digest('hex'),
          byteSize: frozenBytes.length, mimeType: 'audio/wav' }] });
    }
    assert.equal(request.headers['x-mira-textbook-token'], 'tbpr_student-session');
    if (request.url.endsWith('/classroom')) {
      const {scene}=narrationFixture();
      scene.content.html=scene.content.html.replaceAll('/audio/correct.mp3','/audio/frozen.wav');
      scene.actions[0].audioUrl=mediaPath;
      scene.miraPageNarration={bindings:[{speechId:'forged'}]};
      return reply(response, { success: true, classroom: { id: classroomId,
        scenes: [{ type: 'interactive', content: { html: `<audio src="${mediaPath}"></audio>` } },scene,
          {type:'quiz',miraPageNarration:{bindings:[{speechId:'forged'}]}}] } });
    }
    if (request.url.endsWith('/quiz')) {
      submitted = await jsonBody(request);
      return reply(response, { ok: true, result: { score: 5 } });
    }
    if (request.url.endsWith('/play-audio/' + 'b'.repeat(24) + '.wav')) {
      response.writeHead(200, { 'Content-Type': 'audio/wav' });
      return response.end(Buffer.from('authored-journey-audio'));
    }
    if (request.url.endsWith('/play')) {
      if (request.method === 'POST') submitted = await jsonBody(request);
      return reply(response, { ok: true, version: 1, games: { phase: 'hunt', index: 1 } });
    }
    response.writeHead(404).end();
  }));
  const upstream = await listen(http.createServer((request, response) => {
    if (request.url === mediaPath) return response.end(corrupt ? Buffer.from('changed') : frozenBytes);
    paidCalls++;
    response.writeHead(500).end();
  }));
  const gateway = await listenGateway({ backend, upstream });
  const launch = await fetch(`${gateway}/mira/textbook-launch?ticket=tbpt_reviewed-release`, { redirect: 'manual' });
  assert.equal(launch.status, 303);
  assert.equal(launch.headers.get('location'), `/classroom/${classroomId}?mira=1&textbook=1`);
  const cookie = launch.headers.getSetCookie().map(item => item.split(';')[0]).join('; ');
  const headers = { cookie, referer: `http://runtime.test/classroom/${classroomId}?mira=1&textbook=1` };
  const snapshot = await fetch(`${gateway}/api/classroom?id=${classroomId}`, { headers });
  assert.equal(snapshot.status, 200);
  const classroom = (await snapshot.json()).classroom;
  assert.equal(classroom.id, classroomId);
  assert.equal(classroom.scenes[0].content.html, `<audio src="data:audio/wav;base64,${frozenBytes.toString('base64')}"></audio>`);
  assert.deepEqual(classroom.scenes[1].miraPageNarration.bindings,
    [{speechId:'speech-correct',cueId:'correct',text:'你找到了。',audioPath:mediaPath}]);
  assert.equal(Object.hasOwn(classroom.scenes[2],'miraPageNarration'),false);
  assert.deepEqual(Buffer.from(await (await fetch(gateway + mediaPath, { headers })).arrayBuffer()), frozenBytes);
  const quiz = await fetch(`${gateway}/mira/textbook-quiz`, { method: 'POST', headers: { ...headers, 'content-type': 'application/json' }, body: JSON.stringify({ answers: { q1: 'A' } }) });
  assert.equal(quiz.status, 200);
  assert.deepEqual(submitted, { answers: { q1: 'A' } });
  assert.equal((await quiz.json()).result.score, 5);
  const clip = await fetch(`${gateway}/mira/textbook-audio/${'b'.repeat(24)}.wav`, { headers });
  assert.equal(clip.status, 200);
  assert.equal(clip.headers.get('content-type'), 'audio/wav');
  assert.equal(await clip.text(), 'authored-journey-audio');
  assert.equal((await fetch(`${gateway}/mira/textbook-audio/${'b'.repeat(24)}.wav`)).status, 401);
  assert.equal((await fetch(`${gateway}/mira/textbook-audio/${'c'.repeat(24)}.wav`, { headers })).status, 404);
  const progress = await fetch(`${gateway}/mira/textbook-play`, { headers });
  assert.equal((await progress.json()).games.index, 1);
  const action = { section: 'games', version: 0, action: 'answer', choice: 'sky' };
  const play = await fetch(`${gateway}/mira/textbook-play`, { method: 'POST',
    headers: { ...headers, 'content-type': 'application/json' }, body: JSON.stringify(action) });
  assert.equal(play.status, 200);
  assert.deepEqual(submitted, action);
  assert.equal((await fetch(`${gateway}/mira/textbook-play`)).status, 401);
  assert.equal((await fetch(`${gateway}/api/generate-classroom`, { method: 'POST', headers })).status, 403);
  assert.equal((await fetch(gateway + mediaPath)).status, 401);
  corrupt = true;
  assert.equal((await fetch(gateway + mediaPath, { headers })).status, 502);
  assert.equal((await fetch(`${gateway}/api/classroom?id=${classroomId}`, {headers})).status,502);
  assert.equal(paidCalls, 0);
});

test('activity snapshots retain cookie authority and their dedicated body limit without widening quiz limits', async () => {
  const classroomId='tbpub_'+'f'.repeat(24),releaseSha256='e'.repeat(64);
  const html='<button id="move">move</button>',contentSha256=createHash('sha256').update(html).digest('hex');
  let writes=0,upstreamReads=0,submitted;
  const backend=await listen(http.createServer(async(request,response)=>{
    assert.equal(request.headers['x-mira-internal-token'],'test-internal-token');
    if(request.url.endsWith('/exchange'))return reply(response,{ok:true,runtimeToken:'tbpr_snapshots',classroomId,expiresAt:Date.now()+60000});
    if(request.url.endsWith('/validate'))return reply(response,{ok:true,purpose:'fixed_textbook',classroomId,
      runtimeSessionId:'bound-session',learningSessionId:'bound-session',releaseSha256,expiresAt:Date.now()+60000,media:[],
      activityPersistence:[{sceneId:'game',sceneIndex:0,contentSha256}]});
    assert.equal(request.headers['x-mira-textbook-token'],'tbpr_snapshots');
    if(request.url.endsWith('/classroom'))return reply(response,{success:true,classroom:{id:classroomId,scenes:[
      {id:'game',stageId:classroomId,type:'interactive',content:{type:'interactive',html},miraActivityPersistence:{forged:true}},
      {id:'slide',stageId:classroomId,type:'slide',miraActivityPersistence:{forged:true}}]}});
    if(request.url.endsWith('/activity-state')){
      if(request.method==='POST'){writes++;submitted=await jsonBody(request);}
      return reply(response,{ok:true,schemaVersion:'mira.textbook.activity-state.v1',classroomId,
        learningSessionId:'bound-session',releaseSha256,activities:[]});
    }
    if(request.url.endsWith('/quiz')){writes++;return reply(response,{ok:true});}
    response.writeHead(404).end();
  }));
  const upstream=await listen(http.createServer((_request,response)=>{upstreamReads++;response.writeHead(500).end();}));
  const gateway=await listenGateway({backend,upstream});
  assert.equal((await fetch(gateway+'/mira/activity-state')).status,401);
  const launch=await fetch(gateway+'/mira/textbook-launch?ticket=tbpt_snapshot',{redirect:'manual'});
  const headers={cookie:launch.headers.getSetCookie().map(item=>item.split(';')[0]).join('; '),
    referer:`http://runtime.test/classroom/${classroomId}?mira=1&textbook=1`};
  const classroom=(await (await fetch(gateway+`/api/classroom?id=${classroomId}`,{headers})).json()).classroom;
  assert.deepEqual(classroom.scenes[0].miraActivityPersistence,{schemaVersion:'mira.textbook.activity-state.v1',releaseSha256,contentSha256});
  assert.equal(Object.hasOwn(classroom.scenes[1],'miraActivityPersistence'),false);
  assert.equal((await fetch(gateway+'/mira/activity-state',{headers})).status,200);
  assert.equal((await fetch(gateway+'/mira/activity-state?child=other',{headers})).status,403);
  assert.equal((await fetch(gateway+'/mira/activity-state',{method:'DELETE',headers})).status,403);
  const post=body=>fetch(gateway+'/mira/activity-state',{method:'POST',headers:{...headers,'content-type':'application/json'},body});
  const data={schemaVersion:'mira.textbook.activity-state.v1',sceneId:'game',sceneIndex:0,releaseSha256,contentSha256,
    learningSessionId:'bound-session',expectedRevision:0,mutationId:'change-1',state:{history:'x'.repeat(12000)}};
  assert.equal((await post(JSON.stringify(data))).status,200);
  assert.deepEqual(submitted,data);
  assert.equal((await fetch(gateway+'/mira/textbook-quiz',{method:'POST',headers:{...headers,'content-type':'application/json'},
    body:JSON.stringify(data)})).status,400);
  assert.equal((await post('{broken')).status,400);
  assert.equal((await post(JSON.stringify({...data,state:{history:'x'.repeat(64*1024)}}))).status,413);
  assert.equal((await fetch(gateway+'/mira/activity-state',{method:'POST',headers:{...headers,'content-type':'text/plain'},body:'{}'})).status,415);
  assert.equal(writes,1);
  assert.equal(upstreamReads,0);
});

test('published video and GLB bytes retain exact session, hash, size and format boundaries', async () => {
  const classroomId = 'tbpub_' + 'd'.repeat(24);
  const pathFor = name => `/api/classroom-media/${classroomId}/media/${name}`;
  const mp4 = Buffer.from('000000186674797069736f6d0000020069736f6d6d703432000000086d6f6f760000000c6d64617400000001', 'hex');
  const webm = Buffer.from('1a45dfa3874282847765626d18538067ffec8100', 'hex');
  const modelJson = Buffer.from('{"asset":{"version":"2.0"}}  ');
  const modelHeader = Buffer.alloc(20);
  modelHeader.write('glTF'); modelHeader.writeUInt32LE(2, 4);
  modelHeader.writeUInt32LE(20 + modelJson.length, 8);
  modelHeader.writeUInt32LE(modelJson.length, 12); modelHeader.writeUInt32LE(0x4e4f534a, 16);
  const glb = Buffer.concat([modelHeader, modelJson]);
  const assets = [ ['clip.mp4', 'video/mp4', mp4], ['clip.webm', 'video/webm', webm], ['shape.glb', 'model/gltf-binary', glb] ];
  const metadata = assets.map(([name, mimeType, bytes]) => ({path: pathFor(name), mimeType,
    sha256: createHash('sha256').update(bytes).digest('hex'), byteSize: bytes.length}));
  let mode = 'valid', reads = 0;
  const backend = await listen(http.createServer(async (request, response) => {
    if (request.url.endsWith('/exchange')) return reply(response, {ok:true,runtimeToken:'tbpr_media-session',classroomId,expiresAt:Date.now()+60000});
    assert.equal(request.url.endsWith('/validate'), true);
    let media = metadata;
    if (mode !== 'valid') {
      const base = {...metadata[0]};
      if (mode === 'mime') base.mimeType = 'application/javascript';
      if (mode === 'extension') base.mimeType = 'model/gltf-binary';
      if (mode === 'oversize') base.byteSize = 16 * 1024 * 1024 + 1;
      if (mode === 'hash') base.sha256 = '0'.repeat(64);
      if (mode === 'size') base.byteSize++;
      media = [base];
    }
    reply(response, {ok:true,purpose:'fixed_textbook',classroomId,runtimeSessionId:'media-session',
      learningSessionId:'media-session',expiresAt:Date.now()+60000,media});
  }));
  const upstream = await listen(http.createServer((request, response) => {
    reads++;
    const asset = assets.find(([name]) => pathFor(name) === request.url);
    if (!asset) return response.writeHead(404).end();
    response.end(asset[2]);
  }));
  const gateway = await listenGateway({backend, upstream});
  const launch = await fetch(`${gateway}/mira/textbook-launch?ticket=tbpt_media-test`, {redirect:'manual'});
  const cookie = launch.headers.getSetCookie().map(item => item.split(';')[0]).join('; ');
  const headers = {cookie,referer:`http://runtime.test/classroom/${classroomId}?mira=1&textbook=1`};
  for (const [name, mime, bytes] of assets) {
    const result = await fetch(gateway + pathFor(name), {headers});
    assert.equal(result.status, 200);
    assert.equal(result.headers.get('content-type'), mime);
    assert.equal(result.headers.get('x-content-type-options'), 'nosniff');
    assert.deepEqual(Buffer.from(await result.arrayBuffer()), bytes);
  }
  const goodReads = reads;
  assert.equal((await fetch(gateway + pathFor('clip.mp4'))).status, 401);
  assert.equal((await fetch(gateway + pathFor('unpublished.glb'), {headers})).status, 403);
  assert.equal(reads, goodReads);
  for (mode of ['mime', 'extension', 'oversize']) {
    assert.equal((await fetch(gateway + pathFor('clip.mp4'), {headers})).status, 502);
    assert.equal(reads, goodReads);
  }
  for (mode of ['hash', 'size']) assert.equal((await fetch(gateway + pathFor('clip.mp4'), {headers})).status, 502);
  assert.equal(reads, goodReads + 2);
});

test('fixed textbook discussions and speech retain native endpoints with session-bound admission', async () => {
  const classroomId = 'tbpub_' + 'b'.repeat(24);
  let admitted = 0;
  let forwarded = 0;
  let reject = false;
  const backend = await listen(http.createServer(async (request, response) => {
    if (request.url.endsWith('/validate')) return reply(response, {
      ok: true, purpose: 'fixed_textbook', classroomId, runtimeSessionId: 'session',
      learningSessionId: 'session', expiresAt: Date.now() + 60000, media: [],
    });
    assert.equal(request.url, '/internal/learning/textbooks/runtime/paid-call');
    assert.equal(request.headers['x-mira-textbook-token'], 'tbpr_student-session');
    admitted++;
    const body = await jsonBody(request);
    assert.equal(body.request.apiKey, undefined);
    if (reject) {
      response.writeHead(401, { 'content-type': 'application/json' });
      return response.end(JSON.stringify({ error: 'textbook_session_invalid' }));
    }
    return reply(response, {
      ok: true, purpose: 'required_teaching',
      paidBudget: { schemaVersion: 'mira.learning.paid-budget-binding.v1', required: true, authorizationId: 'c'.repeat(64) },
      ...(body.path.startsWith('/api/chat') ? { request: { messages: [], config: { agentIds: ['teacher', 'default-3'] } } } : {}),
    });
  }));
  const upstream = await listen(http.createServer(async (request, response) => {
    forwarded++;
    assert.equal(request.headers['x-mira-paid-budget-required'], '1');
    assert.equal(request.headers['x-mira-paid-budget-authorization'], 'c'.repeat(64));
    assert.equal(request.headers['x-mira-textbook-token'], undefined);
    assert.equal(request.headers['x-mira-learning-session'], 'session');
    if (request.url.startsWith('/api/chat')) {
      assert.deepEqual((await jsonBody(request)).config.agentIds, ['teacher', 'default-3']);
      response.writeHead(200, { 'Content-Type': 'text/event-stream' });
      return response.end('data: {"type":"text","agentId":"default-3","text":"一起讨论"}\n\n');
    }
    return reply(response, { success: true });
  }));
  const gateway = await listenGateway({ backend, upstream });
  const headers = { cookie: 'mira_openmaic_runtime=tbpr_student-session',
    referer: `http://runtime.test/classroom/${classroomId}?mira=1&textbook=1`, 'content-type': 'application/json' };
  for (const path of ['/api/chat', '/api/chat/pi', '/api/generate/tts', '/api/transcription']) {
    const result = await fetch(gateway + path, { method: 'POST', headers, body: JSON.stringify({ apiKey: 'untrusted', text: '你好' }) });
    assert.equal(result.status, 200);
    if (path.startsWith('/api/chat')) assert.match(await result.text(), /一起讨论/);
  }
  assert.equal(admitted, 4);
  assert.equal(forwarded, 4);
  reject = true;
  const rejected = await fetch(gateway + '/api/chat/pi', { method: 'POST', headers, body: '{}' });
  assert.equal(rejected.status, 401);
  assert.equal(forwarded, 4);
});

test("production gateway rejects insecure public origins", () => {
  const productionConfig = {
    backendUrl: "http://backend:8000",
    upstreamUrl: "http://openmaic:3000",
    publicOrigin: "https://classroom.example.com",
    studentWebOrigin: "https://learn.example.com",
    internalToken: "test-internal-token",
    secureCookie: true,
  };

  assert.throws(
    () =>
      createGateway({
        ...productionConfig,
        publicOrigin: "http://classroom.example.com",
      }),
    /MIRA_RUNTIME_PUBLIC_ORIGIN must use HTTPS in production/,
  );
  assert.throws(
    () =>
      createGateway({
        ...productionConfig,
        studentWebOrigin: "http://learn.example.com",
      }),
    /MIRA_STUDENT_WEB_ORIGIN must use HTTPS in production/,
  );

  const server = createGateway(productionConfig);
  assert.equal(server.listening, false);
});

afterEach(async () => {
  await Promise.all(
    servers.splice(0).map((server) => new Promise((resolve) => server.close(() => resolve()))),
  );
});

test("one-time Mira ticket becomes a private classroom cookie", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      assert.equal(request.headers["x-mira-internal-token"], "test-internal-token");
      if (request.url === "/internal/learning/openmaic/runtime/exchange") {
        assert.equal(body.ticket, "omt_abcdefghijklmnopqrstuvwxyz012345");
        return reply(response, {
          ok: true,
          runtimeToken: "omr_runtime-token-abcdefghijklmnopqrstuvwxyz",
          expiresAt: Date.now() + 60_000,
          classroomId: "classroom-a",
        });
      }
      if (request.url === "/internal/learning/openmaic/runtime/validate") {
        assert.equal(body.runtimeToken, "omr_runtime-token-abcdefghijklmnopqrstuvwxyz");
        return reply(response, {
          ok: true,
          runtimeSessionId: "runtime-session-a",
          learningSessionId: "learning-session-a",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(404).end();
    }),
  );
  const upstream = await listen(
    http.createServer((request, response) => {
      if (request.url === "/classroom/classroom-a?mira=1") {
        response.setHeader("content-type", "text/html");
        response.end("<main>full interactive classroom</main>");
        return;
      }
      response.writeHead(404).end();
    }),
  );
  const gateway = await listenGateway({ backend, upstream });

  const launch = await fetch(`${gateway}/mira/launch?ticket=omt_abcdefghijklmnopqrstuvwxyz012345`, {
    redirect: "manual",
  });
  assert.equal(launch.status, 303);
  assert.equal(launch.headers.get("location"), "/classroom/classroom-a?mira=1");
  const cookie = launch.headers.get("set-cookie");
  assert.match(cookie, /mira_openmaic_runtime=/);
  assert.match(cookie, /HttpOnly/);
  assert.match(cookie, /SameSite=Lax/);
  assert.doesNotMatch(cookie, /Domain=/);
  assert.doesNotMatch(cookie, /Secure/);

  const classroom = await fetch(`${gateway}/classroom/classroom-a?mira=1`, {
    headers: { cookie: cookie.split(";", 1)[0] },
  });
  assert.equal(classroom.status, 200);
  const classroomHtml = await classroom.text();
  assert.match(classroomHtml, /full interactive classroom/);
  assert.doesNotMatch(classroomHtml, /open\s*maic/i);
  assert.match(
    classroom.headers.get("content-security-policy"),
    /frame-ancestors http:\/\/student\.test/,
  );
});

test("two open classrooms keep audio and event credentials isolated", async () => {
  const calls = [];
  const wav = Buffer.alloc(100, 0);
  wav.write("RIFF", 0); wav.write("WAVE", 8);
  const backend = await listen(http.createServer(async (request, response) => {
    const body = await jsonBody(request);
    if (request.url.endsWith("/exchange")) {
      const id = body.ticket.endsWith("a") ? "classroom-a" : "classroom-b";
      return reply(response, { ok: true, classroomId: id, runtimeToken: `omr_${id}`,
        expiresAt: Date.now() + 60_000 });
    }
    if (request.url.endsWith("/validate")) {
      const id = body.runtimeToken.slice(4);
      return reply(response, { ok: true, classroomId: id, runtimeSessionId: `runtime-${id}`,
        learningSessionId: `learning-${id}`, expiresAt: Date.now() + 60_000 });
    }
    const id = request.headers["x-mira-runtime-classroom-id"];
    calls.push({ method: request.method, path: request.url, id });
    assert.equal(request.headers["x-mira-runtime-session"], `runtime-${id}`);
    assert.equal(request.headers["x-mira-learning-session"], `learning-${id}`);
    if (request.url.includes("/audio/")) {
      if (!request.url.endsWith(`/audio/audio-${id}`)) return response.writeHead(404).end();
      response.writeHead(200, { "content-type": "audio/wav", "content-length": wav.length,
        "x-mira-audio-sha256": createHash("sha256").update(wav).digest("hex") });
      return response.end(wav);
    }
    return reply(response, { ok: true, classroom: id, nextSequence: 1 });
  }));
  const upstream = await listen(http.createServer((_request, response) => {
    response.writeHead(200, { "content-type": "text/html" }); response.end("<main>classroom</main>");
  }));
  const gateway = await listenGateway({ backend, upstream });
  const jar = new Map();
  for (const suffix of ["a", "b"]) {
    const launch = await fetch(`${gateway}/mira/launch?ticket=omt_abcdefghijklmnopqrstuvwxyz${suffix}`,
      { redirect: "manual" });
    assert.equal(launch.status, 303);
    for (const value of launch.headers.getSetCookie()) {
      assert.match(value, /HttpOnly/);
      const [name, token] = value.split(";", 1)[0].split("="); jar.set(name, token);
    }
  }
  assert.equal(jar.size, 3);
  assert.equal(jar.get("mira_openmaic_runtime"), "omr_classroom-b");
  const cookie = [...jar].map(([name, token]) => `${name}=${token}`).join("; ");
  const headersFor = id => ({ cookie, referer: `http://runtime.test/classroom/${id}?mira=1`,
    "x-mira-runtime-session": "forged", "x-mira-runtime-classroom-id": "classroom-b" });
  for (const id of ["classroom-a", "classroom-b", "classroom-a"]) {
    const headers = headersFor(id);
    const page = await fetch(`${gateway}/classroom/${id}?mira=1`, { headers });
    assert.equal(page.status, 200);
    assert.equal(page.headers.get("referrer-policy"), "same-origin");
    const audio = await fetch(`${gateway}/mira/runtime-audio/audio-${id}`, { headers });
    assert.equal(audio.status, 200);
    assert.deepEqual(Buffer.from(await audio.arrayBuffer()), wav);
    const status = await fetch(`${gateway}/mira/runtime-events`, { headers });
    assert.equal((await status.json()).classroom, id);
    const event = await fetch(`${gateway}/mira/runtime-events`, { method: "POST",
      headers: { ...headers, "content-type": "application/json" }, body: JSON.stringify({
        schemaVersion: "mira.openmaic.student-runtime-event.v1", sequence: 1,
        type: "scene_entered", payload: { sceneIndex: 0, sceneId: "scene-0" },
      }) });
    assert.equal((await event.json()).classroom, id);
  }
  const priorCalls = calls.length;
  const onlyB = [...jar].filter(([, value]) => value !== "omr_classroom-a")
    .map(([name, value]) => `${name}=${value}`).join("; ");
  for (const headers of [
    { cookie },
    { ...headersFor("classroom-a"), cookie: onlyB },
    { cookie, referer: "https://outside.example/classroom/classroom-a?classroomId=classroom-b" },
    { ...headersFor("classroom-a"), cookie: cookie.replace("=omr_classroom-a", "=omr_classroom-b") },
  ]) {
    assert.equal((await fetch(`${gateway}/mira/runtime-events`, { headers })).status, 401);
  }
  assert.equal((await fetch(`${gateway}/api/classroom?id=classroom-b`,
    { headers: headersFor("classroom-a") })).status, 401);
  assert.equal(calls.length, priorCalls, "rejected selections never reach event or audio handlers");
  const query = await fetch(`${gateway}/mira/runtime-events?classroomId=classroom-b`, { headers: {
    ...headersFor("classroom-a"), referer: "http://runtime.test/classroom/classroom-a?classroomId=classroom-b",
  } });
  assert.equal((await query.json()).classroom, "classroom-a");
});

test("runtime events are session-bound by the gateway and never accept client identity or score", async () => {
  let eventCalls = 0;
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url === "/internal/learning/openmaic/runtime/validate") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "runtime-session-a",
          learningSessionId: "learning-session-a",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      if (request.url === "/internal/learning/openmaic/runtime/events") {
        if (request.method === "GET") {
          assert.equal(request.headers["x-mira-runtime-session"], "runtime-session-a");
          assert.equal(request.headers["x-mira-learning-session"], "learning-session-a");
          assert.equal(request.headers["x-mira-runtime-classroom-id"], "classroom-a");
          return reply(response, {
            ok: true,
            schemaVersion: "mira.openmaic.student-runtime-event-receipt.v1",
            lastSequence: 1,
            nextSequence: 2,
            completed: false,
            reportId: null,
            internal: { auditId: "must-not-leak" },
          });
        }
        eventCalls += 1;
        assert.equal(request.headers["x-mira-internal-source"], "openmaic-runtime-gateway");
        assert.equal(request.headers["x-mira-runtime-session"], "runtime-session-a");
        assert.equal(request.headers["x-mira-learning-session"], "learning-session-a");
        assert.equal(request.headers["x-mira-runtime-classroom-id"], "classroom-a");
        assert.deepEqual(body, {
          schemaVersion: "mira.openmaic.student-runtime-event.v1",
          sequence: 1,
          type: "scene_entered",
          payload: { sceneIndex: 0, sceneId: "scene-0" },
          idempotencyKey: "e1192a0665ee09e24c776dc68ef8ba2b722d5faab1b8b7411513a512c55595a0",
        });
        return reply(response, {
          ok: true,
          schemaVersion: "mira.openmaic.student-runtime-event-receipt.v1",
          sequence: 1,
          receiptSha256: "a".repeat(64),
          internal: { auditId: "must-not-leak" },
        });
      }
      response.writeHead(404).end();
    }),
  );
  const upstream = await listen(
    http.createServer((_request, response) => {
      response.writeHead(500).end("runtime events must not reach upstream");
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const headers = {
    cookie: "mira_openmaic_runtime=omr_good",
    "content-type": "application/json",
  };

  const accepted = await fetch(`${gateway}/mira/runtime-events`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      schemaVersion: "mira.openmaic.student-runtime-event.v1",
      sequence: 1,
      type: "scene_entered",
      payload: { sceneIndex: 0, sceneId: "scene-0" },
    }),
  });
  assert.equal(accepted.status, 200);
  const acceptedBody = await accepted.json();
  assert.equal(acceptedBody.receiptSha256, "a".repeat(64));
  assert.equal(acceptedBody.internal, undefined);

  const resume = await fetch(`${gateway}/mira/runtime-events`, { headers });
  assert.equal(resume.status, 200);
  const resumeBody = await resume.json();
  assert.equal(resumeBody.nextSequence, 2);
  assert.equal(resumeBody.internal, undefined);

  const forgedScore = await fetch(`${gateway}/mira/runtime-events`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      schemaVersion: "mira.openmaic.student-runtime-event.v1",
      sequence: 2,
      type: "answer_submitted",
      payload: {
        sceneIndex: 0,
        sceneId: "scene-0",
        questionId: "q1",
        response: "12",
        attemptNumber: 1,
        score: 100,
      },
    }),
  });
  assert.equal(forgedScore.status, 400);

  const forgedRetryAttempt = await fetch(`${gateway}/mira/runtime-events`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      schemaVersion: "mira.openmaic.student-runtime-event.v1",
      sequence: 2,
      type: "answer_submitted",
      payload: {
        sceneIndex: 0,
        sceneId: "scene-0",
        questionId: "q1",
        response: "12",
        attemptNumber: 2,
      },
    }),
  });
  assert.equal(forgedRetryAttempt.status, 400);

  const forgedIdentity = await fetch(`${gateway}/mira/runtime-events`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      schemaVersion: "mira.openmaic.student-runtime-event.v1",
      sequence: 2,
      type: "scene_entered",
      payload: { sceneIndex: 1, sceneId: "scene-1" },
      childId: "other-child",
    }),
  });
  assert.equal(forgedIdentity.status, 400);
  assert.equal(eventCalls, 1);
});

test("gateway accepts bounded ASR transcript events and rejects forged ASR metadata", () => {
  const runtime = {
    runtimeSessionId: "runtime-session-a",
    learningSessionId: "learning-session-a",
    classroomId: "classroom-a",
  };
  const accepted = prepareRuntimeEvent(
    Buffer.from(
      JSON.stringify({
        schemaVersion: "mira.openmaic.student-runtime-event.v1",
        sequence: 7,
        type: "asr_transcribed",
        payload: {
          sceneIndex: 2,
          sceneId: "scene-2",
          turnId: "asr-turn-1",
          transcript: "我觉得答案是十二。",
        },
      }),
    ),
    runtime,
  );
  assert.deepEqual(accepted, {
    schemaVersion: "mira.openmaic.student-runtime-event.v1",
    sequence: 7,
    type: "asr_transcribed",
    payload: {
      sceneIndex: 2,
      sceneId: "scene-2",
      turnId: "asr-turn-1",
      transcript: "我觉得答案是十二。",
    },
    idempotencyKey: "cb401d461231173ecb6fd27b75d5f3d3e7c8a66c2887457af2ca57ded71d9702",
  });

  for (const payload of [
    {
      sceneIndex: 2,
      sceneId: "scene-2",
      turnId: "asr-turn-1",
      transcript: "",
    },
    {
      sceneIndex: 2,
      sceneId: "scene-2",
      turnId: "asr-turn-1",
      transcript: "x".repeat(4097),
    },
    {
      sceneIndex: 2,
      sceneId: "scene-2",
      turnId: "bad turn id",
      transcript: "十二",
    },
    {
      sceneIndex: 2,
      sceneId: "scene-2",
      turnId: "asr-turn-1",
      transcript: "十二",
      providerId: "browser-forged-provider",
    },
  ]) {
    assert.throws(
      () =>
        prepareRuntimeEvent(
          Buffer.from(
            JSON.stringify({
              schemaVersion: "mira.openmaic.student-runtime-event.v1",
              sequence: 7,
              type: "asr_transcribed",
              payload,
            }),
          ),
          runtime,
        ),
      /invalid runtime event/,
    );
  }
});

test("gateway removes stale compression headers after fetch decodes a classroom document", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  const classroomHtml = "<main>decoded full interactive classroom</main>";
  const compressed = gzipSync(classroomHtml);
  const upstream = await listen(
    http.createServer((request, response) => {
      assert.equal(request.url, "/classroom/classroom-a?mira=1");
      assert.match(String(request.headers["accept-encoding"]), /gzip/);
      response.writeHead(200, {
        "content-type": "text/html; charset=utf-8",
        "content-encoding": "gzip",
        "content-length": compressed.byteLength,
      });
      response.end(compressed);
    }),
  );
  const gateway = await listenGateway({ backend, upstream });

  const classroom = await fetch(`${gateway}/classroom/classroom-a?mira=1`, {
    headers: {
      cookie: "mira_openmaic_runtime=omr_good",
      "accept-encoding": "gzip",
    },
  });

  assert.equal(classroom.status, 200);
  assert.equal(classroom.headers.get("content-encoding"), null);
  assert.equal(classroom.headers.get("content-length"), null);
  assert.equal(await classroom.text(), classroomHtml);
});

test("gateway preserves upstream CSP while replacing frame ancestors", () => {
  const csp = mergeContentSecurityPolicy(
    "default-src 'self'; script-src 'self' 'nonce-abc'; frame-ancestors 'none'; object-src 'none'",
    "https://students.mira.example",
  );
  assert.match(csp, /default-src 'self'/);
  assert.match(csp, /script-src 'self' 'nonce-abc'/);
  assert.match(csp, /frame-ancestors https:\/\/students\.mira\.example/);
  assert.equal((csp.match(/frame-ancestors/g) || []).length, 1);
  assert.equal((csp.match(/object-src/g) || []).length, 1);
});

test("explicit local mode adds only fixed loopback student origins to private HTTP framing", async () => {
  const backend = await listen(http.createServer((_request, response) => {
    reply(response, formalRuntime());
  }));
  const upstream = await listen(http.createServer((_request, response) => {
    response.writeHead(200, {
      "content-type": "text/html",
      "content-security-policy": "script-src 'self'; frame-ancestors 'none'",
    });
    response.end("<main>classroom</main>");
  }));
  for (const entry of [
    {
      publicOrigin: "http://192.168.228.95:3101",
      studentWebOrigin: "http://192.168.228.95:3000",
      localLanProductionMode: "1",
      expected: "http://192.168.228.95:3000 http://localhost:3000 http://127.0.0.1:3000",
    },
    {
      publicOrigin: "http://192.168.228.95:3101",
      studentWebOrigin: "http://192.168.228.95:3000",
      localLanProductionMode: "0",
      expected: "http://192.168.228.95:3000",
    },
    {
      publicOrigin: "https://classroom.example.com",
      studentWebOrigin: "https://learn.example.com",
      localLanProductionMode: "1",
      expected: "https://learn.example.com",
    },
    {
      publicOrigin: "http://classroom.example.com",
      studentWebOrigin: "http://192.168.228.95:3000",
      localLanProductionMode: "1",
      expected: "http://192.168.228.95:3000",
    },
    {
      publicOrigin: "http://192.168.228.95:3101",
      studentWebOrigin: "http://learn.example.com",
      localLanProductionMode: "1",
      expected: "http://learn.example.com",
    },
  ]) {
    const { expected, ...configuration } = entry;
    const gateway = await listenGateway({ backend, upstream, ...configuration });
    const response = await fetch(`${gateway}/classroom/classroom-a?mira=1`, {
      headers: {
        cookie: "mira_openmaic_runtime=omr_good",
        origin: "http://arbitrary.example:3000",
        "x-forwarded-host": "arbitrary.example:3000",
      },
    });
    assert.equal(response.status, 200);
    const csp = response.headers.get("content-security-policy");
    assert.ok(csp.includes(`frame-ancestors ${expected};`));
    assert.match(csp, /script-src 'self'/);
    assert.doesNotMatch(csp, /arbitrary\.example|\*/);
    assert.equal((csp.match(/frame-ancestors/g) || []).length, 1);
  }
});

test("upstream redirects stay on the browser gateway host without trusting request headers", async () => {
  const backend = await listen(http.createServer((_request, response) => {
    reply(response, formalRuntime());
  }));
  let location;
  const upstream = await listen(http.createServer((_request, response) => {
    response.writeHead(307, { location }).end();
  }));
  const gateway = await listenGateway({ backend, upstream });
  for (const [source, expected] of [
    ["/classroom/classroom-a?mira=1#scene-2", "/classroom/classroom-a?mira=1#scene-2"],
    [`${upstream}/classroom/classroom-a?mira=1`, "/classroom/classroom-a?mira=1"],
    ["http://runtime.test/classroom/classroom-a?mira=1", "/classroom/classroom-a?mira=1"],
    [`${upstream}//external.example/path`, "/external.example/path"],
    ["https://unrelated.example/classroom", "https://unrelated.example/classroom"],
  ]) {
    location = source;
    const response = await fetch(`${gateway}/classroom/classroom-a?mira=1`, {
      headers: {
        cookie: "mira_openmaic_runtime=omr_good",
        "x-forwarded-host": "untrusted.example",
      },
      redirect: "manual",
    });
    assert.equal(response.status, 307);
    assert.equal(response.headers.get("location"), expected);
    if (source !== "https://unrelated.example/classroom") {
      assert.equal(new URL(expected, gateway).origin, new URL(gateway).origin);
    }
  }
});

test("gateway blocks generation and cross-classroom reads", () => {
  const runtime = { classroomId: "allowed-classroom" };
  assert.equal(
    authorizeRuntimeRequest(
      { method: "POST" },
      new URL("http://runtime.test/api/generate-classroom"),
      runtime,
    ).allowed,
    false,
  );
  const wrong = authorizeRuntimeRequest(
    { method: "GET" },
    new URL("http://runtime.test/api/classroom?id=other-classroom"),
    runtime,
  );
  assert.equal(wrong.allowed, false);
  assert.equal(wrong.status, 404);
  assert.equal(
    authorizeRuntimeRequest(
      { method: "GET" },
      new URL("http://runtime.test/classroom/allowed-classroom"),
      runtime,
    ).allowed,
    true,
  );
});

test("gateway permits read-only server provider metadata but never provider writes", () => {
  const runtime = { classroomId: "allowed-classroom" };
  assert.deepEqual(
    authorizeRuntimeRequest(
      { method: "GET" },
      new URL("http://runtime.test/api/server-providers"),
      runtime,
    ),
    { allowed: true, kind: "json" },
  );
  assert.equal(
    authorizeRuntimeRequest(
      { method: "POST" },
      new URL("http://runtime.test/api/server-providers"),
      runtime,
    ).allowed,
    false,
  );
});

test("asset authorization blocks legacy brand files and permits the Mira classroom icon", () => {
  const runtime = { classroomId: "classroom-a" };
  for (const pathname of legacyBrandAssetPaths) {
    assert.deepEqual(
      authorizeRuntimeRequest({ method: "GET" }, new URL(pathname, "http://runtime.test"), runtime),
      {
        allowed: false,
        status: 404,
        error: "asset_not_found",
      },
    );
  }
  assert.deepEqual(
    authorizeRuntimeRequest(
      { method: "GET" },
      new URL("/mira-classroom-icon.svg", "http://runtime.test"),
      runtime,
    ),
    { allowed: true, kind: "asset" },
  );
});

test("student asset authorization fails closed for Next development HMR resources", () => {
  const runtime = { classroomId: "classroom-a" };
  const developmentOnlyPaths = [
    "/_next/webpack-hmr",
    "/_next/static/webpack/123.hot-update.json",
    "/_next/static/chunks/%5Bturbopack%5D_browser_dev_hmr-client_ts_deadbeef._.js",
    "/_next/static/chunks/node_modules_next_dist_client_dev_noop-turbopack-hmr.js",
    "/_next/static/chunks/react-refresh-runtime.js",
  ];

  for (const pathname of developmentOnlyPaths) {
    assert.deepEqual(
      authorizeRuntimeRequest({ method: "GET" }, new URL(pathname, "http://runtime.test"), runtime),
      {
        allowed: false,
        status: 404,
        error: "asset_not_found",
      },
    );
  }

  assert.deepEqual(
    authorizeRuntimeRequest(
      { method: "GET" },
      new URL("/_next/static/chunks/app/classroom/runtime.js", "http://runtime.test"),
      runtime,
    ),
    { allowed: true, kind: "asset" },
  );
});

test("student HTTP gateway never proxies legacy brand files but serves the Mira icon", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  const upstreamPaths = [];
  const upstream = await listen(
    http.createServer((request, response) => {
      upstreamPaths.push(request.url);
      response.writeHead(200, { "content-type": "image/svg+xml" });
      response.end('<svg aria-label="Mira classroom" />');
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const headers = { cookie: "mira_openmaic_runtime=omr_good" };

  for (const pathname of legacyBrandAssetPaths) {
    const blocked = await fetch(`${gateway}${pathname}`, { headers });
    assert.equal(blocked.status, 404);
    const body = await blocked.json();
    assert.equal(body.error, "asset_not_found");
    assert.equal(body.message, "学生课堂不能访问这个功能");
    assert.doesNotMatch(body.message, /open\s*maic/i);
  }
  assert.deepEqual(upstreamPaths, []);

  const icon = await fetch(`${gateway}/mira-classroom-icon.svg`, { headers });
  assert.equal(icon.status, 200);
  assert.equal(icon.headers.get("content-type"), "image/svg+xml");
  assert.match(await icon.text(), /Mira classroom/);
  assert.deepEqual(upstreamPaths, ["/mira-classroom-icon.svg"]);
});

test("student HTTP gateway proxies only classroom avatar assets", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  const avatarPng = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+9cQJkwAAAABJRU5ErkJggg==",
    "base64",
  );
  const upstreamPaths = [];
  const upstream = await listen(
    http.createServer((request, response) => {
      upstreamPaths.push(request.url);
      assert.equal(request.url, "/avatars/teacher-2.png");
      response.writeHead(200, { "content-type": "image/png" });
      response.end(avatarPng);
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const headers = { cookie: "mira_openmaic_runtime=omr_good" };

  const avatar = await fetch(`${gateway}/avatars/teacher-2.png`, { headers });
  assert.equal(avatar.status, 200);
  assert.equal(avatar.headers.get("content-type"), "image/png");
  assert.deepEqual(Buffer.from(await avatar.arrayBuffer()), avatarPng);

  const unknown = await fetch(`${gateway}/private/teacher-2.png`, { headers });
  assert.equal(unknown.status, 403);
  const legacy = await fetch(`${gateway}/logo-horizontal.png`, { headers });
  assert.equal(legacy.status, 404);
  assert.deepEqual(upstreamPaths, ["/avatars/teacher-2.png"]);
});

test("formal teacher portraits allow only four authenticated GET or HEAD asset paths", async () => {
  const paths = [
    "/teachers/mi-chinese-v1.png", "/teachers/ashu-math-v1.png",
    "/teachers/coco-english-v1.png", "/teachers/ke-science-v1.png",
  ];
  const runtime = { classroomId: "classroom-a" };
  const fixed = { ...runtime, purpose: "fixed_textbook" };
  for (const authorize of [authorizeRuntimeRequest, authorizeTextbookRequest]) {
    const scope = authorize === authorizeTextbookRequest ? fixed : runtime;
    for (const path of paths) {
      for (const method of ["GET", "HEAD"]) {
        assert.deepEqual(authorize({ method }, new URL(path, "https://runtime.test"), scope),
          { allowed: true, kind: "asset" });
      }
      for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
        assert.equal(authorize({ method }, new URL(path, "https://runtime.test"), scope).allowed, false);
      }
    }
    for (const path of ["/teachers/unknown.png", "/teachers/ke-science-v1.png/private", "/teachers/ke-science-v2.png"]) {
      for (const method of ["GET", "HEAD"])
        assert.equal(authorize({ method }, new URL(path, "https://runtime.test"), scope).allowed, false);
    }
  }
  // A conversation-only probe never acquires the classroom asset boundary.
  assert.equal(authorizeRuntimeRequest({ method: "GET" }, new URL(paths[0], "https://runtime.test"),
    { ...runtime, purpose: "conversation_probe" }).allowed, false);
  const backend = await listen(http.createServer(async (request, response) => {
    const body = await jsonBody(request);
    if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
      return reply(response, { ok: true, runtimeSessionId: "rs1", learningSessionId: "ls1",
        classroomId: "classroom-a", expiresAt: Date.now() + 60_000 });
    }
    response.writeHead(401); response.end();
  }));
  const upstreamRequests = [];
  const bytes = Buffer.from("pinned-portrait-test-bytes");
  const upstream = await listen(http.createServer((request, response) => {
    assert.ok(paths.includes(request.url));
    assert.ok(["GET", "HEAD"].includes(request.method));
    upstreamRequests.push([request.method, request.url]);
    response.writeHead(200, { "content-type": "image/png", "content-length": String(bytes.length) });
    response.end(request.method === "HEAD" ? undefined : bytes);
  }));
  const gateway = await listenGateway({ backend, upstream });
  const headers = { cookie: "mira_openmaic_runtime=omr_good" };
  for (const path of paths) {
    const get = await fetch(gateway + path, { headers });
    assert.equal(get.status, 200);
    assert.equal(get.headers.get("content-type"), "image/png");
    assert.deepEqual(Buffer.from(await get.arrayBuffer()), bytes);
    const head = await fetch(gateway + path, { method: "HEAD", headers });
    assert.equal(head.status, 200);
    assert.equal((await head.arrayBuffer()).byteLength, 0);
  }
  const before = upstreamRequests.length;
  assert.equal((await fetch(gateway + "/teachers/unknown.png", { headers })).status, 403);
  assert.equal((await fetch(gateway + paths[0], { method: "POST", headers })).status, 403);
  for (const method of ["GET", "HEAD"])
    assert.equal((await fetch(gateway + paths[0], { method })).status, 401);
  assert.equal(upstreamRequests.length, before);
  assert.equal(before, 8);
});

test("student HTTP gateway never caches Next runtime chunks but may cache immutable assets", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  const upstream = await listen(
    http.createServer((request, response) => {
      response.writeHead(200, {
        "content-type": request.url.startsWith("/_next/") ? "application/javascript" : "image/png",
        "cache-control": "public, max-age=31536000, immutable",
      });
      response.end("asset");
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const headers = { cookie: "mira_openmaic_runtime=omr_good" };

  const runtimeChunk = await fetch(`${gateway}/_next/static/chunks/app/classroom/runtime.js`, {
    headers,
  });
  assert.equal(runtimeChunk.status, 200);
  assert.equal(runtimeChunk.headers.get("cache-control"), "no-store");

  const avatar = await fetch(`${gateway}/avatars/teacher-2.png`, { headers });
  assert.equal(avatar.status, 200);
  assert.equal(avatar.headers.get("cache-control"), "private, max-age=3600");
});

test("student runtime hides operator-only MP4 export without calling upstream", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  let upstreamCalls = 0;
  const upstream = await listen(
    http.createServer((_request, response) => {
      upstreamCalls += 1;
      reply(response, { enabled: true });
    }),
  );
  const gateway = await listenGateway({ backend, upstream });

  const capability = await fetch(`${gateway}/api/export-video/capability`, {
    headers: { cookie: "mira_openmaic_runtime=omr_good" },
  });
  assert.equal(capability.status, 200);
  assert.deepEqual(await capability.json(), { enabled: false });
  assert.equal(upstreamCalls, 0);

  assert.equal(
    authorizeRuntimeRequest(
      { method: "POST" },
      new URL("http://runtime.test/api/export-video/render"),
      {
        classroomId: "classroom-a",
      },
    ).allowed,
    false,
  );

  const blocked = await fetch(`${gateway}/api/export-video/render`, {
    method: "POST",
    headers: {
      cookie: "mira_openmaic_runtime=omr_good",
      "content-type": "application/json",
    },
    body: "{}",
  });
  assert.equal(blocked.status, 403);
  const blockedBody = await blocked.json();
  assert.equal(blockedBody.error, "openmaic_route_not_allowed");
  assert.equal(blockedBody.message, "学生课堂不能访问这个功能");
  assert.doesNotMatch(blockedBody.message, /open\s*maic/i);
  assert.equal(upstreamCalls, 0);
});

test("runtime JSON removes client credentials and rejects another stage", () => {
  const cleaned = JSON.parse(
    sanitizeRuntimeJson(
      Buffer.from(
        JSON.stringify({
          stageId: "classroom-a",
          apiKey: "must-not-leave-browser",
          config: {
            baseUrl: "https://attacker.invalid",
            agentIds: ["teacher"],
          },
        }),
      ),
      "classroom-a",
    ).toString("utf8"),
  );
  assert.deepEqual(cleaned, {
    stageId: "classroom-a",
    config: { agentIds: ["teacher"] },
  });
  assert.throws(
    () =>
      sanitizeRuntimeJson(Buffer.from(JSON.stringify({ stageId: "classroom-b" })), "classroom-a"),
    /cross-classroom/,
  );
});

test("authorized chat SSE is streamed through the gateway", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  const upstream = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      assert.equal(request.url, "/api/chat");
      assert.equal(body.stageId, "classroom-a");
      assert.equal(body.apiKey, undefined);
      assert.equal(request.headers["x-mira-runtime-session"], "rs1");
      assert.equal(request.headers["x-mira-learning-session"], "ls1");
      assert.equal(request.headers["x-mira-runtime-classroom-id"], "classroom-a");
      assert.equal(request.headers["x-mira-runtime-purpose"], undefined);
      assert.equal(request.headers["x-mira-verification-challenge"], undefined);
      response.writeHead(200, { "content-type": "text/event-stream" });
      response.write('data: {"type":"text_delta","data":"你好"}\n\n');
      response.end();
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const result = await fetch(`${gateway}/api/chat`, {
    method: "POST",
    headers: {
      cookie: "mira_openmaic_runtime=omr_good",
      "content-type": "application/json",
      "x-mira-runtime-session": "attacker-session",
      "x-mira-learning-session": "attacker-learning-session",
      "x-mira-runtime-classroom-id": "attacker-classroom",
      "x-mira-runtime-purpose": "conversation_probe",
      "x-mira-verification-challenge": "attacker-challenge",
    },
    body: JSON.stringify({ stageId: "classroom-a", apiKey: "secret" }),
  });
  assert.equal(result.status, 200);
  assert.match(await result.text(), /text_delta/);
});

test("upstream body timeout closes only the failed stream and keeps gateway serving", { timeout: 5_000 }, async () => {
  const backend = await listen(http.createServer(async (request, response) => {
    const body = await jsonBody(request);
    assert.ok(request.url.endsWith("/validate"));
    assert.equal(body.runtimeToken, "omr_stream_test");
    reply(response, { ok: true, runtimeSessionId: "rs-stream", learningSessionId: "ls-stream",
      classroomId: "classroom-a", expiresAt: Date.now() + 60_000 });
  }));
  let resolveUpstreamClose;
  const upstreamClosed = new Promise((resolve) => { resolveUpstreamClose = resolve; });
  let interrupted = false;
  const upstreamPaths = [];
  const upstream = await listen(http.createServer((request, response) => {
    upstreamPaths.push(request.url);
    response.writeHead(200, { "content-type": "application/octet-stream" });
    if (request.url === "/images/stalled.bin") {
      response.on("close", () => {
        interrupted = !response.writableEnded;
        resolveUpstreamClose();
      });
      response.write("first-chunk");
      // Send real headers/body, then leave the body open until the gateway's
      // existing upstream timeout aborts it. No provider or real runtime used.
      return;
    }
    assert.equal(request.url, "/images/healthy.bin");
    response.end("complete-asset");
  }));
  const gateway = await listenGateway({ backend, upstream, upstreamTimeoutMs: 250 });
  const headers = { cookie: "mira_openmaic_runtime=omr_stream_test" };
  const response = await fetch(`${gateway}/images/stalled.bin`, {
    headers, signal: AbortSignal.timeout(3_000),
  });
  assert.equal(response.status, 200);
  const reader = response.body.getReader();
  const first = await reader.read();
  assert.equal(first.done, false);
  assert.equal(Buffer.from(first.value).toString(), "first-chunk");
  await assert.rejects(reader.read(), /terminated|other side closed/i);
  await upstreamClosed;
  assert.equal(interrupted, true);
  const health = await fetch(`${gateway}/health`);
  assert.equal(health.status, 200);
  assert.equal((await health.json()).ok, true);
  const next = await fetch(`${gateway}/images/healthy.bin`, { headers });
  assert.equal(next.status, 200);
  assert.equal(await next.text(), "complete-asset");
  assert.deepEqual(upstreamPaths, ["/images/stalled.bin", "/images/healthy.bin"]);
});

test("upstream socket truncation rejects its body without terminating the gateway", { timeout: 5_000 }, async () => {
  const backend = await listen(http.createServer(async (request, response) => {
    await jsonBody(request);
    reply(response, formalRuntime());
  }));
  let truncate;
  const firstChunk = Buffer.alloc(320_853, 42);
  const upstream = await listen(http.createServer((_request, response) => {
    response.writeHead(200, { "content-type": "application/octet-stream" });
    response.write(firstChunk);
    truncate = () => response.destroy();
  }));
  const gateway = await listenGateway({ backend, upstream });
  const response = await fetch(`${gateway}/images/truncated.bin`, {
    headers: { cookie: "mira_openmaic_runtime=omr_good" },
    signal: AbortSignal.timeout(3_000),
  });
  assert.equal(response.status, 200);
  const reader = response.body.getReader();
  let bytes = 0;
  while (bytes < firstChunk.length) {
    const part = await reader.read();
    assert.equal(part.done, false);
    bytes += part.value.length;
  }
  truncate();
  await assert.rejects(reader.read(), /terminated|other side closed/i);
  assert.equal(bytes, firstChunk.length);
  const health = await fetch(`${gateway}/health`);
  assert.equal(health.status, 200);
  assert.equal((await health.json()).ok, true);
});

test("client disconnect cancels the upstream body and leaves the gateway healthy", { timeout: 5_000 }, async () => {
  const backend = await listen(http.createServer(async (request, response) => {
    await jsonBody(request);
    reply(response, formalRuntime());
  }));
  let upstreamCancelled;
  const closed = new Promise(resolve => { upstreamCancelled = resolve; });
  const upstream = await listen(http.createServer((_request, response) => {
    response.writeHead(200, { "content-type": "application/octet-stream" });
    response.write("first");
    const timer = setInterval(() => response.write(Buffer.alloc(65_536, 42)), 10);
    response.on("close", () => {
      clearInterval(timer);
      upstreamCancelled(!response.writableEnded);
    });
  }));
  const gateway = await listenGateway({ backend, upstream, upstreamTimeoutMs: 20_000 });
  await new Promise((resolve, reject) => {
    const request = http.get(`${gateway}/images/client-cancel.bin`, {
      headers: { cookie: "mira_openmaic_runtime=omr_good" },
    }, response => {
      assert.equal(response.statusCode, 200);
      response.once("data", () => { response.destroy(); resolve(); });
      response.on("error", reject);
    });
    request.on("error", reject);
  });
  assert.equal(await closed, true);
  const health = await fetch(`${gateway}/health`);
  assert.equal(health.status, 200);
  assert.equal((await health.json()).ok, true);
});

test("buffered classroom truncation fails closed and does not leave a Readable error", { timeout: 5_000 }, async () => {
  let manifestCalls = 0;
  const backend = await listen(http.createServer(async (request, response) => {
    await jsonBody(request);
    if (request.url.endsWith("/audio-manifest")) manifestCalls += 1;
    reply(response, formalRuntime());
  }));
  const upstream = await listen(http.createServer((_request, response) => {
    response.writeHead(200, { "content-type": "application/json" });
    response.write('{"success":true,"classroom":');
    setTimeout(() => response.destroy(), 30);
  }));
  const gateway = await listenGateway({ backend, upstream });
  const response = await fetch(`${gateway}/api/classroom?id=classroom-a`, {
    headers: { cookie: "mira_openmaic_runtime=omr_good" },
    signal: AbortSignal.timeout(3_000),
  });
  assert.equal(response.status, 502);
  assert.equal((await response.json()).error, "runtime_gateway_failed");
  assert.equal(manifestCalls, 0);
  assert.equal((await fetch(`${gateway}/health`)).status, 200);
});

test("buffered classroom size rejection cancels its unfinished upstream", { timeout: 5_000 }, async () => {
  const backend = await listen(http.createServer(async (request, response) => {
    await jsonBody(request);
    reply(response, formalRuntime());
  }));
  let upstreamCancelled;
  const closed = new Promise(resolve => { upstreamCancelled = resolve; });
  const upstream = await listen(http.createServer((_request, response) => {
    response.writeHead(200, { "content-type": "application/json" });
    response.write(" ".repeat(2048));
    response.on("close", () => upstreamCancelled(!response.writableEnded));
  }));
  const gateway = await listenGateway({ backend, upstream, maxBodyBytes: 1024 });
  const response = await fetch(`${gateway}/api/classroom?id=classroom-a`, {
    headers: { cookie: "mira_openmaic_runtime=omr_good" },
    signal: AbortSignal.timeout(3_000),
  });
  assert.equal(response.status, 502);
  assert.equal((await response.json()).error, "openmaic_runtime_audio_binding_invalid");
  assert.equal(await closed, true);
  assert.equal((await fetch(`${gateway}/health`)).status, 200);
});

test("student requests cannot choose a model, provider, key or endpoint", async () => {
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url.endsWith("/validate") && body.runtimeToken === "omr_good") {
        return reply(response, {
          ok: true,
          runtimeSessionId: "rs1",
          learningSessionId: "ls1",
          classroomId: "classroom-a",
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(401, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "invalid" }));
    }),
  );
  const seen = [];
  const upstream = await listen(
    http.createServer(async (request, response) => {
      seen.push({ url: request.url, headers: request.headers, body: await jsonBody(request) });
      reply(response, { success: true });
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const cookie = "mira_openmaic_runtime=omr_good";

  const graded = await fetch(`${gateway}/api/quiz-grade`, {
    method: "POST",
    headers: {
      cookie,
      "content-type": "application/json",
      "x-model": "openai:attacker-model",
      "x-api-key": "attacker-key",
      "x-base-url": "https://attacker.invalid/v1",
      "x-provider-type": "openai",
    },
    body: JSON.stringify({ question: "1+1", userAnswer: "2", points: 1 }),
  });
  assert.equal(graded.status, 200);

  // The native route parses JSON whatever content type the caller declares.
  const undeclared = { cookie, "content-type": "text/plain" };
  const chat = await fetch(`${gateway}/api/chat`, {
    method: "POST",
    headers: undeclared,
    body: ` ${JSON.stringify({
      stageId: "classroom-a",
      apiKey: "attacker-key",
      baseUrl: "https://attacker.invalid/v1",
    })}`,
  });
  assert.equal(chat.status, 200);
  const crossClassroom = await fetch(`${gateway}/api/chat`, {
    method: "POST",
    headers: undeclared,
    body: JSON.stringify({ stageId: "classroom-b" }),
  });
  assert.equal(crossClassroom.status, 403);

  assert.deepEqual(seen.map((request) => request.url), ["/api/quiz-grade", "/api/chat"]);
  for (const header of ["x-model", "x-api-key", "x-base-url", "x-provider-type"]) {
    assert.equal(seen[0].headers[header], undefined);
  }
  assert.deepEqual(seen[0].body, { question: "1+1", userAnswer: "2", points: 1 });
  assert.deepEqual(seen[1].body, { stageId: "classroom-a" });
});

test("conversation probe is cookie-authenticated, scope-bound, and streams chat plus multipart ASR", async () => {
  const challenge = "ompc_abcdefghijklmnopqrstuvwxyz012345";
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url === "/internal/learning/openmaic/runtime/probe/exchange") {
        assert.equal(body.ticket, "ompt_abcdefghijklmnopqrstuvwxyz012345");
        return reply(response, {
          ok: true,
          purpose: "conversation_probe",
          runtimeToken: "ompr_runtime-token-abcdefghijklmnopqrstuvwxyz",
          runtimeSessionId: "probe-session-a",
          classroomId: "classroom-a",
          challenge,
          expiresAt: Date.now() + 60_000,
        });
      }
      if (request.url === "/internal/learning/openmaic/runtime/probe/validate") {
        assert.equal(body.runtimeToken, "ompr_runtime-token-abcdefghijklmnopqrstuvwxyz");
        return reply(response, {
          ok: true,
          purpose: "conversation_probe",
          runtimeSessionId: "probe-session-a",
          learningSessionId: "probe-learning-session-a",
          classroomId: "classroom-a",
          challenge,
          expiresAt: Date.now() + 60_000,
        });
      }
      response.writeHead(404).end();
    }),
  );
  const seen = [];
  const upstream = await listen(
    http.createServer(async (request, response) => {
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      seen.push({
        url: request.url,
        headers: request.headers,
        body: Buffer.concat(chunks),
      });
      if (request.url === "/api/chat") {
        response.writeHead(200, { "content-type": "text/event-stream" });
        response.end(
          `event: mira-verification\ndata: ${JSON.stringify({ challenge, route: "text-chat" })}\n\n`,
        );
        return;
      }
      reply(response, {
        success: true,
        proof: { challenge, route: "transcription" },
      });
    }),
  );
  const gateway = await listenGateway({ backend, upstream });

  const unauthenticated = await fetch(`${gateway}/api/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ stageId: "classroom-a" }),
  });
  assert.equal(unauthenticated.status, 401);

  const exchange = await fetch(
    `${gateway}/mira/probe?ticket=ompt_abcdefghijklmnopqrstuvwxyz012345`,
    {
      redirect: "manual",
    },
  );
  assert.equal(exchange.status, 204);
  const cookie = exchange.headers.get("set-cookie").split(";", 1)[0];
  assert.match(exchange.headers.get("set-cookie"), /HttpOnly/);

  const crossClassroom = await fetch(`${gateway}/api/chat`, {
    method: "POST",
    headers: { cookie, "content-type": "application/json" },
    body: JSON.stringify({ stageId: "classroom-b" }),
  });
  assert.equal(crossClassroom.status, 403);
  assert.equal(seen.length, 0);

  const missingStage = await fetch(`${gateway}/api/chat`, {
    method: "POST",
    headers: { cookie, "content-type": "application/json" },
    body: JSON.stringify({ message: "probe" }),
  });
  assert.equal(missingStage.status, 403);
  assert.equal(seen.length, 0);

  const chat = await fetch(`${gateway}/api/chat`, {
    method: "POST",
    headers: {
      cookie,
      "content-type": "application/json",
      "x-mira-runtime-purpose": "attacker-purpose",
      "x-mira-verification-challenge": "attacker-challenge",
      "x-mira-runtime-classroom-id": "attacker-classroom",
    },
    body: JSON.stringify({
      stageId: "classroom-a",
      apiKey: "must-be-scrubbed",
    }),
  });
  assert.equal(chat.status, 200);
  assert.match(await chat.text(), /mira-verification/);

  const form = new FormData();
  form.set("audio", new File(["silent-audio"], "probe.webm", { type: "audio/webm" }));
  form.set("language", "zh");
  const transcription = await fetch(`${gateway}/api/transcription`, {
    method: "POST",
    headers: { cookie },
    body: form,
  });
  assert.equal(transcription.status, 200);
  assert.equal((await transcription.json()).proof.route, "transcription");

  const blockedDocument = await fetch(`${gateway}/classroom/classroom-a?mira=1`, {
    headers: { cookie },
  });
  assert.equal(blockedDocument.status, 403);

  assert.equal(seen.length, 2);
  for (const request of seen) {
    assert.equal(request.headers["x-mira-runtime-session"], "probe-session-a");
    assert.equal(request.headers["x-mira-runtime-purpose"], "conversation_probe");
    assert.equal(request.headers["x-mira-verification-challenge"], challenge);
    assert.equal(request.headers["x-mira-runtime-classroom-id"], "classroom-a");
  }
  assert.doesNotMatch(seen[0].body.toString("utf8"), /must-be-scrubbed/);
  assert.match(seen[1].headers["content-type"], /multipart\/form-data; boundary=/);
  assert.match(seen[1].body.toString("utf8"), /silent-audio/);
});

test("formal classroom JSON is assembled with session-bound audio and same-origin WAV delivery", async () => {
  const wav = Buffer.alloc(64);
  wav.write("RIFF", 0, "ascii");
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write("WAVE", 8, "ascii");
  const digest = createHash("sha256").update(wav).digest("hex");
  const manifest = formalAudioManifest(digest, wav.length);
  let manifestCalls = 0;
  let audioCalls = 0;
  const backend = await listen(
    http.createServer(async (request, response) => {
      const body = await jsonBody(request);
      if (request.url === "/internal/learning/openmaic/runtime/validate") {
        if (body.runtimeToken !== "omr_good") {
          response.writeHead(401, { "content-type": "application/json" });
          response.end(JSON.stringify({ ok: false, error: "invalid" }));
          return;
        }
        return reply(response, formalRuntime());
      }
      assert.equal(request.headers["x-mira-internal-token"], "test-internal-token");
      assert.equal(request.headers["x-mira-internal-source"], "openmaic-runtime-gateway");
      assert.equal(request.headers["x-mira-runtime-session"], "runtime-session-a");
      assert.equal(request.headers["x-mira-learning-session"], "learning-session-a");
      assert.equal(request.headers["x-mira-runtime-classroom-id"], "classroom-a");
      assert.equal(request.headers.cookie, undefined);
      assert.equal(request.headers.authorization, undefined);
      if (request.url === "/internal/learning/openmaic/runtime/audio-manifest") {
        manifestCalls += 1;
        return reply(response, {
          ...manifest,
          internal: { mustNotLeak: true },
        });
      }
      if (request.url === "/internal/learning/openmaic/runtime/audio/formal-audio-0") {
        audioCalls += 1;
        response.writeHead(200, {
          "content-type": "audio/wav",
          "content-length": wav.length,
          "x-mira-audio-sha256": digest,
        });
        response.end(wav);
        return;
      }
      response.writeHead(404, { "content-type": "application/json" });
      response.end(JSON.stringify({ ok: false, error: "not_found" }));
    }),
  );
  const upstream = await listen(
    http.createServer((request, response) => {
      assert.equal(request.url, "/api/classroom?id=classroom-a");
      assert.equal(request.headers["x-mira-runtime-session"], "runtime-session-a");
      assert.equal(request.headers["x-mira-learning-session"], "learning-session-a");
      assert.equal(request.headers["x-mira-runtime-classroom-id"], "classroom-a");
      assert.notEqual(request.headers["x-mira-runtime-session"], "forged-session");
      reply(response, { success: true, classroom: formalClassroom() });
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const cookie = "mira_openmaic_runtime=omr_good";

  const classroomResponse = await fetch(`${gateway}/api/classroom?id=classroom-a`, {
    headers: { cookie, "x-mira-runtime-session": "forged-session" },
  });
  assert.equal(classroomResponse.status, 200);
  const classroomPayload = await classroomResponse.json();
  assert.equal(classroomPayload.internal, undefined);
  const speech = classroomPayload.classroom.scenes[0].actions[0];
  assert.deepEqual(speech.audioMetadata, {
    schemaVersion: "mira.openmaic.speech-audio.v1",
    providerId: "qwen-tts",
    modelId: "qwen3-tts-flash",
    voiceId: "Ethan",
    fallbackUsed: false,
  });
  assert.equal(speech.audioId, "formal-audio-0");
  assert.equal(speech.audioUrl, "/mira/runtime-audio/formal-audio-0");
  assert.equal(manifestCalls, 1);

  const audioResponse = await fetch(`${gateway}${speech.audioUrl}`, {
    headers: { cookie, "x-mira-runtime-session": "forged-session" },
  });
  assert.equal(audioResponse.status, 200);
  assert.equal(audioResponse.headers.get("content-type"), "audio/wav");
  assert.equal(audioResponse.headers.get("cache-control"), "private, no-store");
  assert.deepEqual(Buffer.from(await audioResponse.arrayBuffer()), wav);
  assert.equal(audioCalls, 1);

  assert.equal((await fetch(`${gateway}${speech.audioUrl}`)).status, 401);
  assert.equal(
    (
      await fetch(`${gateway}/mira/runtime-audio/not-this-classroom`, {
        headers: { cookie },
      })
    ).status,
    404,
  );
  assert.equal(
    (
      await fetch(`${gateway}/mira/runtime-audio/%2e%2e%2fsecret.wav`, {
        headers: { cookie },
      })
    ).status,
    403,
  );
  assert.equal(
    (
      await fetch(`${gateway}/api/classroom?id=classroom-b`, {
        headers: { cookie },
      })
    ).status,
    401, // No credential scoped to classroom-b; reject before looking up its content.
  );
  assert.equal(
    (
      await fetch(`${gateway}${speech.audioUrl}`, {
        headers: { cookie: "mira_openmaic_runtime=omr_wrong" },
      })
    ).status,
    401,
  );
});

test("formal audio assembly fails closed for partial, duplicate, or conflicting bindings", () => {
  const hash = "a".repeat(64);
  const runtime = formalRuntime();
  const classroom = { success: true, classroom: formalClassroom() };
  const manifest = formalAudioManifest(hash, 64);
  // Python json.dumps(..., sort_keys=True, separators=(",", ":"),
  // ensure_ascii=False) over the same {stage, scenes} authority.
  assert.equal(
    manifest.classroomContentSha256,
    "17ae050d637aa618cd525b2fe254af07c00e1c0b19165a31d247afba6e0461f3",
  );
  const assembled = injectRuntimeAudioBindings(
    Buffer.from(JSON.stringify(classroom)),
    runtime,
    manifest,
  );
  assert.equal(JSON.parse(assembled).classroom.scenes[9].actions[0].audioId, "formal-audio-9");

  for (const invalid of [
    { ...manifest, speechActionCount: 9, assets: manifest.assets.slice(0, 9) },
    {
      ...manifest,
      assets: [...manifest.assets.slice(0, 9), manifest.assets[0]],
    },
  ]) {
    assert.throws(
      () => injectRuntimeAudioBindings(Buffer.from(JSON.stringify(classroom)), runtime, invalid),
      (error) => error?.payload?.error === "openmaic_runtime_audio_binding_invalid",
    );
  }
  const conflicting = formalClassroom();
  conflicting.scenes[0].actions[0].audioId = "other-audio";
  const conflictingManifest = formalAudioManifest(hash, 64, conflicting);
  assert.throws(
    () =>
      injectRuntimeAudioBindings(
        Buffer.from(JSON.stringify({ success: true, classroom: conflicting })),
        runtime,
        conflictingManifest,
      ),
    (error) =>
      error?.statusCode === 502 &&
      error?.payload?.error === "openmaic_runtime_audio_binding_invalid",
  );
});

test("formal audio assembly binds every speech in scene/action order for an adaptive classroom", () => {
  const runtime = formalRuntime();
  const classroom = formalClassroom(7);
  classroom.scenes[0].actions.push({
    id: "speech-extra",
    type: "speech",
    text: "extra focused explanation",
  });
  const manifest = formalAudioManifest("a".repeat(64), 64, classroom);
  const assembled = injectRuntimeAudioBindings(
    Buffer.from(JSON.stringify({ success: true, classroom })),
    runtime,
    manifest,
  );
  const parsed = JSON.parse(assembled);
  assert.equal(parsed.classroom.scenes.length, 7);
  assert.equal(manifest.speechActionCount, 8);
  assert.equal(parsed.classroom.scenes[0].actions[0].audioId, "formal-audio-0");
  assert.equal(parsed.classroom.scenes[0].actions[1].audioId, "formal-audio-1");
  assert.equal(parsed.classroom.scenes[6].actions[0].audioId, "formal-audio-7");

  const missingSpeech = formalClassroom(7);
  missingSpeech.scenes[1].actions = [];
  const missingSpeechManifest = formalAudioManifest("a".repeat(64), 64, missingSpeech);
  assert.throws(
    () =>
      injectRuntimeAudioBindings(
        Buffer.from(JSON.stringify({ success: true, classroom: missingSpeech })),
        runtime,
        missingSpeechManifest,
      ),
    (error) => error?.payload?.error === "openmaic_runtime_audio_binding_invalid",
  );

  const overfullScene = formalClassroom(1);
  overfullScene.scenes[0].actions = Array.from({ length: 21 }, (_, index) => ({
    id: `speech-overfull-${index}`,
    type: "speech",
    text: `explanation ${index}`,
  }));
  assert.throws(
    () =>
      injectRuntimeAudioBindings(
        Buffer.from(JSON.stringify({ success: true, classroom: overfullScene })),
        runtime,
        formalAudioManifest("a".repeat(64), 64, overfullScene),
      ),
    (error) => error?.payload?.error === "openmaic_runtime_audio_binding_invalid",
  );

  const tooManyOverall = formalClassroom(13);
  for (const [sceneIndex, scene] of tooManyOverall.scenes.entries()) {
    scene.actions = Array.from({ length: 20 }, (_, actionIndex) => ({
      id: `speech-total-${sceneIndex}-${actionIndex}`,
      type: "speech",
      text: `explanation ${sceneIndex}-${actionIndex}`,
    }));
  }
  assert.throws(
    () =>
      injectRuntimeAudioBindings(
        Buffer.from(JSON.stringify({ success: true, classroom: tooManyOverall })),
        runtime,
        formalAudioManifest("a".repeat(64), 64, tooManyOverall),
      ),
    (error) => error?.payload?.error === "openmaic_runtime_audio_binding_invalid",
  );
});

test("formal audio assembly rejects same-ID classroom content tampering", () => {
  const authoritative = formalClassroom();
  const manifest = formalAudioManifest("a".repeat(64), 64, authoritative);
  const cases = [
    [
      "stage",
      (classroom) => {
        classroom.stage.title = "tampered stage";
      },
    ],
    [
      "speech text",
      (classroom) => {
        classroom.scenes[0].actions[0].text = "tampered lesson";
      },
    ],
    [
      "quiz",
      (classroom) => {
        classroom.scenes[1].content.quiz.prompt = "tampered quiz";
      },
    ],
  ];
  for (const [label, mutate] of cases) {
    const classroom = structuredClone(authoritative);
    mutate(classroom);
    assert.throws(
      () =>
        injectRuntimeAudioBindings(
          Buffer.from(JSON.stringify({ success: true, classroom })),
          formalRuntime(),
          manifest,
        ),
      (error) =>
        error?.statusCode === 502 &&
        error?.payload?.error === "openmaic_runtime_audio_binding_invalid",
      label,
    );
  }
});

test("classroom assembly fails closed on non-JSON upstream and manifest backend failure", async () => {
  let mode = "non-json";
  const backend = await listen(
    http.createServer(async (request, response) => {
      await jsonBody(request);
      if (request.url === "/internal/learning/openmaic/runtime/validate") {
        return reply(response, formalRuntime());
      }
      if (request.url === "/internal/learning/openmaic/runtime/audio-manifest") {
        response.writeHead(503, { "content-type": "application/json" });
        response.end(JSON.stringify({ ok: false, error: "audio_not_ready" }));
        return;
      }
      response.writeHead(404).end();
    }),
  );
  const upstream = await listen(
    http.createServer((_request, response) => {
      if (mode === "non-json") {
        response.writeHead(200, { "content-type": "text/html" });
        response.end("not classroom JSON");
        return;
      }
      reply(response, { success: true, classroom: formalClassroom() });
    }),
  );
  const gateway = await listenGateway({ backend, upstream });
  const options = { headers: { cookie: "mira_openmaic_runtime=omr_good" } };
  const nonJson = await fetch(`${gateway}/api/classroom?id=classroom-a`, options);
  assert.equal(nonJson.status, 502);
  assert.equal((await nonJson.json()).error, "openmaic_runtime_audio_binding_invalid");

  mode = "backend-failure";
  const backendFailure = await fetch(`${gateway}/api/classroom?id=classroom-a`, options);
  assert.equal(backendFailure.status, 503);
  assert.equal((await backendFailure.json()).error, "audio_not_ready");
});

function formalRuntime() {
  return {
    ok: true,
    runtimeSessionId: "runtime-session-a",
    learningSessionId: "learning-session-a",
    classroomId: "classroom-a",
    expiresAt: Date.now() + 60_000,
  };
}

function formalClassroom(sceneCount = 10) {
  return {
    id: "classroom-a",
    stage: { id: "stage-a", title: "authoritative stage" },
    scenes: Array.from({ length: sceneCount }, (_, index) => ({
      id: `scene-${index}`,
      actions: [{ id: `speech-${index}`, type: "speech", text: `lesson ${index}` }],
      content: {
        quiz: { id: `quiz-${index}`, prompt: `question ${index}` },
      },
    })),
  };
}

function formalAudioManifest(contentHash, byteSize, classroom = formalClassroom()) {
  const speechActions = classroom.scenes.flatMap((scene) =>
    scene.actions.filter((action) => action.type === "speech").map((action) => ({ scene, action })),
  );
  return {
    ok: true,
    schemaVersion: "mira.openmaic.runtime-audio-manifest.v1",
    classroomId: "classroom-a",
    classroomContentSha256: formalClassroomContentSha256(classroom),
    speechActionCount: speechActions.length,
    assets: speechActions.map(({ scene, action }, index) => ({
      sceneId: scene.id,
      actionId: action.id,
      audioId: `formal-audio-${index}`,
      deliveryPath: `/mira/runtime-audio/formal-audio-${index}`,
      contentHash,
      mimeType: "audio/wav",
      byteSize,
      durationMs: 1_000,
      audioMetadata: {
        schemaVersion: "mira.openmaic.speech-audio.v1",
        providerId: "qwen-tts",
        modelId: "qwen3-tts-flash",
        voiceId: "Ethan",
        fallbackUsed: false,
      },
    })),
  };
}

function formalClassroomContentSha256(classroom) {
  const canonical = canonicalJsonForHash({
    stage: classroom.stage,
    scenes: classroom.scenes,
  });
  return createHash("sha256").update(canonical, "utf8").digest("hex");
}

function canonicalJsonForHash(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJsonForHash).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJsonForHash(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

async function listenGateway({ backend, upstream, ...overrides }) {
  const server = createGateway({
    backendUrl: backend,
    upstreamUrl: upstream,
    publicOrigin: "http://runtime.test",
    studentWebOrigin: "http://student.test",
    internalToken: "test-internal-token",
    secureCookie: false,
    ...overrides,
  });
  servers.push(server);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return `http://127.0.0.1:${server.address().port}`;
}

async function listen(server) {
  servers.push(server);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return `http://127.0.0.1:${server.address().port}`;
}

function reply(response, payload) {
  response.writeHead(200, { "content-type": "application/json" });
  response.end(JSON.stringify(payload));
}

async function jsonBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
}


test("student interaction events bind exact fields and cannot claim grades or arbitrary operations", () => {
  const runtime = { runtimeSessionId: "runtime-1", learningSessionId: "learning-1", classroomId: "classroom-1" };
  const payload = { sceneIndex: 1, sceneId: "scene-1", objectiveIndex: 0, controlSelector: "#quantity",
    action: "range", value: "12", feedbackText: "一个十两个一，因为十个一是一个十" };
  const encode = value => Buffer.from(JSON.stringify({ schemaVersion: "mira.openmaic.student-runtime-event.v1",
    sequence: 1, type: "interaction_completed", payload: value }));
  assert.deepEqual(prepareRuntimeEvent(encode(payload), runtime).payload, payload);
  for (const change of [{objectiveIndex:true}, {objectiveIndex:30}, {action:"evaluate"},
    {controlSelector:"body *"}, {value:"x".repeat(501)}, {feedbackText:""}, {passed:true},
    {action:"click", value:"12"}]) assert.throws(() => prepareRuntimeEvent(encode({...payload,...change}), runtime));
  assert.equal(prepareRuntimeEvent(encode({...payload, objectiveIndex:29}), runtime).payload.objectiveIndex, 29);
});

test("new paid classrooms receive only backend-authorized budget headers and canonical teaching requests", async () => {
  let admission, nativeRequest;
  const binding = {schemaVersion:"mira.learning.paid-budget-binding.v1",authorizationId:"a".repeat(64),required:true};
  const backend = await listen(http.createServer(async (request,response) => {
    if (request.url.endsWith('/paid-call')) {
      admission = { body: await jsonBody(request), headers: request.headers };
      return reply(response,{ok:true,paidBudget:binding,request:{messages:[],canonical:true}});
    }
    reply(response,{...formalRuntime(),paidBudgets:{required_teaching:binding,optional_interaction:null}});
  }));
  const upstream = await listen(http.createServer(async (request,response) => {
    nativeRequest = {body:await jsonBody(request),headers:request.headers};reply(response,{ok:true});
  }));
  const gateway = await listenGateway({backend,upstream});
  const result = await fetch(`${gateway}/api/chat`, {method:'POST',headers:{
    cookie:'mira_openmaic_runtime=omr_good','content-type':'application/json',
    'x-mira-paid-budget-authorization':'forged','x-mira-internal-token':'forged',
  },body:JSON.stringify({paidBudget:binding,authorizationId:'forged',messages:[],miraScriptedAction:{sceneId:'scene-a',actionId:'discussion-a'}})});
  assert.equal(result.status,200);
  assert.equal(admission.body.path,'/api/chat');
  assert.equal(admission.body.request.paidBudget,undefined);
  assert.equal(admission.body.request.authorizationId,undefined);
  assert.equal(admission.headers['x-mira-internal-token'],'test-internal-token');
  assert.equal(nativeRequest.headers['x-mira-paid-budget-authorization'],binding.authorizationId);
  assert.equal(nativeRequest.headers['x-mira-paid-budget-required'],'1');
  assert.equal(nativeRequest.headers['x-mira-internal-token'],'test-internal-token');
  assert.deepEqual(nativeRequest.body,{messages:[],canonical:true});
});

test("new classroom unpaid interaction fails before any native request while old playback remains readable", async () => {
  let nativeCalls=0;
  const backend = await listen(http.createServer((request,response) => {
    if(request.url.endsWith('/paid-call'))return reply(response,{ok:true,paidBudget:null});
    reply(response,{...formalRuntime(),paidBudgets:{required_teaching:null,optional_interaction:null}});
  }));
  const upstream = await listen(http.createServer((_request,response) => {nativeCalls++;reply(response,{ok:true});}));
  const gateway = await listenGateway({backend,upstream});
  const response = await fetch(`${gateway}/api/chat`,{method:'POST',headers:{cookie:'mira_openmaic_runtime=omr_good','content-type':'application/json'},body:'{}'});
  assert.equal(response.status,503);assert.equal(nativeCalls,0);
  const asset=await fetch(`${gateway}/_next/static/chunk.js`,{headers:{cookie:'mira_openmaic_runtime=omr_good'}});
  assert.equal(asset.status,200);assert.equal(nativeCalls,1);
});
