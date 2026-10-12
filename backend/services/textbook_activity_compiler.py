"""Create-only local compilation of frozen textbook authoring inputs.

No network/configuration/Provider/DB imports. Existing paid source artifacts
remain evidence; this operator neither resumes nor changes their jobs.
"""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
from html import escape
import json
import os
from pathlib import Path

from content import textbook_activity_templates as t
from content import textbook_activity_models as models
from content import textbook_activity_source_models as source_models
from content import chinese_community_activity as community
from content import chinese_food_activity as food
from content.textbook_activity_ir import build_ir, byte_sha, require
from content.textbook_catalog import canonical, digest
from content.teacher_profiles import get_formal_runtime_teacher_contract
from content.textbook_interactive_narration import interactive_cues
from services.textbook_batch_generation_service import atomic_json

ROOT = Path(__file__).resolve().parents[2]
OWNED = ROOT / "output"
OWNER_SCHEMA = "mira.textbook.activity-compiler-output.v1"
COMPILER_SCHEMA = "mira.textbook.deterministic-compiler.v1"


def _read(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "input_file_missing_or_symlink")
    raw = path.read_bytes()
    return json.loads(raw), raw


def _label(svg):
    from xml.etree.ElementTree import fromstring
    return fromstring(svg).get("aria-label") or "观察这幅图片"


def _picture(identity, key, svg, extra="", label=""):
    return t.picture_button(identity, key, svg, label, extra).replace(
        'aria-label="' + escape(label or key) + '"',
        'aria-label="' + escape(label or _label(svg), quote=True) + '"')


PROGRESS = """
function updateProgress(){document.querySelectorAll('[data-progress]').forEach((e,i)=>{e.classList.toggle('done',i<round||(i===round&&matched&&feedbackReady));e.setAttribute('aria-label',i<round||(i===round&&matched&&feedbackReady)?'这一幅已配好':'这一幅还可以试');});}
"""


def game_scene(scene, assets, mode):
    keys = list(dict.fromkeys(k for r in scene["rounds"] for k in r["optionAssetIds"]))
    progress = '<div class="progress" aria-label="图片游戏进度">' + ''.join(
        '<i data-progress="' + str(i) + '"></i>' for i in range(len(scene['rounds']))) + '</div>'
    if mode == "visible_picture_matching":
        # A frozen picture may be a wide scene (trays, equal groups, habitats).
        # Keep its whole semantic frame rather than assuming a 160px icon crop.
        crops = {k: assets[k] for k in keys}
        body = '<div class="target-row"><button type="button" id="source" class="target" aria-label="点图或拖动，找图片伙伴">' + crops[scene["rounds"][0]["targetAssetId"]] + '</button><div id="pair" class="pair" aria-live="polite"></div></div>'
        body += '<div class="choices" id="choices">' + ''.join(_picture(
            "option-" + k, k, assets[k], f'data-option="{escape(k)}"') for k in keys) + '</div><div id="detail" class="picture-detail" hidden></div>'
        code = t.VISIBLE_MATCH_CODE
        config = {"rounds": scene["rounds"], "crops": crops, "assets": {k: assets[k] for k in keys},
                  "intro": scene["initialCueId"], "retry": scene["retryCueId"], "hint": scene["hintCueId"],
                  "reset": scene["resetCueId"], "complete": scene["completeCueId"]}
    else:
        body = '<div id="target-character" hidden></div><div id="choices" class="choices">' + ''.join(_picture(
            "answer-" + k, k, assets[k], f'data-answer="{escape(k)}"') for k in keys) + '</div>'
        code = t.LISTEN_MATCH_CODE
        config = {"rounds": scene["rounds"], "intro": scene["initialCueId"], "retry": scene["retryCueId"],
                  "reset": scene["resetCueId"], "complete": scene["completeCueId"]}
    body += progress + '<div class="tools">' + t.button("start", "开始听", "start", "data-cancel")
    body += t.button("replay", "重听", "replay", "data-cancel") + t.button("reset", "重新找", "reset", "data-cancel")
    if mode == "visible_picture_matching":
        body += t.button("hint", "放大看", "hint")
    body += t.button("next", "下一幅", "next") + '</div>'
    # Spoken picture choices must preserve small semantic details such as
    # asking/handing versus grabbing. Keep equal-sized options on phones.
    if mode != "visible_picture_matching":
        body += ('<style data-picture-choice-layout="phone-v2">'
                 '@media(max-width:420px){#choices{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}'
                 '#choices>button{min-height:124px;padding:7px}'
                 '#choices>button>svg:not(.feedback-mark){width:100%;height:auto;max-height:none}}'
                 '</style>')
    return t.scene_html(scene, body, PROGRESS + code.replace("CONFIG", t.js(config)))


