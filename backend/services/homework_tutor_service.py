"""Child-owned, durable AI teaching turns; no schema changes or automatic retries.

The original image, transcription and bounded history are provider inputs. AI
judgments are teaching guidance, never independent exam/ability evidence.
"""
from __future__ import annotations
import base64
import hashlib
import io
import json
import math
from decimal import Decimal, InvalidOperation
import re
from pathlib import Path
import unicodedata
import uuid
from core.errors import ApiError
from services.homework_assets import crop_region, transformed_image
from services.homework_tutor_context import grading_context, reference_comparison
from services.homework_answer_quality import (reviewed_result, reviewed_lesson, teaching_quality, guidance_candidate,
    reference_for_correction, attach_reference_answer_layout, digest as quality_digest)
from services.homework_tencent_lesson import (lesson as reference_lesson, POLICY as REFERENCE_POLICY,
    TEACHING_SOURCE as REFERENCE_SOURCE, FOLLOWUP_SOURCE as REFERENCE_FOLLOWUP_SOURCE, grounded_followup)
from services.homework_tutor_image_target import (IMAGE_SCHEMA as TARGET_IMAGE_CONTRACT,
    verified_answer_target, attach_target_markers, target_contract_valid,
    region_to_target_input, region_from_target_input)
from services.homework_source_review import (run_source_review, read_confirmed_reviews, review_call_id,
    POLICY as SOURCE_REVIEW_POLICY, REVIEW_VERSIONS as SOURCE_REVIEW_VERSIONS)
from services.teacher_speech import normalize_teacher_speech, SPEECH_POLICY_VERSION

ROOT=Path(__file__).parents[1]
POLICY=json.loads((ROOT/'content/homework_tutor_policy.v1.json').read_text())
SCHEMA='mira.homework-tutor-turn.v1'
RESPONSE_SCHEMA='mira.homework-tutor-response.v1'
IMAGE_CONTRACT='mira.homework-tutor-image-input.v2'
CONTEXT_GUARD=dict(POLICY['imageInput']['contextGuard'])
REVIEW_SCOPE_SCHEMA='mira.homework-tutor-review-scope.v1'
QUALITY_IMPLEMENTATION_SHA256=hashlib.sha256((ROOT/'services/homework_answer_quality.py').read_bytes()).hexdigest()
REVIEW_IMPLEMENTATION_SHA256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def parsed(value,default=None):
    return json.loads(value) if isinstance(value,str) else value if value is not None else default


def sha(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('duplicate field')
        result[key]=value
    return result


def valid_region(value):
    try:
        region=crop_region(value)
        return region if region and region['width']>0 and region['height']>0 else None
    except (ApiError,ValueError,TypeError):
        return None


def region_contains(outer,inner):
    return bool(outer and inner and inner['x']>=outer['x']-1e-6 and inner['y']>=outer['y']-1e-6
        and inner['x']+inner['width']<=outer['x']+outer['width']+1e-6
        and inner['y']+inner['height']<=outer['y']+outer['height']+1e-6)


def question_context_suitable(region,page):
    """Conservative geometry guard, not proof of semantic completeness.

    Tencent can label a single fill-in row as a question while the objects or
    shared stem sit above it. Legal coordinates and answer containment cannot
    certify that context. Narrow/line-only windows therefore retain the page;
    a remaining crop still requires the teacher to verify all printed context.
    """
    return bool(region and region['height']>CONTEXT_GUARD['minimumQuestionHeightFraction']
        and region['width']*region['height']>=CONTEXT_GUARD['minimumQuestionAreaFraction']
        and region['width']*page['width']/(region['height']*page['height'])<=CONTEXT_GUARD['maximumQuestionAspectRatio'])


def teacher_input_image(image,photo,result,policy,paper_context=None):
    """Enlarge a verified whole question, never an answer blank by itself.

    Geometry trust is independent of the provider's grading verdict. In old
    Tencent rows the verified answer geometry is a deterministic read projection,
    rather than a field persisted in providerAssessment.
    """
    question=valid_region(result.get('region'))
    assessment=result.get('providerAssessment') or {}
    if not isinstance(assessment,dict): assessment={}
    if result.get('method')=='tencent_question.v1' and 'geometryVerified' not in assessment:
        from services.homework_tencent_normalizer import grading_reference
        assessment=grading_reference(result) or {}
    answer=valid_region(assessment.get('answerRegion'))
    validation=result.get('sourceValidation') or {}
    if not isinstance(validation,dict): validation={}
    question_verified=(validation.get('geometryVerified') is True
        if result.get('method')=='tencent_question.v1' else assessment.get('geometryVerified') is True)
    geometry_verified=bool(question_verified and assessment.get('geometryVerified') is True
        and region_contains(question,answer) and question!=answer)
    # Saved shared stems and diagrams may lie outside the leaf question box.
    # Keep the union, or the full page when the receipt cannot prove its frame.
    structure_context=None
    if isinstance(paper_context,dict):
        context_region=valid_region(paper_context.get('region'))
        verified=(paper_context.get('geometryVerified') is True
            and type(paper_context.get('frameWidth')) is int and paper_context['frameWidth']==photo.width
            and type(paper_context.get('frameHeight')) is int and paper_context['frameHeight']==photo.height
            and region_contains(context_region,answer))
        structure_context={'sourceDigest':paper_context.get('sourceDigest'),
            'regionInOriginalPage':context_region,'geometryVerified':bool(verified)}
        if verified and geometry_verified:
            left,top=min(question['x'],context_region['x']),min(question['y'],context_region['y'])
            right=max(question['x']+question['width'],context_region['x']+context_region['width'])
            bottom=max(question['y']+question['height'],context_region['y']+context_region['height'])
            question=valid_region({'x':left,'y':top,'width':right-left,'height':bottom-top})
        else:
            geometry_verified=False
    context_suitable=question_context_suitable(question,{'width':photo.width,'height':photo.height})
    selection='full_page'
    box=(0,0,photo.width,photo.height)
    # A region that is merely the answer box cannot preserve the printed stem
    # and diagram. Missing/rotated/overlapping geometry falls back to the page.
    if geometry_verified and context_suitable:
        padding=policy.get('imageInput',{}).get('questionPaddingPixels',16)
        if type(padding) is not int or not 0<=padding<=64: raise ValueError('invalid question image padding')
        x,y,width,height=(Decimal(str(question[key])) for key in ('x','y','width','height'))
        left=max(0,math.floor(x*photo.width)-padding)
        top=max(0,math.floor(y*photo.height)-padding)
        right=min(photo.width,math.ceil((x+width)*photo.width)+padding)
        bottom=min(photo.height,math.ceil((y+height)*photo.height)+padding)
        if right>left and bottom>top:
            box=(left,top,right,bottom)
            selection='question_region'
    left,top,right,bottom=box
    if box!=(0,0,photo.width,photo.height):
        buffer=io.BytesIO()
        photo.crop(box).save(buffer,format='PNG')
        selected=buffer.getvalue()
    else:
        selected=image
    contract={'schemaVersion':IMAGE_CONTRACT,'promptVersion':policy['prompt']['version'],
        'selection':selection,'modelCoordinateFrame':'input_image','responseCoordinateFrame':'original_page',
        'originalPageGeometry':{'width':photo.width,'height':photo.height},
        'inputPixelBounds':{'left':left,'top':top,'right':right,'bottom':bottom},
        'inputGeometry':{'width':right-left,'height':bottom-top},
        'inputWindow':{'x':left/photo.width,'y':top/photo.height,'width':(right-left)/photo.width,'height':(bottom-top)/photo.height},
        'contextGuard':{**CONTEXT_GUARD,'sourceQuestionRegionInOriginalPage':question,
            'geometryVerified':geometry_verified,'questionWindowSuitable':context_suitable},
        'sourceImageSha256':hashlib.sha256(image).hexdigest(),'inputImageSha256':hashlib.sha256(selected).hexdigest()}
    if structure_context is not None:contract['paperStructureContext']=structure_context
    return selected,contract


def image_contract_valid(value):
    """Current image contracts prove the source window, never answer accuracy."""
    if isinstance(value,dict) and value.get('schemaVersion')==TARGET_IMAGE_CONTRACT:
        if not target_contract_valid(value): return False
        base=dict(value);bounds=base['inputPixelBounds']
        base.update(schemaVersion=IMAGE_CONTRACT,
            inputGeometry={'width':bounds['right']-bounds['left'],'height':bounds['bottom']-bounds['top']},
            inputImageSha256=base['baseInputImageSha256'])
        return image_contract_valid(base)
    if (not isinstance(value,dict) or value.get('schemaVersion')!=IMAGE_CONTRACT
            or value.get('promptVersion') not in {'v6','v7','v8','v9','v10'} or value.get('selection') not in {'full_page','question_region'}
            or value.get('modelCoordinateFrame')!='input_image' or value.get('responseCoordinateFrame')!='original_page'):
        return False
    page=value.get('originalPageGeometry') or {};bounds=value.get('inputPixelBounds') or {};size=value.get('inputGeometry') or {}
    if not all(isinstance(part,dict) for part in (page,bounds,size)): return False
    width,height=page.get('width'),page.get('height')
    numbers=[width,height]+[bounds.get(key) for key in ('left','top','right','bottom')]
    if any(type(number) is not int for number in numbers): return False
    left,top,right,bottom=numbers[2:]
    if not (0<=left<right<=width and 0<=top<bottom<=height): return False
    if size!={'width':right-left,'height':bottom-top}: return False
    if value.get('inputWindow')!={'x':left/width,'y':top/height,'width':(right-left)/width,'height':(bottom-top)/height}: return False
    guard=value.get('contextGuard')
    if not isinstance(guard,dict) or any(guard.get(key)!=expected for key,expected in CONTEXT_GUARD.items()): return False
    if type(guard.get('geometryVerified')) is not bool or type(guard.get('questionWindowSuitable')) is not bool: return False
    region=valid_region(guard.get('sourceQuestionRegionInOriginalPage'))
    if guard.get('sourceQuestionRegionInOriginalPage') is not None and region is None: return False
    if guard['questionWindowSuitable']!=question_context_suitable(region,page): return False
    if value['selection']=='question_region':
        if not guard['geometryVerified'] or not guard['questionWindowSuitable'] or not region_contains(value['inputWindow'],region): return False
    elif (left,top,right,bottom)!=(0,0,width,height): return False
    structure=value.get('paperStructureContext')
    if structure is not None:
        if (not isinstance(structure,dict) or type(structure.get('geometryVerified')) is not bool
                or not isinstance(structure.get('sourceDigest'),str)
                or not re.fullmatch(r'[a-f0-9]{64}',structure['sourceDigest'])):return False
        context_region=valid_region(structure.get('regionInOriginalPage'))
        if structure.get('regionInOriginalPage') is not None and context_region is None:return False
        if value['selection']=='question_region' and (structure['geometryVerified'] is not True
                or not region_contains(region,context_region)):return False
    return all(isinstance(value.get(key),str) and re.fullmatch(r'[a-f0-9]{64}',value[key])
        for key in ('sourceImageSha256','inputImageSha256'))


def region_to_input(value,contract):
    """Omit cross-window hints instead of moving another question into view."""
    if contract.get('schemaVersion')==TARGET_IMAGE_CONTRACT:
        return region_to_target_input(value,contract)
    region=valid_region(value)
    if not region_contains(contract['inputWindow'],region): return None
    page=contract['originalPageGeometry'];box=contract['inputPixelBounds'];size=contract['inputGeometry']
    return valid_region({'x':max(0,(region['x']*page['width']-box['left'])/size['width']),
        'y':max(0,(region['y']*page['height']-box['top'])/size['height']),
        'width':region['width']*page['width']/size['width'],'height':region['height']*page['height']/size['height']})


def input_geometry_hints(value,contract):
    """Convert nested evidence geometry; remove unsupported pixel coordinates."""
    if isinstance(value,list):
        return [mapped for v in value for mapped in [input_geometry_hints(v,contract)] if mapped is not None]
    if not isinstance(value,dict): return value
    if set(value)=={'x','y','width','height'}: return region_to_input(value,contract)
    output={}
    for key,item in value.items():
        if re.search(r'position|coord|bounds|bbox',key,re.I): continue
        mapped=region_to_input(item,contract) if key in {'region','questionRegion','answerRegion'} else input_geometry_hints(item,contract)
        if mapped is not None: output[key]=mapped
    return output


def remap_image_response(text,contract):
    """Map model-local rectangles before the normal strict response parser.

    The immutable raw response journal stays in the model's actual input frame;
    only this derived parsing view uses the original page's display frame.
    """
    if not image_contract_valid(contract): raise ValueError('invalid teacher image contract')
    value=json.loads(text,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))
    if not isinstance(value,dict): raise ValueError('invalid response')
    def map_region(raw):
        if contract.get('schemaVersion')==TARGET_IMAGE_CONTRACT:
            return region_from_target_input(raw,contract)
        local=valid_region(raw)
        if local is None: raise ValueError('invalid input region')
        page=contract['originalPageGeometry'];box=contract['inputPixelBounds'];size=contract['inputGeometry']
        return crop_region({'x':(box['left']+local['x']*size['width'])/page['width'],
            'y':(box['top']+local['y']*size['height'])/page['height'],
            'width':local['width']*size['width']/page['width'],'height':local['height']*size['height']/page['height']})
    check=value.get('sourceCheck')
    if isinstance(check,dict) and 'questionRegion' in check: check['questionRegion']=map_region(check['questionRegion'])
    for step in value.get('steps') or []:
        if not isinstance(step,dict) or not isinstance(step.get('visual'),dict): continue
        image=step['visual']
        if 'region' in image: image['region']=map_region(image['region'])
        choices=image.get('choices')
        if isinstance(choices,list):
            for choice in choices:
                if isinstance(choice,dict) and 'region' in choice: choice['region']=map_region(choice['region'])
    return encoded(value)


