import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {Readable} from 'node:stream';
import {archiveKey,uploadArchive,savedStages} from './course-archive.mjs';

const digest=b=>crypto.createHash('sha256').update(b).digest('hex');
class S3 {
 constructor(){this.objects=new Map();this.puts=[];}
 async send(c){const k=c.input.Key,kind=c.constructor.name,o=this.objects.get(k);
  if(kind==='HeadObjectCommand'){if(!o)throw Object.assign(Error('missing'),{$metadata:{httpStatusCode:404}});return {ContentLength:o.length,ETag:'"'+digest(o)+'"'};}
  if(kind==='PutObjectCommand'){
   assert.equal(c.input.IfNoneMatch,'*');if(o)throw Error('overwrite');
   const chunks=[];for await(const b of c.input.Body)chunks.push(b);const bytes=Buffer.concat(chunks);
   assert.equal(digest(bytes),c.input.Metadata.sha256);this.objects.set(k,bytes);this.puts.push(k);return {};
  }
  if(kind==='GetObjectCommand'){if(!o)throw Error('missing');return {Body:Readable.from([o]),ETag:'"'+digest(o)+'"'};}
  throw Error(kind);
 }
}
async function fixture(t){
 const root=await fs.realpath(await fs.mkdtemp(path.join(process.env.MIRA_TASK_TMPDIR || os.tmpdir(),'course-archive-')));t.after(()=>fs.rm(root,{recursive:true,force:true}));
 const state=path.join(root,'state'),dir=path.join(state,'archives','pilot');await fs.mkdir(dir,{recursive:true});const files=[];
 for(const [name,bytes,mimeType] of [['课件-完整课件.zip',Buffer.from('complete fixture zip bytes'),'application/zip'],['课件-课堂结构.json',Buffer.from('{"stage":{},"scenes":[]}'),'application/json']]){
  const localPath=path.join(dir,name);await fs.writeFile(localPath,bytes);files.push({localPath,relativePath:'科学/教科版-上册/一年级/2026-10-23/课件/'+name,sha256:digest(bytes),byteSize:bytes.length,mimeType});
 }
 const index=path.join(dir,'export-index.json'),data={schemaVersion:'mira.course-archive.export.v1',complete:true,archiveId:'a'.repeat(64),missingSources:[],generatedPublicFiles:files};await fs.writeFile(index,JSON.stringify(data));
 const client=new S3(),config={endpoint:'http://archive.test:9000',bucket:'study',prefix:'2026-10-23',region:'us-east-1'};
 return {root,state,dir,index,data,client,dependencies:{state,client,config,allowedRoots:[path.join(state,'archives')]}};
}
test('archive keys are dated readable course artifacts, never credentials',()=>{
 const base='科学/教科版-上册/一年级/2026-10-23/课件/';
 assert(archiveKey(base+'课件-完整课件.zip'));
 for(const p of [base+'../file.zip',base+'owner.cookies',base+'.env',base+'a\u0085.json',base.replace('2026-10-23','2026-02-30')+'a.zip','2026-10-23/科学/一年级-课件/课件.zip'])assert(!archiveKey(p),p);
});
test('upload verifies every ZIP/JSON byte and stores private recovery receipt',async t=>{
 const f=await fixture(t);const r=await uploadArchive(f.index,f.dependencies);assert.equal(r.objects.length,2);assert(r.complete);assert.equal(f.client.puts.length,2);
 const saved=JSON.parse(await fs.readFile(path.join(f.state,'archive-transfers',f.data.archiveId,'verified-complete.json')));assert.deepEqual(saved,r);
 const repeated=await uploadArchive(f.index,f.dependencies);assert.deepEqual(repeated,r);assert.equal(f.client.puts.length,2);
 const another=await uploadArchive(f.index,{...f.dependencies,config:{...f.dependencies.config,bucket:'production'}});
 assert.equal(another.storage.bucket,'production');
 const verifications=path.join(f.state,'archive-transfers',f.data.archiveId,'verifications');
 assert.equal((await fs.readdir(verifications)).length,2);
 const restored=await uploadArchive(f.index,f.dependencies);assert.deepEqual(restored,r);
});
test('existing wrong objects are never overwritten or accepted',async t=>{
 const f=await fixture(t);f.client.objects.set(f.data.generatedPublicFiles[0].relativePath,Buffer.from('unknown existing bytes'));
 await assert.rejects(uploadArchive(f.index,f.dependencies),/differ/);assert.equal(f.client.puts.length,0);
 await assert.rejects(fs.stat(path.join(f.state,'archive-transfers',f.data.archiveId,'verified-complete.json')),{code:'ENOENT'});
});
test('incomplete exports and changed or linked sources stay private',async t=>{
 const f=await fixture(t);await fs.writeFile(f.index,JSON.stringify({...f.data,complete:false}));await assert.rejects(uploadArchive(f.index,f.dependencies),/complete validated/);
 await fs.writeFile(f.index,JSON.stringify(f.data));await fs.writeFile(f.data.generatedPublicFiles[0].localPath,'changed');await assert.rejects(uploadArchive(f.index,f.dependencies),/source changed/);assert.equal(f.client.puts.length,0);
 const source=f.data.generatedPublicFiles[0].localPath;await fs.unlink(source);await fs.symlink(f.data.generatedPublicFiles[1].localPath,source);await assert.rejects(uploadArchive(f.index,f.dependencies),/escapes|symlink/);
});
test('historical PG snapshots use read-only queries and exclude producer and owner controls',async()=>{
 const calls=[],row={id:'stage-one',data:{id:'stage-one',name:'观察',dslVersion:3},scenes:[{id:'s1',stageId:'stage-one'}],revision:'9',outline:{producerRef:'private-session',title:'观察'},updated_at:1792713600000};
 const client={async query(sql,args){calls.push({sql,args});return {rows:sql.startsWith('SELECT')?[row]:[]};}};
 const result=await savedStages({client,limit:7,afterStageId:'stage-before'});assert.equal(result.stages.length,1);
 assert.equal(result.stages[0].snapshot_json.dslVersion,3);assert(!JSON.stringify(result).includes('private-session'));
 assert(calls[0].sql.includes('READ ONLY'));assert.equal(calls.at(-1).sql,'ROLLBACK');assert.deepEqual(calls[1].args,['stage-before',7]);
 assert(!calls.some(c=>/INSERT|UPDATE|CREATE|DELETE/.test(c.sql)));
 await assert.rejects(savedStages({client,afterStageId:'unsafe/cursor'}),/Invalid/);
});
