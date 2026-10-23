"""Synthetic formal alias evidence; no provider, browser or real database calls."""
from copy import deepcopy
import base64
import hashlib
import json
import unittest
from unittest.mock import patch
import io
from contextlib import redirect_stdout

from content.textbook_catalog import canonical, digest
from content import textbook_audio_recheck as recheck
from content.textbook_pinyin_alias_alignment import build_evidence, validate_evidence, LIMIT
from content.textbook_pinyin_operator_review_v3 import build_operator_review_v3
from scripts.recheck_textbook_audio import verify_alias_sources
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
VERSION = 'mira.textbook.pinyin-garden3-ssml.v2'
TEXT = 'cā bō li。'


class AliasOperatorV3Tests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.PinyinPublicationTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        f=self.f; self.now=now_ms(); self.request_plans=[]
        f.manifest['units'][0]['lessons'][0]['nodeId']='u3-l6'
        self.frozen=json.loads(f.row['input_json']); self.frozen.update(nodeId='u3-l6',manifestSha256=digest(f.manifest))
        for scene,text in zip(f.classroom['scenes'][:2],[TEXT,'请看图片，听老师说明。']):
            a=scene['actions'][0]; a.clear(); a.update(id='a1' if scene['id']=='s1' else 'a2',type='speech',text=text)
        f.classroom['scenes'][2]['content']['questions'][0]['questionAudioUrl']='pending'
        args=dict(preview_key=f.key,classroom_sha256=digest(f.classroom),core_sha256=digest(core_content(f.classroom)),frozen_input=self.frozen)
        f.plan=new_pinyin_audio_plan(**args,parent_plan=new_audio_plan(**args),revision_id='d'*64)
        (f.root/f.cid/'textbook-preview-audio/plan.json').write_text(canonical(f.plan))
        self.audio=fixtures.wav_fixture(); self.receipts=[]; entries=[]
        for scene in f.classroom['scenes'][:2]:
            a=scene['actions'][0]; receipt=self.audio_receipt(scene,a,f.plan)
            self.receipts.append(receipt)
            transcript='擦玻璃。' if scene['id']=='s1' else a['text']
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
        f.row.update(node_id='u3-l6',input_json=canonical(self.frozen),classroom_json=canonical(f.classroom),
            classroom_sha256=source,result_json=canonical({'audioReceipts':self.receipts}))
        (f.root/(f.cid+'.json')).write_text(canonical(f.classroom));f.review['sourceSha256']=source
        f.service.repository.get_revision.return_value={'manifest_sha256':digest(f.manifest)}
        f.service.repository.manifest.return_value=f.manifest
        self.browser['sourceSha256']=source
        self.browser['checks'][-1].update(**{k:f.audit['segments'][0][k] for k in ('ttsRequestId','audioSha256')});sign(self.browser)

    def alias_context(self):
        f=self.f
        return dict(plan=f.plan,classroom=f.classroom,audit=f.audit,
            expected_source_sha256=f.row['classroom_sha256'],now_ms=self.now)

    def rebuild(self):
        receipt=self.receipts[0]
        source={'sceneId':'s1','actionId':'a1','ttsReceipt':deepcopy(receipt),
                'audioBase64':base64.b64encode(self.audio).decode()}
        if self.request_plans:source['requestPlan']=deepcopy(self.request_plans[0])
        args=self.alias_context();args.pop('now_ms')
        self.proof=build_evidence(sources=[source],recorded_at=self.now-600,**args)
        self.rechecked=None;self.carrier=None
        self.review=self.make_review()

    def make_review(self):
        f=self.f
        return build_operator_review_v3(plan=f.plan,classroom=f.classroom,audit=f.audit,
            tts_receipts=self.receipts,authorization=self.auth,browser_qa=self.browser,reviewer='Synthetic operator',
            reviewed_at=self.now,expected_source_sha256=f.row['classroom_sha256'],now_ms=self.now,
            request_plans=self.request_plans,asr_recheck=self.rechecked,
            carrier_orthographic_evidence=self.carrier,exact_alias_evidence=self.proof)

    def validate(self,value=None):
        f=self.f
        return validate_operator_review(self.review if value is None else value,plan=f.plan,classroom=f.classroom,
            audit=f.audit,expected_source_sha256=f.row['classroom_sha256'],now_ms=self.now)

    def prepare(self,value=None):
        f=self.f
        return f.service.prepare(key=f.key,edition=f.manifest['editionId'],revision=f.manifest['revisionId'],
            node='u3-l6',teaching_revision='1',review=f.review,audio_audit=f.audit,classroom_directory=f.root,
            pronunciation_review=self.review if value is None else value)

    def read(self,prepared):
        return validate_release({**self.f.build(prepared),'node_id':'u3-l6'},self.f.manifest)

    def change_transcript(self, text, index=0):
        f=self.f;scene=f.classroom['scenes'][index];action=scene['actions'][0]
        f.audit['segments'][index]=self.audit_entry(scene,action,self.receipts[index],text)
        f.audit['passed']=all(x['comparison']['passed'] for x in f.audit['segments']);self.sync_source()

    def save_receipts(self):
        (self.f.root/self.f.cid/'textbook-preview-audio/receipts.json').write_text(canonical(self.receipts))

    def add_recheck(self, transcript):
        f=self.f;old=f.audit['segments'][1];scene=f.classroom['scenes'][1];action=scene['actions'][0];receipt=self.receipts[1]
        intent=recheck.build_intent(plan=f.plan,classroom=f.classroom,audit=f.audit,
            expected_source_sha256=f.row['classroom_sha256'],
            selections=[{'sceneId':'s2','actionId':'a2','reason':'SYNTHETIC remaining lexical discrepancy'}],
            created_at=self.now-400,exact_alias_evidence=self.proof)
        request=recheck.logical_request(f.plan,f.classroom,scene,action,receipt,old)
        response=deepcopy(old['asr']);response.update(requestId=request['requestId'],transcript=transcript,transcriptSha256=sha_text(transcript))
        entry={'sceneId':'s2','actionId':'a2','originalSegmentSha256':digest(old),'request':request,
            'requestSha256':digest(request),'ttsReceipt':deepcopy(receipt),'ttsReceiptSha256':digest(receipt),
            'audioBase64':base64.b64encode(self.audio).decode(),'asr':response,'asrSha256':digest(response),
            'comparison':compare_transcript(f.plan,action['text'],transcript),'observedAt':self.now-100}
        self.rechecked=sign({'schemaVersion':recheck.SCHEMA_ALIAS,'intent':intent,'segments':[entry],'createdAt':self.now})

    def test_exact_alias_preserves_zero_and_prepare_portable_release(self):
        before=canonical({'audit':self.f.audit,'proof':self.proof,'review':self.review})
        self.assertEqual(self.f.audit['segments'][0]['similarityBps'],0)
        self.assertFalse(self.f.audit['passed'])
        self.assertEqual(set(self.validate()),{('s1','a1'),('s2','a2')})
        prepared=self.prepare();release=self.read(prepared)
        self.assertEqual(release['audioAudit']['literalAudit'],self.f.audit)
        self.assertFalse(release['audioAudit']['literalPassed'])
        self.assertEqual(release['audioAudit']['acceptanceMethod'],'automatic-asr-with-exact-natural-alias-content')
        self.assertNotIn('listeningReview',release['audioAudit'])
        for key in ('humanListeningVerified','perceptualToneVerified','phoneticAccuracyVerified'):
            self.assertFalse(self.review[key]);self.assertFalse(self.proof[key])
        self.assertFalse(self.proof['perTokenPhonemeVerified']);self.assertIn('not per-token phoneme',LIMIT)
        self.assertIsNone(self.review['asrRecheck'])
        self.assertEqual(canonical({'audit':self.f.audit,'proof':self.proof,'review':self.review}),before)
        self.f.service.preview.runtime.start_formal_audio_asr.assert_not_called()
        self.f.service.preview.runtime.start_formal_audio_tts.assert_not_called()

    def test_complete_transcript_only_no_homophones_substrings_or_threshold(self):
        for text in ('擦玻离。','擦波璃。','擦波埃里。','擦玻璃呀。','请擦玻璃。','擦玻。','玻璃。','cā bō li。',
                     '擦😀玻璃。','擦\u200b玻璃。','擦\u200d玻璃。','擦\x00玻璃。','擦\x1c玻璃。','擦$玻璃。'):
            self.change_transcript(text)
            with self.subTest(text=text),self.assertRaises(ApiError):self.rebuild()
        for text in ('擦，玻璃！','  擦玻璃。  '):
            self.change_transcript(text);self.rebuild();self.validate()

    def test_old_versions_do_not_accept_alias_evidence(self):
        for schema in ('mira.textbook.pinyin-operator-review.v1','mira.textbook.pinyin-operator-review.v2','unknown'):
            bad=deepcopy(self.review);bad['schemaVersion']=schema;sign(bad)
            with self.subTest(schema=schema),self.assertRaises(ApiError):self.validate(bad)
        with self.assertRaises(ApiError):
            build_operator_review(plan=self.f.plan,classroom=self.f.classroom,audit=self.f.audit,
                tts_receipts=self.receipts,authorization=self.auth,browser_qa=self.browser,reviewer='Synthetic',
                reviewed_at=self.now,expected_source_sha256=self.f.row['classroom_sha256'],now_ms=self.now)

    def test_proof_source_plan_time_and_honest_claim_bindings(self):
        for field in ('sourceSha256','sourceClassroomId','sourceSpeechSha256','coreSha256','planSha256','auditSha256',
                      'humanListeningVerified','phoneticAccuracyVerified','perceptualToneVerified','perTokenPhonemeVerified',
                      'minimumSimilarityBpsUnchanged','evidenceLimit'):
            proof=deepcopy(self.proof);proof[field]='altered';sign(proof)
            with self.subTest(field=field),self.assertRaises(ApiError):validate_evidence(proof,**self.alias_context())
        proof=deepcopy(self.proof);proof['recordedAt']=self.now+1;sign(proof)
        with self.assertRaises(ApiError):validate_evidence(proof,**self.alias_context())
        args=self.alias_context();args['classroom']=deepcopy(args['classroom']);args['classroom']['unreviewed']='change'
        with self.assertRaises(ApiError):validate_evidence(self.proof,**args)

    def test_proof_full_receipts_and_audio_not_caller_match_flags(self):
        for kind in ('body','ssml','policy','wav','pcm','raw-hash','transcript','unknown','duplicate','missing'):
            proof=deepcopy(self.proof);e=proof['segments'][0]
            if kind in ('body','ssml','policy'):
                field={'body':'providerBodySha256','ssml':'ssmlSha256','policy':'policyVersion'}[kind]
                e['ttsReceipt']['providerPronunciation'][field]='invalid'
            elif kind=='wav':e['audioBase64']=base64.b64encode(self.audio[:-1]+b'X').decode()
            elif kind=='pcm':e['ttsReceipt']['pcmSha256']='0'*64
            elif kind=='raw-hash':e['auditSegmentSha256']='0'*64
            elif kind=='transcript':e['normalizedTranscript']='擦波璃'
            elif kind=='unknown':e['allow']=True
            elif kind=='duplicate':proof['segments']*=2
            else:proof['segments']=[]
            sign(proof)
            with self.subTest(kind=kind),self.assertRaises(ApiError):validate_evidence(proof,**self.alias_context())

    def test_raw_receipt_and_no_hint_body_are_recomputed(self):
        for mutate in (lambda e:e['asr'].update(providerAsrBodySha256='0'*64),
                       lambda e:e['asr'].update(completionUsable=False),
                       lambda e:e['asr'].update(transcript='擦玻离。'),
                       lambda e:e.update(similarityBps=10000),
                       lambda e:e['comparison'].update(passed=True)):
            old=deepcopy(self.f.audit);mutate(self.f.audit['segments'][0]);sign(self.f.audit)
            with self.assertRaises(ApiError):self.rebuild()
            self.f.audit=old

    def test_recheck_exclusion_requires_full_proof_and_no_alias_redispatch(self):
        args=dict(plan=self.f.plan,classroom=self.f.classroom,audit=self.f.audit,
            expected_source_sha256=self.f.row['classroom_sha256'],selections=[],created_at=self.now)
        with self.assertRaises(ApiError):recheck.build_intent(**args)
        intent=recheck.build_intent(**args,exact_alias_evidence=self.proof)
        self.assertEqual(intent['selection'],[]);self.assertEqual(intent['schemaVersion'],recheck.INTENT_SCHEMA_ALIAS)
        bad=deepcopy(self.proof);bad['segments'][0]['audioBase64']='';sign(bad)
        with self.assertRaises(ApiError):recheck.build_intent(**args,exact_alias_evidence=bad)
        args['selections']=[{'sceneId':'s1','actionId':'a1','reason':'must not call again'}]
        with self.assertRaises(ApiError):recheck.build_intent(**args,exact_alias_evidence=self.proof)

    def test_exclusion_does_not_hide_other_low_or_semantic_failures(self):
        self.change_transcript('完全错误。',index=1);self.rebuild_proof_only()
        with self.assertRaises(ApiError):self.make_review()
        with self.assertRaises(ApiError):recheck.build_intent(plan=self.f.plan,classroom=self.f.classroom,audit=self.f.audit,
            expected_source_sha256=self.f.row['classroom_sha256'],selections=[],created_at=self.now,exact_alias_evidence=self.proof)
        self.add_recheck('仍然错误。')
        with self.assertRaises(ApiError):self.make_review()
        self.add_recheck(self.f.classroom['scenes'][1]['actions'][0]['text']);self.review=self.make_review()
        self.assertEqual(self.read(self.prepare())['audioAudit']['literalAudit'],self.f.audit)

    def rebuild_proof_only(self):
        args=self.alias_context();args.pop('now_ms')
        source={k:self.proof['segments'][0][k] for k in ('sceneId','actionId','ttsReceipt','audioBase64')}
        self.proof=build_evidence(sources=[source],recorded_at=self.now-600,**args)

    def test_alias_and_independent_carrier_are_separate_portable_evidence(self):
        from content.textbook_pinyin_carrier_equivalence import build_evidence as carrier
        f=self.f;scene=f.classroom['scenes'][1];a=scene['actions'][0];a['text']='qí mǎ。'
        self.receipts[1]=self.audio_receipt(scene,a,f.plan);self.change_transcript('骑马。',index=1)
        self.rebuild_proof_only();self.add_recheck('骑马。')
        self.carrier=carrier(selections=[{'sceneId':'s2','actionId':'a2'}],plan=f.plan,classroom=f.classroom,
            audit=f.audit,recheck=self.rechecked,authorization=self.auth,expected_source_sha256=f.row['classroom_sha256'],now_ms=self.now)
        self.review=self.make_review();release=self.read(self.prepare())
        self.assertEqual(release['audioAudit']['literalAudit'],f.audit)
        self.assertIsNone(self.review['segments'][0]['carrierOrthographicEntrySha256'])
        self.assertIsNone(self.review['segments'][1]['exactAliasEntrySha256'])

    def test_revision_child_plan_and_authoritative_archive(self):
        f=self.f;scene=f.classroom['scenes'][0];a=scene['actions'][0]
        child=revision_audio_plan(f.plan,revision_id='e'*64,classroom_sha256=digest(f.classroom),
            core_sha256=digest(core_content(f.classroom)),frozen_input=self.frozen)
        self.request_plans=[child];self.receipts[0]=self.audio_receipt(scene,a,child)
        self.change_transcript('擦玻璃。');self.rebuild()
        folder=f.root/f.cid/'textbook-preview-audio/narration-revisions'/child['revisionId'];folder.mkdir(parents=True)
        (folder/'plan.json').write_text(canonical(child))
        self.assertEqual(self.read(self.prepare())['audioAudit']['literalAudit'],f.audit)
        (folder/'plan.json').unlink()
        with self.assertRaises(ApiError):self.prepare()
        bad=deepcopy(self.proof);bad['segments'][0].pop('requestPlan');sign(bad)
        with self.assertRaises(ApiError):validate_evidence(bad,**self.alias_context())

    def test_cli_exclusion_checks_authoritative_receipt_and_wav(self):
        self.save_receipts();f=self.f
        args=dict(plan=f.plan,classroom=f.classroom,audit=f.audit,audio_directory=f.root/f.cid,
            expected_source_sha256=f.row['classroom_sha256'],latest=self.now)
        self.assertEqual(set(verify_alias_sources(self.proof,**args)),{('s1','a1')})
        path=f.root/f.cid/'audio'/(self.receipts[0]['requestId']+'.wav');old=path.read_bytes();path.write_bytes(old[:-1]+b'X')
        with self.assertRaises(RuntimeError):verify_alias_sources(self.proof,**args)
        path.write_bytes(old);self.receipts[0]['providerRequestId']='other';self.save_receipts()
        with self.assertRaises(RuntimeError):verify_alias_sources(self.proof,**args)

    def test_alias_only_run_never_initializes_provider_or_reports_empty_asr_pass(self):
        from scripts import recheck_textbook_audio as cli
        self.save_receipts();f=self.f
        folder=f.root/'alias-cli';folder.mkdir()
        audit=folder/'audit.json';audit.write_text(canonical(f.audit))
        proof=folder/'proof.json';proof.write_text(canonical(self.proof))
        selection=folder/'selection.json';selection.write_text('[]')
        output=folder/'prepared'
        argv=['recheck','run','--classroom',str(f.root/(f.cid+'.json')),
            '--audio-directory',str(f.root/f.cid),'--audit',str(audit),'--selection',str(selection),
            '--source-sha256',f.row['classroom_sha256'],'--output',str(output),
            '--exact-alias-evidence',str(proof)]
        stdout=io.StringIO()
        with patch('sys.argv',argv),patch.object(cli.AppConfig,'from_env') as config,redirect_stdout(stdout):
            cli.main()
        config.assert_not_called()
        result=json.loads(stdout.getvalue())
        self.assertEqual(result['providerCalls'],0);self.assertFalse(result['independentAsrPerformed'])
        self.assertNotIn('passed',result);self.assertFalse((output/'recheck.json').exists())

    def test_recheck_alias_schema_cannot_be_downgraded_or_drop_evidence(self):
        self.change_transcript('完全错误。',index=1);self.rebuild_proof_only()
        self.add_recheck(self.f.classroom['scenes'][1]['actions'][0]['text'])
        for kind in ('outer-v1','intent-v1','drop-proof','change-proof'):
            value=deepcopy(self.rechecked)
            if kind=='outer-v1':value['schemaVersion']=recheck.SCHEMA
            elif kind=='intent-v1':value['intent']['schemaVersion']=recheck.INTENT_SCHEMA
            elif kind=='drop-proof':value['intent'].pop('exactAliasEvidence')
            else:value['intent']['exactAliasEvidence']['segments'][0]['ttsReceipt']['providerRequestId']='different'
            sign(value['intent']);sign(value)
            with self.subTest(kind=kind),self.assertRaises(ApiError):
                recheck.validate_asr_recheck(value,plan=self.f.plan,classroom=self.f.classroom,audit=self.f.audit,
                    expected_source_sha256=self.f.row['classroom_sha256'],now_ms=self.now)

    def test_v3_prepare_does_not_trust_alternative_tts_receipt_or_media(self):
        value=deepcopy(self.review);value['segments'][0]['ttsReceipt']['providerRequestId']='different'
        value['segments'][0]['ttsReceiptSha256']=digest(value['segments'][0]['ttsReceipt']);sign(value)
        with self.assertRaises(ApiError):self.prepare(value)
        path=self.f.root/self.f.cid/'audio'/(self.receipts[0]['requestId']+'.wav')
        path.write_bytes(self.audio[:-1]+b'X')
        with self.assertRaises(ApiError):self.prepare()

    def test_browser_and_every_speech_still_required(self):
        for kind in ('no-browser','missing-speech','missing-proof','wrong-method','human'):
            value=deepcopy(self.review)
            if kind=='no-browser':value['browserQa']['checks']=[];sign(value['browserQa'])
            elif kind=='missing-speech':value['segments'].pop()
            elif kind=='missing-proof':value['exactAliasEvidence']=None
            elif kind=='wrong-method':value['method']='user-authorized-automated-verification'
            else:value['humanListeningVerified']=True
            sign(value)
            with self.subTest(kind=kind),self.assertRaises(ApiError):self.validate(value)

    def test_chinese_natural_polyphone_and_nonexact_source_not_in_scope(self):
        for text in ('一模一样。','cā bō li！',' cā bō li。','请听：cā bō li。'):
            source=deepcopy(self.f.classroom);source['scenes'][0]['actions'][0]['text']=text
            args=self.alias_context();args['classroom']=source;args['expected_source_sha256']=digest(source)
            with self.subTest(text=text),self.assertRaises(ApiError):validate_evidence(self.proof,**args)


if __name__=='__main__':unittest.main()
