"""Immutable operator-preview audio identities and versioned local ASR checks.

Pure helpers: no provider, filesystem writes or database access. Existing plans
are interpreted, never upgraded. Policies require explicit server registration.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from content.textbook_audio_language import ENGLISH_AUTO_LANGUAGE_POLICY, ENGLISH_AUTO_LANGUAGE_POLICY_SHA256
from content.textbook_catalog import digest
from content.textbook_pinyin_pronunciation import (PLAN_SCHEMA as PINYIN_SCHEMA,
    policy_for_plan, select_policy, pronunciation_identity, validate_formal_receipt,
    registered_policy, provider_body, ZCS_POLICY_VERSION, ZCS_V2_POLICY_VERSION)
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient


SCHEMA = 'mira.textbook.preview-audio-plan.v2'
# Reuse the formal author's structured workload ceiling, without changing any
# historical plan fields or pronunciation/comparison policy identities.
MAX_SPEECH_ACTIONS = OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CLASSROOM_CONTRACT['speechActions']['total']['max']
POLICY = json.loads(Path(__file__).with_name('textbook_preview_audio_policy.v2.json').read_text())
SHA = re.compile(r'[a-f0-9]{64}\Z')
BASE_FIELDS = {'previewKey', 'classroomSha256', 'coreSha256', 'teacher'}
V2_FIELDS = BASE_FIELDS | {'schemaVersion', 'binding', 'subject', 'providerLanguagePolicy',
                         'providerLanguagePolicySha256', 'comparisonPolicy', 'comparisonPolicySha256'}


def fail(message):
    raise ApiError('textbook_preview_audio_contract_invalid', message, 409)


def _binding(frozen):
    keys = ('editionId', 'alignmentRevisionId', 'manifestSha256', 'nodeId', 'gradeCode', 'subject')
    if any(not isinstance(frozen.get(k), str) or not frozen[k] for k in keys):
        fail('冻结的教材与学科身份不完整')
    if frozen['subject'] not in POLICY['subjects'] or not SHA.fullmatch(frozen['manifestSha256']):
        fail('冻结的教材学科或摘要无效')
    return {k: frozen[k] for k in keys}


def _language(subject):
    return deepcopy(ENGLISH_AUTO_LANGUAGE_POLICY if subject == 'english' else POLICY['mandarinLanguagePolicy'])


def new_audio_plan(*, preview_key, classroom_sha256, core_sha256, frozen_input):
    binding = _binding(frozen_input)
    subject = binding['subject']
    configured = POLICY['subjects'][subject]
    language = _language(subject)
    comparison = deepcopy(POLICY['comparisons'][configured['comparison']])
    plan = {'schemaVersion': SCHEMA, 'previewKey': preview_key,
            'classroomSha256': classroom_sha256, 'coreSha256': core_sha256,
            'binding': binding, 'subject': subject, 'teacher': deepcopy(configured['teacher']),
            'providerLanguagePolicy': language, 'providerLanguagePolicySha256': digest(language),
            'comparisonPolicy': comparison, 'comparisonPolicySha256': digest(comparison)}
    resolve_audio_contract(plan, frozen_input)
    return plan


def _pinyin_teacher(policy):
    teacher = deepcopy(POLICY['subjects']['chinese']['teacher'])
    teacher['voiceId'] = policy['voiceId']
    teacher['tts'].update(providerId=policy['providerId'], modelId=policy['modelId'])
    return teacher


def _pinyin_language(policy):
    return {'policyVersion': policy['policyVersion'],
            'tts': {'providerId': policy['providerId'], 'modelId': policy['modelId'],
                    'languageHints': ['zh']}, 'asr': deepcopy(POLICY['mandarinLanguagePolicy']['asr'])}


def new_pinyin_audio_plan(*, preview_key, classroom_sha256, core_sha256, frozen_input,
                          parent_plan, revision_id):
    resolve_audio_contract(parent_plan, frozen_input)
    if parent_plan.get('schemaVersion') != SCHEMA or parent_plan.get('subject') != 'chinese':
        fail('拼音配音修订只能源自原 v2 中文合同')
    policy = select_policy(_binding(frozen_input))
    plan = new_audio_plan(preview_key=preview_key, classroom_sha256=classroom_sha256,
                          core_sha256=core_sha256, frozen_input=frozen_input)
    plan.update(schemaVersion=PINYIN_SCHEMA, teacher=_pinyin_teacher(policy),
                providerLanguagePolicy=_pinyin_language(policy),
                providerLanguagePolicySha256=digest(_pinyin_language(policy)),
                pronunciationPolicy=policy, pronunciationPolicySha256=digest(policy),
                parentPlanSha256=digest(parent_plan), revisionId=revision_id)
    resolve_audio_contract(plan, frozen_input)
    return plan


def resolve_audio_contract(plan, frozen_input=None):
    """Validate both formats without mutating the hash input of legacy requests."""
    if not isinstance(plan, dict) or not BASE_FIELDS.issubset(plan):
        fail('配音计划不完整')
    if any(not isinstance(plan[k], str) or not SHA.fullmatch(plan[k])
           for k in ('previewKey', 'classroomSha256', 'coreSha256')):
        fail('配音计划摘要无效')
    legacy = 'schemaVersion' not in plan
    pinyin = plan.get('schemaVersion') == PINYIN_SCHEMA
    if legacy:
        # Older narration amendments had subject/revisionId but no schema.
        if set(plan) - BASE_FIELDS - {'subject', 'revisionId'}:
            fail('旧配音计划不能追加新策略字段')
        subject = plan.get('subject', 'chinese')
        if subject != 'chinese' or plan['teacher'] != POLICY['subjects']['chinese']['teacher']:
            fail('旧配音计划只能沿用原中文教师身份')
        if frozen_input is not None and frozen_input.get('subject') != subject:
            fail('旧配音计划与教材学科不一致')
        configured = POLICY['legacy']
        language = None
        comparison = POLICY['comparisons']['literal-v1']
    else:
        fields = V2_FIELDS | ({'pronunciationPolicy', 'pronunciationPolicySha256',
                              'revisionId', 'parentPlanSha256'} if pinyin else set())
        if (plan.get('schemaVersion') not in {SCHEMA, PINYIN_SCHEMA} or not fields.issubset(plan)
                or set(plan) - fields - {'revisionId', 'parentPlanSha256'}):
            fail('不支持的配音计划版本或字段')
        subject = plan['subject']
        configured = POLICY['subjects'].get(subject)
        pinyin_policy = policy_for_plan(plan) if pinyin else None
        expected_teacher = _pinyin_teacher(pinyin_policy) if pinyin else (configured or {}).get('teacher')
        if (not configured or plan['teacher'] != expected_teacher or (pinyin and subject != 'chinese')
                or plan['binding'] != _binding(plan['binding']) or plan['binding']['subject'] != subject
                or (frozen_input is not None and plan['binding'] != _binding(frozen_input))):
            fail('配音计划的教材或教师身份不一致')
        language = _pinyin_language(pinyin_policy) if pinyin else _language(subject)
        comparison = POLICY['comparisons'][configured['comparison']]
        if (plan['providerLanguagePolicy'] != language or plan['providerLanguagePolicySha256'] != digest(language)
                or plan['comparisonPolicy'] != comparison or plan['comparisonPolicySha256'] != digest(comparison)):
            fail('已冻结的语言或识别比较策略不一致')
        if pinyin:
            configured = {**configured, 'ttsPrefix': 'tbptts1_', 'asrPrefix': 'tbpasr1_'}
        if 'parentPlanSha256' in plan and not SHA.fullmatch(str(plan['parentPlanSha256'])):
            fail('旁白修订来源摘要无效')
        if ('parentPlanSha256' in plan) != ('revisionId' in plan):
            fail('旁白修订身份不完整')
    if 'revisionId' in plan and not SHA.fullmatch(str(plan['revisionId'])):
        fail('旁白修订编号无效')
    return {'legacy': legacy, 'subject': subject, 'teacher': deepcopy(plan['teacher']),
            'ttsPrefix': configured['ttsPrefix'], 'asrPrefix': configured['asrPrefix'],
            'providerLanguagePolicy': deepcopy(language), 'comparisonPolicy': deepcopy(comparison),
            'planSha256': digest(plan)}


def tts_request_id(plan, scene_id, action_id, text, *, attempt=1):
    contract = resolve_audio_contract(plan)
    if type(attempt) is not int or attempt < 1:
        fail('配音尝试编号无效')
    segment = {'plan': plan, 'sceneId': scene_id, 'actionId': action_id, 'text': text.strip()}
    if plan.get('schemaVersion') == PINYIN_SCHEMA:
        segment['pronunciationProfile'] = pronunciation_identity(
            text.strip(), policy_version=policy_for_plan(plan)['policyVersion'])
    if attempt > 1:
        segment['attempt'] = attempt
    return contract['ttsPrefix'] + digest(segment)


def valid_tts_request_id(plan, request_id):
    prefix = resolve_audio_contract(plan)['ttsPrefix']
    return isinstance(request_id, str) and re.fullmatch(re.escape(prefix) + r'[a-f0-9]{64}', request_id) is not None


def asr_request_id(plan, tts_id, audio_sha256):
    contract = resolve_audio_contract(plan)
    if not valid_tts_request_id(plan, tts_id) or not SHA.fullmatch(str(audio_sha256)):
        fail('配音识别的原音频身份无效')
    # Comparison-policy changes are local computations, never another ASR call.
    return contract['asrPrefix'] + digest({'tts': tts_id, 'audio': audio_sha256})


def check_receipt_language_policy(plan, receipt):
    contract = resolve_audio_contract(plan)
    if plan.get('schemaVersion') == PINYIN_SCHEMA:
        if receipt.get('providerLanguagePolicy') is not None:
            fail('拼音配音不能混入其他语言合同')
        if receipt.get('status') == 'succeeded':
            validate_formal_receipt(receipt, policy_version=policy_for_plan(plan)['policyVersion'])
        return
    if contract['subject'] != 'english':
        if receipt.get('providerLanguagePolicy') is not None:
            fail('非英语音频携带了不匹配的语言策略')
        return
    if receipt.get('status') != 'succeeded':
        return
    actual = receipt.get('providerLanguagePolicy')
    if (not isinstance(actual, dict) or set(actual) != {'policyVersion', 'policySha256', 'providerBodySha256'}
            or actual['policyVersion'] != ENGLISH_AUTO_LANGUAGE_POLICY['policyVersion']
            or actual['policySha256'] != ENGLISH_AUTO_LANGUAGE_POLICY_SHA256
            or not SHA.fullmatch(str(actual['providerBodySha256']))):
        fail('英语音频没有确认冻结的自动语言策略')


def check_receipt_pronunciation(plan, receipt, text):
    resolve_audio_contract(plan)
    if plan.get('schemaVersion') == PINYIN_SCHEMA and receipt.get('status') == 'succeeded':
        validate_formal_receipt(receipt, text.strip(), policy_version=policy_for_plan(plan)['policyVersion'])


def pronunciation_client_options(plan):
    """Internal transport selector; never part of the HTTP or hash payload."""
    resolve_audio_contract(plan)
    return ({'pronunciation_policy_version': policy_for_plan(plan)['policyVersion']}
            if plan.get('schemaVersion') == PINYIN_SCHEMA else {})


def audit_contract_identity(plan):
    contract = resolve_audio_contract(plan)
    result = {'planSha256': contract['planSha256'], 'subject': contract['subject'],
            'teacher': contract['teacher'],
            'providerLanguagePolicySha256': plan['providerLanguagePolicySha256'],
            'comparisonPolicySha256': plan['comparisonPolicySha256']}
    if plan.get('schemaVersion') == PINYIN_SCHEMA:
        result['pronunciationPolicySha256'] = plan['pronunciationPolicySha256']
    return result



def policy_revision_plan(plan, policy_version):
    """The only registered policy amendment is ZCS's Chinese override removal.

    No default, transport, Latin mapping or comparison policy can change here.
    Old plans remain v1; the returned object is only a new request-plan candidate.
    """
    resolve_audio_contract(plan)
    old = policy_for_plan(plan)
    new = registered_policy(policy_version)
    if (old['policyVersion'], new['policyVersion']) != (ZCS_POLICY_VERSION, ZCS_V2_POLICY_VERSION):
        fail('仅允许明确登记的 ZCS 中文覆盖删除修订')
    operational = set(old) - {'policyVersion', 'words', 'approvalBoundary'}
    if (set(old) != set(new) or any(old[k] != new[k] for k in operational)
            or old.get('words') != {'句子': {'ph': 'ju4 zi5', 'carrier': '句子'}} or new.get('words') != {}):
        fail('修订不能改变声母音节、教师、模型或请求参数')
    revised = {**deepcopy(plan), 'pronunciationPolicy': new, 'pronunciationPolicySha256': digest(new),
               'providerLanguagePolicy': _pinyin_language(new),
               'providerLanguagePolicySha256': digest(_pinyin_language(new))}
    resolve_audio_contract(revised, plan['binding'])
    return revised


def validate_child_request_plan(plan, child, *, text=None):
    """Validate a portable immutable child without relabelling parent audio."""
    resolve_audio_contract(child, plan.get('binding'))
    expected = deepcopy(plan)
    changed_policy = child.get('pronunciationPolicySha256') != plan.get('pronunciationPolicySha256')
    if changed_policy:
        expected = policy_revision_plan(plan, policy_for_plan(child)['policyVersion'])
    expected.update(parentPlanSha256=digest(plan), revisionId=child.get('revisionId'),
                    classroomSha256=child.get('classroomSha256'), coreSha256=child.get('coreSha256'))
    if child != expected or not SHA.fullmatch(str(child.get('revisionId'))):
        fail('子请求计划不能改变冻结的教材、教师、比较合同或来源')
    if changed_policy and text is not None and provider_body(text, policy_version=policy_for_plan(plan)['policyVersion']) == provider_body(text, policy_version=policy_for_plan(child)['policyVersion']):
        fail('政策修订只能重配提供方请求正文确实变化的段落')
    return child


def audit_segment_plan(plan, action, entry, *, scene_id=None):
    """New mixed-policy entries carry their exact child request, not a claimed version."""
    child = entry.get('requestPlan')
    if child is None:
        if 'ttsAttempt' in entry:
            fail('审核不能缺失对应子请求计划')
        return plan
    validate_child_request_plan(plan, child, text=action['text'].strip())
    attempt = entry.get('ttsAttempt')
    if (child.get('pronunciationPolicySha256') == plan.get('pronunciationPolicySha256')
            or type(attempt) is not int or attempt < 1
            or action['audioId'] != tts_request_id(child, scene_id or entry.get('sceneId'), action['id'], action['text'], attempt=attempt)):
        fail('混合政策审核必须精确对应实际子请求和尝试编号')
    return child


def validate_v2_audit_segment(plan, action, entry, *, scene_id=None):
    """Recompute policy evidence from the saved raw receipt, never trust passed."""
    request_plan = audit_segment_plan(plan, action, entry, scene_id=scene_id)
    response = entry.get('asr', {})
    transcript = entry.get('transcript')
    expected = action['text'].strip()
    comparison = compare_transcript(plan, expected, transcript)
    expected_request = asr_request_id(plan, action['audioId'], entry.get('audioSha256'))
    if 'asrTerminalRecovery' in entry:
        if plan.get('schemaVersion') == PINYIN_SCHEMA or resolve_audio_contract(plan)['legacy']:
            fail('此终止识别恢复不适用于旧合同或拼音专用合同')
        from content.textbook_asr_terminal_recovery import validate as validate_terminal_recovery
        expected_request = validate_terminal_recovery(entry, plan_sha256=digest(plan),
            action=action, scene_id=scene_id or entry.get('sceneId'),
            expected_request_id=expected_request)
    if (not isinstance(transcript, str) or response.get('status') != 'succeeded'
            or response.get('requestId') != expected_request
            or response.get('transcript') != transcript
            or response.get('transcriptSha256') != hashlib.sha256(transcript.encode()).hexdigest()
            or entry.get('actionId') != action['id'] or (scene_id is not None and entry.get('sceneId') != scene_id)
            or entry.get('ttsRequestId') != action['audioId'] or entry.get('text') != expected
            or entry.get('textSha256') != hashlib.sha256(expected.encode()).hexdigest()
            or entry.get('comparison') != comparison or entry.get('similarityBps') != comparison['similarityBps']):
        fail('审核段落与原音频、原文或冻结的比较策略不一致')
    check_receipt_language_policy(request_plan, response)
    if plan.get('schemaVersion') == PINYIN_SCHEMA:
        validate_formal_receipt(response, expected, policy_version=policy_for_plan(request_plan)['policyVersion'])
    return comparison['passed']


def revision_audio_plan(plan, *, revision_id, classroom_sha256, core_sha256, frozen_input, policy_version=None):
    contract = resolve_audio_contract(plan, frozen_input)
    if contract['legacy']:
        # Keep the existing repair adapter's exact legacy request hash shape.
        revised = {'previewKey': plan['previewKey'], 'revisionId': revision_id,
                   'classroomSha256': classroom_sha256, 'coreSha256': core_sha256,
                   'teacher': deepcopy(plan['teacher']), 'subject': contract['subject']}
    else:
        revised = {**deepcopy(plan), 'revisionId': revision_id, 'parentPlanSha256': digest(plan),
                   'classroomSha256': classroom_sha256, 'coreSha256': core_sha256}
    if policy_version is not None:
        revised = policy_revision_plan(revised, policy_version)
        validate_child_request_plan(plan, revised)
    resolve_audio_contract(revised, frozen_input)
    return revised


def _normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', str(text or '')).casefold()
                   if unicodedata.category(c)[:1] in {'L', 'N'})


def _similarity(expected, actual):
    left, right = _normalize(expected), _normalize(actual)
    if not left or not right:
        return 0
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    size = max(len(left), len(right))
    return max(0, (size - previous[-1]) * 10000 // size)


_DIGITS = {c: i for i, c in enumerate('零一二三四五六七八九')}
_DIGITS.update({'〇': 0, '两': 2})
_UNITS = {'十': 10, '百': 100, '千': 1000}
_NUMBER = re.compile(r'(第)?([0-9]+|[零〇一二两三四五六七八九十百千]+)')
_OPERATORS = {'+': '加', '-': '减', '*': '乘', '×': '乘', '/': '除以', '÷': '除以', '=': '等于', '>': '大于', '<': '小于'}
_OPERATOR = re.compile(r'除以|等于|大于|小于|加|减|乘')


def _integer(token):
    if token.isascii() and token.isdigit():
        return str(int(token)) if len(token) == 1 or not token.startswith('0') else 'digits:' + token
    if all(c in _DIGITS for c in token):
        digits = ''.join(str(_DIGITS[c]) for c in token)
        return digits if len(digits) == 1 else 'digits:' + digits
    total = current = 0
    for c in token:
        if c in _DIGITS:
            current = _DIGITS[c]
        else:
            total += (current or 1) * _UNITS[c]
            current = 0
    return str(total + current)


def _math_comparison(text, policy):
    value = unicodedata.normalize('NFKC', str(text or ''))
    # This first-grade policy intentionally does not guess decimals/fractions.
    unsupported = bool(re.search(r'\d\s*[./]\s*\d|\d\s*%|[零一二两三四五六七八九十百千]点[零一二三四五六七八九]|分之', value))
    meaningful = value
    for phrase in policy['nonNumericPhrases']:
        meaningful = meaningful.replace(phrase, '')
    numbers = [['ordinal' if m[1] else 'number', _integer(m[2])] for m in _NUMBER.finditer(meaningful)]
    # Normalize spelling only; quantities and order remain protected separately.
    value = _NUMBER.sub(lambda m: ('第' if m[1] else '') + _integer(m[2]), value)
    for symbol, spoken in _OPERATORS.items():
        meaningful = meaningful.replace(symbol, spoken)
        value = value.replace(symbol, spoken)
    return value, numbers, _OPERATOR.findall(meaningful), unsupported


def compare_transcript(plan, expected, actual):
    """Return reproducible evidence; callers also require a succeeded ASR receipt."""
    contract = resolve_audio_contract(plan)
    policy = contract['comparisonPolicy']
    left, right = str(expected or ''), str(actual or '')
    protected = True
    evidence = {}
    if policy['version'] == 'math-spoken-v1':
        left, ln, lo, lu = _math_comparison(left, policy)
        right, rn, ro, ru = _math_comparison(right, policy)
        protected = ln == rn and lo == ro and not lu and not ru
        evidence = {'expectedNumbers': ln, 'actualNumbers': rn, 'expectedOperators': lo,
                    'actualOperators': ro, 'unsupportedNumericForm': lu or ru}
    elif policy['version'] == 'english-words-v1':
        def words(value):
            return re.findall(r"[a-z]+(?:'[a-z]+)?", unicodedata.normalize('NFKC', value).casefold().replace('’', "'"))
        lw, rw = words(left), words(right)
        protected = lw == rw
        evidence = {'expectedLatinWords': lw, 'actualLatinWords': rw}
    similarity = _similarity(left, right)
    return {'comparisonPolicy': policy['version'], 'comparisonPolicySha256': digest(policy),
            'expectedComparisonText': left, 'actualComparisonText': right,
            'similarityBps': similarity, 'protectedContentMatched': protected,
            'passed': protected and similarity >= policy['minimumSimilarityBps'], **evidence}
