from copy import deepcopy
import unittest

from content.chinese_reading_activity import picture, reading_scene, rhythm_scene
from content.textbook_activity_ir import byte_sha
from services.chinese_reading_activity_service import validate_recipe, READING_PHASES_V2


def recipe():
    assets=[{'assetId':k,'svgMarkup':picture(k),'sha256':byte_sha(picture(k).encode())}
            for k in ('boat','rabbit','aloud','share')]
    scenes=[]
    for i,renderer in enumerate(('observation_video','picture_match','rhythm_drum','illustrated_reading')):
        scenes.append({'sceneId':'s'+str(i),'title':'原创阅读活动','renderer':renderer,
            'widgetType':'visualization3d' if i==2 else 'game','activityGoalIds':['goal'+str(i)],
            'initialCueId':'cue'+str(i),'finiteCues':[{'cueId':'cue'+str(i),'teacherText':'听老师说，再看图。'}]})
    scenes[0]['observations']=[{'assetId':a,'cueId':'cue0','seekSeconds':i*4+2} for i,a in enumerate(('boat','rabbit','aloud'))]
    scenes[1]['rounds']=[{'mode':'spoken_language_picture_matching','optionAssetIds':['boat','rabbit','aloud'],
                          'targetAssetId':a} for a in ('boat','rabbit','aloud')]
    scenes[2].update(retryCueId='cue2',yourTurnCueId='cue2',completeCueId='cue2',patterns=[
        {'assetId':a,'beats':i+2,'cueId':'cue2','feedbackCueId':'cue2'} for i,a in enumerate(('boat','rabbit','aloud'))])
    scenes[3].update(completeCueId='cue3',pages=[{'assetId':a,'cueId':'cue3','displayText':'看图听读。'} for a in ('boat','rabbit','aloud')])
    return ({'kind':'lesson_courseware','scope':{'subject':'chinese','gradeCode':'primary_1'}},
            {'lessonFamily':'chinese_reading_rhythm_v1','sceneCount':4,'assetPlan':assets,'scenes':scenes,
             'finiteCues':[c for s in scenes for c in s['finiteCues']]},
            {'activityGoalIds':['goal'+str(i) for i in range(4)]})


def detailed_recipe():
    task, design, scope = recipe()
    originals = {s['renderer']:s for s in design['scenes']}
    scenes = []
    for i, role in enumerate(READING_PHASES_V2):
        scene = deepcopy(originals.get(role, originals['illustrated_reading']))
        renames = {cue['cueId']:f'd{i}_{cue["cueId"]}' for cue in scene['finiteCues']}

        def rename(value):
            if isinstance(value, dict):
                return {key:rename(item) for key,item in value.items()}
            if isinstance(value, list):
                return [rename(item) for item in value]
            return renames.get(value,value) if isinstance(value,str) else value

        scene = rename(scene)
        scene.update(sceneId=f'd{i}', renderer=role)
        if role == 'picture_match':
            for row in scene['rounds']:
                row['retryCueId'] = scene['initialCueId']
        if role == 'picture_recitation':
            lines = ['风吹过，','小草摇，','我们笑。']
            scope['publicDomainText'] = {'text':'\n'.join(lines)}
            scene['adapterId'] = 'public_domain_picture_recall_v1'
            scene['pages'] = []
            for n,(text,asset) in enumerate(zip(lines,['boat','rabbit','aloud'])):
                prompt, model = f'd{i}_prompt{n}',f'd{i}_model{n}'
                scene['finiteCues'] += [{'cueId':prompt,'teacherText':'看图，试着说一句。'},
                                       {'cueId':model,'teacherText':text}]
                scene['pages'].append({'assetId':asset,'promptCueId':prompt,'modelCueId':model,'modelText':text})
        scenes.append(scene)
    design.update(lessonFamily='chinese_reading_rhythm_v2',sceneCount=len(scenes),scenes=scenes,
                  finiteCues=[cue for scene in scenes for cue in scene['finiteCues']])
    return task,design,scope


