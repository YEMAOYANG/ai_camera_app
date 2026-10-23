"""Verify the exact human-listened AI/EI/UI v1+v4 probe composition.

The composition is deliberately lesson- and policy-specific.  It preserves
all four historical attempts, proves the selected provider/WAV/PCM bytes, and
only authorizes the six probe recipes.  It never approves formal narration.
"""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
from types import MappingProxyType

from content import textbook_pinyin_pronunciation as pronunciation
from content.textbook_catalog import canonical, digest
from core.errors import ApiError
from services.course_file_store import course_bytes


PLAN_SCHEMA = 'mira.operator.phonetic-composite-probe.v1'
REVIEW_SCHEMA = 'mira.textbook.pinyin-initialization-approval.v2-composite-human'
CONFIRMATION_SCHEMA = 'mira.operator.phonetic-probe-user-confirmation.v2-composite'
VALIDATION_SCHEMA = 'mira.operator.composite-probe-validation.v2-human'
RESULT = 'six-probe-composite-human-listening-verified'
LIMIT = ('Exact v1 samples 1-5 plus exact v4 sample 6 are approved only as pronunciation probe recipes. '
         'Every generated formal sentence containing registered pinyin still requires sentence-level ASR '
         'text checking and human listening; ASR cannot establish tone or neutral-tone correctness.')
PROBE_FILES = ('request.json', 'intent.json', 'receipt.json', 'provider-response.json',
               'audio.wav', 'playback.wav', 'playback-validation.json')
VERSIONS = MappingProxyType({
    'aieiui-v1': pronunciation.AIEIUI_POLICY_VERSION,
    'aieiui-v2': pronunciation.AIEIUI_V2_POLICY_VERSION,
    'aieiui-v3': pronunciation.AIEIUI_V3_POLICY_VERSION,
    'aieiui-v4': pronunciation.AIEIUI_V4_POLICY_VERSION,
})
SLOTS = MappingProxyType({
    'ai-final-and-tones': (1, 'aieiui-v1', 'ɑi，āi、ái、ǎi、ài'),
    'ei-final-and-tones': (2, 'aieiui-v1', 'ei，ēi、éi、ěi、èi'),
    'ui-final-and-tones': (3, 'aieiui-v1', 'ui，uī、uí、uǐ、uì'),
    'textbook-spelling-sequences': (
        4, 'aieiui-v1', 'g、āi、gāi；g、u、āi、guāi；l、èi、lèi；t、uǐ、tuǐ'),
    'pai-dui-whole': (5, 'aieiui-v1', 'pái duì'),
    'luo-bo-neutral': (6, 'aieiui-v4', 'luó bo'),
})
V1_LABELS = tuple(SLOTS)
FAILED_VERSIONS = ('aieiui-v2', 'aieiui-v3')
LESSON = MappingProxyType({
    'editionId': 'pep-chinese-g1-upper-2022-standard',
    'alignmentRevisionId': '20260924-directory-3',
    'nodeId': 'u4-l1',
    'gradeCode': 'primary_1',
    'subject': 'chinese',
})
RELATIVE_ROOT = ('output/textbook-operator-lessons/pep-chinese-g1-upper-2022-standard/'
                 'u4-l1/teaching-1/quality-repairs')
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_REPAIRS_ROOT = REPOSITORY_ROOT / RELATIVE_ROOT
EXPECTED_REVIEW = (EXPECTED_REPAIRS_ROOT / 'pinyin-ssml-probe-composition-v1' /
                   'human-approval-before-adoption-binding.json')


def fail(message):
    raise ApiError('textbook_preview_pronunciation_initialization_conflict', message, 409)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, UnicodeError):
        fail('ɑi ei ui 组合小样文件不是有效 JSON')
    if not isinstance(value, dict):
        fail('ɑi ei ui 组合小样文件必须是对象')
    return value


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed
    except (TypeError, ValueError, AttributeError):
        fail('ɑi ei ui 组合小样时间无效')


def sealed(value):
    return (isinstance(value, dict)
            and value.get('selfDigestScope') == 'canonical JSON object excluding sha256'
            and value.get('sha256') == digest({k: v for k, v in value.items() if k != 'sha256'}))


