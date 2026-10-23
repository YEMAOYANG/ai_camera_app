"""Read-only integrity gate for native textbook author candidates.

This verifies frozen identity and exact saved artifacts, not semantic teaching
quality, real audio playback, review, or permission to publish. Historical jobs
without the v3 contract retain their original adoption path.
"""
from __future__ import annotations

import hashlib
import io
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from PIL import Image

from content.textbook_catalog import canonical, digest, identifier, lesson_by_id
from content.textbook_interactive_narration import interactive_cues
from content.textbook_preview import responsive_activity_marker
from content.textbook_review_followup import discover_complete_scene_review_followup
from content.textbook_scene_contract import scene_canonical
from core.errors import ApiError
from services.course_reuse_resolver import lesson_scope

JOB_SCHEMA = 'mira.operator.workbench-authoring.v3'
LEGACY_JOB_SCHEMAS = {'mira.operator.workbench-authoring.v1', 'mira.operator.workbench-authoring.v2'}
CANDIDATE_SCHEMA = 'mira.textbook.authoring-candidate.v1'
CANDIDATE_FILE = 'textbook-authoring-candidate.json'
DEFAULT_AUTHORING_ROOT = Path(__file__).resolve().parents[2] / 'output/textbook-operator-lessons'
SHA = re.compile(r'^[a-f0-9]{64}$')
IMAGE_URL = re.compile(r'^/api/classroom-media/([A-Za-z0-9_-]+)/media/([A-Za-z0-9_.-]+\.(?:png|webp|jpe?g))$')
IMAGE_REFERENCE = re.compile(r'/api/classroom-media/[A-Za-z0-9_-]+/media/[A-Za-z0-9_.-]+\.(?:png|webp|jpe?g)')


def reject(message):
    raise ApiError('textbook_preview_candidate_invalid', message, 409)


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON member')
        result[key] = value
    return result


def _loads(text):
    return json.loads(text, object_pairs_hook=_object_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))


def _read_json(path):
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError()
        value = _loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (OSError, UnicodeError, ValueError):
        reject('候选或冻结记录缺失、不是完整 JSON，或包含重复字段；请保留原记录后修订')


def _safe_child(root, path):
    """Do not follow links out of the managed evidence tree."""
    if not path.resolve().is_relative_to(root.resolve()):
        reject('候选文件路径超出已管理目录')
    for item in (path, *path.parents):
        if item == root:
            break
        if item.is_symlink():
            reject('候选或素材路径不能使用符号链接')
    return path


def _saved_stages(state):
    saved = state.get('savedStages', [])
    if not isinstance(saved, list):
        reject('作者会话的已保存课堂记录无效')
    return {item.get('stageId') for item in saved if isinstance(item, dict) and isinstance(item.get('stageId'), str)}


def _find_job(output_root, edition, revision, node, session_id, stage_id, has_ledger):
    if not all(identifier(v) for v in (edition, revision, node)):
        reject('教材绑定身份无效')
    root = Path(output_root).resolve()
    lesson = _safe_child(root, root / edition / node)
    jobs, v3_present = [], False
    v3_stage_owners = set()
    for job in sorted(lesson.glob('teaching-*/authoring-job')):
        _safe_child(root, job)
        if not (job / 'frozen.json').exists():
            continue
        frozen = _read_json(job / 'frozen.json')
        schema = frozen.get('schemaVersion')
        binding = frozen.get('binding', {})
        if not isinstance(binding, dict) or binding.get('editionId') != edition or binding.get('nodeId') != node:
            reject('冻结任务目录与教材绑定不一致')
        v3_present |= schema == JOB_SCHEMA
        state = _read_json(job / 'state.json')
        if schema == JOB_SCHEMA and stage_id in _saved_stages(state):
            v3_stage_owners.add(state.get('sessionId'))
        if state.get('sessionId') == session_id and session_id:
            jobs.append((job, frozen, state))
    if len(jobs) > 1:
        reject('同一会话对应多个冻结任务，请先核对原任务')
    if not jobs:
        if has_ledger or v3_present:
            reject('候选缺少对应的真实冻结 v3 会话；不能通过替换会话或删除台账退回旧流程')
        return None
    job, frozen, state = jobs[0]
    if v3_stage_owners and v3_stage_owners != {session_id}:
        reject('当前原生课堂属于另一个 v3 会话，不能通过历史会话降级接收')
    if frozen.get('schemaVersion') != JOB_SCHEMA:
        if v3_present and stage_id not in _saved_stages(state):
            reject('当前课堂不是所选历史会话的真实保存成果，不能绕过 v3 门禁')
        if has_ledger or frozen.get('schemaVersion') not in LEGACY_JOB_SCHEMAS:
            reject('候选台账不能绑定历史或未知任务版本')
        return None
    if not has_ledger:
        reject('v3 任务必须保留原生候选台账，不能退回历史接收流程')
    if frozen['binding'].get('revisionId') != revision:
        reject('候选教材修订与原冻结任务不一致')
    return job, frozen, state


