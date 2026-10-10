"""Build labelled, synthetic homework fixtures without a DB or paid Provider.

The caller owns the development-only family, schema checks and one import
transaction. This module writes only to the explicitly supplied private asset
store and returns ordinary row dictionaries. It never imports service_factory,
starts a worker, invents a paid receipt or connects to a database.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
from copy import copy
import hashlib
import io
import json
from pathlib import Path
import re
import wave

from PIL import Image, ImageDraw, ImageFont

from core.errors import ApiError
from services.homework_math import check_item
from services.homework_service import POLICY, canonical, digest, parsed

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'mira.dev-homework-sample.v1'
KINDS = ('prompt', 'hint', 'explanation', 'success', 'retry')

# Existing original maths lessons; their text hashes and Qwen audio are checked
# against the persisted successful formal-audio receipt before any copy is made.
AUDIO_SOURCES = {
    'read': ('stage-WmNYqudzYa', 'action_j6NjClb_',
             '接下来是两题独立挑战。请你自己读题、自己算，完成后再回头看看自己是怎么算出结果的。'),
    'reflect': ('stage-p83SomVEUh', 'action_qdp88Ta_',
                '再想一想：现在我是怎么想的？和一开始比，哪里变了？'),
    'divide_48_80': ('stage-WmNYqudzYa', 'action_Xn-W7K9o',
                    '第二步，求一个数占另一个数的百分之几。看这里：48÷80=0.6，再换成百分数就是60%。'),
    'divide_1_4': ('stage-WmNYqudzYa', 'action_J20iNKHh',
                  '看中间这条链条：四分之一等于零点二五，也等于百分之二十五。这就是从分数走到百分数的完整路径。'),
}
QUESTIONS = (
    {'prompt': '48 ÷ 80 =', 'studentAnswer': '0.8', 'explanationClip': 'divide_48_80'},
    {'prompt': '1 ÷ 4 =', 'studentAnswer': '0.5', 'explanationClip': 'divide_1_4'},
)


@dataclass(frozen=True)
class VerifiedClip:
    text: str
    body: bytes
    sha256: str
    duration_ms: int
    receipt: dict
    source_classroom: str
    source_action: str


def existing_qwen_clips(repository_root: str | Path = ROOT):
    """Return verified clips and explicit gaps. No fallback or synthesis."""
    runtime = Path(repository_root) / 'openmaic-runtime/.runtime/OpenMAIC/data'
    jobs = {}
    for path in sorted((runtime / 'formal-audio/jobs/tts').glob('*.json')):
        try:
            row = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        key = (row.get('classroomId'), row.get('actionId'))
        if key in {(source[0], source[1]) for source in AUDIO_SOURCES.values()}:
            jobs.setdefault(key, []).append(row)
    clips, gaps = {}, []
    for name, (classroom, action_id, expected_text) in AUDIO_SOURCES.items():
        try:
            document = json.loads((runtime / 'classrooms' / f'{classroom}.json').read_text())
            action = next(a for scene in document['scenes'] for a in scene.get('actions', [])
                          if a.get('id') == action_id)
            actual_text = action.get('text') or action.get('content')
            if actual_text != expected_text:
                raise ValueError('source_text_changed')
            expected_hash = hashlib.sha256(expected_text.encode()).hexdigest()
            receipts = [r for r in jobs.get((classroom, action_id), [])
                        if r.get('state') == 'succeeded' and r.get('providerId') == 'qwen-tts'
                        and r.get('subject') == 'math' and r.get('voiceId') == 'Ethan'
                        and r.get('fallbackUsed') is False and r.get('textSha256') == expected_hash]
            if not receipts:
                raise ValueError('matching_qwen_receipt_missing')
            receipt = sorted(receipts, key=lambda r: str(r.get('completedAt', '')), reverse=True)[0]
            filename = receipt.get('assetFileName', '')
            if not re.fullmatch(r'mirawav_[a-f0-9]+\.wav', filename):
                raise ValueError('source_asset_name_invalid')
            body = (runtime / 'formal-audio/assets' / filename).read_bytes()
            audio_hash = hashlib.sha256(body).hexdigest()
            if audio_hash != receipt.get('audioSha256') or len(body) != receipt.get('sizeBytes'):
                raise ValueError('source_audio_hash_mismatch')
            with wave.open(io.BytesIO(body), 'rb') as audio:
                if audio.getnframes() <= 0 or audio.getframerate() <= 0:
                    raise ValueError('source_audio_empty')
                duration = round(audio.getnframes() * 1000 / audio.getframerate())
            clips[name] = VerifiedClip(expected_text, body, audio_hash, duration, receipt, classroom, action_id)
        except (OSError, ValueError, KeyError, StopIteration, TypeError, wave.Error) as exc:
            gaps.append({'clip': name, 'reason': str(exc) if isinstance(exc, ValueError) else type(exc).__name__,
                         'requiredKinds': ['prompt'] if name == 'read' else
                         ['hint', 'retry'] if name == 'reflect' else ['explanation', 'success']})
    return clips, gaps


def _font(size, font_file=None):
    candidates = [font_file] if font_file else [
        '/System/Library/Fonts/STHeiti Light.ttc',
        '/System/Library/Fonts/Supplemental/Songti.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(str(candidate), size)
    raise ValueError('A local CJK font is required to draw the labelled original sample.')


def original_worksheet_page(page_number, *, font_file=None):
    """Two original, high-resolution pages with explicitly simulated handwriting."""
    if page_number not in (1, 2):
        raise ValueError('The sample has exactly two pages.')
    question = QUESTIONS[page_number - 1]
    width, height = 1200, 1600
    image = Image.new('RGB', (width, height), '#fffcf5')
    draw = ImageDraw.Draw(image)
    ink, muted, rule = '#304844', '#66766f', '#dce3d9'
    draw.rounded_rectangle((70, 65, 1130, 185), radius=20, fill='#edf1e7')
    draw.text((105, 96), '体验数据 · 原创数学试卷', font=_font(40, font_file), fill=ink)
    draw.text((92, 240), '除法与小数', font=_font(64, font_file), fill=ink)
    draw.text((95, 338), '请把计算结果写成小数。', font=_font(32, font_file), fill=muted)
    draw.text((95, 400), f'第 {page_number} 题', font=_font(30, font_file), fill=ink)
    draw.line((95, 455, 1105, 455), fill=rule, width=3)
    draw.text((115, 505), question['prompt'], font=_font(72, font_file), fill=ink)
    draw.text((720, 505), question['studentAnswer'], font=_font(72, font_file), fill='#486894')
    draw.line((704, 605, 1060, 605), fill=rule, width=3)
    draw.text((720, 625), '模拟作答（预设）', font=_font(25, font_file), fill=muted)
    draw.text((100, 790), '草稿区', font=_font(32, font_file), fill=ink)
    for y in range(865, 1216, 70):
        draw.line((100, y, 1100, y), fill=rule, width=2)
    draw.text((98, 1290), '订正时可听老师讲小数与百分数的联系。', font=_font(28, font_file), fill=muted)
    draw.text((98, 1380), '测试合成识别结果，不是真实孩子的学习记录。', font=_font(27, font_file), fill=muted)
    draw.line((95, 1460, 1105, 1460), fill=rule, width=2)
    draw.text((95, 1500), f'MIRA · SAMPLE  /  {page_number} OF 2', font=_font(24, font_file), fill=muted)
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue(), {'width': width, 'height': height,
        'region': {'x': .08, 'y': .30, 'width': .84, 'height': .14}}


def build_dev_homework_sample(*, asset_store, family_id, child_id, sample_id, created_at,
                              repository_root=ROOT, grade_code='primary_6', font_file=None):
    """Prepare one two-page ready fixture; return rows for the caller's transaction.

    Use a NEW development test child. The caller must verify the child belongs
    to family_id, require a development environment and reject an existing
    conflicting sample id. Call again with another sample_id for a report
    example; create completion by using HomeworkService.student_answer rather
    than inventing correction evidence here.
    """
    if grade_code != 'primary_6':
        raise ValueError('This reused narration sample is restricted to the dedicated grade-6 test child.')
    if any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', v)
           for v in (family_id, child_id, sample_id)) or type(created_at) is not int or created_at <= 0:
        raise ValueError('Explicit test family, child, sample identity and timestamp are required.')
    clips, gaps = existing_qwen_clips(repository_root)
    metadata = {'schemaVersion': SCHEMA, 'sampleId': sample_id, 'syntheticFixture': True,
        'recognitionSource': 'synthetic_fixture', 'providerCalls': 0, 'audioCalls': 0,
        'audioPolicy': 'Reuse unchanged Qwen Ethan recordings. Reflection is a generic hint; success repeats the correct calculation. The original explanation includes percentage extension.',
        'audioGaps': gaps, 'gradeCode': grade_code, 'assetKeys': []}
    if gaps:
        return {'ready': False, 'rows': {}, 'evidenceInputs': [], 'metadata': metadata}
    identity = 'hw_' + digest([SCHEMA, family_id, child_id, sample_id])[:32]
    scope = {'schema': SCHEMA, 'sampleId': sample_id, 'familyId': family_id, 'childId': child_id,
             'gradeCode': grade_code, 'recognitionSource': 'synthetic_fixture'}
    submission = {'id': identity, 'family_id': family_id, 'child_id': child_id, 'grade_code': grade_code,
        'subject': 'math', 'title': '体验试卷 · 除法与小数', 'source': 'synthetic_fixture',
        'idempotency_key': 'dev-homework:' + digest(scope)[:56], 'request_sha256': digest(scope),
        'revision': 3, 'status': 'ready', 'consent_at': created_at, 'error_code': None,
        'created_at': created_at, 'updated_at': created_at, 'deleted_at': None}
    rows = {'homework_submissions': [submission], 'homework_pages': [], 'homework_items': [],
            'homework_item_revisions': []}
    evidence = []
    for index, question in enumerate(QUESTIONS):
        body, page_spec = original_worksheet_page(index + 1, font_file=font_file)
        page_id = 'hwp_' + digest([identity, 'page', index])[:32]
        item_id = 'hwi_' + digest([identity, 'item', index])[:56]
        storage = asset_store.put(body, namespace=identity)
        metadata['assetKeys'].append(storage)
        rows['homework_pages'].append({'id': page_id, 'submission_id': identity, 'upload_key': f'dev-page-{index + 1}',
            'content_sha256': hashlib.sha256(body).hexdigest(), 'storage_key': storage, 'mime_type': 'image/png',
            'width': page_spec['width'], 'height': page_spec['height'], 'page_order': index, 'rotation': 0,
            'crop_json': None, 'status': 'ready', 'error_code': None, 'created_at': created_at})
        result = check_item({**question, 'type': 'arithmetic', 'confidence': 1.0,
            'annotationAmbiguous': False, 'region': page_spec['region']},
            grade=grade_code, subject='math', policy=POLICY, confirmed=True)
        if result['status'] != 'incorrect' or result['answerMode'] != 'numeric':
            raise ValueError('The deterministic sample policy changed; inspect before importing.')
        roles = {'prompt': 'read', 'hint': 'reflect', 'explanation': question['explanationClip'],
                 'success': question['explanationClip'], 'retry': 'reflect'}
        result.update(syntheticFixture=True, recognitionSource='synthetic_fixture',
            recognitionNote='测试合成识别结果，未调用识别模型。', confidence=None,
            voiceTexts={kind: clips[name].text for kind, name in roles.items()},
            hint=clips['reflect'].text,
            explanation='计算的小数结果：' + result['expectedAnswer'] + '。老师录音还会讲到对应的百分数。',
            developmentAudioNote=metadata['audioPolicy'])
        media = {}
        for kind in KINDS:
            clip = clips[roles[kind]]
            key = asset_store.put(clip.body, namespace=identity, suffix='wav')
            metadata['assetKeys'].append(key)
            media[kind] = {'status': 'ready', 'storageKey': key, 'mimeType': 'audio/wav',
                'sha256': clip.sha256, 'durationMs': clip.duration_ms,
                'providerId': 'qwen-tts', 'modelId': clip.receipt['modelId'], 'voiceId': clip.receipt['voiceId'],
                'receiptId': clip.receipt['requestId'],
                'provenance': {'kind': 'existing_qwen_recording', 'sourceClassroomId': clip.source_classroom,
                    'sourceActionId': clip.source_action, 'textSha256': clip.receipt['textSha256'],
                    'recordingChanged': False, 'newProviderCall': False}}
        rows['homework_items'].append({'id': item_id, 'submission_id': identity, 'page_id': page_id,
            'revision': 1, 'analysis_revision': 3, 'item_order': 0, 'result_json': canonical(result),
            'media_json': canonical(media), 'correction_json': '{}', 'updated_at': created_at})
        rows['homework_item_revisions'].append({'item_id': item_id, 'revision': 1, 'submission_id': identity,
            'result_json': canonical(result), 'reason': 'synthetic_fixture', 'created_at': created_at})
        evidence.append({'family_id': family_id, 'child_id': child_id, 'source_kind': 'homework',
            'source_id': identity, 'event_key': f'{item_id}:1',
            'question': {'id': item_id, 'version': '1', 'subject': 'math', 'gradeCode': grade_code,
                'knowledgeId': result['knowledgeId'], 'knowledgeLabel': result['knowledgeLabel'],
                'prompt': result['prompt'], 'correctAnswer': result['expectedAnswer'], 'explanation': result['explanation'],
                'private': True, 'syntheticFixture': True},
            'answer': result['studentAnswer'], 'correct': False, 'occurred_at': created_at,
            'independent': None, 'confidence': None, 'confirmed': True,
            'diagnosis': {'scope': 'synthetic_fixture', 'syntheticFixture': True,
                'method': 'decimal_arithmetic.v1', 'recognitionProvider': None, 'masteryClaim': False}})
    metadata['assetKeys'] = sorted(set(metadata['assetKeys']))
    metadata.update(submissionId=identity, questionCount=2, pageCount=2,
                    nextStep='Import only into the dedicated dev child; complete a second sample through normal student_answer calls.')
    return {'ready': True, 'rows': rows, 'evidenceInputs': evidence, 'metadata': metadata}


class _ScopedDemoStudentAuth:
    """An in-process fixture principal, never installed on the live service."""
    def __init__(self, child, token):
        self.child, self.token = child, token

    def authenticate(self, token):
        if token != self.token:
            raise ApiError('demo_scope_invalid', '体验数据范围无效', 403)
        return {'principal': {'family_id': self.child['family_id'], 'child_id': self.child['id']}}


def seed_homework_samples(conn, *, child, service, now, seed_namespace):
    """Seed two labelled examples in the caller's development-only transaction.

    The caller must verify local development DB identity and ownership of the
    dedicated test family before calling. This function neither commits nor
    opens a connection. Existing rows (including deletion and learner progress)
    are preserved; an identity conflict fails the caller's whole transaction.
    Only the newly created completed example is answered through the real
    HomeworkService.student_answer method with a private in-process principal.
    """
    if (type(now) is not int or now <= 0 or not isinstance(seed_namespace, str)
            or not re.fullmatch(r'[A-Za-z0-9_-]{3,80}', seed_namespace)):
        raise ValueError('Explicit stable demo namespace and timestamp required.')
    if not service.enabled or not service.evidence_enabled:
        raise ValueError('Homework and learning evidence must be enabled before seeding.')
    actual = service.repository.child(conn, child['family_id'], child['id'], lock=True)
    if not actual or actual['grade_code'] != 'primary_6' or child.get('grade_code') != 'primary_6':
        raise ValueError('Homework demo requires the dedicated grade-six test child.')
    child = dict(actual)
    token = 'demo-helper:' + digest([seed_namespace, child['family_id'], child['id']])
    scoped = copy(service)
    scoped.repository = copy(service.repository)
    scoped.repository.transaction = lambda: nullcontext(conn)
    scoped.student_auth = _ScopedDemoStudentAuth(child, token)
    scoped.clock = lambda: now
    # Even accidental future fixture code cannot dispatch through the copy.
    scoped.provider = scoped.audio = scoped.capture_service = None
    scoped.processing_enabled = False
    prepared = []
    for scenario in ('pending', 'completed'):
        sample_id = seed_namespace + ':' + scenario
        identity = 'hw_' + digest([SCHEMA, child['family_id'], child['id'], sample_id])[:32]
        scope = {'schema': SCHEMA, 'sampleId': sample_id, 'familyId': child['family_id'],
                 'childId': child['id'], 'gradeCode': 'primary_6', 'recognitionSource': 'synthetic_fixture'}
        expected_key = 'dev-homework:' + digest(scope)[:56]
        existing = conn.execute('SELECT * FROM homework_submissions WHERE id=? FOR UPDATE', (identity,)).fetchone()
        key_owner = conn.execute('SELECT id FROM homework_submissions WHERE family_id=? AND child_id=? AND idempotency_key=?',
            (child['family_id'], child['id'], expected_key)).fetchone()
        if key_owner and key_owner['id'] != identity:
            raise ValueError('Refusing a conflicting development homework identity.')
        if existing:
            if any(existing[key] != value for key, value in {
                'family_id': child['family_id'], 'child_id': child['id'], 'grade_code': 'primary_6',
                'source': 'synthetic_fixture', 'idempotency_key': expected_key,
                'request_sha256': digest(scope),
            }.items()):
                raise ValueError('Refusing to overwrite unrelated homework data.')
            prepared.append((scenario, dict(existing), None))
            continue
        fixture = build_dev_homework_sample(asset_store=service.store, family_id=child['family_id'],
            child_id=child['id'], sample_id=sample_id, created_at=now)
        if not fixture['ready']:
            raise ValueError('Existing teacher audio is unavailable: ' + canonical(fixture['metadata']['audioGaps']))
        row = fixture['rows']['homework_submissions'][0]
        row['title'] = {'pending': '体验试卷 · 等你订正', 'completed': '体验试卷 · 订正报告'}[scenario]
        prepared.append((scenario, row, fixture))
    from services.learning_evidence_service import record_answer
    results = []
    for scenario, row, fixture in prepared:
        if fixture:
            for table, values in fixture['rows'].items():
                for value in values:
                    columns = tuple(value)
                    conn.execute(f'INSERT INTO {table} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',
                                 tuple(value[column] for column in columns))
            for evidence in fixture['evidenceInputs']:
                record_answer(conn, **evidence)
            if scenario == 'completed':
                for index, item in enumerate(fixture['rows']['homework_items']):
                    result = parsed(item['result_json'])
                    scoped.student_answer(token, row['id'], item['id'], {
                        'itemRevision': item['revision'], 'answer': result['expectedAnswer'],
                        'idempotencyKey': f'{seed_namespace}:completed:answer:{index}',
                    })
        if row['deleted_at'] is None:
            view = scoped._view(conn, row)['submission']
            summary, ready = view['summary'], view['readyForStudent']
        else:
            summary, ready = None, False
        results.append({'id': row['id'], 'title': row['title'], 'scenario': scenario, 'status': row['status'],
            'summary': summary, 'readyForStudent': ready, 'deleted': row['deleted_at'] is not None,
            'path': '/learning/homework/' + row['id'], 'created': fixture is not None})
    return {'submissions': results, 'source': {'schemaVersion': SCHEMA, 'recognitionSource': 'synthetic_fixture',
        'syntheticFixture': True, 'providerCalls': 0, 'audioCalls': 0, 'gradeCode': 'primary_6',
        'audioPolicy': 'Existing verified Qwen recordings; generic reflection hints and unchanged percentage explanations.'}}
