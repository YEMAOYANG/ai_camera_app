import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {Readable} from 'node:stream';
import {relocateArchive} from './course-archive-layout.mjs';

const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const canonical=value=>JSON.stringify(value,(key,item)=>item&&!Array.isArray(item)&&typeof item==='object'?Object.fromEntries(Object.keys(item).sort().map(k=>[k,item[k]])):item);
const failure=status=>Object.assign(Error('S3 '+status),{$metadata:{httpStatusCode:status}});
const targetDirectory='语文/人教统编-上册/一年级/2026-10-23/测试课件';
class Bucket {
 constructor(){this.objects=new Map();this.calls=[];this.ignoreDestinationCondition=false;this.failCopyAt=0;this.copyAttempts=0;this.putAttempts=0;this.failPutAt=0;}
 etag(bytes){return '"'+sha(bytes)+'"';}
 async send(command){
  const {input}=command,kind=command.constructor.name,key=input.Key,bytes=this.objects.get(key);this.calls.push({kind,input});
  if(kind==='HeadObjectCommand'){if(!bytes)throw failure(404);return {ContentLength:bytes.length,ETag:this.etag(bytes)};}
  if(kind==='GetObjectCommand'){if(!bytes)throw failure(404);if(input.IfMatch&&input.IfMatch!==this.etag(bytes))throw failure(412);return {Body:Readable.from([bytes]),ETag:this.etag(bytes)};}
  if(kind==='PutObjectCommand'){
   this.putAttempts++;assert.equal(input.IfNoneMatch,'*');assert(!Buffer.isBuffer(input.Body));
   if(this.failPutAt===this.putAttempts)throw failure(503);if(bytes)throw failure(412);
   const chunks=[];for await(const chunk of input.Body)chunks.push(chunk);const body=Buffer.concat(chunks);
   assert.equal(body.length,input.ContentLength);assert.equal(sha(body),input.Metadata.sha256);assert.equal(Buffer.from(sha(body),'hex').toString('base64'),input.ChecksumSHA256);
   this.objects.set(key,body);return {ETag:this.etag(body)};
  }
  if(kind==='CopyObjectCommand'){
   this.copyAttempts++;if(this.failCopyAt===this.copyAttempts)throw failure(503);
   assert.equal(input.IfNoneMatch,'*');assert.equal(input.MetadataDirective,'COPY');
   const sourceKey=input.CopySource.split('/').slice(1).map(decodeURIComponent).join('/'),source=this.objects.get(sourceKey);
   assert.equal(input.CopySource.split('/')[0],'study');if(!source)throw failure(404);
   if(input.CopySourceIfMatch!==this.etag(source))throw failure(412);
   if(bytes&&!this.ignoreDestinationCondition)throw failure(412);
   this.objects.set(key,Buffer.from(source));return {CopyObjectResult:{ETag:this.etag(source)}};
  }
  throw Error('Unexpected operation '+kind);
 }
}
async function fixture(t){
 const root=await fs.realpath(await fs.mkdtemp(path.join(process.env.MIRA_TASK_TMPDIR||os.tmpdir(),'archive-layout-')));t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const state=path.join(root,'state'),archiveId='a'.repeat(24),stagingDirectory=path.join(state,'archives',archiveId+'-12345678');await fs.mkdir(stagingDirectory,{recursive:true,mode:0o700});
 const objectDirectory='语文/待核验-上册/一年级/2026-10-23/测试课件';
 const identity={courseId:'course_one',courseVersion:'1',classroomId:'tbpub_one',contentKey:'b'.repeat(64),releaseSha256:'c'.repeat(64)};
 const manifest={schemaVersion:'mira.course-archive.export.v1',archiveId,identity,complete:true,missingSources:[],files:[{original:true,sourceIdentity:'saved:one',sha256:sha('original'),byteSize:8}]};
 const manifestRaw=Buffer.from(canonical(manifest)+'\n'),client=new Bucket();
 const descriptors=[['课堂结构','classroom.json',Buffer.from('{"stage":{"id":"tbpub_one"},"scenes":[]}')],['归档清单','manifest.json',manifestRaw],['课程资料','metadata.json',Buffer.from('{"title":"测试课件"}')],['完整课件','课程.zip',Buffer.from('different ZIP fixture bytes')]];
 const generatedPublicFiles=descriptors.map(([role,local,bytes])=>{const relativePath=objectDirectory+'/测试课件-'+role+'-2026-10-23 09-00-00.'+(role==='完整课件'?'zip':'json');client.objects.set(relativePath,bytes);return {localPath:path.join(stagingDirectory,role==='完整课件'?local:'课程资料/'+local),relativePath,sha256:sha(bytes),byteSize:bytes.length,mimeType:role==='完整课件'?'application/zip':'application/json'};});
 const zip=generatedPublicFiles.at(-1),indexPath=path.join(stagingDirectory,'index.json');
 const index={schemaVersion:'mira.course-archive.export.v1',archiveId,...identity,complete:true,missingSources:[],sourceKind:'textbook_release',sourceDigest:identity.releaseSha256,stagingDirectory,indexPath,manifestPath:generatedPublicFiles[1].localPath,objectDirectory,archiveVersion:'2026-10-23T09:00:00Z',exportedAt:'2026-10-23T09:00:00Z',totals:{files:1},generatedPublicFiles,zip:{path:zip.localPath,sha256:zip.sha256,byteSize:zip.byteSize}};
 const indexRaw=Buffer.from(canonical(index)+'\n');await fs.writeFile(indexPath,indexRaw);await fs.writeFile(path.join(stagingDirectory,'manifest.json'),manifestRaw);
 const config={endpoint:'http://archive.test:9000',bucket:'study',region:'us-east-1',prefix:'2026-10-23'},storage={endpoint:config.endpoint,bucket:config.bucket,region:config.region};
 const receipt={schemaVersion:'mira.course-archive.verification.v1',archiveId,courseId:index.courseId,courseVersion:index.courseVersion,sourceDigest:index.sourceDigest,indexSha256:sha(indexRaw),storage,verifiedAt:'2026-10-23T09:01:00Z',objects:generatedPublicFiles.map(e=>({objectKey:e.relativePath,sha256:e.sha256,byteSize:e.byteSize,etag:client.etag(client.objects.get(e.relativePath))})),byteSize:generatedPublicFiles.reduce((n,e)=>n+e.byteSize,0),complete:true};
 const receiptPath=path.join(state,'archive-transfers',archiveId,'verifications',sha(canonical(storage)),sha(indexRaw)+'.json');await fs.mkdir(path.dirname(receiptPath),{recursive:true});await fs.writeFile(receiptPath,canonical(receipt)+'\n');
 return {state,indexPath,index,indexRaw,manifest,manifestRaw,receipt,receiptPath,client,dependencies:{state,config,client},destination:e=>targetDirectory+'/'+path.posix.basename(e.relativePath)};
}

