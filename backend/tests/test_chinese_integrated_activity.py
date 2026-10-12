from copy import deepcopy
import json
import re
import shutil
import subprocess
import unittest

from content.chinese_integrated_activity import STROKES, illustration, stroke_scene, stroke_picture, target_picture
from content.chinese_word_activity import cards_scene, glyph_scene, picture as word_picture
from content.chinese_community_activity import WELL_CONTROLS, WELL_CUE_KEYS
from content.chinese_reading_activity import original_recall_scene
from content.chinese_letter_activity import glyph_picture, letter_scene, validate_scene
from content.chinese_dictionary_activity import dictionary_scene, lookup_picture, validate_scene as validate_dictionary
from content.textbook_activity_ir import byte_sha
from services.chinese_integrated_activity_service import validate_recipe
from services.textbook_batch_queue_audio_service import _reviewed_word_observation, _reviewed_dictionary_practice


def recipe():
    assets={k:illustration(k) for k in ['learn','count','choir','snow','willow','flowers']}
    for c,k in [('识','learn'),('计','count'),('唱','choir')]:assets['word'+c]=target_picture(k,c)
    assets['tian']=stroke_picture('田')
    roles=['observation_video','word_cards','stroke_order_3d','picture_match','illustrated_reading']
    scenes=[{'sceneId':'s'+str(i),'title':'图画练习','renderer':role,'widgetType':'visualization3d' if i==2 else 'game',
             'activityGoalIds':['g'+str(i)],'initialCueId':'c'+str(i),
             'finiteCues':[{'cueId':'c'+str(i),'teacherText':'先听老师说，再点图片。'}]} for i,role in enumerate(roles)]
    scenes[0]['observations']=[{'assetId':k,'cueId':'c0'} for k in ['snow','willow','flowers']]
    scenes[1].update(cards=[{'character':c,'assetId':'word'+c,'cueId':'c1'} for c in ['识','计','唱']],writingCharacters=['文'],resetCueId='c1',completeCueId='c1',writeCueId='c1')
    scenes[2].update(characters=[{'character':'田','assetId':'tian','strokes':deepcopy(STROKES['田']),'introCueId':'c2','strokeCueIds':['c2']*5}],retryCueId='c2',completeCueId='c2')
    scenes[3]['rounds']=[{'mode':'spoken_language_picture_matching','optionAssetIds':['learn','count','choir'],'targetAssetId':k} for k in ['learn','count','choir']]
    scenes[4]['pages']=[{'assetId':k,'cueId':'c4','displayText':'看图听读。'} for k in ['snow','willow','flowers']]
    return ({'kind':'lesson_courseware','scope':{'subject':'chinese','gradeCode':'primary_1'}},
        {'lessonFamily':'chinese_integrated_review_v1','sceneCount':5,'scenes':scenes,
         'finiteCues':[c for s in scenes for c in s['finiteCues']],
         'assetPlan':[{'assetId':k,'svgMarkup':v,'sha256':byte_sha(v.encode())} for k,v in assets.items()]},
        {'activityGoalIds':['g'+str(i) for i in range(5)],'outstandingGoalIds':['alphabet_names'],
         'recognizedCharacters':['识','计','唱'],'writingCharacters':['文'],'observedCharacters':['田']})


def dictionary_recipe():
    identity={'character':'母','uppercase':'M','syllable':'mu','tone':3,'demonstrationPage':12}
    assets={'source':target_picture('learn','母')};steps=[]
    for index,(kind,values) in enumerate([('letter',['M','N','Q']),('syllable',['mu','nu','qu']),('entry',['母','目','木'])]):
        options=[]
        for j,value in enumerate(values):
            key=f'option{index}{j}';page=None if index==0 else 12
            phonetic=['mǔ','mù','mù'][j] if index==2 else None
            assets[key]=lookup_picture(kind,value,page,phonetic)
            options.append({'assetId':key,'value':value,**({'page':page} if page is not None else {}),
                            **({'phonetic':phonetic} if phonetic is not None else {})})
        steps.append({'kind':kind,'options':options,'targetAssetId':options[0]['assetId'],
                      'instructionCueId':'ask','matchCueId':'match'})
    scene={'sceneId':'dictionary','title':'查字典','adapterId':'narrated_dictionary_steps_v1',
           'activityGoalIds':['dictionary_lookup'],'initialCueId':'intro','retryCueId':'retry','completeCueId':'complete',
           'entries':[{**identity,'sourceAssetId':'source','steps':steps}],
           'finiteCues':[{'cueId':c,'teacherText':'听老师说，再查字。'} for c in ['intro','ask','match','retry','complete']]}
    return scene,assets,{'dictionaryPracticeEntries':[identity]}


def original_recall_recipe():
    task,design,scope=recipe()
    models=['孩子看图学知识。','小朋友数清物品。','几个伙伴一起唱歌。']
    scope['activityGoalIds'].append('review_and_retrieval')
    scope['originalRecallModels']=models
    scene={'sceneId':'recall','title':'看图，自己说一说','renderer':'original_picture_recall',
           'widgetType':'game','adapterId':'original_picture_recall_v1',
           'activityGoalIds':['review_and_retrieval'],'initialCueId':'intro','completeCueId':'done',
           'finiteCues':[{'cueId':'intro','teacherText':'先听问题，自己想，再决定是否听示范。'},
                         {'cueId':'done','teacherText':'把你想说的话讲给家人听。'}],'pages':[]}
    for i,(asset,model) in enumerate(zip(['learn','count','choir'],models)):
        scene['pages'].append({'assetId':asset,'promptCueId':f'p{i}','modelCueId':f'm{i}','modelText':model})
        scene['finiteCues'] += [{'cueId':f'p{i}','teacherText':'看看人物和物品，说一说画面上的事。'},
                               {'cueId':f'm{i}','teacherText':model}]
    design['scenes'].append(scene);design['sceneCount']+=1;design['finiteCues']+=scene['finiteCues']
    return task,design,scope


