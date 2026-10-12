"""Render reviewed role relationships over original picture-book artwork.

Only annotations move: the speaker marker, a directed relationship line and a
target character. Original artwork is never overwritten. This produces a silent
MP4 for the existing, independently audited Qwen narration player.
"""
import fcntl
from html import escape
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from content.textbook_catalog import digest
from services.textbook_activity_video import _tools
from services.textbook_batch_generation_service import atomic_json
from services.textbook_deepseek_authoring import ROOT, read, require, sha, resolve_blueprint, check_blueprint

WIDTH, HEIGHT, FPS = 960, 540, 20


def checked_plan(review_path):
    review_path = Path(review_path).resolve()
    require(review_path.is_relative_to(ROOT / "output"), "role_video_owned_review")
    review = read(review_path)
    require(review.get("schemaVersion") == "mira.textbook.role-video-review.v1"
            and review.get("status") == "reviewed_for_rendering" and review.get("reviewer"), "role_video_review_required")
    job = Path(review["jobDirectory"]).resolve()
    require(job.is_relative_to(ROOT / "output"), "role_video_owned_job")
    request, response = read(job/"request.json"), read(job/"response.json")
    require(request["requestSha256"] == digest({k: v for k, v in request.items() if k != "requestSha256"}),
            "role_video_request_changed")
    blueprint = resolve_blueprint(request, response)
    check_blueprint(blueprint, request["source"])
    require(review["taskId"] == request["taskId"] and review["blueprintSha256"] == digest(blueprint),
            "role_video_blueprint_changed")
    videos = [v for v in blueprint["mediaDesign"]["video"] if v["id"] == review["videoId"]]
    require(len(videos) == 1, "role_video_identity")
    shots = videos[0]["shots"]
    require(1 <= len(shots) <= 12, "role_video_shot_count")
    source_files = {**request["sourceFiles"], str(job/"request.json"): sha(job/"request.json"),
                    str(job/"response.json"): sha(job/"response.json"), str(review_path): sha(review_path)}
    for key, asset in review["assets"].items():
        path = Path(asset["path"]).resolve()
        require(path.is_relative_to(ROOT / "output") and not path.is_symlink()
                and sha(path) == asset["sha256"], "role_video_art_changed")
        crop = asset["pixelCrop"]
        require(set(crop) == {"left", "top", "width", "height"}
                and all(type(v) is int and v >= 0 for v in crop.values())
                and crop["width"] > 0 and crop["height"] > 0, "role_video_crop_invalid")
        require(set(asset["actors"]) == {"coral", "teal", "yellow"}, "role_video_actor_identity")
        for actor in asset["actors"].values():
            require(set(actor) == {"mouth", "label"} and all(isinstance(p, list) and len(p) == 2
                    and all(type(n) in (int, float) and math.isfinite(n) and .01 <= n <= .99 for n in p)
                    for p in actor.values()), "role_video_actor_anchor_invalid")
        source_files[str(path)] = asset["sha256"]
    duration = 0
    for shot in shots:
        require(type(shot["seconds"]) in (int, float) and 4 <= shot["seconds"] <= 12
                and int(shot["seconds"]*FPS) == shot["seconds"]*FPS, "role_video_duration_invalid")
        require(shot["sceneAssetKey"] in review["assets"] and shot.get("teacherText"), "role_video_shot_source")
        actors = {"coral", "teal", "yellow"}
        speaker, listener, target = (shot[k] for k in ("speakerCharacterId", "listenerCharacterId", "targetCharacterId"))
        require(speaker in actors and listener in actors and speaker != listener and target in actors, "role_video_roles_invalid")
        character = shot["targetCharacter"]
        require((character == "我" and target == speaker) or (character == "你" and target == listener)
                or (character == "他" and target not in {speaker, listener, "coral"}), "role_video_pronoun_mismatch")
        duration += shot["seconds"]
    require(1 <= duration <= 60 and all(sha(path) == expected for path, expected in source_files.items()),
            "role_video_source_or_duration_changed")
    return {"review": review, "request": request, "blueprint": blueprint, "shots": shots,
            "durationSeconds": duration, "sourceFiles": source_files}