class ReadingRecipeTests(unittest.TestCase):
    def test_detailed_reading_keeps_model_practice_recall_sequence(self):
        task,design,scope=detailed_recipe()
        validate_recipe(task,design,scope)
        # Removing the explanation/recall stages cannot silently become a
        # complete detailed recipe, and the legacy four-scene contract stays strict.
        old_family=deepcopy(design);old_family['lessonFamily']='chinese_reading_rhythm_v1'
        with self.assertRaisesRegex(ValueError,'reading_scene_roles_changed'):
            validate_recipe(task,old_family,scope)
        missing=deepcopy(design);missing['scenes'].pop(2)
        with self.assertRaisesRegex(ValueError,'reading_scene_roles_changed'):
            validate_recipe(task,missing,scope)

    def test_detailed_recall_must_match_approved_text_and_exact_model_audio(self):
        task,design,scope=detailed_recipe()
        for field in ['modelText','modelCueId']:
            other=deepcopy(design)
            other['scenes'][3]['pages'][0][field] = ('改写的一句。' if field=='modelText'
                                                   else other['scenes'][3]['initialCueId'])
            with self.assertRaisesRegex(ValueError,'reading_public_domain_recall_contract_invalid'):
                validate_recipe(task,other,scope)
        scope['publicDomainText']['text']='另一首童谣。'
        with self.assertRaisesRegex(ValueError,'reading_public_domain_recall_contract_invalid'):
            validate_recipe(task,design,scope)

    def test_detailed_rounds_require_specific_feedback_and_keep_gaps(self):
        task,design,scope=detailed_recipe()
        design['scenes'][9]['rounds'][0].pop('retryCueId')
        with self.assertRaisesRegex(ValueError,'reading_specific_retry_required'):
            validate_recipe(task,design,scope)
        task,design,scope=detailed_recipe();scope['outstandingGoalIds']=['goal2']
        with self.assertRaisesRegex(ValueError,'reading_unfinished_goal_claimed'):
            validate_recipe(task,design,scope)

    def test_recall_lead_in_cannot_change_or_hide_source_words(self):
        task,design,scope=detailed_recipe()
        page=design['scenes'][3]['pages'][0]
        page['modelLeadIn']='跟老师读。'
        model=next(c for c in design['scenes'][3]['finiteCues'] if c['cueId']==page['modelCueId'])
        model['teacherText']=page['modelLeadIn']+page['modelText']
        validate_recipe(task,design,scope)
        for bad in ['别的话。'+page['modelText'], page['modelText'], '跟老师读。改掉正文。']:
            model['teacherText']=bad
            with self.assertRaisesRegex(ValueError,'reading_public_domain_recall_contract_invalid'):
                validate_recipe(task,design,scope)

    def test_grade_and_goal_coverage_cannot_be_silently_changed(self):
        task,design,scope=recipe()
        validate_recipe(task,design,scope)
        for subject,grade in [('math','primary_1'),('chinese','primary_6')]:
            other=deepcopy(task);other['scope'].update(subject=subject,gradeCode=grade)
            with self.assertRaisesRegex(ValueError,'reading_family_invalid'):
                validate_recipe(other,design,scope)
        design['scenes'][3]['activityGoalIds']=[]
        with self.assertRaisesRegex(ValueError,'reading_goal_coverage_changed'):
            validate_recipe(task,design,scope)

    def test_repeated_answer_pictures_and_foreign_audio_are_rejected(self):
        task,design,scope=recipe()
        design['scenes'][1]['rounds'][0]['optionAssetIds']=['boat','boat','aloud']
        with self.assertRaisesRegex(ValueError,'distinct_answer_pictures'):
            validate_recipe(task,design,scope)
        task,design,scope=recipe();design['scenes'][2]['patterns'][0]['cueId']='cue1'
        with self.assertRaisesRegex(ValueError,'foreign_scene_cue'):
            validate_recipe(task,design,scope)

    def test_rhythm_bounds_and_reading_picture_coverage_are_enforced(self):
        task,design,scope=recipe();design['scenes'][2]['patterns'][0]['beats']=50
        with self.assertRaisesRegex(ValueError,'bounded_rhythm'):
            validate_recipe(task,design,scope)
        task,design,scope=recipe();design['scenes'][3]['pages'][1]['assetId']='boat'
        with self.assertRaisesRegex(ValueError,'reading_pages_invalid'):
            validate_recipe(task,design,scope)

    def test_generated_scenes_use_real_drum_and_recorded_narration(self):
        task,design,scope=recipe();assets=validate_recipe(task,design,scope)
        rhythm=rhythm_scene(design['scenes'][2],assets)
        self.assertIn("canvas.getContext('webgl'",rhythm)
        self.assertIn("part('drum','cylinder'",rhythm)
        self.assertIn('pulseUntil',rhythm)
        self.assertIn('signal.aborted',rhythm)
        self.assertNotIn('speechSynthesis',rhythm)
        self.assertIn('window.miraNarrate("cue2")',rhythm)
        self.assertIn('pageIndex<reading.pages.length-1',reading_scene(design['scenes'][3],assets))


if __name__=='__main__':
    unittest.main()