test('relocation copies four original objects, probes destination conditions and retains all source evidence',async t=>{
 const f=await fixture(t),sourceBefore=new Map(f.client.objects),oldReceipt=await fs.readFile(f.receiptPath);
 const result=await relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies});
 assert.equal(result.complete,true);assert.equal(result.sourceObjectsRetained,true);assert.equal(result.objects,4);assert.notEqual(result.indexPath,f.indexPath);
 const next=JSON.parse(await fs.readFile(result.indexPath)),receipt=JSON.parse(await fs.readFile(result.receiptPath));
 for(const key of ['archiveId','courseId','courseVersion','classroomId','contentKey','releaseSha256','sourceDigest','archiveVersion','exportedAt','totals'])assert.deepEqual(next[key],f.index[key]);
 assert.equal(next.objectDirectory,targetDirectory);assert.equal(receipt.indexSha256,sha(await fs.readFile(result.indexPath)));assert.deepEqual(receipt.storage,f.receipt.storage);
 assert.deepEqual(await fs.readFile(path.join(path.dirname(result.indexPath),'manifest.json')),f.manifestRaw);
 for(let i=0;i<4;i++){const old=f.index.generatedPublicFiles[i],entry=next.generatedPublicFiles[i];assert.equal(path.posix.basename(entry.relativePath),path.posix.basename(old.relativePath));assert.equal(entry.sha256,old.sha256);assert.equal(entry.byteSize,old.byteSize);assert.deepEqual(f.client.objects.get(entry.relativePath),sourceBefore.get(old.relativePath));assert.deepEqual(f.client.objects.get(old.relativePath),sourceBefore.get(old.relativePath));}
 assert.equal(f.client.calls.filter(c=>c.kind==='CopyObjectCommand').length,5);assert(!f.client.calls.some(c=>/Delete|Put/.test(c.kind)));
 const copies=f.client.calls.filter(c=>c.kind==='CopyObjectCommand');assert.deepEqual(copies[0].input,copies[1].input);assert.equal(JSON.parse(await fs.readFile(path.join(result.journalDirectory,'destination-condition.json'))).status,'supported');
 assert.deepEqual(await fs.readFile(f.indexPath),f.indexRaw);assert.deepEqual(await fs.readFile(f.receiptPath),oldReceipt);assert.equal((await fs.stat(result.indexPath)).mode&0o777,0o600);
 const repeated=await relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies});assert.equal(repeated.indexPath,result.indexPath);assert.equal(repeated.receiptPath,result.receiptPath);assert.equal(f.client.calls.filter(c=>c.kind==='CopyObjectCommand').length,5);assert.deepEqual(JSON.parse(await fs.readFile(result.receiptPath)),receipt);
});
test('changed frozen source stops before any copy, including changes to a later object',async t=>{
 const f=await fixture(t);f.client.objects.set(f.index.generatedPublicFiles[3].relativePath,Buffer.from('changed'));
 await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies}),/source.*changed/);assert.equal(f.client.copyAttempts,0);
});
test('an existing wrong destination is never overwritten, even when its size is unchanged',async t=>{
 const f=await fixture(t),entry=f.index.generatedPublicFiles[0],bad=Buffer.alloc(entry.byteSize,88);f.client.objects.set(f.destination(entry),bad);
 await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies}),/destination.*differ/);assert.equal(f.client.copyAttempts,0);assert.deepEqual(f.client.objects.get(f.destination(entry)),bad);
});
test('immutable receipt identity and storage mismatch fail before network activity',async t=>{
 for(const mutation of [r=>r.courseId='another_course',r=>r.storage.bucket='other',r=>r.objects[0].sha256='d'.repeat(64)]){
  const f=await fixture(t),r=structuredClone(f.receipt);mutation(r);await fs.writeFile(f.receiptPath,canonical(r));
  await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies}),/identity|storage/);assert.equal(f.client.calls.length,0);
 }
});
test('copy failure stops immediately, and retry reuses the journal and verifies existing destinations',async t=>{
 const f=await fixture(t);f.client.failCopyAt=3;
 await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies}),/503/);assert.equal(f.client.copyAttempts,3);
 assert.equal(f.index.generatedPublicFiles.filter(e=>f.client.objects.has(f.destination(e))).length,1);
 const [planId]=await fs.readdir(path.join(f.state,'archive-relocations')),planPath=path.join(f.state,'archive-relocations',planId,'plan.json'),plan=JSON.parse(await fs.readFile(planPath));
 f.client.failCopyAt=0;const result=await relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies});assert.equal(path.dirname(result.indexPath),plan.stagingDirectory);assert.equal(result.objects,4);assert.equal((await fs.readdir(result.journalDirectory)).includes('execute.lock'),false);
});
test('a server ignoring destination IfNoneMatch is detected on the first copied target and refuses later copies',async t=>{
 const f=await fixture(t);f.client.ignoreDestinationCondition=true;
 await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies}),/does not enforce.*further copies refused/);
 assert.equal(f.client.copyAttempts,2);assert.equal(f.index.generatedPublicFiles.filter(e=>f.client.objects.has(f.destination(e))).length,1);
 for(const e of f.index.generatedPublicFiles)assert(f.client.objects.has(e.relativePath));
 const [planId]=await fs.readdir(path.join(f.state,'archive-relocations'));assert.equal(JSON.parse(await fs.readFile(path.join(f.state,'archive-relocations',planId,'destination-condition.json'))).status,'unsupported');
 await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies}),/does not enforce/);assert.equal(f.client.copyAttempts,2);
});
test('a 412 caused by a changed source cannot falsely prove destination condition support',async t=>{
 const f=await fixture(t),send=f.client.send.bind(f.client);let copies=0;
 f.client.send=async command=>{if(command.constructor.name==='CopyObjectCommand'&&++copies===2){f.client.objects.set(f.index.generatedPublicFiles[0].relativePath,Buffer.from('changed during probe'));throw failure(412);}return send(command);};
 await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies}),/source.*changed/);assert.equal(copies,2);assert.equal(f.index.generatedPublicFiles.filter(e=>f.client.objects.has(f.destination(e))).length,1);
});
test('an interrupted probe resumes against its first existing target before copying any later object',async t=>{
 const f=await fixture(t);f.client.failCopyAt=2;
 await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies}),/503/);assert.equal(f.client.copyAttempts,2);
 f.client.failCopyAt=0;f.client.ignoreDestinationCondition=true;
 await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies}),/does not enforce/);assert.equal(f.client.copyAttempts,3);
 assert.equal(f.index.generatedPublicFiles.filter(e=>f.client.objects.has(f.destination(e))).length,1);
});
test('manifest tampering, unsafe target paths and linked private inputs are rejected without network activity',async t=>{
 const f=await fixture(t);
 for(const target of ['语文/统编/一年级/2026-02-30/课','语文/统编/一年级/2026-10-23/../课','语文/统编/一年级/2026-10-23/课/.env'])await assert.rejects(relocateArchive(f.indexPath,{targetDirectory:target,dependencies:f.dependencies}),/safe five/);
 await fs.writeFile(path.join(path.dirname(f.indexPath),'manifest.json'),canonical({...f.manifest,identity:{...f.manifest.identity,courseId:'other'}}));
 await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies}),/manifest identity or bytes/);
 await fs.writeFile(path.join(path.dirname(f.indexPath),'manifest.json'),f.manifestRaw);
 const linked=f.indexPath+'.link';await fs.symlink(f.indexPath,linked);await assert.rejects(relocateArchive(linked,{targetDirectory,dependencies:f.dependencies}),/symlink/);assert.equal(f.client.calls.length,0);
});
test('explicit verified-put recovers an unsupported copy journal with streamed conditional PUT and prunes verified caches',async t=>{
 const f=await fixture(t);f.client.ignoreDestinationCondition=true;
 await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,dependencies:f.dependencies}),/does not enforce/);assert.equal(f.client.copyAttempts,2);
 const result=await relocateArchive(f.indexPath,{targetDirectory,transport:'verified-put',dependencies:f.dependencies});
 assert.equal(result.complete,true);assert.equal(result.transport,'verified-put');assert.equal(f.client.copyAttempts,2);assert.equal(f.client.putAttempts,3);
 assert.equal(JSON.parse(await fs.readFile(path.join(result.journalDirectory,'transport.json'))).transport,'verified-put');
 const cache=path.join(result.journalDirectory,'transfer-cache');assert(!(await fs.readdir(cache)).some(name=>name.endsWith('.bin')));
 for(const old of f.index.generatedPublicFiles)assert.deepEqual(f.client.objects.get(old.relativePath),f.client.objects.get(f.destination(old)));
});
test('short or changed source GET bytes are rejected before any PUT',async t=>{
 for(const change of [bytes=>bytes.subarray(1),bytes=>Buffer.alloc(bytes.length,88)]){
  const f=await fixture(t),send=f.client.send.bind(f.client),key=f.index.generatedPublicFiles[0].relativePath;
  f.client.send=async command=>{const response=await send(command);if(command.constructor.name==='GetObjectCommand'&&command.input.Key===key)return {...response,Body:Readable.from([change(f.client.objects.get(key))])};return response;};
  await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,transport:'verified-put',dependencies:f.dependencies}),/source download bytes differ/);assert.equal(f.client.putAttempts,0);assert.equal(f.client.copyAttempts,0);
 }
});
test('conditional PUT 412 races only accept fully verified destination bytes',async t=>{
 for(const correct of [true,false]){
  const f=await fixture(t),send=f.client.send.bind(f.client),first=f.index.generatedPublicFiles[0];let raced=false;
  f.client.send=async command=>{if(command.constructor.name==='PutObjectCommand'&&!raced){raced=true;f.client.putAttempts++;const bytes=f.client.objects.get(first.relativePath);f.client.objects.set(command.input.Key,correct?Buffer.from(bytes):Buffer.alloc(bytes.length,88));throw failure(412);}return send(command);};
  const operation=relocateArchive(f.indexPath,{targetDirectory,transport:'verified-put',dependencies:f.dependencies});
  if(correct){assert.equal((await operation).objects,4);assert.equal(f.client.putAttempts,4);}
  else{await assert.rejects(operation,/destination.*differ/);assert.equal(f.client.putAttempts,1);assert.equal(f.index.generatedPublicFiles.filter(e=>f.client.objects.has(f.destination(e))).length,1);}
  assert.equal(f.client.copyAttempts,0);
 }
});
test('failed PUT keeps one bound cache, resumes without redownloading it and stops before later objects',async t=>{
 const f=await fixture(t);f.client.failPutAt=1;
 await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,transport:'verified-put',dependencies:f.dependencies}),/503/);assert.equal(f.client.putAttempts,1);assert.equal(f.client.copyAttempts,0);
 const [plan]=await fs.readdir(path.join(f.state,'archive-relocations')),cache=path.join(f.state,'archive-relocations',plan,'transfer-cache');assert.equal((await fs.readdir(cache)).filter(n=>n.endsWith('.bin')).length,1);
 const sourceKey=f.index.generatedPublicFiles[0].relativePath,getCount=()=>f.client.calls.filter(c=>c.kind==='GetObjectCommand'&&c.input.Key===sourceKey).length;assert.equal(getCount(),1);
 f.client.failPutAt=0;const result=await relocateArchive(f.indexPath,{targetDirectory,transport:'verified-put',dependencies:f.dependencies});assert.equal(result.complete,true);assert.equal(getCount(),1);assert.equal(f.client.putAttempts,5);assert(!(await fs.readdir(cache)).some(n=>n.endsWith('.bin')));
});
test('changed or symlinked transport caches are rejected before PUT and cannot escape state',async t=>{
 for(const symlink of [false,true]){
  const f=await fixture(t);f.client.failPutAt=1;
  await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,transport:'verified-put',dependencies:f.dependencies}),/503/);
  const [plan]=await fs.readdir(path.join(f.state,'archive-relocations')),cache=path.join(f.state,'archive-relocations',plan,'transfer-cache'),[name]=(await fs.readdir(cache)).filter(n=>n.endsWith('.bin')),filename=path.join(cache,name);
  if(symlink){await fs.unlink(filename);await fs.symlink(f.indexPath,filename);}else await fs.writeFile(filename,'corrupted transfer bytes');
  f.client.failPutAt=0;await assert.rejects(relocateArchive(f.indexPath,{targetDirectory,transport:'verified-put',dependencies:f.dependencies}),/cache.*symlink|cache bytes differ/);assert.equal(f.client.putAttempts,1);assert.equal(f.client.copyAttempts,0);assert.deepEqual(await fs.readFile(f.indexPath),f.indexRaw);
 }
});