def indexed(items, expected, fields):
    if (not isinstance(items, list) or len(items) != len(expected)
            or any(not isinstance(item, dict) or set(item) != fields for item in items)
            or any(not isinstance(item.get('label'), str) for item in items)
            or {item['label'] for item in items} != set(expected)):
        fail('ɑi ei ui 组合小样必须完整、唯一且只包含固定六段')
    return {item['label']: item for item in items}


def evidence_names():
    names = {
        'evidence/plan.json', 'evidence/human-approval.json',
        'evidence/user-confirmation.json', 'evidence/validation.json',
        'evidence/origins/aieiui-v1/plan.json',
        'evidence/origins/aieiui-v1/human-review.partial.json',
    }
    names |= {f'evidence/origins/aieiui-v1/{label}/{name}'
              for label in V1_LABELS for name in PROBE_FILES}
    for origin in ('aieiui-v2', 'aieiui-v3', 'aieiui-v4'):
        names.add(f'evidence/origins/{origin}/plan.json')
        names |= {f'evidence/origins/{origin}/luo-bo-neutral/{name}' for name in PROBE_FILES}
    names |= {f'evidence/origins/{origin}/machine-audio-audit.json' for origin in FAILED_VERSIONS}
    return names


def read_files(review_path):
    candidate = Path(os.path.abspath(Path(review_path).expanduser()))
    expected = Path(os.path.abspath(EXPECTED_REVIEW))
    if (candidate != expected or candidate.resolve() != expected.resolve()
            or candidate.is_symlink() or expected.resolve() != expected):
        fail('ɑi ei ui 组合人听文件必须来自当前仓库固定 u4-l1 原始证据路径')
    review = candidate
    composition = review.parent
    repairs = composition.parent
    if (review.name != 'human-approval-before-adoption-binding.json'
            or composition.name != 'pinyin-ssml-probe-composition-v1'
            or repairs != EXPECTED_REPAIRS_ROOT):
        fail('ɑi ei ui 组合人听证据必须使用保留的 composition-v1 原文件')
    sources = {
        'evidence/plan.json': composition / 'plan.json',
        'evidence/human-approval.json': review,
        'evidence/user-confirmation.json': composition / 'user-confirmation.json',
        'evidence/validation.json': composition / 'validation.json',
        'evidence/origins/aieiui-v1/human-review.partial.json':
            repairs / 'pinyin-ssml-probe-v1/human-review.partial.json',
    }
    for origin in VERSIONS:
        folder = repairs / f'pinyin-ssml-probe-{origin.removeprefix("aieiui-")}'
        sources[f'evidence/origins/{origin}/plan.json'] = folder / 'plan.json'
        labels = V1_LABELS if origin == 'aieiui-v1' else ('luo-bo-neutral',)
        for label in labels:
            for name in PROBE_FILES:
                sources[f'evidence/origins/{origin}/{label}/{name}'] = folder / label / name
    for origin in FAILED_VERSIONS:
        folder = repairs / f'pinyin-ssml-probe-{origin.removeprefix("aieiui-")}'
        sources[f'evidence/origins/{origin}/machine-audio-audit.json'] = folder / 'machine-audio-audit.json'
    if set(sources) != evidence_names():
        fail('ɑi ei ui 组合归档清单不完整')
    files = {}
    for name, source in sources.items():
        if source.is_symlink() or source.resolve() != source:
            fail('ɑi ei ui 组合小样文件不能通过链接跨目录')
        files[name] = course_bytes(source)
    return files


def _lesson_binding(frozen):
    expected = dict(LESSON)
    if any(frozen.get(key) != value for key, value in expected.items()):
        fail('ɑi ei ui 组合小样只能用于登记的 u4-l1 教材版本')
    return expected


def _origin_lesson(frozen):
    return {'editionId': frozen['editionId'], 'nodeId': frozen['nodeId'],
            'revisionId': frozen['alignmentRevisionId']}


def _path_suffix(value, suffix):
    if not isinstance(value, str):
        return False
    normalized = value.replace('\\', '/')
    return normalized == suffix or normalized.endswith('/' + suffix)


def _origin_sample(plan, origin, label):
    items = plan.get('samples') if origin == 'aieiui-v1' else plan.get('newSamples')
    if not isinstance(items, list):
        fail('原始小样计划缺少固定样本')
    matches = [item for item in items if isinstance(item, dict) and item.get('label') == label]
    if len(matches) != 1:
        fail('原始小样计划的标签不唯一')
    return matches[0]


