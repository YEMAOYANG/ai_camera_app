"""Server-owned lesson pronunciation and human-listening evidence; no provider calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import struct
from types import MappingProxyType
import unicodedata

from content.textbook_catalog import canonical, digest
from core.errors import ApiError


POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation.v1.json').read_text())
POLICY_SHA256 = digest(POLICY)
AOE_POLICY_VERSION = POLICY['policyVersion']
_IUU_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_iuu.v1.json').read_text())
IUU_POLICY_VERSION = _IUU_POLICY['policyVersion']
_BPMF_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_bpmf.v1.json').read_text())
BPMF_POLICY_VERSION = _BPMF_POLICY['policyVersion']
_DTNL_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_dtnl.v1.json').read_text())
DTNL_POLICY_VERSION = _DTNL_POLICY['policyVersion']
_GARDEN2_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_garden2.v1.json').read_text())
GARDEN2_POLICY_VERSION = _GARDEN2_POLICY['policyVersion']
_GKH_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_gkh.v1.json').read_text())
GKH_POLICY_VERSION = _GKH_POLICY['policyVersion']
_JQX_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_jqx.v1.json').read_text())
JQX_POLICY_VERSION = _JQX_POLICY['policyVersion']
_ZCS_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_zcs.v1.json').read_text())
ZCS_POLICY_VERSION = _ZCS_POLICY['policyVersion']
_ZCS_V2_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_zcs.v2.json').read_text())
ZCS_V2_POLICY_VERSION = _ZCS_V2_POLICY['policyVersion']
_ZHCHSHR_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_zhchshr.v1.json').read_text())
ZHCHSHR_POLICY_VERSION = _ZHCHSHR_POLICY['policyVersion']
_YW_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_yw.v1.json').read_text())
YW_POLICY_VERSION = _YW_POLICY['policyVersion']
_GARDEN3_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_garden3.v1.json').read_text())
GARDEN3_POLICY_VERSION = _GARDEN3_POLICY['policyVersion']
_GARDEN3_V2_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_garden3.v2.json').read_text())
GARDEN3_V2_POLICY_VERSION = _GARDEN3_V2_POLICY['policyVersion']
_AIEIUI_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_aieiui.v1.json').read_text())
AIEIUI_POLICY_VERSION = _AIEIUI_POLICY['policyVersion']
_AIEIUI_V2_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_aieiui.v2.json').read_text())
AIEIUI_V2_POLICY_VERSION = _AIEIUI_V2_POLICY['policyVersion']
_AIEIUI_V3_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_aieiui.v3.json').read_text())
AIEIUI_V3_POLICY_VERSION = _AIEIUI_V3_POLICY['policyVersion']
_AIEIUI_V4_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_aieiui.v4.json').read_text())
AIEIUI_V4_POLICY_VERSION = _AIEIUI_V4_POLICY['policyVersion']
_AOUIU_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_aouiu.v1.json').read_text())
AOUIU_POLICY_VERSION = _AOUIU_POLICY['policyVersion']
_IEUEER_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_ieueer.v1.json').read_text())
IEUEER_POLICY_VERSION = _IEUEER_POLICY['policyVersion']
_ANENINUNUN_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_aneninunun.v1.json').read_text())
ANENINUNUN_POLICY_VERSION = _ANENINUNUN_POLICY['policyVersion']
_ANGENGINGONG_POLICY = json.loads(Path(__file__).with_name('textbook_pinyin_pronunciation_angengingong.v1.json').read_text())
ANGENGINGONG_POLICY_VERSION = _ANGENGINGONG_POLICY['policyVersion']
# Store canonical strings, not mutable policy objects. The historical aliases
# above remain compatible, but cannot mutate the registry used by validation.
_POLICIES = MappingProxyType({AOE_POLICY_VERSION: canonical(POLICY),
                            IUU_POLICY_VERSION: canonical(_IUU_POLICY),
                            BPMF_POLICY_VERSION: canonical(_BPMF_POLICY),
                            DTNL_POLICY_VERSION: canonical(_DTNL_POLICY),
                            GARDEN2_POLICY_VERSION: canonical(_GARDEN2_POLICY),
                            GKH_POLICY_VERSION: canonical(_GKH_POLICY),
                            JQX_POLICY_VERSION: canonical(_JQX_POLICY),
                            ZCS_POLICY_VERSION: canonical(_ZCS_POLICY),
                            ZCS_V2_POLICY_VERSION: canonical(_ZCS_V2_POLICY),
                            ZHCHSHR_POLICY_VERSION: canonical(_ZHCHSHR_POLICY),
                            YW_POLICY_VERSION: canonical(_YW_POLICY),
                            GARDEN3_POLICY_VERSION: canonical(_GARDEN3_POLICY),
                            GARDEN3_V2_POLICY_VERSION: canonical(_GARDEN3_V2_POLICY),
                            AIEIUI_POLICY_VERSION: canonical(_AIEIUI_POLICY),
                            AIEIUI_V2_POLICY_VERSION: canonical(_AIEIUI_V2_POLICY),
                            AIEIUI_V3_POLICY_VERSION: canonical(_AIEIUI_V3_POLICY),
                            AIEIUI_V4_POLICY_VERSION: canonical(_AIEIUI_V4_POLICY),
                            AOUIU_POLICY_VERSION: canonical(_AOUIU_POLICY),
                            IEUEER_POLICY_VERSION: canonical(_IEUEER_POLICY),
                            ANENINUNUN_POLICY_VERSION: canonical(_ANENINUNUN_POLICY),
                            ANGENGINGONG_POLICY_VERSION: canonical(_ANGENGINGONG_POLICY)})
_AOE_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                       'u2-l1', 'primary_1', 'chinese')
_IUU_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                       'u2-l2', 'primary_1', 'chinese')
_BPMF_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                       'u2-l3', 'primary_1', 'chinese')
_DTNL_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                       'u2-l4', 'primary_1', 'chinese')
_GARDEN2_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                          'u2-l5', 'primary_1', 'chinese')
_GKH_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                      'u3-l1', 'primary_1', 'chinese')
_JQX_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                      'u3-l2', 'primary_1', 'chinese')
_ZCS_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                      'u3-l3', 'primary_1', 'chinese')
_ZHCHSHR_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                          'u3-l4', 'primary_1', 'chinese')
_YW_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                      'u3-l5', 'primary_1', 'chinese')
_GARDEN3_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                           'u3-l6', 'primary_1', 'chinese')
_AIEIUI_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                          'u4-l1', 'primary_1', 'chinese')
_AOUIU_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                        'u4-l2', 'primary_1', 'chinese')
_IEUEER_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                         'u4-l3', 'primary_1', 'chinese')
_ANENINUNUN_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                            'u4-l4', 'primary_1', 'chinese')
_ANGENGINGONG_LESSON_BINDING = ('pep-chinese-g1-upper-2022-standard', '20260924-directory-3',
                              'u4-l5', 'primary_1', 'chinese')
_LESSON_POLICIES = MappingProxyType({_AOE_LESSON_BINDING: AOE_POLICY_VERSION,
                                   _IUU_LESSON_BINDING: IUU_POLICY_VERSION,
                                   _BPMF_LESSON_BINDING: BPMF_POLICY_VERSION,
                                   _DTNL_LESSON_BINDING: DTNL_POLICY_VERSION,
                                   _GARDEN2_LESSON_BINDING: GARDEN2_POLICY_VERSION,
                                   _GKH_LESSON_BINDING: GKH_POLICY_VERSION,
                                   _JQX_LESSON_BINDING: JQX_POLICY_VERSION,
                                   _ZCS_LESSON_BINDING: ZCS_POLICY_VERSION,
                                   _ZHCHSHR_LESSON_BINDING: ZHCHSHR_POLICY_VERSION,
                                   _YW_LESSON_BINDING: YW_POLICY_VERSION,
                                   _GARDEN3_LESSON_BINDING: GARDEN3_V2_POLICY_VERSION,
                                   _AIEIUI_LESSON_BINDING: AIEIUI_V4_POLICY_VERSION,
                                   _AOUIU_LESSON_BINDING: AOUIU_POLICY_VERSION,
                                   _IEUEER_LESSON_BINDING: IEUEER_POLICY_VERSION,
                                   _ANENINUNUN_LESSON_BINDING: ANENINUNUN_POLICY_VERSION,
                                   _ANGENGINGONG_LESSON_BINDING: ANGENGINGONG_POLICY_VERSION})
# Historical permissions are explicit, not derived from the current default:
# changing a future default must not silently revoke an existing publication.
_ALLOWED_LESSON_POLICIES = MappingProxyType({
    _AOE_LESSON_BINDING: frozenset({AOE_POLICY_VERSION}),
    _IUU_LESSON_BINDING: frozenset({IUU_POLICY_VERSION}),
    _BPMF_LESSON_BINDING: frozenset({BPMF_POLICY_VERSION}),
    _DTNL_LESSON_BINDING: frozenset({DTNL_POLICY_VERSION}),
    _GARDEN2_LESSON_BINDING: frozenset({GARDEN2_POLICY_VERSION}),
    _GKH_LESSON_BINDING: frozenset({GKH_POLICY_VERSION}),
    _JQX_LESSON_BINDING: frozenset({JQX_POLICY_VERSION}),
    _ZCS_LESSON_BINDING: frozenset({ZCS_POLICY_VERSION, ZCS_V2_POLICY_VERSION}),
    _ZHCHSHR_LESSON_BINDING: frozenset({ZHCHSHR_POLICY_VERSION}),
    _YW_LESSON_BINDING: frozenset({YW_POLICY_VERSION}),
    _GARDEN3_LESSON_BINDING: frozenset({GARDEN3_POLICY_VERSION, GARDEN3_V2_POLICY_VERSION}),
    _AIEIUI_LESSON_BINDING: frozenset({AIEIUI_POLICY_VERSION, AIEIUI_V2_POLICY_VERSION,
                                       AIEIUI_V3_POLICY_VERSION, AIEIUI_V4_POLICY_VERSION}),
    _AOUIU_LESSON_BINDING: frozenset({AOUIU_POLICY_VERSION}),
    _IEUEER_LESSON_BINDING: frozenset({IEUEER_POLICY_VERSION}),
    _ANENINUNUN_LESSON_BINDING: frozenset({ANENINUNUN_POLICY_VERSION}),
    _ANGENGINGONG_LESSON_BINDING: frozenset({ANGENGINGONG_POLICY_VERSION}),
})
_BINDING_FIELDS = ('editionId', 'alignmentRevisionId', 'nodeId', 'gradeCode', 'subject')
# Later pinyin lessons start with an approved probe profile and cannot dispatch the
# ordinary default voice before that profile has been explicitly initialized.
# Historical AOE plans keep their existing lifecycle and immutable identity.
_INITIALIZATION_REQUIRED = frozenset({_IUU_LESSON_BINDING, _BPMF_LESSON_BINDING,
                                      _DTNL_LESSON_BINDING, _GARDEN2_LESSON_BINDING,
                                      _GKH_LESSON_BINDING, _JQX_LESSON_BINDING, _ZCS_LESSON_BINDING,
                                      _ZHCHSHR_LESSON_BINDING, _YW_LESSON_BINDING, _GARDEN3_LESSON_BINDING,
                                      _AIEIUI_LESSON_BINDING, _AOUIU_LESSON_BINDING,
                                      _IEUEER_LESSON_BINDING, _ANENINUNUN_LESSON_BINDING,
                                      _ANGENGINGONG_LESSON_BINDING})
_WHOLE_TOKEN_POLICIES = frozenset({BPMF_POLICY_VERSION, DTNL_POLICY_VERSION, GARDEN2_POLICY_VERSION,
                                 GKH_POLICY_VERSION, JQX_POLICY_VERSION, ZCS_POLICY_VERSION, ZCS_V2_POLICY_VERSION,
                                 ZHCHSHR_POLICY_VERSION, YW_POLICY_VERSION, GARDEN3_POLICY_VERSION,
                                 GARDEN3_V2_POLICY_VERSION, AIEIUI_POLICY_VERSION,
                                 AIEIUI_V2_POLICY_VERSION, AIEIUI_V3_POLICY_VERSION,
                                 AIEIUI_V4_POLICY_VERSION, AOUIU_POLICY_VERSION, IEUEER_POLICY_VERSION,
                                 ANENINUNUN_POLICY_VERSION, ANGENGINGONG_POLICY_VERSION})
PLAN_SCHEMA = 'mira.textbook.preview-audio-plan.v3-pinyin'
LISTENING_SCHEMA = 'mira.textbook.pinyin-listening.v1'
SHA = re.compile(r'[a-f0-9]{64}\Z')
RECEIPT_FIELDS = {'policyVersion', 'policySha256', 'ssmlSha256', 'sourceTextSha256',
                  'providerBodySha256', 'providerId', 'modelId', 'voiceId'}


def fail(message):
    raise ApiError('textbook_pinyin_pronunciation_invalid', message, 409)


def initialization_required(binding):
    if not isinstance(binding, dict):
        return False
    values = tuple(binding.get(k) for k in _BINDING_FIELDS)
    return all(isinstance(v, str) for v in values) and values in _INITIALIZATION_REQUIRED


def registered_policy(policy_version=AOE_POLICY_VERSION):
    """Resolve only a server-registered version; return an isolated copy."""
    if not isinstance(policy_version, str) or policy_version not in _POLICIES:
        fail('拼音读音政策版本尚未审核或未注册')
    return json.loads(_POLICIES[policy_version])


def select_policy(binding):
    """New plans select a policy from an explicit textbook lesson identity."""
    if not isinstance(binding, dict):
        fail('拼音读音政策缺少冻结教材身份')
    values = tuple(binding.get(k) for k in _BINDING_FIELDS)
    if any(not isinstance(v, str) for v in values) or values not in _LESSON_POLICIES:
        fail('本课尚未登记可用于正式配音的拼音政策')
    version = _LESSON_POLICIES[values]
    if version not in _ALLOWED_LESSON_POLICIES.get(values, ()):
        fail('本课当前拼音政策未登记为允许版本')
    return registered_policy(version)


def policy_for_plan(plan):
    """A v3 plan must name the exact registered policy for its frozen lesson.

    Never infer a policy from text, a receipt, or a missing/unknown version.
    No fields are added to the historical plan or its hash input.
    """
    if not isinstance(plan, dict) or plan.get('schemaVersion') != PLAN_SCHEMA:
        fail('需要明确的正式拼音配音计划')
    frozen = plan.get('pronunciationPolicy')
    if not isinstance(frozen, dict):
        fail('正式拼音配音计划缺少冻结读音政策')
    policy = registered_policy(frozen.get('policyVersion'))
    binding = plan.get('binding')
    values = tuple(binding.get(k) for k in _BINDING_FIELDS) if isinstance(binding, dict) else ()
    if (frozen != policy or plan.get('pronunciationPolicySha256') != digest(policy)
            or any(not isinstance(v, str) for v in values)
            or policy['policyVersion'] not in _ALLOWED_LESSON_POLICIES.get(values, ())):
        fail('冻结拼音政策与已审核版本或本课身份不一致')
    return policy


def sha_text(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def xml_escape(value):
    for old, new in (('&', '&amp;'), ('<', '&lt;'), ('>', '&gt;'), ('"', '&quot;'), ("'", '&apos;')):
        value = value.replace(old, new)
    return value


def pronunciation_symbols(text, *, policy_version=AOE_POLICY_VERSION):
    policy = registered_policy(policy_version)
    if not isinstance(text, str) or not text or text != text.strip():
        fail('拼音配音必须使用原始非空且无首尾空白的讲解文本')
    if policy_version in _WHOLE_TOKEN_POLICIES:
        return _whole_tokens(text, policy)
    found = []
    for index, char in enumerate(text):
        if char in policy['symbols']:
            found.append({'index': index, 'symbol': char, **policy['symbols'][char]})
        elif 'LATIN' in unicodedata.name(char, '') or unicodedata.category(char).startswith('M'):
            fail('拼音音频配置只支持本课已审核的字符')
        elif unicodedata.category(char) == 'Cc' and char not in '\n\r\t':
            fail('讲解文本含不允许的控制字符')
    return found


def _whole_tokens(text, policy):
    """Never split an unknown Latin run into individually supported letters.

    Fixed ranges are shared with native (including compatibility letters and
    numeric tone spellings) so Python/JS Unicode versions cannot change tokens.
    Classification does not normalize or alter any logical text bytes.
    """
    ranges = policy['textHandling']['latinRunRanges']
    def latin(char):
        return any(start <= ord(char) <= end for start, end in ranges)
    words = sorted(policy['words'], key=lambda word: (-len(word), word))
    found, index = [], 0
    while index < len(text):
        char = text[index]
        category = unicodedata.category(char)
        if category.startswith('M') or (category == 'Cc' and char not in '\n\r\t'):
            fail('讲解文本含不允许的组合调号或控制字符')
        if latin(char):
            end = index + 1
            while end < len(text) and latin(text[end]):
                end += 1
            token = text[index:end]
            entry = policy['symbols'].get(token)
            if entry is None:
                fail('拼音音频配置不支持此完整音节，不能逐字拆读')
        else:
            token = next((word for word in words if text.startswith(word, index)), None)
            if token is None:
                index += 1
                continue
            end, entry = index + len(token), policy['words'][token]
        found.append({'index': index, 'symbol': token, **entry})
        index = end
    return found


def pinyin_ssml(text, *, policy_version=AOE_POLICY_VERSION):
    policy = registered_policy(policy_version)
    matches = pronunciation_symbols(text, policy_version=policy_version)
    # Server-owned, full-source match only; token validation still runs above.
    exact = policy.get('exactTextSsml', {}).get(text)
    if exact is not None:
        return exact
    if policy_version in _WHOLE_TOKEN_POLICIES:
        parts, previous = [], 0
        for entry in matches:
            parts.extend((xml_escape(text[previous:entry['index']]),
                          f'<phoneme alphabet="py" ph="{entry["ph"]}">{entry["carrier"]}</phoneme>'))
            previous = entry['index'] + len(entry['symbol'])
        return '<speak>' + ''.join(parts) + xml_escape(text[previous:]) + '</speak>'
    parts = []
    for char in text:
        entry = policy['symbols'].get(char)
        parts.append(f'<phoneme alphabet="py" ph="{entry["ph"]}">{entry["carrier"]}</phoneme>'
                     if entry else xml_escape(char))
    return '<speak>' + ''.join(parts) + '</speak>'


def pronunciation_identity(text, *, policy_version=AOE_POLICY_VERSION):
    policy = registered_policy(policy_version)
    return {'policyVersion': policy['policyVersion'], 'policySha256': digest(policy),
            'ssmlSha256': sha_text(pinyin_ssml(text, policy_version=policy_version))}


def provider_body(text, *, policy_version=AOE_POLICY_VERSION):
    policy = registered_policy(policy_version)
    return {'model': policy['modelId'], 'input': {
        'text': pinyin_ssml(text, policy_version=policy_version), **deepcopy(policy['inputParameters'])}}


def provider_pronunciation(text, *, policy_version=AOE_POLICY_VERSION):
    policy = registered_policy(policy_version)
    return {**pronunciation_identity(text, policy_version=policy_version), 'sourceTextSha256': sha_text(text),
            'providerBodySha256': sha_text(canonical(provider_body(text, policy_version=policy_version))),
            **{k: policy[k] for k in ('providerId', 'modelId', 'voiceId')}}


def validate_provider_pronunciation(value, text=None, *, policy_version=AOE_POLICY_VERSION):
    policy = registered_policy(policy_version)
    if (not isinstance(value, dict) or set(value) != RECEIPT_FIELDS
            or any(value.get(k) != expected for k, expected in {
                'policyVersion': policy['policyVersion'], 'policySha256': digest(policy),
                **{k: policy[k] for k in ('providerId', 'modelId', 'voiceId')}}.items())
            or any(not SHA.fullmatch(str(value.get(k))) for k in
                   ('ssmlSha256', 'sourceTextSha256', 'providerBodySha256'))
            or (text is not None and value != provider_pronunciation(text, policy_version=policy_version))):
        fail('正式拼音回执与实际声音、原文、SSML 或请求正文摘要不一致')
    return deepcopy(value)


def validate_formal_receipt(receipt, text=None, *, policy_version=AOE_POLICY_VERSION):
    policy = registered_policy(policy_version)
    request = str(receipt.get('requestId', ''))
    if re.fullmatch(r'tbptts1_[a-f0-9]{64}', request):
        expected = {k: policy[k] for k in ('providerId', 'modelId', 'voiceId')}
    elif re.fullmatch(r'tbpasr1_[a-f0-9]{64}', request):
        expected = {'providerId': 'qwen-asr', 'modelId': 'qwen3-asr-flash'}
        if receipt.get('voiceId') is not None or not SHA.fullmatch(str(receipt.get('providerAsrBodySha256'))):
            fail('拼音 ASR 回执不能冒用 TTS 音色')
    else:
        fail('正式拼音回执编号无效')
    if any(receipt.get(k) != v for k, v in expected.items()):
        fail('正式拼音回执的实际服务模型或音色不一致')
    identity = validate_provider_pronunciation(receipt.get('providerPronunciation'), text,
                                              policy_version=policy_version)
    if request.startswith('tbptts1_'):
        validate_receipt_wav(receipt)
        request_id, usage, measurement = (receipt.get(k) for k in
                                         ('providerRequestId', 'providerUsage', 'budgetMeasurement'))
        if (not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 512
                or not isinstance(usage, dict) or set(usage) != {'characters'}
                or type(usage['characters']) is not int or usage['characters'] < 0
                or not isinstance(measurement, dict) or set(measurement) != {'kind', 'characters', 'estimated'}
                or measurement['kind'] != 'ssml-codepoint-upper-bound' or measurement['estimated'] is not True
                or type(measurement['characters']) is not int or measurement['characters'] <= 0
                or (text is not None and measurement['characters'] != len(pinyin_ssml(text, policy_version=policy_version)))):
            fail('正式拼音回执必须区分供应商实际计量与 SSML 预算估算')
    return identity


def validate_receipt_wav(receipt, audio=None):
    """Prove normalization changed only the two known streaming length fields."""
    norm = receipt.get('audioNormalization')
    keys = {'policyVersion', 'applied', 'providerRiffSize', 'providerDataSize', 'riffSize',
            'dataSize', 'pcmByteLength', 'sampleRate', 'channels', 'bitsPerSample'}
    if (not isinstance(norm, dict) or set(norm) != keys
            or norm.get('policyVersion') != 'mira.wav.streaming-pcm-lengths.v1'
            or type(norm.get('applied')) is not bool
            or any(type(norm.get(k)) is not int or norm[k] < 0 for k in keys - {'policyVersion', 'applied'})
            or (norm['sampleRate'], norm['channels'], norm['bitsPerSample']) != (24000, 1, 16)
            or not 0 < norm['dataSize'] == norm['pcmByteLength'] or norm['dataSize'] % 2
            or norm['riffSize'] != norm['dataSize'] + 36
            or any(not SHA.fullmatch(str(receipt.get(k))) for k in ('audioSha256', 'providerAudioSha256', 'pcmSha256'))):
        fail('拼音 WAV 回执缺少精确 PCM 及规范化证据')
    source_sizes = (norm['providerRiffSize'], norm['providerDataSize'])
    expected_sizes = (0x7fffffbf, 0x7fffff9b) if norm['applied'] else (norm['riffSize'], norm['dataSize'])
    if source_sizes != expected_sizes:
        fail('拼音 WAV 不是已审核的长度规范化')
    if audio is not None:
        if (not isinstance(audio, bytes) or len(audio) != norm['dataSize'] + 44
                or audio[:4] != b'RIFF' or audio[8:16] != b'WAVEfmt ' or audio[36:40] != b'data'
                or struct.unpack_from('<IHHIIHH', audio, 16) != (16, 1, 1, 24000, 48000, 2, 16)
                or struct.unpack_from('<I', audio, 4)[0] != norm['riffSize']
                or struct.unpack_from('<I', audio, 40)[0] != norm['dataSize']
                or hashlib.sha256(audio).hexdigest() != receipt['audioSha256']
                or hashlib.sha256(audio[44:]).hexdigest() != receipt['pcmSha256']):
            fail('下载的拼音 WAV/PCM 字节与正式回执不一致')
        original = bytearray(audio)
        struct.pack_into('<I', original, 4, norm['providerRiffSize'])
        struct.pack_into('<I', original, 40, norm['providerDataSize'])
        if hashlib.sha256(original).hexdigest() != receipt['providerAudioSha256']:
            fail('规范化后的拼音音频无法还原为原 Provider 音频')


def validate_listening_review(plan, classroom, review, *, now_ms):
    """Require exact current formal bytes, not probe audio or an ASR score."""
    policy = policy_for_plan(plan)
    fields = {'schemaVersion', 'previewKey', 'planSha256', 'coreSha256', 'segments', 'sha256'}
    if (not isinstance(review, dict) or set(review) != fields
            or review.get('schemaVersion') != LISTENING_SCHEMA
            or review.get('previewKey') != plan['previewKey'] or review.get('planSha256') != digest(plan)
            or review.get('coreSha256') != plan['coreSha256']
            or review.get('sha256') != digest({k: v for k, v in review.items() if k != 'sha256'})
            or not isinstance(review.get('segments'), list)):
        fail('拼音听验记录没有绑定当前正式配音计划')
    required = {(s['id'], a['id']): a for s in classroom['scenes'] for a in s.get('actions', [])
                if a.get('type') == 'speech' and pronunciation_symbols(
                    a['text'].strip(), policy_version=policy['policyVersion'])}
    if not required:
        fail('拼音听验必须有明确的拼音示范段落')
    seen = set()
    for item in review['segments']:
        keys = {'sceneId', 'actionId', 'textSha256', 'ttsRequestId', 'audioSha256',
                'verdict', 'reviewer', 'reviewedAt', 'basis'}
        if (not isinstance(item, dict) or set(item) != keys
                or any(not isinstance(item[k], str) or not item[k] for k in ('sceneId', 'actionId'))):
            fail('拼音听验条目不完整')
        identity = (item['sceneId'], item['actionId'])
        action = required.get(identity)
        if (identity in seen or action is None or item['textSha256'] != sha_text(action['text'].strip())
                or item['ttsRequestId'] != action.get('audioId')
                or re.fullmatch(r'tbptts1_[a-f0-9]{64}', str(item['ttsRequestId'])) is None
                or not SHA.fullmatch(str(item['audioSha256']))
                or item['verdict'] != 'accepted'
                or any(not isinstance(item[k], str) or not item[k].strip() for k in ('reviewer', 'basis'))
                or type(item['reviewedAt']) is not int or not 0 < item['reviewedAt'] <= now_ms):
            fail('拼音音频未逐段通过真实听验，或听验已不对应当前音频')
        seen.add(identity)
    if seen != set(required):
        fail('拼音听验没有完整覆盖本课所有拼音出现段落')
    return {(s['sceneId'], s['actionId']): s for s in review['segments']}