def bounded_text(value,maximum,*,empty=False):
    if not isinstance(value,str) or len(value)>maximum or (not empty and not value.strip()):
        raise ValueError('invalid teaching text')
    value=value.strip()
    value.encode('utf-8',errors='strict')
    return value


def visual(value):
    if not isinstance(value,dict): raise ValueError('invalid visual')
    kind=value.get('kind')
    if kind=='paper_region':
        region=crop_region(value.get('region'))
        if region is None: raise ValueError('missing paper region')
        return {'kind':kind,'region':region}
    if kind=='quantity':
        count=value.get('count')
        if type(count) is not int or not 0<=count<=100: raise ValueError('invalid quantity')
        return {'kind':kind,'count':count}
    if kind=='groups':
        groups=value.get('groups')
        if not isinstance(groups,list) or not 2<=len(groups)<=5 or any(type(n) is not int or not 0<=n<=30 for n in groups) or sum(groups)>100:
            raise ValueError('invalid groups')
        return {'kind':kind,'groups':groups}
    if kind=='shapes':
        shapes=value.get('shapes')
        if not isinstance(shapes,list) or not 1<=len(shapes)<=5: raise ValueError('invalid shapes')
        clean=[]
        for shape in shapes:
            if not isinstance(shape,dict) or shape.get('shape') not in {'circle','square','triangle','rectangle'} or type(shape.get('count')) is not int or not 1<=shape['count']<=20:
                raise ValueError('invalid shape')
            color=shape.get('color','amber')
            if color not in {'amber','green','blue','red'}: raise ValueError('invalid color')
            clean.append({'shape':shape['shape'],'count':shape['count'],'color':color})
        return {'kind':kind,'shapes':clean}
    if kind=='choices':
        choices=value.get('choices')
        if not isinstance(choices,list) or not 2<=len(choices)<=4: raise ValueError('invalid picture choices')
        clean=[]
        for index,choice in enumerate(choices):
            if not isinstance(choice,dict): raise ValueError('invalid choice')
            region=crop_region(choice.get('region'))
            if region is None: raise ValueError('choice needs meaningful original picture')
            # IDs are locally generated. Model URLs/HTML/correct-choice flags
            # never become executable UI or reveal an answer through styling.
            clean.append({'id':f'choice-{index+1}','region':region,'label':bounded_text(choice.get('label',''),80,empty=True)})
        if len({encoded(c['region']) for c in clean})!=len(clean): raise ValueError('indistinguishable choices')
        return {'kind':kind,'choices':clean}
    raise ValueError('unknown visual')


def source_check(value, *, required=False):
    """Keep an explicit observation separate from the OCR and model solution."""
    if value is None:
        if required: raise ValueError('source check required')
        return None
    if not isinstance(value,dict) or value.get('status') not in {'matched','mismatch','unclear'}:
        raise ValueError('invalid source check')
    output={'status':value['status'],'reason':bounded_text(value.get('reason',''),300,empty=True)}
    for field,maximum in (('prompt',1800),('studentAnswer',1000)):
        if field in value:
            output[field]=bounded_text(value[field],maximum,empty=True)
    if 'basis' in value:
        if value['basis']!='original_image': raise ValueError('invalid source observation basis')
        output['basis']='original_image'
    for field in ('questionLocated','questionReadable','studentAnswerReadable','answerLocated'):
        if field in value:
            if type(value[field]) is not bool: raise ValueError('invalid source observation flag')
            output[field]=value[field]
    if 'answerOrdinal' in value:
        if type(value['answerOrdinal']) is not int or not 1<=value['answerOrdinal']<=200:
            raise ValueError('invalid source answer ordinal')
        output['answerOrdinal']=value['answerOrdinal']
    if 'questionRegion' in value:
        try:
            region=crop_region(value['questionRegion'])
        except (ApiError,ValueError,TypeError) as error:
            raise ValueError('invalid observed question region') from error
        if region is None: raise ValueError('missing observed question region')
        output['questionRegion']=region
    return output


def source_text(value):
    # Comparing source observations must not infer missing answers by solving.
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(value or '')))


def original_image_teachable(check):
    """An OCR mismatch does not make the independently observed paper unclear.

    These model observations permit bounded guidance only. They neither confirm
    the persisted transcription nor change a paper grade or mastery evidence.
    A bare 'matched' assertion cannot bypass an uncertain original receipt.
    """
    return bool(isinstance(check,dict) and check.get('basis')=='original_image'
        and check.get('questionLocated') is True and check.get('questionReadable') is True
        and isinstance(check.get('prompt'),str) and check['prompt'].strip()
        and not check['prompt'].strip().startswith(('请看原图','请根据这页原作文','请根据原图')))


def answer_target_located(check,result):
    if not original_image_teachable(check) or check.get('answerLocated') is not True:
        return False
    count=result.get('sourceAnswerCount',1)
    if type(count) is not int or not 1<=count<=200: return False
    if count>1:
        return check.get('answerOrdinal')==result.get('sourceAnswerOrdinal')
    return check.get('answerOrdinal',1)==result.get('sourceAnswerOrdinal',1)


def original_answer_observed(check,result):
    return bool(answer_target_located(check,result) and check.get('studentAnswerReadable') is True
        and 'studentAnswer' in check)


def observed_exact_reference(check):
    """Check arithmetic of an observed expression without certifying its OCR.

    The existing whitelist can calculate a reference even when its source stays
    pending. We deliberately do not pass confirmed=True or publish its result.
    """
    if not original_image_teachable(check): return None
    from services.homework_math import check_item
    from services.homework_service import POLICY as analysis_policy
    exact=check_item({'prompt':check['prompt'],'studentAnswer':'','type':'arithmetic',
        'confidence':0,'annotationAmbiguous':True,'recognitionNeedsConfirmation':True},
        grade='primary_1',subject='math',policy=analysis_policy)
    return {'method':'observed_arithmetic_guidance','expectedAnswer':exact['expectedAnswer']} if exact.get('method')=='decimal_arithmetic.v1' else None


def source_needs_confirmation(result):
    """Unknown confidence is never invented, including Tencent receipts."""
    if result.get('recognitionNeedsConfirmation') or result.get('annotationAmbiguous'):
        return True
    validation=result.get('sourceValidation') or {}
    if result.get('type')=='writing' and validation.get('provider')=='tencent' and validation.get('scope')=='guidance_only':
        # An essay prompt is a guidance placeholder, not an OCR transcription.
        # The teacher still must independently match the original image.
        return False
    if result.get('recognitionConfirmed') is True:
        return False
    if validation.get('provider')=='tencent':
        return not (validation.get('trusted') is True
            and all(validation.get(key) is True for key in
                ('strictIsCorrect','studentAnswerPresent','geometryVerified','angleVerified'))
            and validation.get('issues')==[])
    confidence=result.get('confidence')
    return type(confidence) not in {int,float} or not 0.98<=confidence<=1


def trusted_exact_reference(result):
    """Share the local arithmetic reference across legacy and Tencent flows.

    Provider grading itself is not a deterministic reference. A Tencent result
    needs independently validated source evidence and a consistent local check.
    """
    if source_needs_confirmation(result):
        return None
    expected=result.get('expectedAnswer')
    if expected is None or type(expected) not in {str,int,float}:
        return None
    try:
        numeric=Decimal(str(expected))
        if not numeric.is_finite():
            return None
    except InvalidOperation:
        return None
    if result.get('method')=='decimal_arithmetic.v1':
        return {'method':'decimal_arithmetic.v1','expectedAnswer':str(expected)}
    validation=result.get('sourceValidation') or {}
    exact=result.get('deterministicValidation') or {}
    if (result.get('method')!='tencent_question.v1'
            or validation.get('provider')!='tencent' or validation.get('trusted') is not True
            or result.get('correctionMethod')!='decimal_arithmetic.v1'
            or exact.get('method')!='decimal_arithmetic.v1'):
        return None
    try:
        checked=exact.get('expectedAnswer')
        if type(checked) not in {str,int,float} or Decimal(str(checked))!=numeric:
            return None
        # The raw Tencent reference remains separate, and may use equivalent
        # numeric formatting. A contradiction cannot be silently overwritten.
        raw_answer=(result.get('tencentRaw') or {}).get('answer') or {}
        provider_reference=raw_answer.get('RightAnswer')
        if provider_reference is not None and Decimal(str(provider_reference))!=numeric:
            return None
    except (InvalidOperation,TypeError,ValueError):
        return None
    return {'method':'decimal_arithmetic.v1','expectedAnswer':str(expected)}


def exact_reference_conflict(value, reference):
    if reference is None:
        return False
    supplied=(value.get('assessment') or {}).get('expectedAnswer','')
    if isinstance(supplied,str) and re.fullmatch(r'[+\-]?(?:\d+(?:\.\d*)?|\.\d+)',supplied):
        return Decimal(supplied)!=Decimal(reference['expectedAnswer'])
    return False


def invalid_hybrid_reference(result, reference):
    return (result.get('method')=='tencent_question.v1'
        and (result.get('correctionMethod')=='decimal_arithmetic.v1'
            or (result.get('deterministicValidation') or {}).get('method')=='decimal_arithmetic.v1')
        and reference is None)


def illustrative_visual_supported(image, *, result, teacher, step_text):
    """Generated number groups encode addition, never removal or fractions.

    With no verified diagram contract for these meanings, keep the source photo
    rather than rendering a plausible but mathematically misleading picture.
    """
    kind=image.get('kind')
    if kind not in {'quantity','groups','shapes'}:
        return True
    text=unicodedata.normalize('NFKC',' '.join(str(value or '') for value in
        (result.get('prompt'),teacher,step_text)))
    fraction=bool(re.search(r'\d\s*/\s*\d|分之|分数|百分|半个|一半',text))
    if fraction:
        return False
    if kind!='groups':
        return True
    subtraction=bool(re.search(r'\d\s*[-−]\s*\d|减|拿走|取走|去掉|还剩|剩下|剩余|相差|少了',text))
    if subtraction:
        return False
    addition=re.fullmatch(r'\s*(\d{1,2})\s*\+\s*(\d{1,2})\s*(?:=\s*(?:[?？□]|\d+)?)?\s*',
        unicodedata.normalize('NFKC',str(result.get('prompt') or '')))
    if addition and sorted(image.get('groups') or [])!=sorted([int(addition[1]),int(addition[2])]):
        return False
    # A group visual cannot be used as a generic diagram for geometry, time,
    # multiplication or an unspecified task. Retain it for addition/classifying.
    return bool(re.search(r'\d\s*\+\s*\d|加法|加起来|合起来|一共|总共|总数|分类|分组|归类|两组|一组|第一组',text))


