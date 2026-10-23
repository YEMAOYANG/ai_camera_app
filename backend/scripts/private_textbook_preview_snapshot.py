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
from content.textbook_interactive_narration import (AUDIO_BLOCK, bind_interactive_audio,
                                                     interactive_cues, without_audio_helper)
from content.textbook_asr_source_reuse import decoded as origin_bytes, validate_audit as validate_origin_audit
from content.textbook_pinyin_pronunciation import (PLAN_SCHEMA as PINYIN_PLAN_SCHEMA,
                                                   policy_for_plan, validate_receipt_wav)
from content.textbook_preview_audio_contract import validate_child_request_plan
from core.errors import ApiError
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from scripts.narrate_textbook_batch import DEFAULT_CLASSROOM_DIRECTORY, load_candidate
from services.textbook_batch_audio import (audio_language_policy_from_plan, build_audio_plan,
                                          narration_workload, save_json)
from services.textbook_preview_audio import core_content, segment_request_plan, verify_segment_receipt
from content.textbook_number_spelling import validate_page_number_equivalence
from services.learning_media_materialization_service import asr_similarity_bps

SCHEMA = "mira.textbook.private-preview-snapshot.v1"
PINYIN_ORIGIN_SCHEMA = "mira.textbook.private-preview-snapshot.v2-pinyin-origin"
PINYIN_ORIGIN_SOURCE_CONTRACT = {
    "schemaVersion": "mira.textbook.private-preview-pinyin-origin-source.v1",
    "audioPlanSchemaVersion": PINYIN_PLAN_SCHEMA,
    "audioAuditSchemaVersion": "mira.textbook.audio-audit.v3-asr-origin",
    "completeSpeechReceiptAndWavCoverage": True,
    "interactiveHelperAndQuestionAudioBound": True,
}
LEGACY_FIXED_PLAYBACK_CONTRACT = {"schemaVersion": "mira.textbook.private-preview-playback.v1", "fixedTextbook": True}
PLAYBACK_CONTRACT = {"schemaVersion": "mira.textbook.private-preview-playback.v2",
                     "pageManagedNarration": True, "studentGrading": False}
IDENTITY = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")


def _save_contract():
    return {"api": "existing local GET/POST /api/classroom", "explicitSaveRequired": True,
        "unknownAliasContent": "stop", "ambiguousPriorSaveAndAliasMissing": "stop_without_repost",
        "existingExactAlias": "read_only_reconcile", "atomicCompareAndSwapAvailable": False}


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


def document(path, role, *, container=dict):
    path = Path(path).resolve()
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, container):
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


def _media_path(value, runtime_origin, expected):
    """Accept only this local runtime's exact media path."""
    if not isinstance(value, str) or not value:
        raise ValueError("private_preview_pinyin_audio_url_invalid")
    parsed, runtime = urlparse(value), urlparse(runtime_origin)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.params:
        raise ValueError("private_preview_pinyin_audio_url_invalid")
    if parsed.scheme or parsed.netloc:
        if ((parsed.scheme, parsed.hostname, parsed.port) != (runtime.scheme, runtime.hostname, runtime.port)
                or parsed.path != expected):
            raise ValueError("private_preview_pinyin_audio_url_invalid")
    elif value != expected or parsed.path != expected:
        raise ValueError("private_preview_pinyin_audio_url_invalid")
    return expected


