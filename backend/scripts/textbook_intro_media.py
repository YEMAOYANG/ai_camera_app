"""Operator-only, resumable production of shared picture-guide audio.

No database writes, generation from student requests, or automatic paid retries.
Run --synthesize to produce/reconcile audio; --compile verifies all assets before
atomically installing the public media manifest. Receipts stay in output/.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from content.textbook_catalog import canonical, digest, validate_manifest
from core.config import AppConfig
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError

CONTENT = BACKEND / "content/textbooks/intro-media-v1"
ASSETS = ROOT / "student-web/public/textbooks/picture-guide-v1"
WORK = ROOT / "output/textbook-picture-guides-20260924"


def save(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(canonical(value), encoding="utf-8")
    temp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plan():
    source = json.loads((CONTENT / "authoring.json").read_text())
    manifest = validate_manifest(json.loads((BACKEND / "content/textbooks/revisions/pep-chinese-g1-upper.directory.v3.json").read_text()))
    assert all(source[k] == manifest[k] for k in ("editionId", "revisionId", "gradeCode"))
    introductions = [manifest["introduction"], *(unit["introduction"] for unit in manifest["units"])]
    assert {g["id"] for g in source["guides"]} == {i["introductionId"] for i in introductions}
    teacher = get_formal_subject_qwen_voice_identity("chinese")
    frozen = {"authoring": source, "sourceManifestSha256": digest(manifest), "teacher": teacher.to_target_payload(), "audioProcessing": "mp3-atempo-0.93-v1"}
    return frozen, {i["introductionId"]: digest(i) for i in introductions}, teacher


def segments(frozen):
    for guide in frozen["authoring"]["guides"]:
        for kind in ("scenes", "choices"):
            for index, item in enumerate(guide[kind]):
                assert len(item) == 4 and 0 <= item[1] <= 3 and 1 <= len(item[2]) <= 16 and 1 <= len(item[3]) <= 200
                identity = {"planSha256": digest(frozen), "guideId": guide["id"], "kind": kind, "index": index}
                yield guide, kind, index, item, "tbintro_" + digest(identity)


def synthesize(frozen, teacher):
    config = AppConfig.from_env()
    runtime = OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL, formal_audio_internal_token=config.INTERNAL_API_TOKEN)
    reuse = json.loads((CONTENT / "reuse.json").read_text())
    for n, (guide, kind, index, item, request_id) in enumerate(segments(frozen), 1):
        if f"{guide['id']}/{kind}/{index}" in reuse:
            continue
        checkpoint = WORK / (request_id + ".json")
        previous = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
        if previous and previous.get("asset"):
            target = ASSETS / previous["asset"]["file"]
            if target.is_file() and sha(target) == previous["asset"]["sha256"]:
                continue
        try:
            receipt = runtime.get_formal_audio_tts(request_id)
        except OpenMaicFullRuntimeError as exc:
            if exc.status_code != 404:
                raise
            if previous:
                raise RuntimeError(f"Uncertain prior dispatch: {request_id}; reconcile the original receipt before continuing") from exc
            # Written BEFORE dispatch: timeout/crash/404 never permits a new paid call.
            save(checkpoint, {"requestId": request_id, "state": "dispatching"})
            receipt = runtime.start_formal_audio_tts(
                request_id=request_id, classroom_id="tbintro_" + digest(frozen)[:32],
                classroom_content_sha256=digest(frozen), subject="chinese",
                teacher_profile_id=teacher.teacher_profile_id, teacher_profile_version=teacher.teacher_profile_version,
                teacher_profile_sha256=teacher.teacher_profile_hash, teacher_gender=teacher.teacher_gender,
                scene_id=guide["id"], scene_order=next(i for i, g in enumerate(frozen["authoring"]["guides"]) if g["id"] == guide["id"]),
                action_id=f"{kind}-{index}", narration_segment_id=f"{kind}-{index}",
                text=item[3], text_sha256=hashlib.sha256(item[3].encode()).hexdigest())
        save(checkpoint, {"requestId": request_id, "receipt": receipt})
        if receipt["status"] != "succeeded":
            raise RuntimeError(f"Original TTS job is {receipt['status']}: {request_id}; no retry dispatched")
        wav = WORK / (request_id + ".wav")
        if not wav.exists() or sha(wav) != receipt["audioSha256"]:
            wav.write_bytes(runtime.download_formal_audio_tts(request_id, expected_sha256=receipt["audioSha256"]))
        mp3 = WORK / (request_id + ".mp3")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-af", "atempo=0.93", "-codec:a", "libmp3lame", "-q:a", "3", str(mp3)], check=True)
        duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(mp3)]))
        assert 1 < duration < 120
        audio_hash = sha(mp3)
        filename = audio_hash + ".mp3"
        (ASSETS / filename).write_bytes(mp3.read_bytes())
        save(checkpoint, {"requestId": request_id, "receipt": receipt, "asset": {"file": filename, "sha256": audio_hash, "durationSeconds": round(duration, 3)}})
        print(json.dumps({"completed": n, "total": 70, "guide": guide["id"], "segment": f"{kind}-{index}"}), flush=True)


def compile_pack(frozen, sources):
    presentations = {}
    reuse = json.loads((CONTENT / "reuse.json").read_text())
    workload = {f"{g['id']}/{kind}/{index}": (item, request_id) for g, kind, index, item, request_id in segments(frozen)}
    for guide, kind, index, item, request_id in segments(frozen):
        narration = item[3]
        replacement = reuse.get(f"{guide['id']}/{kind}/{index}")
        if replacement:
            source_item, request_id = workload[replacement["source"]]
            narration = source_item[3]
        checkpoint = json.loads((WORK / (request_id + ".json")).read_text())
        audio = checkpoint["asset"]
        assert sha(ASSETS / audio["file"]) == audio["sha256"]
        images = list(ASSETS.glob(item[0] + "-*.png"))
        assert len(images) == 1, f"Expected one original atlas for {item[0]}"
        image_hash = sha(images[0])
        assert images[0].stem == item[0] + "-" + image_hash[:16]
        presentation = presentations.setdefault(guide["id"], {
            "schemaVersion": "mira.textbook.picture-guide.v1", "gradeCode": frozen["authoring"]["gradeCode"],
            "sourceContentSha256": sources[guide["id"]], "title": guide["title"], "scenes": [], "choices": [],
        })
        presentation[kind].append({"caption": item[2], "narration": narration,
            "art": {"src": "/textbooks/picture-guide-v1/" + images[0].name, "panel": item[1], "alt": item[2], "sha256": image_hash},
            "audio": {"src": "/textbooks/picture-guide-v1/" + audio["file"], "sha256": audio["sha256"], "durationSeconds": audio["durationSeconds"]}})
    for presentation in presentations.values():
        presentation["presentationSha256"] = digest(presentation)
    result = {k: frozen["authoring"][k] for k in ("editionId", "revisionId", "gradeCode")}
    result.update(schemaVersion="mira.textbook.picture-guide-pack.v1", planSha256=digest({"frozen": frozen, "reuse": reuse}), guides=presentations)
    # No partially generated package can become visible to students.
    from content.textbook_picture_guides import validate_pack
    validate_pack(result)
    save(CONTENT / "published.json", result)
    print(json.dumps({"guides": len(presentations), "audio": sum(len(p["scenes"]) + len(p["choices"]) for p in presentations.values()), "publishedPack": str(CONTENT / "published.json")}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthesize", action="store_true")
    parser.add_argument("--compile", action="store_true")
    args = parser.parse_args()
    if not args.synthesize and not args.compile:
        parser.error("choose --synthesize and/or --compile")
    ASSETS.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    frozen, sources, teacher = plan()
    with (WORK / "operator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        plan_file = WORK / "plan.json"
        if plan_file.exists():
            assert json.loads(plan_file.read_text()) == frozen, "Authoring changed after dispatch; create a new media version"
        else:
            save(plan_file, frozen)
        if args.synthesize:
            synthesize(frozen, teacher)
        if args.compile:
            compile_pack(frozen, sources)


if __name__ == "__main__":
    main()
