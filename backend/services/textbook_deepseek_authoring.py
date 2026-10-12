"""Durable, single-dispatch DeepSeek instructional design over verified sources.

This authoring stage never publishes, calls TTS, executes model code, or silently
falls back to a local outline. An incomplete/unknown paid response stays fenced.
"""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from content.textbook_batch_generation import freeze_input
from content.textbook_catalog import digest
from services.textbook_batch_generation_service import atomic_json

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / "backend/prompts/textbook-deepseek-instruction.v2.json"
PATCH_PROMPT = ROOT / "backend/prompts/textbook-deepseek-revision.v1.json"
ENV = ROOT / "openmaic-runtime/.env"
BLUEPRINT_SCHEMA = "mira.textbook.deepseek-instruction-blueprint.v1"
STAGES = ("explanation", "demonstration", "guidedPractice", "transfer", "feedback", "retrieval")
PATCH_SCHEMA = "mira.textbook.deepseek-instruction-patch.v1"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError("deepseek_authoring_" + message)


def apply_reviewed_patch(blueprint, patch, allowed_paths):
    """Replace only model-returned values at exact, previously reviewed paths."""
    require(patch.get("schemaVersion") == PATCH_SCHEMA
            and patch.get("parentBlueprintSha256") == digest(blueprint), "patch_parent_changed")
    operations = patch.get("operations", [])
    require(isinstance(operations, list) and len(operations) == len(allowed_paths)
            and len(set(allowed_paths)) == len(allowed_paths)
            and {op.get("path") for op in operations} == set(allowed_paths), "patch_review_coverage")
    result = deepcopy(blueprint)
    for operation in operations:
        path = operation["path"]
        require(operation.get("op") == "replace" and set(operation) == {"op", "path", "value"}
                and path.split("/")[1] in {"activities", "goalEvidence", "mediaDesign", "lessonPlan"},
                "patch_content_only")
        tokens = [t.replace("~1", "/").replace("~0", "~") for t in path[1:].split("/")]
        parent = result
        try:
            for token in tokens[:-1]:
                parent = parent[int(token)] if isinstance(parent, list) else parent[token]
            key = int(tokens[-1]) if isinstance(parent, list) else tokens[-1]
            previous = parent[key]
            require(type(previous) is type(operation["value"]), "patch_value_type_changed")
            parent[key] = deepcopy(operation["value"])
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise ValueError("deepseek_authoring_patch_path_invalid") from exc
    return result


def patch_targets(blueprint, paths):
    """Show the actual activity identity beside each exact zero-based pointer."""
    require(isinstance(paths, list) and paths and len(set(paths)) == len(paths), "patch_target_paths")
    targets = []
    for path in paths:
        require(isinstance(path, str) and path.startswith("/")
                and path.split("/")[1] in {"activities", "goalEvidence", "mediaDesign", "lessonPlan"},
                "patch_target_content_only")
        tokens = [t.replace("~1", "/").replace("~0", "~") for t in path[1:].split("/")]
        value = blueprint
        try:
            for token in tokens:
                value = value[int(token)] if isinstance(value, list) else value[token]
            target = {"path": path, "currentValue": deepcopy(value)}
            if tokens[0] == "activities":
                require(len(tokens) >= 3, "patch_whole_activity_forbidden")
                activity = blueprint["activities"][int(tokens[1])]
                target["activityContext"] = deepcopy(activity)
            targets.append(target)
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            raise ValueError("deepseek_authoring_patch_target_missing") from exc
    return targets


