import assert from 'node:assert/strict';
import test from 'node:test';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

// Exercises the real private checkpoint shim. The override permits checking a
// staged patch in a disposable directory before the managed runtime is rebuilt.
const bridgePath=process.env.MIRA_CHECKPOINT_BRIDGE_SOURCE
  || new URL('../.runtime/OpenMAIC/lib/mira/activity-checkpoint-bridge.ts',import.meta.url);
const bridge=readFileSync(bridgePath,'utf8');
const match=bridge.match(/export const ACTIVITY_CHECKPOINT_SHIM = `([\s\S]*?)`;/);
assert.ok(match,'checkpoint shim is present');
const script=match[1].replace('${ACTIVITY_CHECKPOINT_MAX_BYTES}','65536').replace(/^<script[^>]*>\s*/,'').replace(/\s*<\/script>$/,'');

function harness({saved=true,guarded=true,mayResume=false,ready=true}={}) {
  const winHandlers={},docHandlers={},out=[],tasks=[],timers=new Map();
  let nextTimer=0;
  const add=(table,type,fn)=>(table[type]??=[]).push(fn);
  const emit=(table,type,event={})=>{for(const fn of table[type]||[]){fn(event);if(event.stopped)break;}};
  const parent={};let success=0,calls=0,allowed=ready;
  const api={version:1,capture:()=>({step:0}),restore:()=>true,
    ...(guarded?{beginRequiresSelectedSceneIntent:true}:{}),
    ...(mayResume?{beginMayResumeSelectedSceneIntent:true}:{}),
    begin(){calls++;if(!allowed)return false;success++;return true;}};
  const window={parent,miraActivityCheckpoint:api,addEventListener:(type,fn)=>add(winHandlers,type,fn)};
  const document={hidden:false,readyState:'complete',body:{appendChild(){}},
    createElement:()=>({style:{},setAttribute(){}}),addEventListener:(type,fn)=>add(docHandlers,type,fn)};
  const port={postMessage:data=>out.push(data),close(){}};
  vm.runInNewContext(script,{window,document,queueMicrotask:fn=>tasks.push(fn),setInterval() {},
    setTimeout:fn=>{const id=++nextTimer;timers.set(id,fn);return id;},clearTimeout:id=>timers.delete(id)});
  const windowMessage=data=>emit(winHandlers,'message',{source:parent,data,ports:[],stopImmediatePropagation(){this.stopped=true;}});
  emit(winHandlers,'message',{source:parent,data:{type:'mira:activity-checkpoint-connect'},ports:[port],stopImmediatePropagation(){this.stopped=true;}});
  const message=data=>port.onmessage({data});
  message({type:'mira:checkpoint-restore',state:saved?{step:0}:null,active:true});
  return {message,windowMessage,out,api,
    enable:()=>{allowed=true;emit(winHandlers,'mira-course-operation-ready');},
    input:()=>emit(docHandlers,'pointerdown',{isTrusted:true,preventDefault(){},stopImmediatePropagation(){this.stopped=true;}}),
    hide:()=>{document.hidden=true;},
    calls:()=>calls,success:()=>success,
    flush:()=>{while(tasks.length||timers.size){while(tasks.length)tasks.shift()();
      const [id,fn]=timers.entries().next().value??[];if(fn){timers.delete(id);fn();}}}};
}

test('a restored opt-in page stays silent until selected, visible and ready',()=>{
  const f=harness({mayResume:true,ready:false});
  f.windowMessage({type:'MIRA_NARRATION_VISIBILITY',visible:true});f.enable();
  assert.equal(f.calls(),0); // Ordinary refresh is silent.
  f.message({type:'mira:checkpoint-selected-intro',requested:true});
  f.flush();
  assert.equal(f.success(),1);assert.equal(f.calls(),1);
  f.enable();f.flush();assert.equal(f.success(),1);
  assert.equal(f.out.filter(item=>item.type==='mira:checkpoint-intro-consumed').length,1);
});
test('selected restored opening waits for visibility and operation authorization in either order',()=>{
  for(const order of ['ready-first','visible-first']){
    const f=harness({mayResume:true,ready:false});
    f.message({type:'mira:checkpoint-selected-intro',requested:true});
    if(order==='ready-first')f.enable();else f.windowMessage({type:'MIRA_NARRATION_VISIBILITY',visible:true});
    assert.equal(f.success(),0);
    if(order==='ready-first')f.windowMessage({type:'MIRA_NARRATION_VISIBILITY',visible:true});else f.enable();
    f.flush();
    assert.equal(f.success(),1);f.enable();assert.equal(f.success(),1);
  }
});
test('other restored pages, hidden pages, cancellation and real input never start',()=>{
  for(const mode of ['other','hidden','cancel','input','untrusted-port']){
    const f=harness({mayResume:mode!=='other'});
    if(mode==='untrusted-port')f.windowMessage({type:'mira:checkpoint-selected-intro',requested:true});
    else f.message({type:'mira:checkpoint-selected-intro',requested:true});
    if(mode==='hidden')f.hide();
    if(mode==='cancel')f.message({type:'mira:checkpoint-selected-intro',requested:false});
    if(mode==='input')f.input();
    f.windowMessage({type:'MIRA_NARRATION_VISIBILITY',visible:true});f.enable();f.flush();
    assert.equal(f.success(),0,mode);
  }
});
test('legacy fresh and selected fresh opening paths retain their previous behavior',()=>{
  const legacy=harness({saved:false,guarded:false});
  legacy.windowMessage({type:'MIRA_NARRATION_VISIBILITY',visible:true});legacy.flush();
  assert.equal(legacy.success(),1);
  const guarded=harness({saved:false});guarded.message({type:'mira:checkpoint-selected-intro',requested:true});
  guarded.windowMessage({type:'MIRA_NARRATION_VISIBILITY',visible:true});guarded.flush();assert.equal(guarded.success(),1);
});