def model_scene(scene, assets):
    adapter = scene["modelAdapterKey"]
    if adapter == "chinese_well_bucket_scene":
        return community.well_scene(scene, assets)
    if adapter == "chinese_zongzi_layers_scene":
        return food.zongzi_scene(scene, assets)
    if adapter in source_models.SUPPORTED:
        require(all(s.get("assetId") for s in scene["states"]), "source_semantic_state_pictures_required")
        engine = source_models.engine(adapter)
    elif adapter in {"english_school_semantic_scene", "english_travel_semantic_scene"}:
        engine = models.traffic_engine("school" if "school" in adapter else "travel",
                                       [s["sceneStateId"] for s in scene["states"]])
    elif adapter == "english_colours_semantic_scene":
        engine = models.model_engine("three_backpacks_handle_opening")
    elif adapter == "english_kitchen_semantic_scene":
        engine = models.model_engine("cabinet_hinged_door_drawer_cup")
        old = "const cx=modelState==='cup'?.2:1.55,cz=modelState==='cup'?-.06:.15;"
        require(engine.count(old) == 1, "kitchen_geometry_anchor_changed")
        engine = engine.replace(old, "const cx=modelState==='cup'?1.55:.2,cz=modelState==='cup'?.15:-.06;")
    elif adapter in models.SUPPORTED:
        engine = models.model_engine(adapter)
    else:
        engine = models.legacy_model_engine(adapter)
    if all(s.get("assetId") for s in scene["states"]):
        pictures = [assets[s["assetId"]] for s in scene["states"]]
    elif adapter in models.SUPPORTED:
        pictures = models.pictures(adapter)
    else:
        require(not adapter.endswith("_semantic_scene"), "semantic_state_pictures_required")
        pictures = models.legacy_model_pictures(adapter)
    body = '<canvas id="model-canvas" class="model" aria-label="可以移动、转动并换摆法的真实观察模型"></canvas><div class="choices">'
    body += ''.join(_picture("state-" + s["sceneStateId"], s.get("assetId", s["sceneStateId"]), pic,
        f'data-state="{escape(s["sceneStateId"])}"') for s, pic in zip(scene["states"], pictures)) + '</div><div class="tools">'
    for identity, label, icon, extra in [
        ("start", "开始观察", "start", "data-cancel"), ("replay", "重听", "replay", "data-cancel"),
        ("left", "向左移", "left", ""), ("right", "向右移", "right", ""), ("rotate", "转一转", "rotate", ""),
        ("reset", "重新摆", "reset", "data-cancel"), ("finish", "听老师小结", "speaker", ""),
        ("model-retry", "重新加载模型", "replay", "data-cancel hidden")]:
        body += t.button(identity, label, icon, extra)
    body += '</div>'
    cfg = {"states": scene["states"], "intro": scene["initialCueId"], "retry": scene["retryCueId"],
           "reset": scene["resetCueId"], "complete": scene["completeCueId"]}
    controls = models.MODEL_CONTROLS
    if adapter in models.SUPPORTED or adapter in source_models.SUPPORTED or adapter.endswith("_semantic_scene"):
        controls = controls.replace("p.x+delta< -2.35||p.x+delta>2.35", "p.x+delta< -.6||p.x+delta>.6")
    return t.scene_html(scene, body, engine + controls.replace("CONFIG", t.js(cfg)))