def resolve_blueprint(request, response, *, depth=0):
    """Rebuild from immutable provider responses, never a locally edited draft."""
    # Small field revisions can legitimately exceed twelve saved responses.
    # Walk iteratively while retaining every byte, identity and patch check.
    require(type(depth) is int and 0 <= depth < 256, "lineage_depth_invalid")
    pending, seen = [], set()
    while True:
        identity = request.get("requestSha256")
        require(identity == digest({k: v for k, v in request.items() if k != "requestSha256"})
                and identity not in seen and len(seen) + depth < 256,
                "patch_lineage_identity_changed")
        seen.add(identity)
        require(response.get("model", "").startswith("deepseek-v4-pro")
                and response.get("choices", [{}])[0].get("finish_reason") == "stop",
                "lineage_complete_response_required")
        value = json.loads(response["choices"][0]["message"]["content"])
        if request.get("purpose") != "reviewed_content_patch":
            break
        paths = request["patchParent"]
        documents = []
        for key in ("requestPath", "responsePath", "reviewPath"):
            path = Path(paths[key]).resolve()
            require(str(path) in request["sourceFiles"] and sha(path) == request["sourceFiles"][str(path)],
                    "patch_lineage_bytes_changed")
            documents.append(read(path))
        previous, envelope, review = documents
        require(previous["requestSha256"] == request["parentRequestSha256"]
                and previous["source"] == request["source"]
                and review["taskId"] == request["taskId"]
                and review["allowedPaths"] == paths["allowedPaths"], "patch_lineage_identity_changed")
        pending.append((value, paths["allowedPaths"]))
        request, response = previous, envelope
    for patch, allowed_paths in reversed(pending):
        value = apply_reviewed_patch(value, patch, allowed_paths)
    return value


def provider_config():
    # Same fixed credential owner as native-runtime.sh; never source shell text.
    values = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    endpoint = values.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    parsed = urlparse(endpoint)
    require(parsed.scheme == "https" and parsed.hostname == "api.deepseek.com"
            and parsed.path in ("", "/v1") and not any((parsed.username, parsed.password, parsed.port,
                parsed.query, parsed.fragment)), "official_provider_endpoint_required")
    require(values.get("DEEPSEEK_SERVICE", "official") == "official", "provider_service_changed")
    model = values.get("MIRA_OPENMAIC_MODEL")
    require(model == "deepseek-v4-pro" and model in values.get("DEEPSEEK_MODELS", "").split(","),
            "configured_deepseek_creator_required")
    key = values.get("DEEPSEEK_API_KEY", "")
    require(bool(key), "provider_not_configured")
    return endpoint, model, key


def check_blueprint(value, source):
    """Structural depth evidence, not a semantic approval or publication gate."""
    require(isinstance(value, dict) and value.get("schemaVersion") == BLUEPRINT_SCHEMA, "blueprint_schema")
    require(value.get("taskId") == source["taskId"] and value.get("binding") == source["binding"], "blueprint_binding")
    require(value.get("outstandingGoalIds") == source["outstandingGoalIds"], "unfinished_goals_changed")
    goals = set(source["activityGoalIds"])
    activities = value.get("activities", [])
    require(isinstance(activities, list) and len(activities) >= len(goals), "teaching_activities_missing")
    by_id = {}
    for activity in activities:
        identity = activity.get("activityId")
        require(isinstance(identity, str) and identity and identity not in by_id, "activity_identity")
        require(isinstance(activity.get("teacherText"), str) and activity["teacherText"].strip(), "actual_narration_missing")
        own = activity.get("goalIds", [])
        require(isinstance(own, list) and own and set(own) <= goals, "activity_goal_changed")
        visual, action = activity.get("visual"), activity.get("interaction")
        require(isinstance(visual, dict) and isinstance(action, dict), "picture_and_action_required")
        require(bool(visual.get("existingAssetIds") or visual.get("newPictureDescription")), "meaningful_picture_required")
        require(action.get("type") in {"observe", "choose_picture", "order_pictures", "drag_match",
            "oral_response", "writing_3d", "model_3d"}, "unsupported_interaction")
        choices = action.get("choices", [])
        require(isinstance(choices, list), "choices_invalid")
        ids = [choice.get("choiceId") for choice in choices]
        require(all(isinstance(i, str) and i for i in ids) and len(ids) == len(set(ids)), "choice_identity")
        if action["type"] in {"choose_picture", "order_pictures", "drag_match"}:
            require(len(choices) >= 2 and all(c.get("pictureDescription") and c.get("feedbackText") for c in choices),
                    "specific_picture_feedback_required")
            require(bool(action.get("spokenPrompt")), "spoken_question_required")
        if action["type"] == "choose_picture":
            require(action.get("correctChoiceIds") and set(action["correctChoiceIds"]) <= set(ids), "answer_identity")
        if action["type"] == "order_pictures":
            require(set(action.get("expectedOrder", [])) == set(ids)
                    and len(action["expectedOrder"]) == len(ids), "order_identity")
        if action["type"] == "oral_response":
            require(action.get("waitForStudentBeforeModel") is True and action.get("spokenPrompt")
                    and action.get("modelAnswer"), "student_attempt_before_model_required")
        by_id[identity] = activity
    evidence = value.get("goalEvidence", [])
    require(isinstance(evidence, list) and {e.get("goalId") for e in evidence} == goals
            and len(evidence) == len(goals), "goal_evidence_missing")
    for item in evidence:
        for stage in STAGES:
            refs = item.get(stage, [])
            require(isinstance(refs, list) and refs and all(ref in by_id
                and item["goalId"] in by_id[ref]["goalIds"] for ref in refs), "goal_evidence_reference")
        require(item.get("coverageExplanation"), "goal_evidence_explanation_missing")
    sessions = value.get("lessonPlan", {}).get("sessions", [])
    scheduled = [i for session in sessions for i in session.get("activityIds", [])]
    require(sessions and set(scheduled) == set(by_id) and len(scheduled) == len(by_id), "lesson_schedule_incomplete")
    media = value.get("mediaDesign", {})
    require(media.get("video") and media.get("threeD"), "instructional_media_missing")
    require(isinstance(value.get("unresolved"), list), "unresolved_list_required")
    return {"activityCount": len(activities), "goalCount": len(goals), "sessionCount": len(sessions),
            "narrationCharacters": sum(len(a["teacherText"]) for a in activities),
            "structurePassed": True, "semanticReviewPassed": False, "publicationAllowed": False}


