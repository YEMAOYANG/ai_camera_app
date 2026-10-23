"""Frozen, private preview inputs, deliberately distinct from publishable briefs."""
import base64
from collections import Counter
from copy import deepcopy
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
import json
import hashlib
import re

from content.textbook_catalog import authoring_prompt, digest, lesson_by_id, validate_manifest
from content.textbook_interactive_narration import bind_interactive_audio, interactive_cues
from content.textbook_pedagogy import teaching_profile
from core.errors import ApiError

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts/textbook-preview.v3.json"
MEDIA_PATH = Path(__file__).resolve().parent / "textbooks/lesson-media-v1/tiandiren.json"
UNITS_PATH = Path(__file__).resolve().parent / "textbooks/learning-units"
OPERATOR_PROMPT_SCHEMA = "mira.learning.textbook-operator-preview-prompt.v1"
OPERATOR_AUTHORING_FIELDS = ("mode", "sessionId", "stageId", "skillIds", "request", "imageProvenance")
OPERATOR_IMAGE = re.compile(r"/api/classroom-media/([A-Za-z0-9_-]+)/media/([A-Za-z0-9_.-]+\.(?:png|webp|jpe?g))")
# Same pinned module and import convention as the hand-built 3D activities.
THREE_MODULE_PATH = "public/vendor/three/0.160.0/three.module.js"
THREE_IMPORT = "await import('/vendor/three/0.160.0/three.module.js')"
THREE_SHA256 = "76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495"
KATEX_TAG = re.compile(r"<link\b[^>]*cdn\.jsdelivr\.net/npm/katex@[^>]*>\s*"
                       r"|<script\b[^>]*cdn\.jsdelivr\.net/npm/katex@[^>]*>\s*</script>\s*")
SANDBOX_STORAGE = re.compile(r"\b(?:localStorage|sessionStorage|indexedDB)\b|document\s*\.\s*cookie")
EXTERNAL_RESOURCE = re.compile(r"(?:https?:)?//(?!www\.w3\.org/)[A-Za-z0-9.-]+\.[A-Za-z]{2,}[/\"'?#]")


