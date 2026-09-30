"""Frozen, private preview inputs, deliberately distinct from publishable briefs."""
from pathlib import Path
import json
import hashlib

from content.textbook_catalog import authoring_prompt, digest, lesson_by_id, validate_manifest
from content.textbook_pedagogy import teaching_profile
from core.errors import ApiError

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts/textbook-preview.v3.json"
MEDIA_PATH = Path(__file__).resolve().parent / "textbooks/lesson-media-v1/tiandiren.json"


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


def lesson_blueprint(manifest, node_id):
    unit = json.loads((MEDIA_PATH.parent.parent / 'learning-units/primary1-literacy.v1.json').read_text())
    if (manifest['editionId'], manifest['revisionId']) != (unit['editionId'], unit['revisionId']):
        return None
    lesson = next((v for v in unit['lessons'] if v['nodeId'] == node_id), None)
    if not lesson or lesson['status'] != 'scope_verified_preview_only':
        return None
    return {**lesson, 'sourceScope': unit['source']}


def blueprint_prompt(blueprint):
    count = len(blueprint['targets'])
    return {'schemaVersion': 'mira.learning.textbook-preview-prompt.v4', 'version': '4',
        'expectedSceneCount': count + 4, 'expectedQuestionCount': count, 'targets': blueprint['targets'],
        'requiredSceneTypes': ['slide', 'interactive', 'quiz'], 'instructions': [
            '制作原创教研预览。教材只用于对齐学习范围，不使用教材原文、原题、原图、录音或版式。不得宣布审核或发布通过。',
            '一年级尚不能独立读字。问题、答案和操作使用有意义的场景图与多幅图片选项，教师短句语音引导。文字只作辅助，不用拼音、emoji或装饰图替代教学图片。',
            f'制作 {count + 4} 个场景：生活导入；每个目标各一个讲解场景；一个动手互动；一个含 {count} 道原创单选题的原生 quiz；一个总结。每道题按目标列表顺序覆盖一个目标。',
            '目标依次是：' + '、'.join(blueprint['targets']) + '。这些是图片支持下的理解练习，不自动认定独立识字、朗读或书写达标。',
            '每页一个重点、大图、短句。使用已验证素材清单的真实图片路径，每个场景 description 携带素材和图片任务，禁止生成占位图。',
            '互动设计：' + blueprint['game'], '独立新情境检验：' + blueprint['transfer'],
            '错选先提醒观察方法，再举例，最后带做；获助后的正确不能计为独立完成。连续困难时暂停，不要求无限重试。',
            '每题提供三个可区分的图片选项和简短原因。不要用纯文字选项。禁用 speechSynthesis，讲解通过课堂已有教师 speech 动作完成。',
            '画布与现有课堂一致：1000×562.5、纸白 #fcf6ec、深色文字 #29383b、暖黄与鼠尾草绿点缀。图片保持正确比例，避免文字挡住关键内容。',
            '正常一节约 8 至 10 分钟；已会的目标交由课外适配层缩短。不要虚构已记录的成绩、复习结果或家长用时。']}


def preview_input(manifest, node_id):
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


def preview_checks(classroom, expected_scene_count=8, media_manifest=None, expected_question_count=6):
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
