"""Real immutable files and isolated SQL; provider/MinIO calls are injected, never live."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

from PIL import Image

from content.learning_review_content import SOURCE_SCHEMA, ReviewContentError, canonical, digest, public_question, validate_questions
from services import learning_review_content as content

REAL_REQUIRE_ARCHIVED_PACK = content.require_archived_pack


class FakeProvider:
    provider_name = 'configured-provider'
    model_name = 'configured-model'

    def __init__(self, outputs):
        self.outputs = list(outputs); self.requests = []

    def complete(self, **request):
        self.requests.append(request)
        output = self.outputs.pop(0)
        return None if output is None else SimpleNamespace(text=json.dumps(output), provider=self.provider_name, model=self.model_name)


class ReviewContentTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=os.getenv('MIRA_TASK_TMPDIR'))
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.pack_root = self.root / 'output/learning-review-content'
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {'COURSE_STORAGE_MODE': 'local', 'COURSE_STORAGE_ARCHIVE_ENABLED': '0'}).start()
        patch.object(content, 'ROOT', self.root).start()
        patch.object(content, 'PACK_ROOT', self.pack_root).start()
        def archived(directory, sha):
            receipt=content.read_json(Path(directory)/'archive-receipt.json')
            content.require(receipt.get('complete') is True and receipt.get('sourceDigest')==sha,'review_pack_not_archived')
        patch.object(content,'require_archived_pack',side_effect=archived).start()
        self.db = sqlite3.connect(':memory:'); self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.executescript('''
          CREATE TABLE learning_courses(id TEXT,version TEXT,subject TEXT,grade_code TEXT,status TEXT);
          CREATE TABLE learning_textbook_course_builds(content_key TEXT,edition_id TEXT,revision_id TEXT,node_id TEXT,
            course_id TEXT,course_version TEXT,status TEXT,review_json TEXT);
          CREATE TABLE learning_sessions(id TEXT,family_id TEXT,child_id TEXT,course_id TEXT,course_version TEXT,status TEXT,completed_at INTEGER);
          CREATE TABLE learning_answer_events(family_id TEXT,child_id TEXT,grade_code TEXT,source_kind TEXT,
            revoked_at INTEGER,confirmed INTEGER,correct INTEGER,question_json TEXT);
        ''')
        self.db.execute("INSERT INTO learning_courses VALUES ('course','v1','chinese','primary_1','published')")
        self.db.execute('INSERT INTO learning_textbook_course_builds VALUES (?,?,?,?,?,?,?,?)',
            ('content-key','edition','r1','u4-l6','course','v1','published',json.dumps({'release':{'sha256':'a'*64}})))
        official = self.root / 'output/source.txt'; official.parent.mkdir(parents=True); official.write_text('已核练习：根据图片理解写字、打雷，不以头像颜色判断。')
        assets=[]
        for i, color in enumerate(('red','green','blue')):
            path = self.root / 'output' / f'picture-{i}.png'
            Image.new('RGB',(100,100),color).save(path)
            assets.append({'id':f'picture{i}','path':str(path),'sha256':content.raw_sha(path.read_bytes()),'mimeType':'image/png','meaning':('写字','打雷','叠被子')[i]})
        self.source={'schemaVersion':SOURCE_SCHEMA,
            'binding':{'editionId':'edition','revisionId':'r1','nodeId':'u4-l6','gradeCode':'primary_1','subject':'chinese','volume':'upper'},
            'sourceIdentity':{'courseId':'course','courseVersion':'v1','contentKey':'content-key','releaseSha256':'a'*64,'title':'语文园地四'},
            'officialExercise':{'path':str(official),'sha256':content.raw_sha(official.read_bytes()),
                'sourceKind':'reviewed-official-assignment-record','originalFileDownloaded':False,
                'sourceUrl':'https://basic.smartedu.cn/resource','locations':['第1页第1题'],
                'reviewer':'verified-operator','reviewedAt':'2026-10-26T10:00:00+08:00','exerciseText':official.read_text(),
                'findings':['根据人物动作辨认词义，不预先告知答案']},
            'objectives':[{'id':'writing-word','label':'词义辨认','knowledgeId':'chinese:primary_1:edition:u4-l6:word','targetTexts':['xiě zì']}],
            'originalScope':{'allowed':['本课六个动作词的图片理解'],'excluded':['不引入未学音节，不自动评定发音']},'media':assets}
        self.q={'id':'q1','targetId':'writing-word','prompt':'听一听，点正在写字的图片。','visualAssetId':'picture2',
            'options':[{'value':'A','label':'第一幅','pictureAssetId':'picture0'},{'value':'B','label':'第二幅','pictureAssetId':'picture1'}],
            'correctAnswer':'A','hints':['看看手里的物品。'],'explanation':'手握着笔，笔尖接着纸。','estimatedSeconds':70,
            'assessmentMode':'listening_picture','evidenceClaim':{'observed':['选择图片'],'supports':['图音支持词义辨认'],'doesNotSupport':['独立发音、纸笔书写或完整掌握']}}
        self.provider = FakeProvider([{'questions':[self.q]}, {'answers':[{'id':'q1','answer':'A','accepted':True,'reason':'根据手笔纸的关系判断'}]}])
        self.producer = content.ReviewPackProducer(root=self.pack_root,provider=self.provider)
        self.child={'id':'child-a','family_id':'family-a','grade_code':'primary_1'}

    def generate(self):
        self.producer.prepare(self.source,request_id='job-one',question_count=1,conn=self.db)
        return self.producer.generate('job-one')

    def media(self, draft):
        teacher=draft['teacherContract']; result=[]
        for i,t in enumerate([self.q['prompt'],*self.q['hints'],self.q['explanation']]):
            path=self.root/'output'/f'voice-{i}.wav'
            stream=io.BytesIO()
            with wave.open(stream,'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(bytes([i+1,0])*24000)
            path.write_bytes(stream.getvalue())
            proof={'providerId':'qwen-tts','fallbackUsed':False,'textSha256':content.raw_sha(t.encode()),
                'sha256':content.raw_sha(path.read_bytes()),'voiceId':teacher['voiceId'],'teacherProfileId':teacher['teacherProfile']['id']}
            receipt=self.root/'output'/f'voice-{i}-receipt.json';receipt.write_text(canonical(proof))
            result.append({'id':f'voice{i}','path':str(path),'sha256':proof['sha256'],'mimeType':'audio/wav','meaning':t,
                'text':t,'providerId':'qwen-tts','fallbackUsed':False,'voiceId':teacher['voiceId'],
                'teacherProfileId':teacher['teacherProfile']['id'],'providerReceiptPath':str(receipt),
                'providerReceiptSha256':content.raw_sha(receipt.read_bytes())})
        return result

    def approve(self):
        draft=self.generate()
        review={'draftSha256':digest(draft),'reviewer':'real-reviewer','reviewedAt':'2026-10-26T11:00:00+08:00','basis':'逐图核对、实际听录音和独立核题',
            'reviewKind':'ai','humanListeningVerified':False,
            **{k:True for k in ('sourceScopeConfirmed','originalExpressionConfirmed','imagesConfirmed','teacherAudioConfirmed','independentAnswersConfirmed','approvedForStudent')}}
        approved=self.producer.approve('job-one',media=self.media(draft),review=review,conn=self.db)
        # Storage is a separately tested injected boundary; eligibility tests
        # still require its saved completion receipt before student reads.
        content.immutable(Path(approved['path']).parent/'archive-receipt.json',
            {'complete':True,'sourceDigest':approved['packSha256']})
        return approved

    def test_generation_has_two_real_protocol_calls_and_frozen_receipts_then_replay_is_free(self):
        draft=self.generate();again=self.producer.generate('job-one')
        self.assertEqual(draft,again);self.assertEqual(len(self.provider.requests),2)
        verification=json.loads(self.provider.requests[1]['user_prompt'])
        self.assertNotIn('correctAnswer',verification['questions'][0])
        self.assertNotIn('explanation',verification['questions'][0])
        self.assertEqual(draft['generation']['model'],'configured-model')
        self.assertEqual(draft['generation']['sourceSha256'],digest(self.source))

    def test_unresolved_dispatch_cannot_retry_after_worker_restart(self):
        self.producer.prepare(self.source,request_id='job-one',question_count=1,conn=self.db)
        self.provider.outputs=[None]
        with self.assertRaisesRegex(ReviewContentError,'dispatch_ambiguous'):self.producer.generate('job-one')
        restarted=content.ReviewPackProducer(root=self.pack_root,provider=self.provider)
        with self.assertRaisesRegex(ReviewContentError,'dispatch_ambiguous'):restarted.generate('job-one')
        with self.assertRaisesRegex(ReviewContentError,'source_dispatch_ambiguous'):
            restarted.prepare(self.source,request_id='renamed-job',question_count=1,conn=self.db)
        self.assertEqual(len(self.provider.requests),1)

    def test_assignment_record_hash_is_not_claimed_as_a_downloaded_official_pdf(self):
        record={'schemaVersion':'mira.textbook.post-class-practice.v1','binding':self.source['binding'],
            'reviewedAt':'2026-10-26T10:00:00+08:00',
            'sources':[{'classHourId':'lesson_1','sourceUrl':'https://basic.smartedu.cn/resource',
                'locations':['课后练习第1页'],'findings':['原练习要求朗读时间词，再做原创迁移。'],
                'sourceKind':'reviewed-official-assignment-record','originalFileDownloaded':False}],
            'goals':[{'targetId':'time','objective':'理解时间词'}]}
        path=self.root/'output/assignment-record.json';path.write_text(canonical(record))
        source=content.source_from_assignment_record(path,source_identity=self.source['sourceIdentity'],
            media=self.source['media'],reviewer='actual-reader')
        self.assertEqual(source['officialExercise']['sha256'],content.raw_sha(path.read_bytes()))
        self.assertEqual(source['officialExercise']['sourceKind'],'reviewed-official-assignment-record')
        self.assertFalse(source['officialExercise']['originalFileDownloaded'])

    def test_qwen_narration_is_bounded_frozen_and_does_not_repeat_after_readback(self):
        draft=self.generate();requests=[]
        def transport(payload,headers):
            requests.append(payload);stream=io.BytesIO()
            with wave.open(stream,'wb') as w:
                w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000)
                w.writeframes(bytes([len(requests),0])*24000)
            import base64
            return {'success':True,'audioId':payload['audioId'],'format':'wav','base64':base64.b64encode(stream.getvalue()).decode()}
        result=self.producer.narrate('job-one',transport=transport)
        replay=self.producer.narrate('job-one',transport=lambda *_:self.fail('must reuse saved TTS response'))
        self.assertEqual(result,replay);self.assertEqual(len(requests),3)
        self.assertTrue(all(r['ttsProviderId']=='qwen-tts' and r['ttsVoice']==draft['teacherContract']['voiceId'] for r in requests))
        media=content.read_json(result['mediaPath']);self.assertEqual(len(media),3)
        self.assertTrue(all(Path(a['providerReceiptPath']).is_file() for a in media))

    def test_unknown_tts_never_retries(self):
        self.generate();calls=[]
        def failing(*args):calls.append(1);raise TimeoutError()
        with self.assertRaisesRegex(ReviewContentError,'audio_dispatch_ambiguous'):self.producer.narrate('job-one',transport=failing)
        with self.assertRaisesRegex(ReviewContentError,'audio_dispatch_ambiguous'):self.producer.narrate('job-one',transport=failing)
        self.assertEqual(len(calls),1)

    def test_chinese_latin_text_cannot_go_through_unverified_plain_tts(self):
        self.q['hints']=['请听：xiě zì。']
        self.generate()
        with self.assertRaisesRegex(ReviewContentError,'pronunciation_review_required'):
            self.producer.narrate('job-one',transport=lambda *_:self.fail('unverified pinyin cannot dispatch'))

    def test_changed_original_or_release_is_rejected_before_provider(self):
        wrong=deepcopy(self.source);wrong['sourceIdentity']['releaseSha256']='b'*64
        with self.assertRaisesRegex(ReviewContentError,'source_mismatch'):
            self.producer.prepare(wrong,request_id='job-one',question_count=1,conn=self.db)
        self.producer.prepare(self.source,request_id='job-one',question_count=1,conn=self.db)
        Path(self.source['officialExercise']['path']).write_text('changed')
        with self.assertRaises(ValueError):self.producer.generate('job-one')
        self.assertEqual(self.provider.requests,[])

    def test_independent_disagreement_never_approves_or_retries(self):
        self.provider.outputs[1]['answers'][0]['answer']='B'
        with self.assertRaisesRegex(ReviewContentError,'independent_verification_failed'):self.generate()
        with self.assertRaisesRegex(ReviewContentError,'independent_verification_failed'):self.producer.generate('job-one')
        self.assertEqual(len(self.provider.requests),2)
        self.assertFalse((self.pack_root/'jobs/job-one/draft.json').exists())

    def test_reordered_identical_options_are_not_a_new_variant(self):
        q2=deepcopy(self.q);q2['id']='q2';q2['options'].reverse()
        with self.assertRaisesRegex(ReviewContentError,'question_duplicate'):
            validate_questions([self.q,q2],self.source)

    def test_scene_cannot_reveal_an_answer_by_exact_picture_matching(self):
        q=deepcopy(self.q);q['visualAssetId']='picture0'
        with self.assertRaisesRegex(ReviewContentError,'picture_match_shortcut'):validate_questions([q],self.source)

    def test_target_is_visible_and_spoken_instruction_cannot_contain_it(self):
        q=deepcopy(self.q);q.update(assessmentMode='pinyin_picture',targetText='xiě zì',prompt='看看拼音，点一幅图。')
        got=validate_questions([q],self.source)[0]
        self.assertEqual(got['targetText'],'xiě zì')
        q['prompt']='请听：xiě zì。'
        with self.assertRaisesRegex(ReviewContentError,'target_narration'):validate_questions([q],self.source)

    def test_approved_pack_not_draft_enters_pool_only_after_real_completed_learning(self):
        self.generate()
        self.assertEqual(content.approved_question_pool(self.db,self.child)[0],[])
        approved=self.approve()
        self.db.execute("INSERT INTO learning_sessions VALUES ('opened','family-a','child-a','course','v1','in_progress',NULL)")
        self.assertEqual(content.approved_question_pool(self.db,self.child)[0],[])
        self.db.execute("UPDATE learning_sessions SET status='completed',completed_at=100 WHERE id='opened'")
        questions,gaps=content.approved_question_pool(self.db,self.child)
        self.assertEqual(gaps,[]);self.assertEqual(len(questions),1)
        self.assertTrue(questions[0]['learnedScopeVerified']);self.assertEqual(questions[0]['packSha256'],approved['packSha256'])
        self.assertEqual(questions[0]['sourceIdentity']['releaseSha256'],'a'*64)
        self.assertEqual(content.approved_question_pool(self.db,{**self.child,'family_id':'family-other'})[0],[])
        self.assertEqual(len(self.provider.requests),2)

    def test_approval_without_completed_archive_is_not_student_content(self):
        approved=self.approve()
        (Path(approved['path']).parent/'archive-receipt.json').unlink()
        self.db.execute("INSERT INTO learning_sessions VALUES ('learned','family-a','child-a','course','v1','completed',100)")
        questions,gaps=content.approved_question_pool(self.db,self.child)
        self.assertEqual(questions,[]);self.assertEqual(len(gaps),1)

    def test_archive_readiness_checks_current_storage_identity_and_registry_locator(self):
        approved=self.approve();directory=Path(approved['path']).parent;sha=approved['packSha256']
        receipt={'schemaVersion':'mira.course-archive.verification.v1','complete':True,'sourceDigest':sha,
            'archiveId':'review-'+sha[:24],'storage':{'endpoint':'https://storage.test','bucket':'study','region':'us-east-1'}}
        (directory/'archive-receipt.json').write_text(canonical(receipt))
        from core.course_storage_config import CourseStorageConfig
        cfg=SimpleNamespace(mode='registry',endpoint='https://storage.test',bucket='study',region='us-east-1')
        with patch.object(CourseStorageConfig,'from_env',return_value=cfg),patch.object(content,'CourseFileStore') as store:
            store.return_value.resolve.return_value=None
            with self.assertRaisesRegex(ReviewContentError,'not_registered'):REAL_REQUIRE_ARCHIVED_PACK(directory,sha)
            store.return_value.resolve.return_value={'sha256':content.raw_sha((directory/'pack.json').read_bytes())}
            REAL_REQUIRE_ARCHIVED_PACK(directory,sha)
            receipt['storage']['bucket']='different-bucket';(directory/'archive-receipt.json').write_text(canonical(receipt))
            with self.assertRaisesRegex(ReviewContentError,'not_archived'):REAL_REQUIRE_ARCHIVED_PACK(directory,sha)

    def test_archive_proof_survives_eviction_of_the_local_upload_receipt(self):
        approved=self.approve();directory=Path(approved['path']).parent;sha=approved['packSha256']
        (directory/'archive-receipt.json').unlink()
        receipt={'schemaVersion':'mira.course-archive.verification.v1','complete':True,'sourceDigest':sha,
            'archiveId':'review-'+sha[:24],'storage':{'endpoint':'https://storage.test','bucket':'study','region':'us-east-1'}}
        from core.course_storage_config import CourseStorageConfig
        cfg=SimpleNamespace(mode='registry',endpoint='https://storage.test',bucket='study',region='us-east-1')
        with patch.object(CourseStorageConfig,'from_env',return_value=cfg),patch.object(content,'CourseFileStore') as store:
            store.return_value.repository.scope.return_value={'metadata':{'archiveVerification':receipt}}
            store.return_value.resolve.return_value={'sha256':content.raw_sha((directory/'pack.json').read_bytes())}
            REAL_REQUIRE_ARCHIVED_PACK(directory,sha)
            receipt['sourceDigest']='b'*64
            with self.assertRaisesRegex(ReviewContentError,'not_archived'):REAL_REQUIRE_ARCHIVED_PACK(directory,sha)

    def test_original_file_cannot_escape_workspace_through_parent_components(self):
        path=self.root/'output/../../outside.txt'
        with self.assertRaisesRegex(ReviewContentError,'path_invalid'):
            content.checked_file(path)

    def test_exact_answer_evidence_can_include_one_goal_without_completing_whole_lesson(self):
        self.approve()
        question={'courseId':'course','courseVersion':'v1','targetId':'writing-word'}
        self.db.execute('INSERT INTO learning_answer_events VALUES (?,?,?,?,?,?,?,?)',
            ('family-a','child-a','primary_1','textbook_play',None,1,0,json.dumps(question)))
        self.assertEqual(len(content.approved_question_pool(self.db,self.child)[0]),1)
        self.db.execute('UPDATE learning_answer_events SET revoked_at=200')
        self.assertEqual(content.approved_question_pool(self.db,self.child)[0],[])

    def test_approval_requires_actual_audio_and_exact_teacher_receipt(self):
        draft=self.generate()
        review={'draftSha256':digest(draft),'reviewer':'reviewer','reviewedAt':'2026-10-26T11:00:00+08:00','basis':'actual check',
            'reviewKind':'ai','humanListeningVerified':False,
            **{k:True for k in ('sourceScopeConfirmed','originalExpressionConfirmed','imagesConfirmed','teacherAudioConfirmed','independentAnswersConfirmed','approvedForStudent')}}
        with self.assertRaisesRegex(ReviewContentError,'exact_teacher_audio_missing'):
            self.producer.approve('job-one',media=[],review=review,conn=self.db)
        media=self.media(draft);media[0]['voiceId']='wrong-teacher'
        with self.assertRaisesRegex(ReviewContentError,'teacher_identity_mismatch'):
            self.producer.approve('job-one',media=media,review=review,conn=self.db)

    def test_ai_review_is_allowed_but_cannot_misrepresent_human_listening(self):
        approved=self.approve()
        pack=content.read_json(approved['path'])
        self.assertEqual(pack['review']['reviewKind'],'ai');self.assertFalse(pack['review']['humanListeningVerified'])
        review={**pack['review'],'humanListeningVerified':True}
        with self.assertRaisesRegex(ReviewContentError,'listening_evidence_misrepresented'):
            self.producer.approve('job-one',media=self.media(self.generate()),review=review,conn=self.db)

    def test_bad_unrelated_pack_does_not_break_healthy_pack_media(self):
        approved=self.approve()
        token='reviewpack.'+self.source['media'][0]['sha256']+'.png'
        bad=self.pack_root/'packs'/('0'*64);bad.mkdir(parents=True);(bad/'approval.json').write_text('{}')
        self.assertEqual(content.review_pack_media_file(token).read(),Path(self.source['media'][0]['path']).read_bytes())

    def test_media_serves_the_verified_remote_bytes_instead_of_reopening_local_file(self):
        self.approve()
        asset=self.source['media'][0];token='reviewpack.'+asset['sha256']+'.png'
        local=Path(asset['path']);original=local.read_bytes()
        with patch.object(content,'checked_media',return_value=(local,b'verified-remote-image')):
            self.assertEqual(content.review_pack_media_file(token).read(),b'verified-remote-image')
        self.assertEqual(local.read_bytes(),original)

    def test_archive_verifies_before_registering_and_freezes_all_originals(self):
        approved=self.approve();calls=[]
        class Client:
            def upload(client,index_path):
                index=json.loads(index_path.read_text());calls.append('upload_verified')
                return {'schemaVersion':'mira.course-archive.verification.v1','complete':True,'storage':{'endpoint':'https://storage.test','bucket':'study','region':'us-east-1'},
                    'archiveId':index['archiveId'],'indexSha256':content.raw_sha(index_path.read_bytes()),'sourceDigest':approved['packSha256'],
                    'objects':[{'objectKey':e['relativePath'],'sha256':e['sha256'],'byteSize':e['byteSize'],'etag':'verified-etag'} for e in index['generatedPublicFiles']]}
        class Repository:
            def register_scope(repo,scope,files,storage,**kwargs):
                calls.append('register');repo.files=files;repo.scope=scope
            def activate_missing_heads(repo,*args):calls.append('activate')
        repo=Repository();config=SimpleNamespace(mode='registry',endpoint='https://storage.test',bucket='study',region='us-east-1')
        (Path(approved['path']).parent/'archive-receipt.json').unlink()
        result=content.archive_pack(approved['packSha256'],root=self.pack_root,client=Client(),repository=repo,config=config)
        self.assertEqual(calls,['upload_verified','register','activate']);self.assertEqual(result['status'],'archived')
        self.assertEqual(repo.scope['sourceKind'],'review_question_pack')
        self.assertEqual(repo.scope['archiveVerification']['sourceDigest'],approved['packSha256'])
        self.assertTrue(any(x['sourcePath'].endswith('source.txt') for x in repo.files))
        self.assertTrue(all(x['locator']['kind']=='zip_member' for x in repo.files))

    def test_changed_approved_asset_cannot_be_uploaded_as_a_new_frozen_original(self):
        approved=self.approve()
        Path(self.source['media'][0]['path']).write_bytes(b'changed after approval')
        client=SimpleNamespace(upload=lambda *_:self.fail('upload must not run'))
        with self.assertRaises(ValueError):
            content.archive_pack(approved['packSha256'],root=self.pack_root,client=client,
                repository=SimpleNamespace(),config=SimpleNamespace(mode='registry'))

    def test_existing_authenticated_media_route_keeps_image_and_stream_audio_types(self):
        from flask import Flask
        from routes.api.v2.student_reviews import student_reviews_bp
        app=Flask(__name__);app.config.update(TESTING=True,LEARNING_REVIEW_ENABLED=True)
        app.register_blueprint(student_reviews_bp,url_prefix='/api/v2/student/learning/reviews')
        fake=SimpleNamespace(audio=lambda *_:io.BytesIO(b'verified-media-bytes'))
        with patch('services.service_factory.learning_review_service',return_value=fake):
            client=app.test_client();base='/api/v2/student/learning/reviews/run-one/media/'
            image=client.get(base+'reviewpack.'+'a'*64+'.png',headers={'Authorization':'Bearer student-a'})
            self.assertEqual(image.status_code,200);self.assertEqual(image.mimetype,'image/png')
            self.assertEqual(image.headers['Cache-Control'],'private, no-store')
            audio=client.get(base+'existing.wav',headers={'Authorization':'Bearer student-a'})
            self.assertEqual(audio.status_code,200);self.assertEqual(audio.mimetype,'audio/wav')


if __name__ == '__main__':
    unittest.main()
