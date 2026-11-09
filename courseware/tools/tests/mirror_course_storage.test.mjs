import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {Readable} from 'node:stream';
import {fileURLToPath} from 'node:url';

import {runMirror} from '../mirror_course_storage.mjs';

const etag=bytes=>'"'+crypto.createHash('md5').update(bytes).digest('hex')+'"';
const source={endpoint:'http://source.invalid:9000',bucket:'study',prefix:'mira-courseware/v1',region:'us-east-1',
  provider:'s3-compatible',addressingStyle:'path',accessKeyId:'source-id',secretAccessKey:'source-secret'};
const target={endpoint:'https://cos.ap-guangzhou.myqcloud.com',bucket:'study-1350855375',prefix:'mira-courseware/v1',region:'ap-guangzhou',
  provider:'tencent-cos',addressingStyle:'virtual',accessKeyId:'target-id',secretAccessKey:'target-secret'};

function clients(targetBytes,{bytes=Buffer.from('{"课程":"原稿"}')}={}){
  const key='课程/真实对象.json',sourceCalls=[],targetCalls=[];
  const sourceClient={async send(command){
    sourceCalls.push(command);const name=command.constructor.name,input=command.input;
    if(name==='HeadBucketCommand')return {};
    if(name==='ListObjectsV2Command')return {Contents:[{Key:key,Size:bytes.length,ETag:etag(bytes)}],IsTruncated:false};
    if(name==='HeadObjectCommand')return {ContentLength:bytes.length,ETag:etag(bytes)};
    if(name==='GetObjectCommand')return {ContentLength:bytes.length,ContentType:'application/json',ETag:etag(bytes),Body:Readable.from([bytes])};
    throw Error('unexpected source command '+name);
  }};
  let stored=targetBytes?Buffer.from(targetBytes):null,version=stored?'existing-version':null;
  const targetClient={async send(command){
    targetCalls.push(command);const name=command.constructor.name,input=command.input;
    if(name==='HeadBucketCommand')return {};
    if(name==='GetBucketVersioningCommand')return {Status:'Enabled'};
    if(name==='ListObjectsV2Command')return {Contents:stored?[{Key:key,Size:stored.length,ETag:etag(stored)}]:[],IsTruncated:false};
    if(name==='HeadObjectCommand'){
      if(!stored){const error=Error('missing');error.name='NotFound';error.$metadata={httpStatusCode:404};throw error;}
      return {ContentLength:stored.length,ETag:etag(stored),VersionId:version,ServerSideEncryption:'AES256'};
    }
    if(name==='PutObjectCommand'){
      if(Buffer.isBuffer(input.Body))stored=Buffer.from(input.Body);
      else{const chunks=[];for await(const chunk of input.Body)chunks.push(Buffer.from(chunk));stored=Buffer.concat(chunks);}
      version='new-version';
      return {ETag:etag(stored),VersionId:version,ServerSideEncryption:'AES256'};
    }
    if(name==='GetObjectCommand'){
      let body=stored,contentRange;
      if(input.Range){const [start,end]=input.Range.slice(6).split('-').map(Number);body=stored.subarray(start,end+1);contentRange=`bytes ${start}-${end}/${stored.length}`;}
      return {ContentLength:body.length,ContentRange:contentRange,ETag:etag(stored),VersionId:version,
        ServerSideEncryption:'AES256',Body:Readable.from([body])};
    }
    throw Error('unexpected target command '+name);
  }};
  return {key,bytes,sourceClient,targetClient,sourceCalls,targetCalls,getStored:()=>stored};
}