def verify_pinyin_playback_bindings(classroom, audio_ids, runtime_origin):
    """Verify finite interactive and quiz playback against formal speech."""
    if (not isinstance(classroom, dict) or not IDENTITY.fullmatch(str(classroom.get("id", "")))
            or not isinstance(classroom.get("stage"), dict)
            or classroom["stage"].get("id") != classroom["id"]
            or "fixedTextbook" in classroom["stage"]
            or "miraTextbookPreviewNarration" in classroom["stage"]
            or not isinstance(classroom.get("scenes"), list)):
        raise ValueError("private_preview_pinyin_source_classroom_invalid")
    source_id = classroom["id"]
    question_ids = set()
    for scene in classroom["scenes"]:
        actions = [item for item in scene.get("actions", [])
                   if isinstance(item, dict) and item.get("type") == "speech"]
        by_text = {}
        for action in actions:
            text = str(action.get("text") or "").strip()
            request_id = action.get("audioId")
            if not text or request_id not in audio_ids:
                raise ValueError("private_preview_pinyin_speech_binding_mismatch")
            path = f"/api/classroom-media/{source_id}/audio/{request_id}.wav"
            _media_path(action.get("audioUrl"), runtime_origin, path)
            by_text.setdefault(text, []).append(action)
        if scene.get("type") == "interactive":
            html = scene.get("content", {}).get("html")
            if not isinstance(html, str):
                raise ValueError("private_preview_pinyin_interactive_helper_invalid")
            cues = interactive_cues(html)
            without_audio_helper(html)
            if not cues:
                if AUDIO_BLOCK.findall(html):
                    raise ValueError("private_preview_pinyin_interactive_helper_invalid")
            else:
                clips = {}
                for cue in cues:
                    matches = by_text.get(cue["text"], [])
                    if len(matches) != 1:
                        raise ValueError("private_preview_pinyin_interactive_helper_invalid")
                    clips[cue["id"]] = _media_path(matches[0]["audioUrl"], runtime_origin,
                        f"/api/classroom-media/{source_id}/audio/{matches[0]['audioId']}.wav")
                if html != bind_interactive_audio(html, clips, source_id):
                    raise ValueError("private_preview_pinyin_interactive_helper_invalid")
        if scene.get("type") == "quiz":
            questions = scene.get("content", {}).get("questions")
            if not isinstance(questions, list) or not questions:
                raise ValueError("private_preview_pinyin_question_audio_invalid")
            for question in questions:
                if (not isinstance(question, dict) or not IDENTITY.fullmatch(str(question.get("id", "")))
                        or question["id"] in question_ids):
                    raise ValueError("private_preview_pinyin_question_audio_invalid")
                question_ids.add(question["id"])
                matches = by_text.get(str(question.get("question") or "").strip(), [])
                if len(matches) != 1:
                    raise ValueError("private_preview_pinyin_question_audio_invalid")
                action = matches[0]
                expected = f"/api/classroom-media/{source_id}/audio/{action['audioId']}.wav"
                _media_path(question.get("questionAudioUrl"), runtime_origin, expected)
    return {"interactiveScenes": sum(s.get("type") == "interactive" for s in classroom["scenes"]),
            "quizQuestions": len(question_ids)}


def _archive_json(path, container=dict):
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError, TypeError):
        raise ValueError("private_preview_pinyin_revision_archive_invalid")
    if not isinstance(value, container):
        raise ValueError("private_preview_pinyin_revision_archive_invalid")
    return value


def _receipt_ids(receipts):
    if not isinstance(receipts, list):
        raise ValueError("private_preview_pinyin_receipts_invalid")
    ids = [item.get("requestId") for item in receipts if isinstance(item, dict)]
    if len(ids) != len(receipts) or any(not IDENTITY.fullmatch(str(item or "")) for item in ids) \
            or len(set(ids)) != len(ids):
        raise ValueError("private_preview_pinyin_receipts_invalid")
    return ids


