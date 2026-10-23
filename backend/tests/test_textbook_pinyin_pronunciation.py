"""Versioned pinyin contract and publication counterexamples; no paid calls/DB."""
from copy import deepcopy
import io
import hashlib
import struct
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, Mock
import wave

from content.textbook_catalog import canonical, digest
from content.textbook_pinyin_pronunciation import (LISTENING_SCHEMA, POLICY, POLICY_SHA256,
    pinyin_ssml, pronunciation_identity, pronunciation_symbols, provider_pronunciation,
    sha_text, validate_listening_review, validate_provider_pronunciation, validate_receipt_wav)
from content.textbook_preview_audio_contract import (asr_request_id, audit_contract_identity,
    check_receipt_pronunciation, compare_transcript, new_audio_plan, new_pinyin_audio_plan,
    resolve_audio_contract, tts_request_id)
from content.textbook_release import validate_release
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from services.textbook_preview_audio import core_content
from services.textbook_publication_service import TextbookPublicationService
from tests.test_textbook_preview_audio_contract import frozen as generic_frozen


PINYIN_BINDING = {'editionId': 'pep-chinese-g1-upper-2022-standard',
    'alignmentRevisionId': '20260924-directory-3', 'nodeId': 'u2-l1',
    'gradeCode': 'primary_1', 'subject': 'chinese'}


def frozen(subject='chinese'):
    return {**generic_frozen(subject), **PINYIN_BINDING, 'subject': subject}


def plan(subject='chinese'):
    return new_audio_plan(preview_key='a'*64, classroom_sha256='b'*64, core_sha256='c'*64,
                          frozen_input=frozen(subject))


def bind_audio_fixture(f):
    """Give an isolated narrator fixture the explicitly registered lesson scope."""
    from services.textbook_learning_service import TextbookLearningService
    manifest = json.loads((Path(__file__).parents[1] /
        'content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json').read_text())
    TextbookLearningService(f.service.repository).import_manifest(manifest)
    value = json.loads(f.service.get(f.key)['input_json'])
    value.update(PINYIN_BINDING, manifestSha256=digest(manifest))
    f.db.execute('UPDATE learning_textbook_course_previews SET edition_id=?,revision_id=?,node_id=?,input_json=? WHERE preview_key=?',
        (value['editionId'], value['alignmentRevisionId'], value['nodeId'], canonical(value), f.key))
    f.db.raw.commit()
    return value


def pinyin_plan():
    return new_pinyin_audio_plan(preview_key='a'*64, classroom_sha256='b'*64, core_sha256='c'*64,
        frozen_input=frozen(), parent_plan=plan(), revision_id='d'*64)


def sign(value):
    value['sha256'] = digest({k: v for k, v in value.items() if k != 'sha256'})
    return value


def wav_fixture():
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b'\0\0' * 2400)
    return output.getvalue()


def wav_receipt(audio=None, *, normalized=False):
    audio = audio or wav_fixture()
    original = bytearray(audio)
    data_size = len(audio) - 44
    if normalized:
        struct.pack_into('<I', original, 4, 0x7fffffbf)
        struct.pack_into('<I', original, 40, 0x7fffff9b)
    return {'audioSha256': hashlib.sha256(audio).hexdigest(),
        'providerAudioSha256': hashlib.sha256(original).hexdigest(),
        'pcmSha256': hashlib.sha256(audio[44:]).hexdigest(),
        'audioNormalization': {'policyVersion': 'mira.wav.streaming-pcm-lengths.v1',
            'applied': normalized, 'providerRiffSize': 0x7fffffbf if normalized else data_size + 36,
            'providerDataSize': 0x7fffff9b if normalized else data_size,
            'riffSize': data_size + 36, 'dataSize': data_size, 'pcmByteLength': data_size,
            'sampleRate': 24000, 'channels': 1, 'bitsPerSample': 16}}


def usage_receipt(text):
    return {'providerRequestId': 'synthetic-provider-request', 'providerUsage': {'characters': 1},
            'budgetMeasurement': {'kind': 'ssml-codepoint-upper-bound',
                                  'characters': len(pinyin_ssml(text)), 'estimated': True}}


