"""Freeze exact, provider-free inputs for private textbook authoring drafts."""
from copy import deepcopy
import json
from pathlib import Path
import re

from content.textbook_catalog import digest, validate_manifest
from content.textbook_pedagogy import teaching_profile
from content.teacher_profiles import get_formal_subject_qwen_voice_identity, get_formal_runtime_teacher_contract
from content.textbook_interactive_narration import IDENTITY as CUE_IDENTITY, interactive_cues
from content.textbook_provided_media import validate_provided_media

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "prompts/textbook-batch-authoring.v4.json"
QUALITY_PATH = ROOT / "content/textbook_courseware_quality.v1.json"
INPUT_SCHEMA = "mira.textbook.private-batch-generation-input.v1"
SCOPE_SCHEMA = "mira.textbook.reviewed-lesson-scope.v1"
KINDS = ("book_exploration", "unit_guide", "lesson_courseware")
HASH = re.compile(r"[a-f0-9]{64}\Z")
IDENTITY_KEYS = ("schemaVersion", "kind", "scope", "manifestSha256", "teachingProfileSha256",
                 "qualityPolicySha256", "knowledgeBriefSha256", "originalContentSha256")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _manifest(task):
    paths = task.get("sourcePaths", [])
    _require(isinstance(paths, list) and paths, "Task has no exact manifest source")
    found = []
    for path in paths:
        value = validate_manifest(_read(path))
        _require(digest(value) == task["manifestSha256"], "Source manifest changed after planning")
        found.append(value)
    _require(all(value == found[0] for value in found), "Conflicting manifest sources")
    return found[0]


def reviewed_lesson_scope(task, path):
    _require(path is not None, "Lesson requires an explicit reviewed scope file")
    scope = _read(path)
    _require(isinstance(scope, dict) and scope.get("schemaVersion") == SCOPE_SCHEMA,
             "Reviewed lesson scope schema is invalid")
    _require(scope.get("taskId") == task["taskId"] and scope.get("binding") == task["scope"]
             and scope.get("manifestSha256") == task["manifestSha256"], "Reviewed scope binding does not match task")
    _require(scope.get("reviewStatus") == "approved" and all(isinstance(scope.get(k), str) and scope[k].strip()
             for k in ("reviewer", "basis", "assessmentMode")), "Lesson scope has no explicit review evidence")
    for key in ("objectives", "knowledgePoints", "priorKnowledge", "excludedTopics"):
        value = scope.get(key)
        _require(isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)
                 and (bool(value) or key in {"priorKnowledge", "excludedTopics"}), "Reviewed lesson scope is incomplete")
    return scope