def verify_pinyin_revision_lineage(classroom, plan, receipts, folder, *,
                                    expected_source_sha256, expected_core_sha256):
    """Verify every committed narration amendment from its original source to final save."""
    revision_root = Path(folder) / "narration-revisions"
    if revision_root.is_symlink():
        raise ValueError("private_preview_pinyin_revision_archive_invalid")
    directories = ([item for item in revision_root.iterdir() if item.is_dir()]
                   if revision_root.is_dir() else [])
    if not directories:
        if plan.get("coreSha256") != expected_core_sha256:
            raise ValueError("private_preview_pinyin_final_revision_missing")
        return {"revisionCount": 0, "activeRevisionCount": 0}, set()
    if any(item.is_symlink() or not HASH.fullmatch(item.name) for item in directories):
        raise ValueError("private_preview_pinyin_revision_archive_invalid")

    original_plan_sha256 = digest(plan)
    records = {}
    for archive in directories:
        revision = archive.name
        required = ("source.json", "target-text.json", "target.json", "saved.json", "original-plan.json",
                    "original-receipts.json", "new-receipts.json", "receipts.json", "plan.json",
                    "intent.json", "amendment.json")
        if any((archive / name).is_symlink() or not (archive / name).is_file() for name in required):
            raise ValueError("private_preview_pinyin_revision_archive_invalid")
        source = _archive_json(archive / "source.json")
        target_text = _archive_json(archive / "target-text.json")
        target = _archive_json(archive / "target.json")
        saved = _archive_json(archive / "saved.json")
        archived_parent = _archive_json(archive / "original-plan.json")
        child = _archive_json(archive / "plan.json")
        original_receipts = _archive_json(archive / "original-receipts.json", list)
        new_receipts = _archive_json(archive / "new-receipts.json", list)
        combined_receipts = _archive_json(archive / "receipts.json", list)
        intent = _archive_json(archive / "intent.json")
        amendment = _archive_json(archive / "amendment.json")
        _receipt_ids(original_receipts)
        _receipt_ids(new_receipts)
        _receipt_ids(combined_receipts)

        files = intent.get("files")
        if (intent.get("revisionId") != revision or not isinstance(files, dict)
                or intent.get("sha256") != digest({k: v for k, v in intent.items() if k != "sha256"})
                or not {"source.json", "target-text.json", "original-plan.json", "original-receipts.json",
                        "plan.json"}.issubset(files)):
            raise ValueError("private_preview_pinyin_revision_archive_invalid")
        for name, sha256 in files.items():
            path = archive / name
            if (Path(name).name != name or not HASH.fullmatch(str(sha256)) or path.is_symlink() or not path.is_file()
                    or file_hash(path) != sha256):
                raise ValueError("private_preview_pinyin_revision_archive_invalid")
        if archived_parent != plan:
            raise ValueError("private_preview_pinyin_revision_parent_mismatch")
        try:
            validate_child_request_plan(plan, child)
        except (ApiError, ValueError, KeyError, TypeError):
            raise ValueError("private_preview_pinyin_revision_parent_mismatch")
        if (child.get("revisionId") != revision or child.get("parentPlanSha256") != original_plan_sha256
                or child.get("classroomSha256") != digest(target_text)
                or child.get("coreSha256") != digest(core_content(target_text))):
            raise ValueError("private_preview_pinyin_revision_target_mismatch")
        if (digest(teaching_core(target_text)) != digest(teaching_core(target))
                or digest(teaching_core(target)) != digest(teaching_core(saved))
                or persisted_content(target) != persisted_content(saved)):
            raise ValueError("private_preview_pinyin_revision_target_mismatch")
        source_sha256, saved_sha256 = digest(source), digest(saved)
        if (amendment.get("revisionId") != revision
                or amendment.get("intentSha256") != intent["sha256"]
                or amendment.get("sourceSha256") != source_sha256
                or amendment.get("targetSha256") != saved_sha256
                or amendment.get("audioPlanSha256") != digest(child)
                or amendment.get("sha256") != digest({k: v for k, v in amendment.items() if k != "sha256"})):
            raise ValueError("private_preview_pinyin_revision_hash_mismatch")
        if (len(combined_receipts) < len(original_receipts)
                or combined_receipts[:len(original_receipts)] != original_receipts
                or combined_receipts[len(original_receipts):] != new_receipts
                or not new_receipts
                or any(item.get("narrationRevisionId") != revision for item in new_receipts)):
            raise ValueError("private_preview_pinyin_revision_receipts_invalid")
        new_ids = amendment.get("newTtsRequestIds")
        if (not isinstance(new_ids, list) or not new_ids or len(set(new_ids)) != len(new_ids)
                or not set(new_ids).issubset(set(_receipt_ids(new_receipts)))):
            raise ValueError("private_preview_pinyin_revision_receipts_invalid")
        records[revision] = {"source": source, "sourceSha256": source_sha256,
            "saved": saved, "savedSha256": saved_sha256, "plan": child,
            "originalReceipts": original_receipts, "receipts": combined_receipts,
            "newTtsRequestIds": set(new_ids)}

    by_source = {record["sourceSha256"]: record for record in records.values()}
    if len(by_source) != len(records):
        raise ValueError("private_preview_pinyin_revision_chain_invalid")
    saved_hashes = [record["savedSha256"] for record in records.values()]
    if len(set(saved_hashes)) != len(saved_hashes):
        raise ValueError("private_preview_pinyin_revision_chain_invalid")
    roots = [record for record in records.values() if record["sourceSha256"] not in set(saved_hashes)]
    if len(roots) != 1 or digest(teaching_core(roots[0]["source"])) != plan.get("coreSha256"):
        raise ValueError("private_preview_pinyin_revision_chain_invalid")
    ordered, current, seen = [], roots[0], set()
    while current is not None:
        revision = current["plan"]["revisionId"]
        if revision in seen:
            raise ValueError("private_preview_pinyin_revision_chain_invalid")
        seen.add(revision)
        ordered.append(current)
        current = by_source.get(current["savedSha256"])
    if (len(ordered) != len(records) or ordered[-1]["saved"] != classroom
            or ordered[-1]["savedSha256"] != expected_source_sha256
            or digest(teaching_core(ordered[-1]["saved"])) != expected_core_sha256):
        raise ValueError("private_preview_pinyin_final_revision_missing")
    previous = ordered[0]["originalReceipts"]
    for record in ordered:
        if record["originalReceipts"] != previous:
            raise ValueError("private_preview_pinyin_revision_chain_invalid")
        previous = record["receipts"]
    if previous != receipts:
        raise ValueError("private_preview_pinyin_revision_chain_invalid")
    active_ids = {action.get("audioId") for scene in classroom.get("scenes", [])
                  for action in scene.get("actions", []) if action.get("type") == "speech"}
    active_revisions = {item.get("narrationRevisionId") for item in receipts
                        if item.get("requestId") in active_ids and item.get("narrationRevisionId") is not None}
    if (not active_revisions.issubset(records)
            or not (ordered[-1]["newTtsRequestIds"] & active_ids)):
        raise ValueError("private_preview_pinyin_final_revision_missing")
    return {"revisionCount": len(ordered), "activeRevisionCount": len(active_revisions)}, set(records)


