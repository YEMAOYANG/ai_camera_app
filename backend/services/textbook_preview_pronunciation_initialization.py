"""Freeze the first pinyin profile without generating or replacing any audio.

The only activation write is an atomic plan.json installation. The adopted
classroom and DB row are unchanged; probe bytes remain evidence, never media.
"""
from datetime import datetime
from copy import deepcopy
import fcntl
import json
from pathlib import Path
import re
from types import MappingProxyType
from urllib.parse import urlparse
from xml.etree import ElementTree

from content import textbook_pinyin_pronunciation as pronunciation
from content.textbook_catalog import digest
from content.textbook_interactive_narration import without_audio_helper
from content.textbook_pinyin_operator_review import validate_operator_authorization
from content.textbook_preview_audio_contract import new_audio_plan, new_pinyin_audio_plan, resolve_audio_contract
from core.errors import ApiError
from core.security import now_ms
from services.textbook_preview_audio import bind_question_audio, core_content
from services.textbook_preview_visual_revision import immutable, json_bytes, sha_bytes
from services import textbook_pronunciation_probe_composite as composite
from services import textbook_pronunciation_probe_aieiui_composite as aieiui_composite

SCHEMA = 'mira.textbook.preview-pronunciation-initialization.v1'
OPERATOR_SCHEMA = 'mira.textbook.preview-pronunciation-initialization.v2'
COMPOSITE_HUMAN_SCHEMA = 'mira.textbook.preview-pronunciation-initialization.v3-composite-human'
APPROVAL_SCHEMA = 'mira.textbook.pinyin-initialization-approval.v1'
OPERATOR_REVIEW_SCHEMA = 'mira.textbook.pinyin-initialization-operator-review.v1'
OPERATOR_METHOD = 'user-authorized-automated-verification'
OPERATOR_RESULT = 'protocol-and-wav-verified'
OPERATOR_EVIDENCE_LIMIT = ('Probe request, SSML, provider receipts and unchanged playable PCM only; '
                           'no human listening or perceptual pronunciation/tone verification. '
                           'Formal audio requires separate complete ASR and browser review before publication.')