def _contract(job, frozen, manifest, node):
    # Imported here to keep legacy adoption independent of the new contract.
    from content.textbook_scene_contract import validate_scene_contract
    draft = _read_json(job / 'draft.json')
    try:
        raw = (job / 'draft.json').read_bytes()
        if (hashlib.sha256(raw).hexdigest() != frozen.get('draftSha256')
                or digest(draft) != frozen.get('draftCanonicalSha256')
                or hashlib.sha256(draft['request'].encode()).hexdigest() != frozen.get('requestSha256')
                or draft.get('binding') != frozen.get('binding')
                or draft.get('teacherContract') != frozen.get('teacherContract')):
            raise ValueError()
        contract = validate_scene_contract(frozen.get('sceneContract'), draft=draft,
            catalog_check=frozen.get('catalogCheck'), interaction_policy=frozen.get('interactionPolicy'))
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        reject('冻结场景合同或原始草稿摘要不一致，请从原任务建立明确修订')
    unit, lesson = lesson_by_id(manifest, node)
    expected = {k: manifest[k] for k in ('editionId', 'revisionId', 'gradeCode', 'subject', 'volume', 'schoolSystem')}
    expected.update(nodeId=node, unitId=unit['unitId'], unitTitle=unit['title'], lessonTitle=lesson['title'])
    if any(contract['binding'].get(key) != value for key, value in expected.items()):
        reject('冻结合同与实际教材、年级、学科或课次不一致')
    if contract.get('binding') != frozen.get('binding') or contract.get('catalogEvidence') != {'manifestSha256': digest(manifest), 'lessonScopeSha256': lesson_scope(manifest, node)}:
        reject('教材目录或本课范围已变化，不能采用旧冻结合同的候选')
    return contract


ASSET_FIELDS = {'assetKey', 'src', 'sha256', 'width', 'height', 'bindingVersion', 'status'}


def _asset(asset, directory, stage_id):
    if (not isinstance(asset, dict) or set(asset) != ASSET_FIELDS
            or not identifier(asset.get('assetKey')) or asset.get('status') != 'author_candidate'
            or not isinstance(asset.get('sha256'), str) or not SHA.fullmatch(asset['sha256'])
            or type(asset.get('bindingVersion')) is not int or not 1 <= asset['bindingVersion'] <= 2 ** 53 - 1
            or any(type(asset.get(k)) is not int or not 1 <= asset[k] <= 2 ** 53 - 1 for k in ('width', 'height'))):
        reject('候选图片绑定身份、版本或尺寸无效')
    match = IMAGE_URL.fullmatch(asset.get('src', ''))
    if match is None:
        reject('候选图片必须引用原生素材目录中的原字节')
    owner, name = match.groups()
    if owner != stage_id:
        reject('候选图片必须属于本次原生课堂，跨课堂素材需要明确复制和重新绑定')
    path = _safe_child(directory, directory / owner / 'media' / name)
    try:
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != asset['sha256']:
            raise ValueError()
        with Image.open(io.BytesIO(raw)) as image:
            if image.size != (asset['width'], asset['height']) or image.format not in ('PNG', 'JPEG', 'WEBP'):
                raise ValueError()
            image.verify()
    except (OSError, ValueError, Image.DecompressionBombError):
        reject('原始图片字节、摘要或真实尺寸已变化')
    return asset


def _assets(ledger, directory, stage_id):
    bindings, history = ledger.get('assetBindings'), ledger.get('bindingHistory')
    if not isinstance(bindings, list) or not isinstance(history, list):
        reject('候选缺少已绑定的原始图片或绑定历史')
    result = {}
    for asset in bindings:
        _asset(asset, directory, stage_id)
        if asset['assetKey'] in result:
            reject('候选图片 assetKey 重复')
        result[asset['assetKey']] = asset
    chains = {}
    for change in history:
        if not isinstance(change, dict) or set(change) != {'assetKey', 'from', 'to'}:
            reject('图片重新绑定历史格式无效')
        before, after = _asset(change['from'], directory, stage_id), _asset(change['to'], directory, stage_id)
        key = change['assetKey']
        if (key not in result or key != before['assetKey'] or key != after['assetKey']
                or after['bindingVersion'] != before['bindingVersion'] + 1
                or before != chains.get(key, before) or key not in chains and before['bindingVersion'] != 1):
            reject('图片重新绑定历史缺失、跳号或属于其他素材')
        chains[key] = after
    for key, current in result.items():
        if (key in chains and chains[key] != current) or (key not in chains and current['bindingVersion'] != 1):
            reject('当前图片绑定与原始绑定历史不一致')
    return result