def confirmation_view(value, reason):
    """Use a neutral source-check step instead of uncertain answer narration.

    A historical audio receipt describes the historical text. It must never be
    paired with this replacement guidance, or remain playable by direct URL.
    """
    output=dict(value)
    output.pop('teachingScope',None)
    teacher='我们先看原来的作业照片，找到这道小题和你写的答案。看不清的空格先不猜，核对清楚后再一起解题。'
    steps=[{'id':'step-1','text':'看原照片，找到题目，再指一指你写的答案。',
        'visual':{'kind':'paper_region','region':{'x':0.0,'y':0.0,'width':1.0,'height':1.0}}}]
    check=value.get('sourceCheck') or {}
    if check.get('basis')=='original_image' and not original_image_teachable(check):
        # The teacher identified a concrete source limitation. Give the child
        # that location/reason, rather than asking a parent to repair the OCR.
        limitation=str(check.get('reason') or '当前小题的位置或题目条件还看不清。')[:300]
        teacher='老师还没有看清这道原题。'+limitation+'请指出当前小题，或重新拍清这个位置，我们再一起讲。'
        region=check.get('questionRegion') if check.get('questionLocated') is True else None
        steps=[{'id':'step-1','text':'指一指当前小题；被遮住或拍糊的条件需要拍清楚，先不猜答案。',
            'visual':{'kind':'paper_region','region':region or {'x':0.0,'y':0.0,'width':1.0,'height':1.0}}}]
    safe_narration=(value.get('sourceConfirmationOnly') is True and value.get('teacherText')==teacher
        and value.get('steps')==steps and not (value.get('assessment') or {}).get('expectedAnswer'))
    output.update(teacherText=teacher,steps=steps,sourceConfirmationOnly=True,
        reviewState='required',reviewRetryAllowed=False,reviewReasonCode='source_unconfirmed')
    output['assessment']={'status':'needs_confirmation','reason':reason[:300],'expectedAnswer':'',
        'method':'ai_guidance','countsForAbility':False,'independent':None}
    if not safe_narration and (value.get('status')=='ready' or 'audio' in value):
        output['audio']={'status':'unavailable','errorCode':'homework_tutor_source_unconfirmed'}
    return output


def image_review_view(value):
    """Stop replaying observations without the current image-context safeguards.

    This only changes the read projection. The original paid text, raw response,
    audio receipts and paper grade stay intact, and reading never dispatches AI.
    """
    output=dict(value)
    output.pop('teachingScope',None)
    reason='老师需要放大原题再看。'
    output.update(teacherText=reason+'先看清图中的小字、人物和题目条件，再一起讲解。',
        sourceCheck={'status':'unclear','reason':reason},sourceConfirmationOnly=True,
        sourceImageReviewRequired=True,reviewState='required',reviewRetryAllowed=False,
        reviewReasonCode='image_input_unverified',
        steps=[{'id':'step-1','text':reason,'visual':{'kind':'paper_region',
            'region':{'x':0.0,'y':0.0,'width':1.0,'height':1.0}}}],
        assessment={'status':'needs_confirmation','reason':reason,'expectedAnswer':'',
            'method':'ai_guidance','countsForAbility':False,'independent':None},
        audio={'status':'unavailable','errorCode':'homework_tutor_source_unconfirmed'})
    return output


def answer_quality_view(value, quality):
    """Withdraw unsupported teaching on every read, including historical audio.

    The paid provider receipt is immutable. This projection exposes only an
    answer-free instruction and cannot trigger a new provider or voice call.
    """
    output=dict(value)
    output.pop('teachingScope',None)
    output.pop('gradingReferenceComparison',None)
    reason='这道题的答案还没有核实，讲解已暂停。请先回到原作业查看，不能用同一张照片反复核实。'
    output.update(teacherText=reason,sourceConfirmationOnly=True,sourceImageReviewRequired=True,
        reviewState='required',reviewRetryAllowed=False,reviewReasonCode=quality['method'],
        sourceCheck={'status':'unclear','reason':reason},
        steps=[{'id':'step-1','text':'看看原来的题目图片，暂时不猜答案。',
            'visual':{'kind':'paper_region','region':{'x':0.0,'y':0.0,'width':1.0,'height':1.0}}}],
        assessment={'status':'needs_confirmation','reason':reason,'expectedAnswer':'',
            'method':'ai_guidance','countsForAbility':False,'independent':None},
        teachingQuality=quality,
        audio={'status':'unavailable','errorCode':'homework_tutor_source_unconfirmed'})
    return output


def teaching_view(value, result, *, enforce_quality=True):
    """Drop invented/cross-question clickable choices in both new and old turns.

    This is a read projection: stored paid receipts/history remain unchanged.
    An independent image observation may teach a clear question even while its
    saved paper grade remains pending. Missing choice geometry still cannot be
    turned into answer buttons or independent assessment evidence.
    """
    output=dict(value)
    # Image review is a terminal teaching outcome, not permission to charge for
    # another look. Only the service can prove a changed source/request scope.
    output.update(reviewState='not_required',reviewRetryAllowed=False)
    output.pop('reviewReasonCode',None)
    if enforce_quality:
        quality=teaching_quality(value,result)
        output['teachingQuality']=quality
        if (value.get('status')=='ready' or value.get('assessment') is not None) and quality.get('status') not in {'verified','guidance'}:
            return answer_quality_view(output,quality)
        if quality.get('status')=='guidance':
            # The persisted primary is already strictly parsed and bounded.
            # Do not mutate its content again: the durable blind-review digest
            # must remain identical on GET, speech and history projections.
            output.update(sourceImageReviewRequired=False,sourceConfirmationOnly=False,
                teachingScope='original_image_guidance')
            return output
        if quality.get('status')=='verified' and value.get('teachingSource')=='operator_reviewed_lesson':
            # The quality module compares the exact server-authored lesson and
            # its owned review digest, rather than trusting a model's tags.
            return output
    has_image_contract=image_contract_valid(value.get('sourceImageContract'))
    raw_check=value.get('sourceCheck') or {}
    old_image_turn=(isinstance(raw_check,dict) and raw_check.get('basis')=='original_image'
        or value.get('teachingScope')=='original_image_guidance' or value.get('sourceConfirmationOnly') is True
        or value.get('sourceImageReviewRequired') is True)
    if value.get('status')=='ready' and old_image_turn and not has_image_contract:
        return image_review_view(output)
    if has_image_contract or value.get('status')!='ready':
        output['sourceImageReviewRequired']=False
    if value.get('assessment') is None:
        if value.get('status')=='ready':
            return confirmation_view(output,'这次旧讲解缺少完整原图核验结果，不能据此评价作答。')
        # Queued/working/failed turns do not yet contain a model assessment.
        # Never manufacture a partial assessment merely because mode=explain;
        # its missing status/reason/expectedAnswer breaks the public contract.
        output.update(assessment=None,
            teacherText=value.get('teacherText') if isinstance(value.get('teacherText'),str) else '',
            steps=value.get('steps') if isinstance(value.get('steps'),list) else [])
        return output
    try:
        check=source_check(value.get('sourceCheck'))
    except (ValueError,TypeError,UnicodeError):
        check=None
    if check is not None: output['sourceCheck']=check
    else: output.pop('sourceCheck',None)
    if value.get('sourceConfirmationOnly') is True:
        return confirmation_view(output,str((value.get('assessment') or {}).get('reason') or '原题或原作答尚需核对。'))
    legacy=value.get('status')=='ready' and check is None
    image_teaching=original_image_teachable(check)
    source_unconfirmed=isinstance(check,dict) and (check.get('status')!='matched'
        or check.get('basis')=='original_image' and not image_teaching)
    observation_differs=bool(check and any(field in check and original in result
        and source_text(check[field])!=source_text(result[original])
        for field,original in (('prompt','prompt'),('studentAnswer','studentAnswer'))))
    reference=trusted_exact_reference(result)
    # A computation based on a different OCR expression is not authoritative
    # over the newly observed paper. Guard the actual observed expression too,
    # without turning its AI transcription into a verified ability reference.
    observed_reference=observed_exact_reference(check) if image_teaching else None
    active_reference=observed_reference or (reference if not observation_differs else None)
    if invalid_hybrid_reference(result,reference) and not image_teaching:
        return confirmation_view(output,'保存的题目来源与算式参考尚未一致，请核对原题。')
    if exact_reference_conflict(value,active_reference):
        reason='老师参考答案与这个算式的确定计算结果不同，需要重新核对解题过程。'
        output['sourceCheck']={**(check or {}),'status':'mismatch','reason':reason}
        return confirmation_view(output,reason)
    uncertain=source_needs_confirmation(result)
    uncertain=uncertain and (value.get('status')=='ready' or value.get('assessment') is not None)
    if legacy or (source_unconfirmed or uncertain) and not image_teaching:
        reason='这次旧讲解尚未独立核对原图，请先核对题目和原作答。' if legacy else '原题或原作答尚需核对。'
        if source_unconfirmed:
            reason+=str(check.get('reason') or '')
        return confirmation_view(output,reason)
    if image_teaching:
        output['teachingScope']='original_image_guidance'
        assessment=dict(output.get('assessment') or {})
        assessment.update(status='guidance_only',method='ai_guidance',countsForAbility=False,independent=None,
            feedbackTarget='current_student_message' if value.get('mode')=='answer' and str(value.get('message') or '').strip() and answer_target_located(check,result) else 'original_question',
            originalAnswerObserved=original_answer_observed(check,result))
        assessment.pop('verifiedReferenceAnswer',None)
        output['assessment']=assessment
        # Illustrations must match what was actually observed, not a stale OCR
        # expression from the independent grading pipeline.
        teaching_result={**result,'prompt':check['prompt']}
    else:
        teaching_result=result
    try:
        question_region=crop_region(check.get('questionRegion') if image_teaching and check.get('questionRegion') else result.get('region'))
    except (ApiError,ValueError,TypeError):
        question_region=None
    steps=[]
    downgraded=False
    for step in value.get('steps') or []:
        clean=dict(step)
        image=step.get('visual') or {}
        if not illustrative_visual_supported(image,result=teaching_result,teacher=value.get('teacherText'),step_text=step.get('text')):
            downgraded=True
            clean['visual']={'kind':'paper_region','region':question_region or {'x':0.0,'y':0.0,'width':1.0,'height':1.0}}
        if image.get('kind')=='choices':
            trustworthy=result.get('type')=='choice' and question_region is not None and not source_needs_confirmation(result)
            choices=image.get('choices')
            if not isinstance(choices,list) or not 2<=len(choices)<=4:
                trustworthy=False
            if trustworthy:
                for choice in choices:
                    try:
                        region=crop_region(choice.get('region'))
                    except (ApiError,ValueError,TypeError,AttributeError):
                        region=None
                    if (region is None or region['x']<question_region['x']-1e-6
                            or region['y']<question_region['y']-1e-6
                            or region['x']+region['width']>question_region['x']+question_region['width']+1e-6
                            or region['y']+region['height']>question_region['y']+question_region['height']+1e-6):
                        trustworthy=False
                        break
            if not trustworthy:
                downgraded=True
                clean['visual']={'kind':'paper_region','region':question_region or {'x':0.0,'y':0.0,'width':1.0,'height':1.0}}
        steps.append(clean)
    output['steps']=steps
    if downgraded:
        assessment=dict(output.get('assessment') or {})
        if not image_teaching and (question_region is None or assessment.get('status')=='needs_confirmation'):
            assessment['status']='needs_confirmation'
        else:
            assessment['status']='guidance_only'
        assessment.update(method='ai_guidance',countsForAbility=False,independent=None)
        note='本步骤改用原题图片核对，只作讲解。'
        if question_region is None:
            note='原题位置尚未核实，请先看原图，本步骤不能作为图片选择测验。'
        assessment['reason']=(note+str(assessment.get('reason') or ''))[:300]
        output['assessment']=assessment
    if value.get('mode') in {'explain','followup'} or result.get('type')=='writing':
        assessment=dict(output.get('assessment') or {})
        if assessment.get('status') in {'correct','incorrect'}:
            assessment['status']='guidance_only'
            assessment['reason']=('这是老师讲解或追问，未评估新的独立作答。'+str(assessment.get('reason') or ''))[:300]
        assessment.update(method='ai_guidance',countsForAbility=False,independent=None)
        if result.get('type')=='writing':
            assessment['expectedAnswer']=''
            assessment.pop('verifiedReferenceAnswer',None)
        output['assessment']=assessment
    return output