SHA = re.compile(r'[a-f0-9]{64}\Z')
# This evidence contract is deliberately scoped. Additional lessons need an
# explicit reviewed probe set, never inference from arbitrary Latin input.
PROBES = MappingProxyType({'i-base': 'i', 'u-base': 'u', 'umlaut-base': 'ü'})
_PROBE_CONTRACTS = MappingProxyType({
    'mira.textbook.pinyin-angengingong-ssml.v1': (
        MappingProxyType({'finals-whole-bases': 'ɑng',
                          'printed-syllables-context': 'bāng',
                          'writing-recognition-context': 'míng'}),
        'three_angengingong_fixed_probes_pronunciation_and_source_context_approved'),
    'mira.textbook.pinyin-aneninunun-ssml.v1': (
        MappingProxyType({'finals-whole-bases': 'ɑn',
                          'three-part-whole-context': 'yuán',
                          'petals-and-writing-context': 'wān'}),
        'three_aneninunun_fixed_probes_pronunciation_and_source_context_approved'),
    'mira.textbook.pinyin-ieueer-ssml.v1': (
        MappingProxyType({'ie-whole-context': 'ie',
                          'ue-whole-context': 'üe',
                          'er-source-context': 'er'}),
        'three_ieueer_fixed_probes_pronunciation_and_source_context_approved'),
    'mira.textbook.pinyin-aouiu-ssml.v1': (
        MappingProxyType({'ao-final-and-tones': 'ɑo',
                          'ou-final-and-tones': 'ou',
                          'iu-final-and-tones': 'iu'}),
        'three_aouiu_fixed_probes_pronunciation_and_tones_approved'),
    'mira.textbook.pinyin-garden3-ssml.v1': (
        MappingProxyType({
            'zimu-zhizhu-context': 'zì',
            'ca-boli-neutral-context': 'li',
            'sushe-shujia-context': 'shè',
            'qi-ma-context': 'qí',
            'tuo-di-context': 'tuō',
            'li-fa-context': 'fà',
            'ba-luobo-neutral-context': 'luó',
        }),
        'seven_garden3_phrase_probes_pronunciation_and_tones_approved'),
    'mira.textbook.pinyin-iuu-ssml.v1': (
        PROBES, 'three_base_probes_pronunciation_approved'),
    'mira.textbook.pinyin-bpmf-ssml.v1': (
        MappingProxyType({'b-base': 'b', 'p-base': 'p', 'm-base': 'm', 'f-base': 'f'}),
        'four_base_call_name_probes_pronunciation_approved'),
    'mira.textbook.pinyin-dtnl-ssml.v1': (
        MappingProxyType({'d-base': 'd', 't-base': 't', 'n-base': 'n', 'l-base': 'l',
                          'nv3-whole': 'nǚ', 'lv2-whole': 'lǘ'}),
        'six_dtnl_probes_pronunciation_and_tones_approved'),
    'mira.textbook.pinyin-garden2-ssml.v1': (
        MappingProxyType({'da4-whole': 'dà', 'mo2-whole': 'mó', 'bi3-whole': 'bǐ',
                          'pu2-whole': 'pú', 'pu4-whole': 'pù', 'la4-whole': 'là',
                          'fu2-whole': 'fú', 'ti1-whole': 'tī', 'di4-whole': 'dì'}),
        'nine_garden2_new_syllable_probes_pronunciation_and_tones_approved'),
    'mira.textbook.pinyin-gkh-ssml.v1': (
        MappingProxyType({'g-call-short-context': 'g', 'k-call-short-context': 'k',
                          'h-call-short-context': 'h', 'gua1-three-part': 'guā',
                          'kuo4-three-part': 'kuò', 'huo3-three-part': 'huǒ'}),
        'six_gkh_call_context_and_three_part_probes_pronunciation_and_tones_approved'),
    'mira.textbook.pinyin-jqx-ssml.v1': (
        MappingProxyType({'j-call-short-context': 'j', 'q-call-short-context': 'q',
                          'x-call-short-context': 'x', 'ju1-whole': 'jū',
                          'qu1-whole': 'qū', 'xu1-whole': 'xū'}),
        'six_jqx_call_context_and_umlaut_whole_probes_pronunciation_and_tones_approved'),
    'mira.textbook.pinyin-zcs-ssml.v1': (
        MappingProxyType({'z-call-short-context': 'z', 'c-call-short-context': 'c',
                          's-call-short-context': 's', 'zi3-whole': 'zǐ',
                          'ci4-whole': 'cì', 'si1-whole': 'sī'}),
        'six_zcs_call_context_and_whole_recognition_probes_pronunciation_and_tones_approved'),
    'mira.textbook.pinyin-yw-ssml.v1': (
        MappingProxyType({'y-call-and-blending-context': 'y',
                          'w-call-and-blending-context': 'w',
                          'yi-whole-and-tone': 'yi',
                          'wu-whole-and-tone': 'wu',
                          'yu-whole-and-tone': 'yu'}),
        'five_yw_call_context_and_whole_recognition_probes_pronunciation_and_tones_approved'),
    'mira.textbook.pinyin-zhchshr-ssml.v1': (
        MappingProxyType({'zh-call-and-blending-context': 'zh',
                          'ch-call-and-blending-context': 'ch',
                          'sh-call-and-blending-context': 'sh',
                          'r-call-and-blending-context': 'r',
                          'zhi-whole-and-tone': 'zhi',
                          'chi-whole-and-tone': 'chi',
                          'shi-whole-and-tone': 'shi',
                          'ri-whole-and-tone': 'ri'}),
        'eight_zhchshr_call_context_and_whole_recognition_probes_pronunciation_and_tones_approved'),
    'mira.textbook.pinyin-aieiui-ssml.v1': (
        MappingProxyType({'ai-final-and-tones': 'ɑi',
                          'ei-final-and-tones': 'ei',
                          'ui-final-and-tones': 'ui',
                          'textbook-spelling-sequences': 'gāi',
                          'pai-dui-whole': 'pái',
                          'luo-bo-neutral': 'luó'}),
        'six_aieiui_fixed_probes_pronunciation_tones_and_neutral_tone_approved'),
    'mira.textbook.pinyin-aieiui-ssml.v2': (
        MappingProxyType({'ai-final-and-tones': 'ɑi',
                          'ei-final-and-tones': 'ei',
                          'ui-final-and-tones': 'ui',
                          'textbook-spelling-sequences': 'gāi',
                          'pai-dui-whole': 'pái',
                          'luo-bo-neutral': 'luó'}),
        'six_aieiui_fixed_probes_pronunciation_tones_and_neutral_tone_approved'),
    'mira.textbook.pinyin-aieiui-ssml.v3': (
        MappingProxyType({'ai-final-and-tones': 'ɑi',
                          'ei-final-and-tones': 'ei',
                          'ui-final-and-tones': 'ui',
                          'textbook-spelling-sequences': 'gāi',
                          'pai-dui-whole': 'pái',
                          'luo-bo-neutral': 'luó'}),
        'six_aieiui_fixed_probes_pronunciation_tones_and_neutral_tone_approved'),
    'mira.textbook.pinyin-aieiui-ssml.v4': (
        MappingProxyType({'ai-final-and-tones': 'ɑi',
                          'ei-final-and-tones': 'ei',
                          'ui-final-and-tones': 'ui',
                          'textbook-spelling-sequences': 'gāi',
                          'pai-dui-whole': 'pái',
                          'luo-bo-neutral': 'luó'}),
        'six_aieiui_fixed_probes_pronunciation_tones_and_neutral_tone_approved'),
})
# GKH has component demonstrations followed by a whole syllable.
# The server owns the order; historical non-GKH probes retain their exact sounds.
_GKH_PROBE_TOKENS = MappingProxyType({
    'g-call-short-context': ('g', 'g'),
    'k-call-short-context': ('k', 'k'),
    'h-call-short-context': ('h', 'h'),
    'gua1-three-part': ('g', 'u', 'ā', 'guā'),
    'kuo4-three-part': ('k', 'u', 'ò', 'kuò'),
    'huo3-three-part': ('h', 'u', 'ǒ', 'huǒ'),
})
# This lesson pairs call names with a whole syllable, or a base with its tone example.
_ZHCHSHR_PROBE_TOKENS = MappingProxyType({
    'zh-call-and-blending-context': ('zh', 'zhā'),
    'ch-call-and-blending-context': ('ch', 'chá'),
    'sh-call-and-blending-context': ('sh', 'shà'),
    'r-call-and-blending-context': ('r', 'rè'),
    'zhi-whole-and-tone': ('zhi', 'zhí'),
    'chi-whole-and-tone': ('chi', 'chī'),
    'shi-whole-and-tone': ('shi', 'shī'),
    'ri-whole-and-tone': ('ri', 'rì'),
})
# Fixed YW pairs: call name then whole syllable, or whole base then tone.
_YW_PROBE_TOKENS = MappingProxyType({
    'y-call-and-blending-context': ('y', 'yá'),
    'w-call-and-blending-context': ('w', 'wō'),
    'yi-whole-and-tone': ('yi', 'yī'),
    'wu-whole-and-tone': ('wu', 'wǔ'),
    'yu-whole-and-tone': ('yu', 'yǔ'),
})
# Fixed complete phrases: neutral li/bo and every phoneme position are server-owned.
_GARDEN3_PROBE_TOKENS = MappingProxyType({
    'zimu-zhizhu-context': ('zì', 'mǔ', 'zhī', 'zhū'),
    'ca-boli-neutral-context': ('cā', 'bō', 'li'),
    'sushe-shujia-context': ('sù', 'shè', 'shū', 'jià'),
    'qi-ma-context': ('qí', 'mǎ'),
    'tuo-di-context': ('tuō', 'dì'),
    'li-fa-context': ('lǐ', 'fà'),
    'ba-luobo-neutral-context': ('bá', 'luó', 'bo'),
})
_AIEIUI_PROBE_TEXTS = MappingProxyType({
    'ai-final-and-tones': 'ɑi，āi、ái、ǎi、ài',
    'ei-final-and-tones': 'ei，ēi、éi、ěi、èi',
    'ui-final-and-tones': 'ui，uī、uí、uǐ、uì',
    'textbook-spelling-sequences': 'g、āi、gāi；g、u、āi、guāi；l、èi、lèi；t、uǐ、tuǐ',
    'pai-dui-whole': 'pái duì',
    'luo-bo-neutral': 'luó bo',
})
_AIEIUI_PROBE_TOKENS = MappingProxyType({
    'ai-final-and-tones': ('ɑi', 'āi', 'ái', 'ǎi', 'ài'),
    'ei-final-and-tones': ('ei', 'ēi', 'éi', 'ěi', 'èi'),
    'ui-final-and-tones': ('ui', 'uī', 'uí', 'uǐ', 'uì'),
    'textbook-spelling-sequences': (
        'g', 'āi', 'gāi', 'g', 'u', 'āi', 'guāi', 'l', 'èi', 'lèi', 't', 'uǐ', 'tuǐ'),
    'pai-dui-whole': ('pái', 'duì'),
    'luo-bo-neutral': ('luó', 'bo'),
})
PROBE_FILES = ('request.json', 'intent.json', 'receipt.json', 'provider-response.json',
               'audio.wav', 'playback.wav', 'playback-validation.json')
