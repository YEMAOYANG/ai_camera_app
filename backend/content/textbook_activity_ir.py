"""Provider-free, finite input contract for deterministic textbook activities.

This is an authoring contract, not a pedagogy approval. Only named renderer
families are supported. Design HTML/JavaScript examples are never compiled.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from content.textbook_catalog import digest, validate_manifest
from content.textbook_pedagogy import teaching_profile
from content.teacher_profiles import (get_formal_subject_qwen_voice_identity,
                                      get_formal_runtime_teacher_contract)
from content.textbook_provided_media import validate_frozen_provided_media, ROOT as REPOSITORY_ROOT
from content.textbook_activity_models import SUPPORTED
from content import textbook_activity_source_models as source_models
from content.chinese_community_activity import WELL_CUE_KEYS
from content.chinese_food_activity import ZONGZI_CUE_KEYS

SCHEMA = "mira.textbook.activity-ir.v1"
RECIPE_SCHEMA = "mira.textbook.activity-compiler-recipe.v1"
SHA = re.compile(r"[a-f0-9]{64}\Z")
ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
FAMILIES = {
    "abacus_five_independent_beads": ("math", 1),
    "array_tiles_rearrangement": ("math", 2),
    "same_pivot_hinged_angle": ("math", 4),
    "cylinder_cone_mesh_comparison": ("math", 6),
    "round_tip_scissors_hinges": ("science", 2),
    "circuit_board_physical_switch": ("science", 4),
    "lever_beam_same_fulcrum": ("science", 5),
    "bridge_beam_arch_truss": ("science", 6),
    "three_backpacks_handle_opening": ("english", 1),
    "bus_wheels_hinged_door": ("english", 2),
    "cabinet_hinged_door_drawer_cup": ("english", 4),
    "bicycle_frame_pedal_steering": ("english", 6),
    "chinese_paper_boat_and_kite": ("chinese", 2),
    "chinese_well_bucket_scene": ("chinese", 1),
    "chinese_zongzi_layers_scene": ("chinese", 1),
    "chinese_bird_boat_bowl": ("chinese", 3),
    "english_coloured_spheres_and_tray": ("english", 1),
    "english_hinged_umbrella_mesh": ("english", 3),
    "english_colours_semantic_scene": ("english", 1),
    "english_school_semantic_scene": ("english", 2),
    "english_kitchen_semantic_scene": ("english", 4),
    "english_travel_semantic_scene": ("english", 6),
}
FAMILIES.update(source_models.FAMILIES)
STATES = {**SUPPORTED, **source_models.SUPPORTED,
    "chinese_well_bucket_scene": ("high_empty", "low_full", "high_full"),
    "chinese_zongzi_layers_scene": ("wrapped", "open", "rewrapped"),
    "chinese_paper_boat_and_kite": ("boat_near", "boat_turn", "kite_lift"),
    "chinese_bird_boat_bowl": ("bird_near", "wing_turn", "bowl_pair"),
    "english_coloured_spheres_and_tray": ("red", "blue", "yellow"),
    "english_hinged_umbrella_mesh": ("closed", "open", "tilt"),
    "english_colours_semantic_scene": ("red", "blue", "yellow"),
    "english_school_semantic_scene": ("walk", "bike", "bus"),
    "english_kitchen_semantic_scene": ("door", "drawer", "cup"),
    "english_travel_semantic_scene": ("park_bike", "park_bus", "school_bus"),
}


def require(ok, code):
    if not ok:
        raise ValueError("textbook_compiler_" + code)


def byte_sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_svg(source):
    require(isinstance(source, str) and 80 <= len(source) <= 100_000, "svg_invalid")
    require(not re.search(r"<!|<\?|speechSynthesis|miraNarrate", source, re.I), "svg_active_content")
    try:
        tree = ET.fromstring(source)
    except ET.ParseError as exc:
        raise ValueError("textbook_compiler_svg_malformed") from exc
    tags = {"svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
            "title", "desc", "text", "tspan", "defs", "linearGradient", "radialGradient", "stop", "clipPath"}
    require(tree.tag.rsplit("}", 1)[-1] == "svg" and bool(tree.get("viewBox")), "svg_root_invalid")
    geometry = 0
    for node in tree.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        require(tag in tags, "svg_active_element")
        if tag in {"path", "rect", "circle", "ellipse", "line", "polygon", "polyline"}:
            geometry += 1
        for key, value in node.attrib.items():
            key = key.rsplit("}", 1)[-1].lower()
            require(not key.startswith("on") and key not in {"href", "src", "style"}, "svg_active_attribute")
            require(not re.search(r"(?:https?:|javascript:|data:|//)", value, re.I), "svg_external_resource")
            # Only same-document gradient/clip IDs are permitted.
            require(not re.search(r"url\((?!#[A-Za-z0-9_-]+\))", value, re.I), "svg_external_resource")
    require(geometry >= 2, "svg_meaningful_geometry_required")
    return source


def _cues(cues):
    require(isinstance(cues, list) and 0 < len(cues) <= 120, "finite_cues_required")
    result = {}
    for cue in cues:
        require(isinstance(cue, dict) and ID.fullmatch(str(cue.get("cueId", "")))
                and cue["cueId"] not in result and isinstance(cue.get("teacherText"), str)
                and 0 < len(cue["teacherText"].strip()) <= 1000, "finite_cue_invalid")
        require(cue["teacherText"] == cue["teacherText"].strip(), "cue_text_must_be_exact")
        result[cue["cueId"]] = cue["teacherText"]
    return result


def build_ir(frozen, design, *, expected_input_sha, expected_design_sha,
             expected_scope_sha, expected_media_sha, recipe=None):
    """Validate the complete authoring contract before creating any output.

