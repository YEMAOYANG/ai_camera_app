"""Whole-question zoom, input-frame geometry and safe historical read projection."""
from copy import deepcopy
import hashlib
import io
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from PIL import Image,ImageDraw
from core.errors import ApiError
from integrations.ai.kimi_vision_provider import AiVisionResponse
from services.homework_tutor_service import (POLICY,SCHEMA,encoded,image_contract_valid,
    input_geometry_hints,parse_response,region_to_input,remap_image_response,sha,teacher_input_image,teaching_view)
from tests.test_homework_analysis import HomeworkTest
from tests.test_homework_tutor import teacher_reply
from tests.test_homework_tutor_image_guidance import image_observation


def image_bytes(width=1000,height=1200):
    image=Image.new('RGB',(width,height),'white')
    draw=ImageDraw.Draw(image)
    draw.rectangle((100,200,899,500),fill=(13,71,145))
    draw.text((140,220),'Original printed labels',fill='white')
    output=io.BytesIO();image.save(output,format='PNG')
    return output.getvalue(),image


def tencent_source(**updates):
    return {'method':'tencent_question.v1','region':{'x':.1,'y':.2,'width':.8,'height':.25},
        'providerAssessment':{'answerRegion':{'x':.7,'y':.35,'width':.1,'height':.06}},
        'sourceValidation':{'provider':'tencent','geometryVerified':True,'angleVerified':True,
            'trusted':False,'issues':['multiple_answer_alignment_unverified']},**updates}


