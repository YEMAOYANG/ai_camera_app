const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const adapter=fs.readFileSync(process.env.MIRA_MATH_ADAPTER_SOURCE||path.join(__dirname,'math-subtract-zero.js'),'utf8');
const bridge=fs.readFileSync(process.env.MIRA_CHECKPOINT_BRIDGE_SOURCE||path.join(__dirname,'../.runtime/OpenMAIC/lib/mira/activity-checkpoint-bridge.ts'),'utf8');
const m=bridge.match(/export const ACTIVITY_CHECKPOINT_SHIM = `([\s\S]*?)`;/);assert.ok(m);
const script=m[1].replace('${ACTIVITY_CHECKPOINT_MAX_BYTES}','65536').replace(/^<script[^>]*>\s*/,'').replace(/\s*<\/script>$/,'');
const hash='e3fa57882036c537fe11a8b2592dd77e78a183384cc944e7f30c29861e5736a6';
function harness(install=true){
  const handlers={},out=[],parent={};let restoreCalls=0,received=null;
  const shot={version:1,sceneId:'scene-p11',domainState:{story:{equation:{change:1,result:2,whole:3},remaining:[2,3],removed:[1],total:3},saved:{equation:{change:1,result:2,whole:3},remaining:[2,3],removed:[1],total:3},previousWorks:[],storyVersion:1},firstAttempt:null};
  const checkpoint={version:1,capture:()=>received??shot,restore:value=>{restoreCalls++;received=value;
    return JSON.stringify(value.domainState.story.equation)===JSON.stringify({whole:3,change:1,result:2})
      &&JSON.stringify(value.domainState.story)===JSON.stringify(value.domainState.saved);}};
  const window={parent,miraActivityCheckpoint:checkpoint,addEventListener:(type,fn)=>(handlers[type]??=[]).push(fn)};
  const document={readyState:'complete',hidden:false,body:{appendChild(){}},createElement:()=>({style:{},setAttribute(){}}),addEventListener(){}};
  const port={postMessage:value=>out.push(value),close(){}};
  vm.runInNewContext(install?adapter+'\n'+script:script,{window,document,queueMicrotask(){},setInterval(){}});
  for(const fn of handlers.message||[])fn({source:parent,data:{type:'mira:activity-checkpoint-connect'},ports:[port],stopImmediatePropagation(){}});
  return {shot,out,window,send:(sceneId,sha,extra={})=>port.onmessage({data:{type:'mira:checkpoint-restore',state:shot,active:true,sceneId,contentSha256:sha,classroomId:'tbpub_c52a83637037d27822e26450',releaseSha256:'41b056348d6eabfecb3f21b713ad2325ab31365b3360ff9b165e31ab426f91ba',...extra}}),
    calls:()=>restoreCalls,received:()=>received};
}
test('private checkpoint restore normalizes the SHA-bound saved world before authored restore',()=>{
  const f=harness();f.send('scene-p11',hash);
  assert.equal(f.out.at(-1).type,'mira:checkpoint-restored');assert.equal(f.calls(),1);
  assert.deepEqual(Object.keys(f.received().domainState.story.equation),['whole','change','result']);
  assert.deepEqual(Object.keys(f.shot.domainState.story.equation),['change','result','whole']);
});
test('wrong hash and missing normalizer retain the original rejecting restore behavior',()=>{
  for(const [install,sha] of [[true,'f'.repeat(64)],[false,hash]]){const f=harness(install);f.send('scene-p11',sha);
    assert.equal(f.out.at(-1).type,'mira:checkpoint-rejected');assert.equal(f.calls(),install?1:0);}
});
test('malformed story fails before the original checkpoint can be modified',()=>{
  const f=harness();f.shot.domainState.story.equation.extra=0;f.send('scene-p11',hash);
  assert.equal(f.out.at(-1).type,'mira:checkpoint-rejected');assert.equal(f.calls(),0);assert.equal(f.received(),null);
});

test('other pages or releases never invoke a forged same-name function',()=>{
  for(const [scene,sha,extra] of [
    ['scene-p10',hash,{}],['scene-p11','f'.repeat(64),{}],
    ['scene-p11',hash,{classroomId:'tbpub_other'}],['scene-p11',hash,{releaseSha256:'f'.repeat(64)}],
  ]){
    const f=harness(false);let called=0;f.window.prepareMathSubtractZeroCheckpoint=()=>{called++;throw Error('forged');};
    f.send(scene,sha,extra);assert.equal(called,0);assert.equal(f.calls(),1);
  }
});
