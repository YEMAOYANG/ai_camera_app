"""Freeze exact passed audio for a new private candidate of the same task.

Local files only. Never registers a classroom, dispatches a Provider, changes
source evidence, or reuses a low-score/ambiguous/previously inherited segment.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from content.textbook_catalog import digest
from content.textbook_number_spelling import validate_page_number_equivalence
from scripts.narrate_textbook_batch import load_candidate, DEFAULT_CLASSROOM_DIRECTORY
from services.textbook_batch_audio import (
    AUDIO_CLONE_INHERITANCE_SCHEMA, AUDIO_INSERTION_CLONE_SCHEMA, AUDIO_SCENE_INSERTION_CLONE_SCHEMA,
    _inheritance_targets, same_inherited_teaching_cue,
    audio_language_policy_from_plan, build_audio_plan,
)


def prepare(source, target, source_audit_directory, output, *,
            classroom_directory=DEFAULT_CLASSROOM_DIRECTORY, allow_inserted_cues=False,
            allow_inserted_scenes=False):
    if allow_inserted_scenes and not allow_inserted_cues:
        raise ValueError('scene_insertion_requires_explicit_cue_insertion_policy')
    source, target = Path(source).resolve(), Path(target).resolve()
    audit_dir, output = Path(source_audit_directory).resolve(), Path(output).resolve()
    if output.exists() or not output.is_relative_to(target):
        raise ValueError("new_target_inheritance_manifest_required")
    old_input, old_state, old_room = load_candidate(source)
    new_input, new_state, new_room = load_candidate(target)
    if old_input["taskId"] != new_input["taskId"] or old_room["id"] == new_room["id"]:
        raise ValueError("same_task_new_classroom_required")
    plan = json.loads((audit_dir / "plan.json").read_text())
    audit = json.loads((audit_dir / "audit.json").read_text())
    policy = audio_language_policy_from_plan(plan)
    if plan != build_audio_plan(old_room, old_input["binding"], old_state["runtimeOrigin"],
                                audio_language_policy=policy):
        raise ValueError("exact_frozen_source_audio_plan_required")
    target_plan = build_audio_plan(new_room, new_input["binding"], new_state["runtimeOrigin"],
                                   audio_language_policy=policy)
    old_workload = {(x["sceneId"], x["id"]): (i, x) for i, x in enumerate(plan["workload"])}
    new_workload = {(x["sceneId"], x["id"]): (i, x) for i, x in enumerate(target_plan["workload"])}
    entries = []
    for segment in audit["segments"]:
        key = segment["sceneId"], segment["segmentId"]
        unchanged = (key in old_workload and key in new_workload
            and (same_inherited_teaching_cue(old_workload[key][1], new_workload[key][1],
                                             allow_inserted_scenes=allow_inserted_scenes) if allow_inserted_cues
                 else old_workload[key] == new_workload[key]))
        page_proof = segment.get("pageNumberEquivalence")
        if unchanged and page_proof is not None:
            validate_page_number_equivalence(old_workload[key][1]["text"], page_proof)
        if (not unchanged
                or type(segment.get("similarityBps")) is not int or segment["similarityBps"] < 8500
                or (page_proof is None and segment.get("literalScoreBps", segment["similarityBps"]) < 8500)
                or segment.get("inheritedFrom") is not None):
            continue
        entry = {key: segment[key] for key in (
            "sceneId", "segmentId", "textSha256", "ttsRequestId", "asrRequestId", "audioSha256", "similarityBps")}
        for kind in ("tts", "asr"):
            receipt = json.loads((audit_dir / (entry[kind + "RequestId"] + ".json")).read_text())["receipt"]
            entry[kind + "ReceiptSha256"] = digest(receipt)
        entries.append(entry)
    manifest = {
        "schemaVersion": (AUDIO_SCENE_INSERTION_CLONE_SCHEMA if allow_inserted_scenes else
                          AUDIO_INSERTION_CLONE_SCHEMA if allow_inserted_cues else AUDIO_CLONE_INHERITANCE_SCHEMA),
        "taskId": new_input["taskId"], "sourceCandidateDirectory": str(source),
        "targetCandidateDirectory": str(target), "sourceAudioAuditDirectory": str(audit_dir),
        "sourcePlanSha256": digest(plan), "sourceAuditSha256": digest(audit),
        "sourceSha256": plan["sourceSha256"], "targetPlanSha256": digest(target_plan),
        "targetSourceSha256": target_plan["sourceSha256"], "segments": entries,
    }
    audit_name = "audio-audit-english-auto-v1" if policy is not None else "audio-audit"
    if any(s.get("pageNumberEquivalence") is not None for s in audit["segments"]):
        audit_name = "audio-audit-page-numbers-v1"
    checked = _inheritance_targets(manifest, target_plan, target / audit_name,
        Path(classroom_directory).resolve() / new_room["id"] / "audio",
        get_formal_subject_qwen_voice_identity(new_input["binding"]["subject"]))
    assert len(checked) == len(entries)
    # Exclusive creation: no source files or old authorization manifests change.
    with output.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return {"taskId": new_input["taskId"], "classroomId": new_room["id"],
            "inheritedSegments": len(entries), "totalSegments": len(target_plan["workload"]),
            "remainingSegments": len(target_plan["workload"]) - len(entries),
            "manifestPath": str(output), "providerCalls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source-candidate-directory", "target-candidate-directory",
                 "source-audio-audit-directory", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--allow-inserted-cues", action="store_true",
                        help="Use v3 lineage to retain unchanged paid audio when new cues are inserted; existing cues cannot move")
    parser.add_argument("--allow-inserted-scenes", action="store_true",
                        help="With --allow-inserted-cues, use v4 lineage for new scenes; original scene and cue order must remain")
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_candidate_directory, args.target_candidate_directory,
        args.source_audio_audit_directory, args.output,
        allow_inserted_cues=args.allow_inserted_cues,
        allow_inserted_scenes=args.allow_inserted_scenes), ensure_ascii=False))


if __name__ == "__main__":
    main()
