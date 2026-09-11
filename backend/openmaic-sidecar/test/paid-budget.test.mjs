import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { createSingleDispatchAICall } from '../src/provider.mjs';
const binding={schemaVersion:'mira.learning.paid-budget-binding.v1',authorizationId:'a'.repeat(64),required:true};
const provider={name:'deepseek',model:'fake-model',baseUrl:'https://provider.invalid/v1',apiKeyEnv:'MIRA_BUDGET_TEST_KEY',timeoutMs:1000,maxTokens:100,temperature:0.2};
let requests, claimed, reject, lose;
beforeEach(()=>{
  requests=[];claimed=new Set();reject='';lose=false;
  process.env.MIRA_PAID_BUDGET_BINDING=JSON.stringify(binding);
  process.env.MIRA_PAID_BUDGET_BACKEND_URL='http://budget.invalid';
  process.env.MIRA_PAID_BUDGET_INTERNAL_TOKEN='synthetic-internal';
  process.env.MIRA_BUDGET_TEST_KEY='synthetic-provider';
});
afterEach(()=>{for(const key of ['MIRA_PAID_BUDGET_BINDING','MIRA_PAID_BUDGET_BACKEND_URL','MIRA_PAID_BUDGET_INTERNAL_TOKEN','MIRA_BUDGET_TEST_KEY'])delete process.env[key];});
async function fakeFetch(url,options){
 const parsed=new URL(url);const body=JSON.parse(options.body);const operation=parsed.hostname==='budget.invalid'?parsed.pathname.split('/').pop():'provider';
 requests.push({operation,body,headers:options.headers});
 if(operation===reject)return Response.json({ok:false},{status:429});
 if(operation==='context')return Response.json({ok:true,budget:{prices:{fake:{provider:'deepseek',model:'fake-model',allowedUnits:['calls','input_tokens','output_tokens'],perCallMax:{calls:1,input_tokens:10000,output_tokens:100}}}}});
 if(operation==='reserve')return Response.json({ok:true,budget:{reservationId:body.dispatchId}});
 if(operation==='dispatch'){const allowed=!claimed.has(body.reservationId);claimed.add(body.reservationId);return Response.json({ok:true,budget:{dispatchAllowed:allowed}});}
 if(operation==='provider'){
  if(lose)throw new Error('connection lost');
  return Response.json({id:'synthetic-provider-receipt',choices:[{message:{content:'{"answer":"hello"}'}}],usage:{prompt_tokens:12,completion_tokens:9}});
 }
 return Response.json({ok:true,budget:{state:operation==='settle'?'settled':'unknown'}});
}
function call(){return createSingleDispatchAICall(provider,{fetchImpl:fakeFetch,questionPhase:'outline',requestId:'phase-a'})('system','中文内容');}
test('direct provider receives no request until durable dispatch authorization; actual usage settles',async()=>{
 await call();assert.deepEqual(requests.map(r=>r.operation),['context','reserve','dispatch','provider','settle']);
 assert.deepEqual(requests.at(-1).body.actualUnits,{calls:1,input_tokens:12,output_tokens:9});
 assert.ok(requests[1].body.maxUnits.input_tokens>4096);
 assert.equal(requests[3].body.paidBudget,undefined);
});
test('a denied grant cannot contact the provider or be treated as a free call',async()=>{
 reject='reserve';await assert.rejects(call());assert.equal(requests.some(r=>r.operation==='provider'),false);
});
test('ambiguous provider results keep their full hold and duplicate dispatches cannot resend',async()=>{
 lose=true;await assert.rejects(call());assert.equal(requests.at(-1).operation,'unknown');
 lose=false;await assert.rejects(call());assert.equal(requests.filter(r=>r.operation==='provider').length,1);
 assert.equal(requests.some(r=>r.operation==='settle'),false);
});
test('native Runtime delegation propagates trusted headers and never double-reserves the model call',async()=>{
 let count=0;
 const native=()=>createSingleDispatchAICall({...provider,name:'openmaic_runtime',baseUrl:'http://127.0.0.1:3100'},{questionPhase:'outline',requestId:'phase-a',fetchImpl:async(url,options)=>{
  count++;assert.equal(new URL(url).pathname,'/api/mira/courseware-provider-call');
  assert.equal(options.headers['X-Mira-Paid-Budget-Required'],'1');
  assert.equal(options.headers['X-Mira-Paid-Budget-Authorization'],binding.authorizationId);
  assert.equal(JSON.parse(options.body).paidBudget,undefined);
  return Response.json({success:true,schemaVersion:'mira.openmaic.courseware-provider-call.v1',requestId:'phase-a',phase:'outline',content:'{}',providerRequestIdHash:'b'.repeat(64),inputTokens:12,outputTokens:9,billingEvidence:'reported'});
 }})('system','user');
 await native();assert.equal(count,1);assert.equal(requests.length,0);
});