def freeze_input(task, *, reviewed_scope_path=None, design_plan_path=None, enrich_existing=False,
                 quality_path=QUALITY_PATH, prompt_path=PROMPT_PATH):
    """No DB/configuration/provider access; pending rights never become approval."""
    _require(isinstance(task, dict) and task.get("kind") in KINDS, "Invalid authoring task kind")
    _require(HASH.fullmatch(str(task.get("taskId", ""))) is not None, "Invalid authoring task identity")
    _require(all(key in task for key in IDENTITY_KEYS)
             and digest({key: task[key] for key in IDENTITY_KEYS}) == task["taskId"], "Authoring task identity changed")
    manifest = _manifest(task)
    scope = task["scope"]
    _require(all(scope.get(key) == manifest[key] for key in
                 ("editionId", "revisionId", "gradeCode", "subject", "schoolSystem", "volume")), "Textbook binding changed")
    _require(manifest["units"] and manifest["coverage"]["status"] != "index_only", "Official directory is missing")
    _require(task.get("originalContent") is None or enrich_existing,
             "Original introduction already exists; use explicit enrich-existing to prepare media enrichment")
    profile = teaching_profile(manifest["gradeCode"])
    _require(profile == task["teachingProfile"] and digest(profile) == task["teachingProfileSha256"],
             "Grade pedagogy changed after planning")
    quality = _read(quality_path)
    quality_hash = digest({k: v for k, v in quality.items() if k != "policySha256"})
    _require(quality.get("schemaVersion") == "mira.textbook.courseware-quality-policy.v1"
             and quality.get("policySha256") == quality_hash == task["qualityPolicySha256"],
             "Quality policy changed after planning")
    unit = next((u for u in manifest["units"] if u["unitId"] == scope.get("unitId")), None)
    lesson = next((n for n in (unit or {}).get("lessons", []) if n["nodeId"] == scope.get("nodeId")), None)
    kind = task["kind"]
    _require(kind == "book_exploration" or unit is not None, "Unit does not belong to exact directory")
    _require(kind != "book_exploration" or (scope.get("unitId") is None and scope.get("nodeId") is None),
             "Book exploration scope is inconsistent")
    _require(kind != "unit_guide" or scope.get("nodeId") is None, "Unit guide scope is inconsistent")
    _require(kind != "lesson_courseware" or lesson is not None, "Lesson does not belong to exact unit")
    introduction = (manifest.get("introduction") if kind == "book_exploration" else
                    unit.get("introduction") if kind == "unit_guide" else None)
    _require(task.get("originalContent") == introduction, "Original introduction changed after planning")
    knowledge = lesson["brief"] if lesson else None
    _require(task.get("knowledgeBriefSha256") == (digest(knowledge) if knowledge else None)
             and task.get("originalContentSha256") == (digest(introduction) if introduction else None),
             "Teaching content hash changed after planning")
    directory = [{"unitId": u["unitId"], "title": u["title"], "lessons": [
        {"nodeId": n["nodeId"], "title": n["title"], "sectionTitle": n.get("sectionTitle"),
         "brief": deepcopy(n["brief"])} for n in u["lessons"]
        if not lesson or n["nodeId"] == lesson["nodeId"]]} for u in ([unit] if unit else manifest["units"])]
    _require(directory == task.get("directoryScope"), "Planned directory scope differs from exact manifest")
    reviewed = reviewed_lesson_scope(task, reviewed_scope_path) if lesson else None
    design = _read(design_plan_path) if design_plan_path else None
    provided_media = []
    if design is not None:
        _require(isinstance(design, dict) and design.get("schemaVersion") == "mira.textbook.activity-design.v1"
                 and design.get("binding") == scope and design.get("kind") == kind
                 and design.get("manifestSha256") == task["manifestSha256"], "Activity design does not match exact task")
        _require(design.get("status") == "draft" and design.get("publicationAllowed") is False
                 and isinstance(design.get("designInstructions"), str) and design["designInstructions"].strip(),
                 "Activity design must remain an explicit private draft")
        provided_media = validate_provided_media(design, task_id=task["taskId"], binding=scope)
        if "finiteCues" in design:
            cues = design["finiteCues"]
            _require(isinstance(cues, list) and 0 < len(cues) <= 240,
                     "Activity design finite cues are invalid")
            seen = set()
            for cue in cues:
                _require(isinstance(cue, dict) and CUE_IDENTITY.fullmatch(str(cue.get("cueId", ""))) is not None
                         and cue["cueId"] not in seen
                         and isinstance(cue.get("teacherText"), str) and 0 < len(cue["teacherText"].strip()) <= 1000,
                         "Activity design cue is incompatible with prerecorded narration")
                seen.add(cue["cueId"])
            def check_references(value):
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key.lower().endswith("cueid"):
                            _require(isinstance(child, str) and child in seen,
                                     "Activity design references an unknown narration cue")
                        else:
                            check_references(child)
                elif isinstance(value, list):
                    for child in value:
                        check_references(child)
            check_references(design.get("scenes", []))
    prompt = _read(prompt_path)
    _require(prompt.get("schemaVersion") in {"mira.textbook.private-batch-authoring-prompt.v1",
                                            "mira.textbook.private-batch-authoring-prompt.v2",
                                            "mira.textbook.private-batch-authoring-prompt.v3",
                                            "mira.textbook.private-batch-authoring-prompt.v4"}
             and isinstance(prompt.get("instructions"), list) and prompt["instructions"], "Invalid authoring prompt")
    frozen = {"schemaVersion": INPUT_SCHEMA, "taskId": task["taskId"], "kind": kind,
              "binding": deepcopy(scope), "manifestSha256": task["manifestSha256"],
              "manifest": manifest, "directoryScope": directory, "reviewedLessonScope": reviewed,
              "originalContent": introduction, "teachingProfile": profile, "qualityPolicy": quality,
              "qualityPolicyRuntimeEnforcementVerified": False, "authoringPrompt": prompt,
              "rightsReview": manifest["rightsReview"], "sourceReviewResolved": manifest["rightsReview"]["status"] == "cleared",
              "directoryComplete": manifest["coverage"]["status"] == "complete",
              "publicationAllowed": False, "studentDeliveryAllowed": False,
              "generationOptions": {"enable_web_search": False, "enable_image_generation": True,
                                    "enable_video_generation": kind != "book_exploration",
                                    "enable_tts": False, "agent_mode": "default"}}
    if design is not None:
        frozen["activityDesign"] = design
        frozen["activityDesignSha256"] = digest(design)
    if provided_media:
        frozen["generationOptions"]["enable_image_generation"] = False
        frozen["generationOptions"]["enable_video_generation"] = False
        frozen["providedMediaPolicy"] = "reuse_exact_original_bytes_no_media_provider_generation"
    scope_payload = {key: frozen[key] for key in ("kind", "binding", "manifestSha256", "directoryScope",
        "reviewedLessonScope", "originalContent", "teachingProfile", "qualityPolicy", "rightsReview", "directoryComplete")}
    if design is not None:
        scope_payload["activityDesign"] = design
    prefix = ""
    if prompt.get("version") in {"3", "4"} and scope["gradeCode"] in {"primary_1", "primary_2"}:
        frozen["activityPresentationContract"] = {
            "schemaVersion": "mira.textbook.responsive-activity-contract.v1",
            "marker": {"name": "mira-responsive-activity", "content": "low-reading-v1"},
            "minimumActualTouchTargetPx": 48,
            "requiredViewportWidths": [360, 768, 1280],
            "browserMeasurementRequired": True,
            "browserMeasurementPassed": False,
        }
        scope_payload["activityPresentationContract"] = deepcopy(frozen["activityPresentationContract"])
    if prompt.get("version") in {"2", "3", "4"}:
        identity = get_formal_subject_qwen_voice_identity(scope["subject"])
        teacher = identity.to_target_payload()
        teacher["avatarPath"] = get_formal_runtime_teacher_contract(scope["subject"])["runtime"]["avatar"]
        context = {"schemaVersion": "mira.textbook.batch-context.v2", "taskId": task["taskId"],
                   "kind": kind, "binding": deepcopy(scope), "gradeCode": scope["gradeCode"],
                   "subject": scope["subject"], "teacher": teacher,
                   "directoryComplete": frozen["directoryComplete"]}
        frozen["runtimeBatchContext"] = context
        prefix = "MIRA_TEXTBOOK_BATCH_V2\n" + json.dumps(context, ensure_ascii=False, separators=(",", ":")) + "\n"
    frozen["requirement"] = prefix + "\n".join(prompt["instructions"]) + "\n冻结任务书：\n" + json.dumps(scope_payload, ensure_ascii=False)
    if not frozen["directoryComplete"]:
        frozen["requirement"] += "\n目录不完整：只导览冻结的已知真实课次，明确尚有未同步部分，不宣称全册覆盖。"
    frozen["inputSha256"] = digest(frozen)
    return frozen