class PinyinContractTests(unittest.TestCase):
    def test_exact_mapping_body_hash_and_no_guessing(self):
        self.assertEqual(POLICY_SHA256, 'e325a2ef4706cb6e5cf6b11691d05ee0b30e59ce37d8a06c1528d8c6adf578c7')
        text = 'e，ɑ o e，āáǎà。'
        receipt = provider_pronunciation(text)
        self.assertEqual(receipt['ssmlSha256'], '18ca0381d4d11ce74efe08ac76111aaabc4f16d97ce0cb789e4421032140c737')
        self.assertEqual(receipt['providerBodySha256'], 'd66a1a16ca8b98f99e8eba7c320a4e12f8d66ba1e57aa2280334b24913d6aca3')
        self.assertIn('ph="e1">鹅', pinyin_ssml('e'))
        self.assertEqual([p['ph'] for p in pronunciation_symbols('āáǎàōóǒòēéěè')],
                         [letter+str(tone) for letter in 'aoe' for tone in range(1,5)])
        self.assertEqual(pinyin_ssml('看<&>"\'。'), '<speak>看&lt;&amp;&gt;&quot;&apos;。</speak>')
        for text in ('i', 'ü', 'E', 'hello', 'a\u0304', 'ɑ\u0301', '\x00坏字符'):
            with self.subTest(text=text), self.assertRaises(ApiError): pinyin_ssml(text)
        validate_provider_pronunciation(receipt, 'e，ɑ o e，āáǎà。')
        for field in receipt:
            bad = {**receipt, field: '0'*64}
            with self.subTest(field=field), self.assertRaises(ApiError): validate_provider_pronunciation(bad, text)

    def test_v3_does_not_change_parent_and_has_distinct_namespace(self):
        parent = plan()
        before = canonical(parent)
        value = pinyin_plan()
        self.assertEqual(canonical(parent), before)
        self.assertEqual(value['parentPlanSha256'], digest(parent))
        self.assertEqual(value['teacher']['teacherProfile'], parent['teacher']['teacherProfile'])
        self.assertEqual(value['teacher']['voiceId'], 'longanwen_v3')
        request = tts_request_id(value, 's', 'a', 'e，跟我读。')
        self.assertTrue(request.startswith('tbptts1_'))
        self.assertTrue(asr_request_id(value, request, 'f'*64).startswith('tbpasr1_'))
        for field in ('revisionId', 'parentPlanSha256', 'pronunciationPolicySha256'):
            bad = deepcopy(value); bad.pop(field)
            with self.assertRaises(ApiError): resolve_audio_contract(bad)
        for field, replacement in [('subject','english'), ('teacher', parent['teacher'])]:
            bad = {**value, field: replacement}
            with self.assertRaises(ApiError): resolve_audio_contract(bad)
        with self.assertRaises(ApiError):
            new_pinyin_audio_plan(preview_key='a'*64,classroom_sha256='b'*64,core_sha256='c'*64,
                frozen_input=frozen('math'),parent_plan=plan('math'),revision_id='d'*64)

    def test_succeeded_receipt_must_bind_exact_original_text_and_physical_body(self):
        value = pinyin_plan()
        receipt = {**wav_receipt(),**usage_receipt('é，跟我读。'),'requestId':'tbptts1_'+'f'*64,'status':'succeeded','providerId':'aliyun-cosyvoice','modelId':'cosyvoice-v3-flash','voiceId':'longanwen_v3','providerPronunciation':provider_pronunciation('é，跟我读。')}
        check_receipt_pronunciation(value, receipt, 'é，跟我读。')
        with self.assertRaises(ApiError): check_receipt_pronunciation(value, receipt, 'e，跟我读。')
        receipt['providerPronunciation']['providerBodySha256'] = 'f'*64
        with self.assertRaises(ApiError): check_receipt_pronunciation(value, receipt, 'é，跟我读。')

    def test_wav_normalization_preserves_original_provider_bytes_and_pcm(self):
        audio = wav_fixture()
        for normalized in (False, True):
            receipt = wav_receipt(audio, normalized=normalized)
            validate_receipt_wav(receipt, audio)
            changed = bytearray(audio); changed[-1] = 1
            with self.assertRaises(ApiError): validate_receipt_wav(receipt, bytes(changed))
            receipt['pcmSha256'] = '0'*64
            with self.assertRaises(ApiError): validate_receipt_wav(receipt, audio)
        receipt = wav_receipt(audio, normalized=True)
        receipt['audioNormalization']['providerRiffSize'] = 0xffffffff
        with self.assertRaises(ApiError): validate_receipt_wav(receipt, audio)

    def test_client_builds_profile_and_rejects_cross_subject_or_fake_response(self):
        value = pinyin_plan(); text = 'é，跟我读。'; teacher = value['teacher']['teacherProfile']
        request = tts_request_id(value,'s','a',text)
        kwargs = dict(request_id=request,classroom_id='stage-test',classroom_content_sha256='b'*64,
            subject='chinese',teacher_profile_id=teacher['id'],teacher_profile_version=teacher['version'],
            teacher_profile_sha256=teacher['contentHash'],teacher_gender='female',scene_id='s',scene_order=1,
            action_id='a',narration_segment_id='a',text=text,text_sha256=sha_text(text))
        client = OpenMaicFullRuntimeClient('http://127.0.0.1:3100',formal_audio_internal_token='synthetic-token-'*3)
        response = {'success':True,'requestId':request,'state':'succeeded',**wav_receipt(),**usage_receipt(text),'mimeType':'audio/wav',
                    'providerId':'aliyun-cosyvoice','modelId':'cosyvoice-v3-flash','voiceId':'longanwen_v3','providerPronunciation':provider_pronunciation(text)}
        client._request_formal_audio_json = Mock(return_value=response)
        client.start_formal_audio_tts(**kwargs)
        self.assertEqual(client._request_formal_audio_json.call_args.args[2]['pronunciationProfile'], pronunciation_identity(text))
        response['modelId'] = 'qwen3-tts-flash'
        with self.assertRaises(OpenMaicFullRuntimeError): client.start_formal_audio_tts(**kwargs)
        response['modelId'] = 'cosyvoice-v3-flash'
        response['providerPronunciation'] = provider_pronunciation('e，跟我读。')
        with self.assertRaises(OpenMaicFullRuntimeError): client.start_formal_audio_tts(**kwargs)
        with self.assertRaises(OpenMaicFullRuntimeError): client.start_formal_audio_tts(**{**kwargs,'subject':'english'})
        asr = 'tbpasr1_' + digest({'tts':request,'audio':'f'*64})
        payload = {**client._request_formal_audio_json.call_args.args[2], 'requestId':asr,'ttsRequestId':request,'audioSha256':'f'*64}
        payload.pop('pronunciationProfile')
        client._validate_textbook_audio_namespace(payload,'asr')
        payload['requestId'] = 'tbpasr1_'+'0'*64
        with self.assertRaises(OpenMaicFullRuntimeError): client._validate_textbook_audio_namespace(payload,'asr')


class PinyinPublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.cid='synthetic-pinyin'; self.key='a'*64
        self.classroom={'id':self.cid,'stage':{'id':self.cid,'name':'拼音 fixture'},'scenes':[
            {'id':'s1','type':'slide','content':{},'actions':[{'id':'a1','type':'speech','text':'e，请跟老师读。'}]},
            {'id':'s2','type':'interactive','content':{'html':''},'actions':[{'id':'a2','type':'speech','text':'é，请再读一遍。'}]},
            {'id':'s3','type':'quiz','actions':[],'content':{'questions':[{'id':'q','type':'single','question':'请选择图片。',
                'options':[{'value':'A','label':'图一'},{'value':'B','label':'图二'}],'answer':['A'],'analysis':'听老师读。','questionAudioUrl':'pending'}]}}]}
        self.manifest={'editionId':PINYIN_BINDING['editionId'],'revisionId':PINYIN_BINDING['alignmentRevisionId'],
            'gradeCode':'primary_1','subject':'chinese',
            'units':[{'title':'一','lessons':[{'nodeId':'u2-l1','brief':{'objectives':['读准拼音。']}}]}]}
        frozen_input={**frozen(),'manifestSha256':digest(self.manifest),'previewPrompt':{'expectedSceneCount':3,'expectedQuestionCount':1}}
        parent=new_audio_plan(preview_key=self.key,classroom_sha256=digest(self.classroom),core_sha256=digest(core_content(self.classroom)),frozen_input=frozen_input)
        self.plan=new_pinyin_audio_plan(preview_key=self.key,classroom_sha256=digest(self.classroom),core_sha256=digest(core_content(self.classroom)),frozen_input=frozen_input,parent_plan=parent,revision_id='d'*64)
        folder=self.root/self.cid/'textbook-preview-audio';folder.mkdir(parents=True)
        (folder/'plan.json').write_text(canonical(self.plan)); (self.root/self.cid/'audio').mkdir()
        wav=io.BytesIO()
        with wave.open(wav,'wb') as out: out.setparams((1,2,24000,0,'NONE','not compressed'));out.writeframes(b'\0\0'*2400)
        audio=wav.getvalue(); audio_sha=hashlib.sha256(audio).hexdigest()
        receipts=[];segments=[]; heard=[]
        for scene in self.classroom['scenes'][:2]:
            action=scene['actions'][0]; text=action['text']; request=tts_request_id(self.plan,scene['id'],action['id'],text)
            path=f'/api/classroom-media/{self.cid}/audio/{request}.wav'
            (self.root/self.cid/'audio'/(request+'.wav')).write_bytes(audio)
            action.update(audioId=request,audioUrl=path,audioMetadata={'schemaVersion':'mira.openmaic.speech-audio.v1',
                'providerId':'aliyun-cosyvoice','modelId':'cosyvoice-v3-flash','voiceId':'longanwen_v3','fallbackUsed':False})
            receipts.append({**wav_receipt(audio),**usage_receipt(text),'requestId':request,'status':'succeeded','audioSha256':audio_sha,'mimeType':'audio/wav',
                'previewAudioIdentity':{'planSha256':digest(self.plan),'attempt':1},'providerId':'aliyun-cosyvoice','modelId':'cosyvoice-v3-flash','voiceId':'longanwen_v3','providerPronunciation':provider_pronunciation(text)})
            comparison=compare_transcript(self.plan,text,text)
            segments.append({'sceneId':scene['id'],'actionId':action['id'],'text':text,'textSha256':sha_text(text),'ttsRequestId':request,
                'audioSha256':audio_sha,'transcript':text,'comparison':comparison,'similarityBps':10000,
                'asr':{'status':'succeeded','requestId':asr_request_id(self.plan,request,audio_sha),'transcript':text,
                       'transcriptSha256':sha_text(text),'providerAsrBodySha256':'9'*64,'providerId':'qwen-asr','modelId':'qwen3-asr-flash','providerPronunciation':provider_pronunciation(text)}})
            heard.append({'sceneId':scene['id'],'actionId':action['id'],'textSha256':sha_text(text),'ttsRequestId':request,
                'audioSha256':audio_sha,'verdict':'accepted','reviewer':'Synthetic listener','reviewedAt':now_ms()-1000,'basis':'Isolated fixture'})
        self.classroom['scenes'][2]['content']['questions'][0]['questionAudioUrl']=self.classroom['scenes'][0]['actions'][0]['audioUrl']
        self.listening=sign({'schemaVersion':LISTENING_SCHEMA,'previewKey':self.key,'planSha256':digest(self.plan),'coreSha256':self.plan['coreSha256'],'segments':heard})
        self.audit=sign({'schemaVersion':'mira.textbook.audio-audit.v2','previewKey':self.key,'sourceSha256':digest(self.classroom),
            'passed':True,'contract':audit_contract_identity(self.plan),'segments':segments,'listeningReview':self.listening})
        self.review={'alignmentConfirmed':True,'originalExpressionConfirmed':True,'sourceUsageConfirmed':True,'publicationAuthorized':True,
            'reviewer':'Fixture','basis':'Isolated fixture','sourceSha256':digest(self.classroom),'reviewedAt':now_ms()-1}
        (self.root/(self.cid+'.json')).write_text(canonical(self.classroom))
        self.row={'status':'preview_ready','classroom_id':self.cid,'classroom_json':canonical(self.classroom),'classroom_sha256':digest(self.classroom),
            'edition_id':PINYIN_BINDING['editionId'],'node_id':'u2-l1','input_json':canonical(frozen_input),'result_json':canonical({'audioReceipts':receipts})}
        repo=MagicMock();repo.parse.side_effect=json.loads;repo.get_revision.return_value={'manifest_sha256':digest(self.manifest)};repo.manifest.return_value=self.manifest
        preview=Mock(repository=repo,runtime=Mock(base_url='http://127.0.0.1:3100'));preview.get.return_value=self.row
        self.service=TextbookPublicationService(preview)

    def prepare(self):
        return self.service.prepare(key=self.key,edition=PINYIN_BINDING['editionId'],revision=PINYIN_BINDING['alignmentRevisionId'],node='u2-l1',teaching_revision='1',review=self.review,audio_audit=self.audit,classroom_directory=self.root)

    def build(self, prepared):
        return {'status':'published','input_json':canonical(prepared['frozen']),'review_json':canonical(prepared['review']),
            'content_key':prepared['frozen']['contentKey'],'node_id':'u2-l1','teaching_revision':'1'}

    def test_real_archive_keeps_listening_evidence_and_read_validation(self):
        prepared=self.prepare()
        self.assertEqual(prepared['release']['audioAudit']['listeningReview'],self.listening)
        self.assertEqual(validate_release(self.build(prepared),self.manifest)['sha256'],prepared['release']['sha256'])
        # Even recomputing outer hashes cannot make a failed human verdict pass.
        prepared['review']['release']['audioAudit']['listeningReview']['segments'][0]['verdict']='rejected'
        sign(prepared['review']['release']['audioAudit']['listeningReview']);sign(prepared['review']['release'])
        with self.assertRaises(ApiError):validate_release(self.build(prepared),self.manifest)

    def test_missing_repeated_sample_rejection_probe_and_wrong_audio_never_publish(self):
        original=deepcopy(self.listening)
        for kind in ('missing','rejected','pending','probe','wrong_audio','wrong_plan','wrong_text','duplicate','bad_scene'):
            self.listening=deepcopy(original);self.audit['listeningReview']=self.listening
            item=self.listening['segments'][0]
            if kind=='missing':self.listening['segments'].pop()
            elif kind in ('rejected','pending'):item['verdict']=kind
            elif kind=='probe':item['ttsRequestId']='probe_123'
            elif kind=='wrong_audio':item['audioSha256']='0'*64
            elif kind=='wrong_plan':self.listening['planSha256']='0'*64
            elif kind=='wrong_text':item['textSha256']='0'*64
            elif kind=='bad_scene':item['sceneId']=[]
            else:self.listening['segments'].append(deepcopy(item))
            sign(self.listening);sign(self.audit)
            with self.subTest(kind=kind),self.assertRaises(ApiError):self.prepare()
        self.audit.pop('listeningReview');sign(self.audit)
        with self.assertRaises(ApiError):self.prepare()

    def test_tts_and_asr_actual_provider_body_cannot_be_relabelled(self):
        result=json.loads(self.row['result_json']);result['audioReceipts'][0]['providerPronunciation']['providerBodySha256']='0'*64
        self.row['result_json']=canonical(result)
        with self.assertRaises(ApiError):self.prepare()

    def test_asr_top_level_cannot_claim_tts_provider_even_with_valid_nested_identity(self):
        self.audit['segments'][0]['asr']['providerId']='aliyun-cosyvoice'
        sign(self.audit)
        with self.assertRaises(ApiError):self.prepare()


if __name__=='__main__':unittest.main()