class HomeworkTeacherInputWindowTests(TestCase):
    def test_narrow_fill_in_row_keeps_objects_and_shared_stem_above_it(self):
        image=Image.new('RGB',(3000,4000),'white');draw=ImageDraw.Draw(image)
        # The figure is above a legal Tencent fill-in-row rectangle. Geometry
        # and answer containment alone used to cut this required context away.
        draw.ellipse((590,310,680,400),fill='red')
        draw.ellipse((710,310,800,400),fill='green')
        draw.text((570,460),'Use the pictured objects to fill the boxes',fill='black')
        draw.rectangle((573,549,1221,709),outline='black')
        body=io.BytesIO();image.save(body,format='PNG');original=body.getvalue()
        result=tencent_source(region={'x':.191,'y':.13725,'width':.216333,'height':.04025},
            providerAssessment={'answerRegion':{'x':.37,'y':.15,'width':.02,'height':.02}})
        selected,contract=teacher_input_image(original,image,result,POLICY)
        self.assertEqual(selected,original)
        self.assertEqual(contract['selection'],'full_page')
        self.assertTrue(contract['contextGuard']['geometryVerified'])
        self.assertFalse(contract['contextGuard']['questionWindowSuitable'])
        self.assertEqual(Image.open(io.BytesIO(selected)).getpixel((635,355)),(255,0,0))
        self.assertTrue(image_contract_valid(contract))

    def test_complete_queue_diagram_retains_large_original_pixel_crop(self):
        original,photo=image_bytes(3000,4000)
        result=tencent_source(region={'x':.052,'y':.30,'width':.846,'height':.16},
            providerAssessment={'answerRegion':{'x':.25,'y':.42,'width':.02,'height':.015}})
        selected,contract=teacher_input_image(original,photo,result,POLICY)
        self.assertEqual(contract['selection'],'question_region')
        self.assertEqual(contract['inputGeometry'],{'width':2570,'height':672})
        self.assertTrue(contract['contextGuard']['questionWindowSuitable'])
        self.assertEqual(Image.open(io.BytesIO(selected)).tobytes(),photo.crop((140,1184,2710,1856)).tobytes())

    def test_thin_small_area_or_long_line_windows_fall_back_without_padding_bypass(self):
        original,photo=image_bytes(3000,4000)
        for region in ({'x':.1,'y':.1,'width':.8,'height':.08},
                {'x':.1,'y':.1,'width':.1,'height':.15},
                {'x':.1,'y':.1,'width':.8,'height':.09}):
            answer={'x':region['x']+.01,'y':region['y']+.01,'width':.02,'height':.02}
            with self.subTest(region=region):
                selected,contract=teacher_input_image(original,photo,tencent_source(region=region,
                    providerAssessment={'answerRegion':answer}),POLICY)
                self.assertEqual(selected,original)
                self.assertEqual(contract['selection'],'full_page')
                self.assertFalse(contract['contextGuard']['questionWindowSuitable'])

    def test_new_contract_rechecks_context_instead_of_trusting_a_claimed_crop(self):
        original,photo=image_bytes();_,valid=teacher_input_image(original,photo,tencent_source(),POLICY)
        missing=deepcopy(valid);missing.pop('contextGuard')
        claimed=deepcopy(valid)
        claimed['contextGuard']['sourceQuestionRegionInOriginalPage']={'x':.1,'y':.2,'width':.8,'height':.04}
        claimed['contextGuard']['questionWindowSuitable']=True
        partial=deepcopy(valid);partial['selection']='full_page'
        for contract in (missing,claimed,partial):
            with self.subTest(contract=contract):self.assertFalse(image_contract_valid(contract))

    def test_trusted_question_crop_preserves_pixels_prompt_diagram_and_answer_with_padding(self):
        image,photo=image_bytes();source=tencent_source();before=deepcopy(source)
        cropped,contract=teacher_input_image(image,photo,source,POLICY)
        self.assertEqual(contract['selection'],'question_region')
        self.assertEqual(contract['inputPixelBounds'],{'left':84,'top':224,'right':916,'bottom':556})
        self.assertEqual(contract['inputGeometry'],{'width':832,'height':332})
        self.assertEqual(contract['originalPageGeometry'],{'width':1000,'height':1200})
        actual=Image.open(io.BytesIO(cropped))
        self.assertEqual(actual.size,(832,332))
        self.assertEqual(actual.tobytes(),photo.crop((84,224,916,556)).tobytes())
        self.assertNotEqual(cropped,image)
        self.assertEqual(contract['sourceImageSha256'],hashlib.sha256(image).hexdigest())
        self.assertEqual(contract['inputImageSha256'],hashlib.sha256(cropped).hexdigest())
        self.assertTrue(image_contract_valid(contract))
        self.assertEqual(source,before)

    def test_unverified_wrong_frame_or_blank_only_region_keeps_original_page(self):
        image,photo=image_bytes()
        cases=[tencent_source(sourceValidation={'geometryVerified':False,'angleVerified':True}),
            tencent_source(sourceValidation={'geometryVerified':True,'angleVerified':False}),
            tencent_source(providerAssessment={'geometryVerified':False,'answerRegion':{'x':.7,'y':.35,'width':.1,'height':.06}}),
            tencent_source(region={'x':.7,'y':.35,'width':.1,'height':.06}),
            tencent_source(region={'x':.1,'y':.1,'width':.1,'height':.1}),
            tencent_source(region={'x':.1,'y':.1,'width':2,'height':1}),
            tencent_source(providerAssessment={}),{},
            tencent_source(sourceValidation='untrusted metadata'),
            tencent_source(sourceValidation={'geometryVerified':True,'angleVerified':True},providerAssessment={'answerRegion':{'x':True,'y':0,'width':.1,'height':.1}})]
        for result in cases:
            with self.subTest(result=result):
                selected,contract=teacher_input_image(image,photo,result,POLICY)
                self.assertEqual(selected,image)
                self.assertEqual(contract['selection'],'full_page')
                self.assertEqual(contract['inputWindow'],{'x':0,'y':0,'width':1,'height':1})

    def test_incoming_hints_only_survive_inside_selected_image_and_are_local(self):
        image,photo=image_bytes();_,contract=teacher_input_image(image,photo,tencent_source(),POLICY)
        answer=tencent_source()['providerAssessment']['answerRegion']
        local=region_to_input(answer,contract)
        self.assertAlmostEqual(local['x'],(700-84)/832,places=6)
        self.assertAlmostEqual(local['y'],(420-224)/332,places=6)
        outside={'x':.01,'y':.01,'width':.1,'height':.1}
        hints=input_geometry_hints({'region':outside,'answerRegions':[answer,outside],
            'nested':{'questionRegion':answer,'HandwriteInfoPositions':[1,2,3,4],
                'Coord':{'X':32,'Y':54}}},contract)
        self.assertNotIn('region',hints)
        self.assertEqual(hints['answerRegions'],[local])
        self.assertEqual(hints['nested'],{'questionRegion':local})

    def test_model_rectangles_map_once_before_strict_parser_including_picture_choices(self):
        image,photo=image_bytes();_,contract=teacher_input_image(image,photo,tencent_source(),POLICY)
        reply=teacher_reply(sourceCheck=image_observation(questionRegion={'x':0,'y':0,'width':1,'height':1}),
            steps=[{'text':'看原图','visual':{'kind':'paper_region','region':{'x':.25,'y':.25,'width':.5,'height':.5}}},
                {'text':'看两张原题图片','visual':{'kind':'choices','choices':[
                    {'region':{'x':.1,'y':.1,'width':.2,'height':.2}},
                    {'region':{'x':.6,'y':.1,'width':.2,'height':.2}}]}}])
        raw=encoded(reply);mapped=json.loads(remap_image_response(raw,contract))
        self.assertEqual(encoded(reply),raw)
        self.assertEqual(mapped['sourceCheck']['questionRegion'],{'x':.084,'y':.186667,'width':.832,'height':.276667})
        self.assertEqual(mapped['steps'][0]['visual']['region'],{'x':.292,'y':.255833,'width':.416,'height':.138333})
        self.assertAlmostEqual(mapped['steps'][1]['visual']['choices'][1]['region']['x'],.5832,places=6)
        self.assertNotEqual(mapped['steps'][1]['visual']['choices'][0]['region'],reply['steps'][1]['visual']['choices'][0]['region'])
        parsed=parse_response(encoded(mapped),policy=POLICY,result={'prompt':'3 + 2 =','studentAnswer':'4',
            'confidence':.99,'type':'choice','region':tencent_source()['region']},mode='explain')
        self.assertEqual(parsed['steps'][1]['visual']['kind'],'choices')
        self.assertEqual(parsed['steps'][1]['visual']['choices'][1]['region'],mapped['steps'][1]['visual']['choices'][1]['region'])

    def test_pixel_boolean_nonfinite_and_duplicate_model_regions_are_rejected(self):
        image,photo=image_bytes();_,contract=teacher_input_image(image,photo,tencent_source(),POLICY)
        for region in ({'x':42,'y':0,'width':100,'height':50},{'x':True,'y':0,'width':.1,'height':.1},
                {'x':0,'y':0,'width':float('nan'),'height':.1},None):
            with self.subTest(region=region),self.assertRaises(ValueError):
                remap_image_response(json.dumps({'sourceCheck':{'questionRegion':region}}),contract)
        with self.assertRaises(ValueError):
            remap_image_response('{"sourceCheck":{"questionRegion":{"x":0,"x":0.1,"y":0,"width":0.1,"height":0.1}}}',contract)

    def test_malformed_or_v4_server_binding_cannot_enable_history_audio(self):
        image,photo=image_bytes();_,valid=teacher_input_image(image,photo,tencent_source(),POLICY)
        for update in ({'promptVersion':'v4'},{'promptVersion':'v5'},
                {'schemaVersion':'mira.homework-tutor-image-input.v1'},
                {'inputPixelBounds':{'left':84,'top':224,'right':9000,'bottom':556}},
                {'inputWindow':{'x':0,'y':0,'width':1,'height':1}},
                {'originalPageGeometry':[]},{'inputImageSha256':'not-a-hash'}):
            with self.subTest(update=update): self.assertFalse(image_contract_valid({**valid,**update}))