def route_scene(scene, assets, kind):
    is_book = kind == "book_exploration"
    entries = scene["entries" if is_book else "nodes"]
    key = "unitId" if is_book else "nodeId"
    body = '<div class="route">' + ''.join(_picture(
        "route-" + str(i), e["assetId"], assets[e["assetId"]],
        f'data-route-id="{escape(e[key])}"', e["title"]) for i, e in enumerate(entries)) + '</div><div class="tools">'
    body += t.button("start", "听老师说", "start", "data-cancel") + t.button("replay", "重听", "replay", "data-cancel")
    body += t.button("finish", "听老师小结", "speaker") + '</div>'
    code = """
const config=CONFIG;function refreshControls(){}
function preview(entry){if(interactionBusy)return;run(async signal=>{document.querySelectorAll('[data-route-id]').forEach(b=>b.classList.toggle('selected',b.dataset.routeId===entry[config.key]));await narrate(entry.routeCueId,signal);});}
config.entries.forEach((e,i)=>listen('route-'+i,()=>preview(e)));listen('start',()=>run(signal=>narrate(config.intro,signal)));listen('replay',replay);listen('finish',()=>{if(interactionBusy)return;run(signal=>narrate(config.finish,signal));});
function applyTeacherState(state){if(Object.keys(state).length!==1||typeof state[config.key]!=='string')return;const entry=config.entries.find(e=>e[config.key]===state[config.key]);if(entry){assisted=true;preview(entry);}}
""".replace("CONFIG", t.js({"entries": entries, "key": key, "intro": scene["initialCueId"], "finish": scene["finishCueId"]}))
    return t.scene_html(scene, body, code)


def render(ir, frozen, classroom_id, created_at):
    video, game, model, route = ir["scenes"]
    htmls = [t.video_scene(video, ir["assets"]), game_scene(game, ir["assets"], ir["gameMode"]),
             model_scene(model, ir["assets"]), route_scene(route, ir["assets"], ir["kind"])]
    # The generated dispatcher is the only caller of the runtime audio symbol.
    for planned, html in zip(ir["scenes"], htmls):
        require(interactive_cues(html) == [{"id": c["cueId"], "text": c["teacherText"]} for c in planned["finiteCues"]], "rendered_cue_drift")
        require(html.count("miraNarrate") == len(planned["finiteCues"]), "rendered_dispatch_not_literal")
    runtime = get_formal_runtime_teacher_contract(ir["binding"]["subject"])["runtime"]
    stage = {"id": classroom_id, "name": ir["title"], "style": "interactive", "createdAt": created_at,
             "updatedAt": created_at, "generatedAgentConfigs": [{"id": "mira-textbook-" + ir["taskId"][:16] + "-teacher",
                "name": ir["teacher"]["teacherName"], "role": "teacher", "persona": "用原创图片、声音和真实操作陪伴学生预习。",
                "avatar": runtime["avatar"], "color": "#42685d", "priority": 10,
                "teacherProfile": ir["teacher"]["teacherProfile"], "voiceConfig": runtime["voiceConfig"]}], "videoManifest": {}}
    return {"id": classroom_id, "createdAt": created_at, "stage": stage, "scenes": [
        {"id": s["sceneId"], "outlineId": "local_" + s["sceneId"], "stageId": classroom_id,
         "type": "interactive", "title": s["title"], "order": i,
         "content": {"type": "interactive", "widgetType": s["widgetType"], "html": html},
         "actions": [], "createdAt": created_at, "updatedAt": created_at}
        for i, (s, html) in enumerate(zip(ir["scenes"], htmls))]}


def preflight(entry):
    fields = {"inputPath", "inputSha256", "designPath", "activityDesignSha256", "sourceScopeSha256", "providedMediaSha256"}
    require(isinstance(entry, dict) and fields <= set(entry) and set(entry) <= fields | {"recipePath", "recipeByteSha256"}, "batch_entry_fields_invalid")
    frozen, raw = _read(entry["inputPath"])
    design, design_raw = _read(entry["designPath"])
    source = Path(entry["inputPath"]).resolve().parent
    prepared, prepared_raw = _read(source / "state.json")
    require(prepared.get("schemaVersion") == "mira.textbook.private-batch-generation-state.v1"
            and prepared.get("status") in {"prepared", "dispatching", "dispatch_unknown", "generating",
                                           "generated_needs_review", "failed_needs_reconciliation"}
            and prepared.get("taskId") == frozen.get("taskId") and prepared.get("inputSha256") == frozen.get("inputSha256")
            and prepared.get("publicationAllowed") is False and prepared.get("studentDeliveryAllowed") is False,
            "source_state_binding_invalid")
    if type(prepared.get("createdAt")) is not int:
        # Some earlier local compilers put time only in the immutable classroom.
        # Recover it exclusively from that state's exact hashed local artifact.
        require(prepared["status"] == "generated_needs_review", "source_created_at_missing")
        source_classroom, _ = _read(source / "classroom.json")
        require(prepared.get("classroomSha256") == digest(source_classroom)
                and prepared.get("classroomId") == source_classroom.get("id")
                and source_classroom.get("stage", {}).get("id") == source_classroom.get("id")
                and type(source_classroom.get("createdAt")) is int, "source_created_at_identity_changed")
        prepared = {**prepared, "createdAt": source_classroom["createdAt"]}
    recipe = None
    if "recipePath" in entry:
        recipe, recipe_raw = _read(entry["recipePath"])
        require(byte_sha(recipe_raw) == entry.get("recipeByteSha256"), "recipe_bytes_changed")
    else:
        require("recipeByteSha256" not in entry, "recipe_path_missing")
    ir = build_ir(frozen, design, expected_input_sha=entry["inputSha256"],
        expected_design_sha=entry["activityDesignSha256"], expected_scope_sha=entry["sourceScopeSha256"],
        expected_media_sha=entry["providedMediaSha256"], recipe=recipe)
    evidence = {str(Path(entry["inputPath"]).resolve()): byte_sha(raw),
                str(Path(entry["designPath"]).resolve()): byte_sha(design_raw),
                str(source / "state.json"): byte_sha(prepared_raw)}
    if "recipePath" in entry:
        evidence[str(Path(entry["recipePath"]).resolve())] = entry["recipeByteSha256"]
    # Preserve all original provider receipts/diagnostics already beside input.
    for name in ("classroom.json", "generation-job.json", "job.json", "quality-report.json", "derivation.json"):
        p = source / name
        if p.exists():
            require(not p.is_symlink(), "source_artifact_symlink")
            evidence[str(p)] = byte_sha(p.read_bytes())
    return frozen, raw, prepared, ir, evidence