def annotation_svg(shot, actors, seconds):
    def screen(point):
        return point[0]*WIDTH, 30 + point[1]*480
    sx, sy = screen(actors[shot["speakerCharacterId"]]["label"])
    tx, ty = screen(actors[shot["targetCharacterId"]]["label"])
    progress = max(0, min(1, (seconds-.5)/1.5))
    opacity = max(0, min(1, (seconds-2)/.6))
    pulse = 13 + 3*math.sin(seconds*math.pi*3)
    if shot["targetCharacterId"] == shot["speakerCharacterId"]:
        line = f'M {sx-28:.2f} {sy+22:.2f} C {sx-80:.2f} {sy+82:.2f}, {sx+80:.2f} {sy+82:.2f}, {sx+28:.2f} {sy+22:.2f}'
        points = [((1-t)**3*(sx-28)+3*(1-t)**2*t*(sx-80)+3*(1-t)*t*t*(sx+80)+t**3*(sx+28),
                   (1-t)**3*(sy+22)+3*(1-t)**2*t*(sy+82)+3*(1-t)*t*t*(sy+82)+t**3*(sy+22))
                  for t in (i/100 for i in range(101))]
    else:
        line = f'M {sx:.2f} {sy+28:.2f} Q {(sx+tx)/2:.2f} {min(sy,ty)+95:.2f}, {tx:.2f} {ty+28:.2f}'
        points = [((1-t)**2*sx+2*(1-t)*t*(sx+tx)/2+t*t*tx,
                   (1-t)**2*(sy+28)+2*(1-t)*t*(min(sy,ty)+95)+t*t*(ty+28))
                  for t in (i/100 for i in range(101))]
    length = sum(math.hypot(b[0]-a[0], b[1]-a[1]) for a,b in zip(points,points[1:]))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}">'
            '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0 0L6 3L0 6" fill="none" stroke="#936438" stroke-width="1.6"/></marker></defs>'
            f'<circle cx="{sx+57:.2f}" cy="{sy+3:.2f}" r="{pulse:.2f}" fill="#fffaf0" stroke="#af8045" stroke-width="3" opacity=".9"/>'
            f'<path d="M {sx+51:.2f} {sy:.2f} l 4 -3 v 12 l -4 -3 h -3 v -6 z M {sx+60:.2f} {sy-3:.2f} q 6 6 0 12" fill="none" stroke="#79572f" stroke-width="2.5" stroke-linejoin="round"/>'
            f'<path d="{line}" fill="none" stroke="#fffaf0" stroke-width="8" stroke-dasharray="{progress*length:.2f} {length+1:.2f}"/>'
            f'<path d="{line}" fill="none" stroke="#936438" stroke-width="3.5" stroke-dasharray="{progress*length:.2f} {length+1:.2f}"'
            + (' marker-end="url(#arrow)"' if progress == 1 else '') + '/>'
            f'<g opacity="{opacity:.3f}"><rect x="{tx-38:.2f}" y="{ty-37:.2f}" width="76" height="76" rx="20" fill="#fffaf0" stroke="#d7bd91" stroke-width="2"/>'
            f'<text x="{tx:.2f}" y="{ty+23:.2f}" text-anchor="middle" font-family="STHeiti" font-size="62" fill="#304c44">{escape(shot["targetCharacter"])}</text></g></svg>')