test('pilot mirrors one real key without overwrite or delete and verifies encryption, hash and range',async t=>{
  const directory=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'cos-mirror-test-')));t.after(()=>fs.rm(directory,{recursive:true,force:true}));
  const f=clients(),result=await runMirror({command:'pilot',concurrency:1,limit:1,'max-bytes':1024,state:directory},
    {source,target,sourceClient:f.sourceClient,targetClient:f.targetClient,state:directory});
  assert.equal(result.verifiedObjects,1);assert.equal(result.verifiedBytes,f.bytes.length);assert.deepEqual(f.getStored(),f.bytes);
  const put=f.targetCalls.find(call=>call.constructor.name==='PutObjectCommand').input;
  assert.equal(put.Key,f.key);assert.equal(put.IfNoneMatch,'*');assert.equal(put.ServerSideEncryption,'AES256');
  assert.equal(put.ContentMD5,Buffer.from(etag(f.bytes).replaceAll('"',''),'hex').toString('base64'));
  assert(f.targetCalls.some(call=>call.constructor.name==='GetObjectCommand'&&call.input.Range));
  assert(!f.sourceCalls.concat(f.targetCalls).some(call=>call.constructor.name.startsWith('Delete')));
  const journal=(await fs.readdir(directory)).find(name=>name.endsWith('.jsonl'));
  const records=(await fs.readFile(path.join(directory,journal),'utf8')).trim().split('\n').map(JSON.parse);
  assert.equal(records[0].status,'verified');assert.equal(records[0].rangeVerified,true);
  assert(!JSON.stringify(result).includes('target-secret'));
  const resumed=await runMirror({command:'mirror',concurrency:1,limit:1,'max-bytes':1024,state:directory},
    {source,target,sourceClient:f.sourceClient,targetClient:f.targetClient,state:directory});
  assert.equal(resumed.resumedObjects,1);
  assert.equal(f.targetCalls.filter(call=>call.constructor.name==='PutObjectCommand').length,1);
});

test('standard source MD5 lets COS prove a new object without a second full download',async t=>{
  const directory=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'cos-mirror-test-')));t.after(()=>fs.rm(directory,{recursive:true,force:true}));
  const f=clients(),result=await runMirror({command:'mirror',concurrency:1,limit:1,state:directory},
    {source,target,sourceClient:f.sourceClient,targetClient:f.targetClient,state:directory});
  assert.equal(result.verifiedObjects,1);
  assert.equal(f.targetCalls.filter(call=>call.constructor.name==='GetObjectCommand').length,0);
  const journal=(await fs.readdir(directory)).find(name=>name.endsWith('.jsonl'));
  const receipt=JSON.parse((await fs.readFile(path.join(directory,journal),'utf8')).split('\n')[0]);
  assert.equal(receipt.integrityCheck,'cos-content-md5+source-sha256');
});

test('a large mirror object is fully read from the source before its target upload starts',async t=>{
  const directory=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'cos-mirror-test-')));t.after(()=>fs.rm(directory,{recursive:true,force:true}));
  const bytes=Buffer.alloc(8*1024*1024+13,0x5a),f=clients(undefined,{bytes});
  const sourceSend=f.sourceClient.send.bind(f.sourceClient),targetSend=f.targetClient.send.bind(f.targetClient);
  let sourceRead=false,truncateSource=true;
  f.sourceClient.send=async command=>{
    const response=await sourceSend(command);
    if(command.constructor.name==='GetObjectCommand'){
      response.Body=Readable.from((async function*(){
        yield bytes.subarray(0,4*1024*1024);
        yield bytes.subarray(4*1024*1024,truncateSource?bytes.length-1:bytes.length);
        sourceRead=true;
      })());
    }
    return response;
  };
  f.targetClient.send=async command=>{
    if(command.constructor.name==='PutObjectCommand')assert.equal(sourceRead,true);
    return targetSend(command);
  };
  const options={command:'mirror',concurrency:1,state:directory};
  const dependencies={source,target,sourceClient:f.sourceClient,targetClient:f.targetClient};
  await assert.rejects(runMirror(options,dependencies),/incomplete/);
  assert(!f.targetCalls.some(call=>call.constructor.name==='PutObjectCommand'));
  sourceRead=false;truncateSource=false;
  const result=await runMirror(options,dependencies);
  assert.equal(result.verifiedObjects,1);
  assert.deepEqual(f.getStored(),bytes);
});

