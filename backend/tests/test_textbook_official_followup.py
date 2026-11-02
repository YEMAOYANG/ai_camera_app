"""Synthetic operator attestation; no Codex transcript, provider or real student data."""
from copy import deepcopy
import unittest

from content.textbook_catalog import digest
from content.textbook_official_followup import verify_operator_attestation, validate_effective_review


class OperatorAttestationTest(unittest.TestCase):
    def setUp(self):
        self.auth = {'resourceType': 'video', 'authorizedBy': 'user',
            'question': 'May this specific lesson revision waive the unavailable video?',
            'answer': 'Only this lesson and revision.', 'userMessageId': '01a18197-1ef0-7432-8793-5f7c2d98b025',
            'authorizedAt': '2026-10-28T16:18:47.152+08:00',
            'timeSource': 'uuidv7_message_id_timestamp_not_server_signed', 'recordedBy': 'operator',
            'recordedAt': '2026-10-28T16:23:54+08:00'}
        self.operator = {'question': self.auth['question'], 'answer': self.auth['answer'],
                         'userMessageId': self.auth['userMessageId'],
                         'reviewer': 'operator', 'basis': 'I checked the authentic current user conversation.'}
    def test_caller_must_supply_the_verified_message_not_just_a_sealed_json(self):
        with self.assertRaises(ValueError): verify_operator_attestation(self.auth, None)
        verify_operator_attestation(self.auth, self.operator)
        for field in ('question', 'answer', 'userMessageId', 'reviewer', 'basis'):
            broken = {**self.operator, field: '' if field in ('reviewer', 'basis') else 'different'}
            with self.assertRaises(ValueError, msg=field): verify_operator_attestation(self.auth, broken)
    def test_uuid_time_cannot_be_relabelled(self):
        with self.assertRaises(ValueError):
            verify_operator_attestation({**self.auth, 'authorizedAt': '2026-10-28T15:00:00+08:00'}, self.operator)


class ReviewProjectionTest(unittest.TestCase):
    def test_nonvideo_material_changes_never_hide_behind_new_exception(self):
        resources = {k: {'status': 'reviewed', 'findings': [k]} for k in ('courseware','teachingDesign','learningTaskSheet','afterClassExercise')}
        resources['video'] = {'status': 'waived_unavailable', 'method': 'old'}
        old = {'reviewExceptions': [{'resourceType': 'video'}], 'classHours': [{'classHourId': 'lesson_1', 'resources': resources}]}
        new = deepcopy(old); new['reviewExceptions'] = [{'resourceType': 'video', 'authorizedAt':'new'}];new['classHours'][0]['resources']['video']['method'] = 'corrected'
        nonvideo = {k: resources[k] for k in ('courseware','teachingDesign','learningTaskSheet','afterClassExercise')}
        validate_effective_review(old,new,['lesson_1'],digest(nonvideo))
        new['classHours'][0]['resources']['courseware']['findings'] = ['fabricated']
        with self.assertRaises(ValueError): validate_effective_review(old,new,['lesson_1'],digest(nonvideo))