def _scenes(ledger, classroom, contract):
    records, actual, plan = ledger.get('scenes'), classroom.get('scenes'), contract.get('pagePlan')
    if (not isinstance(records, list) or not isinstance(actual, list) or not isinstance(plan, list)
            or not records or len(records) != len(actual) or len(actual) != len(plan)):
        reject('候选必须完整覆盖冻结计划和实际课堂的全部页面')
    ids = set()
    for index, (record, scene, page) in enumerate(zip(records, actual, plan)):
        if (not isinstance(record, dict) or set(record) != {'sceneId', 'order', 'sha256', 'canonicalJson', 'contractSha256'}
                or not isinstance(scene, dict)
                or record.get('sceneId') != scene.get('id') or not identifier(scene.get('id'))
                or scene['id'] in ids or scene.get('stageId') != classroom['id']
                or type(record.get('order')) is not int or record.get('order') != scene.get('order')
                or type(scene.get('order')) is not int or scene['order'] != index + 1
                or page.get('page') != index + 1 or page.get('type') != scene.get('type')
                or page.get('title') != scene.get('title')
                or not isinstance(scene.get('content'), dict)
                or page.get('widgetType') and page['widgetType'] != scene['content'].get('widgetType')
                or record.get('contractSha256') != ledger['frozenContract']['sha256']):
            reject('候选页身份、顺序、类型或冻结合同不一致')
        ids.add(scene['id'])
        actions = scene.get('actions')
        if not isinstance(actions, list):
            reject('候选页缺少旁白 action 列表')
        speech = [a for a in actions if isinstance(a, dict) and a.get('type') == 'speech']
        if (not speech or any(not identifier(a.get('id')) or not isinstance(a.get('text'), str)
                              or not a['text'].strip() for a in speech)
                or len({a['id'] for a in speech}) != len(speech)):
            reject('每页必须有完整且编号不重复的老师旁白')
        raw = record.get('canonicalJson')
        try:
            if (not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != record.get('sha256')
                    or scene_canonical(_loads(raw)) != scene_canonical(scene)):
                raise ValueError()
        except (UnicodeError, ValueError, TypeError):
            reject('候选页完整内容与实际课堂不一致；不能只核对页数或标题')


