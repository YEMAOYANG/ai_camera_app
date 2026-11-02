import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
const {createMiraStudentRuntimeEventClient} = require('../.runtime/OpenMAIC/lib/mira/student-runtime-events.ts');
const {connectCourseOperationFrame} = require('../.runtime/OpenMAIC/lib/mira/course-operation-bridge.ts');
const digest = 'a'.repeat(64);
const saved = {total: 3, removed: [1], remaining: [2,3], equation: {whole: 3, change: 1, result: 2}};
const context = () => ({schemaVersion: 'mira.math-story-source.v1', sourceSceneId: 'scene-p11',
  available: true, sourceWorkSha256: digest, saved: structuredClone(saved)});
const status = (kind = 'math-subtract', ctx = context()) => ({ok: true,
  schemaVersion: 'mira.openmaic.student-runtime-event-receipt.v1', runtimeSessionId: 'test-runtime',
  lastSequence: 0, nextSequence: 1, completed: false, completionReady: false, answeredQuestionIds: [],
  courseInteractionState: {contractSha256: digest, scenes: {'scene-p12': {kind}},
    sourceContexts: {'scene-p12': ctx}}});
async function clientFor(value) {
  const client = createMiraStudentRuntimeEventClient({classroomId: 'source-test',
    storage: {getItem: () => null, setItem() {}, removeItem() {}},
    fetcher: async () => new Response(JSON.stringify(value), {headers: {'content-type': 'application/json'}})});
  await client.resume(); return client;
}
test('source comes from authenticated status, is contract-bound, and is cloned before sending', async () => {
  const client = await clientFor(status());
  const first = client.getCourseSceneSourceContext('scene-p12', digest);
  assert.deepEqual(first, context()); first.saved.total = 5;
  assert.equal(client.getCourseSceneSourceContext('scene-p12', digest).saved.total, 3);
  assert.throws(() => client.getCourseSceneSourceContext('scene-p12', 'b'.repeat(64)));
});
test('unavailable sources stay empty; wrong source page and fabricated extra fields fail closed', async () => {
  const missing = {...context(), available: false, sourceWorkSha256: null, saved: null};
  const client = await clientFor(status('math-subtract', missing));
  assert.deepEqual(client.getCourseSceneSourceContext('scene-p12', digest), missing);
  for (const invalid of [{...context(), sourceSceneId: 'scene-p13'}, {...context(), trusted: true},
    {...context(), available: false}, {...context(), sourceWorkSha256: 'client-claim'}]) {
    const bad = await clientFor(status('math-subtract', invalid));
    assert.throws(() => bad.getCourseSceneSourceContext('scene-p12', digest), /source is unavailable/);
  }
});
test('other course kinds keep their original path and do not acquire a story context', async () => {
  const client = await clientFor(status('math-split', {invalid: true}));
  assert.equal(client.getCourseSceneSourceContext('scene-p12', digest), null);
});
test('the private operation port carries the server source alongside the current page state', async () => {
  const client = await clientFor(status());
  let dispose, port;
  try {
    const restored = new Promise((resolve, reject) => {
      const frame = {addEventListener() {}, removeEventListener() {}, contentWindow: {
        postMessage(_data, _origin, ports) {
          port = ports[0]; port.onmessage = event => {
            if (event.data.type === 'mira:course-operation-restore') resolve(event.data);
          };
          port.postMessage({type: 'mira:course-operation-ready'});
        },
      }};
      dispose = connectCourseOperationFrame({frame, sceneId: 'scene-p12', sceneIndex: 11,
        contractSha256: digest, contentSha256: 'b'.repeat(64), events: client, active: () => true,
        onError: () => reject(new Error('restore failed'))});
    });
    const result = await restored;
    assert.deepEqual(result.serverState, {kind: 'math-subtract'});
    assert.deepEqual(result.sourceContext, context());
    assert.equal(result.contentSha256, 'b'.repeat(64));
  } finally {dispose?.(); port?.close();}
});
test('only new math kinds receive parent replay requests over the private port, after authorization', async () => {
  for (const kind of ['math-subtract','math-zero','math-split']) {
    let dispose, port, request;
    const messages=[];
    try {
      const authorized=new Promise((resolve,reject)=>{
        const frame={addEventListener(){},removeEventListener(){},contentWindow:{postMessage(_data,_origin,ports){
          port=ports[0];port.onmessage=event=>{
            messages.push(event.data.type);
            if(event.data.type==='mira:course-operation-restore')port.postMessage({type:'mira:course-operation-restored',matches:true});
            if(event.data.type==='mira:course-operation-authorized')setTimeout(resolve,5);
          };port.postMessage({type:'mira:course-operation-ready'});
        }}};
        dispose=connectCourseOperationFrame({frame,sceneId:'scene-p2',sceneIndex:1,contractSha256:digest,
          events:{resume:async()=>{},getCourseSceneState:()=>({kind}),getCourseSceneSourceContext:()=>null},
          active:()=>true,onError:()=>reject(new Error('bridge failed')),bindParentReplay:fn=>request=fn});
        assert.equal(request(),true); // An explicit request can arrive during restore.
      });
      await authorized;
      assert.equal(messages.includes('mira:course-operation-parent-replay'),kind!=='math-split');
      if(kind!=='math-split')assert.ok(messages.indexOf('mira:course-operation-parent-replay')>messages.indexOf('mira:course-operation-authorized'));
      dispose();dispose=null;assert.equal(request,null);
    }finally{dispose?.();port?.close();}
  }
});