def verify_pinyin_origin_complete(classroom, plan, receipts, audit, audio_directory, *,
                                  runtime_origin, expected_source_sha256,
                                  expected_core_sha256, expected_plan_sha256,
                                  expected_speech_count):
    """Rebuild every pinyin TTS/WAV/playback/origin-audit binding locally."""
    if (not all(HASH.fullmatch(str(item)) for item in
                (expected_source_sha256, expected_core_sha256, expected_plan_sha256))
            or type(expected_speech_count) is not int or not 1 <= expected_speech_count <= 240):
        raise ValueError("private_preview_pinyin_expected_identity_invalid")
    if digest(classroom) != expected_source_sha256:
        raise ValueError("private_preview_pinyin_source_sha256_mismatch")
    if digest(teaching_core(classroom)) != expected_core_sha256:
        raise ValueError("private_preview_pinyin_core_sha256_mismatch")
    if (not isinstance(plan, dict) or plan.get("schemaVersion") != PINYIN_PLAN_SCHEMA
            or digest(plan) != expected_plan_sha256):
        raise ValueError("private_preview_pinyin_plan_sha256_mismatch")
    policy_for_plan(plan)
    runtime_origin = local_origin(runtime_origin)
    audio_directory = Path(audio_directory).resolve()
    if audio_directory.name != classroom.get("id"):
        raise ValueError("private_preview_pinyin_audio_directory_invalid")
    folder = audio_directory / "textbook-preview-audio"
    audio_root = (audio_directory / "audio").resolve()
    if not folder.is_dir() or not audio_root.is_dir():
        raise ValueError("private_preview_pinyin_audio_directory_invalid")
    scenes = classroom.get("scenes")
    if not isinstance(scenes, list) or len({s.get("id") for s in scenes if isinstance(s, dict)}) != len(scenes):
        raise ValueError("private_preview_pinyin_scene_identity_invalid")
    speeches = [(scene, action) for scene in scenes for action in scene.get("actions", [])
                if isinstance(action, dict) and action.get("type") == "speech"]
    action_ids = [action.get("id") for _, action in speeches]
    if (len(speeches) != expected_speech_count or len(set(action_ids)) != len(action_ids)
            or any(not IDENTITY.fullmatch(str(item or "")) for item in action_ids)):
        raise ValueError("private_preview_pinyin_speech_count_or_identity_mismatch")
    receipt_ids = _receipt_ids(receipts)
    by_id = {item["requestId"]: item for item in receipts}
    audio_ids = [action.get("audioId") for _, action in speeches]
    if (len(set(audio_ids)) != len(audio_ids) or not set(audio_ids).issubset(by_id)):
        raise ValueError("private_preview_pinyin_receipt_coverage_mismatch")
    lineage, revision_ids = verify_pinyin_revision_lineage(classroom, plan, receipts, folder,
        expected_source_sha256=expected_source_sha256, expected_core_sha256=expected_core_sha256)
    if not revision_ids and set(receipt_ids) != set(audio_ids):
        raise ValueError("private_preview_pinyin_receipt_coverage_mismatch")
    successful_wavs = {}
    for receipt in receipts:
        path = audio_root / f"{receipt['requestId']}.wav"
        if receipt.get("status") == "succeeded" and receipt.get("completionUsable") is not False:
            if path.is_symlink() or not path.is_file() or audio_root not in path.resolve().parents:
                raise ValueError("private_preview_pinyin_wav_missing")
            audio = path.read_bytes()
            validate_receipt_wav(receipt, audio)
            successful_wavs[receipt["requestId"]] = (path.resolve(), audio)
        elif path.exists():
            raise ValueError("private_preview_pinyin_wav_coverage_mismatch")
    actual_wavs = {path.resolve() for path in audio_root.glob("*.wav") if path.is_file()}
    if actual_wavs != {item[0] for item in successful_wavs.values()}:
        raise ValueError("private_preview_pinyin_wav_coverage_mismatch")
    assets, wavs, children = [], {}, {}
    for scene, action in speeches:
        receipt = by_id[action["audioId"]]
        if receipt.get("status") != "succeeded" or receipt.get("completionUsable") is False:
            raise ValueError("private_preview_pinyin_receipt_not_succeeded")
        verify_segment_receipt(plan, receipt, scene, action, folder)
        request_plan = segment_request_plan(plan, receipt, folder, text=action["text"])
        children[(scene["id"], action["id"])] = (None if request_plan == plan else request_plan)
        expected_url = f"/api/classroom-media/{classroom['id']}/audio/{action['audioId']}.wav"
        _media_path(action.get("audioUrl"), runtime_origin, expected_url)
        path, audio = successful_wavs[action["audioId"]]
        wavs[(scene["id"], action["id"])] = audio
        assets.append({"sceneId": scene["id"], "actionId": action["id"],
            "textSha256": hashlib.sha256(action["text"].strip().encode()).hexdigest(),
            "ttsRequestId": action["audioId"], "ttsReceiptSha256": digest(receipt),
            "audioSha256": receipt["audioSha256"], "pcmSha256": receipt["pcmSha256"],
            "audioUrl": action["audioUrl"], "path": str(path), "byteLength": len(audio)})
    playback = verify_pinyin_playback_bindings(classroom, set(audio_ids), runtime_origin)
    checked = validate_origin_audit(audit, plan=plan, classroom=classroom,
        expected_source_sha256=expected_source_sha256)
    if set(checked) != set(wavs):
        raise ValueError("private_preview_pinyin_origin_audit_coverage_mismatch")
    for key, (entry, _origin) in checked.items():
        target = entry.get("target", {})
        if (target.get("ttsReceipt") != by_id[entry["ttsRequestId"]]
                or target.get("requestPlan") != children[key]
                or origin_bytes(target.get("audioBase64")) != wavs[key]):
            raise ValueError("private_preview_pinyin_origin_audit_source_mismatch")
    return assets, {"speechCount": len(speeches), "wavCount": len(wavs),
                    "receiptCount": len(audio_ids), "storedReceiptCount": len(receipts),
                    "storedWavCount": len(actual_wavs), "originAuditSegmentCount": len(checked),
                    **lineage, **playback}


