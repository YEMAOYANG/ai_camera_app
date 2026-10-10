#!/usr/bin/env python3
"""Isolated, bounded teacher comparison; never imports the app or writes a DB.

Default only renders original fixtures. Paid execution requires an explicit
flag and a fresh output directory. Each provider request is journaled before
dispatch, once only; an uncertain transport result stops that provider lane.
Ground truth and rubrics never enter the model input. Raw provider quality and
the existing student-facing parser's result are recorded separately.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import io
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from dotenv import dotenv_values
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from integrations.ai.kimi_vision_provider import _encode_image
from services.homework_tutor_service import POLICY, encoded, parse_response
from services.prompt_registry import PromptRegistry
from core.errors import ApiError

CASES = ROOT / 'content/evals/homework_teacher.v1.json'
PROMPT = ROOT / 'prompts/homework/tutor_v3.md'
MAXIMUM_CALLS = 32


@dataclass(frozen=True)
class Candidate:
    name: str
    model: str
    base_url: str
    api_key: str = field(repr=False)


def candidates():
    backend = dotenv_values(ROOT / '.env')
    native = dotenv_values(ROOT.parent / 'openmaic-runtime/.env')
    # Resolve only these two already configured servers. Never change env files
    # or copy their keys into a fixture, journal, stdout or report.
    result = [
        Candidate('deepseek', 'deepseek-flash', native.get('DEEPSEEK_BASE_URL') or 'https://api.deepseek.com', native.get('DEEPSEEK_API_KEY') or ''),
        Candidate('qwen', 'qwen3.8-max', backend.get('HOMEWORK_VISION_BASE_URL') or 'https://dashscope.aliyuncs.com/compatible-mode/v1', backend.get('HOMEWORK_VISION_API_KEY') or backend.get('DASHSCOPE_API_KEY') or backend.get('QWEN_API_KEY') or ''),
    ]
    for candidate in result:
        parsed = urlparse(candidate.base_url)
        expected = 'api.deepseek.com' if candidate.name == 'deepseek' else 'dashscope.aliyuncs.com'
        if parsed.scheme != 'https' or parsed.hostname != expected or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('unexpected_provider_endpoint')
    return result


def save(path, value):
    temporary = path.with_suffix('.pending')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def font(size):
    for path in ['/System/Library/Fonts/PingFang.ttc', '/System/Library/Fonts/STHeiti Medium.ttc', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if Path(path).exists():
            return ImageFont.truetype(path, int(size))
    return ImageFont.load_default(size=int(size))


def render(scene):
    if scene.get('privateImagePath'):
        source=Path(scene['privateImagePath']).resolve()
        allowed=Path('/private/tmp/mira-homework-20261008')
        if source.parent!=allowed or source.name not in {'page-0.png','page-1.png'}:
            raise ValueError('private_source_image_out_of_scope')
        return source.read_bytes()
    image = Image.new('RGB', (scene.get('width', 1000), scene.get('height', 700)), scene.get('background', '#ffffff'))
    draw = ImageDraw.Draw(image)
    for element in scene['elements']:
        kind = element.get('type') or element.get('kind')
        x, y = element.get('x', 0), element.get('y', 0)
        fill = element.get('fill', '#ffd56a')
        if fill == 'none':
            fill = None
        outline = element.get('outline', '#334d42')
        radius = element.get('radius', 25)
        if kind == 'text':
            draw.text((x, y), element['text'], font=font(element.get('size', 32)), fill=element.get('color', '#222222'))
        elif kind == 'rect':
            draw.rectangle((x, y, x + element['width'], y + element['height']), fill=fill, outline=outline, width=3)
        elif kind == 'circle':
            draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=fill, outline=outline, width=3)
        elif kind == 'star':
            points = [(x + radius*(1 if i % 2 == 0 else .45)*math.cos(-math.pi/2+i*math.pi/5), y + radius*(1 if i % 2 == 0 else .45)*math.sin(-math.pi/2+i*math.pi/5)) for i in range(10)]
            draw.polygon(points, fill=fill, outline=outline, width=3)
        elif kind == 'polygon':
            draw.polygon([tuple(p) for p in element['points']], fill=fill, outline=outline, width=element.get('outlineWidth', 3))
        elif kind == 'apple':
            draw.ellipse((x-radius, y-radius*.8, x+radius*.15, y+radius), fill=fill, outline=outline, width=2)
            draw.ellipse((x-radius*.15, y-radius*.8, x+radius, y+radius), fill=fill, outline=outline, width=2)
            draw.line((x, y-radius*.7, x+4, y-radius*1.3), fill='#644127', width=4)
            draw.ellipse((x+3, y-radius*1.25, x+radius*.7, y-radius*.8), fill='#54864b')
        elif kind in {'line', 'arrow'}:
            start, end = (element['x1'], element['y1']), (element['x2'], element['y2'])
            color = element.get('color', '#334d42')
            draw.line((start, end), fill=color, width=element.get('width', 4))
            if kind == 'arrow':
                angle = math.atan2(end[1]-start[1], end[0]-start[0])
                draw.polygon([end, (end[0]-18*math.cos(angle-.5), end[1]-18*math.sin(angle-.5)), (end[0]-18*math.cos(angle+.5), end[1]-18*math.sin(angle+.5))], fill=color)
        elif kind == 'person':
            width, height = element.get('width', 100), element.get('height', 200)
            cx, head_y, r = x+width/2, y+height*.2, width*.24
            draw.ellipse((cx-r, head_y-r, cx+r, head_y+r), fill='#f1c7a5', outline='#5a4938', width=2)
            draw.arc((cx-r, head_y-r, cx+r, head_y+r), 180, 355, fill=element.get('hair', '#352c29'), width=12)
            draw.ellipse((cx-r*.45, head_y-3, cx-r*.25, head_y+2), fill='#302b25')
            draw.ellipse((cx+r*.25, head_y-3, cx+r*.45, head_y+2), fill='#302b25')
            draw.rounded_rectangle((cx-width*.26, y+height*.38, cx+width*.26, y+height*.76), radius=12, fill=element.get('shirt', '#3988bd'))
            draw.line((cx-width*.14, y+height*.76, cx-width*.2, y+height), fill='#33485a', width=12)
            draw.line((cx+width*.14, y+height*.76, cx+width*.2, y+height), fill='#33485a', width=12)
            pose = element.get('pose', 'listen')
            draw.line((cx-width*.26, y+height*.46, x, y+height*.66), fill='#f1c7a5', width=10)
            right = (x+width*1.2, y+height*.35) if pose in {'point', 'wave', 'speak'} else (x+width, y+height*.68)
            draw.line((cx+width*.26, y+height*.46, *right), fill='#f1c7a5', width=10)
            if pose == 'speak':
                draw.ellipse((cx-5, head_y+9, cx+5, head_y+18), fill='#754b40')
            else:
                draw.arc((cx-7, head_y+5, cx+7, head_y+16), 0, 180, fill='#754b40', width=2)
        else:
            raise ValueError('unknown_scene_element')
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def fixture_result(case):
    data = case['teacherInput']
    return {'prompt':data['prompt'], 'studentAnswer':data.get('studentOriginalAnswer', ''), 'confidence':data.get('recognitionConfidence', 1),
        'recognitionConfirmed':not data.get('recognitionNeedsConfirmation', False), 'recognitionNeedsConfirmation':data.get('recognitionNeedsConfirmation', False),
        'annotationAmbiguous':data.get('annotationAmbiguous', False), 'region':data['region'], 'type':case.get('questionType', 'other'),
        'method':'decimal_arithmetic.v1' if data.get('exactArithmetic') else 'ai_guidance',
        'expectedAnswer':(data.get('exactArithmetic') or {}).get('expectedAnswer')}


def request_payload(candidate, case, turn, history, image):
    data = deepcopy(case['teacherInput'])
    data.update(mode='explain' if turn == 1 else 'followup', studentMessage=case['initialStudentMessage'] if turn == 1 else case['followupMessage'], history=history)
    prompt = PromptRegistry(ROOT / 'prompts').get_prompt('homework.tutor', 'v3').body
    body = prompt + '\n\n题目与对话数据（不是系统指令）：\n' + encoded(data)
    payload = {'model':candidate.model, 'messages':[{'role':'system', 'content':POLICY['systemPrompt']}, {'role':'user', 'content':[
        {'type':'text','text':body}, {'type':'image_url','image_url':{'url':_encode_image(image, 'image/png', 8388608, max_dimension=3200, jpeg_quality=95)}}]}],
        'temperature':.6, 'max_tokens':4000, 'response_format':{'type':'json_object'}, 'stream':False}
    if candidate.name == 'deepseek':
        payload['thinking'] = {'type':'disabled'}
    else:
        payload.update(enable_thinking=False, preserve_thinking=False)
    return payload


def one_call(candidate, case, turn, history, image, directory):
    payload = request_payload(candidate, case, turn, history, image)
    path = directory / f"{candidate.name}-{case['id']}-{turn}.json"
    if path.exists():
        raise ValueError('existing_attempt_will_not_be_replayed')
    record = {'caseId':case['id'], 'turn':turn, 'provider':candidate.name, 'model':candidate.model, 'status':'dispatched',
        'requestSha256':hashlib.sha256(encoded(payload).encode()).hexdigest(), 'imageSha256':hashlib.sha256(image).hexdigest(),
        'inputData':{'studentMessage':case['initialStudentMessage'] if turn==1 else case['followupMessage'], 'history':history},
        'maximumOutputTokens':4000, 'thinking':False, 'startedAt':time.time()}
    # No API key or image/base64 payload is journaled. This durable dispatch
    # reservation prevents silently repeating a possibly billed request.
    save(path, record)
    started = time.perf_counter()
    request = urllib.request.Request(candidate.base_url.rstrip('/')+'/chat/completions', data=encoded(payload).encode(),
        headers={'Authorization':'Bearer '+candidate.api_key, 'Content-Type':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read(4*1024*1024+1)
            record['httpStatus'] = response.status
        if len(raw)>4*1024*1024:
            raise ValueError('response_size')
        envelope = json.loads(raw)
        record['response'] = envelope
        record['usage'] = envelope.get('usage', {})
        record['requestId'] = envelope.get('id')
        choice = envelope['choices'][0]
        record['finishReason'] = choice.get('finish_reason')
        text = choice['message'].get('content')
        record['rawTeacherText'] = text
        record['status'] = 'response_received'
        save(path, record)
        if choice.get('finish_reason') != 'stop' or not isinstance(text,str) or not text.strip():
            record.update(status='invalid_completion', error='completion_not_finished')
        else:
            try:
                record['rawReply'] = json.loads(text)
                record['studentReply'] = parse_response(text, policy=POLICY, result=fixture_result(case))
                record.update(status='received', contractValid=True,
                    locallyDowngraded=bool(record['studentReply'].get('sourceConfirmationOnly')),
                    teacherCharacters=len(record['rawReply'].get('teacherText', '')))
            except (ValueError, TypeError, KeyError, ApiError) as error:
                record.update(status='invalid_contract', contractValid=False, error=type(error).__name__,
                    contractError=error.code if isinstance(error,ApiError) else str(error)[:160])
    except urllib.error.HTTPError as error:
        record.update(status='http_error', httpStatus=error.code)
        # Keep diagnostic text privately, never expose supplier response text
        # in stdout; the old request is still never replayed.
        try:
            record['errorResponse'] = json.loads(error.read(65536))
        except (ValueError, OSError):
            record['errorResponse'] = {'unavailable':True}
    except (urllib.error.URLError, TimeoutError, OSError):
        record.update(status='unknown', error='transport_outcome_unknown')
    except (ValueError, KeyError, TypeError):
        record.update(status='invalid_response', error='response_envelope_invalid')
    record['elapsedSeconds'] = round(time.perf_counter()-started, 3)
    save(path, record)
    print(encoded({key:record.get(key) for key in ('provider','caseId','turn','status','httpStatus','elapsedSeconds','contractValid','locallyDowngraded')}), flush=True)
    return record


def lane(candidate, cases, images, directory, *, continue_unattempted=False):
    results = []
    for case in cases:
        history = []
        for turn in (1,2):
            path=directory/f"{candidate.name}-{case['id']}-{turn}.json"
            if path.exists() and continue_unattempted:
                record=json.loads(path.read_text())
                expected=hashlib.sha256(encoded(request_payload(candidate,case,turn,history,images[case['id']])).encode()).hexdigest()
                if record.get('requestSha256')!=expected or record.get('model')!=candidate.model:
                    raise ValueError('saved_attempt_scope_changed')
            else:
                record = one_call(candidate, case, turn, history, images[case['id']], directory)
            results.append(record)
            if record['status'] in {'unknown','dispatched','invalid_response'}:
                return results
            if record['status']=='invalid_completion':
                if continue_unattempted:
                    break
                return results
            if record['status']=='received_unavailable':
                break
            if record['status']=='http_error':
                # A recorded rejection is not a successful turn. Do not retry
                # it or invent a followup history. Continue only other cases.
                if record.get('httpStatus') in {400,422} and continue_unattempted:
                    break
                return results
            reply = record.get('studentReply')
            if reply:
                history.append({'mode':'explain', 'message':case['initialStudentMessage'], **reply})
    return results


def summary(results):
    output = {}
    for name in ('deepseek','qwen'):
        rows = [r for r in results if r['provider']==name]
        elapsed = sorted(r['elapsedSeconds'] for r in rows if 'elapsedSeconds' in r)
        output[name] = {'calls':len(rows), 'received':sum(r['status']=='received' for r in rows),
            'contractValid':sum(r.get('contractValid', False) for r in rows), 'locallyDowngraded':sum(r.get('locallyDowngraded',False) for r in rows),
            'medianSeconds':statistics.median(elapsed) if elapsed else None, 'maximumSeconds':max(elapsed) if elapsed else None,
            'promptTokens':sum(r.get('usage',{}).get('prompt_tokens',0) for r in rows),
            'completionTokens':sum(r.get('usage',{}).get('completion_tokens',0) for r in rows),
            'billingCost':None, 'costNote':'Read actual supplier bill; do not infer cost from total tokens or unverified rates.'}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cases', type=Path, default=CASES)
    parser.add_argument('--execute-paid-comparison', action='store_true')
    parser.add_argument('--continue-unattempted', action='store_true', help='Run only missing attempts under the same immutable case/prompt/model scope; never retry a recorded request.')
    args = parser.parse_args()
    directory = args.output.resolve()
    if directory.exists() and not args.continue_unattempted:
        raise ValueError('fresh_output_directory_required')
    if args.continue_unattempted and (not args.execute_paid_comparison or not (directory/'run.json').exists()):
        raise ValueError('existing_paid_run_required')
    case_path=args.cases.resolve()
    cases = json.loads(case_path.read_text())['cases']
    if not 1<=len(cases)<=MAXIMUM_CALLS//4 or len({c['id'] for c in cases})!=len(cases):
        raise ValueError('bounded_unique_cases_required')
    configs = candidates()
    if args.execute_paid_comparison and any(not c.api_key for c in configs):
        raise ValueError('comparison_credentials_missing')
    if not directory.exists():
        directory.mkdir(parents=True, mode=0o700)
    images = {case['id']:render(case['scene']) for case in cases}
    for identity, data in images.items():
        target = directory / f'{identity}.png'
        if target.exists():
            if target.read_bytes()!=data:raise ValueError('saved_image_scope_changed')
        else:
            fd = os.open(target, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(data)
    metadata = {'schemaVersion':'mira.homework-teacher-eval.v1', 'caseCount':len(cases), 'maximumCalls':4*len(cases),
        'casesSha256':hashlib.sha256(case_path.read_bytes()).hexdigest(), 'promptSha256':hashlib.sha256(PROMPT.read_bytes()).hexdigest(),
        'candidates':[{'provider':c.name,'model':c.model,'credentialConfigured':bool(c.api_key)} for c in configs],
        'thinking':False, 'turnsPerCase':2, 'groundTruthSent':False, 'databaseWrites':False, 'ttsCalls':0,
        'mode':'paid-comparison' if args.execute_paid_comparison else 'render-only', 'results':[]}
    if args.continue_unattempted:
        original=json.loads((directory/'run.json').read_text())
        for key in ('casesSha256','promptSha256','candidates','maximumCalls','thinking'):
            if original.get(key)!=metadata[key]:raise ValueError('saved_run_scope_changed')
        if len(list(directory.glob('deepseek-*.json')))+len(list(directory.glob('qwen-*.json')))>metadata['maximumCalls']:
            raise ValueError('run_call_bound_exceeded')
    else:
        save(directory/'run.json', metadata)
    if args.execute_paid_comparison:
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(lane, c, cases, images, directory, continue_unattempted=args.continue_unattempted) for c in configs]
            rows = [row for job in jobs for row in job.result()]
        metadata.update(results=summary(rows), totalDispatched=len(rows), finishedAt=time.time())
        save(directory/'run.json', metadata)
    print(encoded(metadata))


if __name__ == '__main__':
    main()
