"""Compile exact-page, bounded Chinese review activities without paid calls."""
import json
from pathlib import Path

from content import chinese_integrated_activity as integrated
from content import chinese_community_activity as community
from content import chinese_reading_activity as reading
from content import chinese_word_activity as words
from content import chinese_letter_activity as letters
from content import chinese_dictionary_activity as dictionary
from content import chinese_animal_activity as animals
from content import chinese_sports_activity as sports
from content import chinese_nature_activity as nature
from content import chinese_surname_activity as surnames
from content import textbook_activity_templates as t
from content.teacher_profiles import get_formal_runtime_teacher_contract
from content.textbook_activity_ir import byte_sha, require, safe_svg
from content.textbook_batch_generation import freeze_input, reviewed_lesson_scope
from content.textbook_catalog import canonical, digest
from content.textbook_interactive_narration import interactive_cues
from content.textbook_provided_media import validate_frozen_provided_media
from services.textbook_activity_compiler import game_scene, _write_exact, ROOT
from services.textbook_batch_generation_service import TextbookBatchGenerationService


def validate_recipe(task, design, scope):
    require(task['kind']=='lesson_courseware' and task['scope']['subject']=='chinese'
            and task['scope']['gradeCode'] in {'primary_1','primary_2'}
            and design.get('lessonFamily')=='chinese_integrated_review_v1', 'integrated_family_invalid')
    required_renderers={'observation_video','picture_match','word_cards','stroke_order_3d','illustrated_reading'}
    renderers=required_renderers|{'well_lift_3d','letter_case_match','rhythm_drum_3d','dictionary_lookup','ant_transport_3d','sports_ball_3d','picture_recitation','original_picture_recall','natural_motion_3d','rain_radical','surname_components_3d','qing_components_3d','riddle_components_3d'}
    scenes=design.get('scenes',[])
    require(5<=len(scenes)<=12 and design.get('sceneCount')==len(scenes)
            and len({s['sceneId'] for s in scenes})==len(scenes)
            and scenes[0]['renderer']=='observation_video'
            and required_renderers<={s['renderer'] for s in scenes}<=renderers, 'integrated_scene_roles_invalid')
    require(all(s['widgetType']==('visualization3d' if s['renderer'] in {'stroke_order_3d','well_lift_3d','rhythm_drum_3d','ant_transport_3d','sports_ball_3d','natural_motion_3d','surname_components_3d','qing_components_3d','riddle_components_3d'} else 'game') for s in scenes), 'integrated_widget_changed')
    goals=scope.get('activityGoalIds',[])
    require(goals and len(set(goals))==len(goals) and set(goals)=={g for s in scenes for g in s.get('activityGoalIds',[])}, 'integrated_goal_coverage_changed')
    require(not (set(goals)&set(scope.get('outstandingGoalIds',[]))), 'integrated_unfinished_goal_cannot_be_claimed')
    assets={}
    for asset in design.get('assetPlan',[]):
        require(asset['assetId'] not in assets and byte_sha(asset['svgMarkup'].encode())==asset['sha256'], 'integrated_picture_changed')
        assets[asset['assetId']]=safe_svg(asset['svgMarkup'])
    cues=[c for s in scenes for c in s.get('finiteCues',[])]
    require(cues==design.get('finiteCues') and len({c['cueId'] for c in cues})==len(cues), 'integrated_cue_coverage_changed')
    for scene in scenes:
        own={c['cueId'] for c in scene['finiteCues']}
        def check(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if key.endswith('CueId') or key=='cueId':require(item in own,'integrated_foreign_cue')
                    elif key.endswith('CueIds'):require(isinstance(item,list) and set(item)<=own,'integrated_foreign_cue')
                    elif key.endswith('AssetId') or key=='assetId':require(item in assets,'integrated_unknown_picture')
                    else:check(item)
            elif isinstance(value,list):
                for item in value:check(item)
        check(scene)
        role=scene['renderer']
        if role=='word_cards':
            require({c['character'] for c in scene['cards']}==set(scope['recognizedCharacters'])
                    and len(scene['cards'])==len(scope['recognizedCharacters'])
                    and scene.get('writingCharacters')==scope['writingCharacters'], 'integrated_character_scope_changed')
        elif role=='picture_match':
            require(3<=len(scene['rounds'])<=12, 'integrated_game_rounds_missing')
            for row in scene['rounds']:
                options=row['optionAssetIds']
                introduced=scope.get('introducedPortraitAssetIds')
                four_portraits=(introduced==surnames.PORTRAIT_IDS and len(options)==4
                               and set(options)==set(introduced)
                               and set(scene.get('activityGoalIds',[]))<={'supported_surname_listening','surname_turn_taking'})
                require(row['mode']=='spoken_language_picture_matching'
                        and (len(options)==3 or four_portraits)
                        and len(options)==len(set(options))==len({assets[a] for a in options})
                        and row['targetAssetId'] in options, 'integrated_distinct_answers_required')
        elif role=='stroke_order_3d':
            require({c['character'] for c in scene['characters']}==set(scope['observedCharacters']), 'integrated_stroke_scope_changed')
            for c in scene['characters']:
                require(c['strokes']==integrated.STROKES.get(c['character']) and len(c['strokeCueIds'])==len(c['strokes']), 'integrated_stroke_order_changed')
        elif role=='illustrated_reading':
            require(3<=len(scene['pages'])<=8 and len({assets[p['assetId']] for p in scene['pages']})==len(scene['pages']), 'integrated_distinct_reading_pages_required')
        elif role=='picture_recitation':
            pages=scene.get('pages',[])
            source=scope.get('publicDomainText',{}).get('text','')
            source_lines=[line.strip() for line in source.splitlines() if line.strip()]
            texts={c['cueId']:c['teacherText'] for c in scene['finiteCues']}
            require(scene.get('adapterId')=='public_domain_picture_recall_v1'
                    and set(scene.get('activityGoalIds',[]))=={'classical_recitation_practice'}
                    and 3<=len(pages)<=8 and len({assets[p['assetId']] for p in pages})==len(pages)
                    and [p.get('modelText') for p in pages]==source_lines
                    and all(p.get('promptCueId') in own and p.get('modelCueId') in own
                            and texts[p['modelCueId']]==p['modelText'] for p in pages)
                    and all(scene.get(k) in own for k in ('initialCueId','completeCueId'))
                    and not any(k in scene for k in ('html','script','geometry','states','score')),
                    'integrated_public_domain_recall_contract_invalid')
        elif role=='original_picture_recall':
            pages=scene.get('pages',[])
            texts={c['cueId']:c['teacherText'] for c in scene['finiteCues']}
            require(scene.get('adapterId')=='original_picture_recall_v1'
                    and set(scene.get('activityGoalIds',[]))=={'review_and_retrieval'}
                    and 3<=len(pages)<=8
                    and len({assets[p['assetId']] for p in pages})==len(pages)
                    and [p.get('modelText') for p in pages]==scope.get('originalRecallModels')
                    and all(isinstance(p.get('modelText'),str) and 1<=len(p['modelText'])<=240
                            and p.get('promptCueId') in own and p.get('modelCueId') in own
                            and p['promptCueId']!=p['modelCueId']
                            and texts[p['modelCueId']]==p['modelText']
                            and p['modelText'] not in texts[p['promptCueId']] for p in pages)
                    and all(scene.get(k) in own for k in ('initialCueId','completeCueId'))
                    and not any(k in scene for k in ('html','script','geometry','states','score','mastery')),
                    'integrated_original_recall_contract_invalid')
        elif role=='observation_video':
            count=scene.get('sourceAlignedObservationCount',3)
            portraits=scope.get('introducedPortraitAssetIds')
            four_portraits=(count==4 and portraits==surnames.PORTRAIT_IDS
                           and [o['assetId'] for o in scene['observations']]==portraits
                           and scene.get('observationPortraitAssetIds')==portraits)
            require(type(count) is int and (count==3 or four_portraits or count==8 and count==len(scope['recognizedCharacters'])
                    and scene.get('observationCharacters')==scope['recognizedCharacters'])
                    and len(scene['observations'])==count and len({o['assetId'] for o in scene['observations']})==count,
                    'integrated_video_views_missing')
        elif role=='surname_components_3d':
            surnames.validate_scene(scene,scope)
        elif role=='qing_components_3d':
            states=scene.get('states',[])
            require(scene.get('modelAdapterKey')=='reviewed_chinese_glyph_relief'
                    and scope.get('componentObservedCharacters')==list('清晴睛情请')
                    and [(s.get('sceneStateId'),s.get('character'),s.get('splitFraction')) for s in states]
                        ==list(zip(['s0','s1','s2','s3','s4'],list('清晴睛情请'),[.32,.43,.43,.31,.33]))
                    and set(scene.get('activityGoalIds',[]))=={'qing_components'}
                    and all(scene.get(k) in own for k in ('initialCueId','retryCueId','resetCueId','completeCueId','separateCueId','joinCueId'))
                    and all(s.get('observationCueId') in own for s in states)
                    and len({s['assetId'] for s in states})==5
                    and not any(k in scene for k in ('html','script','geometry','score')),
                    'integrated_qing_component_contract_invalid')
        elif role=='riddle_components_3d':
            states=scene.get('states',[])
            require(scene.get('modelAdapterKey')=='reviewed_chinese_glyph_relief'
                    and scope.get('componentObservedCharacters')==list('秋明清晴请情')
                    and [(s.get('sceneStateId'),s.get('character'),s.get('splitFraction')) for s in states]
                        ==list(zip(['s0','s1','s2','s3','s4','s5'],list('秋明清晴请情'),[.47,.47,.32,.43,.33,.31]))
                    and set(scene.get('activityGoalIds',[]))=={'riddle_components'}
                    and all(scene.get(k) in own for k in ('initialCueId','retryCueId','resetCueId','completeCueId','separateCueId','joinCueId'))
                    and all(s.get('observationCueId') in own for s in states)
                    and len({s['assetId'] for s in states})==6
                    and not any(k in scene for k in ('html','script','geometry','score')),
                    'integrated_riddle_component_contract_invalid')
        elif role=='natural_motion_3d':
            require(scene.get('modelAdapterKey')=='seasons_natural_motion'
                    and [s.get('sceneStateId') for s in scene.get('states',[])]==['wind','snow','swim']
                    and set(scene.get('activityGoalIds',[]))=={'natural_motion_observation'}
                    and all(scene.get(k) in own for k in ('initialCueId','retryCueId','resetCueId','completeCueId'))
                    and not any(k in scene for k in ('html','script','geometry')), 'integrated_nature_contract_invalid')
        elif role=='rain_radical':
            require('霜' in scope['recognizedCharacters'] and scene.get('character')=='霜'
                    and set(scene.get('activityGoalIds',[]))=={'rain_radical_observation'}
                    and {'frost','rain'}<=assets.keys()
                    and all(scene.get(k) in own for k in ('initialCueId','wholeCueId','topCueId','pictureCueId','resetCueId','finishCueId'))
                    and not any(k in scene for k in ('html','script','geometry')), 'integrated_radical_contract_invalid')
        elif role=='well_lift_3d':
            require(scene.get('adapterId')=='well_bucket_lift_v1'
                    and set(scene.get('activityGoalIds',[]))=={'picture_word_meaning'}
                    and all(scene.get(k) in own for k in community.WELL_CUE_KEYS)
                    and not any(k in scene for k in ('html','script','geometry','states')), 'integrated_well_contract_invalid')
        elif role=='letter_case_match':
            letters.validate_scene(scene,assets,scope)
        elif role=='dictionary_lookup':
            dictionary.validate_scene(scene,assets,scope)
        elif role=='ant_transport_3d':
            require(scene.get('adapterId')=='ant_food_transport_v1'
                    and set(scene.get('activityGoalIds',[]))=={'animal_action_phrases'}
                    and all(scene.get(k) in own for k in animals.ANT_CUE_KEYS)
                    and not any(k in scene for k in ('html','script','geometry','states')), 'integrated_ant_contract_invalid')
        elif role=='sports_ball_3d':
            require(scene.get('adapterId')=='hand_foot_ball_v1'
                    and set(scene.get('activityGoalIds',[]))=={'sports_action_words'}
                    and all(scene.get(k) in own for k in sports.SPORTS_CUE_KEYS)
                    and scene.get('dribbleAssetId') in assets and scene.get('kickAssetId') in assets
                    and assets[scene['dribbleAssetId']]!=assets[scene['kickAssetId']]
                    and not any(k in scene for k in ('html','script','geometry','states')), 'integrated_sports_contract_invalid')
        elif role=='rhythm_drum_3d':
            patterns=scene.get('patterns',[])
            require(scene.get('adapterId')=='turn_taking_drum_v1'
                    and len(patterns)==3 and [p.get('beats') for p in patterns]==[2,3,4]
                    and all(type(p.get('beats')) is int for p in patterns)
                    and len({p.get('assetId') for p in patterns})==3
                    and all(p.get('cueId') in own and p.get('feedbackCueId') in own for p in patterns)
                    and all(scene.get(k) in own for k in ('initialCueId','retryCueId','yourTurnCueId','completeCueId'))
                    and not any(k in scene for k in ('html','script','geometry','states')), 'integrated_drum_contract_invalid')
    return assets


def compile_integrated(task_path, design_path, output):
    task_path,design_path=Path(task_path).resolve(),Path(design_path).resolve()
    task=json.loads(task_path.read_text())
    # Render the same key ordering stored by freeze_input and read by reviewers.
    design=json.loads(canonical(json.loads(design_path.read_text())))
    scope_path=Path(design['reviewedLessonScopePath']).resolve()
    require(byte_sha(scope_path.read_bytes())==design['reviewedLessonScopeByteSha256'],'integrated_scope_bytes_changed')
    scope=reviewed_lesson_scope(task,scope_path)
    require(scope.get('evidence',{}).get('pages'), 'integrated_exact_pages_required')
    for page in scope['evidence']['pages']:require(byte_sha(Path(page['path']).read_bytes())==page['sha256'],'integrated_source_page_changed')
    assets=validate_recipe(task,design,scope)
    frozen=freeze_input(task,reviewed_scope_path=scope_path,design_plan_path=design_path);validate_frozen_provided_media(frozen)
    renderers={'observation_video':t.video_scene,'word_cards':words.cards_scene,'stroke_order_3d':integrated.stroke_scene,
               'well_lift_3d':community.well_scene,
               'letter_case_match':letters.letter_scene,
               'rhythm_drum_3d':reading.rhythm_scene,
               'dictionary_lookup':dictionary.dictionary_scene,
               'ant_transport_3d':animals.ant_scene,
               'sports_ball_3d':sports.sports_scene,
               'natural_motion_3d':nature.model,'rain_radical':nature.radical,
               'surname_components_3d':surnames.glyph_model,
               'qing_components_3d':words.glyph_scene,'riddle_components_3d':words.glyph_scene,
               'picture_recitation':reading.recitation_scene,
               'original_picture_recall':reading.original_recall_scene,
               'illustrated_reading':reading.reading_scene,'picture_match':lambda s,a:game_scene(s,a,'spoken_language_picture_matching')}
    htmls=[renderers[s['renderer']](s,assets) for s in design['scenes']]
    for s,html in zip(design['scenes'],htmls):require(interactive_cues(html)==[{'id':c['cueId'],'text':c['teacherText']} for c in s['finiteCues']],'integrated_rendered_cue_drift')
    output=Path(output).resolve();require(output.is_relative_to(ROOT/'output'),'integrated_owned_output_required')
    state=TextbookBatchGenerationService(output/'prepared').prepare(frozen);folder=output/'candidates'/task['taskId'];folder.mkdir(parents=True,exist_ok=True)
    from services import textbook_activity_compiler
    modules=[Path(__file__),Path(integrated.__file__),Path(community.__file__),Path(reading.__file__),Path(words.__file__),Path(letters.__file__),Path(dictionary.__file__),Path(animals.__file__),Path(sports.__file__),Path(nature.__file__),Path(nature.models.__file__),Path(t.__file__),Path(textbook_activity_compiler.__file__)]
    modules.append(Path(surnames.__file__))
    files={str(p.relative_to(ROOT)):byte_sha(p.read_bytes()) for p in modules};identity='cngarden_'+task['taskId'][:16]+'_'+digest({'design':design,'compiler':files})[:8]
    teacher=frozen['runtimeBatchContext']['teacher'];runtime=get_formal_runtime_teacher_contract('chinese')['runtime'];now=state['createdAt']
    stage={'id':identity,'name':design['title'],'style':'interactive','createdAt':now,'updatedAt':now,'videoManifest':{},
           'generatedAgentConfigs':[{'id':'mira-'+task['taskId'][:16]+'-teacher','name':teacher['teacherName'],'role':'teacher','avatar':runtime['avatar'],
              'teacherProfile':teacher['teacherProfile'],'voiceConfig':runtime['voiceConfig'],'persona':'用图画、声音和实际操作陪伴孩子做本年级语文练习。','color':'#42685d','priority':10}]}
    room={'id':identity,'createdAt':now,'stage':stage,'scenes':[{'id':s['sceneId'],'outlineId':'local_'+s['sceneId'],'stageId':identity,
          'type':'interactive','title':s['title'],'order':i,'content':{'type':'interactive','widgetType':s['widgetType'],'html':html},'actions':[],
          'createdAt':now,'updatedAt':now} for i,(s,html) in enumerate(zip(design['scenes'],htmls))]}
    generated={**state,'status':'generated_needs_review','classroomId':identity,'classroomSha256':digest(room),'runtimeOrigin':'http://127.0.0.1:3100',
        'authoringMode':'structured_local_original','sourceGenerationStatus':'not_dispatched','sourceGenerationJobId':None,
        'qualityPassed':False,'browserQAPassed':False,'sourceNodeEntirelyCovered':False,'outstandingGoalIds':scope.get('outstandingGoalIds',[])}
    source=output/'prepared'/task['taskId']
    derivation={'schemaVersion':'mira.textbook.deterministic-compiler.v1','authoringMode':'structured_local_original','sourceDirectory':str(source),
      'sourceFiles':{n:byte_sha((source/n).read_bytes()) for n in ('input.json','state.json')},'externalAuthoringFiles':{str(p):byte_sha(p.read_bytes()) for p in (task_path,design_path,scope_path)},
      'compilerFiles':files,'parentInputSha256':frozen['inputSha256'],'activityDesignSha256':digest(design),'classroomSha256':digest(room),'sourceGenerationStatus':'not_dispatched',
      'sourceGenerationJobId':None,'providerCalls':0,'runtimeSaves':0,'audioCalls':0,'publicationAllowed':False,'studentDeliveryAllowed':False,'qualityPassed':False,'browserQAPassed':False}
    for name,value in [('input.json',frozen),('state.json',generated),('classroom.json',room),('derivation.json',derivation)]:_write_exact(folder/name,(canonical(value)+'\n').encode())
    from services.textbook_batch_queue_audio_service import structural_review
    review=structural_review(folder);_write_exact(folder/'compiler-static-review.json',(canonical(review)+'\n').encode())
    return {'taskId':task['taskId'],'candidateDirectory':str(folder),'classroomId':identity,'cueCount':len(design['finiteCues']),'structuralChecksPassed':review['structuralChecksPassed'],'issues':review['issues']}