def render_role_video(review_path, output):
    require(os.environ.get("MIRA_TASK_TMPDIR"), "role_video_managed_temporary_directory_required")
    contract = checked_plan(review_path)
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT/"output"), "role_video_output_owner")
    output.mkdir(parents=True, exist_ok=True)
    identity = {"taskId": contract["review"]["taskId"], "blueprintSha256": digest(contract["blueprint"]),
                "reviewByteSha256": sha(review_path), "rendererByteSha256": sha(__file__)}
    receipt_path = output/"render-receipt.json"
    with (output/"render.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if receipt_path.exists():
            old = read(receipt_path)
            require(old["identity"] == identity and sha(old["video"]["path"]) == old["video"]["sha256"],
                    "role_video_existing_bytes_changed")
            return old
        require(set(p.name for p in output.iterdir()) == {"render.lock"}, "role_video_partial_output_preserved")
        node, ffmpeg, ffprobe, native = _tools()
        target = output/"roles.mp4"
        with tempfile.TemporaryDirectory(dir=os.environ["MIRA_TASK_TMPDIR"], prefix="role-frames-") as temp:
            jobs = []
            for index, shot in enumerate(contract["shots"]):
                asset = contract["review"]["assets"][shot["sceneAssetKey"]]
                jobs.append({"source": asset["path"], "crop": asset["pixelCrop"],
                    "frames": [{"path": str(Path(temp)/f'{index}-{frame}.png'),
                                "svg": annotation_svg(shot, asset["actors"], frame/FPS)} for frame in range(61)]})
            program = r"""const fs=require('fs'),sharp=require('sharp');const jobs=JSON.parse(fs.readFileSync(0,'utf8'));(async()=>{for(const j of jobs){const base=await sharp(j.source).extract(j.crop).resize(960,480,{fit:'fill'}).extend({top:30,bottom:30,left:0,right:0,background:'#fffaf0'}).png().toBuffer();for(const f of j.frames)await sharp(base).composite([{input:Buffer.from(f.svg)}]).png().toFile(f.path);}process.stdout.write(JSON.stringify({sharp:sharp.versions.sharp,rsvg:sharp.versions.rsvg}));})().catch(e=>{process.stderr.write(e.message);process.exit(1)});"""
            version = json.loads(subprocess.run([node, "-e", program], input=json.dumps(jobs), cwd=native,
                                capture_output=True, text=True, check=True).stdout)
            process = subprocess.Popen([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "image2pipe", "-vcodec", "png",
                "-r", str(FPS), "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-n", str(target)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                for index, shot in enumerate(contract["shots"]):
                    for frame in range(int(FPS*shot["seconds"])):
                        process.stdin.write(Path(jobs[index]["frames"][min(frame,60)]["path"]).read_bytes())
                process.stdin.close()
                error = process.stderr.read().decode()
                require(process.wait() == 0, "role_video_encode_failed:"+error[:100])
            except BaseException:
                process.terminate(); process.wait(); raise
            finally:
                if not process.stdin.closed: process.stdin.close()
                process.stderr.close()
        probe = json.loads(subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(target)],
                                          capture_output=True, text=True, check=True).stdout)
        require(len(probe["streams"]) == 1 and probe["streams"][0]["codec_name"] == "h264"
                and probe["streams"][0]["width"] == WIDTH and probe["streams"][0]["height"] == HEIGHT
                and abs(float(probe["format"]["duration"])-contract["durationSeconds"]) < .05, "role_video_probe_invalid")
        frames, elapsed = [], 0
        for index, shot in enumerate(contract["shots"]):
            frame = output/f'observation-{index+1}.png'
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", str(elapsed+3), "-i", str(target),
                            "-frames:v", "1", "-n", str(frame)], check=True)
            frames.append({"path": str(frame), "sha256": sha(frame), "seconds": elapsed+3,
                           "speaker": shot["speakerCharacterId"], "target": shot["targetCharacterId"], "character": shot["targetCharacter"]})
            elapsed += shot["seconds"]
        require(all(sha(path) == expected for path, expected in contract["sourceFiles"].items()), "role_video_inputs_changed")
        receipt = {"schemaVersion": "mira.textbook.original-role-animation-receipt.v1", "identity": identity,
            "status": "rendered_pending_visual_and_playback_review", "sourceFiles": contract["sourceFiles"],
            "video": {"path": str(target), "sha256": sha(target), "bytes": target.stat().st_size, "codec": "h264",
                      "width": WIDTH, "height": HEIGHT, "durationSeconds": contract["durationSeconds"], "fps": FPS},
            "observationFrames": frames, "rasterizer": version, "providerCalls": 0, "publicationAllowed": False,
            "studentDeliveryAllowed": False, "notLiveAction": True}
        atomic_json(receipt_path, receipt, immutable=True)
        return receipt
