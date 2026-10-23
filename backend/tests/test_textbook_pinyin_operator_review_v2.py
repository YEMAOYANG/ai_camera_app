"""Synthetic exact-carrier publication regressions; no provider, browser or DB."""
from copy import deepcopy
import base64
import hashlib
import json
import unittest

from content.textbook_catalog import canonical, digest
from content import textbook_audio_recheck as recheck
from content.textbook_pinyin_carrier_equivalence import build_evidence, exact_representation
from content.textbook_pinyin_operator_review import (AUTHORIZATION_SCHEMA, BROWSER_SCHEMA,
    SCHEMA_V2, build_operator_review, build_operator_review_v2, validate_operator_review)
from content.textbook_pinyin_pronunciation import provider_pronunciation, pinyin_ssml, sha_text, policy_for_plan
from content.textbook_preview_audio_contract import (new_audio_plan, new_pinyin_audio_plan,
    revision_audio_plan, tts_request_id, asr_request_id, compare_transcript, audit_contract_identity)
from content.textbook_release import validate_release
from services.textbook_preview_audio import core_content
from core.errors import ApiError
from core.security import now_ms
from tests import test_textbook_pinyin_pronunciation as fixtures
from tests import test_textbook_pinyin_reconciliation_publication as reconciliation_fixtures

sign = fixtures.sign
VERSION = 'mira.textbook.pinyin-zhchshr-ssml.v1'


