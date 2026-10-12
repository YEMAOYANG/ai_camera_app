"""Compile page-reviewed literacy recipes into private OpenMAIC candidates.

No model or speech dispatch and no publication. Renderer inputs, original source
pages and failed native attempts remain distinct immutable artifacts.
"""
from copy import deepcopy
import json
from pathlib import Path
import urllib.request

from content import chinese_word_activity as words
from content import textbook_activity_templates as t
from content.teacher_profiles import get_formal_runtime_teacher_contract
from content.textbook_activity_ir import byte_sha, require, safe_svg
from content.textbook_batch_generation import freeze_input, reviewed_lesson_scope
from content.textbook_catalog import canonical, digest
from content.textbook_interactive_narration import interactive_cues
from content.textbook_provided_media import validate_frozen_provided_media, STORE_ROOT
from services.textbook_activity_compiler import game_scene, _write_exact, ROOT
from services.textbook_batch_generation_service import TextbookBatchGenerationService, atomic_json


def install_video(render_receipt_path, design):
    path = Path(render_receipt_path).resolve()
    receipt = json.loads(path.read_text())
    task = design['taskId']
    require(receipt['taskId'] == task and receipt['binding'] == design['binding']
            and receipt['designSha256'] == digest(design), 'literacy_video_binding_changed')
    video = receipt['video']; source = Path(video['path']).resolve(); raw = source.read_bytes()
    require(source.parent == path.parent and byte_sha(raw) == video['sha256'], 'literacy_video_bytes_changed')
    asset_id = 'word_observation'
    owner = 'tbmedia_' + task[:12]
    name = asset_id+'-'+video['sha256'][:16]+'.mp4'
    target = STORE_ROOT / owner / 'media' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    _write_exact(target, raw)
    src = '/api/classroom-media/'+owner+'/media/'+name
    request = urllib.request.Request('http://127.0.0.1:3100'+src)
    with urllib.request.urlopen(request, timeout=30) as response:
        observed = response.read(len(raw)+1)
        require(response.status == 200 and observed == raw, 'literacy_video_http_readback_failed')
    renderer = Path(receipt['rendererPath'])
    require(byte_sha(renderer.read_bytes()) == receipt['sourceFiles'].get(str(renderer), receipt['rendererFileSha256']), 'literacy_video_renderer_changed')
    snapshot = path.parent / 'renderer-snapshot.py'
    _write_exact(snapshot, renderer.read_bytes())
    provided = path.parent / 'provided-video-receipt.json'
    value = {'schemaVersion':'mira.textbook.provided-video-receipt.v1','taskId':task,'binding':design['binding'],
             'assetId':asset_id,'sha256':video['sha256'],'bytes':len(raw),'mimeType':'video/mp4','src':src,
             'httpReadbackVerified':True,'rendererPath':str(snapshot),'rendererSha256':byte_sha(snapshot.read_bytes()),
             'originalRenderReceiptPath':str(path),'originalRenderReceiptSha256':byte_sha(path.read_bytes()),
             'probe':{'codec':'h264','durationMs':round(video['durationSeconds']*1000),'width':video['width'],'height':video['height']},
             'publicationAllowed':False}
    atomic_json(provided,value,immutable=True)
    result = deepcopy(design)
    result['providedMediaAssets'] = [{k:value[k] for k in ('taskId','binding','assetId','sha256','bytes','mimeType','src')} | {
        'kind':'video','originality':'original_programmatic_animation','localPath':str(source),
        'receiptPath':str(provided),'receiptSha256':byte_sha(provided.read_bytes())}]
    result['scenes'][0]['requiredVideoElement'] = {'src':src}
    return result