def make_source(task_path, scope_path, *, pictures_path=None, gap_path=None):
    task, scope = read(task_path), read(scope_path)
    frozen = freeze_input(task, reviewed_scope_path=scope_path, enrich_existing=True)
    evidence = scope.get("evidence", {}).get("pages", [])
    require(evidence and scope.get("activityGoalIds"), "reviewed_source_goals_required")
    for page in evidence:
        require(sha(page["path"]) == page["sha256"], "source_page_changed")
    # Send curriculum observations, not local paths, source code or credentials.
    scope_fields = ("objectives", "knowledgePoints", "priorKnowledge", "excludedTopics", "recognizedCharacters",
                    "writingCharacters", "observedCharacters", "publicDomainText", "sourceNodeEntirelyCovered",
                    "sourcePageRange", "componentObservedCharacters", "visualQualityBrief",
                    "studentRuntimeConstraints", "sourceReadingObservations")
    facts = {key: scope[key] for key in scope_fields if key in scope}
    if scope.get("strokeOrderReference"):
        ref = scope["strokeOrderReference"]
        reference_path = ref.get("path") or ref.get("referencePath") or ref.get("sourcePath")
        reference_sha = ref.get("byteSha256") or ref.get("referenceSha256") or ref.get("sourceSha256")
        require(reference_path and reference_sha and sha(reference_path) == reference_sha, "stroke_reference_changed")
        facts["strokeOrderReference"] = {key: ref[key] for key in ("standard", "characters") if key in ref}
    pictures = []
    if pictures_path:
        assets = read(pictures_path)
        if isinstance(assets, dict):
            assets = assets.get("assetPlan", assets.get("assets", []))
        from xml.etree.ElementTree import fromstring
        for asset in assets:
            svg = asset.get("svgMarkup", "")
            require(hashlib.sha256(svg.encode()).hexdigest() == asset["sha256"], "picture_changed")
            root = fromstring(svg)
            pictures.append({"assetId": asset["assetId"], "description": root.get("aria-label")
                or " ".join(root.itertext())[:500]})
    source = {"taskId": task["taskId"], "kind": task["kind"], "binding": task["scope"],
              "manifestSha256": task["manifestSha256"], "directoryScope": frozen["directoryScope"],
              "reviewedFacts": facts, "activityGoalIds": scope["activityGoalIds"],
              "outstandingGoalIds": scope.get("outstandingGoalIds", []),
              "sourcePages": [{k: p[k] for k in ("key", "sha256", "printedPage", "printedPages") if k in p} for p in evidence],
              "teacher": frozen["runtimeBatchContext"]["teacher"], "availablePictures": pictures}
    if gap_path:
        gap = read(gap_path)
        source["priorContentGaps"] = {k: gap[k] for k in ("findings", "gaps", "sourceCorrections", "requiredImprovements") if k in gap}
    files = [task_path, scope_path, *([pictures_path] if pictures_path else []), *([gap_path] if gap_path else [])]
    return source, {str(Path(p).resolve()): sha(p) for p in files}