def _questions(classroom, contract, assets):
    locked = contract.get('lockedAssessments')
    if not isinstance(locked, list):
        reject('冻结测评合同缺失')
    expected = {q.get('id'): q for q in locked if isinstance(q, dict)}
    if len(expected) != len(locked):
        reject('冻结题号重复或无效')
    seen = set()
    low_reading = contract['binding']['gradeCode'] in {'primary_1', 'primary_2'}
    for scene in classroom['scenes']:
        if scene['type'] != 'quiz':
            continue
        page = scene['order']
        questions = scene.get('content', {}).get('questions')
        plan = contract['pagePlan'][page - 1]
        if (not isinstance(questions, list) or any(not isinstance(q, dict) for q in questions)
                or [q.get('id') for q in questions] != plan.get('questionIds')):
            reject('随堂测评页与冻结题号绑定不一致')
        speeches = [a.get('text') for a in scene.get('actions', []) if isinstance(a, dict) and a.get('type') == 'speech']
        allowed = [q['question'] for q in questions] + plan.get('narrationGuidance', [])
        # Selected-option feedback is a separate exact speech slot after its
        # stem, not a licence for arbitrary quiz narration or early answers.
        feedback_texts = [f.get('text') for q in questions
                          for f in (q.get('optionFeedback') or {}).values() if isinstance(f, dict)]
        for q in questions:
            for feedback in (q.get('optionFeedback') or {}).values():
                text = feedback.get('text') if isinstance(feedback, dict) else None
                if text not in speeches:
                    continue
                if (not isinstance(text, str) or not text.strip() or text in allowed
                        or feedback_texts.count(text) != 1 or q['question'] not in speeches
                        or speeches.index(text) <= speeches.index(q['question'])):
                    reject('选项反馈旁白必须唯一原文匹配且位于对应题干之后')
                allowed.append(text)
        if any(q.get('analysis') in speeches for q in questions):
            reject('随堂测评不能在作答前朗读答案解析')
        if (len(speeches) != len(set(speeches)) or any(line not in allowed for line in speeches)
                or any(speeches.count(q['question']) != 1 for q in questions)):
            reject('测评旁白与锁定题干或冻结引导不一致')
        for question in questions:
            qid = question.get('id')
            spec = expected.get(qid)
            if not spec or qid in seen or spec.get('page') != page:
                reject('实际测评与冻结题号或页面不一致')
            seen.add(qid)
            choices = spec.get('choices', [])
            answer = question.get('answer')
            if isinstance(answer, list) and len(answer) == 1:
                answer = answer[0]
            if (answer != spec.get('answer') or question.get('hasAnswer') is False
                    or type(question.get('points')) is not int
                    or any(question.get(k) != spec.get(k) for k in ('type', 'points', 'question', 'analysis'))
                    or question.get('options') != [{k: c[k] for k in ('label', 'value')} for c in choices]):
                reject('测评题干、答案、选项值或解析被改动')
            visual = question.get('visual')
            visual_asset = spec.get('visualAsset')
            if visual_asset:
                bound = assets.get(visual_asset)
                if (not bound or not isinstance(visual, dict) or visual.get('kind') != 'image'
                        or visual.get('src') != bound['src']):
                    reject('测评题干情境图与冻结 visualAsset 不一致')
            elif visual is not None and (not isinstance(visual, dict) or visual.get('kind') != 'image'
                    or visual.get('src') not in {asset['src'] for asset in assets.values()}):
                reject('测评题干图片没有绑定原始素材')
            if not low_reading and not any('asset' in choice for choice in choices):
                continue
            visuals = question.get('optionVisuals')
            if not isinstance(visuals, dict) or set(visuals) != {c['value'] for c in choices}:
                reject('测评图片选项未完整绑定冻结素材')
            option_hashes = []
            for choice in choices:
                asset, visual = assets.get(choice.get('asset')), visuals.get(choice['value'])
                if (not asset or not isinstance(visual, dict) or visual.get('kind') != 'image'
                        or visual.get('src') != asset['src']
                        or not isinstance(visual.get('alt'), str) or not visual['alt'].strip()):
                    reject('测评图片选项与冻结 assetKey 不一致')
                option_hashes.append(asset['sha256'])
            if low_reading and len(set(option_hashes)) != len(option_hashes):
                reject('低年级测评图片选项不能使用相同原字节冒充可区分图片')
    if seen != set(expected):
        reject('冻结测评没有被完整采用')



class _ImageMarkup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sources = set()
        self.templates = 0
        self.cue_blocks = []
        self.active_cue = False

    def handle_starttag(self, tag, attrs):
        if tag in ('template', 'noscript'):
            self.templates += 1
        attributes = dict(attrs)
        if not self.templates and tag == 'script' and attributes.get('id') == 'mira-narration-cues':
            if attributes.get('type') != 'application/json' or self.active_cue:
                reject('候选语音 cue 块格式无效')
            self.active_cue = True
            self.cue_blocks.append('')
        if tag != 'img' or self.templates:
            return
        attributes = dict(attrs)
        if not attributes.get('src') or attributes.get('srcset'):
            reject('候选图片不能缺少明确 src 或使用未绑定的 srcset')
        self.sources.add(attributes['src'])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in ('template', 'noscript') and self.templates:
            self.templates -= 1
        if tag == 'script':
            self.active_cue = False

    def handle_data(self, data):
        if self.active_cue:
            self.cue_blocks[-1] += data


