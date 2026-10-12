"""Render finite original SVG component motions locally, with no runtime access.

This renders authored illustrations, never claims footage or an experiment. The
exact target SVG is held at each observation's seek time. Whole-card pans are
unsupported: a plan must move named semantic components against fixed artwork.
"""
import fcntl
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from content.textbook_activity_ir import byte_sha, require, safe_svg, SHA, ID
from content.textbook_batch import TASK_SCHEMA
from content.textbook_catalog import canonical, digest, validate_manifest
from core.errors import ApiError

ET.register_namespace("", "http://www.w3.org/2000/svg")

ROOT = Path(__file__).resolve().parents[2]
OWNED = ROOT / "output"
WIDTH, HEIGHT, FPS, DURATION = 960, 540, 20, 12
FAMILIES = {
    "counted_arrival": ("counted_object", {"translate"}),
    "hinged_component": ("hinged_part", {"rotate"}),
    "journey_vehicle": ("transport", {"translate"}),
    "place_object": ("placed_object", {"translate"}),
    "natural_component_motion": ("natural_part", {"translate", "rotate"}),
}
RECEIPT = "mira.textbook.original-component-animation-receipt.v1"


def _read(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "video_source_file_invalid")
    raw = path.read_bytes()
    return json.loads(raw), raw


def _finite(values, count):
    return (isinstance(values, list) and len(values) == count
            and all(type(v) in {int, float} and math.isfinite(v) for v in values))


def _geometry(node):
    return sum(n.tag.rsplit("}", 1)[-1] in {"path", "rect", "circle", "ellipse", "line", "polygon", "polyline"}
               for n in node.iter())