class DeepSeekTextbookAuthoring:
    def __init__(self, directory, *, opener=None):
        self.directory = Path(directory).resolve()
        self.opener = opener or urllib.request.urlopen

    def prepare(self, task_path, scope_path, *, pictures_path=None, gap_path=None):
        source, files = make_source(task_path, scope_path, pictures_path=pictures_path, gap_path=gap_path)
        prompt = read(PROMPT)
        endpoint, model, _ = provider_config()
        payload = {"model": model, "messages": [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": json.dumps({"instructions": prompt["instructions"],
                "outputContract": prompt["outputContract"], "verifiedCurriculum": source}, ensure_ascii=False)}],
            "response_format": {"type": "json_object"}, "thinking": {"type": "enabled"},
            "reasoning_effort": "high", "max_tokens": 65536, "stream": False}
        request = {"schemaVersion": "mira.textbook.deepseek-instruction-request.v1", "providerId": "deepseek",
                   "endpoint": endpoint + "/chat/completions", "taskId": source["taskId"], "source": source,
                   "sourceFiles": files, "promptByteSha256": sha(PROMPT), "payload": payload,
                   "publicationAllowed": False, "automaticRedispatchAllowed": False}
        request["requestSha256"] = digest(request)
        folder = self.directory / source["taskId"] / request["requestSha256"]
        for claim in (self.directory / source["taskId"]).glob("*/dispatch.json"):
            require(claim.parent == folder or (claim.parent / "response.json").exists(),
                    "prior_unknown_dispatch_requires_reconciliation")
        folder.mkdir(parents=True, exist_ok=True)
        atomic_json(folder / "request.json", request, immutable=True)
        return folder

    def prepare_revision(self, parent_directory, review_path):
        """A new, explicitly reviewed request after a fully received response."""
        parent = Path(parent_directory).resolve()
        require(parent.is_relative_to(self.directory), "revision_parent_identity")
        previous = read(parent / "request.json")
        response = read(parent / "response.json")
        require(previous["requestSha256"] == digest({k: v for k, v in previous.items() if k != "requestSha256"})
                and response.get("model", "").startswith("deepseek-v4-pro")
                and response.get("choices", [{}])[0].get("finish_reason") == "stop", "revision_requires_known_complete_response")
        review = read(review_path)
        require(review.get("schemaVersion") == "mira.textbook.deepseek-instruction-revision-review.v1"
                and review.get("taskId") == previous["taskId"]
                and review.get("parentResponseByteSha256") == sha(parent / "response.json")
                and review.get("findings") and review.get("revisionInstructions"), "revision_review_required")
        request = deepcopy(previous)
        request.pop("requestSha256")
        request["sourceFiles"].update({str(parent / "request.json"): sha(parent / "request.json"),
            str(parent / "response.json"): sha(parent / "response.json"), str(Path(review_path).resolve()): sha(review_path)})
        request["parentRequestSha256"] = previous["requestSha256"]
        request["parentResponseByteSha256"] = sha(parent / "response.json")
        request["purpose"] = "known_complete_response_semantic_revision"
        request["payload"]["messages"] = previous["payload"]["messages"][:2] + [
            {"role": "assistant", "content": response["choices"][0]["message"]["content"]},
            {"role": "user", "content": json.dumps({"review": review["findings"],
                "revisionInstructions": review["revisionInstructions"],
                "requirement": "根据具体审核意见生成完整新 JSON。不要仅补目标标签或更改自评，必须真实补齐讲解、具体练习和按错因的反馈。每个 evidence 引用都要实际存在且其活动的 goalIds 包含该目标。"}, ensure_ascii=False)}]
        request["payload"].update(thinking={"type": "enabled"}, reasoning_effort="high", max_tokens=65536)
        request["payload"].pop("temperature", None)
        request["requestSha256"] = digest(request)
        folder = self.directory / request["taskId"] / request["requestSha256"]
        for claim in (self.directory / request["taskId"]).glob("*/dispatch.json"):
            require(claim.parent == folder or (claim.parent / "response.json").exists(),
                    "prior_unknown_dispatch_requires_reconciliation")
        folder.mkdir(parents=True, exist_ok=True)
        atomic_json(folder / "request.json", request, immutable=True)
        return folder

    def prepare_patch(self, parent_directory, review_path):
        parent = Path(parent_directory).resolve()
        require(parent.is_relative_to(self.directory), "patch_parent_identity")
        previous, response, review = read(parent / "request.json"), read(parent / "response.json"), read(review_path)
        blueprint = resolve_blueprint(previous, response)
        require(review.get("schemaVersion") == "mira.textbook.deepseek-patch-review.v1"
                and review.get("taskId") == previous["taskId"]
                and review.get("parentResponseByteSha256") == sha(parent / "response.json")
                and review.get("parentBlueprintSha256") == digest(blueprint)
                and review.get("findings") and review.get("allowedPaths"), "patch_review_required")
        targets = patch_targets(blueprint, review["allowedPaths"])
        prompt = read(PATCH_PROMPT)
        request = deepcopy(previous)
        request.pop("requestSha256")
        request.update(purpose="reviewed_content_patch", parentRequestSha256=previous["requestSha256"],
            parentResponseByteSha256=sha(parent / "response.json"), patchParent={
                "requestPath": str(parent / "request.json"), "responsePath": str(parent / "response.json"),
                "reviewPath": str(Path(review_path).resolve()), "allowedPaths": review["allowedPaths"]})
        request["sourceFiles"].update({str(parent / "request.json"): sha(parent / "request.json"),
            str(parent / "response.json"): sha(parent / "response.json"), str(Path(review_path).resolve()): sha(review_path),
            str(PATCH_PROMPT): sha(PATCH_PROMPT)})
        request["patchPromptByteSha256"] = sha(PATCH_PROMPT)
        request["payload"]["messages"] = [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": json.dumps({"verifiedCurriculum": request["source"], "currentTargets": targets,
                "activityOutline": [{k: a[k] for k in ("activityId", "title", "goalIds", "phase") if k in a}
                                    for a in blueprint["activities"]],
                "reviewFindings": review["findings"], "outputContract": {"schemaVersion": PATCH_SCHEMA,
                    "parentBlueprintSha256": digest(blueprint), "operations": [{"op": "replace", "path": t["path"],
                        "value": "完整修订值，保持 currentValue 的类型"} for t in targets]},
                "instructions": prompt["instructions"]}, ensure_ascii=False)}]
        request["payload"].update(thinking={"type": "enabled"}, reasoning_effort="high", max_tokens=32768)
        request["requestSha256"] = digest(request)
        folder = self.directory / request["taskId"] / request["requestSha256"]
        for claim in (self.directory / request["taskId"]).glob("*/dispatch.json"):
            require(claim.parent == folder or (claim.parent / "response.json").exists(), "prior_unknown_dispatch_requires_reconciliation")
        folder.mkdir(parents=True, exist_ok=True)
        atomic_json(folder / "request.json", request, immutable=True)
        return folder

    @contextmanager
    def _lock(self, folder):
        with (folder / "dispatch.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def run(self, folder):
        folder = Path(folder).resolve()
        require(folder.is_relative_to(self.directory), "output_identity")
        with self._lock(folder):
            request = read(folder / "request.json")
            require(request["requestSha256"] == digest({k: v for k, v in request.items() if k != "requestSha256"}),
                    "request_changed")
            for path, expected in request["sourceFiles"].items():
                require(sha(path) == expected, "source_input_changed")
            claim = folder / "dispatch.json"
            response_path = folder / "response.json"
            if claim.exists():
                if response_path.exists():
                    return self.reconcile(folder)
                return {"taskId": request["taskId"], "status": "outcome_unknown_fenced", "providerCallsThisRun": 0}
            endpoint, model, key = provider_config()
            require(request["endpoint"] == endpoint + "/chat/completions"
                    and request["payload"]["model"] == model, "provider_changed")
            dispatch = {"requestSha256": request["requestSha256"], "attemptedAt": int(time.time() * 1000),
                        "providerId": "deepseek", "modelId": model, "automaticRedispatchAllowed": False}
            # Exclusive fsync before POST; even a crash before sending stays fenced.
            with claim.open("x") as stream:
                stream.write(json.dumps(dispatch, ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            http = urllib.request.Request(request["endpoint"],
                data=json.dumps(request["payload"], ensure_ascii=False).encode(), method="POST",
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
            try:
                with self.opener(http, timeout=900) as response:
                    raw = response.read(8 * 1024**2 + 1)
                with response_path.open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
            except Exception as exc:
                error = {"status": "outcome_unknown_fenced", "errorType": type(exc).__name__,
                         "httpStatus": getattr(exc, "code", None), "automaticRedispatchAllowed": False}
                if isinstance(exc, urllib.error.HTTPError):
                    with (folder / "http-error-response.bin").open("xb") as stream:
                        stream.write(exc.read(1024 * 1024))
                    error["status"] = "http_error_preserved_no_automatic_retry"
                atomic_json(folder / "dispatch-error.json", error, immutable=True)
                return {"taskId": request["taskId"], **error, "providerCallsThisRun": 1}
            return {**self.reconcile(folder), "providerCallsThisRun": 1}

    def reconcile(self, folder):
        folder = Path(folder)
        request = read(folder / "request.json")
        raw = (folder / "response.json").read_bytes()
        receipt = {"schemaVersion": "mira.textbook.deepseek-instruction-receipt.v1", "taskId": request["taskId"],
            "requestSha256": request["requestSha256"], "responseByteSha256": hashlib.sha256(raw).hexdigest(),
            "providerId": "deepseek", "requestedModel": request["payload"]["model"], "publicationAllowed": False}
        try:
            require(len(raw) <= 8 * 1024**2, "response_too_large")
            envelope = json.loads(raw)
            receipt.update(responseId=envelope.get("id"), responseModel=envelope.get("model"), usage=envelope.get("usage"))
            require(envelope.get("model", "").startswith("deepseek-v4-pro"), "response_model_mismatch")
            choice = envelope["choices"][0]
            receipt["finishReason"] = choice.get("finish_reason")
            require(choice.get("finish_reason") == "stop", "response_incomplete")
            raw_blueprint = json.loads(choice["message"]["content"])
            atomic_json(folder / "blueprint.json", raw_blueprint, immutable=True)
            blueprint = resolve_blueprint(request, envelope)
            if request.get("purpose") == "reviewed_content_patch":
                atomic_json(folder / "resolved-blueprint.json", blueprint, immutable=True)
            observations = check_blueprint(blueprint, request["source"])
            receipt.update(status="generated_needs_semantic_review", blueprintSha256=digest(blueprint), **observations)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            receipt.update(status="response_preserved_needs_repair", errorType=type(exc).__name__,
                safeErrorCode=str(exc) if isinstance(exc, ValueError) and str(exc).startswith("deepseek_authoring_")
                else "response_shape_or_json_invalid")
        atomic_json(folder / "receipt.json", receipt, immutable=True)
        return {k: v for k, v in receipt.items() if k not in {"source", "payload"}}