def make_alias(narrated, alias_id, *, fixed_textbook=False, narration_preview=False):
    if (not IDENTITY.fullmatch(alias_id) or len(alias_id) > 104 or not alias_id.startswith("tbprivate_")
            or alias_id == narrated.get("id") or narrated.get("stage", {}).get("id") != narrated.get("id")
            or set(narrated) - {"id", "createdAt", "stage", "scenes"}):
        raise ValueError("private_preview_alias_identity_invalid")
    if narration_preview and (fixed_textbook or narrated["stage"].get("fixedTextbook") is True):
        raise ValueError("private_preview_playback_contract_invalid")
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
    if fixed_textbook:
        # Retain the exact behavior of earlier, explicitly recorded snapshots.
        alias["stage"]["fixedTextbook"] = True
    if narration_preview:
        # Cue ownership is shared with delivery, but private quizzes retain
        # their existing operator route rather than the student grading API.
        alias["stage"]["miraTextbookPreviewNarration"] = True
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
    alias, mapping = make_alias(narrated, alias_id or "tbprivate_" + uuid4().hex[:24], narration_preview=True)
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
        "playbackContract": deepcopy(PLAYBACK_CONTRACT),
        "htmlRewritten": False, "sourceCandidateModified": False, "providerCalls": 0,
        "semanticPronunciationReview": audit.get("semanticPronunciationReview", "pending"),
        "interactiveStateNarrationReview": audit.get("interactiveStateNarrationReview", "pending"),
        "saveContract": _save_contract()}
    verify_sources(manifest)
    manifest["snapshotSha256"] = digest(manifest)
    output.mkdir(parents=True)
    save_json(output / "source-narrated-classroom.json", narrated)
    save_json(output / "classroom.json", alias)
    save_json(output / "snapshot.json", manifest)
    return manifest


