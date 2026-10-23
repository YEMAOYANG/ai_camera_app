import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {EventEmitter} from 'node:events';
import {Readable} from 'node:stream';
import {canonical,enumerateSnapshotAssets,resolveArchiveAssets,createKatexArchiveResolver,downloadKatexBytes,createThreeArchiveResolver,downloadThreeBytes,publicCdnAddress,assertAssetWriteBudget,saveBytes} from './course-archive-assets.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(path.join(root,'openmaic-runtime/.runtime/OpenMAIC/packages/@openmaic/storage/package.json'));
const {PGlite}=require('@electric-sql/pglite');
const digest=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const room=(refs=['ast_owned'])=>({id:'stage-one',stage:{id:'stage-one',name:'观察'},scenes:[{id:'scene-one',stageId:'stage-one',content:{type:'slide',canvas:{id:'slide-one',elements:refs.map((src,i)=>({id:'image-'+i,type:'image',src})),background:{type:'solid',color:'#fff'}}},actions:[]}]});
async function fixture(t,snapshot=room()){
 const directory=await fs.realpath(await fs.mkdtemp(path.join(process.env.MIRA_TASK_TMPDIR||os.tmpdir(),'archive-assets-')));
 const db=new PGlite();t.after(async()=>{await db.close();await fs.rm(directory,{recursive:true,force:true});});
 await db.exec(`CREATE TABLE document_stages(id text primary key,owner_id text,data jsonb);
 CREATE TABLE document_scenes(id text,stage_id text,scene_order integer,data jsonb);
 CREATE TABLE asset_blobs(content_hash text primary key,byte_size bigint,bytes bytea);
 CREATE TABLE asset_entries(id text primary key,principal text,content_hash text,mime text);`);
 await db.query('INSERT INTO document_stages VALUES($1,$2,$3)',[snapshot.stage.id,'owner-one',snapshot.stage]);
 for(const [i,scene]of snapshot.scenes.entries())await db.query('INSERT INTO document_scenes VALUES($1,$2,$3,$4)',[scene.id,snapshot.stage.id,i,scene]);
 const calls=[];
 const queryable={query:async(sql,values)=>{calls.push(sql);return db.query(sql,values);}};
 const dependencies={db:queryable,config:{},allowedRoots:[directory],nativeRoot:path.join(directory,'native'),stateRoot:path.join(directory,'state')};
 const input={snapshot,stageId:snapshot.stage.id,stagingRoot:path.join(directory,'export','asset-sources')};
 async function asset(id,principal,bytes=Buffer.from('fixture image bytes'),contentHash='sha256-'+digest(bytes)){
  await db.query('INSERT INTO asset_blobs VALUES($1,$2,$3) ON CONFLICT DO NOTHING',[contentHash,bytes.length,bytes]);
  await db.query('INSERT INTO asset_entries VALUES($1,$2,$3,$4)',[id,principal,contentHash,'image/png']);
 }
 return{db,directory,input,dependencies,asset,calls};
}
test('pure DSL traversal discovers rendered assets and bridges only exact speech audio',()=>{
 const snapshot=room(['ast_owned','data:image/png;base64,YQ==','/api/classroom-media/stage-one/media/picture.png','https://example.invalid/image.png']);
 snapshot.scenes[0].actions=[{type:'speech',audioId:'tbprev_narration',audioUrl:'/api/classroom-media/stage-one/audio/narration.wav'}];
 const entries=enumerateSnapshotAssets(snapshot);
 assert.equal(entries.find(e=>e.ref==='ast_owned').status,'unresolved');
 assert.equal(entries.find(e=>e.ref.startsWith('data:')).status,'inline');
 assert.equal(entries.find(e=>e.ref.includes('/media/')).status,'already_collected');
 assert.equal(entries.find(e=>e.ref.startsWith('https:')).status,'unresolved');
 assert.equal(entries.find(e=>e.ref==='tbprev_narration').mappedRef,snapshot.scenes[0].actions[0].audioUrl);
 assert(!JSON.stringify(entries).includes('owner-one'));
 snapshot.scenes[0].actions[0].audioUrl='http://127.0.0.1:3100'+snapshot.scenes[0].actions[0].audioUrl;
 assert.equal(enumerateSnapshotAssets(snapshot).find(e=>e.ref==='tbprev_narration').status,'already_collected');
 snapshot.scenes[0].actions[0].audioUrl='https://other.example'+new URL(snapshot.scenes[0].actions[0].audioUrl).pathname;
 assert.equal(enumerateSnapshotAssets(snapshot).find(e=>e.ref==='tbprev_narration').status,'unresolved');
});
test('interactive HTML media, srcset, SVG and CSS dependencies are discovered without running scripts',()=>{
 const snapshot=room([]);snapshot.scenes[0].content={type:'interactive',html:`<style>.a{background:url('/api/classroom-media/stage-one/media/bg.png')} @import "https://example.invalid/font.css";</style>
 <img src="ast_image" srcset="data:image/png;base64,YQ== 1x, /api/classroom-media/stage-one/media/large.png 2x">
 <video src="ast_video" poster="/api/classroom-media/stage-one/media/poster.png"><source src="https://example.invalid/movie.mp4"></video>
 <audio src="data:audio/wav;base64,YQ=="></audio><svg><image href="ast_svg_image"/><use href="#local-icon"/></svg>
 <script>const generatedImage='ast_script_image';throw Error('must never execute');</script>`};
 snapshot.scenes[0].content.attachments=[{allocatedAssetId:'ast_frozen_attachment'}];
 const entries=enumerateSnapshotAssets(snapshot);
 assert.equal(entries.find(e=>e.ref==='ast_image').status,'unresolved');
 assert.equal(entries.find(e=>e.ref==='ast_video').kind,'video');
 assert.equal(entries.find(e=>e.ref==='ast_svg_image').status,'unresolved');
 assert.equal(entries.find(e=>e.ref==='#local-icon').status,'inline');
 assert.equal(entries.find(e=>e.ref.endsWith('bg.png')).status,'already_collected');
 assert(entries.some(e=>e.ref==='https://example.invalid/font.css'&&e.status==='unresolved'));
 assert(entries.some(e=>e.ref.startsWith('data:audio')&&e.status==='inline'));
 assert(entries.some(e=>e.ref==='ast_script_image'&&e.status==='unresolved'));
 assert(entries.some(e=>e.ref==='ast_frozen_attachment'&&e.status==='unresolved'));
});
test('namespace constants are not fetched dependencies while an actual namespace src stays unresolved',()=>{
 const snapshot=room([]);snapshot.scenes[0].content={type:'interactive',html:`<script>const SVG_NS='http://www.w3.org/2000/svg';document.createElementNS(SVG_NS,'svg');const XLINK='http://www.w3.org/1999/xlink';</script>`};
 assert.deepEqual(enumerateSnapshotAssets(snapshot),[]);
 snapshot.scenes[0].content.html+='<img src="http://www.w3.org/2000/svg">';
 assert.equal(enumerateSnapshotAssets(snapshot)[0].status,'unresolved');
 snapshot.scenes[0].content.html='<script>const nested='+JSON.stringify('<svg xmlns="http://www.w3.org/2000/svg"><path/></svg>')+';</script>';
 assert.deepEqual(enumerateSnapshotAssets(snapshot),[]);
});
test('exact public teaching images are copied with SHA while unrelated public files and links stay unresolved',async t=>{
 const f=await fixture(t,room(['/review-assets/v3-world-action/alex-actions-v1.png','/avatars/teacher-2.png','/other/private.png']));
 const native=f.dependencies.nativeRoot;
 await fs.mkdir(path.join(native,'public/review-assets/v3-world-action'),{recursive:true});await fs.mkdir(path.join(native,'public/avatars'),{recursive:true});
 await fs.writeFile(path.join(native,'public/review-assets/v3-world-action/alex-actions-v1.png'),'exact classroom picture');
 const elsewhere=path.join(f.directory,'elsewhere.png');await fs.writeFile(elsewhere,'unrelated bytes');await fs.symlink(elsewhere,path.join(native,'public/avatars/teacher-2.png'));
 const result=await resolveArchiveAssets(f.input,f.dependencies);
 assert.equal(result.entries[0].status,'resolved');assert.equal(result.entries[0].sha256,digest(await fs.readFile(result.entries[0].sourcePath)));
 assert.equal(result.unresolved.length,2);
});
test('a BASE literal expands only bounded safe stage images, including restored manifest sources',async t=>{
 const snapshot=room([]);snapshot.scenes[0].content={type:'interactive',html:"<script>const BASE='/api/classroom-media/stage-one/media/';</script>"};
 const f=await fixture(t,snapshot),directory=path.join(f.dependencies.nativeRoot,'data/classrooms/stage-one/media');
 await fs.mkdir(directory,{recursive:true});await fs.writeFile(path.join(directory,'local.png'),'image');await fs.writeFile(path.join(directory,'private.json'),'{}');
 const manifestPath=path.join(f.directory,'active-manifest.json');await fs.writeFile(manifestPath,JSON.stringify({schemaVersion:'mira.course-storage.manifest.v2',files:[{path:'openmaic-runtime/.runtime/OpenMAIC/data/classrooms/stage-one/media/remote.webp',mimeType:'image/webp',sha256:'a'.repeat(64),byteSize:123}]}));
 const result=await resolveArchiveAssets(f.input,{...f.dependencies,config:{manifestPath}});
 assert.equal(result.unresolved.length,0);assert(result.entries.some(e=>e.ref.endsWith('/local.png')&&e.status==='already_collected'));assert(result.entries.some(e=>e.ref.endsWith('/remote.webp')));
 assert(!result.entries.some(e=>e.ref.endsWith('private.json')));
 await fs.unlink(path.join(directory,'local.png'));
 const empty=await resolveArchiveAssets({...f.input,stagingRoot:path.join(f.directory,'empty','asset-sources')},f.dependencies);
 assert.equal(empty.unresolved.length,1);
});
test('owner-bound and source-referenced shared bytes are read under a read-only transaction and SHA checked',async t=>{
 const f=await fixture(t,room(['ast_owned','ast_shared']));
 await f.asset('ast_owned','owner-one');await f.asset('ast_shared','shared',Buffer.from('other image bytes'));
 const result=await resolveArchiveAssets(f.input,f.dependencies);
 assert.equal(result.unresolved.length,0);assert.equal(result.entries.length,2);
 for(const entry of result.entries){assert.equal(digest(await fs.readFile(entry.sourcePath)),entry.sha256);assert.equal((await fs.stat(entry.sourcePath)).mode&0o777,0o600);}
 assert(f.calls[0].includes('READ ONLY'));assert.equal(f.calls.at(-1),'ROLLBACK');
 assert(f.calls.every(sql=>/^(SELECT|BEGIN|ROLLBACK)/.test(sql)));
 assert(!JSON.stringify(result).includes('principal'));assert(!JSON.stringify(result).includes('owner-one'));
});
test('another owner and an invented shared reference cannot be exported',async t=>{
 const f=await fixture(t);await f.asset('ast_other_owner','owner-two');await f.asset('ast_unrelated_shared','shared');
 const result=await resolveArchiveAssets({...f.input,snapshot:room(['ast_other_owner','ast_unrelated_shared'])},f.dependencies);
 assert.equal(result.unresolved.length,2);assert(result.entries.every(e=>!e.sourcePath));
});
test('a retained outbox snapshot authorizes its older shared asset without exposing session ownership',async t=>{
 const f=await fixture(t);const old=room(['ast_old_shared']);await f.asset('ast_old_shared','shared');
 await f.db.exec('CREATE TABLE agent_sessions(id text,owner_id text); CREATE TABLE mira_course_archive_events(session_id text,stage_id text,source_digest text,snapshot_json jsonb)');
 await f.db.query('INSERT INTO agent_sessions VALUES($1,$2)',['private-session','owner-one']);
 await f.db.query('INSERT INTO mira_course_archive_events VALUES($1,$2,$3,$4)',['private-session','stage-one',digest(canonical(old)),old]);
 const result=await resolveArchiveAssets({...f.input,snapshot:old},f.dependencies);
 assert.equal(result.unresolved.length,0);assert.equal(result.entries[0].status,'resolved');
 assert(!JSON.stringify(result).includes('private-session'));
});
test('corrupt bytes, external URLs and symlink staging never qualify as resolved',async t=>{
 const f=await fixture(t,room(['ast_corrupt','https://example.invalid/picture.png']));
 await f.asset('ast_corrupt','owner-one',Buffer.from('wrong bytes'),'sha256-'+'0'.repeat(64));
 const result=await resolveArchiveAssets(f.input,f.dependencies);assert.equal(result.unresolved.length,2);
 const target=path.join(f.directory,'linked');await fs.symlink(path.dirname(f.input.stagingRoot),target);
 await assert.rejects(resolveArchiveAssets({...f.input,stagingRoot:path.join(target,'elsewhere')},f.dependencies),/symlink/);
});
test('exact hash selects the configured byte layer and remote bytes must still match',async t=>{
 const f=await fixture(t);const bytes=Buffer.from('S3 asset bytes');await f.asset('ast_owned','owner-one',bytes);
 let calls=0;const result=await resolveArchiveAssets(f.input,{...f.dependencies,readBytes:async(hash,size)=>{calls++;assert.equal(hash,'sha256-'+digest(bytes));assert.equal(size,bytes.length);return bytes;}});
 assert.equal(calls,1);assert.equal(result.entries[0].status,'resolved');
 const bad=await resolveArchiveAssets({...f.input,stagingRoot:path.join(f.directory,'other','asset-sources')},{...f.dependencies,readBytes:async()=>Buffer.from('wrong')});
 assert.equal(bad.unresolved.length,1);
});