def preflight_video(task_path, design_path, *, task_sha256, design_sha256):
    task, task_raw = _read(task_path)
    design, design_raw = _read(design_path)
    require(SHA.fullmatch(str(task_sha256)) and digest(task) == task_sha256
            and task.get("schemaVersion") == TASK_SCHEMA and SHA.fullmatch(str(task.get("taskId", ""))), "video_task_hash_invalid")
    identity_keys = ("schemaVersion", "kind", "scope", "manifestSha256", "teachingProfileSha256",
                     "qualityPolicySha256", "knowledgeBriefSha256", "originalContentSha256")
    require(all(k in task for k in identity_keys) and digest({k: task[k] for k in identity_keys}) == task["taskId"], "video_task_identity_changed")
    require(SHA.fullmatch(str(design_sha256)) and digest(design) == design_sha256
            and design.get("schemaVersion") == "mira.textbook.activity-design.v1"
            and design.get("taskId") == task["taskId"]
            and design.get("binding") == task["scope"]
            and design.get("manifestSha256") == task["manifestSha256"]
            and design.get("kind") == task["kind"]
            and design.get("status") == "draft" and design.get("publicationAllowed") is False,
            "video_design_task_binding_invalid")
    source_files = {str(Path(task_path).resolve()): byte_sha(task_raw), str(Path(design_path).resolve()): byte_sha(design_raw)}
    require(task["kind"] in {"book_exploration", "unit_guide", "lesson_courseware"}, "video_kind_unsupported")
    if task["kind"] == "lesson_courseware":
        from content.textbook_batch_generation import reviewed_lesson_scope
        scope_path = design.get("reviewedLessonScopePath")
        require(isinstance(scope_path, str), "video_reviewed_lesson_scope_required")
        scope, scope_raw = _read(scope_path)
        require(byte_sha(scope_raw) == design.get("reviewedLessonScopeByteSha256")
                and scope == reviewed_lesson_scope(task, scope_path), "video_lesson_scope_changed")
        evidence = scope.get("evidence", {})
        require(evidence.get("pages"), "video_lesson_page_evidence_required")
        for page in evidence["pages"]:
            page_path = Path(page["path"])
            require(page_path.is_file() and not page_path.is_symlink()
                    and byte_sha(page_path.read_bytes()) == page.get("sha256"), "video_lesson_page_changed")
            source_files[str(page_path.resolve())] = page["sha256"]
        source_files[str(Path(scope_path).resolve())] = byte_sha(scope_raw)
    matching_manifest = None
    for path in task.get("sourcePaths", []):
        manifest, raw = _read(path)
        try:
            manifest = validate_manifest(manifest)
        except ApiError as exc:
            raise ValueError("textbook_compiler_video_source_manifest_invalid") from exc
        require(digest(manifest) == task["manifestSha256"], "video_source_manifest_changed")
        require(all(task["scope"].get(k) == manifest[k] for k in
                    ("editionId", "revisionId", "subject", "gradeCode", "schoolSystem", "volume")), "video_source_binding_changed")
        source_files[str(Path(path).resolve())] = byte_sha(raw)
        matching_manifest = manifest
    require(matching_manifest and matching_manifest["coverage"]["status"] != "index_only", "video_known_source_directory_required")
    if task["scope"].get("unitId"):
        require(any(u["unitId"] == task["scope"]["unitId"] for u in matching_manifest["units"]), "video_unit_source_missing")
    plan = design.get("localVideoPlan")
    require(isinstance(plan, dict) and set(plan) == {"schemaVersion", "animationFamily", "shots"}
            and plan["schemaVersion"] == "mira.textbook.original-video-plan.v1"
            and plan["animationFamily"] in FAMILIES
            and isinstance(plan["shots"], list) and len(plan["shots"]) == 3, "video_animation_family_unsupported")
    assets = {}
    for a in design.get("assetPlan", []):
        key = a.get("assetId")
        require(ID.fullmatch(str(key)) and key not in assets, "video_asset_identity_invalid")
        svg = safe_svg(a.get("svgMarkup"))
        require(byte_sha(svg.encode()) == a.get("sha256"), "video_asset_hash_changed")
        assets[key] = svg
    require(isinstance(design.get("scenes"), list) and design["scenes"], "video_observation_scene_missing")
    scene = design["scenes"][0]
    observations = scene.get("observations")
    require(scene.get("type") == "interactive" and scene.get("widgetType") == "game"
            and isinstance(observations, list) and len(observations) == 3, "video_observation_shape_invalid")
    require(len({ob.get("assetId") for ob in observations}) == 3 and len({ob.get("cueId") for ob in observations}) == 3,
            "video_three_distinct_observations_required")
    cues = {c["cueId"]: c["teacherText"] for c in scene.get("finiteCues", [])}
    role, operations = FAMILIES[plan["animationFamily"]]
    for index, (shot, ob) in enumerate(zip(plan["shots"], observations)):
        require(isinstance(shot, dict) and set(shot) == {"sourceAssetId", "tracks"}
                and shot["sourceAssetId"] in assets and ob.get("assetId") == shot["sourceAssetId"]
                and ob.get("cueId") in cues, "video_shot_observation_mismatch")
        seek = ob.get("seekSeconds")
        require(type(seek) in {int, float} and math.isfinite(seek)
                and index * 4 + 1.1 <= seek < (index + 1) * 4, "video_seek_must_hold_exact_target_picture")
        tree = ET.fromstring(assets[shot["sourceAssetId"]])
        nodes = {}
        for n in tree.iter():
            if n.get("id"):
                require(n.get("id") not in nodes, "video_duplicate_svg_id")
                nodes[n.get("id")] = n
        tracks = shot["tracks"]
        require(isinstance(tracks, list) and 0 < len(tracks) <= 10, "video_real_component_motion_required")
        moving = []
        for track in tracks:
            require(isinstance(track, dict) and set(track) == {"groupId", "role", "operation", "from", "to", "startSeconds", "endSeconds"}, "video_track_fields_invalid")
            group = nodes.get(track["groupId"])
            require(group is not None and group is not tree and group.tag.rsplit("}", 1)[-1] == "g"
                    and _geometry(group) > 0 and group not in moving, "video_named_semantic_component_required")
            require(not any(group in list(other.iter()) or other in list(group.iter()) for other in moving), "video_nested_motion_not_supported")
            moving.append(group)
            operation = track["operation"]
            require(track["role"] == role and operation in operations, "video_motion_role_mismatch")
            size = 2 if operation == "translate" else 3
            require(_finite(track["from"], size) and _finite(track["to"], size), "video_motion_values_invalid")
            if operation == "translate":
                require(track["to"] == [0, 0] and 10 <= math.hypot(*track["from"]) <= 500, "video_translation_not_meaningful")
            else:
                require(track["to"][0] == 0 and track["from"][1:] == track["to"][1:]
                        and 15 <= abs(track["from"][0]) <= 140, "video_hinge_not_meaningful")
            require(type(track["startSeconds"]) in {int, float} and type(track["endSeconds"]) in {int, float}
                    and 0 <= track["startSeconds"] < track["endSeconds"] <= 1
                    and track["endSeconds"] - track["startSeconds"] >= .15, "video_motion_timing_invalid")
        # The scenery/landmark stays fixed. Moving an entire card is unsupported.
        require(_geometry(tree) > sum(_geometry(n) for n in moving), "video_whole_card_motion_unsupported")
    return {"task": task, "design": design, "plan": plan, "assets": assets, "sourceFiles": source_files,
            "taskSha256": task_sha256, "designSha256": design_sha256}


