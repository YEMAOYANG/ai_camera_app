import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {canonical,enumerateSnapshotAssets,resolveArchiveAssets} from './course-archive-assets.mjs';

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