class CarrierOperatorV2Tests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PinyinPublicationTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        f=self.f; self.now=now_ms(); self.request_plans=[]
        f.manifest['units'][0]['lessons'][0]['nodeId']='u3-l4'
        self.frozen=json.loads(f.row['input_json']); self.frozen.update(nodeId='u3-l4',manifestSha256=digest(f.manifest))
        for scene,text in zip(f.classroom['scenes'][:2],['请听整卡：chi。','请看图片，听老师说明。']):
            a=scene['actions'][0]; a.clear(); a.update(id='a1' if scene['id']=='s1' else 'a2',type='speech',text=text)
        f.classroom['scenes'][2]['content']['questions'][0]['questionAudioUrl']='pending'
        args=dict(preview_key=f.key,classroom_sha256=digest(f.classroom),core_sha256=digest(core_content(f.classroom)),frozen_input=self.frozen)
        f.plan=new_pinyin_audio_plan(**args,parent_plan=new_audio_plan(**args),revision_id='d'*64)
        (f.root/f.cid/'textbook-preview-audio/plan.json').write_text(canonical(f.plan))
        self.audio=fixtures.wav_fixture(); self.receipts=[]; entries=[]
        for scene in f.classroom['scenes'][:2]:
            a=scene['actions'][0]; receipt=self.audio_receipt(scene,a,f.plan)
            self.receipts.append(receipt)
            transcript='请听整卡：吃。' if scene['id']=='s1' else a['text']
            entries.append(self.audit_entry(scene,a,receipt,transcript))
        f.audit=sign({'schemaVersion':'mira.textbook.audio-audit.v2','previewKey':f.key,
            'sourceSha256':digest(f.classroom),'passed':False,'contract':audit_contract_identity(f.plan),'segments':entries})
        self.auth=sign({'schemaVersion':AUTHORIZATION_SCHEMA,'source':'user-message',
            'statement':'SYNTHETIC TEST ONLY: authorize automated checks and publication without human listening.',
            'recordedAt':self.now-2000,'scope':{k:f.plan['binding'][k] for k in ('editionId','gradeCode','subject')},
            'automatedChecksAuthorized':True,'publicationAuthorized':True,'individualListeningConfirmationRequired':False})
        checks=[{'kind':'picture-supported-layout','sceneId':s['id'],'passed':True,
            'observation':'SYNTHETIC TEST ONLY','evidenceSha256':'1'*64} for s in f.classroom['scenes']]
        checks.append({'kind':'interaction','sceneId':'s2','passed':True,'observation':'SYNTHETIC TEST ONLY','evidenceSha256':'2'*64})
        checks.append({'kind':'audio-playback',**{k:entries[0][k] for k in ('sceneId','actionId','ttsRequestId','audioSha256')},
            'passed':True,'events':['playing','ended'],'syntheticAudio':False,
            'observation':'SYNTHETIC TEST fixture, not real browser evidence','evidenceSha256':'3'*64})
        self.browser=sign({'schemaVersion':BROWSER_SCHEMA,'sourceSha256':digest(f.classroom),
            'coreSha256':f.plan['coreSha256'],'planSha256':digest(f.plan),'method':'real-browser',
            'reviewer':'Synthetic fixture','reviewedAt':self.now-1000,
            'coverage':'all-scenes-layout-and-recorded-action-samples','checks':checks})
        self.sync_source(); self.rebuild()

    def audio_receipt(self,scene,action,plan):
        f=self.f; text=action['text']; rid=tts_request_id(plan,scene['id'],action['id'],text)
        action.update(audioId=rid,audioUrl=f'/api/classroom-media/{f.cid}/audio/{rid}.wav',
            audioMetadata={'schemaVersion':'mira.openmaic.speech-audio.v1','providerId':'aliyun-cosyvoice',
                'modelId':'cosyvoice-v3-flash','voiceId':'longanwen_v3','fallbackUsed':False})
        (f.root/f.cid/'audio'/(rid+'.wav')).write_bytes(self.audio)
        result={**fixtures.wav_receipt(self.audio),'providerRequestId':'synthetic-provider-request',
            'providerUsage':{'characters':1},'budgetMeasurement':{'kind':'ssml-codepoint-upper-bound',
                'characters':len(pinyin_ssml(text,policy_version=VERSION)),'estimated':True},
            'requestId':rid,'status':'succeeded','mimeType':'audio/wav',
            'previewAudioIdentity':{'planSha256':digest(plan),'attempt':1},
            'providerId':'aliyun-cosyvoice','modelId':'cosyvoice-v3-flash','voiceId':'longanwen_v3',
            'providerPronunciation':provider_pronunciation(text,policy_version=VERSION)}
        if plan!=f.plan:result.update(narrationRevisionId=plan['revisionId'],classroomContentSha256=plan['classroomSha256'])
        return result

    def audit_entry(self,scene,action,receipt,transcript):
        f=self.f; text=action['text']; comparison=compare_transcript(f.plan,text,transcript)
        return {'sceneId':scene['id'],'actionId':action['id'],'text':text,'textSha256':sha_text(text),
            'ttsRequestId':receipt['requestId'],'audioSha256':receipt['audioSha256'],'transcript':transcript,
            'comparison':comparison,'similarityBps':comparison['similarityBps'],
            'asr':{'status':'succeeded','completionUsable':True,
                'requestId':asr_request_id(f.plan,receipt['requestId'],receipt['audioSha256']),
                'transcript':transcript,'transcriptSha256':sha_text(transcript),
                'providerAsrBodySha256':hashlib.sha256(recheck.provider_body(self.audio)).hexdigest(),
                'providerId':'qwen-asr','modelId':'qwen3-asr-flash',
                'providerPronunciation':provider_pronunciation(text,policy_version=VERSION)}}

    def sync_source(self):
        f=self.f
        f.classroom['scenes'][2]['content']['questions'][0]['questionAudioUrl']=f.classroom['scenes'][0]['actions'][0]['audioUrl']
        source=digest(f.classroom); f.audit['sourceSha256']=source;sign(f.audit)
        f.row.update(node_id='u3-l4',input_json=canonical(self.frozen),classroom_json=canonical(f.classroom),
            classroom_sha256=source,result_json=canonical({'audioReceipts':self.receipts}))
        (f.root/(f.cid+'.json')).write_text(canonical(f.classroom));f.review['sourceSha256']=source
        f.service.repository.get_revision.return_value={'manifest_sha256':digest(f.manifest)}
        f.service.repository.manifest.return_value=f.manifest
        self.browser['sourceSha256']=source
        self.browser['checks'][-1].update(**{k:f.audit['segments'][0][k] for k in ('ttsRequestId','audioSha256')});sign(self.browser)

    def context(self):
        f=self.f
        return dict(plan=f.plan,classroom=f.classroom,audit=f.audit,recheck=self.rechecked,
            authorization=self.auth,expected_source_sha256=f.row['classroom_sha256'],now_ms=self.now)

    def rebuild(self,transcript=None):
        f=self.f; old=f.audit['segments'][0];receipt=self.receipts[0];scene=f.classroom['scenes'][0];a=scene['actions'][0]
        intent=recheck.build_intent(plan=f.plan,classroom=f.classroom,audit=f.audit,
            expected_source_sha256=f.row['classroom_sha256'],
            selections=[{'sceneId':'s1','actionId':'a1','reason':'SYNTHETIC literal spelling discrepancy'}],created_at=self.now-500)
        request=recheck.logical_request(f.plan,f.classroom,scene,a,receipt,old)
        response=deepcopy(old['asr']); text=transcript or old['asr']['transcript']
        response.update(requestId=request['requestId'],transcript=text,transcriptSha256=sha_text(text))
        entry={'sceneId':'s1','actionId':'a1','originalSegmentSha256':digest(old),'request':request,
            'requestSha256':digest(request),'ttsReceipt':deepcopy(receipt),'ttsReceiptSha256':digest(receipt),
            'audioBase64':base64.b64encode(self.audio).decode(),'asr':response,'asrSha256':digest(response),
            'comparison':compare_transcript(f.plan,a['text'],text),'observedAt':self.now-100}
        if self.request_plans:entry['requestPlan']=deepcopy(self.request_plans[0])
        self.rechecked=sign({'schemaVersion':recheck.SCHEMA,'intent':intent,'segments':[entry],'createdAt':self.now})
        self.proof=build_evidence(selections=[{'sceneId':'s1','actionId':'a1'}],**self.context())
        self.review=self.make_review()

    def make_review(self):
        f=self.f
        return build_operator_review_v2(plan=f.plan,classroom=f.classroom,audit=f.audit,
            tts_receipts=self.receipts,authorization=self.auth,browser_qa=self.browser,reviewer='Synthetic operator',
            reviewed_at=self.now,expected_source_sha256=f.row['classroom_sha256'],now_ms=self.now,
            request_plans=self.request_plans,asr_recheck=self.rechecked,carrier_orthographic_evidence=self.proof)

    def validate(self,value=None):
        f=self.f
        return validate_operator_review(self.review if value is None else value,plan=f.plan,classroom=f.classroom,
            audit=f.audit,expected_source_sha256=f.row['classroom_sha256'],now_ms=self.now)

    def prepare(self,value=None):
        f=self.f
        return f.service.prepare(key=f.key,edition=f.manifest['editionId'],revision=f.manifest['revisionId'],
            node='u3-l4',teaching_revision='1',review=f.review,audio_audit=f.audit,classroom_directory=f.root,
            pronunciation_review=self.review if value is None else value)

    def read(self,prepared):
        return validate_release({**self.f.build(prepared),'node_id':'u3-l4'},self.f.manifest)

    def test_both_failed_preserved_prepare_and_portable_release(self):
        f=self.f;before=canonical({'audit':f.audit,'recheck':self.rechecked,'review':self.review,'row':f.row})
        prepared=self.prepare(); release=self.read(prepared); archived=release['audioAudit']
        self.assertEqual(archived['acceptanceMethod'],'independent-asr-with-exact-carrier-orthography')
        self.assertFalse(archived['literalPassed']);self.assertEqual(archived['literalAudit'],f.audit)
        self.assertFalse(archived['pronunciationReview']['asrRecheck']['segments'][0]['comparison']['passed'])
        self.assertLess(archived['minSimilarityBps'],8500)
        self.assertNotEqual(release['classroom']['id'],f.cid)
        self.assertEqual(archived['pronunciationReview']['sourceClassroomId'],f.cid)
        for field in ('humanListeningVerified','phoneticAccuracyVerified','perceptualToneVerified'):
            self.assertFalse(archived['pronunciationReview'][field])
        self.assertEqual(before,canonical({'audit':f.audit,'recheck':self.rechecked,'review':self.review,'row':f.row}))
        f.service.preview.runtime.start_formal_audio_tts.assert_not_called();f.service.preview.runtime.start_formal_audio_asr.assert_not_called()

    def test_v1_still_rejects_same_failed_evidence_and_unknown_schema(self):
        for schema in ('mira.textbook.pinyin-operator-review.v1','mira.textbook.pinyin-operator-review.v3'):
            bad=deepcopy(self.review);bad['schemaVersion']=schema;sign(bad)
            with self.subTest(schema=schema),self.assertRaises(ApiError):self.validate(bad)
        with self.assertRaises(ApiError):
            build_operator_review(plan=self.f.plan,classroom=self.f.classroom,audit=self.f.audit,
                tts_receipts=self.receipts,authorization=self.auth,browser_qa=self.browser,reviewer='Synthetic',
                reviewed_at=self.now,expected_source_sha256=self.f.row['classroom_sha256'],now_ms=self.now,
                asr_recheck=self.rechecked)

    def test_proof_missing_duplicate_extra_and_unbound_fields_rejected(self):
        for kind in ('missing','duplicate','extra','changed-score','changed-target','unknown-field'):
            value=deepcopy(self.review);proof=value['carrierOrthographicEvidence']
            if kind=='missing':proof['segments']=[]
            elif kind=='duplicate':proof['segments']*=2
            elif kind=='extra':proof['segments'][0]['actionId']='a2'
            elif kind=='changed-score':proof['segments'][0]['originalSimilarityBps']=10000
            elif kind=='changed-target':proof['segments'][0]['originalRepresentation']['targets'][0]['ph']='chi2'
            else:proof['trusted']=True
            sign(proof);sign(value)
            with self.subTest(kind=kind),self.assertRaises(ApiError):self.validate(value)

    def test_claims_threshold_and_source_identity_cannot_change(self):
        for field in ('humanListeningVerified','phoneticAccuracyVerified','perceptualToneVerified'):
            value=deepcopy(self.review);value[field]=True;sign(value)
            with self.subTest(field=field),self.assertRaises(ApiError):self.validate(value)
        for field in ('sourceSha256','planSha256','coreSha256','policySha256','auditSha256','sourceClassroomId'):
            value=deepcopy(self.review);value[field]='0'*64;sign(value)
            with self.subTest(field=field),self.assertRaises(ApiError):self.validate(value)
        value=deepcopy(self.review);value['carrierOrthographicEvidence']['minimumSimilarityBpsUnchanged']=8000
        sign(value['carrierOrthographicEvidence']);sign(value)
        with self.assertRaises(ApiError):self.validate(value)

    def test_full_context_and_each_target_are_exact_not_homophones_or_score(self):
        policy=policy_for_plan(self.f.plan)
        for source,text in [('请听：zhí。','请听：迟。'),('请听：shà。','请听：下。'),
            ('请听整卡：chi。','请听正卡：吃。'),('请听：chī。','请听：chi。'),
            ('请听：rǔ。','请听：rú。'),('请听：chi。','请听：c h i。')]:
            with self.subTest(source=source,text=text),self.assertRaises(ApiError):exact_representation(source,text,policy)
        self.assertTrue(exact_representation('请听：chi。','请听：吃。',policy)['orthographicEquivalent'])
        self.assertTrue(exact_representation('请听：chi。','请听：chi。',policy)['orthographicEquivalent'])

    def test_changed_second_attempt_context_rejected_even_with_valid_new_hashes(self):
        for text in ('请听正卡：吃。','请听整卡：迟。','请听整卡：吃。再来一次。'):
            with self.subTest(text=text),self.assertRaises(ApiError):self.rebuild(text)

    def test_raw_scores_are_recomputed_and_cannot_be_changed_to_pass(self):
        f=self.f;old=deepcopy(f.audit)
        for field in ('similarityBps','passed','transcript'):
            f.audit=deepcopy(old);e=f.audit['segments'][0]
            if field=='similarityBps':e['similarityBps']=10000
            elif field=='passed':e['comparison']['passed']=True
            else:e['asr']['transcript']='请听整卡：chi。'
            sign(f.audit)
            with self.subTest(field=field),self.assertRaises(ApiError):self.rebuild()

    def test_tts_receipt_wav_and_provider_body_bind_actual_audio(self):
        for field in ('ttsRequestId','audioSha256','pcmSha256','requestPlanSha256','ttsReceiptSha256',
                      'asrReceiptSha256','carrierOrthographicEntrySha256','asrRecheckEntrySha256'):
            value=deepcopy(self.review);value['segments'][0][field]='0'*64;sign(value)
            with self.subTest(field=field),self.assertRaises(ApiError):self.validate(value)
        f=self.f;path=f.root/f.cid/'audio'/(self.receipts[0]['requestId']+'.wav')
        audio=bytearray(path.read_bytes());audio[-1]^=1;path.write_bytes(audio)
        with self.assertRaises(ApiError):self.prepare()

    def test_prepare_uses_full_actual_classroom_and_authoritative_receipts(self):
        f=self.f;before=f.row['classroom_json'];changed=json.loads(before)
        changed['stage']['name']='Different source';f.row['classroom_json']=canonical(changed)
        with self.assertRaises(ApiError):self.prepare()
        f.row['classroom_json']=before
        changed=deepcopy(self.receipts);changed[0]['providerRequestId']='another-request'
        f.row['result_json']=canonical({'audioReceipts':changed})
        with self.assertRaises(ApiError):self.prepare()

    def test_portable_acceptance_method_and_source_classroom_cannot_be_resealed_away(self):
        original=self.prepare()
        for field,value in [('acceptanceMethod','literal-asr'),('sourceClassroomId','wrong-stage')]:
            p=deepcopy(original);a=p['review']['release']['audioAudit']
            if field=='acceptanceMethod':a[field]=value
            else:
                a['pronunciationReview'][field]=value;sign(a['pronunciationReview'])
                p['frozen']['pronunciationReviewSha256']=a['pronunciationReview']['sha256']
            p=reconciliation_fixtures.PinyinReconciliationPublicationTests.reseal_release(self,p)
            with self.subTest(field=field),self.assertRaises(ApiError):self.read(p)

    def test_child_request_plan_remains_portable_and_missing_archive_rejected(self):
        f=self.f;scene=f.classroom['scenes'][0];action=scene['actions'][0]
        action['text']='再听整卡：chī。'
        child=revision_audio_plan(f.plan,revision_id='e'*64,classroom_sha256=digest(f.classroom),
            core_sha256=digest(core_content(f.classroom)),frozen_input=self.frozen)
        self.request_plans=[child];self.receipts[0]=self.audio_receipt(scene,action,child)
        folder=f.root/f.cid/'textbook-preview-audio/narration-revisions'/child['revisionId'];folder.mkdir(parents=True)
        (folder/'plan.json').write_text(canonical(child))
        f.audit['segments'][0]=self.audit_entry(scene,action,self.receipts[0],'再听整卡：吃。')
        self.sync_source();self.rebuild()
        release=self.read(self.prepare())
        self.assertEqual(release['audioAudit']['pronunciationReview']['requestPlans'],[child])
        self.assertEqual(self.proof['segments'][0]['requestPlanSha256'],digest(child))
        (folder/'plan.json').write_text('{}')
        with self.assertRaises(ApiError):self.prepare()

    def test_each_still_failed_recheck_requires_its_own_proof_and_original_failure(self):
        # A subset proof cannot hide another unresolved segment.
        f=self.f;second=f.audit['segments'][1]
        second['transcript']='完全无关内容';second['asr'].update(transcript=second['transcript'],transcriptSha256=sha_text(second['transcript']))
        second['comparison']=compare_transcript(f.plan,second['text'],second['transcript'])
        second['similarityBps']=second['comparison']['similarityBps'];sign(f.audit)
        with self.assertRaises(ApiError):self.rebuild()

    def test_exact_matcher_never_applies_chinese_word_overrides(self):
        policy=deepcopy(policy_for_plan(self.f.plan));policy['words']={'桌子':{'ph':'zhuo1 zi5','carrier':'桌子'}}
        with self.assertRaises(ApiError):exact_representation('请听：chi。','请听：吃。',policy)

    def test_evidence_cannot_change_transport_body_or_child_policy(self):
        from content.textbook_pinyin_carrier_equivalence import validate_evidence
        before=deepcopy(self.rechecked)
        for field in ('providerAsrBodySha256','requestId'):
            self.rechecked=deepcopy(before);entry=self.rechecked['segments'][0]
            entry['asr'][field]='0'*64;entry['asrSha256']=digest(entry['asr']);sign(self.rechecked)
            with self.subTest(field=field),self.assertRaises(ApiError):validate_evidence(self.proof,**self.context())
        self.rechecked=before
        before_proof=deepcopy(self.proof)
        for field in ('policySha256','ttsReceiptSha256','requestPlanSha256','pcmSha256'):
            self.proof=deepcopy(before_proof);self.proof['segments'][0][field]='f'*64;sign(self.proof)
            with self.subTest(field=field),self.assertRaises(ApiError):self.make_review()

    def test_current_source_recovery_preserves_same_once_request_without_old_source_evidence(self):
        old_request=deepcopy(self.rechecked['segments'][0]['request']);old_proof=deepcopy(self.proof)
        self.f.classroom['stage']['name']='SYNTHETIC visual-only source update';self.sync_source();self.rebuild()
        self.assertEqual(self.rechecked['segments'][0]['request'],old_request)
        self.assertNotEqual(self.proof['sourceSha256'],old_proof['sourceSha256'])
        self.read(self.prepare())
        self.proof=old_proof
        with self.assertRaises(ApiError):self.make_review()


if __name__=='__main__':unittest.main()