const katexBase='https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/';
async function katexFixture(t,{fontFailure=false,limits={}}={}){
 const directory=await fs.realpath(await fs.mkdtemp(path.join(process.env.MIRA_TASK_TMPDIR||os.tmpdir(),'archive-katex-')));
 t.after(()=>fs.rm(directory,{recursive:true,force:true}));
 const root=path.join(directory,'assets'),cacheRoot=path.join(directory,'cache');
 await fs.mkdir(root);await fs.mkdir(cacheRoot);
 const sources={
  'katex.min.css':Buffer.from('@font-face{src:url(fonts/KaTeX_Main-Regular.woff2)}'),
  'katex.min.js':Buffer.from('throw Error("archived but never executed");'),
  'contrib/auto-render.min.js':Buffer.from('throw Error("also never executed");'),
  'fonts/KaTeX_Main-Regular.woff2':Buffer.from('exact fixture font bytes'),
 };
 const pins=Object.fromEntries(Object.entries(sources).map(([name,bytes])=>[name,[bytes.length,digest(bytes)]])),calls=[];
 const fetchBytes=async(url,options)=>{
  calls.push(url);const name=url.slice(katexBase.length);
  assert.equal(options.maxBytes,sources[name].length);
  if(fontFailure&&name.startsWith('fonts/'))throw Error('fixture unavailable');
  return sources[name];
 };
 return {directory,root,cacheRoot,pins,sources,calls,fetchBytes,
  resolver:createKatexArchiveResolver({root,cacheRoot,pins,fetchBytes,limits})};
}
test('only the exact pinned KaTeX version is eligible; unrelated hosts, paths and credentials never fetch',async t=>{
 const f=await katexFixture(t);
 const forbidden=[
  katexBase.replace('0.16.9','0.16.10')+'katex.min.js',
  katexBase+'katex.min.js?token=private',katexBase+'katex.min.js#fragment',
  katexBase+'../package.json',katexBase+'%6batex.min.js',
  'https://user:password@cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js',
  katexBase.replace('cdn.jsdelivr.net','127.0.0.1')+'katex.min.js',
  katexBase.replace('https:','http:')+'katex.min.js','https://example.invalid/katex.min.js',
 ];
 for(const ref of forbidden)await assert.rejects(f.resolver(ref),/url_rejected/);
 assert.equal(f.calls.length,0);
 for(const address of ['127.0.0.1','10.1.2.3','169.254.169.254','192.168.1.1','172.20.0.1','::1','::ffff:127.0.0.1','fd00::1','fe80::1','2001:db8::1'])assert.equal(publicCdnAddress(address),false);
 assert.equal(publicCdnAddress('104.16.175.226'),true);assert.equal(publicCdnAddress('2606:4700::6810:afe2'),true);
});
test('CSS is complete only with every font and preserves URL-to-SHA records without executing scripts',async t=>{
 const f=await katexFixture(t),entries=await f.resolver(katexBase+'katex.min.css');
 assert.equal(entries.length,2);assert(entries.every(entry=>entry.status==='resolved'));
 assert.equal(entries[0].mimeType,'text/css');assert.equal(entries[1].mimeType,'font/woff2');
 assert.equal(entries[1].originalURL,katexBase+'fonts/KaTeX_Main-Regular.woff2');
 assert.equal(entries[1].dependencyOf,katexBase+'katex.min.css');assert.equal(entries[1].relativeRef,'fonts/KaTeX_Main-Regular.woff2');
 for(const entry of entries){assert.equal(digest(await fs.readFile(entry.sourcePath)),entry.sha256);assert.equal((await fs.stat(entry.sourcePath)).mode&0o777,0o600);}
 assert.equal((await f.resolver(katexBase+'katex.min.js'))[0].status,'resolved');
 assert.equal((await f.resolver(katexBase+'contrib/auto-render.min.js'))[0].status,'resolved');
 const other=path.join(f.directory,'another-document');await fs.mkdir(other);
 const cached=createKatexArchiveResolver({root:other,cacheRoot:f.cacheRoot,pins:f.pins,fetchBytes:()=>{throw Error('cache must avoid network');}});
 assert((await cached(katexBase+'katex.min.css')).every(entry=>entry.status==='resolved'));
 assert.equal(f.calls.length,4);
});
test('missing fonts, corrupt bytes and budgets keep the dependency unresolved',async t=>{
 const unavailable=await katexFixture(t,{fontFailure:true});
 const failed=await unavailable.resolver(katexBase+'katex.min.css');
 assert.equal(failed[0].status,'unresolved');assert.equal(failed[0].reason,'versioned_public_dependency_incomplete');
 assert.equal(failed[1].status,'unresolved');
 const limited=await katexFixture(t,{limits:{requests:1}});
 assert.equal((await limited.resolver(katexBase+'katex.min.css'))[0].status,'unresolved');assert.equal(limited.calls.length,1);
 const bad=await katexFixture(t);
 const corrupt=createKatexArchiveResolver({...bad,fetchBytes:async()=>Buffer.from('invalid CDN response')});
 assert.equal((await corrupt(katexBase+'katex.min.js'))[0].status,'unresolved');
 assert.deepEqual(await fs.readdir(bad.root),[]);
});
test('local bytes qualify only for the exact package version and expected file SHA',async t=>{
 const f=await katexFixture(t),localRoot=path.join(f.directory,'installed-katex');
 await fs.mkdir(path.join(localRoot,'dist'),{recursive:true});
 await fs.writeFile(path.join(localRoot,'package.json'),JSON.stringify({name:'katex',version:'0.16.9'}));
 await fs.writeFile(path.join(localRoot,'dist/katex.min.js'),f.sources['katex.min.js']);
 const local=createKatexArchiveResolver({...f,localRoot,fetchBytes:()=>{throw Error('same-version local bytes must avoid network');}});
 assert.equal((await local(katexBase+'katex.min.js'))[0].status,'resolved');
 const cacheRoot=path.join(f.directory,'other-cache');await fs.mkdir(cacheRoot);
 await fs.writeFile(path.join(localRoot,'package.json'),JSON.stringify({name:'katex',version:'0.16.38'}));
 let attempts=0;
 const other=createKatexArchiveResolver({...f,cacheRoot,localRoot,fetchBytes:()=>{attempts++;throw Error('network unavailable');}});
 assert.equal((await other(katexBase+'katex.min.js'))[0].status,'unresolved');assert.equal(attempts,1);
});
test('document input cannot replace the production release pins or qualify invented CDN bytes',async t=>{
 const snapshot=room([]);snapshot.scenes[0].content={type:'interactive',html:`<script src="${katexBase}contrib/auto-render.min.js"></script>`};
 const f=await fixture(t,snapshot),bytes=Buffer.from('invented code');let calls=0;
 const result=await resolveArchiveAssets({...f.input,pins:{'contrib/auto-render.min.js':[bytes.length,digest(bytes)]}},
  {...f.dependencies,downloadKatexBytes:async()=>{calls++;return bytes;}});
 assert.equal(result.unresolved.length,1);assert.equal(calls,1);assert.equal(f.calls.length,0);
 assert.equal(result.entries[0].sourcePath,undefined);
});
test('untrusted CSS URLs and symlink cache entries never escape the pinned font scope',async t=>{
 const f=await katexFixture(t),css=Buffer.from('@font-face{src:url(https://127.0.0.1/private)}');
 const resolver=createKatexArchiveResolver({...f,pins:{...f.pins,'katex.min.css':[css.length,digest(css)]},fetchBytes:async()=>css});
 assert.equal((await resolver(katexBase+'katex.min.css'))[0].status,'unresolved');
 const outside=path.join(f.directory,'outside.js');await fs.writeFile(outside,f.sources['katex.min.js']);
 await fs.symlink(outside,path.join(f.cacheRoot,f.pins['katex.min.js'][1]+'.js'));
 assert.equal((await f.resolver(katexBase+'katex.min.js'))[0].status,'unresolved');assert.equal(f.calls.length,0);
});
test('HTTPS redirects, oversized bodies and non-exact lengths are rejected without following Location',async()=>{
 for(const [statusCode,body,headers]of [[302,'',{location:'https://127.0.0.1/private'}],[200,'too long',{}],[200,'ok',{'content-length':'99'}]]){
  let calls=0;
  const request=(url,options,callback)=>{
   calls++;assert.equal(url,katexBase+'katex.min.js');assert.equal(options.headers['Accept-Encoding'],'identity');
   const req=new EventEmitter();req.destroy=()=>{};
   queueMicrotask(()=>{const response=Readable.from([Buffer.from(body)]);response.statusCode=statusCode;response.headers=headers;callback(response);});
   return req;
  };
  await assert.rejects(downloadKatexBytes(katexBase+'katex.min.js',{maxBytes:2,request}));
  assert.equal(calls,1);
 }
});