def frame_svg(contract, shot_index, seconds):
    """At >=1s the serialized target SVG is exact; no guessed observation pose."""
    shot = contract["plan"]["shots"][shot_index]
    source = contract["assets"][shot["sourceAssetId"]]
    if seconds >= 1:
        return source
    tree = ET.fromstring(source)
    parents = {child: parent for parent in tree.iter() for child in parent}
    nodes = {n.get("id"): n for n in tree.iter() if n.get("id")}
    for track in shot["tracks"]:
        progress = min(1, max(0, (seconds-track["startSeconds"])/(track["endSeconds"]-track["startSeconds"])))
        eased = progress * progress * (3-2*progress)
        values = [start + (end-start)*eased for start, end in zip(track["from"], track["to"])]
        group = nodes[track["groupId"]]
        parent = parents[group]
        wrapper = ET.Element("{http://www.w3.org/2000/svg}g", {"transform": track["operation"] + "(" + " ".join(format(v, ".6g") for v in values) + ")"})
        at = list(parent).index(group)
        parent.remove(group)
        wrapper.append(group)
        parent.insert(at, wrapper)
    return ET.tostring(tree, encoding="unicode")


def _tools():
    node = shutil.which("node")
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    native = ROOT / "openmaic-runtime/.runtime/OpenMAIC"
    require(node and ffmpeg and ffprobe and (native / "node_modules/sharp").exists(), "video_local_renderer_dependencies_missing")
    return node, ffmpeg, ffprobe, native


def _write(path, raw):
    require(not path.exists() and not path.is_symlink(), "video_create_only_conflict")
    with path.open("xb") as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())


