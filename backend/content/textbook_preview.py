"""Frozen, private preview inputs, deliberately distinct from publishable briefs."""
from pathlib import Path
import json

from content.textbook_catalog import authoring_prompt, digest, lesson_by_id, validate_manifest
from core.errors import ApiError

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts/textbook-preview.v1.json"


def preview_input(manifest, node_id):
    manifest = validate_manifest(manifest)
    unit, lesson = lesson_by_id(manifest, node_id)
    # This first adapter has one reviewed source scope. Do not silently reuse
    # its early-literacy pedagogy for an unverified lesson or another grade.
    if (manifest["editionId"], manifest["revisionId"], node_id) != (
        "pep-chinese-g1-upper-2022-standard", "20260924-preview-2", "u1-l1"
    ):
        raise ApiError("textbook_preview_scope_unsupported", "当前预览仅支持已核对的第一课", 409)
    prompt = json.loads(PROMPT_PATH.read_text(encoding="utf-8"))
    original = authoring_prompt()
    brief = {
        "schemaVersion": "mira.learning.textbook-private-preview.v1",
        "editionId": manifest["editionId"], "alignmentRevisionId": manifest["revisionId"],
        "manifestSha256": digest(manifest), "nodeId": node_id,
        "gradeCode": manifest["gradeCode"], "subject": manifest["subject"],
        "unitTitle": unit["title"], "lessonTitle": lesson["title"],
        "knowledgeBrief": lesson["brief"],
        "executionPolicy": "persist-content-before-segment-audio.v2",
        "originalPrompt": original, "previewPrompt": prompt,
        "generationOptions": {"enable_web_search": False, "enable_image_generation": False,
                              "enable_video_generation": False, "enable_tts": False, "agent_mode": "default"},
        "publicationAllowed": False,
    }
    key = digest(brief)
    requirement = "\n".join(original["instructions"] + prompt["instructions"])
    requirement += "\n教材对应：统编版六年制一年级语文上册 · " + unit["title"] + " · " + lesson["title"]
    requirement += "\n教学目标与范围：\n" + json.dumps({
        k: lesson["brief"][k] for k in ("objectives", "knowledgePoints", "priorKnowledge", "excludedTopics")
    }, ensure_ascii=False, indent=2)
    requirement += "\n制作追踪编号（不得在学生画面或语音中展示）：" + key
    return {**brief, "previewKey": key, "requirement": requirement}


def preview_checks(classroom, expected_scene_count=8):
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
    if len(questions) != 6:
        issues.append("expected_six_questions")
    return {"sceneCount": len(scenes), "sceneTypes": sorted(types), "speechCount": len(speeches),
            "questionCount": len(questions), "issues": issues,
            "publicationAllowed": False, "humanReviewRequired": True}
