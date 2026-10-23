import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {inventoryCourseMaterials} from './course-material-inventory.mjs';

const ROOT=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(path.join(ROOT,'openmaic-runtime/.runtime/OpenMAIC/packages/@openmaic/storage/package.json'));
const {PGlite}=require('@electric-sql/pglite');
const raw=mime=>'raw.'+Buffer.from(mime).toString('base64url');
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
async function fixture(t){
  const db=new PGlite();t.after(()=>db.close());
  await db.exec(`CREATE TABLE agent_sessions(id text primary key,owner_id text,stage_id text,active_stage_id text);
    CREATE TABLE document_stages(id text primary key,owner_id text,data jsonb);
    CREATE TABLE document_outlines(stage_id text primary key,data jsonb);
    CREATE TABLE agent_session_materials(id text primary key,session_id text,kind text,title text,
      text_asset_id text,raw_asset_id text,derived_from text);
    CREATE TABLE owner_material(id text primary key,owner_id text,mime text,bytes bigint,original_name text,
      oss_key text,sha256 text,status text,deleted_at bigint);
    CREATE TABLE mira_course_archive_events(session_id text,stage_id text,source_digest text);
    CREATE TABLE agent_session_events(session_id text,type text,data jsonb);
    INSERT INTO agent_sessions VALUES('producer','owner-one','placeholder',NULL),
      ('edit-session','owner-one','stage-one',NULL),('other-course','owner-one','unrelated',NULL),
      ('foreign-owner','owner-two','stage-one',NULL);
    INSERT INTO document_stages VALUES('stage-one','owner-one','{"id":"stage-one"}');
    INSERT INTO document_outlines VALUES('stage-one','{"producerRef":"producer"}');`);
  const calls=[];
  const client={query:async(sql,values)=>{calls.push(sql);return db.query(sql,values);}};
  async function material(id,session='producer',changes={}){
    const row={kind:'source',title:'教材图片.png',text:null,raw:`materials/${session}/${id}/${raw('image/png')}`,derived:null,...changes};
    await db.query('INSERT INTO agent_session_materials VALUES($1,$2,$3,$4,$5,$6,$7)',
      [id,session,row.kind,row.title,row.text,row.raw,row.derived]);
  }
  return {db,client,calls,material};
}
test('only a course producer and its exact owner originals are enumerated; all queries stay read only',async t=>{
  const f=await fixture(t);
  await f.material('mat_source');
  await f.material('mat_text','producer',{kind:'extraction',raw:null,text:'materials/producer/mat_text/text.md',derived:'mat_source',title:'提取课文'});
  await f.material('mat_unrelated','other-course');
  await f.db.query('INSERT INTO owner_material VALUES($1,$2,$3,$4,$5,$6,$7,$8,NULL)',
    ['mat_source','owner-one','image/png',123,'教材原图.png','materials/owner-one/mat_source','a'.repeat(64),'ready']);
  const result=await inventoryCourseMaterials({stageId:'stage-one',sessionId:'producer',bindingKind:'frozen_authoring'},{client:f.client});
  assert.deepEqual(result.boundSessions,['producer']);assert.equal(result.materials.length,3);
  const owner=result.materials.find(item=>item.role==='owner');
  assert.equal(owner.originalName,'教材原图.png');assert.equal(owner.byteSize,123);assert.equal(owner.sha256,'a'.repeat(64));
  assert(!JSON.stringify(result).includes('mat_unrelated'));
  assert(f.calls.every(sql=>/^(?:SELECT|BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY|ROLLBACK)/.test(sql)));
  assert.equal(f.calls.at(-1),'ROLLBACK');
  const again=await inventoryCourseMaterials({stageId:'stage-one',sessionId:'producer'},{client:f.client});
  assert.equal(again.dependencySha256,result.dependencySha256);
});
test('stage lookup collects every proven edit session and never other courses or foreign owners',async t=>{
  const f=await fixture(t);
  await f.material('mat_source');await f.material('mat_edit','edit-session');
  await f.material('mat_unrelated','other-course');await f.material('mat_foreign','foreign-owner');
  const result=await inventoryCourseMaterials({stageId:'stage-one'},{client:f.client});
  assert.deepEqual(result.boundSessions,['edit-session','producer']);assert.equal(result.materials.length,2);
  await assert.rejects(inventoryCourseMaterials({stageId:'stage-one',sessionId:'foreign-owner'},{client:f.client}));
  await assert.rejects(inventoryCourseMaterials({stageId:'stage-one',sessionId:'other-course'},{client:f.client}));
});
test('an exact Backend frozen authoring binding supports old placeholder sessions without a Native receipt',async t=>{
  const f=await fixture(t);
  await f.db.query("UPDATE agent_sessions SET stage_id='old-placeholder' WHERE id='edit-session'");
  await f.material('mat_edit','edit-session');
  await assert.rejects(inventoryCourseMaterials({stageId:'stage-one',sessionId:'edit-session'},{client:f.client}));
  const result=await inventoryCourseMaterials({stageId:'stage-one',sessionId:'edit-session',bindingKind:'frozen_authoring'},{client:f.client});
  assert.equal(result.materials.length,1);
  await assert.rejects(inventoryCourseMaterials({stageId:'stage-one',sessionId:'foreign-owner',bindingKind:'frozen_authoring'},{client:f.client}));
});
test('saved event and stage creation receipt bind interrupted producer sessions',async t=>{
  const f=await fixture(t);
  await f.db.query("UPDATE agent_sessions SET stage_id='placeholder' WHERE id='edit-session'");
  await f.db.query('INSERT INTO agent_session_events VALUES($1,$2,$3)',
    ['edit-session','library_changed',{change:'stage_created',stageId:'stage-one'}]);
  await f.material('mat_edit','edit-session');
  const receipt=await inventoryCourseMaterials({stageId:'stage-one',sessionId:'edit-session'},{client:f.client});
  assert.equal(receipt.materials.length,1);
  await f.db.exec('DELETE FROM agent_session_events');
  await f.db.query('INSERT INTO mira_course_archive_events VALUES($1,$2,$3)',['edit-session','stage-one','a'.repeat(64)]);
  const event=await inventoryCourseMaterials({stageId:'stage-one',sessionId:'edit-session',sourceDigest:'a'.repeat(64)},{client:f.client});
  assert.equal(event.materials.length,1);
  await assert.rejects(inventoryCourseMaterials({stageId:'stage-one',sessionId:'edit-session',sourceDigest:'b'.repeat(64)},{client:f.client}));
});
test('a deleted historical stage requires exact event evidence, not a stale session target',async t=>{
  const f=await fixture(t);await f.material('mat_edit','edit-session');
  await f.db.exec('DELETE FROM document_stages');
  await assert.rejects(inventoryCourseMaterials({stageId:'stage-one',sessionId:'edit-session'},{client:f.client}));
  await f.db.query('INSERT INTO mira_course_archive_events VALUES($1,$2,$3)',['edit-session','stage-one','a'.repeat(64)]);
  const result=await inventoryCourseMaterials({stageId:'stage-one',sessionId:'edit-session',sourceDigest:'a'.repeat(64)},{client:f.client});
  assert.equal(result.materials.length,1);
});
test('derivatives change the dependency digest and forged material paths are rejected',async t=>{
  const f=await fixture(t);await f.material('mat_source');
  const before=await inventoryCourseMaterials({stageId:'stage-one',sessionId:'producer'},{client:f.client});
  await f.material('mat_text','producer',{kind:'extraction',raw:null,text:'materials/producer/mat_text/text.md',derived:'mat_source'});
  const after=await inventoryCourseMaterials({stageId:'stage-one',sessionId:'producer'},{client:f.client});
  assert.notEqual(after.dependencySha256,before.dependencySha256);
  for(const key of ['materials/foreign/mat_source/'+raw('image/png'),'materials/producer/../private/'+raw('image/png'),
    'materials/producer/mat_source/raw.bm90LWEtbWltZQ']){
    await f.db.query('UPDATE agent_session_materials SET raw_asset_id=$1 WHERE id=$2',[key,'mat_source']);
    await assert.rejects(inventoryCourseMaterials({stageId:'stage-one',sessionId:'producer'},{client:f.client}));
    assert.equal(f.calls.at(-1),'ROLLBACK');
  }
});
test('owner records are joined by exact owner and material id, with finalized integrity evidence',async t=>{
  const f=await fixture(t);await f.material('mat_source');
  await f.db.query('INSERT INTO owner_material VALUES($1,$2,$3,$4,$5,$6,$7,$8,NULL)',
    ['mat_source','owner-two','image/png',123,'别人的图.png','materials/owner-two/mat_source','a'.repeat(64),'ready']);
  const result=await inventoryCourseMaterials({stageId:'stage-one',sessionId:'producer'},{client:f.client});
  assert.equal(result.materials.length,1);
  await f.db.query("UPDATE owner_material SET owner_id='owner-one',oss_key='materials/owner-one/mat_source',sha256=NULL");
  await assert.rejects(inventoryCourseMaterials({stageId:'stage-one',sessionId:'producer'},{client:f.client}));
});
test('no material table is a valid empty dependency set, never a schema write',async t=>{
  const f=await fixture(t);await f.db.exec('DROP TABLE agent_session_materials');
  const result=await inventoryCourseMaterials({stageId:'stage-one',sessionId:'producer'},{client:f.client});
  assert.deepEqual(result.materials,[]);assert.equal(result.dependencySha256,hash('[]'));
});