def compile_literacy(task_path, design_path, output):
    task_path, design_path = Path(task_path).resolve(), Path(design_path).resolve()
    task, design = json.loads(task_path.read_text()), json.loads(design_path.read_text())
    scope_path = Path(design['reviewedLessonScopePath']).resolve()
    require(byte_sha(scope_path.read_bytes()) == design['reviewedLessonScopeByteSha256'], 'literacy_scope_bytes_changed')
    scope = reviewed_lesson_scope(task, scope_path)
    require(task['scope']['subject'] == 'chinese' and task['scope']['gradeCode'] in {'primary_1','primary_2'}
            and task['kind'] == 'lesson_courseware' and design.get('lessonFamily') == 'chinese_word_contexts_v1', 'literacy_recipe_family_invalid')
    for page in scope.get('evidence',{}).get('pages',[]):
        require(byte_sha(Path(page['path']).read_bytes()) == page['sha256'], 'literacy_source_page_changed')
    require(bool(scope.get('evidence',{}).get('pages')), 'literacy_page_review_missing')
    frozen = freeze_input(task, reviewed_scope_path=scope_path, design_plan_path=design_path)
    validate_frozen_provided_media(frozen)
    assets = {}
    for asset in design['assetPlan']:
        require(byte_sha(asset['svgMarkup'].encode()) == asset['sha256'] and asset['assetId'] not in assets,
                'literacy_asset_changed')
        assets[asset['assetId']] = safe_svg(asset['svgMarkup'])
    scenes = design['scenes']
    require(len(scenes)==4 and [s['widgetType'] for s in scenes]==['game','game','visualization3d','game'], 'literacy_roles_changed')
    require(len(scenes[1]['rounds']) >= 3 and len(scenes[2]['states']) >= 3 and len(scenes[3]['cards']) >= 3,
            'literacy_learning_tasks_missing')
    learned = scope.get('recognizedCharacters',[])
    require(bool(learned) and {c['character'] for c in scenes[3]['cards']} == set(learned), 'literacy_recognition_coverage_changed')
    require(scenes[3].get('writingCharacters') == scope.get('writingCharacters'), 'literacy_writing_observation_missing')
    require(set(s['character'] for s in scenes[2]['states']) <= set(scope.get('observedCharacters',[])), 'literacy_model_outside_scope')
    all_cues = [cue for scene in scenes for cue in scene['finiteCues']]
    require(all_cues == design['finiteCues'] and len({c['cueId'] for c in all_cues}) == len(all_cues), 'literacy_cue_coverage_changed')
    htmls = [t.video_scene(scenes[0],assets), game_scene(scenes[1],assets,'spoken_language_picture_matching'),
             words.glyph_scene(scenes[2],assets), words.cards_scene(scenes[3],assets)]
    for scene,html in zip(scenes,htmls):
        require(interactive_cues(html)==[{'id':c['cueId'],'text':c['teacherText']} for c in scene['finiteCues']], 'literacy_rendered_cue_drift')
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT/'output'), 'literacy_owned_output_required')
    preparation = output/'prepared'
    state = TextbookBatchGenerationService(preparation).prepare(frozen)
    folder = output/'candidates'/task['taskId']; folder.mkdir(parents=True,exist_ok=True)
    from services import textbook_activity_compiler
    modules = [Path(__file__),Path(words.__file__),Path(t.__file__),Path(textbook_activity_compiler.__file__)]
    compiler_files = {str(p.relative_to(ROOT)):byte_sha(p.read_bytes()) for p in modules}
    identity = 'cnwords_'+task['taskId'][:16]+'_'+digest({'design':design,'compiler':compiler_files})[:8]
    teacher = frozen['runtimeBatchContext']['teacher']; runtime = get_formal_runtime_teacher_contract('chinese')['runtime']
    stage = {'id':identity,'name':design['title'],'style':'interactive','createdAt':state['createdAt'],'updatedAt':state['createdAt'],
        'generatedAgentConfigs':[{'id':'mira-'+task['taskId'][:16]+'-teacher','name':teacher['teacherName'],'role':'teacher',
        'avatar':runtime['avatar'],'teacherProfile':teacher['teacherProfile'],'voiceConfig':runtime['voiceConfig'],
        'persona':'用图片、声音和实际操作指导本年级识字。','color':'#42685d','priority':10}],'videoManifest':{}}
    classroom = {'id':identity,'createdAt':state['createdAt'],'stage':stage,'scenes':[
        {'id':s['sceneId'],'outlineId':'local_'+s['sceneId'],'stageId':identity,'type':'interactive','title':s['title'],'order':i,
         'content':{'type':'interactive','widgetType':s['widgetType'],'html':html},'actions':[],
         'createdAt':state['createdAt'],'updatedAt':state['createdAt']} for i,(s,html) in enumerate(zip(scenes,htmls))]}
    generated = {**state,'status':'generated_needs_review','classroomId':identity,'classroomSha256':digest(classroom),
        'runtimeOrigin':'http://127.0.0.1:3100','authoringMode':'structured_local_original','sourceGenerationStatus':'not_dispatched',
        'sourceGenerationJobId':None,'qualityPassed':False,'browserQAPassed':False,'sourceNodeEntirelyCovered':False}
    source = preparation/task['taskId']
    derivation = {'schemaVersion':'mira.textbook.deterministic-compiler.v1','authoringMode':'structured_local_original',
        'sourceDirectory':str(source),'sourceFiles':{n:byte_sha((source/n).read_bytes()) for n in ('input.json','state.json')},
        'externalAuthoringFiles':{str(p):byte_sha(p.read_bytes()) for p in (task_path,design_path,scope_path)},
        'compilerFiles':compiler_files,
        'parentInputSha256':frozen['inputSha256'],'activityDesignSha256':digest(design),'classroomSha256':digest(classroom),
        'sourceGenerationStatus':'not_dispatched','sourceGenerationJobId':None,'providerCalls':0,'runtimeSaves':0,'audioCalls':0,
        'publicationAllowed':False,'studentDeliveryAllowed':False,'qualityPassed':False,'browserQAPassed':False}
    for name,value in [('input.json',frozen),('classroom.json',classroom),('state.json',generated),('derivation.json',derivation)]:
        _write_exact(folder/name,(canonical(value)+'\n').encode())
    from services.textbook_batch_queue_audio_service import structural_review
    report = structural_review(folder)
    _write_exact(folder/'compiler-static-review.json',(canonical(report)+'\n').encode())
    return {'taskId':task['taskId'],'candidateDirectory':str(folder),'classroomId':identity,
            'cueCount':len(all_cues),'structuralChecksPassed':report['structuralChecksPassed'],'issues':report['issues']}