test('an existing target with different bytes is never overwritten or deleted',async t=>{
  const directory=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'cos-mirror-test-')));t.after(()=>fs.rm(directory,{recursive:true,force:true}));
  const f=clients(Buffer.alloc(fixedSize(),0x78));
  await assert.rejects(runMirror({command:'mirror',concurrency:1,limit:1,state:directory},
    {source,target,sourceClient:f.sourceClient,targetClient:f.targetClient,state:directory}),/incomplete/);
  assert(!f.targetCalls.some(call=>['PutObjectCommand','DeleteObjectCommand'].includes(call.constructor.name)));
});

test('a timed out target HEAD is retried before resuming a verified object',async t=>{
  const directory=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'cos-mirror-test-')));t.after(()=>fs.rm(directory,{recursive:true,force:true}));
  const f=clients(),options={command:'mirror',concurrency:1,state:directory};
  const dependencies={source,target,sourceClient:f.sourceClient,targetClient:f.targetClient,state:directory};
  await runMirror(options,dependencies);
  const send=f.targetClient.send.bind(f.targetClient);
  let headRequests=0;
  f.targetClient.send=async command=>{
    if(command.constructor.name==='HeadObjectCommand'&&++headRequests===1){
      const error=Error('temporary socket timeout');error.name='TimeoutError';throw error;
    }
    return send(command);
  };
  const resumed=await runMirror(options,dependencies);
  assert.equal(headRequests,2);
  assert.equal(resumed.resumedObjects,1);
  assert.equal(f.targetCalls.filter(call=>call.constructor.name==='PutObjectCommand').length,1);
});

test('mirror defers only backup members identified by the source receipt',async t=>{
  const directory=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'cos-mirror-test-')));t.after(()=>fs.rm(directory,{recursive:true,force:true}));
  const f=clients(),archiveSha256=crypto.createHash('sha256').update(f.bytes).digest('hex');
  const files=['courseware-sources.zip','backup-receipt.json'].map(name=>({path:name,sha256:archiveSha256,
    objectKey:`备份/课件恢复/v1/${archiveSha256}/${name}`,byteSize:f.bytes.length,etag:etag(f.bytes)}));
  const receiptPath=path.join(directory,'remote-verification.json');
  const receipt={schemaVersion:'mira.courseware-backup.remote.v1',archiveSha256,complete:true,files,
    storage:{endpoint:source.endpoint,bucket:source.bucket,region:source.region}};
  const send=f.sourceClient.send.bind(f.sourceClient);
  f.sourceClient.send=async command=>{
    const response=await send(command);
    if(command.constructor.name==='ListObjectsV2Command')response.Contents.push(...files.map(file=>({
      Key:file.objectKey,Size:file.byteSize,ETag:file.etag})));
    return response;
  };
  const options={command:'mirror',concurrency:1,state:directory,deferBackupReceipts:[receiptPath]};
  const dependencies={source,target,sourceClient:f.sourceClient,targetClient:f.targetClient};
  await fs.writeFile(receiptPath,JSON.stringify({...receipt,storage:{...receipt.storage,bucket:'another-bucket'}}));
  await assert.rejects(runMirror(options,dependencies),/does not belong to the source bucket/);
  assert(!f.targetCalls.some(call=>call.constructor.name==='PutObjectCommand'));
  await fs.writeFile(receiptPath,JSON.stringify(receipt));
  const result=await runMirror(options,dependencies);
  assert.equal(result.sourceObjects,3);
  assert.equal(result.deferredObjects,2);
  assert.equal(result.verifiedObjects,1);
  assert.deepEqual(f.targetCalls.filter(call=>call.constructor.name==='PutObjectCommand').map(call=>call.input.Key),[f.key]);
});

test('verify mode is read-only when the target is missing',async t=>{
  const directory=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'cos-mirror-test-')));t.after(()=>fs.rm(directory,{recursive:true,force:true}));
  const f=clients();
  await assert.rejects(runMirror({command:'verify',concurrency:1,limit:1,state:directory},
    {source,target,sourceClient:f.sourceClient,targetClient:f.targetClient,state:directory}),/incomplete/);
  assert(!f.targetCalls.some(call=>['PutObjectCommand','DeleteObjectCommand'].includes(call.constructor.name)));
});

function fixedSize(){return Buffer.byteLength('{"课程":"原稿"}');}