class _ExternalResourceParser(HTMLParser):
    """Distinguish inert citation text from resource-bearing HTML contexts."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.found = False
        self.active_text = None

    def check(self, value):
        # Attribute entities are already decoded once by HTMLParser. Also
        # reject nested encodings and entities in script/style strings, which
        # may be assigned to a resource attribute by page code later.
        while (decoded := unescape(value)) != value:
            value = decoded
        value = value.translate(str.maketrans('', '', '\t\r\n'))
        # Attribute values no longer include their closing HTML quote. Keep
        # the existing URL matcher effective for a bare host at value end.
        self.found |= bool(EXTERNAL_RESOURCE.search(value + '"'))

    def handle_starttag(self, tag, attrs):
        for _, value in attrs:
            if value is not None:
                self.check(value)
        if self.active_text is None and tag in ('script', 'style'):
            self.active_text = tag

    def handle_startendtag(self, tag, attrs):
        # HTML does not honor a self-closing slash on script/style elements.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == self.active_text:
            self.active_text = None

    def handle_data(self, data):
        if self.active_text:
            self.check(data)

    def handle_comment(self, data):
        self.check(data)


def _has_external_html_resource(html):
    parser = _ExternalResourceParser()
    parser.feed(html)
    parser.close()
    if parser.active_text:
        # HTMLParser buffers an unterminated raw-text element until its end
        # tag, so close() alone does not deliver that body to handle_data.
        parser.check(parser.rawdata)
    return parser.found


def preview_media(media_path=MEDIA_PATH):
    """Freeze verified original bytes along with the lesson, not a mutable URL."""
    if not media_path.is_file():
        raise ApiError("textbook_preview_media_required", "本课教学范围已登记，原创教学插画尚未完成，不能开始生成", 409)
    manifest = json.loads(media_path.read_text(encoding="utf-8"))
    for asset in manifest["assets"]:
        path = media_path.parent / asset["file"]
        if path.parent != media_path.parent or hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
            raise ApiError("textbook_preview_media_changed", "课件插画摘要不一致，请先核对素材", 409)
    return manifest


def lesson_blueprint(manifest, node_id, units_path=UNITS_PATH):
    """The verified plan of one lesson, from whichever unit file of its edition holds it."""
    for path in sorted(units_path.glob('*.json')):
        unit = json.loads(path.read_text(encoding='utf-8'))
        if (manifest['editionId'], manifest['revisionId']) != (unit['editionId'], unit['revisionId']):
            continue
        lesson = next((v for v in unit['lessons'] if v['nodeId'] == node_id), None)
        if lesson:
            if lesson['status'] != 'scope_verified_preview_only':
                return None
            return {**lesson, 'sourceScope': unit['source']}
    return None


def blueprint_question_count(blueprint):
    """Count reviewed samples from a server-loaded unit, never request overrides.

    A mapping samples one indexed learning target per question. It need not
    claim that objective questions assess every open expression/reading goal.
    Missing mappings keep the historical one-question-per-target contract;
    malformed explicit mappings fail instead of silently lowering the count.
    """
    targets = blueprint['targets']
    if 'assessmentMapping' not in blueprint:
        return len(targets)
    mapping = blueprint['assessmentMapping']
    valid = isinstance(mapping, list) and 1 <= len(mapping) <= 30
    seen = set()
    for item in mapping if valid else ():
        if (not isinstance(item, dict)
                or type(item.get('targetIndex')) is not int
                or not 0 <= item['targetIndex'] < len(targets)
                or not isinstance(item.get('questionId'), str)
                or not item['questionId'].strip() or item['questionId'] != item['questionId'].strip()
                or item['questionId'] in seen
                or type(item.get('page')) is not int or not 1 <= item['page'] <= 60):
            valid = False
            break
        seen.add(item['questionId'])
    if not valid:
        raise ApiError('textbook_preview_scope_unsupported', '本课已登记的测评目标映射无效', 409)
    return len(mapping)


def blueprint_prompt(blueprint):
    count = len(blueprint['targets'])
    question_count = blueprint_question_count(blueprint)
    mapped_targets = [item['targetIndex'] for item in blueprint.get('assessmentMapping', [])]
    sequential = 'assessmentMapping' not in blueprint or mapped_targets == list(range(count))
    assessment_instruction = ('每道题按目标列表顺序覆盖一个目标。' if sequential else
        '题目按已登记测评映射依次取样目标' +
        '、'.join(str(item['targetIndex'] + 1) for item in blueprint['assessmentMapping']) +
        '；其余开放作品和共读目标不宣称已被这些题评估。')
    return {'schemaVersion': 'mira.learning.textbook-preview-prompt.v4', 'version': '4',
        'expectedSceneCount': count + 4, 'expectedQuestionCount': question_count, 'targets': blueprint['targets'],
        'requiredSceneTypes': ['slide', 'interactive', 'quiz'], 'instructions': [
            '制作原创教研预览。教材只用于对齐学习范围，不使用教材原文、原题、原图、录音或版式。不得宣布审核或发布通过。',
            '一年级尚不能独立读字。问题、答案和操作使用有意义的场景图与多幅图片选项，教师短句语音引导。文字只作辅助，不用拼音、emoji或装饰图替代教学图片。',
            f'制作 {count + 4} 个场景：生活导入；每个目标各一个讲解场景；一个动手互动；一个含 {question_count} 道原创单选题的原生 quiz；一个总结。' + assessment_instruction,
            '目标依次是：' + '、'.join(blueprint['targets']) + '。这些是图片支持下的理解练习，不自动认定独立识字、朗读或书写达标。',
            '每页一个重点、大图、短句。使用已验证素材清单的真实图片路径，每个场景 description 携带素材和图片任务，禁止生成占位图。',
            '互动设计：' + blueprint['game'], '独立新情境检验：' + blueprint['transfer'],
            '错选先提醒观察方法，再举例，最后带做；获助后的正确不能计为独立完成。连续困难时暂停，不要求无限重试。',
            '每题提供三个可区分的图片选项和简短原因。不要用纯文字选项。禁用 speechSynthesis，讲解通过课堂已有教师 speech 动作完成。',
            '画布与现有课堂一致：1000×562.5、纸白 #fcf6ec、深色文字 #29383b、暖黄与鼠尾草绿点缀。图片保持正确比例，避免文字挡住关键内容。',
            '正常一节约 8 至 10 分钟；已会的目标交由课外适配层缩短。不要虚构已记录的成绩、复习结果或家长用时。']}


def preview_input(manifest, node_id, *, teaching_revision="1"):
    manifest = validate_manifest(manifest)
    unit, lesson = lesson_by_id(manifest, node_id)
    legacy_scope = (manifest["editionId"], manifest["revisionId"], node_id) == (
        "pep-chinese-g1-upper-2022-standard", "20260924-preview-2", "u1-l1"
    )
    blueprint = None if legacy_scope else lesson_blueprint(manifest, node_id)
    if not legacy_scope and blueprint is None:
        raise ApiError("textbook_preview_scope_unsupported", "本课教学范围尚未核验", 409)
    prompt = blueprint_prompt(blueprint) if blueprint else json.loads(PROMPT_PATH.read_text(encoding="utf-8"))
    media = preview_media(MEDIA_PATH.parent / blueprint['mediaManifest']) if blueprint else preview_media()
    original = authoring_prompt()
    brief = {
        "schemaVersion": "mira.learning.textbook-private-preview.v1",
        "editionId": manifest["editionId"], "alignmentRevisionId": manifest["revisionId"],
        "manifestSha256": digest(manifest), "nodeId": node_id,
        "gradeCode": manifest["gradeCode"], "subject": manifest["subject"],
        "teachingProfile": teaching_profile(manifest["gradeCode"]),
        "unitTitle": unit["title"], "lessonTitle": lesson["title"],
        "knowledgeBrief": blueprint['knowledgeBrief'] if blueprint else lesson["brief"],
        "executionPolicy": "persist-content-before-segment-audio.v2",
        "originalPrompt": original, "previewPrompt": prompt,
        "originalMedia": media,
        "generationOptions": {"enable_web_search": False, "enable_image_generation": False,
                              "enable_video_generation": False, "enable_tts": False, "agent_mode": "default"},
        "publicationAllowed": False,
    }
    if blueprint:
        brief['sourceScope'] = blueprint['sourceScope']
    # Keep v1 hashes stable; explicit later teaching versions get distinct work.
    if teaching_revision != "1":
        brief["teachingRevision"] = teaching_revision
    key = digest(brief)
    requirement = "\n".join(original["instructions"] + prompt["instructions"])
    requirement += "\n年级教学规则：\n" + json.dumps(brief["teachingProfile"], ensure_ascii=False, indent=2)
    requirement += "\n教材对应：统编版六年制一年级语文上册 · " + unit["title"] + " · " + lesson["title"]
    requirement += "\n已制作的原创教学插画（必须使用真实图片元素，路径原样保留在每个场景大纲的description中，不另调图片生成）：\n" + json.dumps(brief["originalMedia"], ensure_ascii=False, indent=2)
    requirement += "\n教学目标与范围：\n" + json.dumps({
        k: brief["knowledgeBrief"][k] for k in ("objectives", "knowledgePoints", "priorKnowledge", "excludedTopics")
    }, ensure_ascii=False, indent=2)
    requirement += "\n制作追踪编号（不得在学生画面或语音中展示）：" + key
    return {**brief, "previewKey": key, "requirement": requirement}


def self_contained_classroom(classroom, read_three_module):
    """Return a copy whose interactive pages load nothing from another host.

    Released pages run in an opaque sandbox and must work offline. The unused
    CDN formula renderer becomes a no-op and the pinned vendored three.js is
    inlined, as the hand-built 3D activities do; any other host is refused.
    Browser storage throws in that sandbox and can stop a page's whole script.
    """
    result = deepcopy(classroom)
    for scene in result.get("scenes", []):
        content = scene.get("content")
        if scene.get("type") != "interactive" or not isinstance(content, dict) or not isinstance(content.get("html"), str):
            continue
        stub = iter(["<script>window.renderMathInElement=function(){};</script>"])
        html = KATEX_TAG.sub(lambda _: next(stub, ""), content["html"])
        if THREE_IMPORT in html:
            module = read_three_module()
            if hashlib.sha256(module).hexdigest() != THREE_SHA256:
                raise ApiError("textbook_preview_adoption_rejected", "三维依赖与已核对版本不一致", 409)
            data_uri = "data:text/javascript;base64," + base64.b64encode(module).decode("ascii")
            html = html.replace(THREE_IMPORT, "await import(" + json.dumps(data_uri) + ")")
        if (_has_external_html_resource(html) or re.search(r"\bkatex\s*\.", html)
                or str(content.get("url") or "").startswith(("http:", "https:", "//"))):
            raise ApiError("textbook_preview_adoption_rejected", "互动页引用了外部网站资源，发布课件必须自包含", 409)
        if SANDBOX_STORAGE.search(html):
            raise ApiError("textbook_preview_adoption_rejected", "互动页使用了浏览器存储，在发布课件的隔离环境里会报错", 409)
        content["html"] = html
    return result


def unique_speech_ids(classroom):
    """Return a copy whose narration lines have lesson-wide unique ids.

    Publication audits each line by its id alone, while an Agent session
    commonly reuses ids such as ``act-intro`` on every page.
    """
    result = deepcopy(classroom)
    lines = [(scene, action) for scene in result.get("scenes", [])
             for action in scene.get("actions", []) if action.get("type") == "speech"]
    counts = Counter(action.get("id") for _, action in lines)
    for scene, action in lines:
        if counts[action.get("id")] > 1:
            action["id"] = f"{scene.get('id')}-{action.get('id')}"
    if len({action["id"] for _, action in lines}) != len(lines):
        raise ApiError("textbook_preview_adoption_rejected", "讲解段落编号重复，无法逐段核对语音", 409)
    return result


def cue_speech(scene):
    """Pair each in-page teacher cue with the same-page speech line that reads it.

    Operator pages never synthesise speech in the browser. A cue replays the
    audited recording of the speech action carrying exactly its text, so the
    page gains no sound that narration and its audit did not already cover.
    """
    html = scene.get("content", {}).get("html")
    try:
        cues = interactive_cues(html)
        if cues:
            bind_interactive_audio(html, {cue["id"]: "/api/classroom-media/check/audio/check.wav" for cue in cues}, "check")
    except ValueError as exc:
        raise ApiError("textbook_preview_adoption_rejected", "互动页的老师语音提示不合规：" + str(exc), 409) from exc
    lines = {}
    for action in scene.get("actions", []):
        if action.get("type") == "speech":
            lines.setdefault(str(action.get("text") or "").strip(), action)
    missing = [cue["id"] for cue in cues if cue["text"] not in lines]
    if missing:
        raise ApiError("textbook_preview_adoption_rejected", "互动页语音提示缺少同页老师旁白：" + "、".join(missing), 409)
    return {cue["id"]: lines[cue["text"]] for cue in cues}


def operator_media(classroom, classroom_directory, provenance):
    """Freeze the saved illustration bytes an operator-authored classroom shows."""
    root = Path(classroom_directory).resolve()
    assets = []
    for owner, name in sorted(set(OPERATOR_IMAGE.findall(json.dumps(classroom, ensure_ascii=False)))):
        path = (root / owner / "media" / name).resolve()
        if root not in path.parents or not path.is_file():
            raise ApiError("textbook_preview_media_changed", "课件插画文件缺失，请先核对素材", 409)
        assets.append({"id": Path(name).stem, "file": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                       "mediaPath": f"/api/classroom-media/{owner}/media/{name}", "provenance": provenance})
    if not assets:
        raise ApiError("textbook_preview_media_required", "本课没有可核验的原创教学插画，不能接收", 409)
    return {"schemaVersion": "mira.textbook.lesson-media.v1", "version": "1", "assets": assets}


def operator_preview_input(manifest, node_id, classroom, media, authoring, *, teaching_revision="1",
                           authoring_candidate=None):
    """Freeze an operator-authored saved classroom. It is never a dispatch brief."""
    manifest = validate_manifest(manifest)
    unit, lesson = lesson_by_id(manifest, node_id)
    blueprint = lesson_blueprint(manifest, node_id)
    if blueprint is None:
        raise ApiError("textbook_preview_scope_unsupported", "本课教学范围尚未核验", 409)
    if (not isinstance(authoring, dict) or set(authoring) != set(OPERATOR_AUTHORING_FIELDS)
            or authoring["mode"] != "openmaic_pro_workbench"
            or not isinstance(authoring["skillIds"], list) or not authoring["skillIds"]
            or any(not isinstance(authoring[k], str) or not authoring[k].strip()
                   for k in ("sessionId", "stageId", "request", "imageProvenance"))
            or any(not isinstance(skill, str) or not skill.strip() for skill in authoring["skillIds"])
            or len(authoring["request"]) > 20000):
        raise ApiError("textbook_preview_authoring_invalid", "需要完整的运营制作记录", 400)
    scenes = classroom.get("scenes", [])
    if not 3 <= len(scenes) <= 60:
        raise ApiError("textbook_preview_adoption_rejected", "课件页数不在可接收范围内", 409)
    brief = {
        "schemaVersion": "mira.learning.textbook-private-preview.v1",
        "editionId": manifest["editionId"], "alignmentRevisionId": manifest["revisionId"],
        "manifestSha256": digest(manifest), "nodeId": node_id,
        "gradeCode": manifest["gradeCode"], "subject": manifest["subject"],
        "teachingProfile": teaching_profile(manifest["gradeCode"]),
        "unitTitle": unit["title"], "lessonTitle": lesson["title"],
        "knowledgeBrief": blueprint["knowledgeBrief"], "sourceScope": blueprint["sourceScope"],
        "executionPolicy": "operator-authored-saved-classroom.v1",
        # The saved page count is reviewed; question samples come only from the registered unit.
        "previewPrompt": {"schemaVersion": OPERATOR_PROMPT_SCHEMA, "version": "1",
            "expectedSceneCount": len(scenes), "expectedQuestionCount": blueprint_question_count(blueprint),
            "targets": blueprint["targets"], "requiredSceneTypes": ["slide", "interactive", "quiz"]},
        "originalMedia": media, "authoring": authoring, "sourceSha256": digest(classroom),
        "publicationAllowed": False,
    }
    if authoring_candidate is not None:
        brief["authoringCandidate"] = authoring_candidate
    if teaching_revision != "1":
        brief["teachingRevision"] = teaching_revision
    return {**brief, "previewKey": digest(brief), "requirement": authoring["request"]}


class _ResponsiveActivityMarker(HTMLParser):
    """Require the explicit head opt-in consumed by the native iframe host.

    This is a new-preview check, not a rewrite of historical HTML. Inert
    examples in comments, scripts, templates or body markup cannot opt in.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.markers = []

    def handle_starttag(self, tag, attrs):
        if tag == 'meta' and self.stack in (['head'], ['html', 'head']):
            names = [value for name, value in attrs if name == 'name']
            if any(isinstance(value, str) and value.strip().lower() == 'mira-responsive-activity'
                   for value in names):
                contents = [value for name, value in attrs if name == 'content']
                self.markers.append(len(names) == len(contents) == 1
                    and isinstance(contents[0], str) and contents[0].strip() == 'low-reading-v1')
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
                       'param', 'source', 'track', 'wbr'}:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        # HTML ignores the slash on non-void elements such as script/template.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in self.stack:
            del self.stack[len(self.stack) - 1 - self.stack[::-1].index(tag):]