def _image_coverage(classroom, contract, assets):
    bound = {asset['src'] for asset in assets.values()}
    low = contract['binding']['gradeCode'] in {'primary_1', 'primary_2'}
    def structured_images(value):
        sources = set()
        if isinstance(value, list):
            for child in value:
                sources |= structured_images(child)
        elif isinstance(value, dict):
            if value.get('type') == 'image' or value.get('kind') == 'image':
                if not isinstance(value.get('src'), str):
                    reject('候选图片没有明确素材地址')
                sources.add(value['src'])
            if value.get('kind') == 'people':
                sources.update(member.get('src') for member in value.get('members', []) if isinstance(member, dict))
            for child in value.values():
                sources |= structured_images(child)
        return sources
    for scene in classroom['scenes']:
        content = scene['content']
        sources = structured_images(content)
        if scene['type'] == 'interactive':
            html = content.get('html')
            if not isinstance(html, str):
                reject('候选互动页缺少内联 HTML')
            parser = _ImageMarkup()
            parser.feed(html)
            if low and not responsive_activity_marker(html):
                reject('低年级互动候选缺少真实 head 响应式标记')
            try:
                cues = interactive_cues(html)
                if low or parser.cue_blocks or cues:
                    if len(parser.cue_blocks) != 1 or not cues:
                        raise ValueError()
                    original_cues = _loads(parser.cue_blocks[0])['cues']
                    if [cue['text'] for cue in original_cues] != [cue['text'] for cue in cues]:
                        raise ValueError()
            except (ValueError, KeyError, TypeError):
                reject('互动候选缺少真实且完整的预录语音 cue 块')
            speech = [a.get('text') for a in scene.get('actions', []) if isinstance(a, dict) and a.get('type') == 'speech']
            texts = [cue['text'] for cue in cues]
            if cues and (len(texts) != len(set(texts)) or len(texts) != len(speech)
                         or any(speech.count(text) != 1 for text in texts)):
                reject('互动 cue 与同页 speech 必须逐句完全一致且一一对应')
            sources |= parser.sources
            sources.update(src for src in re.findall(r'url\(\s*[\"\']?([^\"\'()\s]+)', html) if not src.startswith('#'))
            if low and not parser.sources:
                reject('低年级互动页缺少真实图片元素，不能用素材清单代替')
        sources |= set(IMAGE_REFERENCE.findall(canonical(content)))
        if sources - bound or low and not sources:
            reject('课堂图片未完整绑定原生候选台账')


def validate_authoring_candidate(classroom, classroom_directory, authoring, manifest, node, *,
                                 output_root=DEFAULT_AUTHORING_ROOT, runtime_origin=None):
    """Return a verified summary for v3; None means a genuine legacy path."""
    directory = Path(classroom_directory).resolve()
    stage_id = classroom.get('id')
    if not identifier(stage_id):
        reject('候选课堂编号无效')
    path = _safe_child(directory, directory / stage_id / CANDIDATE_FILE)
    session_id = authoring.get('sessionId') if isinstance(authoring, dict) else None
    found = _find_job(output_root, manifest['editionId'], manifest['revisionId'], node, session_id, stage_id,
                      path.exists() or path.is_symlink())
    if found is None:
        return None
    job, frozen, state = found
    if (authoring.get('stageId') != stage_id or classroom.get('stage', {}).get('id') != stage_id
            or runtime_origin is not None and frozen.get('origin') != runtime_origin
            or stage_id not in _saved_stages(state)):
        reject('原生课堂、作者会话和真实保存记录不一致')
    ledger = _read_json(path)
    if (set(ledger) != {'schemaVersion', 'sessionId', 'stageId', 'frozenContract', 'status', 'verification',
                         'assetBindings', 'bindingHistory', 'scenes', 'sha256'}
            or ledger.get('schemaVersion') != CANDIDATE_SCHEMA or ledger.get('status') != 'author_candidate'
            or ledger.get('verification') != 'static_contract_only_not_play_or_semantic_review'
            or ledger.get('sessionId') != session_id
            or ledger.get('stageId') != stage_id or ledger.get('frozenContract') != frozen.get('sceneContract')):
        reject('原生候选台账与真实冻结会话不一致')
    # Native uses Unicode-codepoint key order; the envelope contains only safe
    # integers and full scenes are serialized strings, so Python bytes match.
    if digest({k: v for k, v in ledger.items() if k != 'sha256'}) != ledger.get('sha256'):
        reject('原生候选台账摘要不一致')
    contract = _contract(job, frozen, manifest, node)
    assets = _assets(ledger, directory, stage_id)
    _scenes(ledger, classroom, contract)
    _image_coverage(classroom, contract, assets)
    _questions(classroom, contract, assets)
    interaction_policy = contract['interactionPolicy']
    policy = interaction_policy['policy']
    summary = {'schemaVersion': CANDIDATE_SCHEMA, 'sha256': ledger['sha256'],
            'contractSha256': ledger['frozenContract']['sha256'], 'sceneCount': len(ledger['scenes']),
            'assetCount': len(assets), 'verification': 'frozen_identity_and_artifact_integrity_only',
            'interactionPolicyVersion': policy['version'],
            'interactionPolicySha256': interaction_policy['sha256']}
    if isinstance(policy.get('wholeCourseQualityContract'), dict):
        summary['wholeCourseQualityContractSha256'] = digest(policy['wholeCourseQualityContract'])
    try:
        followup = discover_complete_scene_review_followup(
            classroom, directory, session_id=session_id, stage_id=stage_id,
            base_policy_version=policy['version'],
            base_policy_sha256=interaction_policy['sha256'])
    except ValueError:
        reject('完整场景修订追踪缺失、已改变，或与当前候选不一致')
    if followup is not None:
        summary['completeSceneReviewFollowup'] = followup
    return summary