_AOUIU_PROBE_TEXTS = MappingProxyType({
    'ao-final-and-tones': 'ɑo，āo、áo、ǎo、ào',
    'ou-final-and-tones': 'ou，ōu、óu、ǒu、òu',
    'iu-final-and-tones': 'iu，iū、iú、iǔ、iù',
})
_AOUIU_PROBE_TOKENS = MappingProxyType({
    'ao-final-and-tones': ('ɑo', 'āo', 'áo', 'ǎo', 'ào'),
    'ou-final-and-tones': ('ou', 'ōu', 'óu', 'ǒu', 'òu'),
    'iu-final-and-tones': ('iu', 'iū', 'iú', 'iǔ', 'iù'),
})
# The printed lesson has no full tone rows. These finite probes retain whole
# syllables and source phrases; visible spelling components are never voiced.
_IEUEER_PROBE_TEXTS = MappingProxyType({
    'ie-whole-context': '请听：ie、ye。piě、dié、bié、xié、qiē、jiě。',
    'ue-whole-context': '请听：üe、yue。lüè、nüè、jué、quē、xué。',
    'er-source-context': '请听：er、ér。xiě zuò yè。méi huā kāi。xuě huā piāo。yè sè měi。yuè。',
})
_IEUEER_PROBE_TOKENS = MappingProxyType({
    'ie-whole-context': ('ie', 'ye', 'piě', 'dié', 'bié', 'xié', 'qiē', 'jiě'),
    'ue-whole-context': ('üe', 'yue', 'lüè', 'nüè', 'jué', 'quē', 'xué'),
    'er-source-context': ('er', 'ér', 'xiě', 'zuò', 'yè', 'méi', 'huā', 'kāi',
                          'xuě', 'huā', 'piāo', 'yè', 'sè', 'měi', 'yuè'),
})
# Only the exact finite voices in the source-reviewed draft are admitted.
# Visible spelling components and the unvoiced neutral men remain out of scope.
_ANENINUNUN_PROBE_TEXTS = MappingProxyType({
    'finals-whole-bases': '请听：ɑn、en、in、un、ün。yuan、yin、yun。',
    'three-part-whole-context': '请听：yuán、yīn、yùn。guān、kuān、huān、juān、quān、xuān。',
    'petals-and-writing-context': (
        '请听：wān、yǎn、nán、zhàn、duǎn、rǎn、jiān、quān；'
        'nèn、chén、kěn、zhēn、rén、wén；mín、pīn、nín、jìn、xīn、qīn；'
        'chūn、rùn、tūn、hūn、zhǔn、lún；jūn、qún、xún。lún chuán。'),
})
_ANENINUNUN_PROBE_TOKENS = MappingProxyType({
    'finals-whole-bases': ('ɑn', 'en', 'in', 'un', 'ün', 'yuan', 'yin', 'yun'),
    'three-part-whole-context': ('yuán', 'yīn', 'yùn', 'guān', 'kuān', 'huān', 'juān', 'quān', 'xuān'),
    'petals-and-writing-context': (
        'wān', 'yǎn', 'nán', 'zhàn', 'duǎn', 'rǎn', 'jiān', 'quān',
        'nèn', 'chén', 'kěn', 'zhēn', 'rén', 'wén', 'mín', 'pīn', 'nín', 'jìn', 'xīn', 'qīn',
        'chūn', 'rùn', 'tūn', 'hūn', 'zhǔn', 'lún', 'jūn', 'qún', 'xún', 'lún', 'chuán'),
})
# Four back-nasal finals, one whole form and the actual printed syllables only.
# Registering this finite protocol does not approve bare eng/ong pronunciation.
_ANGENGINGONG_PROBE_TEXTS = MappingProxyType({
    'finals-whole-bases': '请听：ɑng、eng、ing、ong。ying。',
    'printed-syllables-context': (
        '请听：bāng、huáng、qiáng、chuāng；rēng、héng、fēng、dēng；'
        'jǐng、bǐng、tīng、qīng；hǒng、zhōng、sòng、qióng。'),
    'writing-recognition-context': '请听：míng liàng。bīng、zì、xíng、chē。',
})
_ANGENGINGONG_PROBE_TOKENS = MappingProxyType({
    'finals-whole-bases': ('ɑng', 'eng', 'ing', 'ong', 'ying'),
    'printed-syllables-context': (
        'bāng', 'huáng', 'qiáng', 'chuāng', 'rēng', 'héng', 'fēng', 'dēng',
        'jǐng', 'bǐng', 'tīng', 'qīng', 'hǒng', 'zhōng', 'sòng', 'qióng'),
    'writing-recognition-context': ('míng', 'liàng', 'bīng', 'zì', 'xíng', 'chē'),
})
ARCHIVE_FILES = {'row.json', 'source.json', 'frozen.json', 'base-plan.json', 'plan.json',
                 'evidence/human-approval.json', 'evidence/plan.json'} | {
                     f'evidence/{label}/{name}' for label in PROBES for name in PROBE_FILES}