def responsive_activity_marker(html):
    parser = _ResponsiveActivityMarker()
    parser.feed(html)
    return parser.markers == [True]


def preview_checks(classroom, expected_scene_count=8, media_manifest=None, expected_question_count=6,
                   *, grade_code=None, responsive_scene_ids=None):
    """Structural checks only. Human pedagogy/originality review remains open."""
    scenes = classroom.get("scenes", [])
    issues = []
    if len(scenes) != expected_scene_count:
        issues.append("scene_count_mismatch")
    types = {s.get("type") for s in scenes}
    if not {"slide", "interactive", "quiz"} <= types:
        issues.append("required_scene_type_missing")
    if any(s.get("type") == "interactive" and "widgetConfig" in s.get("content", {})
           and not isinstance(s["content"]["widgetConfig"], dict) for s in scenes):
        issues.append("interactive_config_invalid")
    # Revision adapters derive this scope from their already verified HTML
    # diff, never from a client-provided exemption list. None checks every page
    # of a newly adopted/generated course; an empty diff preserves old pages.
    if responsive_scene_ids is not None and not set(responsive_scene_ids) <= {s.get('id') for s in scenes}:
        issues.append('responsive_activity_scope_invalid')
    if grade_code in {'primary_1', 'primary_2'} and any(
            s.get('type') == 'interactive' and isinstance(s.get('content', {}).get('html'), str)
            and (responsive_scene_ids is None or s.get('id') in responsive_scene_ids)
            and not responsive_activity_marker(s['content']['html']) for s in scenes):
        issues.append('responsive_activity_marker_missing')
    speeches = [a for s in scenes for a in s.get("actions", []) if a.get("type") == "speech"]
    if not speeches or any(not a.get("text") or not a.get("audioId") or not a.get("audioUrl") for a in speeches):
        issues.append("speech_audio_missing")
    questions = [q for s in scenes if s.get("type") == "quiz" for q in s.get("content", {}).get("questions", [])]
    if len(questions) != expected_question_count:
        issues.append("expected_six_questions" if expected_question_count == 6 else "question_count_mismatch")
    if media_manifest:
        references = {asset["mediaPath"] for asset in media_manifest["assets"]}
        slides = [s for s in scenes if s.get("type") == "slide"]
        if any(not any(e.get("type") == "image" and e.get("src") in references
                       for e in s.get("content", {}).get("canvas", {}).get("elements", [])) for s in slides):
            issues.append("original_teaching_image_missing")
        interactive = [s for s in scenes if s.get("type") == "interactive"]
        if any(not any(ref in json.dumps(s.get("content", {}), ensure_ascii=False) for ref in references) for s in interactive):
            issues.append("interactive_teaching_image_missing")
    return {"sceneCount": len(scenes), "sceneTypes": sorted(types), "speechCount": len(speeches),
            "questionCount": len(questions), "issues": issues,
            "publicationAllowed": False, "humanReviewRequired": True}