class IntegratedActivityTests(unittest.TestCase):
    def test_original_recall_binds_reviewed_models_and_keeps_prompt_separate(self):
        task,design,scope=original_recall_recipe();validate_recipe(task,design,scope)
        for mutation in ['unreviewed_model','shared_cue','answer_in_prompt','score','public_domain']:
            other=deepcopy(design);scene=other['scenes'][-1];page=scene['pages'][0]
            if mutation=='unreviewed_model':page['modelText']='换成未审核的示范。'
            elif mutation=='shared_cue':page['promptCueId']=page['modelCueId']
            elif mutation=='answer_in_prompt':
                next(c for c in scene['finiteCues'] if c['cueId']==page['promptCueId'])['teacherText']=page['modelText']
            elif mutation=='score':scene['score']=100
            else:scene['renderer']='picture_recitation'
            with self.subTest(mutation=mutation),self.assertRaisesRegex(ValueError,'recall_contract_invalid'):
                validate_recipe(task,other,scope)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for rendered recall checks')
    def test_original_recall_waits_for_child_before_revealing_or_speaking_model(self):
        task,design,scope=original_recall_recipe();assets=validate_recipe(task,design,scope)
        html=original_recall_scene(design['scenes'][-1],assets)
        self.assertEqual(html.count('<p data-model-text hidden>'),3)
        self.assertIn('听问题，自己试',html);self.assertNotIn('试着背',html)
        code=re.search(r'\nconst recall=.*?\nshowRecall\(\);',html,re.S).group(0)
        program=r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const callbacks={},cues=[],pages=Array.from({length:3},(_,i)=>({hidden:i!==0}));
const models=Array.from({length:3},()=>({hidden:true})),controls={model:{},next:{}};
let pending,release;const intro=new Promise(resolve=>release=resolve);
const env={interactionBusy:false,assisted:false,note:{textContent:''},
 document:{getElementById:id=>controls[id],querySelectorAll:selector=>selector==='[data-recall-page]'?pages:models},
 listen:(id,fn)=>callbacks[id]=fn,cancelOperation:()=>{},
 narrate:async id=>{cues.push(id);if(id==='intro')await intro;},
 run:fn=>{env.interactionBusy=true;env.refreshControls();pending=Promise.resolve().then(()=>fn({})).finally(()=>{env.interactionBusy=false;env.refreshControls();});}};