def fail(message):
    raise ApiError('textbook_preview_pronunciation_initialization_conflict', message, 409)


def _probe_contract(policy):
    """Evidence scope is server-owned; callers cannot supply a probe inventory.

    Consonant probes establish call names, not formal light-short delivery.
    Formal segments need separate publication review; a protocol-only probe
    review never establishes perceptual pronunciation or tone accuracy.
    """
    contract = _PROBE_CONTRACTS.get(policy.get('policyVersion'))
    if contract is None:
        fail('本读音政策尚未登记首次小样证据合同')
    return contract


def _evidence_key(patch):
    if patch['schemaVersion'] == OPERATOR_SCHEMA:
        return 'verifiedProbeEvidence'
    if patch['schemaVersion'] == COMPOSITE_HUMAN_SCHEMA:
        return 'approvedCompositeProbeEvidence'
    return 'approvedProbeEvidence'


def _review_file(automatic):
    return 'evidence/operator-probe-review.json' if automatic else 'evidence/human-approval.json'


def _archive_files(policy, *, automatic=False, composite_human=False):
    if composite_human:
        if policy['policyVersion'] != pronunciation.AIEIUI_V4_POLICY_VERSION:
            fail('复合人听小样只登记于 aieiui v4')
        return {'row.json', 'source.json', 'frozen.json', 'base-plan.json', 'plan.json'} | \
            aieiui_composite.evidence_names()
    if policy['policyVersion'] == pronunciation.GARDEN3_V2_POLICY_VERSION:
        if not automatic:
            fail('本课 v2 只接受明确保留原始身份的自动组合证据')
        return {'row.json', 'source.json', 'frozen.json', 'base-plan.json', 'plan.json'} | composite.evidence_names()
    probes, _ = _probe_contract(policy)
    return {'row.json', 'source.json', 'frozen.json', 'base-plan.json', 'plan.json',
            _review_file(automatic), 'evidence/plan.json'} | {
                f'evidence/{label}/{name}' for label in probes for name in PROBE_FILES}


def _json(raw):
    try:
        return json.loads(raw)
    except (TypeError, ValueError, UnicodeError):
        fail('首次拼音配置证据不是有效 JSON')


def validate_patch(patch):
    if (not isinstance(patch, dict)
            or patch.get('schemaVersion') not in {SCHEMA, OPERATOR_SCHEMA, COMPOSITE_HUMAN_SCHEMA}):
        fail('不支持的首次拼音配置版本')
    fields = {'schemaVersion', 'expectedSourceSha256', 'expectedCoreSha256',
              'pronunciationPolicyVersion', 'pronunciationPolicySha256',
              'reviewer', 'basis', _evidence_key(patch)}
    if (set(patch) != fields
            or any(not SHA.fullmatch(str(patch[k])) for k in
                   ('expectedSourceSha256', 'expectedCoreSha256', 'pronunciationPolicySha256'))
            or any(not isinstance(patch[k], str) or not patch[k].strip()
                   for k in ('pronunciationPolicyVersion', 'reviewer', 'basis'))):
        fail('首次配置必须绑定采用后的课件、内容和已登记读音政策')
    item = patch[_evidence_key(patch)]
    if (not isinstance(item, dict) or set(item) != {'path', 'sha256'}
            or not isinstance(item['path'], str) or not item['path']
            or not SHA.fullmatch(str(item['sha256']))):
        fail('首次小样核验证据需要文件及原字节摘要')


def _verify_operator_review(review, patch, key, frozen, policy, *,
                            review_schema=OPERATOR_REVIEW_SCHEMA, evidence_limit=OPERATOR_EVIDENCE_LIMIT):
    fields = {'schemaVersion', 'method', 'previewKey', 'sourceSha256', 'coreSha256',
              'pronunciationPolicyVersion', 'pronunciationPolicySha256', 'reviewer', 'recordedAt',
              'authorization', 'result', 'humanListeningVerified', 'perceptualToneVerified',
              'formalUseAllowed', 'probePlanSha256', 'samples', 'evidenceLimit', 'sha256'}
    if (not isinstance(review, dict) or set(review) != fields
            or review['sha256'] != digest({k: v for k, v in review.items() if k != 'sha256'})
            or review['schemaVersion'] != review_schema or review['method'] != OPERATOR_METHOD
            or review['previewKey'] != key or review['sourceSha256'] != patch['expectedSourceSha256']
            or review['coreSha256'] != patch['expectedCoreSha256']
            or review['pronunciationPolicyVersion'] != policy['policyVersion']
            or review['pronunciationPolicySha256'] != digest(policy)
            or review['result'] != OPERATOR_RESULT or review['formalUseAllowed'] is not False
            or review['humanListeningVerified'] is not False or review['perceptualToneVerified'] is not False
            or review['evidenceLimit'] != evidence_limit
            or not isinstance(review['reviewer'], str) or not review['reviewer'].strip()
            or type(review['recordedAt']) is not int or not 0 < review['recordedAt'] <= now_ms()):
        fail('自动小样核验必须明确证据范围，不能冒充人听、声调准确或正式音频通过')
    validate_operator_authorization(review['authorization'], binding=frozen, recorded_at=review['recordedAt'])