Recipes only supply explicit picture mappings omitted by early frozen unit
designs. They cannot add narration, sources, state logic or executable code.
"""
    require(isinstance(frozen, dict) and isinstance(design, dict), "input_shape")
    require(all(isinstance(v, str) and SHA.fullmatch(v) for v in (
        expected_input_sha, expected_design_sha, expected_scope_sha, expected_media_sha)), "explicit_hashes_required")
    require(frozen.get("schemaVersion") == "mira.textbook.private-batch-generation-input.v1"
            and SHA.fullmatch(str(frozen.get("taskId", "")))
            and frozen.get("inputSha256") == expected_input_sha
            == digest({k: v for k, v in frozen.items() if k != "inputSha256"}), "input_hash_changed")
    require(design == frozen.get("activityDesign") and frozen.get("activityDesignSha256")
            == expected_design_sha == digest(design), "design_hash_changed")
    require(design.get("schemaVersion") == "mira.textbook.activity-design.v1", "design_schema_unsupported")
    require(frozen.get("publicationAllowed") is False and frozen.get("studentDeliveryAllowed") is False
            and design.get("publicationAllowed") is False and design.get("status") == "draft", "private_draft_required")
    require(frozen.get("kind") in {"book_exploration", "unit_guide"}, "unsupported_lesson_semantics")
    binding, manifest = frozen["binding"], validate_manifest(deepcopy(frozen["manifest"]))
    require(frozen["manifestSha256"] == digest(manifest)
            and all(binding.get(k) == manifest[k] for k in (
                "editionId", "revisionId", "gradeCode", "subject", "schoolSystem", "volume")), "textbook_binding_changed")
    require(design.get("binding") == binding and design.get("kind") == frozen["kind"]
            and design.get("manifestSha256") == frozen["manifestSha256"], "design_binding_changed")
    require(manifest["coverage"]["status"] != "index_only" and manifest["units"], "source_directory_missing")
    units = manifest["units"] if frozen["kind"] == "book_exploration" else [
        u for u in manifest["units"] if u["unitId"] == binding.get("unitId")]
    require(bool(units) and binding.get("nodeId") is None
            and (frozen["kind"] != "book_exploration" or binding.get("unitId") is None), "source_scope_invalid")
    directory = [{"unitId": u["unitId"], "title": u["title"], "lessons": [
        {"nodeId": n["nodeId"], "title": n["title"], "sectionTitle": n.get("sectionTitle"), "brief": n["brief"]}
        for n in u["lessons"]]} for u in units]
    require(directory == frozen.get("directoryScope") and digest(directory) == expected_scope_sha, "source_scope_changed")
    require(frozen.get("teachingProfile") == teaching_profile(binding["gradeCode"]), "grade_policy_changed")
    quality = frozen.get("qualityPolicy", {})
    require(quality.get("schemaVersion") == "mira.textbook.courseware-quality-policy.v1"
            and quality.get("policySha256") == digest({k: v for k, v in quality.items() if k != "policySha256"}), "quality_policy_changed")
    original = manifest.get("introduction") if frozen["kind"] == "book_exploration" else units[0].get("introduction")
    task_identity = {"schemaVersion": "mira.learning.textbook-authoring-task.v1", "kind": frozen["kind"],
                     "scope": binding, "manifestSha256": digest(manifest),
                     "teachingProfileSha256": digest(frozen["teachingProfile"]),
                     "qualityPolicySha256": quality["policySha256"], "knowledgeBriefSha256": None,
                     "originalContentSha256": digest(original) if original else None}
    require(frozen.get("originalContent") == original and digest(task_identity) == frozen["taskId"], "task_identity_changed")
    teacher = get_formal_subject_qwen_voice_identity(binding["subject"]).to_target_payload()
    teacher["avatarPath"] = get_formal_runtime_teacher_contract(binding["subject"])["runtime"]["avatar"]
    context = frozen.get("runtimeBatchContext", {})
    require(context.get("teacher") == teacher and context.get("binding") == binding
            and context.get("taskId") == frozen["taskId"] and context.get("kind") == frozen["kind"]
            and context.get("subject") == binding["subject"] and context.get("gradeCode") == binding["gradeCode"], "teacher_context_changed")
    media = validate_frozen_provided_media(frozen)
    require(media and digest(media) == expected_media_sha, "provided_media_hash_changed")
    assets = {}
    for asset in design.get("assetPlan", []):
        key, svg = asset.get("assetId"), asset.get("svgMarkup")
        require(isinstance(key, str) and ID.fullmatch(key) and key not in assets
                and asset.get("sha256") == byte_sha(str(svg).encode())
                and asset.get("containsAnswerText") is not True, "picture_hash_or_identity_changed")
        assets[key] = safe_svg(svg)
    require(3 <= len(assets) <= 160, "original_pictures_required")
    scenes = deepcopy(design.get("scenes"))
    require(isinstance(scenes, list) and len(scenes) == 4
            and len({s.get("sceneId") for s in scenes}) == 4, "exact_four_scene_family_required")
    whole = _cues(design.get("finiteCues")) if len(design.get("finiteCues", [])) <= 120 else {}
    if not whole:
        for chunk in range(0, len(design.get("finiteCues", [])), 100):
            part = _cues(design["finiteCues"][chunk:chunk + 100])
            require(not set(whole) & set(part), "duplicate_global_cue")
            whole.update(part)
    scene_cues = {}
    for scene in scenes:
        require(ID.fullmatch(str(scene.get("sceneId", ""))) and scene.get("type") == "interactive"
                and scene.get("widgetType") in {"game", "visualization3d"}
                and isinstance(scene.get("title"), str) and scene["title"], "scene_identity_invalid")
        cues = _cues(scene.get("finiteCues"))
        require(not set(scene_cues) & set(cues) and all(whole.get(k) == v for k, v in cues.items()), "cross_scene_or_unfrozen_cue")
        scene_cues.update(cues)
        def check_references(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key.lower().endswith("cueid"):
                        require(item in cues if isinstance(item, str) else False, "foreign_scene_cue_reference")
                    else:
                        check_references(item)
            elif isinstance(value, list):
                for item in value:
                    check_references(item)
        check_references(scene)
        if "cueInventoryJSON" in scene:
            try:
                inv = json.loads(scene["cueInventoryJSON"])
            except (ValueError, TypeError) as exc:
                raise ValueError("textbook_compiler_frozen_cue_inventory_invalid") from exc
            require(inv == {"schemaVersion": "mira.interactive.narration-cues.v1",
                           "cues": [{"id": k, "text": v} for k, v in cues.items()]}, "frozen_cue_inventory_mismatch")
    require(scene_cues == whole, "scene_cue_coverage_mismatch")
    video, game, model, route = scenes
    require(video["widgetType"] == game["widgetType"] == route["widgetType"] == "game"
            and model["widgetType"] == "visualization3d", "scene_roles_unsupported")
    videos = {a["src"]: a for a in media}
    require(video.get("requiredVideoElement", {}).get("src") in videos, "exact_video_source_required")
    receipt_path = Path(videos[video["requiredVideoElement"]["src"]]["receiptPath"])
    if not receipt_path.is_absolute():
        receipt_path = REPOSITORY_ROOT / receipt_path
    duration = json.loads(receipt_path.read_text())["probe"]["durationMs"] / 1000
    observations = video.get("observations", [])
    require(len(observations) == 3 and len({o.get("assetId") for o in observations}) == 3
            and all(o.get("assetId") in assets and type(o.get("seekSeconds")) in {int, float}
                    and math.isfinite(o["seekSeconds"]) and 0 <= o["seekSeconds"] < duration for o in observations), "video_observations_invalid")
    mode = {r.get("mode") for r in game.get("rounds", [])}
    require(mode in ({"visible_picture_matching"}, {"spoken_language_picture_matching"}), "unsupported_game_semantics")
    require(len(game["rounds"]) == 3 and len({r.get("roundId") for r in game["rounds"]}) == 3, "three_distinct_game_rounds_required")
    for r in game["rounds"]:
        options = r.get("optionAssetIds", [])
        require(ID.fullmatch(str(r.get("roundId", ""))) and len(options) == len(set(options)) == 3
                and all(k in assets for k in options) and r.get("targetAssetId") in options
                and len({assets[k] for k in options}) == 3, "meaningful_distinct_game_pictures_required")
        require(not r.get("targetCharacter"), "unsupported_character_teaching_game")
    mandatory = [(video, ("initialCueId", "replayCueId", "finishCueId")),
                 (game, ("initialCueId", "retryCueId", "resetCueId", "completeCueId")),
                 (model, ("initialCueId", "retryCueId", "resetCueId", "completeCueId")),
                 (route, ("initialCueId", "finishCueId"))]
    if mode == {"visible_picture_matching"}:
        mandatory.append((game, ("hintCueId",)))
    for scene, keys in mandatory:
        require(all(isinstance(scene.get(key), str) for key in keys), "required_state_cue_missing")
    for r in game["rounds"]:
        require(all(isinstance(r.get(key), str) for key in ("instructionCueId", "matchCueId")), "required_round_cue_missing")
    adapter = model.get("modelAdapterKey")
    require(adapter in FAMILIES, "unsupported_semantic_model_family")
    require(FAMILIES[adapter] == (binding["subject"], int(binding["gradeCode"].split("_")[-1])), "unsupported_family_subject_or_grade")
    require(tuple(s.get("sceneStateId") for s in model.get("states", [])) == STATES[adapter], "model_states_changed")
    require(all(isinstance(s.get("observationCueId"), str) for s in model["states"]), "required_model_cue_missing")
    if adapter == "chinese_well_bucket_scene":
        own = {c["cueId"] for c in model["finiteCues"]}
        require(frozen["kind"] == "unit_guide" and model.get("adapterId") == "well_bucket_lift_v1"
                and all(model.get(key) in own for key in WELL_CUE_KEYS)
                and [s["observationCueId"] for s in model["states"]]
                    == [model["initialCueId"], model["lowerCueId"], model["raiseCueId"]]
                and not any(key in model for key in ("html", "script", "geometry")),
                "well_guide_contract_changed")
    if adapter == "chinese_zongzi_layers_scene":
        own = {c["cueId"] for c in model["finiteCues"]}
        require(frozen["kind"] == "unit_guide" and model.get("adapterId") == "zongzi_layers_v1"
                and all(model.get(key) in own for key in ZONGZI_CUE_KEYS)
                and [s["observationCueId"] for s in model["states"]]
                    == [model["initialCueId"], model["openCueId"], model["closeCueId"]]
                and not any(key in model for key in ("html", "script", "geometry")),
                "zongzi_guide_contract_changed")
    if binding["subject"] == "english" and frozen["kind"] == "unit_guide":
        require(adapter.startswith("english_") and adapter.endswith("_semantic_scene")
                and mode == {"spoken_language_picture_matching"} and design.get("originalLanguageIntroduction"), "english_language_task_required")
    mappings = {"routeAssetIds": {}, "modelStateAssetIds": {}}
    if recipe is not None:
        require(isinstance(recipe, dict) and set(recipe) <= {"schemaVersion", "inputSha256", "activityDesignSha256", *mappings}
                and recipe.get("schemaVersion") == RECIPE_SCHEMA and recipe.get("inputSha256") == expected_input_sha
                and recipe.get("activityDesignSha256") == expected_design_sha, "recipe_binding_or_fields_invalid")
        for key in mappings:
            require(isinstance(recipe.get(key, {}), dict), "recipe_picture_mapping_invalid")
            mappings[key] = recipe.get(key, {})
    if frozen["kind"] == "book_exploration":
        entries = route.get("entries", [])
        require(len(entries) == len(directory), "book_directory_coverage_changed")
        for entry, u in zip(entries, directory):
            require(entry.get("unitId") == u["unitId"] and entry.get("title") == u["title"]
                    and any(n["nodeId"] == entry.get("representativeNodeId") and n["title"] == entry.get("representativeNodeTitle")
                            for n in u["lessons"]) and entry.get("assetId") in assets, "book_route_binding_changed")
    else:
        entries = route.get("nodes", [])
        require(len(entries) == len(directory[0]["lessons"]), "unit_directory_coverage_changed")
        for entry, node in zip(entries, directory[0]["lessons"]):
            require(all(entry.get(k) == node[k] for k in ("nodeId", "title", "sectionTitle")), "unit_route_binding_changed")
            entry["assetId"] = entry.get("assetId") or mappings["routeAssetIds"].get(entry["nodeId"])
            require(entry["assetId"] in assets, "explicit_route_picture_mapping_required")
    require(set(mappings["routeAssetIds"]) <= {e.get("nodeId") for e in entries}
            and set(mappings["modelStateAssetIds"]) <= set(STATES[adapter]), "unknown_recipe_mapping")
    for state in model["states"]:
        key = state.get("assetId") or mappings["modelStateAssetIds"].get(state["sceneStateId"])
        if key is not None:
            require(key in assets, "model_picture_missing")
            state["assetId"] = key
    return {"schemaVersion": SCHEMA, "taskId": frozen["taskId"], "kind": frozen["kind"],
            "binding": deepcopy(binding), "inputSha256": expected_input_sha,
            "activityDesignSha256": expected_design_sha, "sourceScopeSha256": expected_scope_sha,
            "providedMediaSha256": expected_media_sha, "title": design["title"], "assets": assets,
            "scenes": scenes, "modelAdapterKey": adapter, "gameMode": next(iter(mode)),
            "recipe": deepcopy(recipe), "teacher": teacher, "sourceNodeEntirelyCovered": False,
            "publicationAllowed": False, "studentDeliveryAllowed": False}
