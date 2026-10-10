"""Serial, opt-in Qwen narration for structurally checked private queue drafts.

Static checks are admission to audio authoring, never a teaching, browser,
pronunciation or publication approval. Unknown attempts resume GET-only until
an operator explicitly permits continuing previously unstarted segments.
"""
from contextlib import contextmanager
import fcntl
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import unquote, urlparse

from content.textbook_catalog import digest
from content.textbook_interactive_narration import interactive_cues
from content.textbook_provided_media import validate_frozen_provided_media
from content.textbook_release_media import MAX_MEDIA_BYTES, media_mime_type
from scripts.narrate_textbook_batch import DEFAULT_CLASSROOM_DIRECTORY, load_candidate
from services.textbook_batch_audio import (build_audio_plan, narrate_candidate,
                                         normalize_audio_inheritance)
from services.textbook_batch_generation_service import atomic_json
from services.textbook_batch_queue_service import TextbookBatchQueueService, document, file_sha

SCHEMA = "mira.textbook.queue-audio-state.v1"
LITERAL_CALL = re.compile(r"window\s*\.\s*miraNarrate\s*\(\s*(['\"])([A-Za-z0-9_-]+)\1\s*\)")


class _Markup(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.tags, self.scripts, self.choices = [], [], []
        self._script, self._choice, self._depth = None, None, 0
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if self._choice is not None:
            if tag in {"svg", "path", "rect", "circle", "ellipse", "polygon", "polyline", "line", "img"}:
                self._choice.append((tag, {key: value for key, value in attrs.items()
                                          if key not in {"id", "aria-label", "title"}}))
            if tag not in {"img", "input", "meta", "br", "hr", "source", "link"}:
                self._depth += 1
        if "data-mira-picture-choice" in attrs:
            if self._choice is not None:
                raise ValueError("nested_picture_choice_ambiguous")
            self._choice, self._depth = [], 1
        if tag == "script":
            self._script = {"attrs": attrs, "code": ""}
            self.scripts.append(self._script)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in {"img", "input", "meta", "br", "hr", "source", "link"}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "script":
            self._script = None
        if self._choice is not None:
            self._depth -= 1
            if self._depth == 0:
                self.choices.append(self._choice)
                self._choice = None

    def handle_data(self, text):
        if self._script is not None:
            self._script["code"] += text


def structural_review(folder, classroom_directory=DEFAULT_CLASSROOM_DIRECTORY):
    """Provider-free, exact teacher/binding plus conservative static admission."""
    frozen, state, classroom = load_candidate(folder)
    design = frozen.get("activityDesign", {})
    if frozen.get("activityDesignSha256") != digest(design):
        raise ValueError("queue_audio_exact_activity_design_required")
    expected = {cue["cueId"]: cue["teacherText"].strip() for cue in design.get("finiteCues", [])}
    issues, seen, scene_reports = [], set(), []
    if not expected:
        issues.append("specific_frozen_finite_cues_required_before_audio")
    provided = validate_frozen_provided_media(frozen)
    provided_sources = {entry["src"] for entry in provided}
    node = shutil.which("node")
    if not node:
        issues.append("node_static_syntax_checker_unavailable")
    text = json.dumps(classroom.get("scenes", []), ensure_ascii=False)
    if node:
        detector = "let s='';process.stdin.on('data',v=>s+=v);process.stdin.on('end',()=>console.log(/[\\p{Extended_Pictographic}\\u{1f1e6}-\\u{1f1ff}\\u20e3]/u.test(JSON.parse(s))?'yes':'no'));"
        result = subprocess.run([node, "-e", detector], input=json.dumps(text), text=True,
                                capture_output=True, timeout=20, check=True)
        if result.stdout.strip() == "yes":
            issues.append("emoji_in_scene_source")
    if re.search(r"speechSynthesis|SpeechSynthesisUtterance", text, re.I):
        issues.append("browser_tts_forbidden")
    widgets, html_by_id = [], {}
    for scene in classroom.get("scenes", []):
        prefix = str(scene.get("id")) + ":"
        if scene.get("type") == "quiz" and frozen.get("reviewedLessonScope") is None:
            issues.append(prefix + "unreviewed_quiz_forbidden")
        if scene.get("type") != "interactive":
            continue
        if scene.get("content", {}).get("type") != "interactive":
            issues.append(prefix + "native_interactive_content_type_required")
        source = scene.get("content", {}).get("html", "")
        html_by_id[scene["id"]] = source
        widget = scene.get("content", {}).get("widgetType")
        widgets.append(widget)
        try:
            cues = interactive_cues(source)
            if not cues:
                raise ValueError("finite_cues_missing")
        except ValueError as exc:
            issues.append(prefix + str(exc))
            continue
        cue_map = {cue["id"]: cue["text"] for cue in cues}
        if any(expected.get(key) != value for key, value in cue_map.items()):
            issues.append(prefix + "cue_not_exactly_frozen")
        seen.update(cue_map)
        markup = _Markup(source)
        scripts = [script for script in markup.scripts
                   if script["attrs"].get("type") != "application/json"]
        code = "\n".join(script["code"] for script in scripts)
        code += "\n" + "\n".join(value or "" for _, attrs in markup.tags
                                    for key, value in attrs.items() if key.startswith("on"))
        calls = [match[1] for match in LITERAL_CALL.findall(code)]
        if not calls or len(calls) != code.count("miraNarrate") or any(call not in cue_map for call in calls):
            issues.append(prefix + "narration_calls_must_be_fixed_declared_literals")
        if re.search(r"(?:window\s*\.\s*miraNarrate\s*=|function\s+miraNarrate\b)", code):
            issues.append(prefix + "narration_player_override_forbidden")
        if re.search(r"localStorage|sessionStorage", code):
            issues.append(prefix + "unreviewed_persistent_state")
        if not all(command in code for command in ("SET_WIDGET_STATE", "HIGHLIGHT_ELEMENT")) or not re.search(
                r"\.source\s*!==?\s*(?:window\.)?parent", code):
            issues.append(prefix + "native_parent_type_state_target_protocol_missing")
        if re.search(r"\.(?:action|payload)\b", code):
            issues.append(prefix + "old_native_event_payload_protocol")
        if node:
            for script in scripts:
                result = subprocess.run([node, "--check", "--input-type=module"], input=script["code"],
                                        text=True, capture_output=True, timeout=20)
                if result.returncode:
                    issues.append(prefix + "javascript_syntax_invalid")
                    break
        low = frozen["binding"]["gradeCode"] in {"primary_1", "primary_2"}
        graphics = [digest(graphic) for graphic in markup.choices if any(
            tag in {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line", "img"}
            for tag, _ in graphic)]
        if low and widget != "visualization3d" and (len(graphics) < 2 or len(set(graphics)) != len(graphics)):
            issues.append(prefix + "distinct_meaningful_picture_container_structure_missing")
        if low and len([attrs for tag, attrs in markup.tags if tag == "meta"
                and attrs.get("name") == "mira-responsive-activity"
                and attrs.get("content") == "low-reading-v1"]) != 1:
            issues.append(prefix + "responsive_profile_missing_or_ambiguous")
        if widget == "visualization3d":
            if not any(tag == "canvas" for tag, _ in markup.tags):
                issues.append(prefix + "3d_canvas_missing")
            three_renderer = bool(re.search(r"new\s+(?:[A-Za-z_$][\w$]*\s*\.\s*)?WebGLRenderer\s*\(", code)
                    and re.search(r"new\s+(?:[A-Za-z_$][\w$]*\s*\.\s*)?\w*Geometry\s*\(", code)
                    and re.search(r"new\s+(?:[A-Za-z_$][\w$]*\s*\.\s*)?Mesh\s*\(", code)
                    and re.search(r"\.render\s*\(", code)
                    and re.search(r"requestAnimationFrame|setAnimationLoop", code))
            native_renderer = bool(re.search(r"\.getContext\s*\(\s*(['\"])webgl2?\1", code)
                and all(re.search(r"\." + method + r"\s*\(", code) for method in (
                    "createShader", "shaderSource", "compileShader", "createProgram", "linkProgram",
                    "createBuffer", "bufferData", "uniformMatrix4fv"))
                and re.search(r"\.(?:drawElements|drawArrays)\s*\(", code)
                and "Float32Array" in code and "gl_Position" in code and "mat4" in code
                and "requestAnimationFrame" in code)
            if not (three_renderer or native_renderer):
                issues.append(prefix + "actual_3d_renderer_mesh_geometry_loop_structure_missing")
        video_count, video_sources = 0, []
        for tag, attrs in markup.tags:
            for key in ("src", "href", "poster"):
                value = attrs.get(key, "") or ""
                if re.search(r"^(?:gen_|image_|placeholder)|example\.(?:com|org)|about:blank", value, re.I):
                    issues.append(prefix + "unresolved_asset_reference")
            if tag != "video":
                continue
            video_count += 1
            src = attrs.get("src", "")
            video_sources.append(src)
            if "controls" not in attrs or "playsinline" not in attrs or not src or "autoplay" in attrs:
                issues.append(prefix + "real_user_controlled_video_required")
            if src not in provided_sources:
                path = unquote(urlparse(src).path)
                match = re.fullmatch(r"/api/classroom-media/([A-Za-z0-9_-]{1,128})/(.+)", path)
                if not match or match[1] != classroom["id"] or urlparse(src).scheme:
                    issues.append(prefix + "video_source_not_frozen_local_media")
                else:
                    root = Path(classroom_directory).resolve() / classroom["id"]
                    original_path = root / match[2]
                    media = original_path.resolve()
                    if (not media.is_relative_to(root) or not media.is_file() or original_path.is_symlink()
                            or media.stat().st_size > MAX_MEDIA_BYTES):
                        issues.append(prefix + "actual_video_bytes_missing_or_unsafe")
                    else:
                        media_mime_type(media.suffix, media.read_bytes())
        scene_reports.append({"sceneId": scene["id"], "type": scene["type"], "widgetType": widget,
            "finiteCueCount": len(cue_map), "literalCallCount": len(calls),
            "cueIds": sorted(cue_map),
            "pictureGraphicCount": len(graphics), "videoCount": video_count,
            "videoSources": video_sources,
            "rendererStructure": ("three_scene_graph" if three_renderer else "native_webgl_mesh" if native_renderer
                                  else "unverified") if widget == "visualization3d" else None,
            "htmlSha256": hashlib.sha256(source.encode()).hexdigest()})
    if set(expected) - seen:
        issues.append("frozen_cues_missing_from_saved_courseware")
    for widget in ("game", "visualization3d"):
        if widget not in widgets:
            issues.append("required_widget_missing:" + widget)
    if design.get("sceneCount") is not None and len(classroom.get("scenes", [])) != design["sceneCount"]:
        issues.append("frozen_scene_count_changed")
    if frozen["kind"] != "book_exploration" and not any(scene["videoCount"] for scene in scene_reports):
        issues.append("actual_video_observation_missing_before_audio")
    mapped_scenes = set()
    def references(value):
        found = set()
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower().endswith("cueid") and isinstance(child, str):
                    found.add(child)
                else:
                    found.update(references(child))
        elif isinstance(value, list):
            for child in value:
                found.update(references(child))
        return found
    for planned in design.get("scenes", []):
        cue_ids = references(planned)
        planned_id = str(planned.get("sceneId", "unknown"))
        matches = [scene for scene in scene_reports if cue_ids and cue_ids <= set(scene["cueIds"])]
        if len(matches) != 1:
            issues.append("design_scene_exact_cue_coverage_missing_or_ambiguous:" + planned_id)
            continue
        actual = matches[0]
        if actual["sceneId"] in mapped_scenes:
            issues.append("design_scenes_combined_instead_of_independent:" + planned_id)
        mapped_scenes.add(actual["sceneId"])
        if (planned.get("type", "interactive") != actual["type"]
                or planned.get("widgetType") != actual["widgetType"]):
            issues.append("design_scene_type_or_widget_changed:" + planned_id)
        required_video = planned.get("requiredVideoElement")
        required_src = required_video.get("src") if isinstance(required_video, dict) else None
        required_local = (re.fullmatch(r"/api/classroom-media/([A-Za-z0-9_-]{1,128})/(.+)", required_src)
                          if isinstance(required_src, str) else None)
        required_video_role = bool(isinstance(required_src, str) and required_src
            and required_src == required_src.strip()
            and (required_src in provided_sources or (required_local
                and required_local[1] == classroom["id"]
                and not urlparse(required_src).query and not urlparse(required_src).fragment)))
        if required_src and not required_video_role:
            issues.append("design_required_video_source_invalid:" + planned_id)
        if required_video_role and required_src not in actual["videoSources"]:
            issues.append("design_required_video_source_not_exactly_present:" + planned_id)
        video_role = bool(planned.get("videoSrc") or planned.get("videoStoryboard")
                          or "video" in planned_id.lower() or planned.get("observations")
                          or required_video_role)
        if video_role and not actual["videoCount"]:
            issues.append("design_actual_video_scene_missing:" + planned_id)
        if not video_role and planned.get("widgetType") == "game" and actual["videoCount"]:
            issues.append("design_independent_game_or_route_replaced_with_video:" + planned_id)
        route_nodes = planned.get("nodes", planned.get("entries", []))
        if route_nodes and any(isinstance(node, dict) and node.get("nodeId") for node in route_nodes):
            source = html_by_id[actual["sceneId"]]
            if actual["pictureGraphicCount"] < len(route_nodes):
                issues.append("design_route_distinct_picture_entries_missing:" + planned_id)
            if any(node.get("nodeId", "") not in source or node.get("title", "") not in source
                   for node in route_nodes if isinstance(node, dict)):
                issues.append("design_route_exact_node_ids_or_titles_missing:" + planned_id)
    return {"schemaVersion": "mira.textbook.queue-audio-structural-review.v1",
        "taskId": frozen["taskId"], "inputSha256": frozen["inputSha256"],
        "classroomSha256": digest(classroom), "issues": sorted(set(issues)), "scenes": scene_reports,
        "structuralChecksPassed": not issues, "semanticTeachingReview": "pending",
        "pictureMeaningAndMaskedTextReview": "pending", "actualTouchAndBrowserReview": "pending",
        "browserQAPassed": False, "publicationAllowed": False}


class _GetOnlyAudioRuntime:
    def __init__(self, runtime, output):
        self.runtime, self.output, self.base_url = runtime, output, runtime.base_url

    def __getattr__(self, name):
        original = getattr(self.runtime, name)
        if name in {"start_formal_audio_tts", "start_formal_audio_asr"}:
            def forbidden(**_kwargs):
                raise RuntimeError("audio_unknown_never_reposted")
            return forbidden
        if name in {"get_formal_audio_tts", "get_formal_audio_asr"}:
            def existing_only(identity):
                if not (self.output / (identity + ".json")).is_file():
                    raise RuntimeError("audio_get_only_reconciled_explicit_continue_required")
                return original(identity)
            return existing_only
        return original


class TextbookBatchQueueAudioService:
    def __init__(self, queue, *, classroom_directory=DEFAULT_CLASSROOM_DIRECTORY):
        self.queue, self.classroom_directory = queue, Path(classroom_directory)

    @contextmanager
    def _lock(self):
        with (self.queue.directory / "audio-queue.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("queue_audio_operator_already_running") from exc
            yield

    def narrate(self, *, limit=1, filters=None, continue_audio=False):
        if not 1 <= limit <= 24 or self.queue.runtime is None:
            raise ValueError("queue_audio_runtime_and_bounded_limit_required")
        with self._lock():
            manifest = self.queue._manifest()
            if shutil.disk_usage(self.queue.directory).free < self.queue.minimum_free_bytes:
                return []
            results = []
            for row in self.queue._inventory():
                if not self.queue._matches(row, filters):
                    continue
                generation = self.queue._state(row, manifest)
                if generation["status"] != "generated_needs_review":
                    continue
                folder = self.queue.drafts / row["taskId"]
                path, output = folder / "audio-state.json", folder / "audio-audit"
                previous = document(path) if path.exists() else None
                if previous and previous.get("status") in {"audio_blocked", "audio_completed_needs_review"}:
                    continue
                if previous and previous.get("status") == "audio_waiting_explicit_continue" and not continue_audio:
                    continue
                self.queue._space()
                try:
                    frozen, generation, classroom = load_candidate(folder)
                    if generation["runtimeOrigin"] != self.queue.runtime.base_url:
                        raise ValueError("queue_audio_runtime_changed")
                    review = structural_review(folder, self.classroom_directory)
                except Exception as exc:
                    if previous:
                        raise ValueError("queue_prior_audio_candidate_validation_failed") from exc
                    # A malformed new candidate is a per-task block, not a
                    # reason to silently skip it or stop all other textbooks.
                    state = {"schemaVersion": SCHEMA, "status": "audio_blocked",
                        "bound": {"taskId": row["taskId"], "inputSha256": generation["inputSha256"],
                                  "classroomSha256": generation["classroomSha256"]},
                        "safeErrorCode": "candidate_identity_or_static_validation_failed",
                        "errorType": type(exc).__name__, "publicationAllowed": False,
                        "studentDeliveryAllowed": False, "browserQAPassed": False, "previewReady": False}
                    atomic_json(path, state)
                    results.append(state)
                    if len(results) >= limit:
                        break
                    continue
                plan = build_audio_plan(classroom, frozen["binding"], self.queue.runtime.base_url)
                inheritance_path = output / "inheritance-manifest.json"
                inheritance = normalize_audio_inheritance(document(inheritance_path)) if inheritance_path.exists() else None
                bound = {"taskId": row["taskId"], "inputSha256": frozen["inputSha256"],
                    "classroomSha256": digest(classroom), "planSha256": digest(plan),
                    "structuralReviewSha256": digest(review), "runtimeOrigin": self.queue.runtime.base_url,
                    "inheritanceSetSha256": digest(inheritance) if inheritance else None}
                if previous and (previous.get("schemaVersion") != SCHEMA or previous.get("bound") != bound
                        or previous.get("publicationAllowed") is not False):
                    raise ValueError("queue_audio_frozen_state_changed")
                atomic_json(folder / "audio-structural-review.json", review, immutable=True)
                state = {"schemaVersion": SCHEMA, "bound": bound, "status": "narrating",
                    "publicationAllowed": False, "studentDeliveryAllowed": False,
                    "browserQAPassed": False, "previewReady": False, "maximumConcurrentAudioTasks": 1}
                if not review["structuralChecksPassed"]:
                    state.update(status="audio_blocked", safeErrorCode="structural_review_failed",
                                 issues=review["issues"])
                    atomic_json(path, state)
                    results.append(state)
                else:
                    # A crash without an audio-state update is also fenced by
                    # the existing per-request durable audio checkpoints.
                    getter_only = previous is not None and not continue_audio
                    if previous is None and output.exists() and any(output.glob("tbb*.json")):
                        getter_only = True
                    state["resumeMode"] = "get_only" if getter_only else "existing_workload_authorized"
                    atomic_json(path, state)
                    runtime = _GetOnlyAudioRuntime(self.queue.runtime, output) if getter_only else self.queue.runtime
                    try:
                        audit = narrate_candidate(runtime, classroom, frozen["binding"], output,
                                                  self.classroom_directory, audio_inheritance=inheritance)
                        if (audit.get("allSegmentsPassed") is not True
                                or audit.get("expectedSegments") != len(plan["workload"])
                                or audit.get("completedSegments") != len(plan["workload"])
                                or len(audit.get("segments", [])) != len(plan["workload"])
                                or audit.get("planSha256") != digest(plan)
                                or audit.get("sha256") != digest({key: value for key, value in audit.items() if key != "sha256"})
                                or not (output / "audit.json").is_file()
                                or document(output / "audit.json") != audit
                                or any(segment.get("similarityBps", 0) < 8500 for segment in audit.get("segments", []))):
                            raise ValueError("queue_audio_completed_audit_mismatch")
                        state.update(status="audio_completed_needs_review", completedSegments=audit["completedSegments"],
                            expectedSegments=audit["expectedSegments"], auditSha256=digest(audit),
                            semanticPronunciationReview="pending", interactiveStateNarrationReview="pending")
                    except Exception as exc:
                        code = str(exc)
                        status = ("audio_waiting_explicit_continue" if code == "audio_get_only_reconciled_explicit_continue_required"
                                  else "audio_blocked" if any(fragment in code for fragment in (
                                      "semantic_review_required", "transcript_recovery_required", "_failed_no_retry",
                                      "changed", "mismatch", "identity_conflict")) else "audio_unknown_needs_reconciliation")
                        state.update(status=status, safeErrorCode="audio_stopped_without_retry",
                                     errorType=type(exc).__name__)
                        audit_path = output / "audit.json"
                        if audit_path.exists():
                            audit = document(audit_path)
                            state.update(completedSegments=audit.get("completedSegments", 0),
                                         expectedSegments=audit.get("expectedSegments", len(plan["workload"])))
                    state["updatedAt"] = int(time.time() * 1000)
                    atomic_json(path, state)
                    results.append(state)
                if len(results) >= limit:
                    break
            return results