def _verify_evidence(files, patch, key, frozen, policy):
    if patch['schemaVersion'] == COMPOSITE_HUMAN_SCHEMA:
        raw = files['evidence/human-approval.json']
        review = _json(raw)
        if (sha_bytes(raw) != patch['approvedCompositeProbeEvidence']['sha256']
                or patch['pronunciationPolicyVersion'] != policy['policyVersion']
                or patch['pronunciationPolicySha256'] != digest(policy)):
            fail('ɑi ei ui 复合人听字节或目标政策不一致')
        aieiui_composite.verify_files(files, review, frozen, policy)
        return
    if policy['policyVersion'] == pronunciation.GARDEN3_V2_POLICY_VERSION:
        if patch['schemaVersion'] != OPERATOR_SCHEMA:
            fail('本课 v2 不能使用历史人听格式')
        raw = files[_review_file(True)]
        review = _json(raw)
        if (sha_bytes(raw) != patch['verifiedProbeEvidence']['sha256']
                or patch['pronunciationPolicyVersion'] != policy['policyVersion']
                or patch['pronunciationPolicySha256'] != digest(policy)):
            fail('组合核验字节或目标政策不一致')
        _verify_operator_review(review, patch, key, frozen, policy,
                                review_schema=composite.REVIEW_SCHEMA, evidence_limit=composite.LIMIT)
        composite.verify_files(files, review, frozen, policy)
        return
    probes, approval_result = _probe_contract(policy)
    automatic = patch['schemaVersion'] == OPERATOR_SCHEMA
    raw = files[_review_file(automatic)]
    approval = _json(raw)
    if (sha_bytes(raw) != patch[_evidence_key(patch)]['sha256']
            or patch['pronunciationPolicyVersion'] != policy['policyVersion']
            or patch['pronunciationPolicySha256'] != digest(policy)):
        fail('小样核验字节或读音政策与本次配置不一致')
    if automatic:
        _verify_operator_review(approval, patch, key, frozen, policy)
    else:
        _verify_human_approval(approval, patch, key, policy, approval_result)
    _verify_probe_files(files, approval, frozen, policy, probes,
                        sample_result=OPERATOR_RESULT if automatic else 'approved_by_human_listening')


def _verify_human_approval(approval, patch, key, policy, approval_result):
    fields = {'schemaVersion', 'previewKey', 'sourceSha256', 'pronunciationPolicyVersion',
              'pronunciationPolicySha256', 'reviewer', 'receivedAt', 'statements', 'result',
              'formalUseAllowed', 'probePlanSha256', 'samples'}
    if (not isinstance(approval, dict) or set(approval) != fields
            or approval['schemaVersion'] != APPROVAL_SCHEMA or approval['previewKey'] != key
            or approval['sourceSha256'] != patch['expectedSourceSha256']
            or approval['pronunciationPolicyVersion'] != policy['policyVersion']
            or approval['pronunciationPolicySha256'] != digest(policy)
            or approval['result'] != approval_result
            or approval['formalUseAllowed'] is not False
            or not isinstance(approval['reviewer'], str) or not approval['reviewer'].strip()
            or not isinstance(approval['statements'], list) or not approval['statements']
            or any(not isinstance(s, str) or not s.strip() for s in approval['statements'])):
        fail('小样认可没有绑定当前课件及政策，或误充当正式音频审核')
    try:
        if datetime.fromisoformat(approval['receivedAt'].replace('Z', '+00:00')).tzinfo is None:
            fail('小样认可时间必须带时区')
    except (ValueError, TypeError, AttributeError):
        fail('小样认可时间无效')


