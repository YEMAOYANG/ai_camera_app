"""Revise an unpublished preview's visuals without changing its paid audio identity.

The narration plan and receipts remain immutable. ASR still uses that original
plan identity; its aggregate audit and the publication review cover the current
classroom hash. A durable amendment records the relationship between the two.
"""
from copy import deepcopy
import base64
import binascii
import fcntl
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse
from xml.etree import ElementTree

from content.textbook_catalog import canonical, digest
from content.textbook_preview_audio_contract import check_receipt_language_policy, resolve_audio_contract, valid_tts_request_id
from content.textbook_interactive_narration import AUDIO_BLOCK, interactive_cues, without_audio_helper
from content.textbook_preview import THREE_MODULE_PATH, cue_speech, preview_checks, self_contained_classroom
from content.textbook_release import MEDIA
from core.errors import ApiError
from services.textbook_preview_revision_transaction import PreviewRevisionTransaction
from core.security import now_ms
from services.textbook_preview_audio import verify_segment_receipt
from services.course_file_store import course_bytes, course_exists, course_text

SCHEMA = 'mira.textbook.preview-visual-patch.v1'
CANVAS_SCHEMA = 'mira.textbook.preview-visual-patch.v2'
QUIZ_VISUAL_SCHEMA = 'mira.textbook.preview-visual-patch.v3'
QUANTITY_VISUAL_SCHEMA = 'mira.textbook.preview-visual-patch.v4'
IMAGE_ALT_SCHEMA = 'mira.textbook.preview-visual-patch.v5'
QUESTION_BINDING_SCHEMA = 'mira.textbook.preview-question-binding-patch.v1'
SHA = re.compile(r'[a-f0-9]{64}\Z')
SVG_DATA = 'data:image/svg+xml;base64,'
SVG_TAGS = {'svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'title', 'desc'}
SVG_ATTRIBUTES = {'viewBox', 'width', 'height', 'x', 'y', 'x1', 'y1', 'x2', 'y2', 'cx', 'cy', 'r', 'rx', 'ry',
                  'd', 'points', 'fill', 'fill-rule', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-opacity',
                  'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit', 'stroke-dasharray', 'stroke-dashoffset',
                  'opacity', 'transform', 'preserveAspectRatio', 'id', 'class', 'role', 'aria-label', 'aria-hidden', 'focusable'}


def fail(message):
    raise ApiError('textbook_preview_visual_revision_conflict', message, 409)


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def persisted(value):
    """The save API supplies a new createdAt, but must preserve every other field."""
    return {k: v for k, v in value.items() if k != 'createdAt'}


def immutable(path, raw):
    if course_exists(path):
        if course_bytes(path) != raw:
            fail('修订归档已存在不同内容，不能覆盖')
        return
    # The shared operator lock serializes writers; publish complete files only.
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('wb') as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def json_bytes(value):
    return canonical(value).encode('utf-8')


def validate_patch(patch):
    if isinstance(patch, dict) and patch.get('schemaVersion') == QUESTION_BINDING_SCHEMA:
        if (set(patch) != {'schemaVersion', 'expectedSourceSha256', 'reviewer', 'basis', 'changes'}
                or not SHA.fullmatch(str(patch['expectedSourceSha256']))
                or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis'))
                or not isinstance(patch['changes'], list) or not 1 <= len(patch['changes']) <= 60):
            fail('听题绑定修订需要当前课件摘要和依据')
        seen = set()
        for change in patch['changes']:
            if (not isinstance(change, dict) or set(change) != {'sceneId', 'questionId', 'actionId', 'beforeQuestionSha256'}
                    or any(not isinstance(change[k], str) or not change[k].strip() for k in ('sceneId', 'questionId', 'actionId'))
                    or not SHA.fullmatch(str(change['beforeQuestionSha256']))
                    or (change['sceneId'], change['questionId']) in seen):
                fail('听题绑定只能明确引用已有题目及逐字旁白')
            seen.add((change['sceneId'], change['questionId']))
        return
    if isinstance(patch, dict) and patch.get('schemaVersion') == IMAGE_ALT_SCHEMA:
        if (set(patch) != {'schemaVersion', 'expectedSourceSha256', 'reviewer', 'basis', 'changes'}
                or not SHA.fullmatch(str(patch['expectedSourceSha256']))
                or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis'))
                or not isinstance(patch['changes'], list) or not 1 <= len(patch['changes']) <= 60):
            fail('图片替代说明修订需要准确的原课件摘要和审查依据')
        seen = set()
        for change in patch['changes']:
            if (not isinstance(change, dict) or set(change) != {'sceneId', 'questionId', 'optionValue',
                    'beforeQuestionSha256', 'beforeVisualSha256', 'beforeAlt', 'src', 'imageSha256', 'alt'}
                    or any(not isinstance(change[k], str) or not change[k].strip()
                           for k in ('sceneId', 'questionId', 'optionValue', 'src'))
                    or any(not SHA.fullmatch(str(change[k]))
                           for k in ('beforeQuestionSha256', 'beforeVisualSha256', 'imageSha256'))
                    or not isinstance(change['beforeAlt'], str)
                    or not isinstance(change['alt'], str) or not 1 <= len(change['alt']) <= 500
                    or change['alt'] != change['alt'].strip()
                    or re.search(r'[<>\x00-\x1f\x7f]', change['alt'])
                    or change['alt'] == change['beforeAlt']
                    or (change['sceneId'], change['questionId'], change['optionValue']) in seen):
                fail('图片替代说明只能修改已有选项的纯文本 alt，必须绑定原题、原图和原说明')
            seen.add((change['sceneId'], change['questionId'], change['optionValue']))
        return
    if isinstance(patch, dict) and patch.get('schemaVersion') == QUANTITY_VISUAL_SCHEMA:
        if (set(patch) != {'schemaVersion', 'expectedSourceSha256', 'reviewer', 'basis', 'changes', 'derivedImages'}
                or not SHA.fullmatch(str(patch['expectedSourceSha256']))
                or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis'))
                or not isinstance(patch['changes'], list) or not 1 <= len(patch['changes']) <= 30
                or not isinstance(patch['derivedImages'], list) or not 1 <= len(patch['derivedImages']) <= 30):
            fail('数量图修订需要准确的原课件、派生定义和逐题绑定')
        seen = set()
        for change in patch['changes']:
            if (not isinstance(change, dict) or set(change) != {'sceneId', 'questionId', 'beforeQuestionSha256',
                    'visualImageId', 'optionImageIds'}
                    or any(not isinstance(change[k], str) or not change[k].strip() for k in
                           ('sceneId', 'questionId', 'visualImageId'))
                    or not SHA.fullmatch(str(change['beforeQuestionSha256']))
                    or not isinstance(change['optionImageIds'], dict) or not change['optionImageIds']
                    or any(not isinstance(k, str) or not isinstance(v, str) or not k or not v
                           for k, v in change['optionImageIds'].items())
                    or (change['sceneId'], change['questionId']) in seen):
                fail('数量图修订只能绑定已有题目及选项图片，不能修改题目字段')
            seen.add((change['sceneId'], change['questionId']))
        return
    if (not isinstance(patch, dict) or set(patch) != {
            'schemaVersion', 'expectedSourceSha256', 'reviewer', 'basis', 'changes'}
            or patch['schemaVersion'] not in (SCHEMA, CANVAS_SCHEMA, QUIZ_VISUAL_SCHEMA)
            or not SHA.fullmatch(str(patch['expectedSourceSha256']))
            or any(not isinstance(patch[k], str) or not patch[k].strip() for k in ('reviewer', 'basis'))
            or not isinstance(patch['changes'], list) or not 1 <= len(patch['changes']) <= 60):
        fail('需要准确的原课件摘要、修订说明和逐页视觉补丁')
    seen = set()
    for change in patch['changes']:
        html_change = isinstance(change, dict) and set(change) == {'sceneId', 'beforeHtmlSha256', 'html'}
        canvas_change = (patch['schemaVersion'] in (CANVAS_SCHEMA, QUIZ_VISUAL_SCHEMA) and isinstance(change, dict)
                         and set(change) == {'sceneId', 'beforeCanvasSha256', 'canvas'})
        quiz_change = (patch['schemaVersion'] == QUIZ_VISUAL_SCHEMA and isinstance(change, dict)
                       and set(change) == {'sceneId', 'questionId', 'beforeQuestionSha256', 'visual'})
        if (not (html_change or canvas_change or quiz_change)
                or not isinstance(change['sceneId'], str) or change['sceneId'] in seen
                or not SHA.fullmatch(str(change['beforeHtmlSha256' if html_change else
                                              'beforeCanvasSha256' if canvas_change else 'beforeQuestionSha256']))
                or (html_change and (not isinstance(change['html'], str) or not change['html'].strip()))
                or (canvas_change and not isinstance(change['canvas'], dict))
                or (quiz_change and (not isinstance(change['questionId'], str) or not change['questionId'].strip()
                                     or not isinstance(change['visual'], dict)))):
            fail('视觉补丁重复、包含非视觉字段或缺少原页面摘要')
        seen.add(change['sceneId'])


class _InlineSvg(HTMLParser):
    """Collect original inline SVG slices without normalizing their bytes."""
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source, self.depth, self.start, self.values = source, 0, 0, set()
        self.offsets = [0]
        for line in source.splitlines(keepends=True):
            self.offsets.append(self.offsets[-1] + len(line))

    def source_offset(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag == 'svg':
            if not self.depth:
                self.start = self.source_offset()
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        if tag == 'svg' and not self.depth:
            self.values.add(self.get_starttag_text().encode('utf-8'))

    def handle_endtag(self, tag):
        if tag == 'svg' and self.depth:
            self.depth -= 1
            if not self.depth:
                end = self.source.find('>', self.source_offset())
                if end >= 0:
                    self.values.add(self.source[self.start:end + 1].encode('utf-8'))


def original_inline_svgs(source):
    values = set()
    for scene in source['scenes']:
        content = scene.get('content', {})
        html = content.get('html')
        if isinstance(html, str):
            parser = _InlineSvg(html)
            parser.feed(html)
            values.update(parser.values)
        # Adopted slides can already contain exact SVG data images. Collect
        # only canonical bytes from actual image elements, not arbitrary text
        # or metadata. Every candidate use still passes validate_svg_image.
        canvas = content.get('canvas')
        if isinstance(canvas, dict):
            for element in canvas.get('elements', []):
                if not isinstance(element, dict) or element.get('type') != 'image':
                    continue
                value = element.get('src')
                if not isinstance(value, str) or not value.startswith(SVG_DATA):
                    continue
                encoded = value[len(SVG_DATA):]
                if len(encoded) > 350_000:
                    continue
                try:
                    raw = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error):
                    continue
                if base64.b64encode(raw).decode('ascii') == encoded:
                    values.add(raw)
    return values


def validate_svg_image(value, originals):
    """Only an exact, inert geometric SVG from the source HTML or canvas."""
    try:
        encoded = value[len(SVG_DATA):]
        if len(encoded) > 350_000:
            raise ValueError()
        raw = base64.b64decode(encoded, validate=True)
        if base64.b64encode(raw).decode('ascii') != encoded or raw not in originals:
            raise ValueError()
        text = raw.decode('utf-8')
        if '<!' in text or '<?' in text:
            raise ValueError()
        svg = ElementTree.fromstring(text)
        if svg.tag not in ('svg', '{http://www.w3.org/2000/svg}svg'):
            raise ValueError()
        for element in svg.iter():
            name = element.tag.removeprefix('{http://www.w3.org/2000/svg}')
            if name not in SVG_TAGS:
                raise ValueError()
            for key, item in element.attrib.items():
                if key not in SVG_ATTRIBUTES or re.search(r'url\s*\(|:|//', item, re.I):
                    raise ValueError()
    except (ValueError, UnicodeError, binascii.Error, ElementTree.ParseError):
        fail('SVG 图片必须逐字节复用原课件 HTML 或画布的安全静态 SVG，不能新增、改写或引用外部资源')


def frozen_image(owner, name, root, original_references, original_images):
    reference = f'/api/classroom-media/{owner}/{name}'
    asset = original_images.get(reference, {})
    path = (root / owner / name).resolve()
    if ((owner, name) not in original_references or not name.startswith('media/')
            or path.suffix.lower() not in {'.png', '.webp', '.jpg', '.jpeg'}
            or not SHA.fullmatch(str(asset.get('sha256', '')))
            or root not in path.parents or not course_exists(path)
            or sha_bytes(course_bytes(path)) != asset['sha256']):
        fail('图片必须是本课已使用、已冻结且文件摘要一致的原图')


def quantity_assets(source, patch, root, frozen):
    """Validate/reproduce immutable old and new diagrams without writing files."""
    if patch.get('schemaVersion') != QUANTITY_VISUAL_SCHEMA:
        return [], {}
    from content.textbook_preview_quantity_images import TRANSFORM, quantity_png, rgb_pixels
    references = set(MEDIA.findall(canonical(source)))
    originals = {a['mediaPath']: a for a in frozen.get('originalMedia', {}).get('assets', [])}
    assets, files, seen, replaced = [], {}, set(), set()
    for definition in patch['derivedImages']:
        if (not isinstance(definition, dict) or set(definition) != {'id', 'transform', 'sourcePath', 'sourceSha256',
                'sourceSize', 'count', 'replacesPath', 'replacesSha256', 'originalLayout', 'layout', 'sha256'}
                or not isinstance(definition.get('id'), str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', definition['id']) or definition['id'] in seen
                or definition['transform'] != TRANSFORM
                or any(not isinstance(definition[k], str) for k in ('sourcePath', 'replacesPath'))
                or definition['replacesPath'] in replaced
                or any(not SHA.fullmatch(str(definition[k])) for k in ('sourceSha256', 'replacesSha256', 'sha256'))):
            fail('派生图需要唯一编号、原图和被替换图的准确摘要及固定算法')
        for path_key, hash_key in (('sourcePath', 'sourceSha256'), ('replacesPath', 'replacesSha256')):
            path = definition[path_key]
            match = MEDIA.fullmatch(path) if isinstance(path, str) else None
            if not match or not path.startswith('/api/classroom-media/') or originals.get(path, {}).get('sha256') != definition[hash_key]:
                fail('派生来源和原数量图必须同时属于冻结的本课图片')
            frozen_image(*match.groups(), root, references, originals)
        owner, name = MEDIA.fullmatch(definition['sourcePath']).groups()
        raw = course_bytes(root / owner / name)
        old_owner, old_name = MEDIA.fullmatch(definition['replacesPath']).groups()
        original_png = course_bytes(root / old_owner / old_name)
        try:
            old = quantity_png(raw, source_size=definition['sourceSize'], count=definition['count'], layout=definition['originalLayout'])
            new = quantity_png(raw, source_size=definition['sourceSize'], count=definition['count'], layout=definition['layout'])
            old_pixels, new_pixels = rgb_pixels(old), rgb_pixels(new)
            if old_pixels != rgb_pixels(original_png):
                fail('旧数量图无法按同源同数量逐像素重建，不能证明数量保留')
        except (ValueError, OSError) as exc:
            fail('数量图派生定义无效：' + str(exc))
        if sha_bytes(new) != definition['sha256'] or old_pixels == new_pixels:
            fail('新数量图必须与确定性派生摘要一致且有实际变化')
        path = f"/api/classroom-media/{source['id']}/media/{definition['sha256']}.png"
        file = root / source['id'] / 'media' / (definition['sha256'] + '.png')
        if course_exists(file) and course_bytes(file) != new:
            fail('派生资源的内容地址已存在不同字节，不能覆盖')
        assets.append({'definition': deepcopy(definition), 'sha256': definition['sha256'], 'mediaPath': path, 'byteSize': len(new),
                       'originalRgbSha256': sha_bytes(old_pixels[1]), 'derivedRgbSha256': sha_bytes(new_pixels[1])})
        files[definition['sha256'] + '.png'] = new
        seen.add(definition['id'])
        replaced.add(definition['replacesPath'])
    return assets, files


def quantity_candidate(source, patch, assets):
    target = deepcopy(source)
    images = {a['definition']['id']: a for a in assets}
    used = set()
    scenes = {s['id']: s for s in target['scenes']}
    if len(scenes) != len(target['scenes']):
        fail('页面编号重复')

    def replace(old, image_id):
        asset = images.get(image_id)
        if (not asset or not isinstance(old, dict) or old.get('kind') != 'image'
                or old.get('src') != asset['definition']['replacesPath']):
            fail('派生图只能替换明确绑定的原数量图片')
        used.add(image_id)
        return {**deepcopy(old), 'src': asset['mediaPath']}

    for change in patch['changes']:
        scene = scenes.get(change['sceneId'])
        if not scene or scene.get('type') != 'quiz':
            fail('数量图修订只允许已有测验题')
        matches = [q for q in scene.get('content', {}).get('questions', []) if q.get('id') == change['questionId']]
        if len(matches) != 1 or digest(matches[0]) != change['beforeQuestionSha256']:
            fail('原题目身份或摘要已变化')
        q = matches[0]
        values = [o.get('value') for o in q.get('options', [])]
        if (len(values) != len(set(values)) or set(change['optionImageIds']) != set(values)
                or not isinstance(q.get('optionVisuals'), dict) or set(q['optionVisuals']) != set(values)):
            fail('数量图必须准确保留全部原选项对应关系')
        q['visual'] = replace(q.get('visual'), change['visualImageId'])
        q['optionVisuals'] = {value: replace(q['optionVisuals'][value], change['optionImageIds'][value]) for value in values}
    if used != set(images):
        fail('派生定义必须全部用于明确的题图，不能夹带无关资源')
    return target


class _CanvasText(HTMLParser):
    """Canvas rich text can format words, not add another media/script channel."""
    def handle_starttag(self, tag, attrs):
        if tag not in {'p', 'div', 'span', 'br', 'b', 'strong', 'i', 'em', 'u', 's', 'sub', 'sup', 'ul', 'ol', 'li'}:
            fail('画布文本只能包含静态文字格式，不能嵌入脚本或媒体')
        for key, value in attrs:
            if key not in {'style', 'class', 'dir', 'lang'} or re.search(
                    r'url\s*\(|expression\s*\(|@import|javascript:', value or '', re.I):
                fail('画布文本不能包含事件、链接或外部资源')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def validate_canvas(old, new, scene, source, root, original_references, original_images):
    if (set(new) != set(old) or new.get('id') != old.get('id')
            or not isinstance(new.get('elements'), list) or not 1 <= len(new['elements']) <= 2000
            or any(not isinstance(e, dict) or e.get('type') not in {'text', 'image', 'shape', 'line', 'table', 'chart', 'latex'}
                   for e in new['elements'])):
        fail('画布必须保持原结构和身份，只能包含静态视觉元素')
    ids = [e.get('id') for e in new['elements']]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
        fail('画布元素编号无效或重复')
    for action in scene.get('actions', []):
        if action.get('elementId') and action['elementId'] not in ids:
            fail('画布不能删除原讲解动作指向的元素')
    originals = original_inline_svgs(source)

    def inspect(value, key=None):
        if isinstance(value, dict):
            for field, item in value.items():
                if field.lower().startswith('on') or field in {'actions', 'questions', 'speech', 'scenes', 'stage',
                        'audioId', 'audioUrl', 'audioMetadata', 'questionAudioUrl', 'href', 'hyperlink'}:
                    fail('画布补丁不能带入音频、场景、题目、事件或链接')
                inspect(item, field)
        elif isinstance(value, list):
            for item in value:
                inspect(item, key)
        elif isinstance(value, str):
            if key == 'src':
                if value.startswith(SVG_DATA):
                    validate_svg_image(value, originals)
                else:
                    match = MEDIA.fullmatch(value)
                    if not match or not value.startswith('/api/classroom-media/'):
                        fail('画布图片只能引用本课冻结图片或原字节 SVG')
                    frozen_image(*match.groups(), root, original_references, original_images)
            else:
                if re.search(r'url\s*\(|expression\s*\(|@import|javascript:|data:', value, re.I) or MEDIA.search(value):
                    fail('素材只能通过受校验的图片 src 引用')
                if '<' in value:
                    _CanvasText().feed(value)

    for element in new['elements']:
        if element['type'] == 'image' and (not isinstance(element.get('src'), str) or not element['src']):
            fail('画布图片缺少有效来源')
    inspect(new)


def candidate(source, patch, root, frozen):
    if patch.get('schemaVersion') == QUANTITY_VISUAL_SCHEMA:
        assets, _ = quantity_assets(source, patch, root, frozen)
        return quantity_candidate(source, patch, assets)
    target = deepcopy(source)
    scenes = {s['id']: s for s in target['scenes']}
    source_scenes = {s['id']: s for s in source['scenes']}
    original_references = set(MEDIA.findall(canonical(source)))
    original_images = {asset['mediaPath']: asset for asset in frozen.get('originalMedia', {}).get('assets', [])}
    if len(scenes) != len(target['scenes']):
        fail('页面编号重复')
    for change in patch['changes']:
        scene = scenes.get(change['sceneId'])
        if patch['schemaVersion'] == QUESTION_BINDING_SCHEMA:
            if not scene or scene.get('type') != 'quiz':
                fail('听题绑定只能修订已有测验题的元数据')
            questions = scene.get('content', {}).get('questions', [])
            matches = [q for q in questions if q.get('id') == change['questionId']]
            if len(matches) != 1 or digest(matches[0]) != change['beforeQuestionSha256']:
                fail('听题绑定的原题身份或摘要已变化')
            question = matches[0]
            actions = [a for a in scene.get('actions', [])
                       if a.get('type') == 'speech' and a.get('text') == question.get('question')]
            if (len(actions) != 1 or actions[0].get('id') != change['actionId']
                    or sum(q.get('question') == question.get('question') for q in questions) != 1):
                fail('听题绑定必须有唯一对应的完整逐字旁白')
            action = actions[0]
            if (not action.get('audioId') or not action.get('audioUrl')
                    or urlparse(question.get('questionAudioUrl', '')).path != urlparse(action['audioUrl']).path):
                fail('听题绑定只能修复已指向正确正式录音的元数据')
            binding = {'schemaVersion': 'mira.learning.question-narration-binding.v1',
                       'sceneId': scene['id'], 'actionId': action['id'], 'ttsRequestId': action['audioId'],
                       'sourceTextSha256': sha_bytes(action['text'].strip().encode('utf-8'))}
            if question.get('questionAudioBinding') == binding:
                fail('听题绑定已正确，不能创建空修订')
            question['questionAudioBinding'] = binding
            continue
        if patch['schemaVersion'] == IMAGE_ALT_SCHEMA:
            if scene is None or scene.get('type') != 'quiz':
                fail('图片替代说明补丁只允许修改已有测验选项')
            original_questions = source_scenes[change['sceneId']].get('content', {}).get('questions')
            matches = [q for q in original_questions if isinstance(q, dict) and q.get('id') == change['questionId']] \
                if isinstance(original_questions, list) else []
            if len(matches) != 1 or digest(matches[0]) != change['beforeQuestionSha256']:
                fail('图片替代说明的原题编号或摘要已变化')
            question = matches[0]
            options = question.get('options')
            if (not isinstance(options, list)
                    or sum(isinstance(o, dict) and o.get('value') == change['optionValue'] for o in options) != 1):
                fail('图片替代说明必须对应唯一的已有选项')
            visuals = question.get('optionVisuals')
            old = visuals.get(change['optionValue']) if isinstance(visuals, dict) else None
            if (not isinstance(old, dict) or set(old) != {'kind', 'src', 'alt'} or old.get('kind') != 'image'
                    or digest(old) != change['beforeVisualSha256'] or old['alt'] != change['beforeAlt']
                    or old['src'] != change['src']):
                fail('原选项图片身份或替代说明已变化，不能覆盖')
            match = MEDIA.fullmatch(change['src'])
            if not match or original_images.get(change['src'], {}).get('sha256') != change['imageSha256']:
                fail('图片替代说明必须绑定本课已冻结的相同图片字节')
            frozen_image(*match.groups(), root, original_references, original_images)
            target_question = next(q for q in scene['content']['questions'] if q['id'] == change['questionId'])
            target_question['optionVisuals'][change['optionValue']]['alt'] = change['alt']
            continue
        if 'visual' in change:
            if scene is None or scene.get('type') != 'quiz':
                fail('题目图片补丁只允许修改已有测验题的 visual')
            questions = scene.get('content', {}).get('questions')
            matches = [q for q in questions if isinstance(q, dict) and q.get('id') == change['questionId']] \
                if isinstance(questions, list) else []
            if len(matches) != 1 or digest(matches[0]) != change['beforeQuestionSha256']:
                fail('题目编号或原题目摘要不符，不能修改图片')
            old, visual = matches[0], change['visual']
            if (set(visual) != {'kind', 'src', 'alt'} or visual.get('kind') != 'image'
                    or not isinstance(visual.get('src'), str) or not visual['src'].startswith('/api/classroom-media/')
                    or not isinstance(visual.get('alt'), str) or not visual['alt'].strip()
                    or old.get('visual') == visual):
                fail('题目图片只能包含已有图片地址及替代说明，且必须有实际修订')
            match = MEDIA.fullmatch(visual['src'])
            if not match:
                fail('题目图片必须引用本课已冻结的原图')
            frozen_image(*match.groups(), root, original_references, original_images)
            old['visual'] = deepcopy(visual)
            continue
        if 'canvas' in change:
            if scene is None or scene.get('type') != 'slide':
                fail('canvas 补丁只允许修改已有幻灯页的 content.canvas')
            old, new = scene.get('content', {}).get('canvas'), change['canvas']
            if not isinstance(old, dict) or digest(old) != change['beforeCanvasSha256'] or old == new:
                fail('画布摘要不符或没有实际修订')
            validate_canvas(old, new, scene, source, root, original_references, original_images)
            scene['content']['canvas'] = deepcopy(new)
            continue
        if scene is None or scene.get('type') != 'interactive':
            fail('只允许修改已有互动页的 HTML')
        old, new = scene['content'].get('html'), change['html']
        if not isinstance(old, str) or sha_bytes(old.encode()) != change['beforeHtmlSha256'] or old == new:
            fail('页面摘要不符或没有实际修订')
        try:
            without_audio_helper(old)
            without_audio_helper(new)
            if interactive_cues(old) != interactive_cues(new) or AUDIO_BLOCK.findall(old) != AUDIO_BLOCK.findall(new):
                fail('修订不能改变语音提示或音频播放器')
            old_media, new_media = set(MEDIA.findall(old)), set(MEDIA.findall(new))
            if not old_media <= new_media:
                fail('修订不能移除或替换已有素材引用')
            for owner, name in new_media - old_media:
                frozen_image(owner, name, root, original_references, original_images)
            scene['content']['html'] = new
            cue_speech(scene)
        except ValueError as exc:
            fail('互动页语音或 HTML 无效：' + str(exc))
    # This is a pure validation: do not silently transform another part of the lesson.
    contained = self_contained_classroom(target, lambda: (root.parents[1] / THREE_MODULE_PATH).read_bytes())
    if contained != target:
        fail('修订必须已自包含，不能顺带转换其他内容')
    return target


def verify_audio(source, result, root, classroom_id):
    plan = json.loads(course_text(root / classroom_id / 'textbook-preview-audio/plan.json'))
    resolve_audio_contract(plan)
    receipts = result.get('audioReceipts', [])
    by_id = {r['requestId']: r for r in receipts}
    speech = [a for s in source['scenes'] for a in s.get('actions', []) if a.get('type') == 'speech']
    if (result.get('audioStopCode') or not speech or len(by_id) != len(receipts)
            or len({a['id'] for a in speech}) != len(speech)):
        fail('请先完成全课配音并核对段落编号')
    for action in speech:
        request = action.get('audioId', '')
        receipt = by_id.get(request, {})
        if (not valid_tts_request_id(plan, request)
                or receipt.get('status') != 'succeeded'
                or not SHA.fullmatch(str(receipt.get('audioSha256', '')))):
            fail('每段讲解都必须有成功的原始配音收据')
        path = root / classroom_id / 'audio' / (request + '.wav')
        if (urlparse(action.get('audioUrl', '')).path != f'/api/classroom-media/{classroom_id}/audio/{request}.wav'
                or not course_exists(path) or sha_bytes(course_bytes(path)) != receipt['audioSha256']):
            fail('已完成配音文件缺失、变化或绑定不一致')
    for scene in source['scenes']:
        for action in scene.get('actions', []):
            if action.get('type') == 'speech':
                verify_segment_receipt(plan, by_id[action['audioId']], scene, action,
                                       root / classroom_id / 'textbook-preview-audio')


def revise_preview_visuals(service, key, classroom_directory, patch):
    """Apply/reconcile one exact patch. No generation, TTS, ASR or publication."""
    validate_patch(patch)
    row = service.get(key)
    classroom_id = row['classroom_id']
    if (urlparse(service.runtime.base_url).hostname not in {'localhost', '127.0.0.1', '::1'}
            or not re.fullmatch(r'[A-Za-z0-9_-]+', classroom_id or '')):
        fail('只能修订本机已保存的课件')
    root = Path(classroom_directory).resolve()
    audio_folder = root / classroom_id / 'textbook-preview-audio'
    if not course_exists(audio_folder / 'plan.json'):
        fail('原始配音计划不存在')
    audio_folder.mkdir(parents=True, exist_ok=True)
    with (audio_folder / 'operator.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail('课件正在配音或修订，请等待已有任务结束')
        with PreviewRevisionTransaction(service.repository, key, fail, root / (classroom_id + '.json')) as conn:
            row = conn.execute('SELECT * FROM learning_textbook_course_previews WHERE preview_key=? FOR UPDATE', (key,)).fetchone()
            if row['status'] != 'preview_ready' or row['runtime_origin'] != service.runtime.base_url:
                fail('请先完成全课配音和结构检查')
            published = conn.execute("SELECT input_json FROM learning_textbook_course_builds WHERE edition_id=? AND node_id=? AND status='published'",
                                     (row['edition_id'], row['node_id'])).fetchall()
            if any(service.repository.parse(b['input_json']).get('previewKey') == key for b in published):
                fail('已发布的课件不能原地修改')
            conn.release(row)
            revision_id = digest({'previewKey': key, 'patch': patch})
            archive = audio_folder / 'visual-revisions' / revision_id
            intent_path = archive / 'intent.json'
            if not course_exists(intent_path):
                source = service.repository.parse(row['classroom_json'])
                result = service.repository.parse(row['result_json'])
                if digest(source) != row['classroom_sha256'] or row['classroom_sha256'] != patch['expectedSourceSha256']:
                    fail('课件摘要已变化，必须针对当前版本重新准备补丁')
                current = service.runtime.get_classroom(classroom_id)
                local = json.loads(course_text(root / (classroom_id + '.json')))
                if digest(current) != digest(source) or digest(local) != digest(source):
                    fail('数据库、本机文件和运行课件快照不一致')
                verify_audio(source, result, root, classroom_id)
                plan_bytes = course_bytes(audio_folder / 'plan.json')
                plan = json.loads(plan_bytes)
                if plan.get('previewKey') != key or not SHA.fullmatch(str(plan.get('classroomSha256'))):
                    fail('原配音计划身份不一致')
                receipt_bytes = course_bytes(audio_folder / 'receipts.json')
                if json.loads(receipt_bytes) != result['audioReceipts']:
                    fail('原配音收据与数据库不一致')
                frozen = service.repository.parse(row['input_json'])
                resolve_audio_contract(plan, frozen)
                target = candidate(source, patch, root, frozen)
                derived, derivative_files = quantity_assets(source, patch, root, frozen)
                prompt = frozen['previewPrompt']
                original_html = {s['id']: s.get('content', {}).get('html') for s in source['scenes']}
                responsive_ids = {s['id'] for s in target['scenes'] if s.get('type') == 'interactive'
                                  and s.get('content', {}).get('html') != original_html.get(s['id'])}
                checks = preview_checks(target, prompt['expectedSceneCount'], frozen.get('originalMedia'), prompt.get('expectedQuestionCount', 6),
                                        grade_code=frozen.get('gradeCode'), responsive_scene_ids=responsive_ids)
                if checks['issues']:
                    fail('修订后课件结构或插画检查未通过：' + '、'.join(checks['issues']))
                archive.mkdir(parents=True, exist_ok=True)
                files = {'source.json': json_bytes(source), 'source-row.json': json_bytes(row),
                         'target.json': json_bytes(target), 'plan.json': plan_bytes, 'receipts.json': receipt_bytes}
                if derived:
                    files['derived-images.json'] = json_bytes(derived)
                    files.update({'derived-' + name: raw for name, raw in derivative_files.items()})
                for name, raw in files.items():
                    immutable(archive / name, raw)
                intent = {'schemaVersion': 'mira.textbook.preview-visual-intent.v1', 'revisionId': revision_id,
                          'previewKey': key, 'classroomId': classroom_id, 'patch': patch, 'checks': checks,
                          'audioIdentityClassroomSha256': plan['classroomSha256'],
                          'files': {name: sha_bytes(raw) for name, raw in files.items()}}
                intent['sha256'] = digest(intent)
                immutable(intent_path, json_bytes(intent))
            intent = json.loads(course_text(intent_path))
            expected_files = {'source.json', 'source-row.json', 'target.json', 'plan.json', 'receipts.json'}
            if patch['schemaVersion'] == QUANTITY_VISUAL_SCHEMA:
                expected_files.add('derived-images.json')
                expected_files.update('derived-' + a['sha256'] + '.png' for a in patch['derivedImages'])
            if (intent.get('sha256') != digest({k: v for k, v in intent.items() if k != 'sha256'})
                    or intent.get('revisionId') != revision_id or intent.get('patch') != patch
                    or intent.get('previewKey') != key or intent.get('classroomId') != classroom_id
                    or set(intent.get('files', {})) != expected_files):
                fail('修订意图记录被改变')
            for name, sha in intent['files'].items():
                if sha_bytes(course_bytes(archive / name)) != sha:
                    fail('原始快照或修订目标被改变')
            for name in ('plan.json', 'receipts.json'):
                if course_bytes(audio_folder / name) != course_bytes(archive / name):
                    fail('修订期间原配音计划或收据已改变')
            source = json.loads(course_text(archive / 'source.json'))
            source_row = json.loads(course_text(archive / 'source-row.json'))
            target = json.loads(course_text(archive / 'target.json'))
            if row['input_json'] != source_row['input_json']:
                fail('视觉修订不能改变原始冻结输入')
            if candidate(source, patch, root, service.repository.parse(source_row['input_json'])) != target:
                fail('修订目标与原始补丁不一致')
            derived, derivative_files = quantity_assets(source, patch, root, service.repository.parse(source_row['input_json']))
            if derived and json.loads(course_text(archive / 'derived-images.json')) != derived:
                fail('派生图归档与确定性定义不一致')
            result = service.repository.parse(source_row['result_json'])
            verify_audio(source, result, root, classroom_id)
            current = service.runtime.get_classroom(classroom_id)
            local_path = root / (classroom_id + '.json')
            if digest(json.loads(course_text(local_path))) != digest(current):
                fail('本机文件与运行课件不一致')
            receipt_path = archive / 'amendment.json'
            committed = service.repository.parse(row['result_json']).get('visualRevisions', [])[-1:]
            committed = committed[0] if committed and committed[0].get('revisionId') == revision_id else None
            if course_exists(receipt_path) or committed is not None:
                receipt = json.loads(course_text(receipt_path)) if course_exists(receipt_path) else committed
                if (receipt.get('sha256') != digest({k: v for k, v in receipt.items() if k != 'sha256'})
                        or receipt.get('intentSha256') != intent['sha256']):
                    fail('修订回执被改变')
                if (row['classroom_sha256'] == receipt['targetSha256'] == digest(current)
                        and persisted(current) == persisted(target)
                        and service.repository.parse(row['result_json']).get('visualRevisions', [])[-1:] == [receipt]):
                    for name, raw in derivative_files.items():
                        asset = root / classroom_id / 'media' / name
                        if not course_exists(asset) or course_bytes(asset) != raw:
                            fail('已完成修订的派生图缺失或变化')
                    immutable(receipt_path, json_bytes(receipt))
                    return receipt
                fail('已完成修订之后课件又发生变化')
            if (row['classroom_sha256'] != patch['expectedSourceSha256']
                    or row['classroom_json'] != source_row['classroom_json']
                    or row['result_json'] != source_row['result_json']):
                fail('数据库快照已变化，不能覆盖')
            if digest(current) == digest(source):
                marker = archive / 'save-attempt.json'
                if course_exists(marker):
                    fail('上次保存结果不明且未发现目标快照，不能自动重发')
                # Recheck under operator.lock, with no database row lock;
                # the runtime also forwards this read version to remote CAS.
                if digest(service.runtime.get_classroom(classroom_id)) != digest(source):
                    fail('保存前课件已被其他编辑者修改')
                for name, raw in derivative_files.items():
                    immutable(root / classroom_id / 'media' / name, raw)
                immutable(marker, json_bytes({'intentSha256': intent['sha256'], 'attemptedAt': now_ms()}))
                service.runtime.save_preview_classroom(target)
                current = service.runtime.get_classroom(classroom_id)
            if persisted(current) != persisted(target) or digest(json.loads(course_text(local_path))) != digest(current):
                fail('保存结果不符，原始课件与目标已保留供核对')
            for name, raw in derivative_files.items():
                asset = root / classroom_id / 'media' / name
                if not course_exists(asset) or course_bytes(asset) != raw:
                    fail('派生图未完整保存或字节已变化')
            immutable(archive / 'saved.json', json_bytes(current))
            receipt = {'schemaVersion': 'mira.textbook.preview-visual-amendment.v1', 'revisionId': revision_id,
                       'intentSha256': intent['sha256'], 'previewKey': key, 'classroomId': classroom_id,
                       'sourceSha256': digest(source), 'targetSha256': digest(current),
                       'audioIdentityClassroomSha256': intent['audioIdentityClassroomSha256'],
                       'audioPlanSha256': intent['files']['plan.json'], 'audioReceiptsSha256': intent['files']['receipts.json'],
                       'sceneIds': [c['sceneId'] for c in patch['changes']], 'reviewer': patch['reviewer'], 'basis': patch['basis'],
                       'generationDispatched': False, 'ttsDispatched': False, 'asrDispatched': False,
                       'atomicRuntimeCompareAndSwapAvailable': False, 'publicationAllowed': False}
            if derived:
                receipt.update(patchSchemaVersion=QUANTITY_VISUAL_SCHEMA,
                               derivedImagesSha256=intent['files']['derived-images.json'])
            elif patch['schemaVersion'] in (IMAGE_ALT_SCHEMA, QUESTION_BINDING_SCHEMA):
                receipt['patchSchemaVersion'] = patch['schemaVersion']
            receipt['sha256'] = digest(receipt)
            updated = {**result, **intent['checks']}
            updated.pop('frozenPreview', None)
            updated['visualRevisions'] = [*result.get('visualRevisions', []), receipt]
            conn.commit_phase()
            if (json.loads(course_text(local_path)) != current
                    or any(course_bytes(audio_folder / name) != course_bytes(archive / name)
                           for name in ('plan.json', 'receipts.json'))):
                fail('提交前运行原稿或配音证据已变化，保留修订断点')
            changed = conn.execute("UPDATE learning_textbook_course_previews SET classroom_json=?,classroom_sha256=?,result_json=?,updated_at=? WHERE preview_key=? AND classroom_sha256=? AND status='preview_ready'",
                                   (canonical(current), digest(current), canonical(updated), now_ms(), key, digest(source))).rowcount
            if changed != 1:
                fail('数据库版本已变化，请对账已有修订')
        # A crash after the commit is recovered from the exact saved snapshot
        # and the amendment already committed in result_json on the next run.
        immutable(receipt_path, json_bytes(receipt))
        return receipt


def verify_quantity_visual_revisions(row, classroom_directory):
    """Revalidate v4 derivation and amendment chain before publication.

    Frozen input and original narration bytes remain unchanged. Legacy visual
    revisions keep their existing contract unless a v4 amendment uses them as
    history; this check performs no writes or provider calls.
    """
    result = json.loads(row['result_json'])
    revisions = result.get('visualRevisions', [])
    if not any(r.get('patchSchemaVersion') == QUANTITY_VISUAL_SCHEMA for r in revisions):
        return
    root = Path(classroom_directory).resolve()
    audio = root / row['classroom_id'] / 'textbook-preview-audio'
    previous = None
    try:
        for receipt in revisions:
            revision_id = receipt.get('revisionId')
            if not SHA.fullmatch(str(revision_id)):
                fail('视觉修订归档编号无效')
            archive = audio / 'visual-revisions' / revision_id
            intent = json.loads(course_text(archive / 'intent.json'))
            patch = intent['patch']
            validate_patch(patch)
            if (receipt.get('sha256') != digest({k: v for k, v in receipt.items() if k != 'sha256'})
                    or intent.get('sha256') != digest({k: v for k, v in intent.items() if k != 'sha256'})
                    or receipt.get('intentSha256') != intent['sha256']
                    or digest({'previewKey': row['preview_key'], 'patch': patch}) != revision_id
                    or intent.get('previewKey') != row['preview_key'] or intent.get('classroomId') != row['classroom_id']
                    or json.loads(course_text(archive / 'amendment.json')) != receipt):
                fail('视觉修订回执或归档绑定已变化')
            expected = {'source.json', 'source-row.json', 'target.json', 'plan.json', 'receipts.json'}
            if patch['schemaVersion'] == QUANTITY_VISUAL_SCHEMA:
                expected |= {'derived-images.json', *('derived-' + a['sha256'] + '.png' for a in patch['derivedImages'])}
            if set(intent.get('files', {})) != expected:
                fail('视觉修订归档文件清单不一致')
            for name, sha in intent['files'].items():
                if sha_bytes(course_bytes(archive / name)) != sha:
                    fail('视觉修订归档字节已变化')
            for name in ('plan.json', 'receipts.json'):
                if course_bytes(archive / name) != course_bytes(audio / name):
                    fail('数量图修订不能改变原配音计划或收据')
            source = json.loads(course_text(archive / 'source.json'))
            source_row = json.loads(course_text(archive / 'source-row.json'))
            target = json.loads(course_text(archive / 'target.json'))
            saved = json.loads(course_text(archive / 'saved.json'))
            if (source_row['input_json'] != row['input_json'] or digest(source) != patch['expectedSourceSha256']
                    or digest(source) != receipt['sourceSha256']
                    or previous is not None and previous != receipt['sourceSha256']
                    or persisted(saved) != persisted(target) or digest(saved) != receipt['targetSha256']
                    or candidate(source, patch, root, json.loads(row['input_json'])) != target):
                fail('视觉修订链与冻结输入或原课件不一致')
            derived, files = quantity_assets(source, patch, root, json.loads(row['input_json']))
            if derived:
                if (json.loads(course_text(archive / 'derived-images.json')) != derived
                        or receipt.get('patchSchemaVersion') != QUANTITY_VISUAL_SCHEMA
                        or receipt.get('derivedImagesSha256') != intent['files']['derived-images.json']):
                    fail('数量图派生证据与回执不一致')
                for name, raw in files.items():
                    if course_bytes(root / row['classroom_id'] / 'media' / name) != raw:
                        fail('数量图派生资源已变化')
            previous = receipt['targetSha256']
        if previous != row['classroom_sha256'] or digest(json.loads(row['classroom_json'])) != previous:
            fail('待发布课件不是完整视觉修订链的最终版本')
    except (OSError, KeyError, TypeError, ValueError) as exc:
        fail('无法核验数量图派生归档：' + str(exc))
