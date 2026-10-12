#!/usr/bin/env python3
"""Prepare, then explicitly save a local private preview with fresh identities.

Uses only the existing classroom GET/POST API. No generation, TTS, ASR,
publication, database writes, IndexedDB operations or source modifications.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content.textbook_catalog import digest
from content.textbook_interactive_narration import AUDIO_BLOCK, interactive_cues, without_audio_helper
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from scripts.narrate_textbook_batch import DEFAULT_CLASSROOM_DIRECTORY, load_candidate
from services.textbook_batch_audio import (audio_language_policy_from_plan, build_audio_plan,
                                          narration_workload, save_json)
from services.textbook_preview_audio import core_content
from content.textbook_number_spelling import validate_page_number_equivalence
from services.learning_media_materialization_service import asr_similarity_bps

SCHEMA = "mira.textbook.private-preview-snapshot.v1"
IDENTITY = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(131072), b""):
            result.update(chunk)
    return result.hexdigest()


def persisted_content(classroom):
    """The existing API normalizes only the top-level creation timestamp."""
    value = deepcopy(classroom)
    value.pop("createdAt", None)
    return value


def teaching_core(classroom):
    value = core_content(classroom)
    for scene in value.get("scenes", []):
        if scene.get("type") == "interactive":
            html = scene.get("content", {}).get("html")
            if isinstance(html, str):
                scene["content"]["html"] = without_audio_helper(html)
        for question in scene.get("content", {}).get("questions", []):
            question.pop("questionAudioUrl", None)
            question.pop("feedbackAudioUrl", None)
    return value


def local_origin(value):
    parsed = urlparse(value)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise ValueError("private_preview_local_runtime_required")
    return value.rstrip("/")


def document(path, role):
    path = Path(path).resolve()
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("private_preview_document_invalid")
    return value, {"role": role, "path": str(path), "byteSha256": hashlib.sha256(raw).hexdigest(),
                   "canonicalSha256": digest(value)}


def verify_sources(manifest):
    for source in manifest["sourceDocuments"]:
        if file_hash(source["path"]) != source["byteSha256"]:
            raise ValueError("private_preview_source_document_changed")
    for asset in manifest["audioAssets"]:
        if file_hash(asset["path"]) != asset["audioSha256"]:
            raise ValueError("private_preview_source_audio_changed")


def verify_complete_audio(original, narrated, plan, audit, media_directory):
    """Check saved evidence and bindings; never infer semantic approval."""
    if (digest(original) != plan.get("sourceSha256")
            or teaching_core(original) != teaching_core(narrated)
            or digest(teaching_core(narrated)) != plan.get("coreSha256")):
        raise ValueError("private_preview_narrated_source_mismatch")
    workload = narration_workload(original)
    auto_language = audio_language_policy_from_plan(plan) is not None
    segments = audit.get("segments", [])
    if (audit.get("schemaVersion") != "mira.textbook.batch-audio-audit.v1"
            or audit.get("publicationAllowed") is not False or audit.get("allSegmentsPassed") is not True
            or audit.get("expectedSegments") != len(workload) or audit.get("completedSegments") != len(workload)
            or not isinstance(segments, list) or len(segments) != len(workload)
            or audit.get("planSha256") != digest(plan)
            or audit.get("sha256") != digest({key: value for key, value in audit.items() if key != "sha256"})):
        raise ValueError("private_preview_complete_audio_audit_required")
    source_id = original["id"]
    media_root = Path(media_directory).resolve()
    source_root = (media_root / source_id / "audio").resolve()
    if media_root not in source_root.parents:
        raise ValueError("private_preview_audio_path_invalid")
    scenes = {scene["id"]: scene for scene in narrated["scenes"]}
    if len(scenes) != len(narrated["scenes"]):
        raise ValueError("private_preview_duplicate_scene")
    expected_interactive = {}
    assets, seen = [], set()
    for item, segment in zip(workload, segments):
        key = item["sceneId"], item["id"]
        tts_id = segment.get("ttsRequestId", "")
        audio_hash = segment.get("audioSha256", "")
        if (key in seen or segment.get("sceneId") != key[0] or segment.get("segmentId") != key[1]
                or segment.get("textSha256") != hashlib.sha256(item["text"].encode()).hexdigest()
                or not IDENTITY.fullmatch(tts_id) or not HASH.fullmatch(audio_hash)
                or not isinstance(segment.get("similarityBps"), int) or segment["similarityBps"] < 8500):
            raise ValueError("private_preview_audio_segment_mismatch")
        if auto_language and (not re.fullmatch(r"tbbtts2_[0-9a-f]{64}", tts_id)
                or not re.fullmatch(r"(?:tbbasr2|tbbreasr2)_[0-9a-f]{64}", str(segment.get("asrRequestId", "")))):
            raise ValueError("private_preview_audio_language_namespace_mismatch")
        if 'pageNumberEquivalence' in segment:
            receipt = validate_page_number_equivalence(item['text'], segment['pageNumberEquivalence'])
            if (plan.get('binding', {}).get('subject') != 'chinese'
                    or receipt.get('requestId') != segment.get('asrRequestId')
                    or segment['similarityBps'] != 10000
                    or segment.get('literalScoreBps') != asr_similarity_bps(item['text'], receipt['transcript'])):
                raise ValueError('private_preview_page_number_evidence_mismatch')
        seen.add(key)
        url = f"/api/classroom-media/{source_id}/audio/{tts_id}.wav"
        if segment.get("audioUrl") != url:
            raise ValueError("private_preview_source_audio_url_changed")
        path = (source_root / f"{tts_id}.wav").resolve()
        if source_root not in path.parents or file_hash(path) != audio_hash:
            raise ValueError("private_preview_source_audio_changed")
        scene = scenes[item["sceneId"]]
        if item["kind"] == "speech":
            action = next((a for a in scene.get("actions", []) if a.get("id") == item["id"]), None)
            expected_metadata = {"schemaVersion": "mira.openmaic.speech-audio.v1",
                "providerId": plan["teacher"]["tts"]["providerId"], "modelId": plan["teacher"]["tts"]["modelId"],
                "voiceId": plan["teacher"]["voiceId"], "fallbackUsed": False}
            if (not action or action.get("audioId") != tts_id or action.get("audioUrl") != url
                    or action.get("audioMetadata") != expected_metadata):
                raise ValueError("private_preview_speech_binding_mismatch")
        elif item["kind"] == "interactive":
            expected_interactive.setdefault(item["sceneId"], {})[item["cueId"]] = url
        else:
            question = next((q for q in scene.get("content", {}).get("questions", [])
                             if q.get("id") == item["questionId"]), None)
            field = "questionAudioUrl" if item["kind"] == "prompt" else "feedbackAudioUrl"
            if not question or question.get(field) != url:
                raise ValueError("private_preview_quiz_binding_mismatch")
        assets.append({"sceneId": key[0], "segmentId": key[1], "textSha256": segment["textSha256"],
            "ttsRequestId": tts_id, "asrRequestId": segment.get("asrRequestId"), "audioSha256": audio_hash,
            "audioUrl": url, "path": str(path), "byteLength": path.stat().st_size})
    for scene in narrated["scenes"]:
        if scene.get("type") != "interactive":
            continue
        html = scene.get("content", {}).get("html", "")
        without_audio_helper(html)  # Reject modified or ambiguous helper code.
        cues, blocks = interactive_cues(html), AUDIO_BLOCK.findall(html)
        expected = expected_interactive.get(scene["id"], {})
        if not cues and not expected and not blocks:
            continue
        if len(blocks) != 1:
            raise ValueError("private_preview_interactive_audio_incomplete")
        urls = json.loads(blocks[0].split("const clips=", 1)[1].split(";let active=null;", 1)[0])
        if urls != expected or set(urls) != {cue["id"] for cue in cues}:
            raise ValueError("private_preview_interactive_audio_incomplete")
    return assets


def make_alias(narrated, alias_id):
    if (not IDENTITY.fullmatch(alias_id) or len(alias_id) > 104 or not alias_id.startswith("tbprivate_")
            or alias_id == narrated.get("id") or narrated.get("stage", {}).get("id") != narrated.get("id")
            or set(narrated) - {"id", "createdAt", "stage", "scenes"}):
        raise ValueError("private_preview_alias_identity_invalid")
    alias = deepcopy(narrated)
    source_id = narrated["id"]
    mapping = {scene["id"]: f"{alias_id}_s{index:03d}" for index, scene in enumerate(narrated["scenes"], 1)}
    if len(mapping) != len(narrated["scenes"]) or source_id in mapping:
        raise ValueError("private_preview_source_scene_identity_invalid")
    references = {"stageId", "classroomId", "sceneId", "fromSceneId", "toSceneId", "targetSceneId", "nextSceneId"}

    def rewrite(value):
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, item in value.items():
            if key == "audioMetadata":
                result[key] = deepcopy(item)
            elif key in references and isinstance(item, str):
                result[key] = alias_id if item == source_id else mapping.get(item, item)
            else:
                result[key] = rewrite(item)
        return result

    alias = rewrite(alias)
    alias["id"], alias["stage"]["id"] = alias_id, alias_id
    for scene in alias["scenes"]:
        old = scene["id"]
        scene["id"], scene["stageId"] = mapping[old], alias_id
    return alias, mapping


def prepare_snapshot(candidate_directory, output, *, audio_audit_directory=None,
                     classroom_directory=DEFAULT_CLASSROOM_DIRECTORY, alias_id=None):
    candidate, output = Path(candidate_directory).resolve(), Path(output).resolve()
    audit_dir = Path(audio_audit_directory or candidate / "audio-audit").resolve()
    if output.exists() or output == candidate or candidate in output.parents or audit_dir in output.parents:
        raise ValueError("private_preview_requires_new_separate_output_directory")
    frozen, state, original = load_candidate(candidate)
    origin = local_origin(state["runtimeOrigin"])
    loaded, evidence = {}, []
    for role, path in [("input", candidate / "input.json"), ("state", candidate / "state.json"),
        ("classroom", candidate / "classroom.json"), ("audioPlan", audit_dir / "plan.json"),
        ("audioAudit", audit_dir / "audit.json"), ("narratedClassroom", audit_dir / "narrated-classroom.json")]:
        loaded[role], source = document(path, role)
        evidence.append(source)
    if loaded["input"] != frozen or loaded["state"] != state or loaded["classroom"] != original:
        raise ValueError("private_preview_source_changed_during_read")
    plan, audit, narrated = loaded["audioPlan"], loaded["audioAudit"], loaded["narratedClassroom"]
    if plan != build_audio_plan(original, frozen["binding"], origin,
                               audio_language_policy=audio_language_policy_from_plan(plan)):
        raise ValueError("private_preview_audio_plan_mismatch")
    assets = verify_complete_audio(original, narrated, plan, audit, classroom_directory)
    alias, mapping = make_alias(narrated, alias_id or "tbprivate_" + uuid4().hex[:24])
    manifest = {"schemaVersion": SCHEMA, "purpose": "private_operator_acceptance_preview_alias",
        "createdAt": datetime.now(timezone.utc).isoformat(), "publicationAllowed": False,
        "studentDeliveryAllowed": False, "runtimeOrigin": origin, "sourceClassroomId": original["id"],
        "aliasClassroomId": alias["id"], "taskId": frozen["taskId"], "binding": frozen["binding"],
        "teacher": plan["teacher"], "sourceDocuments": evidence, "audioAssets": assets,
        "sourceSha256": plan["sourceSha256"], "audioPlanSha256": digest(plan), "audioAuditSha256": digest(audit),
        "narratedClassroomSha256": digest(narrated), "expectedRuntimeCoreSha256": plan["coreSha256"],
        "expectedRuntimeNarratedSha256": digest(persisted_content(narrated)),
        "aliasClassroomSha256": digest(alias), "aliasPersistedSha256": digest(persisted_content(alias)),
        "sceneIdMapping": mapping, "audioUrlsRewritten": False, "mediaUrlsRewritten": False,
        "htmlRewritten": False, "sourceCandidateModified": False, "providerCalls": 0,
        "semanticPronunciationReview": audit.get("semanticPronunciationReview", "pending"),
        "interactiveStateNarrationReview": audit.get("interactiveStateNarrationReview", "pending"),
        "saveContract": {"api": "existing local GET/POST /api/classroom", "explicitSaveRequired": True,
            "unknownAliasContent": "stop", "ambiguousPriorSaveAndAliasMissing": "stop_without_repost",
            "existingExactAlias": "read_only_reconcile", "atomicCompareAndSwapAvailable": False}}
    verify_sources(manifest)
    manifest["snapshotSha256"] = digest(manifest)
    output.mkdir(parents=True)
    save_json(output / "source-narrated-classroom.json", narrated)
    save_json(output / "classroom.json", alias)
    save_json(output / "snapshot.json", manifest)
    return manifest


def load_snapshot(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "snapshot.json").read_text())
    alias = json.loads((directory / "classroom.json").read_text())
    narrated = json.loads((directory / "source-narrated-classroom.json").read_text())
    if (manifest.get("schemaVersion") != SCHEMA or manifest.get("publicationAllowed") is not False
            or manifest.get("studentDeliveryAllowed") is not False
            or manifest.get("snapshotSha256") != digest({k: v for k, v in manifest.items() if k != "snapshotSha256"})
            or manifest.get("aliasClassroomSha256") != digest(alias)
            or manifest.get("narratedClassroomSha256") != digest(narrated)
            or manifest.get("aliasPersistedSha256") != digest(persisted_content(alias))
            or manifest.get("expectedRuntimeNarratedSha256") != digest(persisted_content(narrated))
            or manifest.get("expectedRuntimeCoreSha256") != digest(teaching_core(narrated))):
        raise ValueError("private_preview_snapshot_integrity_failed")
    expected, mapping = make_alias(narrated, manifest["aliasClassroomId"])
    if expected != alias or mapping != manifest.get("sceneIdMapping"):
        raise ValueError("private_preview_alias_content_changed")
    local_origin(manifest["runtimeOrigin"])
    verify_sources(manifest)
    return directory, manifest, alias


def save_snapshot(directory, runtime, *, expected_runtime_core_sha256=None):
    directory, manifest, alias = load_snapshot(directory)
    if (local_origin(runtime.base_url) != manifest["runtimeOrigin"] or
            expected_runtime_core_sha256 not in (None, manifest["expectedRuntimeCoreSha256"])):
        raise ValueError("private_preview_expected_runtime_identity_mismatch")
    with (directory / "operator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        checkpoint_path = directory / "save-state.json"
        checkpoint = json.loads(checkpoint_path.read_text()) if checkpoint_path.exists() else None
        if checkpoint and checkpoint.get("snapshotSha256") != manifest["snapshotSha256"]:
            raise ValueError("private_preview_save_checkpoint_conflict")

        def source_check():
            source = runtime.get_classroom(manifest["sourceClassroomId"])
            if (source.get("id") != manifest["sourceClassroomId"]
                    or digest(teaching_core(source)) != manifest["expectedRuntimeCoreSha256"]
                    or digest(persisted_content(source)) != manifest["expectedRuntimeNarratedSha256"]):
                raise ValueError("private_preview_runtime_source_changed")

        def existing_alias():
            try:
                existing = runtime.get_classroom(manifest["aliasClassroomId"])
            except OpenMaicFullRuntimeError as exc:
                if exc.status_code == 404:
                    return None
                raise
            if (existing.get("id") != manifest["aliasClassroomId"] or
                    digest(persisted_content(existing)) != manifest["aliasPersistedSha256"]):
                raise ValueError("private_preview_alias_already_exists_with_unknown_content")
            return existing

        source_check()
        existing = existing_alias()
        saved_now = False
        if existing is None:
            if checkpoint and checkpoint.get("dispatchAttempted"):
                raise RuntimeError("private_preview_ambiguous_save_missing_no_repost")
            # Fresh random IDs plus local locking avoid reusing editor caches.
            # The existing API has no CAS; never claim atomic exclusion of an
            # independent writer between this final check and its POST.
            source_check()
            existing = existing_alias()
            if existing is None:
                checkpoint = {"schemaVersion": "mira.textbook.private-preview-save.v1",
                    "snapshotSha256": manifest["snapshotSha256"], "aliasClassroomId": alias["id"],
                    "dispatchAttempted": True, "status": "saving", "publicationAllowed": False}
                save_json(checkpoint_path, checkpoint)
                try:
                    runtime.save_preview_classroom(alias)
                    existing = existing_alias()
                    if existing is None:
                        raise RuntimeError("private_preview_saved_alias_not_found")
                except Exception as exc:
                    checkpoint.update(status="save_outcome_unknown_needs_reconciliation", errorType=type(exc).__name__)
                    save_json(checkpoint_path, checkpoint)
                    raise
                saved_now = True
        receipt = {"schemaVersion": "mira.textbook.private-preview-save-receipt.v1",
            "snapshotSha256": manifest["snapshotSha256"], "aliasClassroomId": alias["id"],
            "sourceClassroomId": manifest["sourceClassroomId"], "status": "saved_private_preview" if saved_now else "existing_exact_preview_reconciled",
            "sourceRuntimeCoreSha256": manifest["expectedRuntimeCoreSha256"],
            "readbackSha256": digest(existing), "readbackPersistedSha256": digest(persisted_content(existing)),
            "url": manifest["runtimeOrigin"] + "/classroom/" + alias["id"], "audioUrlsRewritten": False,
            "sourceModified": False, "publicationAllowed": False, "studentDeliveryAllowed": False,
            "atomicCompareAndSwapAvailable": False}
        save_json(directory / "save-receipt.json", receipt)
        save_json(checkpoint_path, {"schemaVersion": "mira.textbook.private-preview-save.v1",
            "snapshotSha256": manifest["snapshotSha256"], "aliasClassroomId": alias["id"],
            "dispatchAttempted": bool(saved_now or checkpoint and checkpoint.get("dispatchAttempted")),
            "status": "readback_verified", "publicationAllowed": False})
        return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Pure local preparation; no API calls")
    prepare.add_argument("--candidate-directory", type=Path, required=True)
    prepare.add_argument("--audio-audit-directory", type=Path)
    prepare.add_argument("--classroom-directory", type=Path, default=DEFAULT_CLASSROOM_DIRECTORY)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--alias-id")
    save = commands.add_parser("save", help="Explicitly save the prepared alias over the existing local API")
    save.add_argument("--snapshot-directory", type=Path, required=True)
    save.add_argument("--expected-runtime-core-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_snapshot(args.candidate_directory, args.output,
                audio_audit_directory=args.audio_audit_directory, classroom_directory=args.classroom_directory,
                alias_id=args.alias_id)
            status = "prepared_private_preview_not_saved"
        else:
            _, manifest, _ = load_snapshot(args.snapshot_directory)
            runtime = OpenMaicFullRuntimeClient(local_origin(manifest["runtimeOrigin"]))
            result = save_snapshot(args.snapshot_directory, runtime,
                                  expected_runtime_core_sha256=args.expected_runtime_core_sha256)
            status = result["status"]
        print(json.dumps({"ok": True, "status": status, "aliasClassroomId": result["aliasClassroomId"],
            "snapshotSha256": result["snapshotSha256"], "url": result.get("url"),
            "publicationAllowed": False, "studentDeliveryAllowed": False}))
        return 0
    except Exception as exc:
        message = str(exc)
        code = (message if re.fullmatch(r"private_preview_[a-z_]+", message)
                else getattr(exc, "code", "private_preview_operation_failed"))
        print(json.dumps({"ok": False, "status": "private_preview_stopped", "errorType": type(exc).__name__,
            "errorCode": code,
            "publicationAllowed": False, "studentDeliveryAllowed": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