def _verify_probe_files(files, approval, frozen, policy, probes, *, sample_result):
    """Shared byte/SSML verification; the review method does not weaken it."""
    plan_raw = files['evidence/plan.json']
    probe_plan = _json(plan_raw)
    if (sha_bytes(plan_raw) != approval['probePlanSha256']
            or probe_plan.get('schemaVersion') != 'mira.operator.phonetic-ssml-probe.v1'
            or probe_plan.get('formalUseAllowed') is not False
            or probe_plan.get('plannedCalls') != len(probes)
            or probe_plan.get('sourceLesson', {}).get('editionId') != frozen['editionId']
            or probe_plan.get('sourceLesson', {}).get('nodeId') != frozen['nodeId']
            or any(probe_plan.get(k) != policy[v] for k, v in
                   (('provider', 'providerId'), ('model', 'modelId'), ('voice', 'voiceId')))):
        fail('原始小样计划来源或服务身份不一致')
    samples, planned = approval['samples'], probe_plan.get('samples')
    if (not isinstance(samples, list) or not isinstance(planned, list)
            or len(samples) != len(probes) or len(planned) != len(probes)
            or any(not isinstance(s, dict) for s in samples + planned)
            or {s.get('label') for s in samples} != set(probes)
            or {s.get('label') for s in planned} != set(probes)):
        fail('基础音小样必须完整且各有唯一来源')
    for sample in samples:
        label = sample['label']
        target = probes[label]
        expected = policy['symbols'].get(target)
        fields = {'label', 'target', 'phonemeCandidate', 'providerRequestId', 'requestSha256',
                  'providerResponseSha256', 'providerAudioSha256', 'playbackSha256', 'pcmSha256', 'result'}
        if (set(sample) != fields or expected is None or sample['target'] != target
                or sample['phonemeCandidate'] != expected['ph']
                or sample['result'] != sample_result):
            fail('认可小样的目标或音素不是已登记的基础音')
        raws = {name: files[f'evidence/{label}/{name}'] for name in PROBE_FILES}
        request, intent, receipt, response, validation = (_json(raws[name]) for name in
            ('request.json', 'intent.json', 'receipt.json', 'provider-response.json', 'playback-validation.json'))
        original = next(p for p in planned if p['label'] == label)
        if (original.get('body') != request or original.get('target') != target
                or original.get('phonemeCandidate') != expected['ph'] or original.get('carrier') != expected['carrier']
                or original.get('requestSha256') != sha_bytes(raws['request.json'])
                or request.get('model') != policy['modelId']
                or set(request) != {'model', 'input'} or not isinstance(request['input'], dict)
                or set(request['input']) != set(policy['inputParameters']) | {'text'}
                or any(request['input'].get(k) != v for k, v in policy['inputParameters'].items())):
            fail('原始小样请求与计划或冻结配置不一致')
        ssml = request['input']['text']
        try:
            xml = ElementTree.fromstring(ssml)
        except (ElementTree.ParseError, TypeError):
            fail('原始小样 SSML 无效')
        phonemes = list(xml.iter('phoneme'))
        tokens = (_GKH_PROBE_TOKENS[label] if policy['policyVersion'] == pronunciation.GKH_POLICY_VERSION
                  else _ZHCHSHR_PROBE_TOKENS[label]
                  if policy['policyVersion'] == pronunciation.ZHCHSHR_POLICY_VERSION
                  else _YW_PROBE_TOKENS[label]
                  if policy['policyVersion'] == pronunciation.YW_POLICY_VERSION
                  else _GARDEN3_PROBE_TOKENS[label]
                  if policy['policyVersion'] == pronunciation.GARDEN3_POLICY_VERSION
                  else _AOUIU_PROBE_TOKENS[label]
                  if policy['policyVersion'] == pronunciation.AOUIU_POLICY_VERSION
                  else _IEUEER_PROBE_TOKENS[label]
                  if policy['policyVersion'] == pronunciation.IEUEER_POLICY_VERSION
                  else _ANENINUNUN_PROBE_TOKENS[label]
                  if policy['policyVersion'] == pronunciation.ANENINUNUN_POLICY_VERSION
                  else _ANGENGINGONG_PROBE_TOKENS[label]
                  if policy['policyVersion'] == pronunciation.ANGENGINGONG_POLICY_VERSION
                  else _AIEIUI_PROBE_TOKENS[label]
                  if policy['policyVersion'] in {
                      pronunciation.AIEIUI_POLICY_VERSION,
                      pronunciation.AIEIUI_V2_POLICY_VERSION,
                      pronunciation.AIEIUI_V3_POLICY_VERSION,
                      pronunciation.AIEIUI_V4_POLICY_VERSION,
                  } else (target, target))
        expected_phonemes = ([{
            'ph': ' '.join(policy['symbols'][token]['ph'] for token in tokens),
            'carrier': ''.join(policy['symbols'][token]['carrier'] for token in tokens),
        }] if (policy['policyVersion'] == pronunciation.AIEIUI_V3_POLICY_VERSION
               and label == 'luo-bo-neutral')
            else [policy['symbols'][token] for token in tokens])
        v4_luo_bo = (policy['policyVersion'] == pronunciation.AIEIUI_V4_POLICY_VERSION
                     and label == 'luo-bo-neutral')
        aliases = list(xml.iter('sub'))
        valid_shape = (len(xml) == 1 and not phonemes and len(aliases) == 1
                       and aliases[0].attrib == {'alias': '萝卜'}
                       and aliases[0].text == 'luó bo' and not len(aliases[0])
                       and aliases[0].tail == '。') if v4_luo_bo else (
            not aliases and len(phonemes) == len(expected_phonemes)
            and all(p.attrib == {'alphabet': 'py', 'ph': entry['ph']}
                    and p.text == entry['carrier'] and not len(p)
                    for p, entry in zip(phonemes, expected_phonemes)))
        if (xml.tag != 'speak' or '<!' in ssml or not valid_shape
                or original.get('ssmlSha256') != sha_bytes(ssml.encode())):
            fail('原始小样 SSML 不符合本课已登记的音素顺序')
        if policy['policyVersion'] in {
                pronunciation.AIEIUI_POLICY_VERSION,
                pronunciation.AIEIUI_V2_POLICY_VERSION,
                pronunciation.AIEIUI_V3_POLICY_VERSION,
                pronunciation.AIEIUI_V4_POLICY_VERSION,
                pronunciation.AOUIU_POLICY_VERSION,
                pronunciation.IEUEER_POLICY_VERSION,
                pronunciation.ANENINUNUN_POLICY_VERSION,
                pronunciation.ANGENGINGONG_POLICY_VERSION,
        }:
            source_text = (_AOUIU_PROBE_TEXTS[label]
                           if policy['policyVersion'] == pronunciation.AOUIU_POLICY_VERSION
                           else _IEUEER_PROBE_TEXTS[label]
                           if policy['policyVersion'] == pronunciation.IEUEER_POLICY_VERSION
                           else _ANENINUNUN_PROBE_TEXTS[label]
                           if policy['policyVersion'] == pronunciation.ANENINUNUN_POLICY_VERSION
                           else _ANGENGINGONG_PROBE_TEXTS[label]
                           if policy['policyVersion'] == pronunciation.ANGENGINGONG_POLICY_VERSION
                           else _AIEIUI_PROBE_TEXTS[label])
            if (original.get('sourceText') != source_text
                    or original.get('tokens') != list(tokens)
                    or request != pronunciation.provider_body(
                        source_text, policy_version=policy['policyVersion'])):
                fail('复韵母小样必须使用服务端登记的固定原文和完整音节顺序')
        checks = {'requestSha256': sha_bytes(raws['request.json']),
                  'providerResponseSha256': sha_bytes(raws['provider-response.json']),
                  'providerAudioSha256': sha_bytes(raws['audio.wav']),
                  'playbackSha256': sha_bytes(raws['playback.wav']),
                  'pcmSha256': sha_bytes(raws['playback.wav'][44:]),
                  'providerRequestId': response.get('request_id')}
        if (any(sample.get(k) != v or receipt.get(k) != v for k, v in checks.items())
                or not isinstance(checks['providerRequestId'], str) or not checks['providerRequestId']
                or receipt.get('status') != 'succeeded' or receipt.get('formalUseAllowed') is not False
                or receipt.get('postAttempts') != 1 or receipt.get('target') != target
                or receipt.get('phonemeCandidate') != expected['ph']
                or any(receipt.get(k) != policy[v] for k, v in
                       (('provider', 'providerId'), ('model', 'modelId'), ('voice', 'voiceId')))
                or receipt.get('audioSha256') != checks['playbackSha256']
                or receipt.get('planSha256') != approval['probePlanSha256']
                or intent.get('requestSha256') != checks['requestSha256']
                or intent.get('planSha256') != approval['probePlanSha256']
                or intent.get('formalUseAllowed') is not False
                or response.get('output', {}).get('finish_reason') != 'stop'
                or response.get('usage') != receipt.get('usage')):
            fail('小样请求、供应商回执或原音频证据不一致')
        pronunciation.validate_receipt_wav(receipt, raws['playback.wav'])
        if (validation.get('schemaVersion') != 'mira.operator.probe-wav-validation.v1'
                or validation.get('pcmUnchanged') is not True
                or validation.get('audioNormalization') != receipt['audioNormalization']
                or any(validation.get(k) != checks[k] for k in
                       ('providerAudioSha256', 'playbackSha256', 'pcmSha256'))
                or raws['audio.wav'][44:] != raws['playback.wav'][44:]):
            fail('播放小样必须保留原供应商 PCM')