def render_video(task_path, design_path, output_directory, *, task_sha256, design_sha256):
    contract = preflight_video(task_path, design_path, task_sha256=task_sha256, design_sha256=design_sha256)
    output = Path(output_directory).absolute()
    require(output.resolve().is_relative_to(OWNED.resolve()) and output.resolve() != OWNED.resolve()
            and all(not p.is_symlink() for p in (output, *output.parents)), "video_owned_output_required")
    output.mkdir(parents=True, exist_ok=True)
    folder = output / contract["task"]["taskId"]
    require(not folder.is_symlink(), "video_output_symlink")
    folder.mkdir(exist_ok=True)
    renderer_sha = byte_sha(Path(__file__).read_bytes())
    identity = {"taskId": contract["task"]["taskId"], "binding": contract["task"]["scope"],
                "taskSha256": task_sha256, "designSha256": design_sha256,
                "rendererFileSha256": renderer_sha, "sourceFiles": contract["sourceFiles"]}
    receipt_path = folder / "local-render-receipt.json"
    lock_path = folder / "render.lock"
    require(not lock_path.is_symlink(), "video_lock_symlink")
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if receipt_path.exists():
            receipt, _ = _read(receipt_path)
            require(all(receipt.get(k) == v for k, v in identity.items())
                    and receipt.get("schemaVersion") == RECEIPT and receipt.get("status") == "rendered_pending_visual_review"
                    and receipt.get("providerCalls") == receipt.get("runtimeCalls") == receipt.get("databaseWrites") == 0
                    and receipt.get("publicationAllowed") is False and receipt.get("studentDeliveryAllowed") is False
                    and len(receipt.get("observationFrames", [])) == 3, "video_receipt_identity_changed")
            for entry in [receipt["video"], *receipt["observationFrames"]]:
                path = Path(entry["path"])
                require(path.parent == folder.resolve() and path.is_file() and not path.is_symlink()
                        and byte_sha(path.read_bytes()) == entry["sha256"], "video_saved_bytes_changed")
            return receipt
        require(set(p.name for p in folder.iterdir()) == {"render.lock"}, "video_incomplete_output_preserved")
        node, ffmpeg, ffprobe, native = _tools()
        target = folder / "observation.mp4"
        with tempfile.TemporaryDirectory(prefix="textbook-video-", dir=os.environ.get("MIRA_TASK_TMPDIR")) as temp:
            temp = Path(temp)
            jobs, keys = [], {}
            for shot in range(3):
                for frame in range(FPS+1):
                    key = (shot, frame)
                    path = temp / (str(shot) + "-" + str(frame) + ".png")
                    keys[key] = path
                    jobs.append({"svg": frame_svg(contract, shot, frame/FPS), "path": str(path)})
            program = r"""const fs=require('fs'),sharp=require('sharp');const jobs=JSON.parse(fs.readFileSync(0,'utf8'));(async()=>{for(const job of jobs)await sharp(Buffer.from(job.svg),{density:144}).resize(960,540,{fit:'contain',background:'#f7f3e8'}).flatten({background:'#f7f3e8'}).png().toFile(job.path);process.stdout.write(JSON.stringify({sharp:sharp.versions.sharp,librsvg:sharp.versions.rsvg}));})().catch(e=>{process.stderr.write(e.message);process.exit(1)});"""
            rasterizer = json.loads(subprocess.run([node, "-e", program], cwd=native,
                input=json.dumps(jobs), text=True, capture_output=True, check=True).stdout)
            # Actual component frames, then stable target frames for each cue.
            command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "image2pipe", "-vcodec", "png", "-r", str(FPS), "-i", "pipe:0",
                       "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-n", str(target)]
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                for frame in range(FPS*DURATION):
                    shot, local = divmod(frame, 4*FPS)
                    process.stdin.write(keys[(shot, min(local, FPS))].read_bytes())
                process.stdin.close()
                error = process.stderr.read().decode()
                require(process.wait() == 0, "video_encoder_failed:" + error[:160])
            except BaseException:
                process.terminate(); process.wait(); raise
            finally:
                if not process.stdin.closed:
                    process.stdin.close()
                process.stderr.close()
        probe = json.loads(subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(target)], capture_output=True, text=True, check=True).stdout)
        require(len(probe["streams"]) == 1, "video_audio_or_extra_stream_forbidden")
        require(0 < target.stat().st_size <= 16 * 1024 * 1024, "video_archive_size_limit")
        stream = probe["streams"][0]
        require(stream.get("codec_type") == "video" and stream.get("codec_name") == "h264"
                and stream.get("pix_fmt") == "yuv420p" and stream.get("width") == WIDTH
                and stream.get("height") == HEIGHT and abs(float(probe["format"]["duration"])-DURATION) < .01,
                "video_probe_mismatch")
        frames = []
        for index, ob in enumerate(contract["design"]["scenes"][0]["observations"]):
            path = folder / ("observation-" + str(index+1) + ".png")
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", str(ob["seekSeconds"]), "-i", str(target), "-frames:v", "1", "-n", str(path)], check=True)
            frames.append({"seconds": ob["seekSeconds"], "assetId": ob["assetId"], "cueId": ob["cueId"], "path": str(path.resolve()), "sha256": byte_sha(path.read_bytes())})
        require(all(byte_sha(Path(p).read_bytes()) == sha for p, sha in contract["sourceFiles"].items()), "video_sources_changed_during_render")
        receipt = {"schemaVersion": RECEIPT, "status": "rendered_pending_visual_review", **identity,
            "rendererPath": str(Path(__file__).resolve()), "animationFamily": contract["plan"]["animationFamily"],
            "rasterizer": rasterizer, "video": {"path": str(target.resolve()), "sha256": byte_sha(target.read_bytes()),
                "sizeBytes": target.stat().st_size, "codec": "h264", "pixelFormat": "yuv420p", "durationSeconds": DURATION,
                "width": WIDTH, "height": HEIGHT, "fps": FPS, "audioStreams": 0}, "observationFrames": frames,
            "notLiveAction": True, "notExperimentEvidence": True, "visualReviewStatus": "pending",
            "providerCalls": 0, "runtimeCalls": 0, "databaseWrites": 0, "publicationAllowed": False, "studentDeliveryAllowed": False}
        _write(receipt_path, (canonical(receipt)+"\n").encode())
        return receipt
