"""Versioned reuse of a source-bound reference; no visual re-solving or grades."""
from copy import deepcopy
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
POLICY=json.loads((ROOT/'content/homework_tencent_reference_policy.v1.json').read_text())
TEACHING_SOURCE='tencent_reference_lesson.v1'
FOLLOWUP_SOURCE='tencent_reference_followup.v1'
PRESETS={
    '我还没有听懂，请用更简单的图片和短句再讲一次。': '先看图片上这道题。我们把已有解析分成小步，再慢慢听一遍。',
    '为什么要这样做？请看着原题再解释一下。': '我们按这道原题已有的解析，看看每一步为什么这样做。',
    '还有别的方法吗？请用另一种方法给我讲讲这道原题。': '先用这道题已有的解析再讲一遍；原解析没有提供另一种方法时，老师不会猜。',
}


def plain_reference_text(value):
    """Remove common OCR math wrappers only in a narration copy."""
    text=str(value or '')
    for _ in range(8):
        changed=re.sub(r'\\(?:boxed|text|mathrm|operatorname)\{([^{}]*)\}',r'\1',text)
        changed=re.sub(r'\\frac\{([^{}]*)\}\{([^{}]*)\}',r'\1除以\2',changed)
        if changed==text: break
        text=changed
    for before,after in {'\\times':'乘','\\div':'除以','\\neq':'不等于','\\leq':'小于或等于',
            '\\geq':'大于或等于','\\quad':' ','\\qquad':' ','\\bigcirc':'○','\\circ':'○',
            '\\left':'','\\right':'','\\(':'','\\)':'','\\[':'','\\]':''}.items():
        text=text.replace(before,after)
    text=text.replace('$','').replace('{','').replace('}','')
    # Unknown markup is unsuitable for child narration; retain original analysis
    # in grading and ask the child to look at the marked picture instead.
    if re.search(r'\\[A-Za-z]+',text): return '看着原题图片，对照这道题已有的解析。'
    return re.sub(r'\s+',' ',text).strip()


def lesson(result,reference,mode='explain',message=''):
    if reference is None or mode not in {'explain','followup','answer'}: return None
    if mode=='followup' and message not in PRESETS: return None
    from services.homework_answer_quality import canonical_correction_answer
    answer=plain_reference_text(reference['expectedAnswer'])
    lead='看着原来的题目图片，老师按这道题已有的解析陪你订正。'
    if mode=='followup': lead=PRESETS[message]
    if mode=='answer':
        actual=canonical_correction_answer(message)
        expected=reference['canonicalExpectedAnswer']
        lead=('你这次的作答与这道题的参考相同。我们再听听为什么。' if actual==expected
            else '这次作答与这道题的参考还不相同。看着原图，听老师再讲一遍。' if actual is not None
            else '老师还不能确定你这次说的答案。看着原图，先听解析，再清楚说出你的答案。')
    analysis=plain_reference_text(reference['analysis'])
    chunks=[part.strip() for part in re.findall(r'.{1,150}(?:[。！？；]|$)|.{1,150}',analysis) if part.strip()]
    # A long original analysis remains available in full beside the photo.
    chunks=chunks[:3]
    texts=[lead,*chunks,f'这道小题的参考答案是{answer}。听过讲解以后，还需要你自己再试一试。']
    region=deepcopy(result.get('region') or {'x':0.,'y':0.,'width':1.,'height':1.})
    return {'teachingSource':TEACHING_SOURCE,'referenceDigest':reference['digest'],
        'teacherText':lead,'mode':mode,'message':message,
        'sourceCheck':{'status':'matched','reason':'复用当前小题来源完整且一致的原解析；不是新的图像核实。',
            'answerOrdinal':result.get('sourceAnswerOrdinal',1),'questionRegion':region},
        'steps':[{'id':f'step-{index+1}','text':text,'visual':{'kind':'paper_region','region':deepcopy(region)}} for index,text in enumerate(texts)],
        'assessment':{'status':'guidance_only','reason':'按当前小题已有参考订正，不代表独立掌握。',
            'expectedAnswer':reference['expectedAnswer'],'method':'ai_guidance','countsForAbility':False,'independent':None}}


def matches_lesson(value,result,reference):
    approved=lesson(result,reference,value.get('mode','explain'),value.get('message',''))
    return bool(approved and value.get('teachingSource')==TEACHING_SOURCE
        and all(value.get(key)==approved[key] for key in ('referenceDigest','teacherText','steps','assessment','sourceCheck')))


def grounded_followup(value,result,reference):
    """Reject a paraphrase which replaces the fixed answer or invents arithmetic."""
    if reference is None or value.get('mode')!='followup': return False
    from services.homework_answer_quality import canonical_correction_answer, _numeric_answer, _arithmetic_claims_consistent
    assessment=value.get('assessment') or {}
    if canonical_correction_answer(assessment.get('expectedAnswer'))!=reference['canonicalExpectedAnswer']: return False
    text=' '.join([str(value.get('teacherText') or '')]+[str(step.get('text') or '') for step in value.get('steps',[])])
    numeric=_numeric_answer(reference['expectedAnswer'])
    if numeric is not None and not _arithmetic_claims_consistent(text,str(numeric)): return False
    # Source-consistent reference is a teaching level, never a new verdict.
    return not re.search(r'已经掌握|独立掌握|人工(?:已)?核实|我(?:重新)?(?:看图|核实).*正确答案',text)