def published_reply_view(value, result):
    """Apply the complete ready-source gate before exposing an early reply.

    The worker marker controls timing, never answer authority. A changed source
    withdraws text even when it was already shown or voice generation failed.
    """
    actual_status=value.get('status')
    published=value.get('replyReady') is True
    candidate={**value,'status':'ready'} if published and actual_status in {'working','unknown','failed'} else value
    output=teaching_view(candidate,result)
    output['status']=actual_status
    output['replyReady']=bool((published or actual_status=='ready')
        and output.get('teachingQuality',{}).get('status') in {'verified','guidance'}
        and output.get('reviewState')!='required'
        and isinstance(output.get('teacherText'),str) and output['teacherText'].strip()
        and output.get('steps'))
    return output


def parse_response(text,*,policy,result,mode=None,student_message=None,fixed_reference=None):
    value=json.loads(text,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))
    if not isinstance(value,dict): raise ValueError('invalid response')
    check=source_check(value.get('sourceCheck'),required=policy.get('requireSourceCheck',policy.get('prompt',{}).get('version') in {'v3','v4','v5','v6'}))
    if check and check['status']=='matched':
        for field,original in (('prompt','prompt'),('studentAnswer','studentAnswer')):
            if result.get('type')!='writing' and field in check and original in result and source_text(check[field])!=source_text(result[original]):
                check['status']='mismatch'
                check['reason']='原图观察与已保存的题目或原作答不同。'+check['reason']
                check['reason']=check['reason'][:300]
                break
    teacher=bounded_text(value.get('teacherText'),policy['maximumTeacherCharacters'])
    assessment=value.get('assessment')
    if not isinstance(assessment,dict) or assessment.get('status') not in {'correct','incorrect','needs_confirmation','guidance_only'}:
        raise ValueError('invalid assessment')
    assessment={
        'status':assessment['status'],'reason':bounded_text(assessment.get('reason',''),300,empty=True),
        'expectedAnswer':bounded_text(assessment.get('expectedAnswer',''),1000,empty=True),
        'method':'ai_guidance','countsForAbility':False,'independent':None,
    }
    image_teaching=original_image_teachable(check)
    # A clear independent image observation permits teaching, not confirmation
    # of the old OCR or an automatic update of the original paper grade.
    uncertain=(source_needs_confirmation(result) or check is not None and (check['status']!='matched'
        or check.get('basis')=='original_image' and not image_teaching)) and not image_teaching
    reference=trusted_exact_reference(result)
    if invalid_hybrid_reference(result,reference) and not image_teaching:
        uncertain=True
        check={**(check or {}),'status':'unclear','reason':'保存的题目来源与算式参考尚未一致，请核对原题。'}
    if not uncertain and not image_teaching and reference is not None:
        if exact_reference_conflict({'assessment':assessment},reference):
            uncertain=True
            check={**(check or {}),'status':'mismatch','reason':'原图解答与已保存算式的计算结果不一致，需要核对题目识别。'}
        if not uncertain: assessment['verifiedReferenceAnswer']=reference['expectedAnswer']
    steps=value.get('steps')
    if not isinstance(steps,list) or not 1<=len(steps)<=policy['maximumSteps']: raise ValueError('invalid steps')
    clean=[]
    for index,step in enumerate(steps):
        if not isinstance(step,dict): raise ValueError('invalid step')
        clean.append({'id':f'step-{index+1}','text':bounded_text(step.get('text'),160),'visual':visual(step.get('visual'))})
    reply={'teacherText':teacher,'steps':clean,'assessment':assessment}
    if mode is not None: reply['mode']=mode
    if student_message is not None: reply['message']=student_message
    if check is not None: reply['sourceCheck']=check
    if fixed_reference is not None:
        if not grounded_followup(reply,result,fixed_reference):raise ValueError('reference followup conflict')
        # This branch copies no provider claim of source verification or grade.
        reply.update(teachingSource=REFERENCE_FOLLOWUP_SOURCE,referenceDigest=fixed_reference['digest'],
            sourceCheck={'status':'matched','reason':'仅解释当前小题已有解析，不是新的图像核实。'})
        reply['assessment'].update(status='guidance_only',reason='按已有解析回答本轮问题，不作为独立掌握证据。')
        return reply
    if uncertain: reply=confirmation_view(reply,'原题或原作答尚需核对。'+str((check or {}).get('reason') or ''))
    # The durable worker attaches the exact image contract before enforcing
    # answer quality. Parsing alone never publishes text or audio to a child.
    return teaching_view(reply,result,enforce_quality=False)