def prepare_pinyin_snapshot(classroom_path, audio_directory, audio_audit_path, output, *,
                            expected_source_sha256, expected_core_sha256,
                            expected_plan_sha256, expected_speech_count,
                            runtime_origin="http://127.0.0.1:3100", alias_id=None):
    """Prepare a v3-pinyin/origin-audit alias without network or runtime writes."""
    classroom_path, audio_directory = Path(classroom_path).resolve(), Path(audio_directory).resolve()
    audio_audit_path, output = Path(audio_audit_path).resolve(), Path(output).resolve()
    if (output.exists() or output == audio_directory or audio_directory in output.parents
            or output == classroom_path.parent or output == audio_audit_path.parent):
        raise ValueError("private_preview_requires_new_separate_output_directory")
    origin = local_origin(runtime_origin)
    roles = [("classroom", classroom_path, dict),
        ("audioPlan", audio_directory / "textbook-preview-audio" / "plan.json", dict),
        ("audioReceipts", audio_directory / "textbook-preview-audio" / "receipts.json", list),
        ("audioAudit", audio_audit_path, dict)]
    loaded, evidence = {}, []
    for role, path, container in roles:
        loaded[role], source = document(path, role, container=container)
        evidence.append(source)
    classroom, plan = loaded["classroom"], loaded["audioPlan"]
    receipts, audit = loaded["audioReceipts"], loaded["audioAudit"]
    assets, verification = verify_pinyin_origin_complete(classroom, plan, receipts, audit, audio_directory,
        runtime_origin=origin, expected_source_sha256=expected_source_sha256,
        expected_core_sha256=expected_core_sha256, expected_plan_sha256=expected_plan_sha256,
        expected_speech_count=expected_speech_count)
    alias, mapping = make_alias(classroom, alias_id or "tbprivate_" + uuid4().hex[:24], narration_preview=True)
    source_contract = {**deepcopy(PINYIN_ORIGIN_SOURCE_CONTRACT),
        "expectedSpeechCount": expected_speech_count, "sourceAudioDirectory": str(audio_directory),
        "sourceSha256": expected_source_sha256, "coreSha256": expected_core_sha256,
        "planSha256": expected_plan_sha256, "receiptsSha256": digest(receipts),
        "audioAuditSha256": digest(audit)}
    manifest = {"schemaVersion": PINYIN_ORIGIN_SCHEMA,
        "purpose": "private_operator_acceptance_preview_alias", "createdAt": datetime.now(timezone.utc).isoformat(),
        "publicationAllowed": False, "studentDeliveryAllowed": False, "runtimeOrigin": origin,
        "sourceClassroomId": classroom["id"], "aliasClassroomId": alias["id"],
        "taskId": plan["previewKey"], "binding": plan["binding"], "teacher": plan["teacher"],
        "sourceDocuments": evidence, "audioAssets": assets, "sourceSha256": expected_source_sha256,
        "audioPlanSha256": expected_plan_sha256, "audioReceiptsSha256": digest(receipts),
        "audioAuditSha256": digest(audit), "narratedClassroomSha256": digest(classroom),
        "expectedRuntimeCoreSha256": expected_core_sha256,
        "expectedRuntimeNarratedSha256": digest(persisted_content(classroom)),
        "aliasClassroomSha256": digest(alias), "aliasPersistedSha256": digest(persisted_content(alias)),
        "sceneIdMapping": mapping, "audioUrlsRewritten": False, "mediaUrlsRewritten": False,
        "playbackContract": deepcopy(PLAYBACK_CONTRACT), "pinyinOriginSourceContract": source_contract,
        "verification": verification, "htmlRewritten": False, "sourceCandidateModified": False,
        "providerCalls": 0, "saveContract": _save_contract()}
    verify_sources(manifest)
    manifest["snapshotSha256"] = digest(manifest)
    output.mkdir(parents=True)
    save_json(output / "source-narrated-classroom.json", classroom)
    save_json(output / "classroom.json", alias)
    save_json(output / "snapshot.json", manifest)
    return manifest