const quickRetry={baseMs:1,capMs:2};
const failure=(name,extra={})=>Object.assign(Error(name),{name},extra);
async function stateDirectory(t){
  const directory=await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(),'cos-mirror-test-')));
  t.after(()=>fs.rm(directory,{recursive:true,force:true}));
  return directory;
}
async function journalRecords(directory){
  const journal=(await fs.readdir(directory)).find(name=>name.endsWith('.jsonl'));
  return (await fs.readFile(path.join(directory,journal),'utf8')).trim().split('\n').map(JSON.parse);
}

test('verify retries transient read failures with backoff and still proves the bytes',async t=>{
  const directory=await stateDirectory(t),f=clients(Buffer.from('{"课程":"原稿"}'));
  const send=f.targetClient.send.bind(f.targetClient);
  let heads=0,gets=0;
  f.targetClient.send=async command=>{
    const name=command.constructor.name;
    if(name==='HeadObjectCommand'&&++heads===1)throw failure('ServiceUnavailable',{$metadata:{httpStatusCode:503}});
    if(name==='GetObjectCommand'&&++gets<3){
      if(gets===1)throw failure('TimeoutError',{code:'ECONNRESET'});
      const response=await send(command);
      response.Body=Readable.from((async function*(){yield f.bytes.subarray(0,4);throw failure('Error',{code:'ECONNRESET'});})());
      return response;
    }
    return send(command);
  };
  const result=await runMirror({command:'verify',concurrency:1,state:directory},
    {source,target,sourceClient:f.sourceClient,targetClient:f.targetClient,retry:quickRetry});
  assert.equal(result.verifiedObjects,1);assert.equal(result.retriedReads,3);
  assert.equal(heads,4);assert.equal(gets,3);
  const [receipt,summary]=await journalRecords(directory);
  assert.equal(receipt.integrityCheck,'source-target-sha256');
  assert.equal(receipt.sha256,crypto.createHash('sha256').update(f.bytes).digest('hex'));
  assert.equal(summary.mode,'verify');assert.equal(summary.retriedReads,3);assert.equal(summary.resumedBytes,0);
  assert(!f.targetCalls.some(call=>['PutObjectCommand','DeleteObjectCommand'].includes(call.constructor.name)));
});

test('verify stops at once on definite failures and after its retry limit on a persistent outage',async t=>{
  const mismatch=clients(Buffer.alloc(fixedSize(),0x78));
  await assert.rejects(runMirror({command:'verify',concurrency:1,state:await stateDirectory(t)},
    {source,target,sourceClient:mismatch.sourceClient,targetClient:mismatch.targetClient,retry:quickRetry}),/incomplete/);
  assert.equal(mismatch.targetCalls.filter(call=>call.constructor.name==='GetObjectCommand').length,1);
  const denied=clients(Buffer.from('{"课程":"原稿"}')),deniedSend=denied.targetClient.send.bind(denied.targetClient);
  let heads=0;
  denied.targetClient.send=async command=>{
    if(command.constructor.name==='HeadObjectCommand'){heads++;throw failure('AccessDenied',{$metadata:{httpStatusCode:403}});}
    return deniedSend(command);
  };
  await assert.rejects(runMirror({command:'verify',concurrency:1,state:await stateDirectory(t)},
    {source,target,sourceClient:denied.sourceClient,targetClient:denied.targetClient,retry:quickRetry}),/incomplete/);
  assert.equal(heads,1);
  const outage=clients(Buffer.from('{"课程":"原稿"}')),outageSend=outage.targetClient.send.bind(outage.targetClient);
  let gets=0;
  outage.targetClient.send=async command=>{
    if(command.constructor.name==='GetObjectCommand'){gets++;throw failure('InternalError',{$metadata:{httpStatusCode:500}});}
    return outageSend(command);
  };
  await assert.rejects(runMirror({command:'verify',concurrency:1,state:await stateDirectory(t)},
    {source,target,sourceClient:outage.sourceClient,targetClient:outage.targetClient,retry:{...quickRetry,attempts:3}}),/incomplete/);
  assert.equal(gets,3);
});

