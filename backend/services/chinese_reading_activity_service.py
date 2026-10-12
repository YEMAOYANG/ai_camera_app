"""Compile reviewed original reading recipes; no model calls or publication."""
import json
from pathlib import Path

from content import chinese_reading_activity as reading
from content import textbook_activity_templates as t
from content.teacher_profiles import get_formal_runtime_teacher_contract
from content.textbook_activity_ir import byte_sha, require, safe_svg
from content.textbook_batch_generation import freeze_input, reviewed_lesson_scope
from content.textbook_catalog import canonical, digest
from content.textbook_interactive_narration import interactive_cues
from content.textbook_provided_media import validate_frozen_provided_media
from services.textbook_activity_compiler import game_scene, _write_exact, ROOT
from services.textbook_batch_generation_service import TextbookBatchGenerationService


READING_PHASES_V1 = ['observation_video', 'picture_match', 'rhythm_drum', 'illustrated_reading']
READING_PHASES_V2 = [
    'observation_video', 'illustrated_reading', 'illustrated_reading',
    'picture_recitation', 'picture_match', 'illustrated_reading',
    'rhythm_drum', 'illustrated_reading', 'illustrated_reading',
    'picture_match', 'illustrated_reading',
]


def validate_recipe(task, design, scope):
    detailed = design.get('lessonFamily') == 'chinese_reading_rhythm_v2'
    require(task['kind']=='lesson_courseware' and task['scope']['subject']=='chinese'
            and task['scope']['gradeCode'] in {'primary_1','primary_2'}
            and design.get('lessonFamily') in {'chinese_reading_rhythm_v1', 'chinese_reading_rhythm_v2'}, 'reading_family_invalid')
    scenes=design.get('scenes',[])
    phases = READING_PHASES_V2 if detailed else READING_PHASES_V1
    require([s.get('renderer') for s in scenes] == phases, 'reading_scene_roles_changed')
    require([s.get('widgetType') for s in scenes] == [
        'visualization3d' if role == 'rhythm_drum' else 'game' for role in phases], 'reading_widgets_changed')
    require(design.get('sceneCount')==len(phases) and len({s['sceneId'] for s in scenes})==len(phases), 'reading_scene_identity_invalid')
    assets={}
    for asset in design.get('assetPlan',[]):
        require(asset['assetId'] not in assets and byte_sha(asset['svgMarkup'].encode())==asset['sha256'], 'reading_picture_changed')
        assets[asset['assetId']]=safe_svg(asset['svgMarkup'])
    require(len(assets)>=3, 'reading_pictures_missing')
    goal_ids=scope.get('activityGoalIds',[])
    require(len(goal_ids)>=3 and len(set(goal_ids))==len(goal_ids)
            and set(goal_ids)=={g for s in scenes for g in s.get('activityGoalIds',[])}, 'reading_goal_coverage_changed')
    if detailed:
        require(not set(goal_ids).intersection(scope.get('outstandingGoalIds', [])), 'reading_unfinished_goal_claimed')
    cues=[c for s in scenes for c in s.get('finiteCues',[])]
    require(cues==design.get('finiteCues') and len({c['cueId'] for c in cues})==len(cues), 'reading_cue_coverage_changed')
    for scene in scenes:
        own={c['cueId'] for c in scene['finiteCues']}
        def check(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if key.endswith('CueId') or key=='cueId':
                        require(item in own,'reading_foreign_scene_cue')
                    elif key.endswith('AssetId') or key=='assetId':
                        require(item in assets,'reading_unknown_picture')
                    else:
                        check(item)
            elif isinstance(value,list):
                for item in value: check(item)
        check(scene)
        role = scene['renderer']
        if role == 'observation_video':
            require(len(scene.get('observations',[]))==3 and len({v['assetId'] for v in scene['observations']})==3, 'reading_video_observations_missing')
        elif role == 'picture_match':
            require(3<=len(scene.get('rounds',[]))<=12,'reading_picture_rounds_invalid')
            for r in scene['rounds']:
                options=r['optionAssetIds']
                require(r['mode']=='spoken_language_picture_matching' and len(options)==len(set(options))==3
                        and set(options)<=set(assets) and r['targetAssetId'] in options
                        and len({assets[k] for k in options})==3, 'reading_distinct_answer_pictures_required')
                if detailed:
                    require(r.get('retryCueId') in own, 'reading_specific_retry_required')
        elif role == 'rhythm_drum':
            patterns=scene.get('patterns',[])
            require(len(patterns)==3 and all(type(p.get('beats')) is int and 2<=p['beats']<=4 for p in patterns)
                    and len({p['assetId'] for p in patterns})==3, 'reading_bounded_rhythm_required')
        elif role == 'illustrated_reading':
            pages=scene.get('pages',[])
            require(3<=len(pages)<=8 and len({assets[p['assetId']] for p in pages})==len(pages)
                    and all(isinstance(p.get('displayText'),str) and 1<=len(p['displayText'])<=100 for p in pages), 'reading_pages_invalid')
        elif role == 'picture_recitation':
            source_lines = [line.strip() for line in scope.get('publicDomainText', {}).get('text', '').splitlines() if line.strip()]
            pages = scene.get('pages', [])
            texts = {c['cueId']:c['teacherText'] for c in scene['finiteCues']}
            require(scene.get('adapterId')=='public_domain_picture_recall_v1'
                    and 3<=len(pages)<=8 and len({assets[p['assetId']] for p in pages})==len(pages)
                    and [p.get('modelText') for p in pages]==source_lines
                    and all(p.get('promptCueId') in own and p.get('modelCueId') in own
                            and p.get('modelLeadIn', '') in {'', '跟老师读。'}
                            and texts[p['modelCueId']]==p.get('modelLeadIn', '')+p['modelText'] for p in pages)
                    and all(scene.get(k) in own for k in ('initialCueId','completeCueId'))
                    and not any(k in scene for k in ('html','script','geometry','states','score')),
                    'reading_public_domain_recall_contract_invalid')
    return assets


def compile_reading(task_path, design_path, output):
    task_path,design_path=Path(task_path).resolve(),Path(design_path).resolve()
    task,design=json.loads(task_path.read_text()),json.loads(design_path.read_text())
    scope_path=Path(design['reviewedLessonScopePath']).resolve()
    require(byte_sha(scope_path.read_bytes())==design['reviewedLessonScopeByteSha256'],'reading_scope_bytes_changed')
    scope=reviewed_lesson_scope(task,scope_path)
    pages=scope.get('evidence',{}).get('pages',[])
    require(bool(pages),'reading_source_pages_required')
    for page in pages:
        require(byte_sha(Path(page['path']).read_bytes())==page['sha256'],'reading_source_page_changed')
    assets=validate_recipe(task,design,scope)
    frozen=freeze_input(task,reviewed_scope_path=scope_path,design_plan_path=design_path)
    validate_frozen_provided_media(frozen)
    scenes=design['scenes']
    renderers={'observation_video':t.video_scene,
               'picture_match':lambda scene, assets:game_scene(scene,assets,'spoken_language_picture_matching'),
               'rhythm_drum':reading.rhythm_scene,'illustrated_reading':reading.reading_scene,
               'picture_recitation':reading.recitation_scene}
    htmls=[renderers[scene['renderer']](scene,assets) for scene in scenes]
    for scene,html in zip(scenes,htmls):
        require(interactive_cues(html)==[{'id':c['cueId'],'text':c['teacherText']} for c in scene['finiteCues']], 'reading_rendered_cue_drift')
    output=Path(output).resolve()
    require(output.is_relative_to(ROOT/'output'),'reading_owned_output_required')
    prepared=output/'prepared'; state=TextbookBatchGenerationService(prepared).prepare(frozen)
    folder=output/'candidates'/task['taskId'];folder.mkdir(parents=True,exist_ok=True)
    from services import textbook_activity_compiler
    modules=[Path(__file__),Path(reading.__file__),Path(t.__file__),Path(textbook_activity_compiler.__file__)]
    compiler_files={str(p.relative_to(ROOT)):byte_sha(p.read_bytes()) for p in modules}
    identity='cnread_'+task['taskId'][:16]+'_'+digest({'design':design,'compiler':compiler_files})[:8]
    teacher=frozen['runtimeBatchContext']['teacher'];runtime=get_formal_runtime_teacher_contract('chinese')['runtime']
    stage={'id':identity,'name':design['title'],'style':'interactive','createdAt':state['createdAt'],'updatedAt':state['createdAt'],
           'generatedAgentConfigs':[{'id':'mira-'+task['taskId'][:16]+'-teacher','name':teacher['teacherName'],'role':'teacher',
              'avatar':runtime['avatar'],'teacherProfile':teacher['teacherProfile'],'voiceConfig':runtime['voiceConfig'],
              'persona':'用原创图画、声音和节奏陪孩子读儿歌。','color':'#42685d','priority':10}],'videoManifest':{}}
    classroom={'id':identity,'createdAt':state['createdAt'],'stage':stage,'scenes':[
        {'id':s['sceneId'],'outlineId':'local_'+s['sceneId'],'stageId':identity,'type':'interactive','title':s['title'],'order':i,
         'content':{'type':'interactive','widgetType':s['widgetType'],'html':html},'actions':[],
         'createdAt':state['createdAt'],'updatedAt':state['createdAt']} for i,(s,html) in enumerate(zip(scenes,htmls))]}
    generated={**state,'status':'generated_needs_review','classroomId':identity,'classroomSha256':digest(classroom),
        'runtimeOrigin':'http://127.0.0.1:3100','authoringMode':'structured_local_original','sourceGenerationStatus':'not_dispatched',
        'sourceGenerationJobId':None,'qualityPassed':False,'browserQAPassed':False,'sourceNodeEntirelyCovered':False,
        'outstandingGoalIds':scope.get('outstandingGoalIds',[])}
    source=prepared/task['taskId']
    derivation={'schemaVersion':'mira.textbook.deterministic-compiler.v1','authoringMode':'structured_local_original',
        'sourceDirectory':str(source),'sourceFiles':{n:byte_sha((source/n).read_bytes()) for n in ('input.json','state.json')},
        'externalAuthoringFiles':{str(p):byte_sha(p.read_bytes()) for p in (task_path,design_path,scope_path)},
        'compilerFiles':compiler_files,'parentInputSha256':frozen['inputSha256'],'activityDesignSha256':digest(design),
        'classroomSha256':digest(classroom),'sourceGenerationStatus':'not_dispatched','sourceGenerationJobId':None,
        'providerCalls':0,'runtimeSaves':0,'audioCalls':0,'publicationAllowed':False,'studentDeliveryAllowed':False,
        'qualityPassed':False,'browserQAPassed':False}
    for name,value in [('input.json',frozen),('state.json',generated),('classroom.json',classroom),('derivation.json',derivation)]:
        _write_exact(folder/name,(canonical(value)+'\n').encode())
    from services.textbook_batch_queue_audio_service import structural_review
    report=structural_review(folder)
    _write_exact(folder/'compiler-static-review.json',(canonical(report)+'\n').encode())
    return {'taskId':task['taskId'],'candidateDirectory':str(folder),'classroomId':identity,
            'cueCount':len(design['finiteCues']),'structuralChecksPassed':report['structuralChecksPassed'],'issues':report['issues']}