@contextmanager
def owned_output(directory):
    directory = Path(directory).absolute()
    require(directory.resolve().is_relative_to(OWNED.resolve()) and directory.resolve() != OWNED.resolve(), "owned_output_required")
    require(all(not p.is_symlink() for p in (directory, *directory.parents)), "output_symlink_forbidden")
    if directory.exists() and not (directory / "compiler-owner.json").exists():
        require(not any(directory.iterdir()), "output_not_empty_or_owned")
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / "compiler.lock"
    require(not lock_path.is_symlink(), "output_lock_symlink")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        owner = directory / "compiler-owner.json"
        value = {"schemaVersion": OWNER_SCHEMA, "compilerSchema": COMPILER_SCHEMA,
                 "publicationAllowed": False, "providerCalls": 0}
        if owner.exists():
            require(not owner.is_symlink() and json.loads(owner.read_text()) == value, "output_owner_conflict")
        else:
            require(not any(p.name != "compiler.lock" for p in directory.iterdir()), "output_not_empty_or_owned")
            atomic_json(owner, value, immutable=True)
        yield directory.resolve()


def _write_exact(path, raw):
    require(not path.is_symlink(), "output_artifact_symlink")
    if path.exists():
        require(path.read_bytes() == raw, "immutable_output_conflict")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def compile_batch(entries, output_directory):
    require(isinstance(entries, list) and 0 < len(entries) <= 128, "bounded_batch_required")
    checked = [preflight(e) for e in entries]  # all-or-nothing preflight before any output
    require(len({item[0]["taskId"] for item in checked}) == len(checked), "duplicate_batch_task")
    results = []
    with owned_output(output_directory) as output:
        for frozen, input_raw, prepared, ir, evidence in checked:
            task = ir["taskId"]
            folder = output / task
            require(not folder.is_symlink() and folder.resolve() != Path(next(iter(evidence))).parent, "distinct_candidate_required")
            modules = [Path(__file__), ROOT / "backend/content/textbook_activity_ir.py",
                       ROOT / "backend/content/textbook_activity_templates.py", ROOT / "backend/content/textbook_activity_models.py"]
            if ir["modelAdapterKey"] in source_models.SUPPORTED:
                modules.append(ROOT / "backend/content/textbook_activity_source_models.py")
            if ir["modelAdapterKey"] == "chinese_well_bucket_scene":
                modules.append(Path(community.__file__))
            if ir["modelAdapterKey"] == "chinese_zongzi_layers_scene":
                modules.append(Path(food.__file__))
            compiler_files = {str(p.relative_to(ROOT)): byte_sha(p.read_bytes()) for p in modules}
            # Changed narration or rendering must never reuse a cached classroom identity.
            revision = digest({"ir": ir, "compilerFiles": compiler_files})[:12]
            classroom_id = ir["kind"] + "_" + task[:16] + "_" + revision
            classroom = render(ir, frozen, classroom_id, prepared["createdAt"])
            classroom_sha = digest(classroom)
            parent_generation_status = prepared.get("sourceGenerationStatus") or (
                "not_dispatched" if prepared["status"] == "prepared" and prepared.get("providerDispatched") is False
                else prepared["status"])
            parent_generation_job = prepared.get("sourceGenerationJobId") or prepared.get("runtimeJobId")
            state = {"schemaVersion": "mira.textbook.private-batch-generation-state.v1", "status": "generated_needs_review",
                "taskId": task, "inputSha256": frozen["inputSha256"], "classroomId": classroom_id,
                "classroomSha256": classroom_sha, "runtimeOrigin": "http://127.0.0.1:3100",
                "authoringMode": "structured_local_original", "sourceGenerationStatus": parent_generation_status,
                "sourceGenerationJobId": parent_generation_job, "parentCandidateStatus": prepared["status"],
                "parentInputSha256": frozen["inputSha256"],
                "providerDispatched": False, "publicationAllowed": False, "studentDeliveryAllowed": False,
                "qualityPassed": False, "browserQAPassed": False, "semanticTeachingReview": "pending",
                "sourceNodeEntirelyCovered": False, "createdAt": prepared["createdAt"]}
            source_directory = Path(next(iter(evidence))).parent
            local_source_files = {str(Path(p).relative_to(source_directory)): sha for p, sha in evidence.items()
                                  if Path(p).is_relative_to(source_directory)}
            external_source_files = {p: sha for p, sha in evidence.items() if not Path(p).is_relative_to(source_directory)}
            derivation = {"schemaVersion": COMPILER_SCHEMA, "authoringMode": "structured_local_original",
                "sourceGenerationStatus": parent_generation_status, "sourceGenerationJobId": parent_generation_job,
                "parentCandidateStatus": prepared["status"],
                "parentInputSha256": frozen["inputSha256"], "sourceDirectory": str(source_directory),
                "sourceFiles": local_source_files, "externalAuthoringFiles": external_source_files,
                "activityDesignSha256": ir["activityDesignSha256"], "irSha256": digest(ir),
                "classroomSha256": classroom_sha, "compilerFiles": compiler_files,
                "providerCalls": 0, "runtimeSaves": 0, "audioCalls": 0, "publicationAllowed": False,
                "studentDeliveryAllowed": False, "qualityPassed": False, "browserQAPassed": False,
                "pending": ["independent grade/source/learning-task review", "actual browser, video, mesh and touch verification",
                            "registered teacher prerecorded narration and ASR", "formal release rights/publication review"]}
            artifacts = {"input.json": input_raw, "classroom.json": (canonical(classroom) + "\n").encode(),
                         "state.json": (canonical(state) + "\n").encode(), "activity-ir.json": (canonical(ir) + "\n").encode(),
                         "derivation.json": (canonical(derivation) + "\n").encode()}
            # Refuse conflicting/unknown destination contents before any write.
            if folder.exists():
                require(folder.is_dir() and all(not p.is_symlink() for p in folder.iterdir()), "output_artifact_symlink")
                require(set(p.name for p in folder.iterdir()) <= set(artifacts) | {"compiler-static-review.json"}, "existing_candidate_has_external_consumers")
                for name, raw in artifacts.items():
                    if (folder / name).exists():
                        require((folder / name).read_bytes() == raw, "immutable_output_conflict")
            folder.mkdir(exist_ok=True)
            for name, raw in artifacts.items():
                _write_exact(folder / name, raw)
            from services.textbook_batch_queue_audio_service import structural_review
            review = structural_review(folder)
            _write_exact(folder / "compiler-static-review.json", (canonical(review) + "\n").encode())
            require(all(byte_sha(Path(p).read_bytes()) == sha for p, sha in evidence.items()), "source_changed_during_compile")
            results.append({"candidateDirectory": str(folder), "taskId": task, "classroomId": classroom_id,
                "classroomSha256": classroom_sha, "inputSha256": ir["inputSha256"], "sceneCount": 4,
                "finiteCueCount": sum(len(s["finiteCues"]) for s in ir["scenes"]), "modelAdapterKey": ir["modelAdapterKey"],
                "structuralChecksPassed": review["structuralChecksPassed"], "issues": review["issues"],
                "providerCalls": 0, "runtimeSaves": 0, "audioCalls": 0, "qualityPassed": False,
                "browserQAPassed": False, "publicationAllowed": False, "sourceNodeEntirelyCovered": False})
    return results