class HomeworkTeacherWindowFlowTests(TestCase):
    def setUp(self):
        HomeworkTest.setUp(self)
        self.service.tutor.policy={**self.service.tutor.policy,'unreferencedTencentImageTeaching':True}
    create=HomeworkTest.create
    upload=HomeworkTest.upload
    ready=HomeworkTest.ready
    events=HomeworkTest.events

    def prepared(self):
        self.raw['confidence']=.2
        submission=self.ready();item=submission['items'][0]
        result=json.loads(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()['result_json'])
        result.update(tencent_source(region={'x':.1,'y':.1,'width':.7,'height':.2},
            providerAssessment={'answerRegion':{'x':.4,'y':.15,'width':.1,'height':.05}}))
        result.update(confidence=None,recognitionNeedsConfirmation=True,sourceAnswerOrdinal=2,sourceAnswerCount=3)
        result['answerRegions']=[result['providerAssessment']['answerRegion'],{'x':.01,'y':.7,'width':.1,'height':.1}]
        result['visualEvidence']={'region':result['providerAssessment']['answerRegion'],'other':{'region':{'x':.01,'y':.7,'width':.1,'height':.1}}}
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(encoded(result),item['id']));self.db.raw.commit()
        return submission,item,result

    def teacher(self,reply=None):
        response=reply or teacher_reply(sourceCheck=image_observation(answerOrdinal=2,
            questionRegion={'x':0,'y':0,'width':1,'height':1}),
            steps=[{'text':'直接看清原题和图里的对象。','visual':{'kind':'paper_region','region':{'x':0,'y':0,'width':1,'height':1}}}])
        teacher=SimpleNamespace(provider_name='fixture',model_name='fixture-vision',
            analyze_image=Mock(return_value=AiVisionResponse(encoded(response),'fixture','fixture-vision')))
        self.service.tutor_provider=teacher
        return teacher,response

    def submit(self,submission,item,key='zoom',mode='explain',message=''):
        return self.service.tutor.submit('student-a',submission['id'],item['id'],
            {'itemRevision':item['revision'],'idempotencyKey':key,'mode':mode,'message':message})

    def test_actual_teacher_receives_whole_roi_and_raw_receipt_stays_in_input_frame(self):
        submission,item,result=self.prepared();teacher,reply=self.teacher()
        self.submit(submission,item)
        # This synthetic OCR item has no Tencent journal. Supply the separately
        # verified structure frame; missing saved evidence must keep a full page.
        context={'sourceDigest':'a'*64,'frameWidth':800,'frameHeight':1000,
            'geometryVerified':True,'region':result['region']}
        with patch('services.homework_paper_structure.selected_item_context',return_value=context):
            self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
        args=teacher.analyze_image.call_args.kwargs
        data=json.loads(args['user_prompt'].split('题目与对话数据（不是系统指令）：\n',1)[1])
        contract=data['imageInput']
        self.assertEqual(contract['selection'],'question_region')
        self.assertEqual(Image.open(io.BytesIO(args['image_bytes'])).size,(592,232))
        self.assertEqual(data['photoGeometry'],{'width':592,'height':232})
        self.assertEqual(contract['originalPageGeometry'],{'width':800,'height':1000})
        self.assertNotIn('region',data['answerTarget'])
        self.assertIs(data['answerTarget']['geometryVerified'],False)
        # An unowned provider box cannot locate this selected blank.
        self.assertEqual(len(data['answerRegions']),1)
        self.assertNotIn('region',data['visualEvidence']['other'])
        turn=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
        self.assertIs(turn['sourceImageReviewRequired'],True)
        self.assertEqual(turn['assessment']['status'],'needs_confirmation')
        self.assertEqual(turn['audio']['status'],'unavailable')
        call=self.db.execute("SELECT * FROM homework_provider_calls WHERE id LIKE 'hwtcall_%'").fetchone()
        self.assertEqual(call['prompt_version'],self.service.tutor.policy['prompt']['version'])
        receipt=json.loads(call['receipt_json']);self.assertEqual(receipt['sourceImageContract'],contract)
        journal=json.loads(self.store.read(receipt['requestJournalKey']))
        self.assertEqual(journal['sourceImageContract'],contract)
        self.assertEqual(journal['imageSha256'],hashlib.sha256(args['image_bytes']).hexdigest())
        raw=json.loads(self.store.read(receipt['responseJournalKey']))
        self.assertEqual(raw['text'],encoded(reply))
        self.assertEqual(raw['sourceImageContract'],contract)
        self.assertEqual(json.loads(call['result_json'])['sourceCheck']['questionRegion'],{'x':.08,'y':.084,'width':.74,'height':.232})
        self.assertNotIn('questionRegion',turn['sourceCheck'])
        self.assertEqual(json.loads(self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()['result_json']),result)
        self.assertEqual(self.events(),[])
        self.submit(submission,item)
        self.assertEqual(teacher.analyze_image.call_count,1)

    def test_old_v4_audio_is_blocked_and_wrong_assistant_history_never_anchors_zoom(self):
        submission,item,result=self.prepared();teacher,_=self.teacher()
        queued=self.submit(submission,item,key='historical')['tutor']['turns'][0]
        original=json.loads(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(queued['id'],)).fetchone()['result_json'])
        # A historical v4 turn predates the server's review-scope fingerprint;
        # record its old input version so an explicit upgraded look is allowed.
        original.pop('reviewScopeSha256',None)
        original.update(status='ready',mode='followup',message='为什么这个人排这里？',
            sourceImageContract={'schemaVersion':'mira.homework-tutor-image-input.v1','promptVersion':'v4'},
            teacherText='旧老师凭模糊姓名猜测出错误位置。',sourceCheck=image_observation(prompt='模糊小字被猜成了错误对象'),
            teachingScope='original_image_guidance',steps=[{'text':'旧的错误推理','visual':{'kind':'quantity','count':3}}],
            assessment={'status':'guidance_only','reason':'错误旧观察','expectedAnswer':'3'},
            audio={'status':'ready','storageKey':'never-read-old-audio'})
        private=encoded(original)
        self.db.execute('UPDATE homework_actions SET result_json=? WHERE id=?',(private,queued['id']));self.db.raw.commit()
        projected=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
        self.assertIs(projected['sourceImageReviewRequired'],True)
        self.assertIs(projected['sourceConfirmationOnly'],True)
        self.assertIn('答案还没有核实',projected['teacherText'])
        self.assertNotIn('猜测',projected['teacherText'])
        self.assertEqual(projected['assessment']['expectedAnswer'],'')
        self.assertEqual(projected['audio']['status'],'unavailable')
        self.assertNotIn('assetUrl',projected['audio'])
        with self.assertRaises(ApiError) as error:
            self.service.tutor.audio('student-a',submission['id'],item['id'],queued['id'])
        self.assertEqual(error.exception.code,'homework_tutor_audio_not_ready')
        self.assertEqual(teacher.analyze_image.call_count,0)
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(queued['id'],)).fetchone()['result_json'],private)
        self.submit(submission,item,key='explicit-zoom')
        self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
        data=json.loads(teacher.analyze_image.call_args.kwargs['user_prompt'].split('题目与对话数据（不是系统指令）：\n',1)[1])
        self.assertEqual(data['history'],[{'mode':'followup','message':'为什么这个人排这里？'}])
        self.assertNotIn('旧老师',encoded(data))

    def test_already_saved_v5_partial_context_cannot_play_resume_or_certify_a_paper_grade(self):
        submission,item,result=self.prepared();teacher,_=self.teacher()
        queued=self.submit(submission,item,key='v5-partial')['tutor']['turns'][0]
        old=json.loads(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(queued['id'],)).fetchone()['result_json'])
        page={'width':3000,'height':4000};bounds={'left':557,'top':533,'right':1238,'bottom':726}
        legacy={'schemaVersion':'mira.homework-tutor-image-input.v1','promptVersion':'v5',
            'selection':'question_region','modelCoordinateFrame':'input_image','responseCoordinateFrame':'original_page',
            'originalPageGeometry':page,'inputPixelBounds':bounds,'inputGeometry':{'width':681,'height':193},
            'inputWindow':{'x':557/3000,'y':533/4000,'width':681/3000,'height':193/4000},
            'sourceImageSha256':'a'*64,'inputImageSha256':'b'*64}
        old.update(status='ready',sourceImageContract=legacy,sourceImageReviewRequired=False,
            teacherText='缺配图时只看到了方框与圆圈。',teachingScope='original_image_guidance',
            sourceCheck=image_observation(status='unclear',questionReadable=False,prompt='□○□=□'),
            sourceConfirmationOnly=True,assessment={'status':'needs_confirmation','reason':'只有填空行','expectedAnswer':''},
            audio={'status':'ready','storageKey':'old-v5-narration'})
        private=encoded(old)
        self.db.execute('UPDATE homework_actions SET result_json=? WHERE id=?',(private,queued['id']));self.db.raw.commit()
        for _ in range(2):
            projected=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
            self.assertTrue(projected['sourceImageReviewRequired'])
            self.assertEqual(projected['audio']['status'],'unavailable')
            self.assertNotIn('assetUrl',projected['audio'])
            self.assertNotIn('方框',projected['teacherText'])
            self.assertEqual(projected['assessment']['expectedAnswer'],'')
        with self.assertRaises(ApiError) as error:
            self.service.tutor.resume_audio('student-a',submission['id'],item['id'],queued['id'],
                {'itemRevision':item['revision'],'idempotencyKey':'old-v5-voice'})
        self.assertEqual(error.exception.code,'homework_tutor_source_unconfirmed')
        self.assertEqual(teacher.analyze_image.call_count,0)
        self.assertEqual(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(queued['id'],)).fetchone()['result_json'],private)
        self.assertEqual(self.events(),[])

    def test_new_v6_true_unclear_is_not_marked_for_another_automatic_paid_review(self):
        submission,item,result=self.prepared()
        teacher,_=self.teacher(teacher_reply(sourceCheck=image_observation(status='unclear',questionReadable=False,
            answerLocated=False,studentAnswerReadable=False,prompt='',reason='人物之间的小字和指向线还看不清。',
            questionRegion={'x':0,'y':0,'width':1,'height':1})))
        self.submit(submission,item)
        self.assertTrue(self.service.process_next(submission_id=submission['id'])['ok'])
        for _ in range(3):
            turn=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
            self.assertIs(turn['sourceImageReviewRequired'],True)
            self.assertIs(turn['sourceConfirmationOnly'],True)
            self.assertEqual(turn['assessment']['expectedAnswer'],'')
            self.assertIn('答案还没有核实',turn['teacherText'])
            self.assertEqual(turn['audio']['status'],'unavailable')
        self.assertEqual(teacher.analyze_image.call_count,1)

    def test_non_ready_states_never_claim_historical_image_review_required(self):
        submission,item,result=self.prepared();self.teacher()
        turn=self.submit(submission,item)['tutor']['turns'][0]
        value=json.loads(self.db.execute('SELECT result_json FROM homework_actions WHERE id=?',(turn['id'],)).fetchone()['result_json'])
        for state in ('queued','working','failed','unknown'):
            current={**value,'status':state,'assessment':None,'sourceCheck':image_observation(),
                'sourceImageReviewRequired':True}
            self.db.execute('UPDATE homework_actions SET result_json=? WHERE id=?',(encoded(current),turn['id']));self.db.raw.commit()
            projected=self.service.tutor.get('student-a',submission['id'],item['id'])['tutor']['turns'][0]
            self.assertIs(projected['sourceImageReviewRequired'],False)
            self.assertIsNone(projected['assessment'])

    def test_old_dispatched_hash_is_not_replayed_with_new_crop_or_prompt(self):
        submission,item,result=self.prepared();teacher,_=self.teacher()
        turn=self.submit(submission,item)['tutor']['turns'][0]
        call_id='hwtcall_'+sha(turn['id'])[:56]
        self.db.execute('INSERT INTO homework_provider_calls (id,submission_id,page_id,child_id,request_sha256,status,provider,model,prompt_version,receipt_json,dispatched_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (call_id,submission['id'],item['pageId'],'child-a','old-v4-whole-page-hash','dispatched','fixture','fixture-vision','v4','{}',self.clock(),self.clock(),self.clock()))
        self.db.raw.commit()
        outcome=self.service.process_next(submission_id=submission['id'])
        self.assertEqual(outcome['error'],'homework_tutor_scope_changed')
        self.assertEqual(teacher.analyze_image.call_count,0)
        self.assertEqual(self.db.execute('SELECT status FROM homework_provider_calls WHERE id=?',(call_id,)).fetchone()['status'],'dispatched')

    def test_bad_model_pixel_coordinates_preserve_raw_receipt_without_repair_or_more_calls(self):
        submission,item,result=self.prepared()
        invalid=teacher_reply(sourceCheck=image_observation(questionRegion={'x':32,'y':80,'width':400,'height':50}))
        teacher,_=self.teacher(invalid)
        self.submit(submission,item)
        outcome=self.service.process_next(submission_id=submission['id'])
        self.assertEqual(outcome['error'],'homework_tutor_response_invalid')
        call=self.db.execute("SELECT * FROM homework_provider_calls WHERE id LIKE 'hwtcall_%'").fetchone()
        self.assertEqual(call['status'],'returned_invalid')
        receipt=json.loads(call['receipt_json'])
        self.assertEqual(json.loads(self.store.read(receipt['responseJournalKey']))['text'],encoded(invalid))
        self.assertFalse(self.service.process_next(submission_id=submission['id'])['processed'])
        self.assertEqual(teacher.analyze_image.call_count,1)
        self.assertEqual(self.events(),[])