def _verify_origin_plan(raw, origin, frozen):
    plan = parse(raw)
    version = VERSIONS[origin]
    policy = pronunciation.registered_policy(version)
    lesson = plan.get('sourceLesson')
    expected_lesson = _origin_lesson(frozen)
    if (not isinstance(lesson, dict)
            or any(lesson.get(k) != v for k, v in expected_lesson.items())
            or plan.get('provider') != policy['providerId']
            or plan.get('model') != policy['modelId'] or plan.get('voice') != policy['voiceId']
            or plan.get('formalUseAllowed') is not False
            or plan.get('policyVersion') != version
            or plan.get('policyCanonicalSha256') != digest(policy)):
        fail('原始小样计划的教材、政策或服务参数不一致')
    if origin == 'aieiui-v1':
        if (plan.get('schemaVersion') != 'mira.operator.phonetic-ssml-probe.v1'
                or plan.get('plannedCalls') != 6
                or {x.get('label') for x in plan.get('samples', []) if isinstance(x, dict)} != set(V1_LABELS)):
            fail('前五段必须来自完整保留的 aieiui v1 六段计划')
    elif (plan.get('schemaVersion') != 'mira.operator.phonetic-ssml-probe-composite.v1'
          or plan.get('plannedNewCalls') != 1 or plan.get('maximumPostAttemptsPerStage') != 1
          or [x.get('label') for x in plan.get('newSamples', []) if isinstance(x, dict)] != ['luo-bo-neutral']):
        fail('修复历史必须保留单段、单次调用身份')
    return plan


def _verify_execution(files, origin, label, text, plan, plan_sha):
    prefix = f'evidence/origins/{origin}/{label}/'
    raws = {name: files[prefix + name] for name in PROBE_FILES}
    hashes = {name: sha(raw) for name, raw in raws.items()}
    version = VERSIONS[origin]
    policy = pronunciation.registered_policy(version)
    body = pronunciation.provider_body(text, policy_version=version)
    request, intent, receipt, response, validation = (parse(raws[name]) for name in
        ('request.json', 'intent.json', 'receipt.json', 'provider-response.json', 'playback-validation.json'))
    sample = _origin_sample(plan, origin, label)
    if (raws['request.json'] != canonical(body).encode() or request != body
            or sample.get('sourceText') != text or sample.get('body') != request
            or sample.get('requestSha256') != hashes['request.json']
            or sample.get('ssml') != request['input']['text']
            or sample.get('ssmlSha256') != sha(request['input']['text'].encode())):
        fail('原始小样请求不等于对应登记政策重算结果')
    checks = {
        'requestSha256': hashes['request.json'],
        'providerResponseSha256': hashes['provider-response.json'],
        'providerAudioSha256': hashes['audio.wav'],
        'playbackSha256': hashes['playback.wav'],
        'pcmSha256': sha(raws['playback.wav'][44:]),
        'providerRequestId': response.get('request_id'),
    }
    if (any(receipt.get(k) != value for k, value in checks.items())
            or not isinstance(checks['providerRequestId'], str) or not checks['providerRequestId']
            or receipt.get('status') != 'succeeded' or receipt.get('formalUseAllowed') is not False
            or receipt.get('postAttempts') != 1 or receipt.get('planSha256') != plan_sha
            or receipt.get('audioSha256') != checks['playbackSha256']
            or receipt.get('ssmlSha256') != sha(request['input']['text'].encode())
            or intent.get('requestSha256') != checks['requestSha256']
            or intent.get('planSha256') != plan_sha or intent.get('maxPostAttempts') != 1
            or intent.get('formalUseAllowed') is not False
            or any(record.get(k) != policy[v] for record in (intent, receipt) for k, v in
                   (('provider', 'providerId'), ('model', 'modelId'), ('voice', 'voiceId')))
            or response.get('output', {}).get('finish_reason') != 'stop'
            or response.get('usage') != receipt.get('usage')
            or timestamp(intent.get('createdAt')) > timestamp(receipt.get('completedAt'))):
        fail('原始意图、单次完成回执、响应或音频身份不一致')
    if origin != 'aieiui-v1':
        if (intent.get('policyVersion') != version or intent.get('policyCanonicalSha256') != digest(policy)
                or receipt.get('policyVersion') != version
                or receipt.get('policyCanonicalSha256') != digest(policy)
                or intent.get('sourceText') != text or receipt.get('sourceText') != text):
            fail('修复回执必须保留其实际政策版本和原文')
    pronunciation.validate_receipt_wav(receipt, raws['playback.wav'])
    if (validation.get('schemaVersion') != 'mira.operator.probe-wav-validation.v1'
            or validation.get('pcmUnchanged') is not True
            or validation.get('audioNormalization') != receipt['audioNormalization']
            or validation.get('durationSeconds') != receipt.get('durationSeconds')
            or any(validation.get(k) != checks[k] for k in
                   ('providerAudioSha256', 'playbackSha256', 'pcmSha256'))
            or raws['audio.wav'][44:] != raws['playback.wav'][44:]):
        fail('组合小样必须保留供应商原 WAV/PCM')
    return {'hashes': hashes, 'receipt': receipt, 'sample': sample,
            'providerRequestId': checks['providerRequestId']}


