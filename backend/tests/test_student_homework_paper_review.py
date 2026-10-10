"""Private paper-review GETs use saved analysis, never new AI or answer events."""
import io
import json
import unittest
from unittest.mock import patch

from flask import Flask
from PIL import Image

from integrations.ai.kimi_vision_provider import AiVisionResponse
from services.homework_service import canonical
import test_homework_analysis as homework_fixture


class StudentHomeworkPaperReviewTest(unittest.TestCase):
    setUp=homework_fixture.HomeworkTest.setUp
    create=homework_fixture.HomeworkTest.create
    upload=homework_fixture.HomeworkTest.upload
    ready=homework_fixture.HomeworkTest.ready
    error=homework_fixture.HomeworkTest.error
    events=homework_fixture.HomeworkTest.events

    def app(self):
        from routes.api.v2.student_homework import student_homework_bp
        app=Flask(__name__)
        app.register_blueprint(student_homework_bp,url_prefix='/api/v2/student/learning')
        return app

    def test_student_photo_get_is_private_and_read_only(self):
        s=self.ready()
        changes=self.db.raw.total_changes
        events=self.events()
        call_counts=(self.provider.analyze_image.call_count,self.transport.call_count)
        with patch('services.service_factory.homework_service',return_value=self.service):
            client=self.app().test_client()
            headers={'Authorization':'Bearer student-a'}
            detail=client.get(f"/api/v2/student/learning/homework/{s['id']}",headers=headers)
            self.assertEqual(detail.status_code,200)
            page=detail.json['submission']['pages'][0]
            self.assertEqual(page['assetUrl'],f"/api/v2/student/learning/homework/{s['id']}/pages/{page['id']}/image")
            image=client.get(page['assetUrl'],headers=headers)
            self.assertEqual(image.status_code,200)
            self.assertEqual(image.content_type,'image/png')
            self.assertEqual(image.headers['Cache-Control'],'private, no-store')
            self.assertEqual(image.headers['X-Content-Type-Options'],'nosniff')
            self.assertEqual(image.headers['Content-Security-Policy'],"default-src 'none'")
            self.assertNotIn('storageKey',page)
            self.assertNotIn('contentSha256',page)
            self.assertEqual(client.get(page['assetUrl'],headers={'Authorization':'Bearer student-b'}).status_code,404)
            self.assertEqual(client.get(page['assetUrl']).status_code,401)
            self.assertEqual(client.get(page['assetUrl'],headers={'Authorization':'Bearer parent-a'}).status_code,401)
            for query in ('?original=1','?original=0','?cache=x'):
                self.assertEqual(client.get(page['assetUrl']+query,headers=headers).status_code,400)
        self.assertEqual(self.db.raw.total_changes,changes)
        self.assertEqual(self.events(),events)
        self.assertEqual((self.provider.analyze_image.call_count,self.transport.call_count),call_counts)

    def test_student_image_checks_family_child_and_page_ownership(self):
        s=self.upload(self.create());page=s['pages'][0]
        other=self.upload(self.create('other'));other_page=other['pages'][0]
        self.error('homework_not_found',lambda:self.service.image('student-b',s['id'],page['id'],student=True))
        self.error('homework_page_not_found',lambda:self.service.image('student-a',s['id'],other_page['id'],student=True))
        self.db.execute('INSERT INTO children VALUES (?,?,?,?)',('child-a2','family-a','primary_1',1));self.db.raw.commit()
        with patch.object(self.service.student_auth,'authenticate',return_value={'principal':{'family_id':'family-a','child_id':'child-a2'}}):
            self.error('homework_not_found',lambda:self.service.image('student-a2',s['id'],page['id'],student=True))
        self.error('homework_original_parent_only',lambda:self.service.image('student-a',s['id'],page['id'],student=True,original=True))

    def test_deleted_submission_and_removed_page_revoke_student_photo(self):
        s=self.upload(self.create());page=s['pages'][0]
        self.service.delete('parent-a',s['id'],{'revision':s['revision']})
        self.error('homework_not_found',lambda:self.service.image('student-a',s['id'],page['id'],student=True))
        other=self.upload(self.create('remove-page'));page=other['pages'][0]
        self.service.update_pages('parent-a',other['id'],{'revision':other['revision'],'pages':[]})
        self.error('homework_page_not_found',lambda:self.service.image('student-a',other['id'],page['id'],student=True))
        self.assertEqual(self.service.student_detail('student-a',other['id'])['submission']['pages'],[])
        self.provider.analyze_image.assert_not_called();self.transport.assert_not_called()

    def test_photo_metadata_and_region_use_current_rotation_crop(self):
        s=self.upload(self.create());page=s['pages'][0]
        crop={'x':0.1,'y':0.1,'width':0.8,'height':0.8}
        s=self.service.update_pages('parent-a',s['id'],{'revision':s['revision'],'pages':[{'id':page['id'],'rotation':90,'crop':crop}]})['submission']
        self.service.analyze('parent-a',s['id'],{'revision':s['revision']});self.assertTrue(self.service.process_next()['ok'])
        student=self.service.student_detail('student-a',s['id'])['submission']
        display=student['pages'][0]
        self.assertEqual((display['width'],display['height']),(800,640))
        self.assertEqual(display['rotation'],90);self.assertEqual(display['crop'],crop)
        image,mime=self.service.image('student-a',s['id'],page['id'],student=True)
        self.assertEqual(mime,'image/png')
        with Image.open(io.BytesIO(image)) as opened:self.assertEqual(opened.size,(display['width'],display['height']))
        self.assertEqual(image,self.provider.analyze_image.call_args.kwargs['image_bytes'])
        original,_=self.service.image('parent-a',s['id'],page['id'],original=True)
        self.assertNotEqual(image,original)
        parent=self.service.get('parent-a',s['id'])['submission']['pages'][0]
        self.assertEqual((parent['width'],parent['height']),(800,1000))
        self.assertEqual(student['items'][0]['reviewContext']['region'],self.raw['region'])

    def test_review_context_is_saved_wrong_answer_and_full_analysis_ordinal(self):
        # The uncertain repetition is a different paper location from item 5;
        # an exact overlapping duplicate must now remain unverified.
        raw=[{**self.raw,'studentAnswer':'5','region':{'x':0.1,'y':0.7,'width':0.7,'height':0.05}},{**self.raw,'confidence':0.1,'region':{'x':0.1,'y':0.4,'width':0.7,'height':0.2}},
             {**self.raw,'studentAnswer':'','region':{'x':0.1,'y':0.8,'width':0.7,'height':0.05}},{**self.raw,'prompt':'应用题','type':'unsupported'},
             self.raw,{**self.raw,'prompt':'2+2=','studentAnswer':'3','region':None}]
        self.provider.analyze_image.side_effect=lambda **kw:AiVisionResponse(json.dumps({'pageReadable':True,'items':raw}),'fixture','fixture-vision')
        s=self.ready();events=self.events();changes=self.db.raw.total_changes
        student=self.service.student_detail('student-a',s['id'])['submission']
        self.assertEqual(student['originalSummary'],{'total':6,'correct':1,'incorrect':1,'blank':1,'pending':2,'unsupported':1})
        self.assertEqual(len(student['items']),1)
        first=student['items'][0]
        self.assertEqual(first['reviewContext'],{'pageId':s['pages'][0]['id'],'region':self.raw['region'],'originalAnswer':'4','originalOrdinal':5,
            'recognitionConfirmed':False,'recognitionNeedsConfirmation':False})
        unlocated=student['tutorItems'][-1]
        self.assertEqual(unlocated['status'],'pending')
        self.assertIsNone(unlocated['reviewContext']['region'])
        self.assertTrue(unlocated['reviewContext']['recognitionNeedsConfirmation'])
        for item in student['items']:
            for private in ('expectedAnswer','explanation','studentAnswer','region','voiceTexts'):
                self.assertNotIn(private,item)
            self.assertFalse(item['explanationViewed'])
        self.assertEqual(self.db.raw.total_changes,changes);self.assertEqual(self.events(),events)
        self.error('homework_audio_not_open',lambda:self.service.audio_asset('student-a',s['id'],first['id'],'explanation',student=True))
        explained=self.service.student_action('student-a',s['id'],first['id'],{'itemRevision':first['revision'],'action':'explanation'})['submission']['items'][0]
        self.assertEqual(explained['expectedAnswer'],'5');self.assertIn('等于5',explained['explanation'])
        self.assertEqual(explained['reviewContext'],first['reviewContext'])
        self.assertEqual(self.events(),events)

    def test_unverified_status_does_not_get_review_context(self):
        s=self.ready();item=s['items'][0]
        row=self.db.execute('SELECT result_json FROM homework_items WHERE id=?',(item['id'],)).fetchone()
        result=json.loads(row['result_json']);result['method']='unverified'
        self.db.execute('UPDATE homework_items SET result_json=? WHERE id=?',(canonical(result),item['id']));self.db.raw.commit()
        student=self.service.student_detail('student-a',s['id'])['submission']['items'][0]
        self.assertNotIn('reviewContext',student)
        self.assertNotIn('studentAnswer',student);self.assertNotIn('expectedAnswer',student)

    def test_internal_paid_validation_is_not_a_student_assignment(self):
        s=self.ready()
        self.db.execute('UPDATE homework_submissions SET source=? WHERE id=?',('paid_validation',s['id']));self.db.raw.commit()
        changes=self.db.raw.total_changes
        self.assertEqual(self.service.list_student('student-a')['submissions'],[])
        self.assertEqual(self.db.raw.total_changes,changes)
        self.assertEqual(self.service.get('parent-a',s['id'])['submission']['id'],s['id'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM homework_submissions').fetchone()['n'],1)


if __name__=='__main__':unittest.main()