class HomeworkTutorService:
    def __init__(self,homework,*,policy=None):
        self.host=homework
        self.policy=policy or POLICY

    def available(self,row,result):
        return bool(self.host.enabled and self.host.processing_enabled and row['source'] in {'parent_app','document_camera'} and row['consent_at'] and result.get('prompt'))

    def _owned(self,conn,principal,identity,item_id,revision=None,*,lock=False):
        host=self.host
        row=host.repository.submission(conn,principal['family_id'],identity,child=principal['child_id'],lock=lock)
        item=host._item(conn,identity,item_id)
        if revision is not None and (type(revision) is not int or revision!=item['revision']):
            raise ApiError('homework_revision_conflict','题目已更新，请刷新后再问老师',409)
        if not self.available(row,parsed(item['result_json'],{})):
            raise ApiError('homework_tutor_unavailable','这份作业暂不能进行老师讲解',409)
        return row,item

    def _turns(self,conn,row,item):
        records=conn.execute('SELECT * FROM homework_actions WHERE submission_id=? AND item_id=? ORDER BY created_at,id',(row['id'],item['id'])).fetchall()
        return sorted([(dict(record),parsed(record['result_json'],{})) for record in records
            if parsed(record['result_json'],{}).get('schemaVersion')==SCHEMA
            and parsed(record['result_json'],{}).get('itemRevision')==item['revision']
            and parsed(record['result_json'],{}).get('submissionRevision')==row['revision']],key=lambda pair:(pair[1].get('ordinal',0),pair[1]['createdAt'],pair[1]['id']))

    def _result(self,conn,row,item,result=None):
        if result is not None:
            result=dict(result)
            result['_confirmedGuidanceReviews']=({} if reference_for_correction(result) is not None
                else read_confirmed_reviews(self.host,conn,row,item,result))
            result['_confirmedTencentReferenceTurns']=self._reference_turn_proofs(conn,row,item,result)
            return result
        page=conn.execute('SELECT * FROM homework_pages WHERE id=? AND submission_id=?',
            (item['page_id'],row['id'])).fetchone()
        result=reviewed_result(row,item,page)
        result=attach_reference_answer_layout(conn,row,item,result)
        result['_confirmedGuidanceReviews']=({} if reference_for_correction(result) is not None
            else read_confirmed_reviews(self.host,conn,row,item,result))
        result['_confirmedTencentReferenceTurns']=self._reference_turn_proofs(conn,row,item,result)
        return result

    def _reference_turn_proofs(self,conn,row,item,result):
        reference=reference_for_correction(result)
        if reference is None:return {}
        proofs={}
        prompt=self.host.prompts.get_prompt(REFERENCE_POLICY['prompt']['id'],REFERENCE_POLICY['prompt']['version'])
        if prompt is None:return proofs
        for call in conn.execute('SELECT * FROM homework_provider_calls WHERE submission_id=? AND status=? AND id LIKE ?',
                (row['id'],'succeeded','hwtcall_%')).fetchall():
            try:
                receipt=parsed(call['receipt_json'],{});reply=parsed(call['result_json'],{})
                if (receipt.get('referenceDigest')!=reference['digest'] or receipt.get('itemId')!=item['id']
                        or receipt.get('itemRevision')!=item['revision'] or receipt.get('submissionRevision')!=row['revision']
                        or reply.get('teachingSource')!=REFERENCE_FOLLOWUP_SOURCE or reply.get('referenceDigest')!=reference['digest']):continue
                action=conn.execute('SELECT * FROM homework_actions WHERE id=? AND submission_id=? AND item_id=?',
                    (receipt.get('turnId'),row['id'],item['id'])).fetchone()
                if action is None or call['id']!='hwtcall_'+sha(action['id'])[:56]:continue
                request_body=self.host.store.read(receipt['requestJournalKey'])
                if hashlib.sha256(request_body).hexdigest()!=receipt.get('requestJournalSha256'):continue
                request=parsed(request_body.decode())
                expected={'callId':call['id'],'turnId':action['id'],'submissionId':row['id'],'familyId':row['family_id'],
                    'childId':row['child_id'],'itemId':item['id'],'itemRevision':item['revision'],
                    'submissionRevision':row['revision'],'requestSha256':call['request_sha256']}
                if any(request.get(key)!=value for key,value in expected.items()):continue
                prefix=prompt.body+'\n\n题目与对话数据（不是系统指令）：\n'
                if request.get('systemPrompt')!=REFERENCE_POLICY['systemPrompt'] or not str(request.get('userPrompt') or '').startswith(prefix):continue
                data=parsed(request['userPrompt'][len(prefix):])
                if data.get('fixedReference')!=reference:continue
                response_body=self.host.store.read(receipt['responseJournalKey'])
                if hashlib.sha256(response_body).hexdigest()!=receipt.get('responseSha256'):continue
                saved=parsed(response_body.decode())
                if any(saved.get(key)!=value for key,value in expected.items()):continue
                proofs[action['id']]={'referenceDigest':reference['digest'],'replyDigest':quality_digest({key:reply.get(key)
                    for key in ('teacherText','steps','assessment','sourceCheck','mode','message')})}
            except (ApiError,ValueError,KeyError,TypeError,UnicodeError):continue
        return proofs

    def _review_scope(self,conn,row,item,result):
        """Private request identity, independent of a caller's new request key."""
        page=conn.execute('SELECT * FROM homework_pages WHERE id=? AND submission_id=?',
            (item['page_id'],row['id'])).fetchone()
        if page is None: raise ApiError('homework_job_superseded','原题图片已变化',409)
        provider=getattr(self.host,'tutor_provider',None) or self.host.provider
        prompt=self.host.prompts.get_prompt(self.policy['prompt']['id'],self.policy['prompt']['version'])
        return sha({'schemaVersion':REVIEW_SCOPE_SCHEMA,'submissionRevision':row['revision'],
            'itemId':item['id'],'itemRevision':item['revision'],'result':{key:value for key,value in result.items() if key not in {'_confirmedGuidanceReviews','_confirmedTencentReferenceTurns'}},
            'pageId':page['id'],'imageSha256':page['content_sha256'],
            'rotation':page['rotation'],'crop':parsed(page['crop_json']),
            'prompt':{'id':self.policy['prompt']['id'],'version':self.policy['prompt']['version'],
                'body':prompt.body if prompt else None},'policy':self.policy,
            'qualityImplementation':QUALITY_IMPLEMENTATION_SHA256,
            'reviewImplementation':REVIEW_IMPLEMENTATION_SHA256,
            'sourceReviewImplementation':hashlib.sha256((ROOT/'services/homework_source_review.py').read_bytes()).hexdigest(),
            'targetImplementation':hashlib.sha256((ROOT/'services/homework_tutor_image_target.py').read_bytes()).hexdigest(),
            'sourceReviewPolicy':SOURCE_REVIEW_POLICY,
            'provider':getattr(provider,'provider_name',None),'model':getattr(provider,'model_name',None),
            'providerConfiguration':{name:getattr(provider,name,None) for name in
                ('base_url','max_bytes','max_image_dimension','jpeg_quality','timeout_seconds',
                    'json_output','disable_thinking','capture_received_response')}})

    def _legacy_review_scope(self,conn,row,item,turn,result,source_cache=None):
        """Prove an old request used the current source, prompt and provider.

        No missing receipt authorizes another paid call. An explicit difference
        can allow a new request, but unknown transport state remains separate.
        """
        old_contract=turn.get('sourceImageContract')
        if not isinstance(old_contract,dict): return 'unavailable'
        if old_contract.get('schemaVersion') not in {IMAGE_CONTRACT,TARGET_IMAGE_CONTRACT} or old_contract.get('promptVersion')!=self.policy['prompt']['version']:
            return 'changed'
        if source_cache is not None and 'source' in source_cache:
            image,contract=source_cache['source']
        else:
            page=conn.execute('SELECT * FROM homework_pages WHERE id=? AND submission_id=?',
                (item['page_id'],row['id'])).fetchone()
            if page is None: return 'unavailable'
            image,photo=transformed_image(self.host.store.read(page['storage_key']),page['rotation'],parsed(page['crop_json']))
            from services.homework_paper_structure import selected_item_context
            context=selected_item_context(self.host,conn,row,item)
            image,contract=teacher_input_image(image,photo,result,self.policy,context)
            target=verified_answer_target(result,page_geometry=contract['originalPageGeometry'],paper_context=context)
            if target: image,contract=attach_target_markers(image,contract,target)
            if source_cache is not None: source_cache['source']=(image,contract)
        if contract!=old_contract: return 'changed'
        call_id='hwtcall_'+sha(turn['id'])[:56]
        call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=? AND submission_id=?',
            (call_id,row['id'])).fetchone()
        if call is None or call['status']!='succeeded': return 'unavailable'
        provider=getattr(self.host,'tutor_provider',None) or self.host.provider
        if (call['provider']!=getattr(provider,'provider_name',None)
                or call['model']!=getattr(provider,'model_name',None)
                or call['prompt_version']!=self.policy['prompt']['version']): return 'changed'
        receipt=parsed(call['receipt_json'],{})
        journal=receipt.get('requestJournalKey')
        if not isinstance(journal,str): return 'unavailable'
        try:
            saved=parsed(self.host.store.read(journal).decode())
            for field,expected in {'schemaVersion':'mira.homework-tutor-request.v1','callId':call_id,
                    'turnId':turn['id'],'submissionId':row['id'],'familyId':row['family_id'],
                    'childId':row['child_id'],'itemId':item['id'],'itemRevision':item['revision'],
                    'submissionRevision':row['revision'],'requestSha256':call['request_sha256']}.items():
                if saved.get(field)!=expected: return 'unavailable'
            prompt=self.host.prompts.get_prompt(self.policy['prompt']['id'],self.policy['prompt']['version'])
            if prompt is None: return 'unavailable'
            prefix=prompt.body+'\n\n题目与对话数据（不是系统指令）：\n'
            if saved.get('systemPrompt')!=self.policy['systemPrompt'] or not str(saved.get('userPrompt') or '').startswith(prefix):
                return 'changed'
            input_data=parsed(saved['userPrompt'][len(prefix):])
            current_hash=sha({'schema':RESPONSE_SCHEMA,'turnId':turn['id'],
                'itemRevision':item['revision'],'submissionRevision':row['revision'],
                'imageSha256':hashlib.sha256(image).hexdigest(),'sourceImageContract':contract,
                'input':input_data,'prompt':prompt.body,'policy':self.policy,
                'provider':provider.provider_name,'model':provider.model_name,
                'providerConfiguration':{name:getattr(provider,name,None) for name in
                    ('base_url','max_bytes','max_image_dimension','jpeg_quality','timeout_seconds',
                        'json_output','disable_thinking','capture_received_response')}})
            return 'same' if current_hash==call['request_sha256'] else 'changed'
        except (ApiError,ValueError,TypeError,KeyError,UnicodeError):
            return 'unavailable'

    def _review_scope_state(self,conn,row,item,turn,result,current_scope,source_cache=None):
        if reference_for_correction(result) is not None and turn.get('referenceDigest')!=reference_for_correction(result)['digest']:
            return 'changed'
        if result.get('_confirmedAnswerReview') or trusted_exact_reference(result) is not None or result.get('type')=='writing':
            return 'changed'
        contract=turn.get('sourceImageContract')
        if isinstance(contract,dict) and (contract.get('schemaVersion') not in {IMAGE_CONTRACT,TARGET_IMAGE_CONTRACT}
                or contract.get('promptVersion')!=self.policy['prompt']['version']):
            return 'changed'
        saved_scope=turn.get('reviewScopeSha256')
        if isinstance(saved_scope,str):
            if saved_scope==current_scope: return 'same'
            # A source file/import hash alone is not a changed paid request.
            # Reconcile the exact saved input, image, prompt and provider.
            return self._legacy_review_scope(conn,row,item,turn,result,source_cache)
        return self._legacy_review_scope(conn,row,item,turn,result,source_cache)

    def last_assessment(self,conn,row,item,*,result=None):
        values=[turn for _,turn in self._turns(conn,row,item) if turn.get('status')=='ready']
        return teaching_view(values[-1],self._result(conn,row,item,result)).get('assessment') if values else None

    def summary(self,conn,row):
        records=conn.execute('SELECT item_id,result_json FROM homework_actions WHERE submission_id=?',(row['id'],)).fetchall()
        items={item['id']:item for item in self.host.repository.items(conn,row['id'])}
        turns=[]
        for record in records:
            turn=parsed(record['result_json'],{})
            if turn.get('schemaVersion')!=SCHEMA or turn.get('submissionRevision')!=row['revision'] or turn.get('status')=='revoked': continue
            item=items.get(record['item_id'])
            if item and turn.get('itemRevision')==item['revision']:
                turn=teaching_view(turn,self._result(conn,row,item))
            turns.append(turn)
        return {'questionCount':sum(bool(parsed(i['result_json'],{}).get('prompt')) for i in items.values()),
            'turnCount':len(turns),
            'readyTurnCount':sum(t.get('status')=='ready' and t.get('reviewState')!='required' for t in turns),
            'reviewRequiredTurnCount':sum(t.get('status')=='ready' and t.get('reviewState')=='required' for t in turns),
            'needsConfirmationCount':sum(t.get('assessment',{}).get('status')=='needs_confirmation' for t in turns if t.get('assessment'))}

    def _view(self,conn,row,item,*,result=None):
        turns=[]
        result=self._result(conn,row,item,result)
        current_scope=None
        source_cache={}
        for record,turn in self._turns(conn,row,item):
            raw_turn=turn
            turn=published_reply_view(turn,result)
            if turn.get('status')=='ready' and turn.get('reviewState')=='required':
                if current_scope is None: current_scope=self._review_scope(conn,row,item,result)
                turn['reviewRetryAllowed']=self._review_scope_state(conn,row,item,raw_turn,result,current_scope,source_cache)=='changed'
            public={key:turn.get(key) for key in ('id','mode','message','status','replyReady','teacherText','steps','assessment','errorCode','createdAt')}
            public['teacherText']=turn.get('teacherText') if isinstance(turn.get('teacherText'),str) else ''
            public['steps']=turn.get('steps') if isinstance(turn.get('steps'),list) else []
            if turn.get('sourceCheck') is not None: public['sourceCheck']=turn['sourceCheck']
            if turn.get('gradingReferenceComparison') is not None:
                public['gradingReferenceComparison']=turn['gradingReferenceComparison']
            if turn.get('teachingQuality') is not None:
                public['teachingQuality']=turn['teachingQuality']
            if turn.get('teachingScope') is not None: public['teachingScope']=turn['teachingScope']
            if type(turn.get('sourceConfirmationOnly')) is bool:
                public['sourceConfirmationOnly']=turn['sourceConfirmationOnly']
            if type(turn.get('sourceImageReviewRequired')) is bool:
                public['sourceImageReviewRequired']=turn['sourceImageReviewRequired']
            public['reviewRetryAllowed']=turn.get('reviewRetryAllowed') is True
            public['reviewState']=turn.get('reviewState','not_required')
            if turn.get('reviewState')=='required': public['reviewReasonCode']=turn['reviewReasonCode']
            feedback_target=(turn.get('assessment') or {}).get('feedbackTarget')
            if feedback_target in {'original_question','current_student_message'}:
                public['feedbackTarget']=feedback_target
            # This owned request identity, not message text or client clock,
            # reconciles a lost POST response and repeated identical questions.
            public['requestKey']=record['idempotency_key']
            media=turn.get('audio',{})
            public['audio']={'status':media.get('status','pending'),'errorCode':media.get('errorCode')}
            if media.get('status')=='ready':
                public['audio']['assetUrl']=f'/api/v2/student/learning/homework/{row["id"]}/items/{item["id"]}/tutor/{turn["id"]}/audio'
            turns.append(public)
        actions=conn.execute('SELECT result_json FROM homework_actions WHERE submission_id=?',(row['id'],)).fetchall()
        reserved=sum(parsed(action['result_json'],{}).get('callBudget',1) for action in actions
            if parsed(action['result_json'],{}).get('schemaVersion')==SCHEMA)
        dispatched=conn.execute('SELECT COUNT(*) n FROM homework_provider_calls WHERE submission_id=? AND id LIKE ?',
            (row['id'],'hwtcall_%')).fetchone()['n']
        from services.homework_correction import correction_view
        return {'ok':True,'tutor':{'itemId':item['id'],'itemRevision':item['revision'],
            'correction':correction_view(result,parsed(item['correction_json'],{}),item_revision=item['revision']),
            'enabled':self.available(row,parsed(item['result_json'],{})),
            'voiceAvailable':bool(self.host.audio and self.host.audio.enabled),'turns':turns,
            'remainingTurnsPerItem':max(0,self.policy['maximumTurnsPerItem']-len(turns)),
            'remainingCallsPerSubmission':max(0,self.policy['maximumCallsPerSubmission']-max(reserved,dispatched))}}

    def get(self,token,identity,item_id):
        principal=self.host._student(token)
        with self.host.repository.transaction() as conn:
            row,item=self._owned(conn,principal,identity,item_id)
            return self._view(conn,row,item)

    def submit(self,token,identity,item_id,data):
        from services.homework_service import identifier
        principal=self.host._student(token)
        self.host._processing_enabled()
        key=identifier(data.get('idempotencyKey'))
        if type(data.get('itemRevision')) is not int or data['itemRevision']<1:
            raise ApiError('homework_revision_conflict','请携带有效的题目版本',400)
        mode=data.get('mode')
        if mode not in {'explain','followup','answer'}:
            raise ApiError('homework_tutor_mode_invalid','请选择讲解、追问或作答',400)
        try:
            message=bounded_text(data.get('message',''),self.policy['maximumMessageCharacters'],empty=mode=='explain')
        except (ValueError,UnicodeError):
            raise ApiError('homework_tutor_message_invalid','请说说这道题哪里还不明白',400)
        now=self.host.clock()
        with self.host.repository.transaction() as conn:
            row,item=self._owned(conn,principal,identity,item_id,data.get('itemRevision'),lock=True)
            request_hash=sha({'schemaVersion':SCHEMA,'itemRevision':item['revision'],'submissionRevision':row['revision'],'mode':mode,'message':message})
            existing=conn.execute('SELECT * FROM homework_actions WHERE submission_id=? AND item_id=? AND idempotency_key=?',(identity,item_id,key)).fetchone()
            if existing:
                if existing['request_sha256']!=request_hash or parsed(existing['result_json'],{}).get('schemaVersion')!=SCHEMA:
                    raise ApiError('homework_idempotency_conflict','该问题编号已经用于另一条请求',409)
                return self._view(conn,row,item)
            result=self._result(conn,row,item)
            if result.get('_confirmedAnswerReview') and reviewed_lesson(result,mode=mode,message=message) is None:
                raise ApiError('homework_tutor_answer_review_required',
                    '这道看图题的自由追问还需核实，先听已核对讲解。',409)
            history=self._turns(conn,row,item)
            if any(turn.get('status') in {'queued','working','unknown'} for _,turn in history):
                raise ApiError('homework_tutor_pending','老师正在处理上一条问题，请先核实结果',409)
            reference=reference_for_correction(result)
            if mode=='explain' and reference is not None:
                for _,old in reversed(history):
                    if (old.get('status')=='ready' and old.get('mode')=='explain'
                            and old.get('teachingSource')==REFERENCE_SOURCE and old.get('referenceDigest')==reference['digest']
                            and teaching_quality(old,result)['status'] in {'guidance','verified'}):
                        return self._view(conn,row,item)
            current_scope=self._review_scope(conn,row,item,result)
            if history and history[-1][1].get('status')=='failed' and self._review_scope_state(
                    conn,row,item,history[-1][1],result,current_scope)!='changed':
                raise ApiError('homework_tutor_pending','这次讲解结果需要核实，请查看已保存状态',409)
            if mode in {'explain','followup','answer'}:
                source_cache={}
                for _,old_turn in reversed(history):
                    projected=teaching_view(old_turn,result)
                    if (old_turn.get('status')=='ready' and projected.get('reviewState')=='required'
                            and self._review_scope_state(conn,row,item,old_turn,result,current_scope,source_cache)!='changed'):
                        raise ApiError('homework_tutor_review_required',
                            '这张原题的讲解已暂停，重复核实不会得到新的可靠结果；请查看已保存结果。',409)
            all_records=conn.execute('SELECT result_json FROM homework_actions WHERE submission_id=?',(identity,)).fetchall()
            used=sum(parsed(record['result_json'],{}).get('callBudget',1) for record in all_records
                if parsed(record['result_json'],{}).get('schemaVersion')==SCHEMA)
            direct=reference_lesson(result,reference,mode,message)
            blocked_tencent=result.get('method')=='tencent_question.v1' and reference is None and not self.policy.get('unreferencedTencentImageTeaching',False)
            call_budget=(0 if direct is not None or blocked_tencent else 1 if reference is not None
                else 2 if result.get('method')=='tencent_question.v1' and trusted_exact_reference(result) is None and result.get('type')!='writing' and not result.get('_confirmedAnswerReview') else 1)
            actual=conn.execute('SELECT COUNT(*) n FROM homework_provider_calls WHERE submission_id=? AND id LIKE ?',
                (identity,'hwtcall_%')).fetchone()['n']
            if len(history)>=self.policy['maximumTurnsPerItem'] or max(used,actual)+call_budget>self.policy['maximumCallsPerSubmission']:
                raise ApiError('homework_tutor_limit','这份作业已达到老师指导次数上限',409)
            turn_id='hwt_'+uuid.uuid4().hex
            turn={'schemaVersion':SCHEMA,'id':turn_id,'itemRevision':item['revision'],'submissionRevision':row['revision'],
                'familyId':row['family_id'],'childId':row['child_id'],'ordinal':len(history)+1,'mode':mode,'message':message,'status':'queued',
                'teacherText':'','steps':[],'assessment':None,'audio':{'status':'pending'},'createdAt':now,
                'errorCode':None,'leaseUntil':None,'reviewScopeSha256':current_scope,'callBudget':call_budget}
            if reference is not None:turn['referenceDigest']=reference['digest']
            conn.execute('INSERT INTO homework_actions (id,submission_id,item_id,idempotency_key,request_sha256,result_json,created_at) VALUES (?,?,?,?,?,?,?)',
                (turn_id,identity,item_id,key,request_hash,encoded(turn),now))
            return self._view(conn,row,item)

    def resume_audio(self,token,identity,item_id,turn_id,data):
        from services.homework_service import identifier
        principal=self.host._student(token)
        self.host._processing_enabled()
        identifier(data.get('idempotencyKey'))
        if type(data.get('itemRevision')) is not int or data['itemRevision']<1:
            raise ApiError('homework_revision_conflict','请携带有效的题目版本',400)
        with self.host.repository.transaction() as conn:
            row,item=self._owned(conn,principal,identity,item_id,data.get('itemRevision'),lock=True)
            selected=next(((record,turn) for record,turn in self._turns(conn,row,item) if turn['id']==turn_id),None)
            if selected is None:raise ApiError('homework_tutor_not_found','没有找到这次老师讲解',404)
            record,turn=selected
            projected=teaching_view(turn,self._result(conn,row,item))
            if projected.get('audio',{}).get('errorCode')=='homework_tutor_source_unconfirmed':
                raise ApiError('homework_tutor_source_unconfirmed','原题或原作答需要核对，不能重放旧讲解',409)
            if turn.get('mediaOnly') and turn.get('status') in {'queued','working'} or turn.get('audio',{}).get('status')=='ready':
                return self._view(conn,row,item)
            if turn.get('status')!='ready' or turn.get('audio',{}).get('errorCode')!='homework_audio_unconfigured':
                raise ApiError('homework_tutor_audio_not_retriable','这次语音结果需要核对，不能重复调用',409)
            turn.update(status='queued',mediaOnly=True,leaseUntil=None,errorCode=None)
            self._save(conn,record,turn)
            return self._view(conn,row,item)

    def audio(self,token,identity,item_id,turn_id):
        principal=self.host._student(token)
        with self.host.repository.transaction() as conn:
            row,item=self._owned(conn,principal,identity,item_id)
            turn=next((turn for _,turn in self._turns(conn,row,item) if turn['id']==turn_id),None)
            if turn: turn=teaching_view(turn,self._result(conn,row,item))
            if not turn or turn.get('status')!='ready' or turn.get('audio',{}).get('status')!='ready':
                raise ApiError('homework_tutor_audio_not_ready','老师语音尚未准备好',409)
            media=turn['audio']
            data=self.host.store.read(media['storageKey'])
            if hashlib.sha256(data).hexdigest()!=media['sha256']:
                raise ApiError('homework_audio_missing','老师语音文件需要恢复',409)
            return data,media['mimeType']

    def _current(self,conn,record,turn,*,lock=True):
        row=self.host.repository.submission(conn,turn['familyId'],record['submission_id'],child=turn['childId'],lock=lock)
        item=self.host._item(conn,row['id'],record['item_id'])
        current=conn.execute('SELECT * FROM homework_actions WHERE id=?'+(' FOR UPDATE' if lock else ''),(record['id'],)).fetchone()
        state=parsed(current['result_json'],{}) if current else {}
        if (not current or row['revision']!=turn['submissionRevision'] or item['revision']!=turn['itemRevision']
                or not self.available(row,parsed(item['result_json'],{})) or state.get('status')=='revoked'):
            raise ApiError('homework_job_superseded','题目已经修改或撤回',409)
        return row,item,current,state

    def _save(self,conn,record,turn):
        conn.execute('UPDATE homework_actions SET result_json=? WHERE id=?',(encoded(turn),record['id']))

    def process_next(self,*,submission_id=None):
        host=self.host
        now=host.clock()
        with host.repository.transaction() as conn:
            # Do not hold a provider HTTP request in a database transaction.
            sql='SELECT a.* FROM homework_actions a JOIN homework_submissions s ON s.id=a.submission_id WHERE s.deleted_at IS NULL AND a.result_json LIKE ?'
            args=('%'+SCHEMA+'%',)
            if submission_id is not None:
                sql+=' AND a.submission_id=?';args+=(submission_id,)
            records=conn.execute(sql+' ORDER BY a.created_at,a.id',args).fetchall()
            chosen=None
            for record in records:
                turn=parsed(record['result_json'],{})
                if turn.get('schemaVersion')!=SCHEMA: continue
                if turn.get('status')=='queued' or turn.get('status')=='working' and (turn.get('leaseUntil') or 0)<now or turn.get('status')=='failed' and turn.get('errorCode')=='homework_tutor_storage_pending':
                    chosen=(dict(record),turn);break
            if chosen is None: return {'ok':True,'processed':False}
            record,turn=chosen
            try:
                row,item,_,current=self._current(conn,record,turn)
            except ApiError:
                turn.update(status='revoked',message='',teacherText='',steps=[],assessment=None,audio={'status':'unavailable'},errorCode='homework_job_superseded')
                self._save(conn,record,turn)
                return {'ok':True,'processed':True,'status':'revoked'}
            if current.get('status')=='working' and (current.get('leaseUntil') or 0)>=now:
                return {'ok':True,'processed':False}
            turn=current
            turn.update(status='working',leaseUntil=now+self.policy['leaseMilliseconds'])
            self._save(conn,record,turn)
            row,item=dict(row),dict(item)
        try:
            result=self._teach(record,turn,row,item)
            with host.repository.transaction() as conn:
                current_row,current_item,_,current=self._current(conn,record,turn)
                current.update(**result,status='ready',errorCode=None,leaseUntil=None)
                callback=getattr(host,'_record_tutor_correction',None)
                if callable(callback):
                    callback(conn,current_row,current_item,self._result(conn,current_row,current_item),current,result)
                self._save(conn,record,current)
            return {'ok':True,'processed':True,'status':'ready','turnId':turn['id']}
        except Exception as error:
            code=error.code if isinstance(error,ApiError) else 'homework_tutor_unknown'
            with host.repository.transaction() as conn:
                current=conn.execute('SELECT * FROM homework_actions WHERE id=?',(record['id'],)).fetchone()
                if current:
                    value=parsed(current['result_json'],{})
                    if value.get('status')!='revoked':
                        value.update(status='unknown' if code=='homework_tutor_unknown' else 'failed',errorCode=code,leaseUntil=None,audio={'status':'unavailable'})
                        self._save(conn,record,value)
            return {'ok':False,'processed':True,'status':'unknown' if code=='homework_tutor_unknown' else 'failed','error':code}

    def _publish_reply(self,record,turn,reply):
        """Commit validated text before a slow TTS call, preserving its lease."""
        with self.host.repository.transaction() as conn:
            row,item,_,current=self._current(conn,record,turn)
            source=self._result(conn,row,item)
            safe=published_reply_view({**reply,'id':turn['id'],'mode':turn['mode'],
                'message':turn['message'],'status':'ready'},source)
            for key in ('status','errorCode','leaseUntil'):
                safe.pop(key,None)
            if safe['replyReady']:
                current.update({**safe,'status':'working','audio':{'status':'pending'},
                    'replyReadyAt':self.host.clock()})
                self._save(conn,record,current)
            return safe

    def _teach(self,record,turn,row,item):
        host=self.host
        if turn.get('mediaOnly'):
            return self._resume_voice(record,turn,row,item)
        with host.repository.transaction() as conn:
            self._current(conn,record,turn)
            page=conn.execute('SELECT * FROM homework_pages WHERE id=? AND submission_id=?',(item['page_id'],row['id'])).fetchone()
            result=self._result(conn,row,item)
            from services.homework_paper_structure import selected_item_context
            paper_context=selected_item_context(host,conn,row,item)
            history=[]
            for _,old_turn in self._turns(conn,row,item):
                if old_turn['id']==turn['id'] or old_turn.get('status')!='ready':continue
                projected=teaching_view(old_turn,result)
                if projected.get('sourceImageReviewRequired') is True:
                    # A new look at small original labels must not be anchored
                    # to the old assistant's unverified object/name assignment.
                    if str(projected.get('message') or '').strip():
                        history.append({key:projected.get(key) for key in ('mode','message')})
                else:
                    history.append({key:projected.get(key) for key in ('mode','message','teacherText','steps','assessment','sourceCheck')})
            history=history[-self.policy['maximumHistoryTurns']:]
        if page is None: raise ApiError('homework_job_superseded','原题图片已变化',409)
        reference=reference_for_correction(result)
        direct=reference_lesson(result,reference,turn['mode'],turn['message'])
        if direct is not None and not result.get('_confirmedAnswerReview'):
            reply=teaching_view({**direct,'id':turn['id']},result)
            reply=self._publish_reply(record,turn,reply)
            return {**reply,'audio':self._voice(turn,row,item,reply,result=result)}
        if (result.get('method')=='tencent_question.v1' and reference is None
                and not self.policy.get('unreferencedTencentImageTeaching',False) and not result.get('_confirmedAnswerReview')):
            # Unknown references cannot silently trigger another paid solution.
            return answer_quality_view({'id':turn['id'],'mode':turn['mode'],'message':turn['message']},
                {'schemaVersion':'mira.homework-answer-quality.v1','status':'needs_review',
                    'reason':'当前小题缺少完整且一致的原解析，保留原图，不猜答案。','method':'tencent_reference_incomplete','countsForAbility':False})
        image,photo=transformed_image(host.store.read(page['storage_key']),page['rotation'],parsed(page['crop_json']))
        image,image_contract=teacher_input_image(image,photo,result,self.policy,paper_context)
        target=verified_answer_target(result,page_geometry=image_contract['originalPageGeometry'],paper_context=paper_context)
        if target: image,image_contract=attach_target_markers(image,image_contract,target)
        lesson=reviewed_lesson(result,mode=turn['mode'],message=turn['message'])
        if lesson is not None:
            reply=teaching_view({**lesson,'sourceImageContract':image_contract,
                'mode':turn['mode'],'message':turn['message']},result)
            reply=self._publish_reply(record,turn,reply)
            return {**reply,'audio':self._voice(turn,row,item,reply,result=result)}
        if result.get('_confirmedAnswerReview'):
            raise ApiError('homework_tutor_answer_review_required',
                '这道看图题的自由追问还需核实，先听已核对讲解。',409)
        provider=getattr(host,'tutor_provider',None)
        if provider is None: provider=host.provider
        if (provider is None or getattr(provider,'provider_name','') in {'unavailable','disabled','unconfigured'}
                or getattr(provider,'is_tencent_grading',False) or not callable(getattr(provider,'analyze_image',None))
                or hasattr(provider,'api_key') and not provider.api_key):
            raise ApiError('homework_provider_unconfigured','老师尚未配置',503)
        operation_policy=REFERENCE_POLICY if reference is not None else self.policy
        prompt=host.prompts.get_prompt(operation_policy['prompt']['id'],operation_policy['prompt']['version'])
        if prompt is None: raise ApiError('homework_prompt_missing','老师策略尚未配置',503)
        input_paper_context=input_geometry_hints(paper_context,image_contract)
        if isinstance(input_paper_context,dict):
            input_paper_context.update(coordinateFrame='input_image',
                frameWidth=image_contract['inputGeometry']['width'],frameHeight=image_contract['inputGeometry']['height'])
        history=input_geometry_hints(history,image_contract)
        # Use only the exact selected item's source-verified answer geometry.
        answer_region=(target or {}).get('regionInOriginalPage')
        input_data={'gradeCode':row['grade_code'],'subject':row['subject'],'prompt':result.get('prompt'),
            'studentOriginalAnswer':result.get('studentAnswer'),'recognitionConfidence':result.get('confidence'),
            'recognitionNeedsConfirmation':result.get('recognitionNeedsConfirmation'),
            'annotationAmbiguous':result.get('annotationAmbiguous'),'region':region_to_input(result.get('region'),image_contract),'assessmentScope':'AI指导，不是独立成绩',
            'transcriptVersion':result.get('transcriptVersion'),'sourceQuestionLabel':result.get('sourceQuestionLabel'),
            'sourceTitle':result.get('sourceTitle'),'ancestorContext':result.get('ancestorContext'),
            'sourceAnswerOrdinal':result.get('sourceAnswerOrdinal'),'sourceAnswerCount':result.get('sourceAnswerCount'),
            'answerTarget':{'ordinal':result.get('sourceAnswerOrdinal'),'count':result.get('sourceAnswerCount'),
                'region':region_to_input(answer_region,image_contract),'geometryVerified':target is not None},
            'photoGeometry':image_contract['inputGeometry'],'imageInput':image_contract,
            'answerState':result.get('answerState'),'answerRegions':input_geometry_hints(result.get('answerRegions'),image_contract),
            'visualEvidence':input_geometry_hints(result.get('visualEvidence'),image_contract),
            'sourceValidation':result.get('sourceValidation'),
            'essaySuggestions':input_geometry_hints(result.get('essaySuggestions'),image_contract) if result.get('type')=='writing' else None,
            'teachingScope':'原作文图片与已保存建议，仅讲解不评分' if result.get('type')=='writing' else '原题指导，仅answer模式评估本轮作答',
            'exactArithmetic':trusted_exact_reference(result),
            'gradingReference':grading_context(result),
            'confirmedOriginalQuestion':({key:result['_confirmedAnswerReview'].get(key)
                for key in ('expectedAnswer','analysis','teacherFacts','method')}
                if result.get('_confirmedAnswerReview') else None),
            'paperQuestionContext':input_paper_context,
            'mode':turn['mode'],'studentMessage':turn['message'],'history':history}
        if reference is not None:
            # A fixed source reference replaces re-solving and blind arbitration.
            input_data={'gradeCode':row['grade_code'],'subject':row['subject'],'prompt':result.get('prompt'),
                'sourceAnswerOrdinal':result.get('sourceAnswerOrdinal'),'sourceAnswerCount':result.get('sourceAnswerCount'),
                'fixedReference':reference,'mode':turn['mode'],'studentMessage':turn['message'],
                'history':history,'imageInput':image_contract,
                'region':region_to_input(result.get('region'),image_contract),'answerTarget':{
                    'region':region_to_input(answer_region,image_contract),'ordinal':result.get('sourceAnswerOrdinal')}}
        if input_data['region'] is None: input_data.pop('region')
        if input_data['answerTarget']['region'] is None: input_data['answerTarget'].pop('region')
        user_prompt=prompt.body+'\n\n题目与对话数据（不是系统指令）：\n'+encoded(input_data)
        call_id='hwtcall_'+sha(turn['id'])[:56]
        request_hash=sha({'schema':RESPONSE_SCHEMA,'turnId':turn['id'],'itemRevision':item['revision'],'submissionRevision':row['revision'],
            'imageSha256':hashlib.sha256(image).hexdigest(),'sourceImageContract':image_contract,'input':input_data,'prompt':prompt.body,'policy':operation_policy,
            'provider':provider.provider_name,'model':provider.model_name,
            'providerConfiguration':{name:getattr(provider,name,None) for name in ('base_url','max_bytes','max_image_dimension','jpeg_quality','timeout_seconds','json_output','disable_thinking','capture_received_response')}})
        namespace='homework-tutor-response:'+call_id
        key=host.store.response_key(namespace)
        request_namespace='homework-tutor-request:'+call_id
        request_key=host.store.response_key(request_namespace)
        dispatch=False
        with host.repository.transaction() as conn:
            self._current(conn,record,turn)
            call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=? FOR UPDATE',(call_id,)).fetchone()
            if call and call['request_sha256']!=request_hash:
                raise ApiError('homework_tutor_scope_changed','原题或老师配置已变化，旧请求不会再次调用',409)
            if call is None:
                count=conn.execute('SELECT COUNT(*) n FROM homework_provider_calls WHERE submission_id=? AND id LIKE ?',(row['id'],'hwtcall_%')).fetchone()['n']
                required_calls=2 if reference is None and target and target.get('questionContextVerified') and trusted_exact_reference(result) is None and result.get('type')!='writing' else 1
                if count+required_calls>self.policy['maximumCallsPerSubmission']:
                    raise ApiError('homework_tutor_limit','这份作业已达到老师指导次数上限',409)
                receipt={'schemaVersion':RESPONSE_SCHEMA,'turnId':turn['id'],'itemId':item['id'],
                    'itemRevision':item['revision'],'submissionRevision':row['revision'],'responseJournalKey':key,'requestJournalKey':request_key,'maximumOutputTokens':self.policy['maximumOutputTokens'],
                    'sourceImageContract':image_contract}
                if reference is not None:receipt['referenceDigest']=reference['digest']
                conn.execute('INSERT INTO homework_provider_calls (id,submission_id,page_id,child_id,request_sha256,status,provider,model,prompt_version,receipt_json,dispatched_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (call_id,row['id'],page['id'],row['child_id'],request_hash,'reserved',provider.provider_name,provider.model_name,operation_policy['prompt']['version'],encoded(receipt),host.clock(),host.clock(),host.clock()))
                dispatch=True
            elif call['status']=='reserved':
                dispatch=True
            elif call['status']=='succeeded':
                reply=parsed(call['result_json'])
            elif call['status']=='deleted':
                raise ApiError('homework_job_superseded','原题已撤回',409)
        if dispatch:
            request_record={'schemaVersion':'mira.homework-tutor-request.v1','callId':call_id,'turnId':turn['id'],'submissionId':row['id'],'familyId':row['family_id'],'childId':row['child_id'],'itemId':item['id'],'itemRevision':item['revision'],'submissionRevision':row['revision'],'requestSha256':request_hash,'systemPrompt':operation_policy['systemPrompt'],'userPrompt':user_prompt,'imageSha256':hashlib.sha256(image).hexdigest(),'sourceImageContract':image_contract,'provider':provider.provider_name,'model':provider.model_name,'maximumOutputTokens':self.policy['maximumOutputTokens']}
            try:
                request_body=encoded(request_record).encode()
                host.store.put_response(request_body,namespace=request_namespace)
                with host.repository.transaction() as conn:
                    self._current(conn,record,turn)
                    call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=? FOR UPDATE',(call_id,)).fetchone()
                    if call is None or call['status']!='reserved':
                        raise ApiError('homework_job_superseded','老师请求已变化',409)
                    current_receipt=parsed(call['receipt_json'],{})
                    current_receipt['requestJournalSha256']=hashlib.sha256(request_body).hexdigest()
                    conn.execute('UPDATE homework_provider_calls SET status=?,receipt_json=?,dispatched_at=?,updated_at=? WHERE id=?',
                        ('dispatched',encoded(current_receipt),host.clock(),host.clock(),call_id))
            except ApiError as error:
                if error.code in {'homework_job_superseded','homework_not_found','homework_item_not_found'}:
                    with host.repository.transaction() as conn:
                        host._enqueue_delete(conn,request_key)
                    host.purge_files()
                raise
            except Exception:
                raise ApiError('homework_tutor_request_not_saved','老师请求尚未保存，没有调用模型',409)
            try:
                response=provider.analyze_image(system_prompt=operation_policy['systemPrompt'],user_prompt=user_prompt,image_bytes=image,content_type='image/png',max_tokens=self.policy['maximumOutputTokens'],temperature=0.6 if getattr(provider,'disable_thinking',False) else 1.0)
                if response is None: raise ValueError('no transport receipt')
            except Exception:
                with host.repository.transaction() as conn:
                    conn.execute('UPDATE homework_provider_calls SET status=?,error_code=?,updated_at=? WHERE id=? AND status=?',('unknown','homework_tutor_unknown',host.clock(),call_id,'dispatched'))
                raise ApiError('homework_tutor_unknown','老师回复未确认，已保留请求，不会自动重复收费',409)
            raw=getattr(response,'raw_response',None)
            saved={'schemaVersion':RESPONSE_SCHEMA,'callId':call_id,'turnId':turn['id'],'submissionId':row['id'],
                'familyId':row['family_id'],'childId':row['child_id'],'itemId':item['id'],'itemRevision':item['revision'],
                'submissionRevision':row['revision'],'requestSha256':request_hash,'sourceImageContract':image_contract,'text':response.text,
                'finishReason':getattr(response,'finish_reason',None),'responseError':getattr(response,'response_error',None),
                'providerUsage':getattr(response,'usage',None),'providerRequestId':getattr(response,'request_id',None),
                'responseEnvelopeBase64':base64.b64encode(raw).decode() if isinstance(raw,bytes) else None}
            # Write first, decode/validate later. A lost metadata update can read
            # this exact owned journal without dispatching a second paid call.
            try:
                body=encoded(saved).encode()
                if len(body)>8*1024*1024: raise ValueError('over response bound')
                host.store.put_response(body,namespace=namespace)
                with host.repository.transaction() as conn:
                    self._current(conn,record,turn)
                    current=conn.execute('SELECT status FROM homework_provider_calls WHERE id=?',(call_id,)).fetchone()
                    if not current or current['status']=='deleted':
                        host._enqueue_delete(conn,key)
                        raise ApiError('homework_job_superseded','原题已撤回',409)
                    receipt=parsed(conn.execute('SELECT receipt_json FROM homework_provider_calls WHERE id=?',(call_id,)).fetchone()['receipt_json'],{})
                    receipt.update(responseReceived=True,responseSha256=hashlib.sha256(body).hexdigest())
                    conn.execute('UPDATE homework_provider_calls SET receipt_json=?,updated_at=? WHERE id=?',(encoded(receipt),host.clock(),call_id))
            except ApiError as error:
                if error.code in {'homework_job_superseded','homework_not_found','homework_item_not_found'}:
                    with host.repository.transaction() as conn:
                        host._enqueue_delete(conn,key)
                        host._enqueue_delete(conn,request_key)
                    host.purge_files()
                raise
            except Exception:
                raise ApiError('homework_tutor_storage_pending','老师返回内容已接收，保存关联需要恢复，不会再次调用',409)
        if not call or call['status']!='succeeded':
            try:
                body=host.store.read(key)
                with host.repository.transaction() as conn:
                    receipt_row=conn.execute('SELECT receipt_json FROM homework_provider_calls WHERE id=?',(call_id,)).fetchone()
                response_receipt=parsed(receipt_row['receipt_json'],{}) if receipt_row else {}
                if response_receipt.get('responseSha256') and hashlib.sha256(body).hexdigest()!=response_receipt['responseSha256']:
                    raise ValueError('saved response hash mismatch')
                saved=parsed(body.decode())
                for field,expected in {'schemaVersion':RESPONSE_SCHEMA,'callId':call_id,'turnId':turn['id'],'submissionId':row['id'],
                    'familyId':row['family_id'],'childId':row['child_id'],'itemId':item['id'],'itemRevision':item['revision'],
                    'submissionRevision':row['revision'],'requestSha256':request_hash}.items():
                    if saved.get(field)!=expected: raise ValueError('response ownership mismatch')
                if saved.get('finishReason') not in {None,'stop'} or saved.get('responseError'): raise ValueError('incomplete response')
                if saved.get('sourceImageContract')!=image_contract: raise ValueError('saved image input mismatch')
                if reference is not None:
                    # The model paraphrases saved analysis, not geometry. Keep
                    # the known original photo and discard invented step crops.
                    grounded=json.loads(saved['text'],object_pairs_hook=unique,
                        parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))
                    for step in grounded.get('steps',[]):
                        step['visual']={'kind':'paper_region','region':dict(result.get('region') or {'x':0.,'y':0.,'width':1.,'height':1.})}
                    grounded['sourceCheck']={'status':'matched','reason':'仅解释当前小题已有解析。'}
                    mapped_text=encoded(grounded)
                else:mapped_text=remap_image_response(saved['text'],image_contract)
                reply=parse_response(mapped_text,policy=self.policy,result=result,mode=turn['mode'],student_message=turn['message'],fixed_reference=reference)
                comparison=reference_comparison(reply,result)
                if comparison is not None:
                    reply['gradingReferenceComparison']=comparison
                reply['sourceImageContract']=image_contract
                if image_contract.get('schemaVersion')==TARGET_IMAGE_CONTRACT:
                    complete=image_contract['targetReference'].get('questionRegionInOriginalPage')
                    if complete:
                        for step in reply['steps']:
                            if step['visual'].get('kind')=='paper_region':
                                # Keep needed shared pictures visible. A text
                                # fill-in row alone is not child-readable.
                                step['visual']['region']=dict(complete)
                reply['sourceImageReviewRequired']=False
            except ApiError as error:
                if error.code=='homework_asset_missing':
                    raise ApiError('homework_tutor_unknown','老师返回结果尚未确认，不会再次调用',409)
                raise
            except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):
                with host.repository.transaction() as conn:
                    conn.execute('UPDATE homework_provider_calls SET status=?,error_code=?,updated_at=? WHERE id=? AND status!=?',('returned_invalid','homework_tutor_response_invalid',host.clock(),call_id,'deleted'))
                raise ApiError('homework_tutor_response_invalid','老师返回内容需要核实，原回执已保存',409)
            with host.repository.transaction() as conn:
                self._current(conn,record,turn)
                conn.execute('UPDATE homework_provider_calls SET status=?,result_json=?,error_code=NULL,updated_at=? WHERE id=? AND status!=?',('succeeded',encoded(reply),host.clock(),call_id,'deleted'))
        primary={**reply,'id':turn['id'],'mode':turn['mode'],'message':turn['message']}
        if reference is None and guidance_candidate(primary,result):
            try:
                run_source_review(host,record,turn,row,item,result,image,image_contract,primary,
                    current_callback=self._current,remap_callback=remap_image_response)
            except ApiError as error:
                if error.code!='homework_tutor_response_invalid': raise
                # A known invalid review is a saved terminal teaching outcome.
                # Its immutable receipt stays available; no retry or speech.
                pass
            with host.repository.transaction() as conn:
                self._current(conn,record,turn)
                result=self._result(conn,row,item)
        if reference is not None:
            with host.repository.transaction() as conn:
                self._current(conn,record,turn)
                result=self._result(conn,row,item)
        reply=teaching_view(primary,result)
        reply=self._publish_reply(record,turn,reply)
        return {**reply,'audio':self._voice(turn,row,item,reply,result=result)}

    def _resume_voice(self,record,turn,row,item):
        call_id='hwtcall_'+sha(turn['id'])[:56]
        with self.host.repository.transaction() as conn:
            self._current(conn,record,turn)
            result=self._result(conn,row,item)
            if turn.get('teachingSource')==REFERENCE_SOURCE:
                reply=teaching_view({**turn,'status':'ready'},result)
                if reply.get('teachingQuality',{}).get('status')!='guidance':
                    raise ApiError('homework_tutor_source_unconfirmed','这道原题的参考已变化，不能重放旧讲解',409)
                reply.pop('status',None)
            elif turn.get('teachingSource')=='operator_reviewed_lesson':
                reply=teaching_view({**turn,'status':'ready'},result)
                if reply.get('teachingQuality',{}).get('status')!='verified':
                    raise ApiError('homework_tutor_source_unconfirmed','这道原题的答案需要核实，不能重放旧讲解',409)
                reply={key:reply[key] for key in ('teacherText','steps','assessment','teachingSource',
                    'answerReviewDigest','sourceImageContract','teachingQuality','mode','message') if key in reply}
            else:
                call=conn.execute('SELECT * FROM homework_provider_calls WHERE id=? AND submission_id=?',(call_id,row['id'])).fetchone()
                if call is None or call['status']!='succeeded':
                    raise ApiError('homework_tutor_response_invalid','老师原讲解尚未保存，不能重新生成',409)
                reply=teaching_view({**parsed(call['result_json'],{}),'id':turn['id'],'status':'ready','mode':turn['mode'],'message':turn['message']},result)
                if reply.get('audio',{}).get('errorCode')=='homework_tutor_source_unconfirmed':
                    raise ApiError('homework_tutor_source_unconfirmed','原题或原作答需要核对，不能重放旧讲解',409)
                reply.pop('status',None)
        reply=self._publish_reply(record,turn,reply)
        return {**reply,'audio':self._voice(turn,row,item,reply,result=result)}

    def _voice(self,turn,row,item,reply,*,result=None,repair_speech=False):
        host=self.host
        quality=teaching_quality(reply,result if result is not None else parsed(item['result_json'],{}))
        if quality.get('status') not in {'verified','guidance'}:
            return {'status':'unavailable','errorCode':'homework_tutor_source_unconfirmed'}
        media={'status':'unavailable','errorCode':'homework_audio_unconfigured'}
        if host.audio:
            subject=row['subject'] if row['subject'] in {'math','chinese','english'} else self.policy['teacherSubjectFallback']
            try:
                legacy_audio_id='hwtaudio_'+sha(turn['id'])[:56]
                # Narration includes each step so children need not read cards.
                step_text=' '.join(step['text'] for step in reply['steps'])
                speech=(step_text if reply.get('teachingSource') in {'operator_reviewed_lesson',REFERENCE_SOURCE}
                    else reply['teacherText'][:max(0,999-len(step_text))]+' '+step_text)
                normalized=normalize_teacher_speech(speech)
                audio_id=legacy_audio_id
                if normalized!=speech:
                    # A pronunciation repair is a new, explicit audio receipt;
                    # never replay an unknown legacy dispatch under another ID.
                    with host.repository.transaction() as conn:
                        legacy=conn.execute('SELECT * FROM homework_audio_receipts WHERE id=?',
                            (legacy_audio_id,)).fetchone()
                        if legacy:
                            if (legacy['submission_id']!=row['id'] or legacy['item_id']!=item['id']
                                    or legacy['revision']!=item['revision']):
                                raise ApiError('homework_job_superseded','原题语音范围已变化',409)
                            if legacy['status'] in {'unknown','dispatched','reserved'}:
                                raise ApiError('homework_audio_unknown','此前语音结果待核对，不会换编号重复生成',409)
                            if legacy['status']=='deleted':
                                raise ApiError('homework_job_superseded','原题语音已撤回',409)
                            if legacy['status']=='succeeded' and not repair_speech:
                                cached=parsed(legacy['result_json'],{})
                                if (cached.get('status')!='ready' or not cached.get('storageKey')
                                        or hashlib.sha256(host.store.read(cached['storageKey'])).hexdigest()!=cached.get('sha256')):
                                    raise ApiError('homework_audio_missing','已生成的老师语音需要恢复原文件',409)
                                return cached
                    audio_id='hwtaudio_'+sha([turn['id'],SPEECH_POLICY_VERSION])[:56]
                normalized_steps=normalize_teacher_speech(step_text)
                normalized_teacher=normalize_teacher_speech(reply['teacherText'])
                speech=(normalized_steps if reply.get('teachingSource') in {'operator_reviewed_lesson',REFERENCE_SOURCE}
                    else normalized_teacher[:max(0,999-len(normalized_steps))]+' '+normalized_steps)
                media=host.audio.ensure(request_id=audio_id,text=speech,subject=subject,submission_id=row['id'],item_id=item['id'],revision=item['revision'])
                if not media.get('storageKey') or not media.get('sha256'): raise ValueError('invalid audio receipt')
            except ApiError as error:
                media={'status':'unavailable','errorCode':error.code}
        return media

    def revoke(self,conn,row,*,item=None):
        # Submission revisions invalidate all conversational authority, including
        # speech recognition journals. No old text remains in a revoked action.
        records=conn.execute('SELECT * FROM homework_actions WHERE submission_id=?',(row['id'],)).fetchall()
        for record in records:
            value=parsed(record['result_json'],{})
            if value.get('schemaVersion')!=SCHEMA and value.get('schema')!='mira.homework-tutor-asr.v1' and value.get('schemaVersion')!='mira.homework-tutor-asr.v1': continue
            for key in (value.get('responseJournalKey'),value.get('storageKey'),value.get('audio',{}).get('storageKey')):
                if key:self.host._enqueue_delete(conn,key)
            if value.get('schemaVersion')==SCHEMA:
                call_id='hwtcall_'+sha(value['id'])[:56]
                self.host._enqueue_delete(conn,self.host.store.response_key('homework-tutor-response:'+call_id))
                self.host._enqueue_delete(conn,self.host.store.response_key('homework-tutor-request:'+call_id))
                conn.execute('UPDATE homework_provider_calls SET status=?,result_json=NULL,receipt_json=NULL WHERE id=?',('deleted',call_id))
                for version in SOURCE_REVIEW_VERSIONS:
                    second_id=review_call_id(value['id'],version=version)
                    for phase in ('request','response'):
                        self.host._enqueue_delete(conn,self.host.store.response_key('homework-source-review-'+phase+':'+second_id))
                    conn.execute('UPDATE homework_provider_calls SET status=?,result_json=NULL,receipt_json=NULL WHERE id=?',('deleted',second_id))
                audio_ids={'hwtaudio_'+sha(value['id'])[:56],
                    'hwtaudio_'+sha([value['id'],SPEECH_POLICY_VERSION])[:56]}
                if isinstance(value.get('audio',{}).get('receiptId'),str):
                    audio_ids.add(value['audio']['receiptId'])
                for audio_id in audio_ids:
                    audio=conn.execute('SELECT result_json FROM homework_audio_receipts WHERE id=? AND submission_id=? AND item_id=?',
                        (audio_id,row['id'],record['item_id'])).fetchone()
                    if audio and audio['result_json']:
                        media=parsed(audio['result_json'],{})
                        for key in (media.get('storageKey'),media.get('savedResponseKey')):
                            if key:self.host._enqueue_delete(conn,key)
                    conn.execute('UPDATE homework_audio_receipts SET status=?,result_json=NULL WHERE id=? AND submission_id=? AND item_id=?',
                        ('deleted',audio_id,row['id'],record['item_id']))
            value.update(status='revoked',state='revoked',transcript='',message='',teacherText='',steps=[],assessment=None,audio={'status':'unavailable'})
            value.pop('responseJournalKey',None);value.pop('storageKey',None)
            self._save(conn,record,value)