def _evidence_files(patch, policy):
    if patch['schemaVersion'] == COMPOSITE_HUMAN_SCHEMA:
        if policy['policyVersion'] != pronunciation.AIEIUI_V4_POLICY_VERSION:
            fail('复合人听小样只登记于 aieiui v4')
        return aieiui_composite.read_files(patch['approvedCompositeProbeEvidence']['path'])
    if policy['policyVersion'] == pronunciation.GARDEN3_V2_POLICY_VERSION:
        if patch['schemaVersion'] != OPERATOR_SCHEMA:
            fail('本课 v2 需要自动组合证据')
        return composite.read_files(patch['verifiedProbeEvidence']['path'])
    probes, _ = _probe_contract(policy)
    path = Path(patch[_evidence_key(patch)]['path']).resolve()
    review_raw = path.read_bytes()
    if _json(review_raw).get('schemaVersion') == aieiui_composite.REVIEW_SCHEMA:
        fail('ɑi ei ui 复合人听证据必须使用显式复合初始化版本')
    files = {_review_file(patch['schemaVersion'] == OPERATOR_SCHEMA): review_raw,
             'evidence/plan.json': (path.parent / 'plan.json').read_bytes()}
    for label in probes:
        for name in PROBE_FILES:
            source = path.parent / label / name
            if source.resolve().parent != path.parent / label:
                fail('小样文件不能跨越固定证据目录')
            files[f'evidence/{label}/{name}'] = source.read_bytes()
    return files


def _without_audio(classroom):
    # Question/feedback bindings are derived by the narrator. Verify them against
    # the current exact speech before excluding them from the authoring identity.
    # A malformed binding must not become invisible to this recovery check.
    bound = deepcopy(classroom)
    for scene in bound['scenes']:
        if scene.get('type') == 'quiz':
            scene['content']['questions'] = [
                question for question in scene['content'].get('questions', [])
                if question.get('questionAudioUrl') or question.get('questionAudioBinding')
                or any(feedback.get('audioUrl') or feedback.get('audioBinding')
                       for feedback in (question.get('optionFeedback') or {}).values())]
    bind_question_audio(bound)
    result = core_content(classroom)
    for scene in result['scenes']:
        if scene.get('type') == 'interactive':
            scene['content']['html'] = without_audio_helper(scene['content']['html'])
        for question in scene.get('content', {}).get('questions', []):
            question.pop('questionAudioUrl', None)
            question.pop('questionAudioBinding', None)
            for feedback in (question.get('optionFeedback') or {}).values():
                feedback.pop('audioUrl', None)
                feedback.pop('audioBinding', None)
    return result