const until=async predicate=>{for(let i=0;i<100;i++){if(predicate())return;await new Promise(resolve=>setTimeout(resolve,2));}throw new Error('message timeout');};
test('guarded math waits for the iframe to acknowledge authorization before enabling its controls',async()=>{
  let port,dispose,ready=0;const messages=[];
  try{
    const frame={addEventListener(){},removeEventListener(){},contentWindow:{postMessage(_d,_o,ps){
      port=ps[0];port.onmessage=e=>messages.push(e.data);port.postMessage({type:'mira:course-operation-ready'});
    }}};
    dispose=connectCourseOperationFrame({frame,sceneId:'scene-p1',sceneIndex:0,contractSha256:digest,
      events:{resume:async()=>{},getCourseSceneState:()=>({kind:'math-zero'}),getCourseSceneSourceContext:()=>null},
      active:()=>true,guardMathInteraction:true,onReady:()=>ready++,onError:()=>{throw Error('unexpected');}});
    await until(()=>messages.some(x=>x.type==='mira:course-operation-restore'));
    port.postMessage({type:'mira:course-operation-restored',matches:true});
    await until(()=>messages.some(x=>x.type==='mira:course-operation-authorized'));
    assert.equal(ready,0);port.postMessage({type:'mira:course-operation-authorization-ready'});
    await until(()=>ready===1);
  }finally{dispose?.();port?.close();}
});
test('a failed host fence refuses authorization instead of opening a stale page',async()=>{
  let port,dispose,errors=0,ready=0;const messages=[];
  try{
    const frame={addEventListener(){},removeEventListener(){},contentWindow:{postMessage(_d,_o,ps){
      port=ps[0];port.onmessage=e=>messages.push(e.data);port.postMessage({type:'mira:course-operation-ready'});
    }}};
    dispose=connectCourseOperationFrame({frame,sceneId:'scene-p1',sceneIndex:0,contractSha256:digest,
      events:{resume:async()=>{},getCourseSceneState:()=>({kind:'math-zero'}),getCourseSceneSourceContext:()=>null},
      active:()=>true,guardMathInteraction:true,canAuthorize:()=>false,onReady:()=>ready++,onError:()=>errors++});
    await until(()=>messages.some(x=>x.type==='mira:course-operation-restore'));
    port.postMessage({type:'mira:course-operation-restored',matches:true});
    await until(()=>errors===1);
    assert.equal(ready,0);assert.equal(messages.some(x=>x.type==='mira:course-operation-authorized'),false);
    await until(()=>messages.some(x=>x.type==='mira:course-operation-unavailable'));
  }finally{dispose?.();port?.close();}
});
test('an iframe operation failure informs the host and fences its controls',async()=>{
  let port,dispose,errors=0;const messages=[];
  try{
    const frame={addEventListener(){},removeEventListener(){},contentWindow:{postMessage(_d,_o,ps){
      port=ps[0];port.onmessage=e=>messages.push(e.data);port.postMessage({type:'mira:course-operation-ready'});
    }}};
    dispose=connectCourseOperationFrame({frame,sceneId:'scene-p1',sceneIndex:0,contractSha256:digest,
      events:{resume:async()=>{},getCourseSceneState:()=>({kind:'math-zero'}),getCourseSceneSourceContext:()=>null},
      active:()=>true,onError:()=>errors++});
    await until(()=>messages.some(x=>x.type==='mira:course-operation-restore'));
    port.postMessage({type:'mira:course-operation-restored',matches:true});
    await until(()=>messages.some(x=>x.type==='mira:course-operation-authorized'));
    port.postMessage({type:'mira:course-operation-client-error'});await until(()=>errors===1);
  }finally{dispose?.();port?.close();}
});
test('a recovery-locked page can reject a toolbar replay without credit or retrying it on reconnect',async()=>{
  const ports=[],messages=[],operations=[];let load,request,dispose,errors=0;
  const frame={addEventListener:(name,fn)=>{if(name==='load')load=fn;},removeEventListener(){},contentWindow:{postMessage(_d,_o,ps){
    const port=ps[0], index=ports.length;ports.push(port);messages.push([]);port.onmessage=e=>messages[index].push(e.data);
  }}};
  const events={resume:async()=>{},getCourseSceneState:()=>({kind:'math-zero'}),getCourseSceneSourceContext:()=>null,
    courseOperation:async input=>{operations.push(input);}};
  const authorize=async index=>{ports[index].postMessage({type:'mira:course-operation-ready'});
    await until(()=>messages[index].some(x=>x.type==='mira:course-operation-restore'));
    ports[index].postMessage({type:'mira:course-operation-restored',matches:true});
    await until(()=>messages[index].some(x=>x.type==='mira:course-operation-authorized'));};
  try{
    dispose=connectCourseOperationFrame({frame,sceneId:'scene-p1',sceneIndex:0,contractSha256:digest,events,
      active:()=>true,onError:()=>errors++,bindParentReplay:fn=>request=fn});
    await authorize(0);assert.equal(request(),true);
    await until(()=>messages[0].some(x=>x.type==='mira:course-operation-parent-replay'));
    const id=messages[0].find(x=>x.type==='mira:course-operation-parent-replay').requestId;
    ports[0].postMessage({type:'mira:course-operation-parent-replay-blocked',requestId:id});
    await new Promise(resolve=>setTimeout(resolve,10));
    load();await authorize(1);await new Promise(resolve=>setTimeout(resolve,10));
    assert.equal(messages[1].some(x=>x.type==='mira:course-operation-parent-replay'),false);
    assert.deepEqual(operations,[]);assert.equal(errors,0);
  }finally{dispose?.();ports.forEach(port=>port.close());}
});
test('a blocked reply never discards a replay that was already posted for acknowledgement',async()=>{
  const ports=[],messages=[],operations=[];let load,request,dispose,errors=0,resolveSave;
  const frame={addEventListener:(name,fn)=>{if(name==='load')load=fn;},removeEventListener(){},contentWindow:{postMessage(_d,_o,ps){
    const port=ps[0],index=ports.length;ports.push(port);messages.push([]);port.onmessage=e=>messages[index].push(e.data);
  }}};
  const events={resume:async()=>{},getCourseSceneState:()=>({kind:'math-zero'}),getCourseSceneSourceContext:()=>null,
    courseOperation:input=>{operations.push(input);return new Promise(resolve=>{resolveSave=resolve;});}};
  const authorize=async index=>{ports[index].postMessage({type:'mira:course-operation-ready'});
    await until(()=>messages[index].some(x=>x.type==='mira:course-operation-restore'));
    ports[index].postMessage({type:'mira:course-operation-restored',matches:true});
    await until(()=>messages[index].some(x=>x.type==='mira:course-operation-authorized'));};
  try{
    dispose=connectCourseOperationFrame({frame,sceneId:'scene-p1',sceneIndex:0,contractSha256:digest,events,
      active:()=>true,onError:()=>errors++,bindParentReplay:fn=>request=fn});
    await authorize(0);request();await until(()=>messages[0].some(x=>x.type==='mira:course-operation-parent-replay'));
    const id=messages[0].find(x=>x.type==='mira:course-operation-parent-replay').requestId;
    const work={removed:[],remaining:[1,2],answer:null};
    ports[0].postMessage({type:'mira:course-operation',operationId:id,operation:{name:'replay',work}});
    await until(()=>operations.length===1);
    ports[0].postMessage({type:'mira:course-operation-parent-replay-blocked',requestId:id});
    await until(()=>errors===1);load();await authorize(1);
    await until(()=>messages[1].some(x=>x.type==='mira:course-operation-parent-replay'));
    const retry=messages[1].find(x=>x.type==='mira:course-operation-parent-replay');
    assert.equal(retry.requestId,id);assert.deepEqual(retry.work,work);
  }finally{resolveSave?.();dispose?.();ports.forEach(port=>port.close());}
});
test('queued and posted replay requests survive reconnection with one stable id until server acknowledgement',async()=>{
  const ports=[],messages=[],operations=[],resolvers=[];let load,request,dispose,errors=0;
  const work={removed:[],remaining:[1,2,3,4,5],prediction:null};
  const frame={addEventListener:(name,fn)=>{if(name==='load')load=fn;},removeEventListener(){},contentWindow:{postMessage(_d,_o,ps){
    const port=ps[0];ports.push(port);messages.push([]);const index=ports.length-1;
    port.onmessage=e=>messages[index].push(e.data);
  }}};
  const events={resume:async()=>{},getCourseSceneState:()=>({kind:'math-subtract'}),getCourseSceneSourceContext:()=>null,
    courseOperation:input=>{operations.push(input);return new Promise(resolve=>resolvers.push(resolve));}};
  const authorize=async index=>{const port=ports[index];port.postMessage({type:'mira:course-operation-ready'});
    await until(()=>messages[index].some(x=>x.type==='mira:course-operation-restore'));
    port.postMessage({type:'mira:course-operation-restored',matches:true});
    await until(()=>messages[index].some(x=>x.type==='mira:course-operation-parent-replay'));
    return messages[index].find(x=>x.type==='mira:course-operation-parent-replay');};
  try{
    dispose=connectCourseOperationFrame({frame,sceneId:'scene-p1',sceneIndex:0,contractSha256:digest,events,
      active:()=>true,onError:()=>errors++,bindParentReplay:fn=>request=fn});
    assert.equal(request(),true);load(); // Not ready; the queued request survives.
    const first=await authorize(1);assert.match(first.requestId,/^[a-f0-9-]{36}$/);
    load();const second=await authorize(2);assert.equal(second.requestId,first.requestId); // Posted but not yet received by adapter.
    ports[2].postMessage({type:'mira:course-operation',operationId:second.requestId,operation:{name:'replay',work}});
    await until(()=>operations.length===1);load();
    const third=await authorize(3);assert.equal(third.requestId,first.requestId);assert.deepEqual(third.work,work);
    ports[3].postMessage({type:'mira:course-operation',operationId:third.requestId,operation:{name:'replay',work:third.work}});
    await until(()=>operations.length===2);assert.deepEqual(operations[0],operations[1]);
    resolvers.splice(0).forEach(resolve=>resolve());await until(()=>messages[3].some(x=>x.type==='mira:course-operation-ack'));
    load();ports[4].postMessage({type:'mira:course-operation-ready'});
    await until(()=>messages[4].some(x=>x.type==='mira:course-operation-restore'));
    ports[4].postMessage({type:'mira:course-operation-restored',matches:true});
    await until(()=>messages[4].some(x=>x.type==='mira:course-operation-authorized'));
    await new Promise(resolve=>setTimeout(resolve,5));assert.equal(messages[4].some(x=>x.type==='mira:course-operation-parent-replay'),false);
    assert.equal(errors,0);
  }finally{dispose?.();ports.forEach(port=>port.close());}
});