def verify_files(files, review, frozen, policy):
    """Verify exact historical bytes; preview/source binding remains initializer-owned."""
    if policy.get('policyVersion') != pronunciation.AIEIUI_V4_POLICY_VERSION:
        fail('人听组合小样只登记于 aieiui v4')
    if not evidence_names() <= set(files):
        fail('ɑi ei ui 组合小样缺少原始历史文件')
    lesson = _lesson_binding(frozen)
    if digest(policy) != digest(pronunciation.registered_policy(pronunciation.AIEIUI_V4_POLICY_VERSION)):
        fail('ɑi ei ui 目标政策字节已变化')

    raw_plan = files['evidence/plan.json']
    plan = parse(raw_plan)
    if (set(plan) != {'schemaVersion', 'pronunciationPolicyVersion', 'pronunciationPolicySha256',
                      'sourceLesson', 'formalUseAllowed', 'originPlans', 'samples'}
            or plan['schemaVersion'] != PLAN_SCHEMA
            or plan['pronunciationPolicyVersion'] != policy['policyVersion']
            or plan['pronunciationPolicySha256'] != digest(policy)
            or plan['sourceLesson'] != lesson or plan['formalUseAllowed'] is not False):
        fail('组合计划没有绑定固定教材和 aieiui v4 政策')
    origins = plan['originPlans']
    if (not isinstance(origins, list) or len(origins) != 2
            or any(not isinstance(x, dict) or set(x) != {'originId', 'planSha256'} for x in origins)
            or {x['originId'] for x in origins} != {'aieiui-v1', 'aieiui-v4'}):
        fail('组合计划必须明确保留 v1 与 v4 两个来源')

    origin_plans, origin_shas = {}, {}
    for origin in VERSIONS:
        raw = files[f'evidence/origins/{origin}/plan.json']
        origin_shas[origin] = sha(raw)
        origin_plans[origin] = _verify_origin_plan(raw, origin, frozen)
    if {x['originId']: x['planSha256'] for x in origins} != {
            origin: origin_shas[origin] for origin in ('aieiui-v1', 'aieiui-v4')}:
        fail('组合计划引用的 v1/v4 原计划摘要不一致')

    partial_raw = files['evidence/origins/aieiui-v1/human-review.partial.json']
    v2_predecessor = origin_plans['aieiui-v2'].get('predecessor')
    if (not isinstance(v2_predecessor, dict)
            or set(v2_predecessor) != {'finding', 'humanReviewPath', 'humanReviewSha256', 'originId',
                                      'planPath', 'planSha256', 'rejectedPlaybackSha256', 'rejectedSample'}
            or v2_predecessor.get('originId') != 'aieiui-v1'
            or v2_predecessor.get('finding') != 'bo_inaudible_or_missing'
            or v2_predecessor.get('rejectedSample') != 'luo-bo-neutral'
            or v2_predecessor.get('planSha256') != origin_shas['aieiui-v1']
            or v2_predecessor.get('humanReviewSha256') != sha(partial_raw)
            or v2_predecessor.get('rejectedPlaybackSha256') != sha(
                files['evidence/origins/aieiui-v1/luo-bo-neutral/playback.wav'])
            or not _path_suffix(v2_predecessor.get('planPath'),
                f'{RELATIVE_ROOT}/pinyin-ssml-probe-v1/plan.json')
            or not _path_suffix(v2_predecessor.get('humanReviewPath'),
                f'{RELATIVE_ROOT}/pinyin-ssml-probe-v1/human-review.partial.json')):
        fail('v2 修复计划没有保留被拒绝 v1 第六段的完整身份')

    # The v3/v4 plans preserve the failed chain. Paths are checked by stable
    # repository suffix so moving the checkout cannot weaken the evidence.
    for child, expected_origins in (('aieiui-v3', ('aieiui-v1', 'aieiui-v2')),
                                    ('aieiui-v4', ('aieiui-v1', 'aieiui-v2', 'aieiui-v3'))):
        items = origin_plans[child].get('origins')
        if (not isinstance(items, list)
                or {x.get('originId') for x in items if isinstance(x, dict)} != set(expected_origins)):
            fail(f'{child} 修复计划没有完整保留前序历史')
        for item in items:
            origin = item['originId']
            suffix = f'{RELATIVE_ROOT}/pinyin-ssml-probe-{origin.removeprefix("aieiui-")}/plan.json'
            if item.get('planSha256') != origin_shas[origin] or not _path_suffix(item.get('planPath'), suffix):
                fail(f'{child} 修复计划的历史计划路径或摘要不一致')
            if origin in FAILED_VERSIONS:
                audit_name = f'evidence/origins/{origin}/machine-audio-audit.json'
                audit_suffix = (f'{RELATIVE_ROOT}/pinyin-ssml-probe-'
                                f'{origin.removeprefix("aieiui-")}/machine-audio-audit.json')
                if (item.get('machineAuditSha256') != sha(files[audit_name])
                        or not _path_suffix(item.get('machineAuditPath'), audit_suffix)):
                    fail(f'{child} 修复计划没有保留失败机器审计')

    # Keep this direct check as a readable policy boundary for the final plan.
    v4_origins = origin_plans['aieiui-v4'].get('origins')
    if (not isinstance(v4_origins, list) or {x.get('originId') for x in v4_origins if isinstance(x, dict)}
            != {'aieiui-v1', 'aieiui-v2', 'aieiui-v3'}):
        fail('v4 修复计划没有完整保留 v1-v3 历史')
    for item in v4_origins:
        origin = item['originId']
        suffix = f'{RELATIVE_ROOT}/pinyin-ssml-probe-{origin.removeprefix("aieiui-")}/plan.json'
        if item.get('planSha256') != origin_shas[origin] or not _path_suffix(item.get('planPath'), suffix):
            fail('v4 修复计划的历史计划路径或摘要不一致')

    executions = {}
    for label, (_, _, text) in SLOTS.items():
        executions[('aieiui-v1', label)] = _verify_execution(
            files, 'aieiui-v1', label, text, origin_plans['aieiui-v1'], origin_shas['aieiui-v1'])
    for origin in ('aieiui-v2', 'aieiui-v3', 'aieiui-v4'):
        executions[(origin, 'luo-bo-neutral')] = _verify_execution(
            files, origin, 'luo-bo-neutral', 'luó bo', origin_plans[origin], origin_shas[origin])
    # Reused v1 requests must remain byte-identical to the active v4 recipes.
    for label, (_, _, text) in list(SLOTS.items())[:5]:
        expected = canonical(pronunciation.provider_body(
            text, policy_version=pronunciation.AIEIUI_V4_POLICY_VERSION)).encode()
        actual = files[f'evidence/origins/aieiui-v1/{label}/request.json']
        if actual != expected:
            fail('复用的 v1 前五段不等于 aieiui v4 的当前固定配方')

    partial = parse(partial_raw)
    partial_samples = indexed(partial.get('samples'), SLOTS, {
        'number', 'label', 'requestSha256', 'receiptSha256', 'playbackSha256', 'result', 'finding'})
    if (partial.get('schemaVersion') != 'mira.operator.phonetic-probe-human-review.partial.v1'
            or partial.get('sourceLesson') != _origin_lesson(frozen)
            or partial.get('probePlanSha256') != origin_shas['aieiui-v1']
            or partial.get('formalUseAllowed') is not False or partial.get('pronunciationApproved') is not False
            or partial.get('reviewer') != 'parent-user' or not partial.get('statements')):
        fail('v1 部分人听证据身份无效')
    timestamp(partial.get('receivedAt'))
    for label, (number, _, _) in SLOTS.items():
        item = partial_samples[label]
        execution = executions[('aieiui-v1', label)]
        expected_result = 'rejected_by_human_listening' if number == 6 else 'accepted_by_human_listening'
        expected_finding = 'bo_inaudible_or_missing' if number == 6 else 'no_problem_reported'
        if (item['number'] != number or item['result'] != expected_result or item['finding'] != expected_finding
                or item['requestSha256'] != execution['hashes']['request.json']
                or item['receiptSha256'] != execution['hashes']['receipt.json']
                or item['playbackSha256'] != execution['hashes']['playback.wav']):
            fail('v1 人听接受/拒绝结果与原字节不一致')

    raw_confirmation = files['evidence/user-confirmation.json']
    confirmation = parse(raw_confirmation)
    expected_confirmation_fields = {'schemaVersion', 'recordedAt', 'reviewer', 'sourceLesson',
        'probePlanSha256', 'reviewContext', 'priorHumanEvidence', 'assertions', 'samples',
        'evidenceBoundary', 'selfDigestScope', 'sha256'}
    prior = confirmation.get('priorHumanEvidence', {})
    review_context = confirmation.get('reviewContext', {})
    if (set(confirmation) != expected_confirmation_fields or not sealed(confirmation)
            or confirmation.get('schemaVersion') != CONFIRMATION_SCHEMA
            or confirmation.get('sourceLesson') != lesson
            or confirmation.get('probePlanSha256') != sha(raw_plan)
            or confirmation.get('reviewer') != 'parent-user'
            or set(prior) != {'path', 'sha256', 'acceptedSamples', 'rejectedSample', 'rejectionStatements'}
            or prior.get('sha256') != sha(partial_raw) or prior.get('acceptedSamples') != [1, 2, 3, 4, 5]
            or prior.get('rejectedSample') != 6
            or prior.get('rejectionStatements') != ['前几段都没问题，第六段没办法播放', 'bo没有声音']
            or not _path_suffix(prior.get('path'),
                f'{RELATIVE_ROOT}/pinyin-ssml-probe-v1/human-review.partial.json')
            or review_context != {
                'assistantPrompt': '请确认新版第六段：luó 是二声、bo 清楚可闻且为轻声。准确的话回复“第六段准确”。',
                'userStatement': '可以的，继续按照claude的规则生成剩余的课件',
                'interpretation': ('The direct affirmative reply accepts the repaired sixth sample and '
                                   'authorizes continuation under the established Claude rules.')}
            or confirmation.get('evidenceBoundary') != (
                'Approval is limited to these exact six playback WAV identities and their registered probe '
                'recipes. It does not approve any future full-course narration segment.')
            or confirmation.get('assertions') != {
                'samplesOneThroughFiveAcceptedFromV1': True, 'sampleSixAcceptedFromV4': True,
                'compoundFinalsAndTonesAccurateForProbeScope': True,
                'textbookSpellingSequencesAccurateForProbeScope': True,
                'paiDuiWholeWordAccurateForProbeScope': True, 'luoSecondToneAccurateForProbeScope': True,
                'boAudibleAndNeutralToneAccurateForProbeScope': True,
                'formalCourseNarrationApproved': False}):
        fail('用户确认没有完整绑定前五段、修复第六段和正式配音边界')
    timestamp(confirmation.get('recordedAt'))
    confirmation_samples = indexed(confirmation.get('samples'), SLOTS,
        {'number', 'label', 'originId', 'playbackSha256', 'result'})

    expected_review_fields = {'schemaVersion', 'method', 'recordedAt', 'reviewer', 'sourceLesson',
        'pronunciationPolicyVersion', 'pronunciationPolicySha256', 'probePlanSha256',
        'userConfirmationSha256', 'result', 'humanListeningVerified', 'perceptualToneVerified',
        'probeScopeApproved', 'formalUseAllowed', 'previewBound', 'initializationPerformed',
        'samples', 'failedHistoryPreserved', 'evidenceLimit', 'validatorCompatibility',
        'selfDigestScope', 'sha256'}
    if (not isinstance(review, dict) or set(review) != expected_review_fields or not sealed(review)
            or review['schemaVersion'] != REVIEW_SCHEMA or review['method'] != 'direct-human-listening-composite'
            or review['sourceLesson'] != lesson or review['reviewer'] != 'parent-user'
            or review['pronunciationPolicyVersion'] != policy['policyVersion']
            or review['pronunciationPolicySha256'] != digest(policy)
            or review['probePlanSha256'] != sha(raw_plan)
            or review['userConfirmationSha256'] != sha(raw_confirmation)
            or review['result'] != RESULT or review['humanListeningVerified'] is not True
            or review['perceptualToneVerified'] is not True or review['probeScopeApproved'] is not True
            or review['formalUseAllowed'] is not False or review['previewBound'] is not False
            or review['initializationPerformed'] is not False or review['evidenceLimit'] != LIMIT):
        fail('组合人听批准没有绑定固定六段或误充当正式逐句审核')
    if review.get('validatorCompatibility') != {
            'currentSinglePlanInitializerAcceptsThisComposite': False,
            'requiredBeforeFormalInitialization': ('Add and test a dedicated u4-l1 composite-human validator; '
                'do not pass this evidence to the single-plan v1 initializer or the Garden3-only composite validator.')}:
        fail('组合人听证据没有保留其创建时的初始化兼容性边界')
    timestamp(review.get('recordedAt'))
    reviewed_samples = indexed(review.get('samples'), SLOTS, {
        'number', 'label', 'originId', 'originPlanSha256', 'requestSha256', 'receiptSha256',
        'playbackSha256', 'durationSeconds', 'result'})
    planned_samples = indexed(plan['samples'], SLOTS, {
        'number', 'label', 'originId', 'originLabel', 'sourceText',
        'requestSha256', 'playbackSha256', 'receiptSha256'})
    for label, (number, origin, text) in SLOTS.items():
        execution = executions[(origin, label)]
        hashes, receipt = execution['hashes'], execution['receipt']
        expected = {'number': number, 'label': label, 'originId': origin, 'originLabel': label,
                    'sourceText': text, 'requestSha256': hashes['request.json'],
                    'playbackSha256': hashes['playback.wav'], 'receiptSha256': hashes['receipt.json']}
        if planned_samples[label] != expected:
            fail('组合计划的六段来源或摘要不一致')
        human = reviewed_samples[label]
        user = confirmation_samples[label]
        if (human != {**{k: expected[k] for k in ('number', 'label', 'originId')},
                      'originPlanSha256': origin_shas[origin],
                      'requestSha256': hashes['request.json'], 'receiptSha256': hashes['receipt.json'],
                      'playbackSha256': hashes['playback.wav'],
                      'durationSeconds': receipt['durationSeconds'],
                      'result': 'accepted_by_human_listening'}
                or user != {**{k: expected[k] for k in ('number', 'label', 'originId')},
                            'playbackSha256': hashes['playback.wav'],
                            'result': 'accepted_by_human_listening'}):
            fail('组合人听批准或用户确认不等于选中的原始 WAV')

    reused_fields = {'number', 'label', 'originId', 'originPlanSha256', 'requestSha256',
                     'receiptSha256', 'playbackSha256', 'humanResult'}
    for origin in ('aieiui-v2', 'aieiui-v3', 'aieiui-v4'):
        reused = indexed(origin_plans[origin].get('reusedSamples'), list(SLOTS)[:5], reused_fields)
        for label, (number, _, _) in list(SLOTS.items())[:5]:
            execution = executions[('aieiui-v1', label)]
            hashes = execution['hashes']
            if reused[label] != {
                    'number': number, 'label': label, 'originId': 'aieiui-v1',
                    'originPlanSha256': origin_shas['aieiui-v1'],
                    'requestSha256': hashes['request.json'], 'receiptSha256': hashes['receipt.json'],
                    'playbackSha256': hashes['playback.wav'],
                    'humanResult': 'accepted_by_human_listening'}:
                fail(f'{origin} 没有原样复用已人听通过的 v1 前五段')

    failure_files = {
        'v1': ('evidence/origins/aieiui-v1/human-review.partial.json',
               'bo_inaudible_or_missing'),
        'v2': ('evidence/origins/aieiui-v2/machine-audio-audit.json',
               'repair_failed_machine_audio_audit'),
        'v3': ('evidence/origins/aieiui-v3/machine-audio-audit.json',
               'repair_byte_identical_to_v2_and_not_human-reviewed'),
    }
    histories = review.get('failedHistoryPreserved')
    if (not isinstance(histories, list) or len(histories) != 3
            or {x.get('version') for x in histories if isinstance(x, dict)} != set(failure_files)):
        fail('v1-v3 失败历史没有完整保留')
    for item in histories:
        name, finding = failure_files[item['version']]
        suffix = f'{RELATIVE_ROOT}/pinyin-ssml-probe-{item["version"]}/' + (
            'human-review.partial.json' if item['version'] == 'v1' else 'machine-audio-audit.json')
        if (set(item) != {'version', 'finding', 'path', 'sha256'} or item['finding'] != finding
                or item['sha256'] != sha(files[name]) or not _path_suffix(item['path'], suffix)):
            fail('失败历史路径、结论或摘要不一致')

    for origin in FAILED_VERSIONS:
        raw = files[f'evidence/origins/{origin}/machine-audio-audit.json']
        audit = parse(raw)
        execution = executions[(origin, 'luo-bo-neutral')]
        version = origin.removeprefix('aieiui-')
        if (audit.get('schemaVersion') != 'mira.operator.probe-machine-audio-audit.v1'
                or audit.get('planSha256') != origin_shas[origin]
                or audit.get('formalUseAllowed') is not False
                or audit.get('humanListeningVerified') is not False
                or audit.get('perceptualToneVerified') is not False
                or audit.get('result') != 'blocked_before_human_review'
                or audit.get('sample', {}).get('label') != 'luo-bo-neutral'
                or audit['sample'].get('requestSha256') != execution['hashes']['request.json']
                or audit['sample'].get('playbackSha256') != execution['hashes']['playback.wav']
                or audit['sample'].get('providerResponseSha256') != execution['hashes']['provider-response.json']):
            fail(f'{version} 失败机器审计与原字节不一致')
        timestamp(audit.get('recordedAt'))
    if (parse(files['evidence/origins/aieiui-v3/machine-audio-audit.json'])
            .get('comparison', {}).get('v2PlaybackSha256')
            != executions[('aieiui-v2', 'luo-bo-neutral')]['hashes']['playback.wav']):
        fail('v3 未保留与 v2 字节相同的失败证据')

    validation = parse(files['evidence/validation.json'])
    expected_validation_fields = {'schemaVersion', 'validatedAt', 'compositionPlanSha256',
        'userConfirmationSha256', 'humanApprovalSha256', 'targetPolicyVersion', 'targetPolicySha256',
        'originCount', 'sampleCount', 'providerCalls', 'originalFilesCopied',
        'originalFilesReferencedInPlace', 'allReferencedFilesExist', 'allReferencedFileHashesVerified',
        'fullWavAndPcmVerifiedFromOriginalReceipts', 'humanListeningVerified', 'perceptualToneVerified',
        'formalUseAllowed', 'previewBound', 'initializationPerformed', 'historicalV1ThroughV4FilesModified',
        'historicalFailuresPreserved', 'readyForAssetAdoption',
        'notReadyForFormalNarrationWithoutSentenceReview', 'selfDigestScope', 'sha256'}
    if (set(validation) != expected_validation_fields or not sealed(validation)
            or validation.get('schemaVersion') != VALIDATION_SCHEMA
            or validation.get('compositionPlanSha256') != sha(raw_plan)
            or validation.get('userConfirmationSha256') != sha(raw_confirmation)
            or validation.get('humanApprovalSha256') != sha(files['evidence/human-approval.json'])
            or validation.get('targetPolicyVersion') != policy['policyVersion']
            or validation.get('targetPolicySha256') != digest(policy)
            or validation.get('originCount') != 2 or validation.get('sampleCount') != 6
            or validation.get('providerCalls') != 0 or validation.get('originalFilesCopied') is not False
            or validation.get('originalFilesReferencedInPlace') is not True
            or validation.get('allReferencedFilesExist') is not True
            or validation.get('allReferencedFileHashesVerified') is not True
            or validation.get('fullWavAndPcmVerifiedFromOriginalReceipts') is not True
            or validation.get('humanListeningVerified') is not True
            or validation.get('perceptualToneVerified') is not True
            or validation.get('formalUseAllowed') is not False
            or validation.get('previewBound') is not False
            or validation.get('initializationPerformed') is not False
            or validation.get('historicalV1ThroughV4FilesModified') is not False
            or validation.get('historicalFailuresPreserved') is not True
            or validation.get('readyForAssetAdoption') is not True
            or validation.get('notReadyForFormalNarrationWithoutSentenceReview') is not True):
        fail('组合验证摘要、自封摘要或正式逐句审核边界无效')
    timestamp(validation.get('validatedAt'))
