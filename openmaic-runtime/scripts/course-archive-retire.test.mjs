import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {Readable} from 'node:stream';
import {planArchiveRetirement,retireArchive} from './course-archive-retire.mjs';

const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const raw=value=>Buffer.from(JSON.stringify(value)+'\n');
const identity={courseId:'textbook-fixture',courseVersion:'1',classroomId:'tbpub_fixture',releaseSha256:'a'.repeat(64)};
class Bucket{
 constructor(){this.objects=new Map();this.calls=[];this.failDelete=false;}
 async send(command){
  const kind=command.constructor.name,key=command.input.Key,bytes=this.objects.get(key);this.calls.push({kind,key});
  if(!bytes)throw Object.assign(Error('missing'),{$metadata:{httpStatusCode:404}});
  const etag='"'+sha(bytes)+'"';if(command.input.IfMatch)assert.equal(command.input.IfMatch,etag);
  if(kind==='GetObjectCommand')return{Body:Readable.from([bytes]),ETag:etag};
  if(kind==='HeadObjectCommand')return{ContentLength:bytes.length,ETag:etag};
  if(kind==='DeleteObjectCommand'){if(this.failDelete)throw Error('first delete failed');this.objects.delete(key);return{};}
  throw Error('unexpected '+kind);
 }
}
async function fixture(t,{legacy=false,missingOriginal=false}={}){
 const directory=await fs.realpath(await fs.mkdtemp(path.join(process.env.MIRA_TASK_TMPDIR||os.tmpdir(),'archive-retire-')));t.after(()=>fs.rm(directory,{recursive:true,force:true}));
 const state=path.join(directory,'state'),client=new Bucket(),config={endpoint:'https://media.example.test',bucket:'study',region:'us-east-1',prefix:'2026-10-23'};
 const storage={endpoint:config.endpoint,bucket:config.bucket,region:config.region};
 const original={sourceIdentity:'owned/original.json',sha256:sha('exact original bytes'),byteSize:20,original:true};
 async function make(name,replacement){
  const folder=path.join(directory,name);await fs.mkdir(folder,{recursive:true});
  const archiveId=(replacement?'b':'c').repeat(24),objectDirectory=!replacement&&legacy?'2026-10-23/科学/一年级-课件':'科学/教材-上册/一年级/2026-10-23/课件';
  const files=missingOriginal&&replacement?[]:[original];if(replacement)files.push({sourceIdentity:'owned/additional.png',sha256:sha('extra'),byteSize:5,original:true});
  const manifest={schemaVersion:'mira.course-archive.export.v1',archiveId,complete:true,identity,missingSources:[],files};
  const manifestRaw=raw(manifest),manifestPath=path.join(folder,'manifest.json');await fs.writeFile(manifestPath,manifestRaw);
  const publicFiles=[];
  for(const [role,bytes]of [['课堂结构',Buffer.from('derived structure')],['归档清单',manifestRaw],['课程资料',Buffer.from(replacement?'new derived metadata':'old derived metadata')],['完整课件',Buffer.from(replacement?'new complete ZIP including every original':'old complete ZIP')]]){
   const ext=role==='完整课件'?'.zip':'.json',timestamp=replacement?'2026-10-23 09-00-00':'2026-10-23 08-00-00';
   const relativePath=objectDirectory+(!replacement&&legacy?'/完整课件/'+timestamp+'/课件-'+role+ext:'/课件-'+role+'-'+timestamp+ext);
   client.objects.set(relativePath,bytes);publicFiles.push({relativePath,sha256:sha(bytes),byteSize:bytes.length,mimeType:ext==='.zip'?'application/zip':'application/json'});
  }
  const index={schemaVersion:manifest.schemaVersion,...identity,archiveId,complete:true,missingSources:[],manifestPath,objectDirectory,generatedPublicFiles:publicFiles};
  const indexPath=path.join(folder,'index.json'),indexRaw=raw(index);await fs.writeFile(indexPath,indexRaw);
  const receipt={schemaVersion:'mira.course-archive.verification.v1',archiveId,indexSha256:sha(indexRaw),complete:true,storage,courseId:identity.courseId,courseVersion:identity.courseVersion,sourceDigest:null,objects:publicFiles.map(e=>({objectKey:e.relativePath,sha256:e.sha256,byteSize:e.byteSize,etag:'"'+e.sha256+'"'})),byteSize:publicFiles.reduce((sum,e)=>sum+e.byteSize,0)};
  const receipts=path.join(state,'archive-transfers',archiveId,'verifications');await fs.mkdir(receipts,{recursive:true});await fs.writeFile(path.join(receipts,sha(indexRaw)+'.json'),raw(receipt));
  return{index,indexPath,manifestPath,publicFiles};
 }
 const old=await make('old',false),replacement=await make('replacement',true);
 return{directory,state,client,config,old,replacement,options:{index:old.indexPath,replacementIndex:replacement.indexPath},dependencies:{client,config,state}};
}
test('read-only plan proves original coverage and freshly checks all eight archive objects without DELETE',async t=>{
 const f=await fixture(t,{legacy:true});const result=await planArchiveRetirement({...f.options,verifyRemote:true},f.dependencies);
 assert.equal(result.originalFiles,1);assert.equal(result.replacementOriginalFiles,2);assert.equal(result.deleteExecuted,false);assert(result.remoteVerified);
 assert.equal(f.client.calls.filter(c=>c.kind==='GetObjectCommand').length,8);assert(!f.client.calls.some(c=>c.kind==='DeleteObjectCommand'));
 assert.equal((await fs.stat(path.join(result.journalDirectory,'old-index.json'))).mode&0o777,0o600);
});
test('missing original and overlapping or unrelated targets are refused before deletion',async t=>{
 const f=await fixture(t,{missingOriginal:true});await assert.rejects(retireArchive({...f.options,execute:true},f.dependencies),/every original/);assert(!f.client.calls.length);
 const other=await fixture(t);other.replacement.index.courseVersion='2';await fs.writeFile(other.replacement.indexPath,raw(other.replacement.index));
 await assert.rejects(retireArchive({...other.options,execute:true},other.dependencies),/manifest.*bound|must match/);assert(!other.client.calls.length);
});
test('changed replacement bytes prevent every old-object deletion',async t=>{
 const f=await fixture(t);f.client.objects.set(f.replacement.publicFiles[0].relativePath,Buffer.from('corrupted replacement'));
 await assert.rejects(retireArchive({...f.options,execute:true},f.dependencies));assert(!f.client.calls.some(c=>c.kind==='DeleteObjectCommand'));
});
test('retirement is exact, conditional, sequential and stops on its first DELETE failure',async t=>{
 const f=await fixture(t);f.client.failDelete=true;
 await assert.rejects(retireArchive({...f.options,execute:true},f.dependencies),/first delete failed/);
 assert.equal(f.client.calls.filter(c=>c.kind==='DeleteObjectCommand').length,1);
 f.client.failDelete=false;const result=await retireArchive({...f.options,execute:true},f.dependencies);
 assert.equal(result.removedObjects,4);for(const old of f.old.publicFiles)assert(!f.client.objects.has(old.relativePath));
 for(const replacement of f.replacement.publicFiles)assert(f.client.objects.has(replacement.relativePath));
});
test('journaled deletion can resume an ambiguous interrupted response without touching later unrelated keys',async t=>{
 const f=await fixture(t);const send=f.client.send.bind(f.client);let interrupted=true;
 f.client.send=async command=>{const result=await send(command);if(interrupted&&command.constructor.name==='DeleteObjectCommand'){interrupted=false;throw Error('connection lost after delete');}return result;};
 await assert.rejects(retireArchive({...f.options,execute:true},f.dependencies),/connection lost/);
 const result=await retireArchive({...f.options,execute:true},f.dependencies);assert.equal(result.resumedObjects,1);assert.equal(result.removedObjects,3);
 const again=await retireArchive({...f.options,execute:true},f.dependencies);assert.equal(again.resumedObjects,4);assert.equal(again.removedObjects,0);
});
test('frozen journal indices and receipts survive removal of disposable exports',async t=>{
 const f=await fixture(t),plan=await planArchiveRetirement(f.options,f.dependencies);
 await fs.rm(path.dirname(f.old.indexPath),{recursive:true});await fs.rm(path.dirname(f.replacement.indexPath),{recursive:true});await fs.rm(path.join(f.state,'archive-transfers'),{recursive:true});
 const result=await retireArchive({index:plan.resumeIndex,replacementIndex:plan.resumeReplacementIndex,execute:true},f.dependencies);
 assert.equal(result.removedObjects,4);assert.equal(result.complete,true);
});