const {connectInteractiveAudioControls} = require('../.runtime/OpenMAIC/lib/mira/interactive-audio-controls.ts');
const {togglePageNarration,releasePageNarrationPause} = require('../.runtime/OpenMAIC/lib/mira/page-narration.ts');
test('trusted toolbar replay records a request without delaying audio; synthetic and lifecycle calls do not',()=>{
  const original=globalThis.window, handlers={},posts=[];
  globalThis.window={addEventListener:(name,fn)=>handlers[name]=fn,removeEventListener:name=>delete handlers[name]};
  releasePageNarrationPause();
  let count=0;
  const frame={addEventListener(){},removeEventListener(){},contentWindow:{postMessage:data=>posts.push(data)}};
  const dispose=connectInteractiveAudioControls({frame,active:()=>true,isBoundCue:id=>id==='task',
    onExplicitReplay:()=>{count++;return new Promise(()=>{});}});
  try{
    const channel=posts.at(-1).channel;
    const ended=()=>handlers.message({source:frame.contentWindow,data:{type:'MIRA_INTERACTIVE_AUDIO_STATE',channel,
      cueId:'task',status:'ended',hasReplay:true}});
    assert.equal(count,0);assert.equal(posts.filter(v=>v.command==='play').length,0);
    handlers.message({source:frame.contentWindow,data:{type:'MIRA_INTERACTIVE_AUDIO_STATE',channel,cueId:null,status:'idle',hasReplay:true}});
    togglePageNarration(undefined,{isTrusted:true});assert.equal(count,0); // Opening play has no previous cue to replay.
    ended();togglePageNarration(undefined,{isTrusted:false});assert.equal(count,0);
    ended();togglePageNarration();assert.equal(count,0);
    ended();togglePageNarration(undefined,{isTrusted:true});assert.equal(count,1);
    assert.equal(posts.filter(v=>v.command==='play').length,4); // No ACK or audio-completion wait.
    handlers.message({source:frame.contentWindow,data:{type:'MIRA_INTERACTIVE_AUDIO_STATE',channel,
      cueId:'task',status:'paused',hasReplay:true}}); // Failed playback changes no evidence claim.
    assert.equal(count,1);
  }finally{dispose();globalThis.window=original;releasePageNarrationPause();}
});
