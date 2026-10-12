"""Compile a reviewed provider blueprint using exact narration and raster art.

No model calls, inferred teaching copy, student writes or publication occur
here. Missing pictures, unsupported interactions and absent video are errors.
"""
import hashlib
import math
from pathlib import Path

from content import textbook_deepseek_activity as renderer
from content import textbook_activity_templates as shared
from content.teacher_profiles import get_formal_runtime_teacher_contract
from content.textbook_batch_generation import freeze_input
from content.textbook_catalog import canonical, digest
from content.textbook_deepseek_release import CONTRACT
from content.textbook_interactive_narration import interactive_cues
from content.textbook_provided_media import validate_provided_media, STORE_ROOT
from content.textbook_release_media import media_mime_type
from services.textbook_activity_compiler import ROOT, _write_exact
from services.textbook_batch_generation_service import TextbookBatchGenerationService
from services.textbook_deepseek_authoring import read, sha, require, check_blueprint, resolve_blueprint


def compile_pages(task_path, scope_path, job_directory, asset_review_path, output):
    task_path, scope_path, job_directory, asset_review_path, output = map(lambda p: Path(p).resolve(),
        (task_path, scope_path, job_directory, asset_review_path, output))
    require(output.is_relative_to(ROOT / "output"), "compiler_owned_output_required")
    task, scope = read(task_path), read(scope_path)
    request, response = read(job_directory / "request.json"), read(job_directory / "response.json")
    require(request["requestSha256"] == digest({k: v for k, v in request.items() if k != "requestSha256"})
            and request["taskId"] == task["taskId"] and request["source"]["binding"] == task["scope"],
            "compiler_provider_binding_changed")
    for path, expected in request["sourceFiles"].items():
        require(sha(path) == expected, "compiler_source_bytes_changed")
    blueprint = resolve_blueprint(request, response)
    check_blueprint(blueprint, request["source"])
    review = read(asset_review_path)
    require(review.get("schemaVersion") == "mira.textbook.deepseek-assets-review.v1"
            and review.get("taskId") == task["taskId"] and review.get("blueprintSha256") == digest(blueprint)
            and review.get("status") == "reviewed_for_compilation" and review.get("reviewer"),
            "compiler_reviewed_picture_mapping_required")
    modules = [Path(__file__), Path(renderer.__file__), Path(shared.__file__), Path(renderer.__file__).with_name("textbook_role_garden.js")]
    implementation = {str(p): sha(p) for p in modules}
    identity = "dsbook_" + task["taskId"][:16] + "_" + digest({
        "blueprint": blueprint, "assets": review, "implementation": implementation})[:8]
    images = {}
    copies = []
    from PIL import Image
    for key, asset in review.get("images", {}).items():
        path = Path(asset["path"]).resolve()
        require(path.is_relative_to(ROOT / "output") or path.is_relative_to(ROOT / "backend/content/textbooks/lesson-media-v1"),
                "compiler_image_owner_required")
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == asset["sha256"], "compiler_image_changed")
        require(media_mime_type(path.suffix, raw).startswith("image/"), "compiler_bitmap_required")
        with Image.open(path) as source:
            width, height = source.size
        crop = asset.get("crop", [0, 0, 1, 1])
        require(len(crop) == 4 and all(type(x) in (int, float) and math.isfinite(x) for x in crop)
                and 0 <= crop[0] < 1 and 0 <= crop[1] < 1 and crop[2] > 0 and crop[3] > 0
                and crop[0]+crop[2] <= 1.00000001 and crop[1]+crop[3] <= 1.00000001
                and isinstance(asset.get("description"), str) and asset["description"], "compiler_image_view_invalid")
        name = asset["sha256"] + path.suffix
        images[key] = {"src": f"/api/classroom-media/{identity}/media/{name}", "sha256": asset["sha256"],
            "width": width, "height": height, "crop": crop, "description": asset["description"]}
        copies.append((STORE_ROOT / identity / "media" / name, raw))
    provided = review.get("providedMediaAssets", [])
    validate_provided_media({"providedMediaAssets": provided}, task_id=task["taskId"], binding=task["scope"])
    video_by_id = review.get("videoMediaIds", {})
    video_by_asset = {a["assetId"]: a for a in provided}
    activities = {a["activityId"]: (i, a) for i, a in enumerate(blueprint["activities"])}
    scenes, origins = [], []

    def cue(scene, value, pointer, activity_id):
        if not value:
            return None
        require(isinstance(value, str), "compiler_spoken_string_required")
        # Identical controls in one scene may share audio; each activity's actual
        # explanation retains its own provenance even if the words repeat.
        if not (pointer.startswith("/activities/") and pointer.count("/") == 3 and pointer.endswith("/teacherText")):
            reused = next((c for c in scene["finiteCues"] if c["teacherText"] == value), None)
            if reused:
                return reused["cueId"]
        cue_id = "ds_" + hashlib.sha256((scene["sceneId"]+pointer).encode()).hexdigest()[:22]
        scene["finiteCues"].append({"cueId": cue_id, "teacherText": value})
        origins.append({"cueId": cue_id, "sceneId": scene["sceneId"], "activityId": activity_id,
                        "method": "deepseek_exact", "pointer": pointer})
        return cue_id

    def image_key(activity_id, role, suggested=None):
        key = review.get("activityImages", {}).get(activity_id, {}).get(role, suggested)
        require(key in images, "compiler_missing_picture:"+activity_id+":"+role)
        return key

    def glyph_overlays(activity_id, role):
        overlays = review.get("glyphOverlays", {}).get(activity_id, {}).get(role, [])
        known = scope.get("recognizedCharacters", [])
        require(isinstance(overlays, list) and len(overlays) <= 3, "compiler_glyph_overlay_shape")
        for item in overlays:
            require(isinstance(item, dict) and set(item) == {"character", "x", "y"}
                    and isinstance(item["character"], str) and len(item["character"]) == 1
                    and item["character"] in known
                    and all(type(item[k]) in (int, float) and math.isfinite(item[k]) and .05 <= item[k] <= .95
                            for k in ("x", "y")), "compiler_glyph_overlay_requires_known_character_and_position")
        return overlays

    for session_index, session in enumerate(blueprint["lessonPlan"]["sessions"]):
        group = None
        for activity_id in session["activityIds"]:
            index, activity = activities[activity_id]
            interaction, visual = activity["interaction"], activity["visual"]
            kind, base = interaction["type"], f"/activities/{index}"
            require(kind in {"observe", "choose_picture", "oral_response", "model_3d"}, "compiler_unsupported_interaction")
            if group is None or kind == "model_3d" or len(group.get("pages", [])) >= 6:
                group = {"sceneId": f"ds_{task['taskId'][:10]}_{len(scenes)+1}", "title": session["title"],
                         "widgetType": "visualization3d" if kind == "model_3d" else "game",
                         "renderer": "deepseek_role_garden" if kind == "model_3d" else "deepseek_picture_pages",
                         "pages": [], "activityGoalIds": [], "finiteCues": []}
                scenes.append(group)
            group["activityGoalIds"] = sorted(set(group["activityGoalIds"]) | set(activity["goalIds"]))
            teacher = cue(group, activity["teacherText"], base+"/teacherText", activity_id)
            prompt = cue(group, interaction.get("spokenPrompt"), base+"/interaction/spokenPrompt", activity_id)
            if kind == "model_3d":
                models = blueprint["mediaDesign"]["threeD"]
                model_index = next((i for i, m in enumerate(models) if m["id"] == interaction.get("mediaId")), None)
                require(model_index is not None, "compiler_three_d_identity")
                model = models[model_index]
                configs = []
                for n, configuration in enumerate(model.get("roleConfigurations", [])):
                    own = {k: configuration[k] for k in ("speakerCharacterId", "listenerCharacterId", "thirdCharacterId")}
                    require(set(own.values()) == {"coral", "teal", "yellow"} and own["thirdCharacterId"] != "coral", "compiler_three_d_roles")
                    pointer = f"/mediaDesign/threeD/{model_index}/roleConfigurations/{n}"
                    own.update(portraitAssetKey=image_key(activity_id, "portrait_"+own["speakerCharacterId"], "portrait_"+own["speakerCharacterId"]),
                        teacherCueId=cue(group, configuration["teacherText"], pointer+"/teacherText", activity_id),
                        questionCueId=cue(group, configuration["questionText"], pointer+"/questionText", activity_id),
                        modelCueId=cue(group, configuration["modelAnswer"], pointer+"/modelAnswer", activity_id))
                    configs.append(own)
                require(len(configs) == 3 and len({r["speakerCharacterId"] for r in configs}) == 3, "compiler_three_d_configurations")
                group["roleModel"] = {"teacherCueId": teacher, "promptCueId": prompt, "configurations": configs,
                    "completeCueId": cue(group, interaction.get("completionTeacherText"),
                                         base+"/interaction/completionTeacherText", activity_id)}
                group["roleModel"] = {k: v for k, v in group["roleModel"].items()
                                      if not (k.endswith("CueId") and v is None)}
                group = None
                continue
            page = {"pageId": f"{group['sceneId']}_{activity_id}", "activityId": activity_id,
                "kind": kind, "assetKey": image_key(activity_id, "main", visual.get("assetKey")),
                "glyphOverlays": glyph_overlays(activity_id, "main"),
                "targetCharacters": visual.get("targetCharacters", []), "teacherCueId": teacher,
                "promptCueId": prompt, "choices": [], "correctChoiceIds": interaction.get("correctChoiceIds", [])}
            page["hideMainArt"] = review.get("activityLayouts", {}).get(activity_id, {}).get("hideMainArt", False)
            require(type(page["hideMainArt"]) is bool and (not page["hideMainArt"] or
                    (kind == "choose_picture" and len(interaction.get("choices", [])) >= 2 and page["targetCharacters"])),
                    "compiler_picture_choice_layout_invalid")
            for field, source_field in (("retryCueId", "retryTeacherText"), ("completeCueId", "completionTeacherText"), ("modelCueId", "modelAnswer")):
                page[field] = cue(group, interaction.get(source_field), base+"/interaction/"+source_field, activity_id)
            for number, choice in enumerate(interaction.get("choices", [])):
                key = image_key(activity_id, choice["choiceId"], choice.get("assetKey") or choice.get("existingAssetId"))
                page["choices"].append({"choiceId": choice["choiceId"], "assetKey": key,
                    "glyphOverlays": glyph_overlays(activity_id, choice["choiceId"]),
                    "buttonId": page["pageId"]+"_"+choice["choiceId"],
                    "feedbackCueId": cue(group, choice["feedbackText"], base+f"/interaction/choices/{number}/feedbackText", activity_id)})
            # Shuffle only presentation order, preserving choice identities and answer mappings.
            page["choices"].sort(key=lambda c: digest([task["taskId"], activity_id, c["choiceId"]]))
            media_id = interaction.get("mediaId")
            if media_id:
                asset = video_by_asset.get(video_by_id.get(media_id))
                require(asset is not None, "compiler_actual_video_required")
                video_index = next((i for i, v in enumerate(blueprint["mediaDesign"]["video"]) if v["id"] == media_id), None)
                require(video_index is not None, "compiler_video_design_missing")
                elapsed, shots = 0, []
                for shot_index, shot in enumerate(blueprint["mediaDesign"]["video"][video_index]["shots"]):
                    shots.append({"start": elapsed, "end": elapsed+shot["seconds"],
                        "cueId": cue(group, shot["teacherText"], f"/mediaDesign/video/{video_index}/shots/{shot_index}/teacherText", activity_id)})
                    elapsed += shot["seconds"]
                page["videoSrc"] = asset["src"]
                page["videoShots"] = shots
                group["requiredVideoElement"] = {"src": asset["src"]}
            group["pages"].append({k: v for k, v in page.items() if not (k.endswith("CueId") and v is None)})

    design = {"schemaVersion": "mira.textbook.activity-design.v1", "status": "draft", "publicationAllowed": False,
        "taskId": task["taskId"], "kind": task["kind"], "binding": task["scope"], "manifestSha256": task["manifestSha256"],
        "title": blueprint["title"], "lessonFamily": "deepseek_picture_book_v1", "sceneCount": len(scenes), "scenes": scenes,
        "designInstructions": "Exact provider text and reviewed original raster assets; private until content, audio and browser review.",
        "compiledImageAssets": images, "providedMediaAssets": provided,
        "finiteCues": [c for scene in scenes for c in scene["finiteCues"]],
        "deepseekAuthoring": {"schemaVersion": CONTRACT, "requestPath": str(job_directory / "request.json"),
            "requestByteSha256": sha(job_directory / "request.json"), "responsePath": str(job_directory / "response.json"),
            "responseByteSha256": sha(job_directory / "response.json"), "blueprintSha256": digest(blueprint), "cueOrigins": origins}}
    output.mkdir(parents=True, exist_ok=True)
    design_path = output / "design.json"
    _write_exact(design_path, (canonical(design)+'\n').encode())
    frozen = freeze_input(task, reviewed_scope_path=scope_path, design_plan_path=design_path, enrich_existing=True)
    state = TextbookBatchGenerationService(output / "prepared").prepare(frozen)
    teacher = frozen["runtimeBatchContext"]["teacher"]
    runtime = get_formal_runtime_teacher_contract(task["scope"]["subject"])["runtime"]
    now = state["createdAt"]
    room = {"id": identity, "createdAt": now, "stage": {"id": identity, "name": blueprint["title"],
        "style": "interactive", "createdAt": now, "updatedAt": now, "generatedAgentConfigs": [{
            "id": identity+"_teacher", "name": teacher["teacherName"], "role": "teacher", "avatar": runtime["avatar"],
            "teacherProfile": teacher["teacherProfile"], "voiceConfig": runtime["voiceConfig"], "priority": 10}]}, "scenes": []}
    for n, scene in enumerate(scenes):
        html = renderer.role_scene(scene, images) if scene["renderer"] == "deepseek_role_garden" else renderer.pages_scene(scene, images)
        require(interactive_cues(html) == [{"id": c["cueId"], "text": c["teacherText"]} for c in scene["finiteCues"]], "compiler_cue_drift")
        room["scenes"].append({"id": scene["sceneId"], "outlineId": "outline_"+scene["sceneId"], "stageId": identity,
            "type": "interactive", "title": scene["title"], "order": n, "content": {"type": "interactive",
                "widgetType": scene["widgetType"], "html": html}, "actions": [], "createdAt": now, "updatedAt": now})
    for target, raw in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_exact(target, raw)
    folder = output / "candidates" / task["taskId"]
    folder.mkdir(parents=True, exist_ok=True)
    generated = {**state, "status": "generated_needs_review", "classroomId": identity, "classroomSha256": digest(room),
        "runtimeOrigin": "http://127.0.0.1:3100", "authoringMode": "deepseek_blueprint_local_compilation",
        "sourceGenerationStatus": "deepseek_response_preserved", "sourceGenerationJobId": response["id"],
        "qualityPassed": False, "browserQAPassed": False, "sourceNodeEntirelyCovered": False,
        "outstandingGoalIds": scope.get("outstandingGoalIds", [])}
    for name, value in (("input.json", frozen), ("state.json", generated), ("classroom.json", room)):
        _write_exact(folder/name, (canonical(value)+'\n').encode())
    _write_exact(folder/"derivation.json", (canonical({"schemaVersion": "mira.textbook.deepseek-compiler.v1",
        "requestSha256": request["requestSha256"], "responseId": response["id"], "blueprintSha256": digest(blueprint),
        "sourceFiles": {str(p): sha(p) for p in [task_path, scope_path, asset_review_path, *modules]},
        "classroomSha256": digest(room), "publicationAllowed": False})+'\n').encode())
    return {"candidateDirectory": str(folder), "sceneCount": len(scenes), "activityCount": len(activities),
            "cueCount": len(design["finiteCues"]), "publicationAllowed": False}