test('verify turns a silent stall into a retried timeout instead of waiting forever',async t=>{
  const f=clients(Buffer.from('{"课程":"原稿"}')),send=f.targetClient.send.bind(f.targetClient);
  let heads=0,gets=0;
  f.targetClient.send=async command=>{
    const name=command.constructor.name;
    if(name==='HeadObjectCommand'&&++heads===1)return new Promise(()=>{});
    if(name==='GetObjectCommand'&&++gets===1){
      const response=await send(command),body=new Readable({read(){}});
      body.push(f.bytes.subarray(0,4));response.Body=body;
      return response;
    }
    return send(command);
  };
  const result=await runMirror({command:'verify',concurrency:1,state:await stateDirectory(t)},
    {source,target,sourceClient:f.sourceClient,targetClient:f.targetClient,retry:{...quickRetry,idleMs:50}});
  assert.equal(result.verifiedObjects,1);assert.equal(result.retriedReads,1);
  assert.equal(heads,3);assert.equal(gets,2);
});

test('verify resume skips only earlier read-backs whose source and target identities are unchanged',async t=>{
  const directory=await stateDirectory(t),f=clients();
  const options={command:'verify',concurrency:1,state:directory,resume:true};
  const dependencies={source,target,sourceClient:f.sourceClient,targetClient:f.targetClient,retry:quickRetry};
  const targetReads=()=>f.targetCalls.filter(call=>call.constructor.name==='GetObjectCommand').length;
  await runMirror({command:'mirror',concurrency:1,state:directory},dependencies);
  assert.equal(targetReads(),0);
  const first=await runMirror(options,dependencies);
  assert.equal(first.resumedObjects,0);assert.equal(targetReads(),1);
  const second=await runMirror(options,dependencies);
  assert.equal(second.verifiedObjects,1);assert.equal(second.resumedObjects,1);assert.equal(second.resumedBytes,f.bytes.length);
  assert.equal(targetReads(),1);
  const send=f.targetClient.send.bind(f.targetClient);
  f.targetClient.send=async command=>{
    const response=await send(command);
    if(['HeadObjectCommand','GetObjectCommand'].includes(command.constructor.name))response.VersionId='replacement-version';
    return response;
  };
  const third=await runMirror(options,dependencies);
  assert.equal(third.resumedObjects,0);assert.equal(targetReads(),2);
  const records=await journalRecords(directory);
  assert.deepEqual(records.filter(record=>record.status).map(record=>[record.integrityCheck,record.targetVersionId]),
    [['cos-content-md5+source-sha256','new-version'],['source-target-sha256','new-version'],['source-target-sha256','replacement-version']]);
  assert.deepEqual(records.filter(record=>record.mode).map(record=>[record.mode,record.verifiedObjects,record.resumedObjects]),
    [['mirror',1,0],['verify',1,0],['verify',1,1],['verify',1,0]]);
  assert.equal(f.targetCalls.filter(call=>call.constructor.name==='PutObjectCommand').length,1);
  assert(!f.targetCalls.some(call=>call.constructor.name==='DeleteObjectCommand'));
});

test('resume is a verify-only command line flag',async t=>{
  const tool=fileURLToPath(new URL('../mirror_course_storage.mjs',import.meta.url));
  const directory=await stateDirectory(t),config=path.join(directory,'empty.env');
  await fs.writeFile(config,'');
  const run=args=>spawnSync(process.execPath,[tool,...args],{encoding:'utf8',env:{PATH:process.env.PATH}});
  const accepted=run(['verify','--resume','--config',config,'--state',directory]);
  assert.equal(accepted.status,1);assert.match(accepted.stderr,/configuration is incomplete/);
  const rejected=run(['mirror','--resume','--config',config]);
  assert.notEqual(rejected.status,0);assert.match(rejected.stderr,/Invalid mirror arguments/);
  const unused={send(){throw Error('no request expected');}};
  await assert.rejects(runMirror({command:'mirror',concurrency:1,resume:true,state:directory},
    {source,target,sourceClient:unused,targetClient:unused}),/only to verify/);
});
