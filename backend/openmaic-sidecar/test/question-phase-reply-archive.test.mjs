import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {prepareQuestionPhaseReplyArchive,QUESTION_PHASE_REPLY_ARCHIVE_SCHEMA} from '../src/question-phase-reply-archive.mjs';

const request={requestId:'paid-reply-fixture',phase:'independent_verification',phaseOrdinal:11,gradeCode:'primary_6',subject:'math',skillBoundary:{skillId:'fraction_ratio_percentage'},objectivePolicy:{difficultyCode:'standard'},provider:{name:'fixture',model:'fixture'},mode:'live'};
test('exact unparsed reply survives parsing failure in a private independent archive',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'phase-reply-'));
  try {
    const archive=await prepareQuestionPhaseReplyArchive(request,{root,now:()=>123});
    const content='not JSON: this original paid reply must remain available';
    await archive.save({content,providerRequestIdHash:'a'.repeat(64),inputTokens:100,outputTokens:20,billingEvidence:'reported',untrustedExtra:'never archived'});
    assert.throws(()=>JSON.parse(content));
    const data=JSON.parse(await fs.readFile(archive.finalPath,'utf8'));
    assert.equal(data.schemaVersion,QUESTION_PHASE_REPLY_ARCHIVE_SCHEMA);
    assert.equal(data.content,content);assert.equal(data.difficultyCode,'standard');
    assert.equal(data.inputSha256,archive.inputSha256);assert.equal('untrustedExtra' in data,false);
    assert.equal((await fs.stat(archive.finalPath)).mode&0o777,0o600);
    await assert.rejects(()=>prepareQuestionPhaseReplyArchive(request,{root}));
    await assert.rejects(()=>archive.save({content}));
  } finally {await fs.rm(root,{recursive:true,force:true});}
});
test('fake mode creates no paid archive and exclusive intent blocks concurrent dispatch',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'phase-reply-'));
  try {
    assert.equal(await prepareQuestionPhaseReplyArchive({...request,mode:'fake'},{root}),null);
    assert.deepEqual(await fs.readdir(root),[]);
    await prepareQuestionPhaseReplyArchive(request,{root});
    await assert.rejects(()=>prepareQuestionPhaseReplyArchive(request,{root}));
  } finally {await fs.rm(root,{recursive:true,force:true});}
});