def _zero_audio(source, result, folder, root, cid, *, installation_bytes=None):
    allowed = {'operator.lock', 'pronunciation-initializations'}
    staging = folder / 'plan.json.tmp'
    if installation_bytes is not None and staging.exists():
        # Only a complete staging file belonging to the verified intent is
        # recoverable. Unknown/partial local files remain a conservative stop.
        if staging.is_symlink() or not staging.is_file() or staging.read_bytes() != installation_bytes:
            fail('首次配置安装暂存文件不等于已核验目标，不能覆盖')
        allowed.add(staging.name)
    if (core_content(source) != _without_audio(source)
            or any(any(k in a for k in ('audioId', 'audioUrl', 'audioMetadata'))
                   for s in source['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech')
            or any(result.get(k) for k in ('audioReceipts', 'audioPartial', 'audioStopCode', 'audioCompleted',
                       'audioAudit', 'audioReview', 'frozenPreview', 'narrationRevisions', 'pronunciationRevisions'))
            or any((root / cid / 'audio').glob('*'))
            or any(p.name not in allowed for p in folder.iterdir())):
        fail('首次拼音配置仅接受零音频新课；已有调用、回执或绑定必须保留并单独处理')


def initialize_preview_pronunciation(service, key, classroom_directory, patch, *, execute=False):
    validate_patch(patch)
    # Resolve the version before reading any caller-nominated evidence. New
    # plans additionally require the current lesson policy below; recovery
    # validates the historical frozen plan instead of a future default.
    automatic = patch['schemaVersion'] == OPERATOR_SCHEMA
    composite_human = patch['schemaVersion'] == COMPOSITE_HUMAN_SCHEMA
    archive_files = _archive_files(pronunciation.registered_policy(patch['pronunciationPolicyVersion']),
                                   automatic=automatic, composite_human=composite_human)
    row = service.get(key)
    cid, root = row['classroom_id'], Path(classroom_directory).resolve()
    if (urlparse(service.runtime.base_url).hostname not in {'localhost', '127.0.0.1', '::1'}
            or not re.fullmatch(r'[A-Za-z0-9_-]+', cid or '')):
        fail('只支持本机已采用的未发布课件')
    folder = root / cid / 'textbook-preview-audio'
    folder.mkdir(parents=True, exist_ok=True)
    initialization_id = digest({'previewKey': key, 'patch': patch})
    archive = folder / 'pronunciation-initializations' / initialization_id
    with (folder / 'operator.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail('课件正在配音或修改配置')
        with service.repository.transaction() as conn:
            row = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE', (key,)).fetchone()
            if (row is None or row['classroom_id'] != cid or row['runtime_origin'] != service.runtime.base_url
                    or row['status'] not in {'review_required', 'preview_ready'}):
                fail('课件运行身份或状态已改变')
            builds = conn.execute("SELECT input_json FROM learning_textbook_course_builds WHERE edition_id=? AND node_id=? AND status='published'",
                                  (row['edition_id'], row['node_id'])).fetchall()
            if any(service.repository.parse(b['input_json']).get('previewKey') == key for b in builds):
                fail('已发布课件不能初始化配音配置')
            frozen = service.repository.parse(row['input_json'])
            if (not pronunciation.initialization_required(frozen)
                    or (row['edition_id'], row['revision_id'], row['node_id']) !=
                       (frozen['editionId'], frozen['alignmentRevisionId'], frozen['nodeId'])):
                fail('本课没有登记首次拼音配置要求')
            source = service.repository.parse(row['classroom_json'])
            if (digest(source) != row['classroom_sha256'] or source.get('id') != cid
                    or source.get('stage', {}).get('id') != cid
                    or service.runtime.get_classroom(cid) != source
                    or _json((root / (cid + '.json')).read_bytes()) != source):
                fail('数据库、运行课件及本地文件必须完全一致')
            intent_path, active = archive / 'intent.json', folder / 'plan.json'
            if not intent_path.exists():
                _zero_audio(source, service.repository.parse(row['result_json']) or {}, folder, root, cid)
                if (row['status'] != 'review_required' or digest(source) != patch['expectedSourceSha256']
                        or digest(core_content(source)) != patch['expectedCoreSha256']):
                    fail('采用后的原始课件或内容摘要已变化')
                policy = pronunciation.select_policy(frozen)
                if (policy['policyVersion'] != patch['pronunciationPolicyVersion']
                        or digest(policy) != patch['pronunciationPolicySha256']):
                    fail('请求的政策不等于服务端本课已审核配置')
                files = _evidence_files(patch, policy)
                _verify_evidence(files, patch, key, frozen, policy)
                base = new_audio_plan(preview_key=key, classroom_sha256=digest(source),
                                      core_sha256=digest(core_content(source)), frozen_input=frozen)
                plan = new_pinyin_audio_plan(preview_key=key, classroom_sha256=digest(source),
                    core_sha256=digest(core_content(source)), frozen_input=frozen,
                    parent_plan=base, revision_id=initialization_id)
                for scene in source['scenes']:
                    for action in scene.get('actions', []):
                        if action.get('type') == 'speech':
                            pronunciation.pronunciation_identity(action['text'].strip(), policy_version=policy['policyVersion'])
                files.update({'row.json': json_bytes(row), 'source.json': json_bytes(source),
                              'frozen.json': json_bytes(frozen), 'base-plan.json': json_bytes(base),
                              'plan.json': json_bytes(plan)})
                for name, raw in files.items():
                    target = archive / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    immutable(target, raw)
                intent = {'schemaVersion': patch['schemaVersion'], 'initializationId': initialization_id, 'previewKey': key,
                          'classroomId': cid, 'patch': patch, 'files': {k: sha_bytes(v) for k, v in files.items()}}
                intent['sha256'] = digest(intent)
                immutable(intent_path, json_bytes(intent))
            intent = _json(intent_path.read_bytes())
            if (intent.get('sha256') != digest({k: v for k, v in intent.items() if k != 'sha256'})
                    or intent.get('schemaVersion') != patch['schemaVersion'] or intent.get('patch') != patch
                    or intent.get('previewKey') != key or intent.get('classroomId') != cid
                    or intent.get('initializationId') != initialization_id
                    or set(intent.get('files', {})) != archive_files):
                fail('首次配置归档身份无效')
            files = {name: (archive / name).read_bytes() for name in archive_files}
            if any(sha_bytes(raw) != intent['files'][name] for name, raw in files.items()):
                fail('首次配置归档字节已变化')
            plan, base = _json(files['plan.json']), _json(files['base-plan.json'])
            resolve_audio_contract(plan, frozen)
            resolve_audio_contract(base, frozen)
            if (files['frozen.json'] != json_bytes(frozen) or plan['previewKey'] != key
                    or plan.get('revisionId') != initialization_id or plan.get('parentPlanSha256') != digest(base)
                    or plan['classroomSha256'] != patch['expectedSourceSha256']
                    or plan['coreSha256'] != patch['expectedCoreSha256']
                    or digest(_without_audio(source)) != plan['coreSha256']):
                fail('首次配置来源、冻结内容或当前课件已变化')
            _verify_evidence(files, patch, key, frozen, pronunciation.policy_for_plan(plan))
            if active.exists():
                if active.read_bytes() != files['plan.json']:
                    fail('已有其他活动配音计划，不能覆盖')
            else:
                if row != _json(files['row.json']):
                    fail('准备后数据库记录已变化，不能激活配置')
                _zero_audio(source, service.repository.parse(row['result_json']) or {}, folder, root, cid,
                            installation_bytes=files['plan.json'])
                if execute:
                    immutable(active, files['plan.json'])
            result = {'schemaVersion': patch['schemaVersion'], 'initializationId': initialization_id,
                      'intentSha256': intent['sha256'], 'previewKey': key, 'classroomId': cid,
                      'sourceSha256': patch['expectedSourceSha256'], 'coreSha256': plan['coreSha256'],
                      'audioPlanSha256': digest(plan), 'parentPlanSha256': digest(base),
                      'generationDispatched': False, 'publicationAllowed': False,
                      'requiresFormalHumanListening': not automatic}
            if automatic:
                result.update(verifiedProbeEvidenceSha256=patch['verifiedProbeEvidence']['sha256'],
                              requiresFormalOperatorReview=True, humanListeningVerified=False,
                              perceptualToneVerified=False, evidenceLimit=OPERATOR_EVIDENCE_LIMIT)
            elif composite_human:
                result.update(
                    approvedCompositeProbeEvidenceSha256=patch['approvedCompositeProbeEvidence']['sha256'],
                    probeHumanListeningVerified=True, perceptualToneVerifiedForProbeScope=True,
                    requiresFormalSentenceListening=True, evidenceLimit=aieiui_composite.LIMIT)
            else:
                result['approvedProbeEvidenceSha256'] = patch['approvedProbeEvidence']['sha256']
            result['sha256'] = digest(result)
            if execute:
                immutable(archive / 'initialization.json', json_bytes(result))
                return result
            return {**result, 'prepared': True, 'initialized': active.exists(), 'archive': str(archive)}