vm.createContext(env);vm.runInContext(JSON.parse(process.argv[1]),env);
(async()=>{
 assert.equal(controls.model.disabled,true);callbacks.model();assert.deepEqual(cues,[]);
 callbacks.start();await Promise.resolve();callbacks.model();assert.deepEqual(cues,['intro']);
 assert.ok(models.every(x=>x.hidden));release();await pending;
 assert.deepEqual(cues,['intro','p0']);assert.equal(controls.model.disabled,false);
 assert.ok(models.every(x=>x.hidden));callbacks.model();await pending;
 assert.equal(models[0].hidden,false);assert.equal(cues.at(-1),'m0');
 callbacks.next();await pending;assert.equal(pages[1].hidden,false);assert.ok(models.every(x=>x.hidden));
 assert.equal(cues.at(-1),'p1');callbacks.next();await pending;
 assert.equal(cues.includes('m1'),false);assert.equal(pages[2].hidden,false);
 callbacks.next();await pending;assert.equal(controls.next.disabled,true);
 assert.equal(cues.includes('m2'),false);assert.match(env.note.textContent,/家人/);
 callbacks.reset();await pending;assert.equal(pages[0].hidden,false);assert.ok(models.every(x=>x.hidden));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result=subprocess.run([shutil.which('node'),'-e',program,json.dumps(code)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_garden_writing_targets_preserve_source_strokes_and_turns(self):
        self.assertEqual([len(STROKES[c]) for c in '文卡片合'], [4,5,4,6])
        # 卡的短横先接上竖，长横再穿过；不能把上、下分别写完。
        upper,short,long,lower,dot=STROKES['卡']
        self.assertEqual(short[0][0],upper[0][0])
        self.assertEqual(upper[-1],lower[0])
        self.assertLess(long[0][0],short[0][0])
        self.assertGreater(long[-1][0],short[-1][0])
        # 片末笔是一笔连续横折，没有额外钩；合的口最后封底。
        turn=STROKES['片'][-1]
        self.assertEqual(len(turn),3)
        self.assertEqual(turn[0][1],turn[1][1])
        self.assertEqual(turn[1][0],turn[2][0])
        left,top_right,bottom=STROKES['合'][-3:]
        self.assertEqual(bottom[0],left[-1])
        self.assertEqual(bottom[-1],top_right[-1])

    def riddle_recipe(self):
        task,design,scope=self.qing_recipe()
        scope['componentObservedCharacters']=list('秋明清晴请情')
        scope['activityGoalIds'][-1]='riddle_components'
        scene=design['scenes'][-1]
        scene.update(renderer='riddle_components_3d',activityGoalIds=['riddle_components'],states=[])
        for i,(char,cut,key) in enumerate(zip('秋明清晴请情',[.47,.47,.32,.43,.33,.31],['autumn','bright','clear','sunny','please','feeling'])):
            svg=word_picture(key);asset='riddle_picture'+str(i)
            design['assetPlan'].append({'assetId':asset,'sha256':byte_sha(svg.encode()),'svgMarkup':svg})
            scene['states'].append({'sceneStateId':'s'+str(i),'character':char,'splitFraction':cut,
                                    'assetId':asset,'observationCueId':'qing_cue'})
        return task,design,scope

    def test_riddle_component_contract_preserves_exact_six_reviewed_glyphs(self):
        task,design,scope=self.riddle_recipe();assets=validate_recipe(task,design,scope)
        html=glyph_scene(design['scenes'][-1],assets)
        self.assertIn("canvas.getContext('webgl'",html)
        for i in range(6):self.assertIn('id="state-s'+str(i)+'"',html)
        for field,value in [('character','日'),('splitFraction',.31),('sceneStateId','s9')]:
            wrong=deepcopy(design);wrong['scenes'][-1]['states'][1][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'riddle_component_contract'):
                validate_recipe(task,wrong,scope)
        wrong=deepcopy(design);wrong['scenes'][-1]['geometry']={}
        with self.assertRaisesRegex(ValueError,'riddle_component_contract'):validate_recipe(task,wrong,scope)
        wrong=deepcopy(design);wrong['scenes'][-1]['states'][1]['observationCueId']='c1'
        with self.assertRaisesRegex(ValueError,'foreign_cue'):validate_recipe(task,wrong,scope)

    def test_riddle_strokes_preserve_order_and_connected_turns(self):
        self.assertEqual({c:len(STROKES[c]) for c in '字红动万无明'},dict(zip('字红动万无明',[6,6,6,3,4,8])))
        # 万 second stroke is a connected horizontal-turn-hook, before the left-falling stroke.
        bend,fall=STROKES['万'][1:]
        self.assertEqual(bend[0][1],bend[1][1]);self.assertGreater(bend[2][1],bend[1][1])
        self.assertLess(bend[-1][0],bend[-2][0]);self.assertLess(fall[-1][0],fall[0][0])
        # 红 finishes the silk radical with a rising stroke; 无 finishes a connected bent hook.
        rise=STROKES['红'][2];self.assertGreater(rise[-1][0],rise[0][0]);self.assertLess(rise[-1][1],rise[0][1])
        self.assertGreaterEqual(len(STROKES['无'][-1]),5)
        # 明 writes the whole 日 before 月; its last two strokes are the two inner horizontals.
        for stroke in STROKES['明'][-2:]:self.assertEqual(stroke[0][1],stroke[-1][1])

    def qing_recipe(self):
        task,design,scope=recipe()
        scope['componentObservedCharacters']=list('清晴睛情请')
        scope['activityGoalIds'].append('qing_components')
        scene={'sceneId':'qing','title':'青字族部件观察','renderer':'qing_components_3d',
               'widgetType':'visualization3d','modelAdapterKey':'reviewed_chinese_glyph_relief',
               'activityGoalIds':['qing_components'],
               'finiteCues':[{'cueId':'qing_cue','teacherText':'看图听词语，再分合字形。'}],
               **{k:'qing_cue' for k in ['initialCueId','retryCueId','resetCueId','completeCueId','separateCueId','joinCueId']},
               'states':[]}
        for i,(char,cut,key) in enumerate(zip('清晴睛情请',[.32,.43,.43,.31,.33],['clear','sunny','eyes','feeling','please'])):
            svg=word_picture(key);asset='qing_picture'+str(i)
            design['assetPlan'].append({'assetId':asset,'origin':'original_local_svg','sha256':byte_sha(svg.encode()),'svgMarkup':svg})
            scene['states'].append({'sceneStateId':'s'+str(i),'character':char,'splitFraction':cut,
                                    'assetId':asset,'observationCueId':'qing_cue'})
        design['scenes'].append(scene);design['sceneCount']=6;design['finiteCues']+=scene['finiteCues']
        return task,design,scope

    def test_qing_component_role_requires_exact_source_targets_and_splits(self):
        task,design,scope=self.qing_recipe();validate_recipe(task,design,scope)
        for field,value in [('character','晴'),('splitFraction',.60),('sceneStateId','unreviewed')]:
            changed=deepcopy(design);changed['scenes'][-1]['states'][2][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'qing_component_contract'):
                validate_recipe(task,changed,scope)
        changed=deepcopy(scope);changed['componentObservedCharacters']=list('清晴睛情猜')
        with self.assertRaisesRegex(ValueError,'qing_component_contract'):validate_recipe(task,design,changed)

    def test_qing_component_role_rejects_arbitrary_geometry_and_repeated_picture(self):
        task,design,scope=self.qing_recipe()
        changed=deepcopy(design);changed['scenes'][-1]['geometry']={}
        with self.assertRaisesRegex(ValueError,'qing_component_contract'):validate_recipe(task,changed,scope)
        changed=deepcopy(design);changed['scenes'][-1]['states'][1]['assetId']='qing_picture0'
        with self.assertRaisesRegex(ValueError,'qing_component_contract'):validate_recipe(task,changed,scope)
        changed=deepcopy(design);changed['scenes'][-1]['states'][1]['observationCueId']='c1'
        with self.assertRaisesRegex(ValueError,'foreign_cue'):validate_recipe(task,changed,scope)

    def test_qing_component_role_uses_existing_real_glyph_renderer(self):
        task,design,scope=self.qing_recipe();assets=validate_recipe(task,design,scope)
        html=glyph_scene(design['scenes'][-1],assets)
        self.assertIn("canvas.getContext('webgl'",html)
        self.assertIn('const glyphs=',html)
        for index in range(5):self.assertIn('id="state-s'+str(index)+'"',html)
        self.assertIn('function splitParts(value)',html)
        self.assertNotIn('speechSynthesis',html)

    def test_frog_strokes_keep_connected_bend_rising_strokes_and_field_closure(self):
        self.assertEqual({c:len(STROKES[c]) for c in '青清晴苗请生'},dict(zip('青清晴苗请生',[8,11,12,8,10,5])))
        # 请: 横折提 is one connected stroke, ending upward to the right.
        bend=STROKES['请'][1]
        self.assertEqual(len(bend),4)
        self.assertEqual(bend[0][1],bend[1][1]);self.assertEqual(bend[1][0],bend[2][0])
        self.assertGreater(bend[-1][0],bend[-2][0]);self.assertLess(bend[-1][1],bend[-2][1])
        rising=STROKES['清'][2]
        self.assertGreater(rising[-1][0],rising[0][0]);self.assertLess(rising[-1][1],rising[0][1])
        # 苗: the inner horizontal and vertical precede the bottom closure.
        horizontal,vertical,bottom=STROKES['苗'][5:]
        self.assertEqual(horizontal[0][1],horizontal[-1][1])
        self.assertEqual(vertical[0][0],vertical[-1][0])
        self.assertEqual(bottom[0][1],bottom[-1][1]);self.assertGreater(bottom[0][1],horizontal[0][1])

    def test_surname_source_contract_rejects_wrong_parts_and_unreviewed_geometry(self):
        from content import chinese_surname_activity as surname
        scene={'modelAdapterKey':'real_font_voxel_relief_character_components',
               'activityGoalIds':['surname_character_components'],
               'finiteCues':[{'cueId':'c','teacherText':'观察字形。'}],
               **{k:'c' for k in surname.CUE_KEYS},
               'states':[{'sceneStateId':a['key'],'assetId':'actor_'+a['key'],
                          'char':a['char'],'layout':a['layout'],'parts':a['parts'],
                          'observationCueId':'c'} for a in surname.ACTORS]}
        scope={'recognizedCharacters':list('氏什李张弓古胡吴言孙'),
               'introducedPortraitAssetIds':surname.PORTRAIT_IDS}
        surname.validate_scene(scene,scope)
        scene['states'][2]['parts']=['古','日']
        with self.assertRaisesRegex(ValueError,'surname_component'):surname.validate_scene(scene,scope)
        scene['states'][2]['parts']=['古','月'];scene['geometry']={}
        with self.assertRaisesRegex(ValueError,'surname_component'):surname.validate_scene(scene,scope)

    def test_surname_four_choice_exception_requires_introduced_source_portraits(self):
        from content.chinese_surname_activity import PORTRAIT_IDS
        task,design,scope=recipe()
        pictures=[illustration(k) for k in ['learn','count','choir','snow']]
        design['assetPlan'] += [{'assetId':k,'svgMarkup':s,'sha256':byte_sha(s.encode())}
                               for k,s in zip(PORTRAIT_IDS,pictures)]
        scene=design['scenes'][3];scene['activityGoalIds']=['supported_surname_listening']
        scope['activityGoalIds'][3]='supported_surname_listening'
        for row in scene['rounds']:
            row.update(optionAssetIds=list(PORTRAIT_IDS),targetAssetId='actor_hu')
        with self.assertRaisesRegex(ValueError,'distinct_answers'):validate_recipe(task,design,scope)
        scope['introducedPortraitAssetIds']=list(PORTRAIT_IDS)
        validate_recipe(task,design,scope)
        scene['rounds'][0]['optionAssetIds'][2]='flowers'
        with self.assertRaisesRegex(ValueError,'distinct_answers'):validate_recipe(task,design,scope)

    def test_surname_component_model_split_join_visit_and_reset(self):
        from content import chinese_surname_activity as surname
        from tests.test_textbook_activity_compiler import DeterministicActivityCompiler
        scene={'sceneId':'surname','title':'看字形','finiteCues':[
            {'cueId':k,'teacherText':'看字形的部件。'} for k in ['intro','retry','reset','done','apart','join','li','zhang','hu','wu']],
            **dict(zip(surname.CUE_KEYS,['intro','retry','reset','done','apart','join'])),
            'states':[{'sceneStateId':a['key'],'assetId':'learn','observationCueId':a['key']}
                      for a in surname.ACTORS]}
        DeterministicActivityCompiler.execute(self,surname.glyph_model(scene,{'learn':illustration('learn')}),r'''
assert.equal(document.getElementById('finish').disabled,true);
for(const key of ['li','zhang','hu','wu']){
 click('state-'+key);await tick();frame();frame();await tick();await ended();
 assert.equal(run('active'),key);
 assert.equal(run('meshes.filter(m=>m.glyphPart!==undefined).length'),2);
 assert.equal(run('meshes.every(m=>geometries[m.shape].every(Number.isFinite))'),true);
 click('separate');await tick();frame();frame();await tick();await ended();
 assert.equal(run('separated'),true);
 const positions=run('meshes.filter(m=>m.glyphPart!==undefined).map(m=>Array.from(m.local))');
 click('join');await tick();frame();frame();await tick();await ended();
 assert.equal(run('separated'),false);
 assert.notDeepEqual(run('meshes.filter(m=>m.glyphPart!==undefined).map(m=>Array.from(m.local))'),positions);
}
assert.equal(document.getElementById('finish').disabled,false);
click('reset');await tick();frame();frame();await tick();await ended();
assert.equal(run('active'),'li');assert.equal(run('visited.size'),0);
assert.equal(document.getElementById('finish').disabled,true);
''',model=True)

    def test_surname_writing_preserves_hook_and_dot_distinctions(self):
        self.assertEqual([len(STROKES[c]) for c in '什么古胡双言'],[4,3,5,9,4,7])
        self.assertGreater(STROKES['胡'][6][-1][1],STROKES['胡'][6][-2][1]-8)
        self.assertLess(STROKES['胡'][6][-1][1],STROKES['胡'][6][-2][1])
        self.assertEqual(len(STROKES['双'][1]),2)
        self.assertGreater(len(STROKES['双'][3]),2)
        self.assertGreater(STROKES['言'][0][-1][1],STROKES['言'][0][0][1])

    def test_natural_motion_three_real_models_audio_gates_and_reset(self):
        from content.chinese_nature_activity import model
        from tests.test_textbook_activity_compiler import DeterministicActivityCompiler
        scene={'sceneId':'nature','title':'观察自然','modelAdapterKey':'seasons_natural_motion',
               'initialCueId':'intro','retryCueId':'retry','resetCueId':'reset','completeCueId':'done',
               'finiteCues':[{'cueId':k,'teacherText':'先看图，再听老师说。'} for k in ['intro','retry','reset','done','wind','snow','swim']],
               'states':[{'sceneStateId':k,'assetId':'learn','observationCueId':k} for k in ['wind','snow','swim']]}
        DeterministicActivityCompiler.execute(self,model(scene,{'learn':illustration('learn')}),r'''
assert.equal(document.getElementById('finish').disabled,true);
for(const key of ['wind','snow','swim']){
 click('state-'+key);await tick();frame();frame();await tick();
 assert.equal(run('active'),key);assert.equal(document.getElementById('finish').disabled,true);
 await ended();
 assert.equal(run('meshes.every(m=>geometries[m.shape].every(Number.isFinite))'),true);
 if(key==='wind')assert.equal(run("meshes.filter(m=>m.shape.startsWith('blade')).length"),3);
 if(key==='snow')assert.equal(run("meshes.filter(m=>m.shape==='snowflake').length"),5);
 if(key==='swim')assert.equal(run("meshes.some(m=>m.group==='pond')&&meshes.some(m=>m.shape==='tail')"),true);
}
assert.equal(document.getElementById('finish').disabled,false);
const before=run('manualAngle');click('rotate');assert.notEqual(run('manualAngle'),before);
click('reset');await tick();frame();frame();await tick();await ended();
assert.equal(run('motionRunning'),false);assert.equal(run('visited.size'),0);
assert.equal(document.getElementById('finish').disabled,true);
''',model=True)

    def test_natural_motion_contract_rejects_extra_state_and_geometry(self):
        task,design,scope=recipe()
        scene={'sceneId':'nature','renderer':'natural_motion_3d','widgetType':'visualization3d',
               'modelAdapterKey':'seasons_natural_motion','activityGoalIds':['natural_motion_observation'],
               'initialCueId':'nc','retryCueId':'nc','resetCueId':'nc','completeCueId':'nc',
               'finiteCues':[{'cueId':'nc','teacherText':'看图，再观察模型。'}],
               'states':[{'sceneStateId':key,'assetId':'learn','observationCueId':'nc'} for key in ['wind','snow','swim']]}
        design['scenes'].append(scene);design['sceneCount']=6;design['finiteCues']+=scene['finiteCues']
        scope['activityGoalIds'].append('natural_motion_observation')
        validate_recipe(task,design,scope)
        scene['states'][0]['sceneStateId']='unreviewed'
        with self.assertRaisesRegex(ValueError,'nature_contract'):validate_recipe(task,design,scope)
        scene['states'][0]['sceneStateId']='wind';scene['geometry']={}
        with self.assertRaisesRegex(ValueError,'nature_contract'):validate_recipe(task,design,scope)

    def test_season_writing_connections_and_stroke_totals(self):
        self.assertEqual([len(STROKES[c]) for c in '春冬吹花飞入'],[9,5,7,7,3,2])
        self.assertGreater(len(STROKES['飞'][0]),4)
        self.assertLess(STROKES['入'][1][0][1],STROKES['入'][0][0][1])
        self.assertGreater(STROKES['春'][2][-1][0]-STROKES['春'][2][0][0],
                           STROKES['春'][0][-1][0]-STROKES['春'][0][0][0])
        self.assertEqual(STROKES['冬'][3][0][1]<STROKES['冬'][4][0][1],True)

    def test_dictionary_rejects_changed_initial_demo_page_and_visible_character(self):
        scene,assets,scope=dictionary_recipe();validate_dictionary(scene,assets,scope)
        scene['entries'][0]['uppercase']='N'
        with self.assertRaisesRegex(ValueError,'scope_changed'):validate_dictionary(scene,assets,scope)
        scene['entries'][0]['uppercase']='M';option=scene['entries'][0]['steps'][1]['options'][0]
        option['page']=99;assets[option['assetId']]=lookup_picture('syllable','mu',99)
        with self.assertRaisesRegex(ValueError,'index_target_changed'):validate_dictionary(scene,assets,scope)
        option['page']=12;assets[option['assetId']]=lookup_picture('syllable','mu',12)
        assets['option20']=lookup_picture('entry','目',12)
        with self.assertRaisesRegex(ValueError,'choice_picture_changed'):validate_dictionary(scene,assets,scope)

    def test_dictionary_wrong_answer_feedback_gate_and_reset(self):
        from tests.test_textbook_activity_compiler import DeterministicActivityCompiler
        scene,assets,_=dictionary_recipe()
        DeterministicActivityCompiler.execute(self,dictionary_scene(scene,assets),r'''
assert.equal(document.getElementById('lookup-0-0-0').disabled,true);
assert.equal(document.querySelectorAll('.selected').length,0);
click('start');await tick();await ended();await ended();
click('lookup-0-0-1');await tick();await ended();
assert.equal(run('stepIndex'),0);assert.equal(document.getElementById('next').disabled,true);
click('lookup-0-0-0');await tick();assert.equal(document.getElementById('next').disabled,true);
assert.equal(document.querySelectorAll('.feedback-mark').length,1);
await ended();assert.equal(document.getElementById('next').disabled,false);
click('next');await tick();await ended();
assert.equal(run('stepIndex'),1);assert.equal(document.querySelector('[data-step="0"]').hidden,true);
click('lookup-0-1-0');await tick();await ended();click('next');await tick();await ended();
assert.equal(run('stepIndex'),2);click('lookup-0-2-0');await tick();await ended();
click('next');await tick();assert.equal(run('finished'),false);await ended();
assert.equal(run('finished'),true);assert.equal(document.querySelector('[data-progress]').getAttribute('aria-label'),'这个字已找到');
click('reset');await tick();await ended();await ended();
assert.equal(run('stepIndex'),0);assert.equal(run('completed.size'),0);
assert.equal(document.querySelectorAll('.selected').length,0);
assert.equal(document.getElementById('next').disabled,true);
''')

    def test_dictionary_target_glyph_exception_requires_exact_bounded_scene(self):
        scene,assets,scope=dictionary_recipe();scene['renderer']='dictionary_lookup'
        design={'lessonFamily':'chinese_integrated_review_v1','scenes':[scene],
                'assetPlan':[{'assetId':k,'svgMarkup':v} for k,v in assets.items()]}
        frozen={'activityDesign':design,'reviewedLessonScope':scope,'binding':{'subject':'chinese'}}
        actual={'id':scene['sceneId']};source=dictionary_scene(scene,assets)
        self.assertTrue(_reviewed_dictionary_practice(frozen,actual,source))
        self.assertFalse(_reviewed_dictionary_practice(frozen,actual,source+'<button>未审核答案</button>'))
        scene['entries'][0]['steps'][2]['options'][0]['phonetic']='mù'
        self.assertFalse(_reviewed_dictionary_practice(frozen,actual,source))

    def test_drum_rejects_unbounded_patterns_and_foreign_feedback(self):
        task,design,scope=recipe()
        scene={'sceneId':'drum','renderer':'rhythm_drum_3d','widgetType':'visualization3d',
               'adapterId':'turn_taking_drum_v1','activityGoalIds':['g4'],
               'initialCueId':'drumcue','retryCueId':'drumcue','yourTurnCueId':'drumcue','completeCueId':'drumcue',
               'finiteCues':[{'cueId':'drumcue','teacherText':'先听，再轮到你。'}],
               'patterns':[{'assetId':asset,'beats':beats,'cueId':'drumcue','feedbackCueId':'drumcue'}
                           for asset,beats in [('learn',2),('count',3),('choir',4)]]}
        design['scenes'].append(scene);design['sceneCount']=6;design['finiteCues']+=scene['finiteCues']
        validate_recipe(task,design,scope)
        scene['patterns'][2]['beats']=40
        with self.assertRaisesRegex(ValueError,'drum_contract'):validate_recipe(task,design,scope)
        scene['patterns'][2]['beats']=4;scene['patterns'][0]['feedbackCueId']='c1'
        with self.assertRaisesRegex(ValueError,'foreign_cue'):validate_recipe(task,design,scope)
        scene['patterns'][0]['feedbackCueId']='drumcue';scene['geometry']={}
        with self.assertRaisesRegex(ValueError,'drum_contract'):validate_recipe(task,design,scope)

    def test_letter_pairs_reject_wrong_case_and_mismatched_visible_glyph(self):
        assets = {c: glyph_picture(c) for c in 'NnRrDd'}
        rows = [{'uppercase': c, 'lowercase': c.lower(), 'uppercaseAssetId': c,
                 'targetAssetId': c.lower(), 'optionAssetIds': ['n', 'r', 'd'],
                 'mode': 'letter_case_shape_matching'} for c in 'NRD']
        scope = {'letterCasePairs': {c: c.lower() for c in 'NRD'}}
        scene = {'activityGoalIds': ['letter_case_matching'], 'rounds': rows}
        validate_scene(scene, assets, scope)
        rows[0]['lowercase'] = 'r'
        with self.assertRaisesRegex(ValueError, 'letter_case_scope'):
            validate_scene(scene, assets, scope)
        rows[0]['lowercase'] = 'n'; assets['n'] = glyph_picture('r')
        with self.assertRaisesRegex(ValueError, 'letter_case_glyph'):
            validate_scene(scene, assets, scope)

    def test_letter_hint_is_requested_and_pair_waits_for_matching_feedback_audio(self):
        from tests.test_textbook_activity_compiler import DeterministicActivityCompiler
        assets = {c: glyph_picture(c) for c in 'NnRrDd'}
        scene = {'sceneId': 'letters', 'title': '找字形伙伴', 'initialCueId': 'intro',
                 'retryCueId': 'retry', 'hintCueId': 'hint', 'resetCueId': 'reset',
                 'completeCueId': 'complete', 'finiteCues': [
                     {'cueId': c, 'teacherText': '看图配对。'}
                     for c in ['intro', 'retry', 'hint', 'reset', 'complete', 'ask', 'match']],
                 'rounds': [{'roundId': c, 'uppercaseAssetId': c,
                            'targetAssetId': c.lower(), 'optionAssetIds': ['n', 'r', 'd'],
                            'instructionCueId': 'ask', 'matchCueId': 'match'} for c in 'NRD']}
        DeterministicActivityCompiler.execute(self, letter_scene(scene, assets), r'''
assert.equal(document.getElementById('detail').hidden,true);
assert.equal(document.querySelectorAll('[data-option].selected').length,0);
click('start');await tick();await ended();await ended();
assert.equal(document.querySelector('#source svg').getAttribute('aria-label'),'大写字形 N');
click('source');click('option-r');await tick();await ended();
assert.equal(run('matched'),false);assert.equal(document.getElementById('next').disabled,true);
click('hint');await tick();
assert.deepEqual(Array.from(document.querySelectorAll('#detail svg')).map(e=>e.getAttribute('aria-label')),['大写字形 N','小写字形 n']);
assert.equal(run('assisted'),true);await ended();
click('option-n');await tick();assert.equal(document.getElementById('next').disabled,true);
await ended();assert.equal(document.getElementById('next').disabled,false);
click('next');await tick();await ended();
assert.equal(document.querySelector('#source svg').getAttribute('aria-label'),'大写字形 R');
assert.equal(document.getElementById('detail').hidden,true);
assert.equal(document.querySelectorAll('[data-option].selected').length,0);
''')

    def test_fang_hook_precedes_final_left_falling_stroke(self):
        self.assertEqual(len(STROKES['方']),4)
        hook,fall=STROKES['方'][2:]
        self.assertEqual(hook[0][1],hook[1][1])
        self.assertGreater(hook[1][0],hook[0][0])
        self.assertLess(hook[-1][1],hook[-2][1])
        self.assertLess(fall[-1][0],fall[0][0])
        self.assertGreater(fall[-1][1],fall[0][1])

    def test_well_role_keeps_bounded_adapter_and_same_scene_cues(self):
        task,design,scope=recipe()
        scope['activityGoalIds'].append('picture_word_meaning')
        scene={'sceneId':'well','renderer':'well_lift_3d','widgetType':'visualization3d',
               'adapterId':'well_bucket_lift_v1','activityGoalIds':['picture_word_meaning'],
               'finiteCues':[{'cueId':'wellcue','teacherText':'把水桶放下。'}],
               **{key:'wellcue' for key in WELL_CUE_KEYS}}
        design['scenes'].append(scene);design['sceneCount']=6;design['finiteCues']+=scene['finiteCues']
        validate_recipe(task,design,scope)
        scene['geometry']={}
        with self.assertRaisesRegex(ValueError,'well_contract'):validate_recipe(task,design,scope)
        del scene['geometry'];scene['lowerCueId']='c1'
        with self.assertRaisesRegex(ValueError,'foreign_cue'):validate_recipe(task,design,scope)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for bounded interaction checks')
    def test_well_requires_lowering_before_lifting_and_reset_clears_water(self):
        program=r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const callbacks={},cues=[],elements={};let pending;
const env={state:'high_empty',started:true,interactionBusy:false,gl:{},filled:false,bucketY:1.5,
 poses:{well:{angle:0}},config:{lowerCueId:'lower',raiseCueId:'raise',resetCueId:'reset'},
 canvas:{dataset:{}},document:{getElementById:id=>elements[id]??={},querySelectorAll:()=>[]},
 updateModel:()=>{},initModel:()=>{},cancelOperation:()=>{},replay:()=>{},
 animateBucket:async target=>{env.bucketY=target;},narrate:async id=>{cues.push(id);},
 listen:(id,fn)=>callbacks[id]=fn,run:fn=>{pending=fn({});}};
vm.createContext(env);vm.runInContext(JSON.parse(process.argv[1]),env);
(async()=>{callbacks.raise();assert.equal(pending,undefined);assert.equal(env.state,'high_empty');
 callbacks.lower();await pending;assert.equal(env.state,'low_full');assert.equal(env.filled,true);
 assert.equal(elements.lower.disabled,true);callbacks.raise();await pending;
 assert.equal(env.bucketY,1.5);assert.equal(env.state,'high_full');assert.equal(elements.finish.disabled,false);
 callbacks.rotate();assert.ok(env.poses.well.angle>0);callbacks.reset();await pending;
 assert.equal(env.state,'high_empty');assert.equal(env.filled,false);assert.equal(env.poses.well.angle,0);
 assert.deepEqual(cues,['lower','raise','reset']);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result=subprocess.run([shutil.which('node'),'-e',program,json.dumps(WELL_CONTROLS)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_chan_keeps_its_fifth_horizontal_before_the_final_left_falling_stroke(self):
        # GF 0023-2020: 产 is six strokes, 4 1 4 3 1 3.
        self.assertEqual(len(STROKES['产']), 6)
        fifth, sixth = STROKES['产'][4:]
        self.assertEqual(fifth[0][1], fifth[-1][1])
        self.assertGreater(fifth[-1][0], fifth[0][0])
        self.assertLess(sixth[-1][0], sixth[0][0])
        self.assertGreater(sixth[-1][1], sixth[0][1])

    def test_unfinished_goals_and_changed_target_characters_are_rejected(self):
        task,design,scope=recipe();validate_recipe(task,design,scope)
        scope['activityGoalIds'].append('alphabet_names');design['scenes'][1]['activityGoalIds'].append('alphabet_names')
        with self.assertRaisesRegex(ValueError,'unfinished_goal'):validate_recipe(task,design,scope)
        task,design,scope=recipe();design['scenes'][1]['cards'][0]['character']='高'
        with self.assertRaisesRegex(ValueError,'character_scope'):validate_recipe(task,design,scope)

    def test_reordering_strokes_or_reusing_answer_pictures_is_rejected(self):
        task,design,scope=recipe();row=design['scenes'][2]['characters'][0];row['strokes'][2],row['strokes'][4]=row['strokes'][4],row['strokes'][2]
        with self.assertRaisesRegex(ValueError,'stroke_order'):validate_recipe(task,design,scope)
        task,design,scope=recipe();design['scenes'][3]['rounds'][0]['optionAssetIds']=['learn']*3
        with self.assertRaisesRegex(ValueError,'distinct_answers'):validate_recipe(task,design,scope)

    def test_foreign_scene_audio_and_unbounded_roles_are_rejected(self):
        task,design,scope=recipe();design['scenes'][2]['characters'][0]['strokeCueIds'][0]='c1'
        with self.assertRaisesRegex(ValueError,'foreign_cue'):validate_recipe(task,design,scope)
        task,design,scope=recipe();design['scenes'][2]['renderer']='arbitrary_html'
        with self.assertRaisesRegex(ValueError,'scene_roles'):validate_recipe(task,design,scope)

    def test_shared_picture_exception_requires_exact_generated_observation(self):
        task,design,scope=recipe();assets=validate_recipe(task,design,scope);planned=design['scenes'][1]
        frozen={'activityDesign':design,'reviewedLessonScope':scope,'binding':task['scope']};scene={'id':planned['sceneId']}
        html=cards_scene(planned,assets)
        self.assertTrue(_reviewed_word_observation(frozen,scene,html))
        self.assertFalse(_reviewed_word_observation(frozen,scene,html+'<button>未审核选择</button>'))
        geometry=stroke_scene(design['scenes'][2],assets)
        self.assertIn("canvas.getContext('webgl'",geometry)
        self.assertIn('strokeGeometry',geometry)
        self.assertNotIn('speechSynthesis',geometry)

    @unittest.skipUnless(shutil.which('node'), 'Node is required for the rendered interaction check')
    def test_rendered_next_stroke_waits_for_paint_and_dispatches_narration(self):
        task,design,scope=recipe();assets=validate_recipe(task,design,scope)
        html=stroke_scene(design['scenes'][2],assets)
        helper=re.search(r'function displayed\(signal\).*?\n',html)
        self.assertIsNotNone(helper, 'Rendered stroke controls must include their frame-wait helper')
        next_handler=re.search(r"listen\('next',.*?\n",html).group(0)
        program=r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
const callbacks={},cues=[],signal=new AbortController().signal;let pending;
const env={AbortController,setTimeout,clearTimeout,document:{hidden:false},
  requestAnimationFrame:fn=>setTimeout(fn,0),cancelAnimationFrame:clearTimeout,
  interactionBusy:false,started:true,gl:{},shown:0,item:0,
  config:{characters:[{strokes:[[],[],[],[],[]],strokeCueIds:['first']}]},
  show:()=>{},listen:(id,fn)=>{callbacks[id]=fn;},
  run:fn=>{pending=fn(signal);},narrate:async id=>{cues.push(id);}};
vm.createContext(env);vm.runInContext(JSON.parse(process.argv[1]),env);
(async()=>{callbacks.next();await pending;assert.equal(env.shown,1);
  assert.deepEqual(cues,['first']);const stop=new AbortController();stop.abort();
  await assert.rejects(env.displayed(stop.signal),/cancelled/);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result=subprocess.run([shutil.which('node'),'-e',program,json.dumps(helper.group(0)+next_handler)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