def _verify_pinyin_snapshot_sources(manifest, narrated):
    contract = manifest.get("pinyinOriginSourceContract")
    if (not isinstance(contract, dict)
            or {k: contract.get(k) for k in PINYIN_ORIGIN_SOURCE_CONTRACT} != PINYIN_ORIGIN_SOURCE_CONTRACT
            or set(contract) != set(PINYIN_ORIGIN_SOURCE_CONTRACT) | {"expectedSpeechCount", "sourceAudioDirectory",
                "sourceSha256", "coreSha256", "planSha256", "receiptsSha256", "audioAuditSha256"}):
        raise ValueError("private_preview_pinyin_source_contract_invalid")
    sources = manifest.get("sourceDocuments")
    if not isinstance(sources, list) or {item.get("role") for item in sources if isinstance(item, dict)} != {
            "classroom", "audioPlan", "audioReceipts", "audioAudit"} or len(sources) != 4:
        raise ValueError("private_preview_pinyin_source_contract_invalid")
    loaded = {}
    for source in sources:
        container = list if source["role"] == "audioReceipts" else dict
        value, actual = document(source["path"], source["role"], container=container)
        if actual != source:
            raise ValueError("private_preview_source_document_changed")
        loaded[source["role"]] = value
    if (loaded["classroom"] != narrated or manifest.get("sourceSha256") != contract["sourceSha256"]
            or manifest.get("audioPlanSha256") != contract["planSha256"]
            or manifest.get("audioReceiptsSha256") != contract["receiptsSha256"]
            or manifest.get("audioAuditSha256") != contract["audioAuditSha256"]
            or manifest.get("expectedRuntimeCoreSha256") != contract["coreSha256"]):
        raise ValueError("private_preview_pinyin_source_contract_invalid")
    assets, verification = verify_pinyin_origin_complete(loaded["classroom"], loaded["audioPlan"],
        loaded["audioReceipts"], loaded["audioAudit"], contract["sourceAudioDirectory"],
        runtime_origin=manifest["runtimeOrigin"], expected_source_sha256=contract["sourceSha256"],
        expected_core_sha256=contract["coreSha256"], expected_plan_sha256=contract["planSha256"],
        expected_speech_count=contract["expectedSpeechCount"])
    if assets != manifest.get("audioAssets") or verification != manifest.get("verification"):
        raise ValueError("private_preview_pinyin_source_contract_invalid")