class FollowupEvidenceTest(unittest.TestCase):
    def setUp(self):
        import hashlib, json, pathlib, tempfile
        from tests.test_textbook_official_resource_review import reviewed_official_resources
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.course = pathlib.Path(temp.name).resolve() / 'teaching-1'; self.job = self.course / 'authoring-job'; self.job.mkdir(parents=True)
        source = self.course / 'source-input/sources'; source.mkdir(parents=True)
        binding = {'editionId':'edition-one','revisionId':'revision-one','nodeId':'lesson-one',
            'gradeCode':'primary_1','subject':'chinese','volume':'upper','schoolSystem':'six_year'}
        self.original = reviewed_official_resources(binding)
        video = self.original['classHours'][0]['resources']['video']; video['status'] = 'waived_unavailable'; video.pop('videoModalityReview')
        old = {'resourceType':'video','binding':binding,'classHourIds':['lesson_1'],'authorizedBy':'user',
               'authorizedAt':'2026-10-26T17:00:00+08:00','userInstruction':'ambiguous old words','reason':'old interpretation'}
        self.original['reviewExceptions'] = [old]
        self.auth = {'resourceType':'video','authorizedBy':'user','question':'May this exact lesson waive video?',
            'answer':'Only this lesson and revision.','userMessageId':'01a18197-1ef0-7432-8793-5f7c2d98b025',
            'authorizedAt':'2026-10-28T16:18:47.152+08:00','timeSource':'uuidv7_message_id_timestamp_not_server_signed',
            'recordedBy':'recorder','recordedAt':'2026-10-28T16:23:54+08:00'}
        self.operator = {'question':self.auth['question'],'answer':self.auth['answer'],'userMessageId':self.auth['userMessageId'],
                         'reviewer':'operator','basis':'Checked the authentic conversation.'}
        meta = lambda p:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'byteSize':p.stat().st_size}
        entries = []
        for index,kind in enumerate(('courseware','teachingDesign','learningTaskSheet','afterClassExercise')):
            image=source/f'{kind}.jpg'; image.write_bytes(f'synthetic-{index}'.encode())
            resource=self.original['classHours'][0]['resources'][kind];resource['resourceId']=f'resource-{index}'
            entries.append({'resourceType':kind,'resourceId':resource['resourceId'],'classHourId':'lesson_1','page':1,
                'path':image.name,'sourceUrl':resource['sourceUrl'],'byteSize':image.stat().st_size,'sha256':meta(image)['sha256']})
        self.image = source / 'courseware.jpg'
        manifest = source/'manifest.json'; manifest.write_text(json.dumps({'binding':binding,'entries':entries}))
        self.original['sourceManifest']={'path':manifest.name,'sha256':meta(manifest)['sha256']}
        review_file=source/'original-review.json';review_file.write_text(json.dumps(self.original))
        post=source/'post.json';post.write_text('{}')
        self.draft={'scopeReview':{'officialResourceReview':self.original,'postClassPractice':{'sourcePath':str(post),
            'sourceSha256':meta(post)['sha256'],'officialResourceReviewSha256':digest(self.original)}}}
        self.frozen={'binding':binding,'teachingRevision':'1','requestSha256':'9'*64,
                     'sceneContract':{'sha256':'a'*64},'authorDispatchContract':{'sha256':'b'*64}}
        self.dispatch={'createdAt':'2026-10-28T14:00:00+08:00','requestSha256':'c'*64}
        for name,value in [('draft.json',self.draft),('frozen.json',self.frozen),('dispatch.json',self.dispatch)]:
            (self.job/name).write_text(json.dumps(value))
        source_draft=self.course/'source-input/request-draft.json';source_draft.write_bytes((self.job/'draft.json').read_bytes())
        self.proof={'sessionId':'session','stageId':'stage','nativeDocumentSha256':'d'*64,'authoringSourceSha256':'e'*64,
                    'candidateSha256':'f'*64,'candidateFileSha256':'1'*64}
        self.chain={'sha256':'2'*64}
        effective=deepcopy(self.original);effective['reviewExceptions'][0].update(authorizedAt=self.auth['authorizedAt'],
            userInstruction=self.auth['answer'],reason='Explicit current scoped user permission.')
        self.record={'schemaVersion':'mira.textbook.official-resource-review-followup.v1','status':'authorized_for_current_review_followup',
            'verification':'authorization_record_only_not_play_audio_or_publication','binding':binding,'teachingRevision':'1','classHourIds':['lesson_1'],
            'authorization':self.auth,'originals':{'jobDir':str(self.job),'frozen':meta(self.job/'frozen.json'),
                'draft':meta(self.job/'draft.json'),'dispatch':meta(self.job/'dispatch.json'),'sourceDraft':meta(source_draft),
                'requestSha256':self.dispatch['requestSha256'],'sceneContractSha256':'a'*64,'authorDispatchContractSha256':'b'*64},
            'currentNative':{'sessionId':'session','stageId':'stage','documentSha256':'d'*64,'authoringSourceSha256':'e'*64,
                'candidateSha256':'f'*64,'candidateFileSha256':'1'*64,'completeSceneReviewFollowupSha256':'2'*64},
            'priorReview':{'sha256':digest(self.original),'reviewExceptions':[old],'priorAuthorizationInterpretation':'insufficiently_explicit','correction':'No retroactive claim.'},
            'effectiveReview':effective,'unchangedEvidence':{'nonVideoResourcesSha256':digest({k:self.original['classHours'][0]['resources'][k] for k in ('courseware','teachingDesign','learningTaskSheet','afterClassExercise')}),
                'postClassPracticeSource':meta(post),'officialSourceManifest':{**meta(manifest),'entryCount':4},'originalReviewFile':meta(review_file)},
            'evidenceBoundaries':['No audio or publication acceptance.']}
        self._write()
    def _write(self):
        import json
        self.record.pop('sha256',None);self.record['sha256']=digest(self.record)
        self.path=self.course/'review-followups/official-video-exception'/self.record['sha256']/'review-followup.json';self.path.parent.mkdir(parents=True,exist_ok=True);self.path.write_text(json.dumps(self.record))
    def check(self, *, operator=None, proof=None):
        from unittest.mock import patch
        from content.textbook_official_followup import validate_followup
        with patch('content.textbook_official_resource_review.validate_new_course_post_class_practice'):
            return validate_followup(self.path,self.record['sha256'],self.operator if operator is None else operator,
                job=self.job,frozen=self.frozen,draft=self.draft,dispatch=self.dispatch,native_proof=proof or self.proof,followup=self.chain)
    def test_exact_bound_source_and_explicit_operator_pass(self):
        self.assertEqual(self.check()['followupSha256'],self.record['sha256'])
        with self.assertRaises(ValueError): self.check(operator={})
        with self.assertRaises(ValueError): self.check(operator={**self.operator,'answer':'different'})
    def test_changed_original_image_or_stale_native_is_rejected(self):
        with self.assertRaises(ValueError): self.check(proof={**self.proof,'candidateSha256':'0'*64})
        self.image.write_bytes(b'tampered')
        with self.assertRaises(ValueError): self.check()
    def test_resealed_cross_lesson_or_changed_nonvideo_is_rejected(self):
        self.record['binding']['nodeId']='other';self._write()
        with self.assertRaises(ValueError): self.check()
        self.record['binding']['nodeId']='lesson-one'
        self.record['effectiveReview']['classHours'][0]['resources']['courseware']['findings']=['fabricated'];self._write()
        with self.assertRaises(ValueError): self.check()
    def test_published_proof_binds_operator_review_source_and_followup(self):
        from content.textbook_official_followup import validate_frozen_followup
        summary = self.check(); native = {**self.proof, 'followupSha256':self.chain['sha256']}
        validate_frozen_followup(summary,native)
        with self.assertRaises(ValueError):
            validate_frozen_followup({**summary,'effectiveReviewSha256':'0'*64},native)
        with self.assertRaises(ValueError):
            validate_frozen_followup(summary,{**native,'candidateSha256':'0'*64})
        changed=deepcopy(summary);changed['operatorAttestation']['answer']='not the actual decision'
        with self.assertRaises(ValueError): validate_frozen_followup(changed,native)
