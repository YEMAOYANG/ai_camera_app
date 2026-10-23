"""Verify original probe bytes against a newly registered exact request.

No provider dispatch, audio acceptance, or rewriting of historical receipts.
Only the explicitly registered Garden 3 v2 composition is supported.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from content import textbook_pinyin_pronunciation as pronunciation
from content.textbook_catalog import canonical, digest
from core.errors import ApiError
from services.course_file_store import course_bytes

PLAN_SCHEMA = 'mira.operator.phonetic-composite-probe.v1'
REVIEW_SCHEMA = 'mira.textbook.pinyin-initialization-operator-review.v2-composite'
RESULT = 'protocol-and-wav-verified'
LIMIT = ('Original plans, requests, provider receipts and unchanged playable PCM, with exact target-policy '
         'request equality. Six historical v1 requests and one pre-registration natural-Chinese alias '
         'request retain their original identities. The alias is not li5 phoneme evidence. No human '
         'listening or perceptual pronunciation/tone verification; formal audio needs separate ASR and browser review.')
PROBE_FILES = ('request.json', 'intent.json', 'receipt.json', 'provider-response.json',
               'audio.wav', 'playback.wav', 'playback-validation.json')
ORIGINS = ('garden3-v1', 'garden3-alias-preregistration')
# label -> (origin, exact original label, exact logical source, v1 target or None)
SLOTS = MappingProxyType({
    'zimu-zhizhu-context': ('garden3-v1', 'zimu-zhizhu-context', 'zì mǔ。zhī zhū。', 'zì'),
    'ca-boli-natural-alias': ('garden3-alias-preregistration', 'ca-boli-natural-alias', 'cā bō li。', None),
    'sushe-shujia-context': ('garden3-v1', 'sushe-shujia-context', 'sù shè。shū jià。', 'shè'),
    'qi-ma-context': ('garden3-v1', 'qi-ma-context', 'qí mǎ。', 'qí'),
    'tuo-di-context': ('garden3-v1', 'tuo-di-context', 'tuō dì。', 'tuō'),
    'li-fa-context': ('garden3-v1', 'li-fa-context', 'lǐ fà。', 'fà'),
    'ba-luobo-neutral-context': ('garden3-v1', 'ba-luobo-neutral-context', 'bá luó bo。', 'luó'),
})


def fail(message):
    raise ApiError('textbook_preview_pronunciation_initialization_conflict', message, 409)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, UnicodeError):
        fail('组合小样文件不是有效 JSON')
    if not isinstance(value, dict):
        fail('组合小样文件必须是对象')
    return value


def evidence_names():
    return {'evidence/plan.json', 'evidence/operator-probe-review.json'} | {
        f'evidence/origins/{origin}/plan.json' for origin in ORIGINS} | {
        f'evidence/origins/{origin}/{label}/{name}'
        for origin, label, _, _ in SLOTS.values() for name in PROBE_FILES}


def read_files(review_path):
    path = Path(review_path).resolve()
    files = {}
    for name in evidence_names():
        source = path if name == 'evidence/operator-probe-review.json' else path.parent / name.removeprefix('evidence/')
        if source.is_symlink() or source.resolve() != source:
            fail('组合小样文件不能通过链接跨目录')
        files[name] = course_bytes(source)
    return files


def indexed(items, expected, fields=None):
    if (not isinstance(items, list) or len(items) != len(expected)
            or any(not isinstance(item, dict) or (fields is not None and set(item) != fields) for item in items)
            or any(not isinstance(item.get('label'), str) for item in items)
            or {item['label'] for item in items} != set(expected)):
        fail('组合小样必须完整、唯一且只包含固定目标')
    return {item['label']: item for item in items}


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError()
        return result
    except (TypeError, ValueError, AttributeError):
        fail('原调用意图或完成时间无效')


def verify_files(files, review, frozen, policy):
    """Review authorization/source/core are checked by the existing initializer."""
    if policy['policyVersion'] != pronunciation.GARDEN3_V2_POLICY_VERSION:
        fail('组合小样仅登记于本课 v2 政策')
    required = evidence_names()
    if not required <= set(files):
        fail('组合小样缺少原始文件')
    plan_raw = files['evidence/plan.json']
    plan = parse(plan_raw)
    fields = {'schemaVersion', 'pronunciationPolicyVersion', 'pronunciationPolicySha256',
              'sourceLesson', 'formalUseAllowed', 'originPlans', 'samples'}
    binding = {key: frozen[key] for key in pronunciation._BINDING_FIELDS}
    if (set(plan) != fields or plan['schemaVersion'] != PLAN_SCHEMA
            or plan['pronunciationPolicyVersion'] != policy['policyVersion']
            or plan['pronunciationPolicySha256'] != digest(policy)
            or plan['sourceLesson'] != binding or plan['formalUseAllowed'] is not False
            or sha(plan_raw) != review['probePlanSha256']):
        fail('组合计划必须绑定真实目标政策和冻结教材')
    origin_refs = plan['originPlans']
    if (not isinstance(origin_refs, list) or len(origin_refs) != 2
            or any(not isinstance(x, dict) or set(x) != {'originId', 'planSha256'} for x in origin_refs)
            or any(not isinstance(x['originId'], str) for x in origin_refs)
            or {x['originId'] for x in origin_refs} != set(ORIGINS)):
        fail('组合计划必须分别保留两个原计划身份')
    origins, origin_shas = {}, {}
    historical = pronunciation.registered_policy(pronunciation.GARDEN3_POLICY_VERSION)
    for ref in origin_refs:
        origin = ref['originId']
        raw = files[f'evidence/origins/{origin}/plan.json']
        original = parse(raw)
        origin_shas[origin] = sha(raw)
        lesson = original.get('sourceLesson')
        if (ref['planSha256'] != sha(raw) or not isinstance(lesson, dict)
                or any(lesson.get('revisionId' if key == 'alignmentRevisionId' else key) != value
                       for key, value in binding.items())
                or original.get('formalUseAllowed') is not False
                or any(original.get(k) != historical[v] for k, v in
                       (('provider', 'providerId'), ('model', 'modelId'), ('voice', 'voiceId')))):
            fail('原计划身份、教材或服务参数不一致')
        if origin == 'garden3-v1':
            if (original.get('schemaVersion') != 'mira.operator.phonetic-ssml-probe.v1'
                    or original.get('policyVersion') != historical['policyVersion']
                    or original.get('policyCanonicalSha256') != digest(historical)
                    or type(original.get('plannedCalls')) is not int or original['plannedCalls'] != 7):
                fail('六段必须引用历史 v1 原计划，不能改标为 v2')
            labels = (set(SLOTS) - {'ca-boli-natural-alias'}) | {'ca-boli-neutral-context'}
        else:
            if (original.get('schemaVersion') != 'mira.operator.phrase-comparison-probe.v1'
                    or original.get('parameterBasePolicyVersion') != historical['policyVersion']
                    or original.get('parameterBasePolicyCanonicalSha256') != digest(historical)
                    or original.get('registeredPolicyMatch') is not False
                    or original.get('policyModificationAllowed') is not False
                    or original.get('plannedTtsCalls') != 1
                    or original.get('maximumPostAttemptsPerStage') != 1):
                fail('alias 必须引用注册前独立诊断身份，不能冒充 v2 配音')
            labels = {'ca-boli-natural-alias'}
        origins[origin] = indexed(original.get('samples'), labels)
    planned = indexed(plan['samples'], SLOTS, {'label', 'originId', 'originLabel', 'sourceText', 'requestSha256'})
    samples = indexed(review['samples'], SLOTS, {'label', 'originId', 'originLabel', 'originPlanSha256',
                                                'files', 'providerRequestId', 'result'})
    for label, (origin, origin_label, text, target) in SLOTS.items():
        sample, item = samples[label], planned[label]
        original = origins[origin][origin_label]
        raws = {name: files[f'evidence/origins/{origin}/{origin_label}/{name}'] for name in PROBE_FILES}
        hashes = {name: sha(raw) for name, raw in raws.items()}
        if (item != {'label': label, 'originId': origin, 'originLabel': origin_label,
                     'sourceText': text, 'requestSha256': hashes['request.json']}
                or sample['originId'] != origin or sample['originLabel'] != origin_label
                or sample['originPlanSha256'] != origin_shas[origin] or sample['files'] != hashes
                or sample['result'] != RESULT):
            fail('组合目标、来源或文件字节不一致')
        request, intent, receipt, response, validation = (parse(raws[name]) for name in
            ('request.json', 'intent.json', 'receipt.json', 'provider-response.json', 'playback-validation.json'))
        body = pronunciation.provider_body(text, policy_version=policy['policyVersion'])
        if (raws['request.json'] != canonical(body).encode() or request != body
                or original.get('sourceText') != text or original.get('body') != request
                or original.get('requestSha256') != hashes['request.json']
                or original.get('ssmlSha256') != sha(request['input']['text'].encode())):
            fail('每段原始请求必须逐字等于目标 v2 重算的完整请求')
        if target is not None:
            entry = historical['symbols'][target]
            if (request != pronunciation.provider_body(text, policy_version=historical['policyVersion'])
                    or original.get('target') != target or original.get('phonemeCandidate') != entry['ph']
                    or original.get('carrier') != entry['carrier']
                    or receipt.get('policyVersion') != historical['policyVersion']
                    or receipt.get('policyCanonicalSha256') != digest(historical)
                    or receipt.get('target') != target or receipt.get('phonemeCandidate') != entry['ph']):
                fail('继承请求必须保留 v1 实际音素及回执身份')
        elif (original.get('ssml') != request['input']['text']
                or original.get('expectedNaturalPhrase') != '擦玻璃。'
                or receipt.get('parameterBasePolicyVersion') != historical['policyVersion']
                or receipt.get('parameterBasePolicyCanonicalSha256') != digest(historical)
                or receipt.get('registeredPolicyMatch') is not False
                or intent.get('registeredPolicyMatch') is not False
                or receipt.get('target') != 'cā bō li' or receipt.get('subAlias') != '擦玻璃'
                or 'phonemeCandidate' in receipt or 'policyVersion' in receipt):
            fail('alias 原回执不能冒称 li5 音素或生成时已注册 v2')
        checks = {'requestSha256': hashes['request.json'], 'providerResponseSha256': hashes['provider-response.json'],
                  'providerAudioSha256': hashes['audio.wav'], 'playbackSha256': hashes['playback.wav'],
                  'pcmSha256': sha(raws['playback.wav'][44:]), 'providerRequestId': response.get('request_id')}
        if (any(receipt.get(k) != value for k, value in checks.items())
                or not isinstance(checks['providerRequestId'], str) or not checks['providerRequestId']
                or sample['providerRequestId'] != checks['providerRequestId']
                or receipt.get('status') != 'succeeded' or receipt.get('formalUseAllowed') is not False
                or type(receipt.get('postAttempts')) is not int or receipt['postAttempts'] != 1
                or receipt.get('planSha256') != origin_shas[origin]
                or receipt.get('ssmlSha256') != sha(request['input']['text'].encode())
                or receipt.get('audioSha256') != checks['playbackSha256']
                or intent.get('requestSha256') != checks['requestSha256']
                or intent.get('planSha256') != origin_shas[origin]
                or type(intent.get('maxPostAttempts')) is not int or intent['maxPostAttempts'] != 1
                or intent.get('formalUseAllowed') is not False
                or any(record.get(k) != policy[v] for record in (intent, receipt) for k, v in
                       (('provider', 'providerId'), ('model', 'modelId'), ('voice', 'voiceId')))
                or response.get('output', {}).get('finish_reason') != 'stop'
                or response.get('usage') != receipt.get('usage')
                or timestamp(intent.get('createdAt')) > timestamp(receipt.get('completedAt'))):
            fail('原始意图、单次完成回执、响应或音频身份不一致；未知结果不得替换')
        pronunciation.validate_receipt_wav(receipt, raws['playback.wav'])
        if (validation.get('schemaVersion') != 'mira.operator.probe-wav-validation.v1'
                or validation.get('pcmUnchanged') is not True
                or validation.get('audioNormalization') != receipt['audioNormalization']
                or any(validation.get(k) != checks[k] for k in
                       ('providerAudioSha256', 'playbackSha256', 'pcmSha256'))
                or raws['audio.wav'][44:] != raws['playback.wav'][44:]):
            fail('组合证据播放文件必须保留供应商原 PCM')
