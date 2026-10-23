#!/usr/bin/env node
/** Read only the assets referenced by one authoritative Native course capture. */
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const NATIVE=path.join(ROOT,'openmaic-runtime/.runtime/OpenMAIC');
const require=createRequire(path.join(NATIVE,'package.json'));
const {enumerateAssetManifest}=await import(pathToFileURL(path.join(NATIVE,'packages/@openmaic/dsl/dist/index.js')));
const {DOMParser}=require('linkedom');
const parseSrcset=require('parse-srcset');
const parseCssValue=require('postcss-value-parser');
const ts=require('typescript');
const MAX_BYTES=768*1024**2,MAX_TOTAL=4*1024**3,MAX_INPUT=128*1024**2;
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
export function canonical(value){
 const sorted=x=>Array.isArray(x)?x.map(sorted):x&&typeof x==='object'?Object.fromEntries(Object.entries(x).sort(([a],[b])=>a<b?-1:a>b?1:0).map(([k,v])=>[k,sorted(v)])):x;
 return JSON.stringify(sorted(value));
}
function classroom(ref){
 if(typeof ref!=='string')return false;
 let logical=ref;
 if(/^https?:/i.test(ref)){
  try{const url=new URL(ref);if(!['localhost','127.0.0.1','[::1]'].includes(url.hostname)||url.username||url.password||url.search||url.hash)return false;logical=url.pathname;}
  catch{return false;}
 }
 return /^\/api\/classroom-media\/[A-Za-z0-9_-]+\/(?:audio|media)\/[A-Za-z0-9_.-]+$/.test(logical)&&!logical.includes('..');
}
const inline=ref=>typeof ref==='string' && /^(?:#|data:(?:(?:image|audio|video|font)\/[a-z0-9.+-]+|application\/(?:font[a-z0-9.+-]*|x-font[a-z0-9.+-]*|vnd.ms-fontobject))[;,])/i.test(ref);
const plain=ref=>typeof ref==='string' && ref && !/[\x00-\x1f\x7f-\x9f]/.test(ref);
const NAMESPACES=new Set(['http://www.w3.org/2000/svg','http://www.w3.org/1999/xhtml','http://www.w3.org/1999/xlink','http://www.w3.org/XML/1998/namespace','http://www.w3.org/2000/xmlns/']);
const classroomDirectory=ref=>typeof ref==='string'&&/^\/api\/classroom-media\/[A-Za-z0-9_-]+\/media\/$/.test(ref);
const staticPublic=ref=>typeof ref==='string'&&/^\/(?:review-assets\/v3-world-action\/[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|webp)|avatars\/teacher-[1-9][0-9]*\.png)$/.test(ref);

function htmlReferences(html){
 const result=[];
 if(typeof html!=='string'||!html)return result;
 const document=new DOMParser().parseFromString(html,'text/html');
 const add=(ref,kind)=>{if(typeof ref==='string'&&ref.trim())result.push({ref:ref.trim(),kind});};
 for(const node of document.querySelectorAll('img,video,audio,source,image,use,input[type="image"],object,embed,iframe,script[src],link[href]')){
  const tag=node.localName;
  const parent=node.parentElement?.localName;
  const kind=tag==='video'?'video':tag==='audio'?'audio':tag==='source'?(parent==='audio'?'audio':parent==='video'?'video':'image'):['img','image','input'].includes(tag)?'image':'dependency';
  add(node.getAttribute('src')||node.getAttribute('href')||node.getAttribute('xlink:href')||node.getAttribute('data'),kind);
  if(tag==='video')add(node.getAttribute('poster'),'poster');
  if(node.hasAttribute('srcset'))for(const entry of parseSrcset(node.getAttribute('srcset')))add(entry.url,kind);
  // Nested srcdoc is inert while parsing; its own media still belongs to the archive.
  if(tag==='iframe'&&node.hasAttribute('srcdoc'))result.push(...htmlReferences(node.getAttribute('srcdoc')));
 }
 for(const node of document.querySelectorAll('[style],style')){
  const css=node.localName==='style'?node.textContent:node.getAttribute('style');
  parseCssValue(css).walk(value=>{
   if(value.type==='function'&&value.value.toLowerCase()==='url'){
    add(parseCssValue.stringify(value.nodes).trim().replace(/^(['"])(.*)\1$/s,'$2'),'dependency');return false;
   }
  });
  // String-form @import does not have a url() node.
  for(const match of css.matchAll(/@import\s+(['"])([^'"\n]+)\1/gi))add(match[2],'dependency');
 }
 // Allocated ids interpolated by a generated activity's script have no DOM
 // src yet. Capture explicit literals; never run or evaluate the activity.
 for(const script of document.querySelectorAll('script')){
  // Parse JavaScript literals without evaluating it. A regexp over quoted
  // source accidentally retained the backslash in nested escaped SVG markup.
  const source=ts.createSourceFile('course.js',script.textContent,ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);
  const visit=node=>{
   if(ts.isStringLiteral(node)||ts.isNoSubstitutionTemplateLiteral(node)){
    const value=node.text;
    if(!NAMESPACES.has(value)&&/^(?:ast_|https?:\/\/|\/\/|blob:|file:|\/api\/classroom-media\/|\/review-assets\/|\/avatars\/)/.test(value))add(value,'dependency');
    if(value.includes('<')&&value.includes('>'))result.push(...htmlReferences(value));
   }
   ts.forEachChild(node,visit);
  };
  visit(source);
 }
 return result;
}

export function enumerateSnapshotAssets(snapshot){
 if(!snapshot || !snapshot.stage || !Array.isArray(snapshot.scenes))throw Error('archive_asset_snapshot_invalid');
 const bridges=new Map();
 for(const scene of snapshot.scenes)for(const action of scene.actions || []){
  if(action.type==='speech' && plain(action.audioId) && (classroom(action.audioUrl)||inline(action.audioUrl))){
   const urls=bridges.get(action.audioId)||new Set();urls.add(action.audioUrl);bridges.set(action.audioId,urls);
  }
 }
 const allocated=[];
 const visit=value=>{
  if(Array.isArray(value)){for(const child of value)visit(child);return;}
  if(!value||typeof value!=='object')return;
  for(const [key,child]of Object.entries(value)){
   if(['allocatedAssetId','assetId'].includes(key)&&plain(child))allocated.push({ref:child,kind:'dependency'});
   else visit(child);
  }
 };
 visit(snapshot);
 const speechUrls=snapshot.scenes.flatMap(scene=>(scene.actions||[]).filter(action=>action.type==='speech'&&plain(action.audioUrl)).map(action=>({ref:action.audioUrl,kind:'audio'})));
 const discovered=[...enumerateAssetManifest(snapshot).entries,...snapshot.scenes.flatMap(scene=>htmlReferences(scene.content?.html)),...speechUrls,...allocated];
 const unique=new Map(discovered.map(entry=>[entry.kind+'\0'+entry.ref,entry]));
 return [...unique.values()].map(({ref,kind})=>{
  const urls=kind==='audio'?bridges.get(ref):undefined;
  const bridge=urls?.size===1?[...urls][0]:undefined;
  const effective=bridge || ref;
  return {ref,kind,...(bridge?{mappedRef:bridge}:{}),status:inline(effective)?'inline':classroom(effective)?'already_collected':'unresolved',
   ...(!inline(effective)&&!classroom(effective)?{reason:classroomDirectory(effective)?'controlled_classroom_media_directory':'asset_bytes_unresolved'}:{})};
 });
}

function dotenv(text){
 const values={};for(const line of text.split(/\r?\n/)){const m=line.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/);if(m)values[m[1]]=m[2].replace(/^(['"])(.*)\1$/,'$2');}return values;
}
async function configuration(){
 let file={};try{file=dotenv(await fs.readFile(path.join(ROOT,'backend/.env'),'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
 const value=key=>process.env[key] ?? file[key];
 // The launcher maps this backend-owned key to Native's DATABASE_URL. Never
 // infer the URL from a second dotenv or initialize application/schema writers.
 return {url:value('MIRA_OPENMAIC_AGENT_DATABASE_URL'),manifestPath:value('COURSE_STORAGE_MANIFEST_PATH'),bucket:value('ASSET_S3_BUCKET'),region:value('AWS_REGION')||value('AWS_DEFAULT_REGION'),
  endpoint:value('AWS_ENDPOINT_URL_S3')||value('AWS_ENDPOINT_URL'),accessKeyId:value('AWS_ACCESS_KEY_ID'),secretAccessKey:value('AWS_SECRET_ACCESS_KEY'),sessionToken:value('AWS_SESSION_TOKEN')};
}
async function directory(target,roots){
 if(typeof target!=='string'||!path.isAbsolute(target))throw Error('archive_asset_staging_invalid');
 const absolute=path.resolve(target);
 const allowed=roots.find(root=>absolute.startsWith(root+path.sep));
 if(!allowed)throw Error('archive_asset_staging_outside_private_root');
 // Walk all existing ancestors, including the trusted root itself; never
 // create or follow a symlink to a source or unrelated directory.
 let current=path.parse(absolute).root;
 for(const segment of absolute.slice(current.length).split(path.sep).filter(Boolean)){
  current=path.join(current,segment);
  try{const stat=await fs.lstat(current);if(stat.isSymbolicLink()||!stat.isDirectory())throw Error('archive_asset_staging_symlink');}
  catch(error){if(error.code!=='ENOENT')throw error;await fs.mkdir(current,{mode:0o700});}
 }
 return absolute;
}
async function readJson(filename){
 let current=filename;
 while(current!==path.dirname(current)){const stat=await fs.lstat(current);if(stat.isSymbolicLink())throw Error('archive_asset_authority_symlink');current=path.dirname(current);}
 const stat=await fs.stat(filename);if(!stat.isFile()||stat.size>MAX_INPUT)throw Error('archive_asset_authority_invalid');
 return JSON.parse(await fs.readFile(filename,'utf8'));
}
const references=snapshot=>new Set(enumerateSnapshotAssets(snapshot).map(e=>e.ref));

async function authorize(db,snapshot,stageId,dependencies){
 const own=await db.query('SELECT owner_id,data FROM document_stages WHERE id=$1',[stageId]);
 const stage=own.rows[0];
 const allowedShared=new Set();
 if(stage){
  const rows=await db.query('SELECT data FROM document_scenes WHERE stage_id=$1 ORDER BY scene_order,id',[stageId]);
  for(const ref of references({stage:stage.data,scenes:rows.rows.map(row=>row.data)}))allowedShared.add(ref);
 }
 const digest=sha(canonical(snapshot));
 const exists=await db.query("SELECT to_regclass('mira_course_archive_events') AS relation");
 let eventOwner;
 if(exists.rows[0]?.relation){
  const event=await db.query(`SELECT session.owner_id FROM mira_course_archive_events event
   LEFT JOIN agent_sessions session ON session.id=event.session_id
   WHERE event.stage_id=$1 AND event.source_digest=$2 AND event.snapshot_json=$3::jsonb LIMIT 1`,[stageId,digest,JSON.stringify(snapshot)]);
  if(event.rows.length){eventOwner=event.rows[0].owner_id;for(const ref of references(snapshot))allowedShared.add(ref);}
 }
 const nativeRoot=dependencies.nativeRoot||NATIVE;
 const paths=[path.join(nativeRoot,'data/classrooms',stageId+'.json'),path.join(nativeRoot,'data/classrooms',stageId,'artifact/classroom.json')];
 const state=dependencies.stateRoot||path.join(ROOT,'backend/data/course-storage');
 paths.push(path.join(state,'archive-events','legacy-'+sha(stageId+':'+digest)+'.json'));
 for(const filename of paths){
  try{
   const value=await readJson(filename),document=value.schemaVersion==='mira.course-archive.event.v1'?value.snapshot:value;
   if(document?.stage?.id!==stageId)continue;
   // Retained source documents may be a later revision: only the references
   // actually present in that authority qualify for shared-principal access.
   for(const ref of references(document))allowedShared.add(ref);
  }catch(error){if(error.code!=='ENOENT')throw error;}
 }
 return {owner:stage?.owner_id||eventOwner,allowedShared};
}
async function s3Bytes(config,hash,expected){
 const {S3Client,GetObjectCommand}=require('@aws-sdk/client-s3');
 const credentials=config.accessKeyId&&config.secretAccessKey?{accessKeyId:config.accessKeyId,secretAccessKey:config.secretAccessKey,...(config.sessionToken?{sessionToken:config.sessionToken}:{})}:undefined;
 const client=new S3Client({...(config.region?{region:config.region}:{}),...(config.endpoint?{endpoint:config.endpoint}:{}),...(credentials?{credentials}:{}),maxAttempts:2});
 try{
  const response=await client.send(new GetObjectCommand({Bucket:config.bucket,Key:hash}));
  const chunks=[];let size=0;
  for await(const chunk of response.Body){size+=chunk.length;if(size>expected){response.Body.destroy?.();throw Error('archive_asset_byte_size_mismatch');}chunks.push(chunk);}
  return Buffer.concat(chunks);
 }finally{client.destroy();}
}
function extension(mime,kind){
 const allowed={
  'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp','image/gif':'.gif','image/svg+xml':'.svg','image/avif':'.avif',
  'audio/wav':'.wav','audio/x-wav':'.wav','audio/mpeg':'.mp3','audio/ogg':'.ogg','audio/mp4':'.m4a','audio/webm':'.webm',
  'video/mp4':'.mp4','video/webm':'.webm','video/ogg':'.ogv',
  'application/pdf':'.pdf','model/gltf-binary':'.glb','font/woff':'.woff','font/woff2':'.woff2','font/ttf':'.ttf','font/otf':'.otf',
 };
 const family=kind==='audio'?'audio/':kind==='video'?'video/':'image/';
 return typeof mime==='string'&&(kind==='dependency'||mime.startsWith(family))?allowed[mime]:undefined;
}
async function saveBytes(root,digest,ext,bytes){
 const filename=path.join(root,digest+ext);
 try{const handle=await fs.open(filename,'wx',0o600);try{await handle.writeFile(bytes);await handle.sync();}finally{await handle.close();}}
 catch(error){if(error.code!=='EEXIST')throw error;const stat=await fs.lstat(filename);if(stat.isSymbolicLink()||!stat.isFile()||sha(await fs.readFile(filename))!==digest)throw Error('archive_asset_staging_conflict');}
 return filename;
}
async function publicBytes(ref,nativeRoot){
 const root=path.join(nativeRoot,'public'),filename=path.resolve(root,'.'+ref);
 if(!filename.startsWith(root+path.sep)||await fs.realpath(filename)!==filename)throw Error('archive_static_source_path_invalid');
 let current=filename;
 while(current!==path.dirname(root)){const stat=await fs.lstat(current);if(stat.isSymbolicLink())throw Error('archive_static_source_symlink');current=path.dirname(current);}
 const stat=await fs.stat(filename);if(!stat.isFile()||stat.size<1||stat.size>32*1024**2)throw Error('archive_static_source_invalid');
 return fs.readFile(filename);
}
async function directoryChildren(ref,config,dependencies){
 const parts=ref.split('/'),stageId=parts[3],nativeRoot=dependencies.nativeRoot||NATIVE;
 const sourcePrefix='openmaic-runtime/.runtime/OpenMAIC/data/classrooms/'+stageId+'/media/';
 const filenames=new Set(),safeImage=name=>/^[A-Za-z0-9_.-]+\.(?:png|jpg|jpeg|webp|gif|avif|svg)$/i.test(name)&&!name.includes('..');
 const directory=path.join(nativeRoot,'data/classrooms',stageId,'media');
 try{
  if(await fs.realpath(directory)!==directory)throw Error('archive_media_directory_symlink');
  let current=directory;while(current!==path.dirname(nativeRoot)){if((await fs.lstat(current)).isSymbolicLink())throw Error('archive_media_directory_symlink');current=path.dirname(current);}
  const names=await fs.readdir(directory,{withFileTypes:true});
  if(names.length>512)throw Error('archive_media_directory_limit');
  for(const entry of names){if(entry.isSymbolicLink())throw Error('archive_media_directory_symlink');if(entry.isFile()&&safeImage(entry.name))filenames.add(entry.name);}
 }catch(error){if(error.code!=='ENOENT')throw error;}
 if(config.manifestPath){
  const manifest=await readJson(config.manifestPath);
  if(!['mira.course-storage.manifest.v1','mira.course-storage.manifest.v2'].includes(manifest.schemaVersion)||!Array.isArray(manifest.files))throw Error('archive_media_manifest_invalid');
  for(const file of manifest.files){
   if(typeof file.path!=='string'||!file.path.startsWith(sourcePrefix))continue;
   const name=file.path.slice(sourcePrefix.length);
   if(safeImage(name)&&/^image\//.test(file.mimeType||'')&&/^[a-f0-9]{64}$/.test(file.sha256||'')&&Number.isSafeInteger(file.byteSize)&&file.byteSize>0)filenames.add(name);
  }
 }
 if(filenames.size===0||filenames.size>512)throw Error('archive_media_directory_unavailable_or_oversized');
 return [...filenames].sort().map(name=>({ref:ref+name,kind:'image',status:'already_collected'}));
}

export async function resolveArchiveAssets(input,dependencies={}){
 const {snapshot,stageId,stagingRoot}=input;
 if(typeof stageId!=='string'||!/^[A-Za-z0-9_-]{1,255}$/.test(stageId)||snapshot?.stage?.id!==stageId)throw Error('archive_asset_stage_identity_invalid');
 const entries=enumerateSnapshotAssets(snapshot);
 if(entries.length>12000)throw Error('archive_asset_reference_limit');
 if(!entries.some(e=>e.status==='unresolved'))return {schemaVersion:'mira.course-archive.assets.v1',entries,unresolved:[]};
 const roots=dependencies.allowedRoots||[path.join(ROOT,'backend/data/course-storage/archives'),...(process.env.MIRA_TASK_TMPDIR?[await fs.realpath(process.env.MIRA_TASK_TMPDIR)]:[])];
 const target=await directory(stagingRoot,roots);
 const config=dependencies.config||await configuration();
 for(const entry of [...entries]){
  if(entry.status!=='unresolved')continue;
  if(staticPublic(entry.ref)){
   try{
    const bytes=await publicBytes(entry.ref,dependencies.nativeRoot||NATIVE),digest=sha(bytes),ext=path.extname(entry.ref).toLowerCase();
    const mimeType={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}[ext];
    Object.assign(entry,{status:'resolved',sourcePath:await saveBytes(target,digest,ext,bytes),sha256:digest,byteSize:bytes.length,mimeType});delete entry.reason;
   }catch{entry.reason='controlled_public_asset_missing_or_invalid';}
  }else if(classroomDirectory(entry.ref)){
   try{entries.push(...await directoryChildren(entry.ref,config,dependencies));entry.status='already_collected';entry.expandedDirectory=true;delete entry.reason;}
   catch{entry.reason='controlled_classroom_media_directory_unavailable';}
  }
 }
 const pending=entries.filter(e=>e.status==='unresolved'&&!staticPublic(e.ref)&&!classroomDirectory(e.ref)&&plain(e.ref)&&!/^(?:[a-z][a-z0-9+.-]*:|\/)/i.test(e.ref));
 if(!pending.length)return {schemaVersion:'mira.course-archive.assets.v1',entries,unresolved:entries.filter(e=>e.status==='unresolved')};
 let db=dependencies.db;
 if(!db){
  if(!config.url||!['postgres:','postgresql:'].includes(new URL(config.url).protocol))throw Error('archive_asset_database_unavailable');
  const {Client}=require('pg');db=new Client({connectionString:config.url,statement_timeout:30000,connectionTimeoutMillis:10000});await db.connect();
 }
 try{
  await db.query('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY');
  const authority=await authorize(db,snapshot,stageId,dependencies);
  const cache=new Map();let total=0;
  for(const entry of pending){
   const {ref,kind}=entry;
   // Never fetch a URL taken from document content. Only the registry's exact
   // opaque ID is queried, then its content hash selects an existing byte layer.
   if(!plain(ref)||/^(?:[a-z][a-z0-9+.-]*:|\/)/i.test(ref)){entry.reason='unsupported_external_asset_reference';continue;}
   try{
    let result=cache.get(ref);
    if(!result){
     const rows=await db.query(`SELECT entry.content_hash,entry.mime,blob.byte_size
      FROM asset_entries entry JOIN asset_blobs blob ON blob.content_hash=entry.content_hash
      WHERE entry.id=$1 AND (entry.principal=$2 OR ($3::boolean AND entry.principal='shared'))
      ORDER BY CASE WHEN entry.principal=$2 THEN 0 ELSE 1 END LIMIT 1`,[ref,authority.owner||null,authority.allowedShared.has(ref)]);
     const row=rows.rows[0],size=Number(row?.byte_size);
     if(!row||!/^sha256-[a-f0-9]{64}$/.test(row.content_hash)||!Number.isSafeInteger(size)||size<1||size>MAX_BYTES)throw Error('archive_asset_identity_missing_or_oversized');
     let bytes;
     if(dependencies.readBytes)bytes=await dependencies.readBytes(row.content_hash,size);
     else if(config.bucket)bytes=await s3Bytes(config,row.content_hash,size);
     else{const value=await db.query('SELECT bytes FROM asset_blobs WHERE content_hash=$1',[row.content_hash]);bytes=value.rows[0]?.bytes;}
     if(!bytes||bytes.length!==size||sha(bytes)!==row.content_hash.slice(7))throw Error('archive_asset_bytes_invalid');
     total+=size;if(total>MAX_TOTAL)throw Error('archive_asset_total_limit');
     const ext=extension(row.mime,kind);if(!ext)throw Error('archive_asset_mime_kind_mismatch');
     const digest=sha(bytes),sourcePath=await saveBytes(target,digest,ext,bytes);
     result={sourcePath,sha256:digest,byteSize:size,mimeType:row.mime};cache.set(ref,result);
    }
    const ext=extension(result.mimeType,kind);if(!ext)throw Error('archive_asset_mime_kind_mismatch');
    Object.assign(entry,{status:'resolved',...result});delete entry.reason;
   }catch{entry.reason='asset_bytes_unavailable_or_invalid';}
  }
  await db.query('ROLLBACK');
  return {schemaVersion:'mira.course-archive.assets.v1',entries,unresolved:entries.filter(e=>e.status==='unresolved')};
 }catch(error){await db.query('ROLLBACK').catch(()=>{});throw error;}
 finally{if(!dependencies.db)await db.end();}
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 let raw='';try{
  for await(const chunk of process.stdin){raw+=chunk;if(Buffer.byteLength(raw)>MAX_INPUT)throw Error('archive_asset_input_limit');}
  console.log(JSON.stringify(await resolveArchiveAssets(JSON.parse(raw))));
 }catch{console.error(JSON.stringify({error:'course_archive_assets_failed'}));process.exitCode=1;}
}