def inspect_draft(classroom, frozen):
    """Diagnostic observations only; semantic/visual/media QA remains unresolved."""
    scenes = classroom.get("scenes", [])
    issues = ["human_grade_alignment_review_required", "human_engagement_review_required",
              "human_low_reading_visual_review_required", "qwen_narration_and_asr_pending",
              "source_usage_review_required", "publication_release_review_pending"]
    if not isinstance(scenes, list) or not scenes:
        return {"issues": issues + ["scene_content_missing"], "qualityPassed": False, "publicationAllowed": False}
    interactive = [s for s in scenes if s.get("type") == "interactive"]
    widgets = [s.get("content", {}).get("widgetType") for s in interactive]
    if "game" not in widgets:
        issues.append("explicit_game_widget_missing")
    if "visualization3d" not in widgets:
        issues.append("explicit_3d_widget_missing")
    text = json.dumps(scenes, ensure_ascii=False)
    if "speechSynthesis" in text:
        issues.append("browser_speech_synthesis_forbidden")
    if frozen.get("authoringPrompt", {}).get("version") in {"2", "3", "4"}:
        for scene in interactive:
            try:
                if not interactive_cues(scene.get("content", {}).get("html", "")):
                    issues.append("interactive_prerecorded_cue_inventory_missing")
            except ValueError as exc:
                issues.append(str(exc))
        if frozen.get("reviewedLessonScope") is None and any(scene.get("type") == "quiz" for scene in scenes):
            issues.append("unreviewed_exploration_assessment_forbidden")
    if not any(a.get("type") == "speech" and a.get("text") for s in scenes for a in s.get("actions", [])):
        issues.append("teacher_narration_text_missing")
    if frozen["generationOptions"]["enable_video_generation"]:
        issues.append("actual_video_bytes_and_playback_review_required")
    if not frozen["directoryComplete"]:
        issues.append("directory_incomplete")
    return {"sceneCount": len(scenes), "interactiveSceneCount": len(interactive),
            "widgetTypes": sorted({w for w in widgets if isinstance(w, str)}), "issues": list(dict.fromkeys(issues)),
            "qualityPassed": False, "runtimeEnforcementVerified": False,
            "publicationAllowed": False, "studentDeliveryAllowed": False}