const threeBase='https://unpkg.com/three@0.160.0/';
const threeMap={imports:{three:threeBase+'build/three.module.js','three/addons/':threeBase+'examples/jsm/'}};
function threeRoom(code,map=threeMap){
 const snapshot=room([]);
 snapshot.scenes[0].content={type:'interactive',html:`<script type="importmap">${JSON.stringify(map)}</script><script type="module">${code}</script>`};
 return snapshot;
}
async function threeFixture(t,{limits={},moduleSource}={}){
 const directory=await fs.realpath(await fs.mkdtemp(path.join(process.env.MIRA_TASK_TMPDIR||os.tmpdir(),'archive-three-')));
 t.after(()=>fs.rm(directory,{recursive:true,force:true}));
 const root=path.join(directory,'assets'),cacheRoot=path.join(directory,'cache');await fs.mkdir(root);await fs.mkdir(cacheRoot);
 const sources={
  'build/three.module.js':Buffer.from('export class EventDispatcher{};throw Error("archive never executes code");'),
  'examples/jsm/controls/OrbitControls.js':Buffer.from(moduleSource||'import {EventDispatcher} from "three";export class OrbitControls extends EventDispatcher{};'),
  LICENSE:Buffer.from('MIT license fixture'),
  'package.json':Buffer.from(JSON.stringify({name:'three',version:'0.160.0'})),
 };
 const pins=Object.fromEntries(Object.entries(sources).map(([name,bytes])=>[name,[bytes.length,digest(bytes)]])),calls=[];
 const fetchBytes=async(url,options)=>{calls.push(url);const bytes=sources[url.slice(threeBase.length)];assert.equal(options.maxBytes,bytes.length);return bytes;};
 return{directory,root,cacheRoot,sources,pins,calls,fetchBytes,resolver:createThreeArchiveResolver({root,cacheRoot,pins,fetchBytes,limits})};
}
test('Three import maps expand actual static, export and literal dynamic modules without downloading directory declarations',()=>{
 const original=threeRoom('import * as THREE from "three";import {OrbitControls} from "three/addons/controls/OrbitControls.js";');
 const before=JSON.stringify(original),refs=enumerateSnapshotAssets(original).map(e=>e.ref);
 assert.deepEqual(refs.sort(),[threeBase+'build/three.module.js',threeBase+'examples/jsm/controls/OrbitControls.js'].sort());
 assert.equal(JSON.stringify(original),before);
 assert.deepEqual(enumerateSnapshotAssets(threeRoom('import * as THREE from "three";')).map(e=>e.ref),[threeBase+'build/three.module.js']);
 assert.deepEqual(enumerateSnapshotAssets(threeRoom('const unused=1;')),[]);
 const other=enumerateSnapshotAssets(threeRoom('export {OrbitControls} from "three/addons/controls/OrbitControls.js";import("three");'));
 assert.equal(other.length,2);assert(!other.some(e=>e.ref.endsWith('/')));
});
test('Three unknown addons, unmapped bare and computed imports remain explicit unresolved dependencies',async t=>{
 for(const code of ['import "unknown-package";','import(variableName);','import `three/addons/${addon}.js`;']){
  const entries=enumerateSnapshotAssets(threeRoom(code));
  assert(entries.some(e=>e.status==='unresolved'&&e.ref.startsWith('mira:three-')));
 }
 const unknown=threeRoom('import "three/addons/controls/UnknownControls.js";'),f=await fixture(t,unknown);let downloads=0;
 const result=await resolveArchiveAssets(f.input,{...f.dependencies,downloadThreeBytes:()=>{downloads++;throw Error('unknown addon must not download');}});
 assert.equal(result.unresolved.length,1);assert.equal(downloads,0);assert.equal(f.calls.length,0);
 const altered=enumerateSnapshotAssets(threeRoom('import "three/addons/controls/OrbitControls.js";',
  {imports:{...threeMap.imports,three:threeBase.replace('0.160.0','0.180.0')+'build/three.module.js'}}));
 assert(altered.some(e=>e.ref.includes('0.180.0')&&e.status==='unresolved'));
});
test('Three resolver preserves its exact transitive modules, package evidence and license bytes in private cache',async t=>{
 const f=await threeFixture(t),entries=await f.resolver(threeBase+'examples/jsm/controls/OrbitControls.js');
 assert.equal(entries.length,4);assert(entries.every(e=>e.status==='resolved'));assert.equal(f.calls.length,4);
 assert.deepEqual(entries[0].dependencyRefs,[threeBase+'build/three.module.js']);
 const license=entries.find(e=>e.originalURL===threeBase+'LICENSE');assert(license.packageEvidence);assert.equal(license.mimeType,'text/plain');
 for(const e of entries){assert.equal(digest(await fs.readFile(e.sourcePath)),e.sha256);assert.equal((await fs.stat(e.sourcePath)).mode&0o777,0o600);assert.equal(e.packageVersion,'0.160.0');}
 const other=path.join(f.directory,'other');await fs.mkdir(other);
 const cached=createThreeArchiveResolver({...f,root:other,fetchBytes:()=>{throw Error('no cache redownload');}});
 assert((await cached(threeBase+'examples/jsm/controls/OrbitControls.js')).every(e=>e.status==='resolved'));assert.equal(f.calls.length,4);
});
test('Three unknown transitive imports, incomplete bytes and finite budgets never qualify a complete dependency',async t=>{
 for(const moduleSource of ['import "three/addons/Unknown.js";','import "unknown-package";','import(variableName);']){
  const f=await threeFixture(t,{moduleSource});assert.equal((await f.resolver(threeBase+'examples/jsm/controls/OrbitControls.js'))[0].status,'unresolved');
 }
 const budget=await threeFixture(t,{limits:{requests:3}});
 assert.equal((await budget.resolver(threeBase+'examples/jsm/controls/OrbitControls.js'))[0].status,'unresolved');assert.equal(budget.calls.length,3);
 const bytes=await threeFixture(t,{limits:{totalBytes:1}});
 assert.equal((await bytes.resolver(threeBase+'build/three.module.js'))[0].status,'unresolved');assert.equal(bytes.calls.length,0);
 const corrupt=await threeFixture(t),resolver=createThreeArchiveResolver({...corrupt,fetchBytes:async()=>Buffer.from('not the pinned artifact')});
 assert.equal((await resolver(threeBase+'build/three.module.js'))[0].status,'unresolved');
 const pins={...corrupt.pins,'build/three.module.js':[2*1024**2+1,'a'.repeat(64)]};let calls=0;
 const oversized=createThreeArchiveResolver({...corrupt,pins,fetchBytes:()=>{calls++;throw Error('oversized pin must not fetch');}});
 assert.equal((await oversized(threeBase+'build/three.module.js'))[0].status,'unresolved');assert(calls<=2);
});
test('Three local package version, file SHA and symlink cache checks cannot substitute a different release',async t=>{
 const f=await threeFixture(t),localRoot=path.join(f.directory,'local');
 for(const [name,bytes]of Object.entries(f.sources)){const p=path.join(localRoot,name);await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,bytes);}
 const local=createThreeArchiveResolver({...f,localRoot,fetchBytes:()=>{throw Error('exact local bytes must avoid network');}});
 assert((await local(threeBase+'examples/jsm/controls/OrbitControls.js')).every(e=>e.status==='resolved'));
 const cacheRoot=path.join(f.directory,'wrong-version');await fs.mkdir(cacheRoot);
 await fs.writeFile(path.join(localRoot,'package.json'),JSON.stringify({name:'three',version:'0.180.0'}));
 const wrong=createThreeArchiveResolver({...f,cacheRoot,localRoot,fetchBytes:async()=>{throw Error('no replacement release');}});
 assert.equal((await wrong(threeBase+'build/three.module.js'))[0].status,'unresolved');
 const linkedCache=path.join(f.directory,'linked');await fs.mkdir(linkedCache);
 await fs.symlink(path.join(localRoot,'build/three.module.js'),path.join(linkedCache,f.pins['build/three.module.js'][1]+'.js'));
 const linked=createThreeArchiveResolver({...f,cacheRoot:linkedCache});assert.equal((await linked(threeBase+'build/three.module.js'))[0].status,'unresolved');
});
test('Three accepts only its four exact HTTPS artifact paths and has independent transport limits',async t=>{
 const f=await threeFixture(t),entry=threeBase+'build/three.module.js';
 for(const ref of [entry.replace('0.160.0','0.180.0'),entry+'?token=secret',entry+'#fragment',threeBase+'examples/jsm/',threeBase+'../package.json',entry.replace('unpkg.com','127.0.0.1'),entry.replace('https:','http:'),entry.replace('unpkg.com','user:password@unpkg.com')]){
  await assert.rejects(f.resolver(ref),/url_rejected/);assert.throws(()=>downloadThreeBytes(ref,{maxBytes:2}),/request_rejected/);
 }
 assert.equal(f.calls.length,0);assert.throws(()=>downloadThreeBytes(entry,{maxBytes:2*1024**2+1}),/request_rejected/);
 assert.throws(()=>downloadKatexBytes(katexBase+'katex.min.js',{maxBytes:512*1024+1}),/request_rejected/);
 for(const [statusCode,body,headers]of [[302,'',{location:'https://127.0.0.1/private'}],[200,'oversized',{}],[200,'ok',{'content-length':'3'}]]){
  let calls=0;
  const request=(url,options,callback)=>{
   calls++;assert.equal(url,entry);assert.equal(options.headers['Accept-Encoding'],'identity');
   options.lookup('127.0.0.1',{},error=>assert(error));
   const req=new EventEmitter();req.destroy=()=>{};
   queueMicrotask(()=>{const response=Readable.from([Buffer.from(body)]);response.statusCode=statusCode;response.headers=headers;callback(response);});return req;
  };
  await assert.rejects(downloadThreeBytes(entry,{maxBytes:2,request}));assert.equal(calls,1);
 }
});
test('Three document fields cannot override production file pins',async t=>{
 const snapshot=threeRoom('import "three";'),f=await fixture(t,snapshot),fake=Buffer.from('invented code');
 const result=await resolveArchiveAssets({...f.input,pins:{'build/three.module.js':[fake.length,digest(fake)]}},
  {...f.dependencies,downloadThreeBytes:async()=>fake});
 assert(result.unresolved.some(e=>e.ref===threeBase+'build/three.module.js'));assert.equal(f.calls.length,0);
});
test('new asset copies retain one GiB and existing verified caches remain readable without extra reserve',async t=>{
 const f=await threeFixture(t),bytes=Buffer.from('protected asset'),hash=digest(bytes),reserve=1024**3;
 let checks=0;
 await assert.rejects(saveBytes(f.root,hash,'.bin',bytes,{statfs:async()=>{checks++;return{bavail:reserve+bytes.length-1,bsize:1};}}),/disk_space_insufficient/);
 assert.deepEqual(await fs.readdir(f.root),[]);assert.equal(checks,1);
 const saved=await saveBytes(f.root,hash,'.bin',bytes,{statfs:async()=>{checks++;return{bavail:BigInt(reserve+bytes.length),bsize:1n};}});
 assert.equal(digest(await fs.readFile(saved)),hash);assert.equal((await fs.stat(saved)).mode&0o777,0o600);assert.equal(checks,2);
 assert.equal(await saveBytes(f.root,hash,'.bin',bytes,{statfs:()=>{throw Error('cache hit must not reserve new space');}}),saved);
 await fs.writeFile(saved,'changed');
 await assert.rejects(saveBytes(f.root,hash,'.bin',bytes,{statfs:()=>{throw Error('must reject stale bytes first');}}),/staging_conflict/);
 await fs.unlink(saved);const elsewhere=path.join(f.directory,'elsewhere');await fs.writeFile(elsewhere,bytes);await fs.symlink(elsewhere,saved);
 await assert.rejects(saveBytes(f.root,hash,'.bin',bytes,{statfs:()=>{throw Error('must reject symlink first');}}),/staging_conflict/);
 for(const stat of [{bavail:-1,bsize:4096},{bavail:NaN,bsize:4096},{bavail:100,bsize:0}])assert.throws(()=>assertAssetWriteBudget(stat,1),/space_unavailable/);
});