def load_snapshot(directory):
    directory = Path(directory).resolve()
    manifest = json.loads((directory / "snapshot.json").read_text())
    alias = json.loads((directory / "classroom.json").read_text())
    narrated = json.loads((directory / "source-narrated-classroom.json").read_text())
    if (manifest.get("schemaVersion") not in {SCHEMA, PINYIN_ORIGIN_SCHEMA}
            or manifest.get("publicationAllowed") is not False
            or manifest.get("studentDeliveryAllowed") is not False
            or manifest.get("snapshotSha256") != digest({k: v for k, v in manifest.items() if k != "snapshotSha256"})
            or manifest.get("aliasClassroomSha256") != digest(alias)
            or manifest.get("narratedClassroomSha256") != digest(narrated)
            or manifest.get("aliasPersistedSha256") != digest(persisted_content(alias))
            or manifest.get("expectedRuntimeNarratedSha256") != digest(persisted_content(narrated))
            or manifest.get("expectedRuntimeCoreSha256") != digest(teaching_core(narrated))):
        raise ValueError("private_preview_snapshot_integrity_failed")
    # Old saved previews retain their exact identity and original behavior.
    # New previews explicitly record the metadata change in their hashed receipt.
    playback = manifest.get("playbackContract")
    if "playbackContract" in manifest and playback not in (PLAYBACK_CONTRACT, LEGACY_FIXED_PLAYBACK_CONTRACT):
        raise ValueError("private_preview_playback_contract_invalid")
    expected, mapping = make_alias(narrated, manifest["aliasClassroomId"],
        fixed_textbook=playback == LEGACY_FIXED_PLAYBACK_CONTRACT, narration_preview=playback == PLAYBACK_CONTRACT)
    if expected != alias or mapping != manifest.get("sceneIdMapping"):
        raise ValueError("private_preview_alias_content_changed")
    local_origin(manifest["runtimeOrigin"])
    verify_sources(manifest)
    if manifest["schemaVersion"] == PINYIN_ORIGIN_SCHEMA:
        if (playback != PLAYBACK_CONTRACT or alias.get("stage", {}).get("miraTextbookPreviewNarration") is not True
                or "fixedTextbook" in alias.get("stage", {})):
            raise ValueError("private_preview_playback_contract_invalid")
        _verify_pinyin_snapshot_sources(manifest, narrated)
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
    pinyin = commands.add_parser("prepare-pinyin-origin",
        help="Pure local v3-pinyin/origin-audit preparation; no API or provider calls")
    pinyin.add_argument("--classroom", type=Path, required=True)
    pinyin.add_argument("--audio-directory", type=Path, required=True)
    pinyin.add_argument("--audio-audit", type=Path, required=True)
    pinyin.add_argument("--source-sha256", required=True)
    pinyin.add_argument("--core-sha256", required=True)
    pinyin.add_argument("--plan-sha256", required=True)
    pinyin.add_argument("--expected-speech-count", type=int, required=True)
    pinyin.add_argument("--runtime-origin", default="http://127.0.0.1:3100")
    pinyin.add_argument("--output", type=Path, required=True)
    pinyin.add_argument("--alias-id")
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
        elif args.command == "prepare-pinyin-origin":
            result = prepare_pinyin_snapshot(args.classroom, args.audio_directory, args.audio_audit, args.output,
                expected_source_sha256=args.source_sha256, expected_core_sha256=args.core_sha256,
                expected_plan_sha256=args.plan_sha256, expected_speech_count=args.expected_speech_count,
                runtime_origin=args.runtime_origin, alias_id=args.alias_id)
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
