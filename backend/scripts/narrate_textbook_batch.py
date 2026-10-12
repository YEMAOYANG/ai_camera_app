"""Narrate one exact saved private candidate; never approve or publish it.

Only an explicit CLI invocation loads runtime configuration or dispatches paid
Qwen TTS/ASR. Invalid local snapshots fail before configuration or network use.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content.textbook_batch_generation import HASH, INPUT_SCHEMA, KINDS
from content.textbook_catalog import digest, validate_manifest
from content.textbook_pedagogy import teaching_profile
from content.teacher_profiles import get_formal_subject_qwen_voice_identity, get_teacher_profile, get_formal_runtime_teacher_contract

DEFAULT_CLASSROOM_DIRECTORY = ROOT.parent / "openmaic-runtime/.runtime/OpenMAIC/data/classrooms"


def load_candidate(directory):
    """Cross-check frozen input, generation receipt, classroom and exact scope."""
    directory = Path(directory).resolve()
    frozen, state, classroom = [json.loads((directory / name).read_text(encoding="utf-8"))
                                for name in ("input.json", "state.json", "classroom.json")]
    if not all(isinstance(value, dict) for value in (frozen, state, classroom)):
        raise ValueError("candidate_artifact_shape_invalid")
    if (frozen.get("schemaVersion") != INPUT_SCHEMA
            or HASH.fullmatch(str(frozen.get("taskId", ""))) is None
            or directory.name != frozen["taskId"]
            or frozen.get("inputSha256") != digest({key: value for key, value in frozen.items() if key != "inputSha256"})
            or frozen.get("publicationAllowed") is not False or frozen.get("studentDeliveryAllowed") is not False):
        raise ValueError("frozen_candidate_input_integrity_failed")
    if (state.get("schemaVersion") != "mira.textbook.private-batch-generation-state.v1"
            or state.get("status") != "generated_needs_review"
            or state.get("taskId") != frozen["taskId"] or state.get("inputSha256") != frozen["inputSha256"]
            or state.get("publicationAllowed") is not False or state.get("studentDeliveryAllowed") is not False
            or state.get("classroomSha256") != digest(classroom)
            or state.get("classroomId") != classroom.get("id")
            or classroom.get("stage", {}).get("id") != classroom.get("id")):
        raise ValueError("saved_candidate_state_or_classroom_integrity_failed")
    binding = frozen.get("binding")
    manifest = frozen.get("manifest")
    if not isinstance(binding, dict) or not isinstance(manifest, dict):
        raise ValueError("exact_textbook_binding_required")
    validate_manifest(manifest)
    if (digest(manifest) != frozen.get("manifestSha256")
            or any(binding.get(key) != manifest[key] for key in
                   ("editionId", "revisionId", "gradeCode", "subject", "schoolSystem", "volume"))
            or frozen.get("teachingProfile") != teaching_profile(binding["gradeCode"])):
        raise ValueError("candidate_textbook_scope_or_grade_changed")
    kind = frozen.get("kind")
    unit = next((entry for entry in manifest["units"] if entry["unitId"] == binding.get("unitId")), None)
    lesson = next((entry for entry in (unit or {}).get("lessons", []) if entry["nodeId"] == binding.get("nodeId")), None)
    if (kind not in KINDS
            or kind == "book_exploration" and (binding.get("unitId") is not None or binding.get("nodeId") is not None)
            or kind == "unit_guide" and (unit is None or binding.get("nodeId") is not None)
            or kind == "lesson_courseware" and (unit is None or lesson is None)):
        raise ValueError("candidate_unit_or_lesson_scope_changed")
    if frozen.get("authoringPrompt", {}).get("version") in {"2", "3", "4"}:
        identity = get_formal_subject_qwen_voice_identity(binding["subject"])
        teacher = identity.to_target_payload()
        runtime_teacher = get_formal_runtime_teacher_contract(binding["subject"])["runtime"]
        teacher["avatarPath"] = runtime_teacher["avatar"]
        # Early v2 inputs froze the mobile portrait path. Preserve those paid
        # inputs, while requiring their repaired classroom to use the actual
        # registered runtime portrait before narration can dispatch.
        legacy_teacher = {**teacher, "avatarPath": get_teacher_profile(
            identity.teacher_profile_id, identity.teacher_profile_version).avatar_path}
        context = frozen.get("runtimeBatchContext", {})
        if (context.get("teacher") not in (teacher, legacy_teacher) or context.get("binding") != binding
                or context.get("taskId") != frozen["taskId"] or context.get("kind") != kind
                or context.get("gradeCode") != binding["gradeCode"] or context.get("subject") != binding["subject"]):
            raise ValueError("candidate_frozen_teacher_or_runtime_scope_changed")
        teachers = [entry for entry in classroom.get("stage", {}).get("generatedAgentConfigs", [])
                    if isinstance(entry, dict) and entry.get("role") == "teacher"]
        if (len(teachers) != 1 or teachers[0].get("name") != teacher["teacherName"]
                or teachers[0].get("avatar") != runtime_teacher["avatar"]
                or teachers[0].get("teacherProfile") != teacher["teacherProfile"]
                or teachers[0].get("voiceConfig") != runtime_teacher["voiceConfig"]):
            raise ValueError("candidate_visible_teacher_or_portrait_changed")
    return frozen, state, classroom


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-directory", type=Path, required=True)
    parser.add_argument("--classroom-directory", type=Path, default=DEFAULT_CLASSROOM_DIRECTORY)
    parser.add_argument("--output", type=Path, help="Durable audio audit directory; default candidate/audio-audit")
    parser.add_argument('--allow-page-number-equivalence', action='store_true',
                        help='Exact Chinese/Arabic page-number spelling only; requires separate audit output')
    parser.add_argument("--audio-language-policy", choices=["english-auto-v1"],
                        help="Opt in to the versioned English Auto TTS/ASR plan; requires a separate --output")
    parser.add_argument("--asr-reconciliation-file", type=Path,
                        help="Explicit exact manifest for one ASR review of known successful, low-similarity audio")
    parser.add_argument("--audio-inheritance-file", type=Path, action="append",
                        help="Explicit frozen lineage for unchanged passed audio; repeat for distinct source audits")
    args = parser.parse_args(argv)
    try:
        frozen, state, classroom = load_candidate(args.candidate_directory)
        if args.audio_language_policy is not None:
            if (frozen["binding"]["subject"] != "english" or args.output is None
                    or args.output.resolve() == (args.candidate_directory / "audio-audit").resolve()
                    or args.output.name == "audio-audit"):
                raise ValueError("english_auto_language_requires_english_and_distinct_explicit_output")
        # Import configuration only after immutable local artifacts pass checks.
        from core.config import AppConfig
        from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
        from services.textbook_batch_audio import (narrate_candidate, load_asr_reconciliation_file,
                                                   load_audio_inheritance_file)
        reconciliation = (load_asr_reconciliation_file(args.asr_reconciliation_file)
                          if args.asr_reconciliation_file else None)
        inheritance_files = [load_audio_inheritance_file(path) for path in (args.audio_inheritance_file or [])]
        inheritance = (inheritance_files[0] if len(inheritance_files) == 1 else inheritance_files) or None
        config = AppConfig.from_env()
        runtime = OpenMaicFullRuntimeClient(config.OPENMAIC_FULL_RUNTIME_INTERNAL_URL,
                                           formal_audio_internal_token=config.INTERNAL_API_TOKEN)
        if state.get("runtimeOrigin") != runtime.base_url:
            raise ValueError("candidate_belongs_to_different_runtime")
        output = args.output or args.candidate_directory / "audio-audit"
        if args.allow_page_number_equivalence and (args.output is None
                or output.name != 'audio-audit-page-numbers-v1'
                or not output.resolve().is_relative_to(args.candidate_directory.resolve())):
            raise ValueError('page_number_review_requires_distinct_owned_audit')

        def progress(value):
            print(json.dumps({"status": "narrating", "completedSegments": value["completed"],
                              "expectedSegments": value["total"], "similarityBps": value["similarityBps"],
                              "publicationAllowed": False}), flush=True)

        result = narrate_candidate(runtime, classroom, frozen["binding"], output,
                                   args.classroom_directory, progress=progress,
                                   asr_reconciliation=reconciliation, audio_inheritance=inheritance,
                                   **({'allow_page_number_equivalence': True}
                                      if args.allow_page_number_equivalence else {}),
                                   **({"audio_language_policy": args.audio_language_policy}
                                      if args.audio_language_policy is not None else {}))
        print(json.dumps({"ok": True, "status": "audio_completed_needs_review",
                          "expectedSegments": result["expectedSegments"],
                          "completedSegments": result["completedSegments"],
                          "allSegmentsPassed": result["allSegmentsPassed"],
                          "semanticPronunciationReview": result["semanticPronunciationReview"],
                          "interactiveStateNarrationReview": result["interactiveStateNarrationReview"],
                          "publicationAllowed": False, "studentDeliveryAllowed": False}), flush=True)
        return 0
    except Exception as exc:
        # Raw provider exceptions can include private request text or headers.
        print(json.dumps({"ok": False, "status": "audio_stopped_needs_reconciliation",
                          "errorType": type(exc).__name__, "publicationAllowed": False,
                          "studentDeliveryAllowed": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
