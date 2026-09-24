"""Local operator adapter: saved content first, durable server TTS per segment.

Reuses the private, idempotent audio transport. Its receipt is not a formal
course release or ASR approval. A failed/ambiguous segment is never re-created.
"""
from copy import deepcopy
import fcntl
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urlparse
import wave

from content.teacher_profiles import get_formal_subject_qwen_voice_identity
from content.textbook_catalog import canonical, digest
from content.textbook_preview import preview_checks
from core.errors import ApiError
from core.security import now_ms
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeError


def core_content(classroom):
    result = deepcopy(classroom)
    result.pop("createdAt", None)
    for scene in result["scenes"]:
        for action in scene.get("actions", []):
            if action.get("type") == "speech":
                for field in ("audioId", "audioUrl", "audioMetadata"):
                    action.pop(field, None)
    return result


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(canonical(value), encoding="utf-8")
    temporary.replace(path)


def narrate_preview(service, key, classroom_directory, *, progress=lambda value: None):
    row = service.get(key)
    runtime = service.runtime
    classroom_id = row["classroom_id"]
    if row["status"] not in {"preview_ready", "review_required"} or not classroom_id:
        raise ApiError("textbook_preview_content_required", "请先完成并保存课件，再生成配音", 409)
    if urlparse(runtime.base_url).hostname not in {"127.0.0.1", "localhost", "::1"} or not re.fullmatch(r"[A-Za-z0-9_-]+", classroom_id):
        raise ApiError("textbook_preview_audio_local_only", "此媒体保存工具仅支持本机 OpenMAIC", 409)
    root = Path(classroom_directory).resolve()
    # The operator must point at the actual classroom store, not an arbitrary
    # destination. Confirm content identity before creating any files or calls.
    source_file = root / f"{classroom_id}.json"
    if not source_file.is_file():
        raise ApiError("textbook_preview_storage_mismatch", "没有找到对应的本机课件文件", 409)
    original = service.repository.parse(row["classroom_json"])
    if core_content(json.loads(source_file.read_text())) != core_content(original):
        raise ApiError("textbook_preview_storage_mismatch", "本机课件内容与数据库快照不一致", 409)
    saved_result = service.repository.parse(row["result_json"]) or {}
    receipts = saved_result.get("audioReceipts", [])
    speeches = [a for s in original["scenes"] for a in s.get("actions", []) if a.get("type") == "speech"]
    if row["status"] == "preview_ready" and len(receipts) == len(speeches) and receipts:
        by_id = {r["requestId"]: r for r in receipts}
        if all(a.get("audioId") in by_id for a in speeches):
            for request_id, receipt in by_id.items():
                if not re.fullmatch(r"tbprev_[a-f0-9]{64}", request_id):
                    raise ApiError("textbook_preview_audio_invalid", "音频记录编号无效", 409)
                asset = root / classroom_id / "audio" / (request_id + ".wav")
                if not asset.is_file() or hashlib.sha256(asset.read_bytes()).hexdigest() != receipt["audioSha256"]:
                    raise ApiError("textbook_preview_audio_asset_missing", "已完成的配音文件缺失或变化，请从原音频记录恢复", 409)
            return service.summary(row)
    folder = root / classroom_id / "textbook-preview-audio"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "operator.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ApiError("textbook_preview_audio_running", "这节课正在配音，请读取已有任务", 409)
        classroom = runtime.get_classroom(classroom_id)
        if core_content(classroom) != core_content(original):
            raise ApiError("textbook_preview_changed", "课件已被编辑，请先核对音频任务", 409)
        teacher = get_formal_subject_qwen_voice_identity("chinese")
        plan_path = folder / "plan.json"
        if plan_path.exists():
            plan = json.loads(plan_path.read_text())
            if plan["previewKey"] != key or plan["coreSha256"] != digest(core_content(classroom)) or plan["teacher"] != teacher.to_target_payload():
                raise ApiError("textbook_preview_audio_conflict", "已冻结的配音内容或声音身份不一致", 409)
        else:
            plan = {"previewKey": key, "classroomSha256": row["classroom_sha256"],
                    "coreSha256": digest(core_content(classroom)), "teacher": teacher.to_target_payload()}
            atomic_json(plan_path, plan)
        workload = [(scene, action) for scene in classroom["scenes"] for action in scene.get("actions", []) if action.get("type") == "speech"]
        if not 1 <= len(workload) <= 80 or any(not a.get("text", "").strip() or len(a["text"]) > 4000 for _, a in workload):
            raise ApiError("textbook_preview_audio_workload", "配音数量或文本范围无效", 409)
        receipts, stopped = [], None
        audio_dir = root / classroom_id / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        for index, (scene, action) in enumerate(workload, 1):
            text = action["text"].strip()
            request_id = "tbprev_" + digest({"plan": plan, "sceneId": scene["id"], "actionId": action["id"], "text": text})
            try:
                try:
                    receipt = runtime.get_formal_audio_tts(request_id)
                except OpenMaicFullRuntimeError as exc:
                    if exc.status_code != 404:
                        raise
                    receipt = runtime.start_formal_audio_tts(
                        request_id=request_id, classroom_id=classroom_id,
                        classroom_content_sha256=plan["classroomSha256"], subject="chinese",
                        teacher_profile_id=teacher.teacher_profile_id, teacher_profile_version=teacher.teacher_profile_version,
                        teacher_profile_sha256=teacher.teacher_profile_hash, teacher_gender=teacher.teacher_gender,
                        scene_id=scene["id"], scene_order=scene["order"], action_id=action["id"],
                        narration_segment_id=action["id"], text=text, text_sha256=hashlib.sha256(text.encode()).hexdigest())
                if receipt["status"] != "succeeded":
                    receipts.append(receipt)
                    stopped = "textbook_preview_audio_" + receipt["status"]
                    break
                filename = request_id + ".wav"
                target = audio_dir / filename
                if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == receipt["audioSha256"]:
                    audio = target.read_bytes()
                else:
                    audio = runtime.download_formal_audio_tts(request_id, expected_sha256=receipt["audioSha256"])
                with wave.open(io.BytesIO(audio), "rb") as wav:
                    duration = wav.getnframes() / wav.getframerate()
                    if duration <= 0:
                        raise ValueError("Empty audio")
                temporary = target.with_suffix(".tmp")
                temporary.write_bytes(audio)
                temporary.replace(target)
                action.update(audioId=request_id, audioUrl=f"{runtime.base_url}/api/classroom-media/{classroom_id}/audio/{filename}",
                              audioMetadata={"schemaVersion": "mira.openmaic.speech-audio.v1", "providerId": teacher.tts_provider_id,
                                             "modelId": teacher.tts_model_id, "voiceId": teacher.voice_id, "fallbackUsed": False})
                receipts.append({**receipt, "durationSeconds": round(duration, 3)})
                atomic_json(folder / "checkpoint.json", classroom)
                atomic_json(folder / "receipts.json", receipts)
                progress({"completedAudio": index, "totalAudio": len(workload)})
            except (OpenMaicFullRuntimeError, OSError, ValueError) as exc:
                stopped = getattr(exc, "code", "textbook_preview_audio_invalid")
                break
        # Do not overwrite an independently edited classroom. A lost publish
        # response is reconciled against content on the next operator run.
        current = runtime.get_classroom(classroom_id)
        if core_content(current) != core_content(classroom):
            raise ApiError("textbook_preview_changed", "配音过程中课件被编辑，已保留音频且停止覆盖", 409)
        runtime.save_preview_classroom(classroom)
        saved = runtime.get_classroom(classroom_id)
        if core_content(saved) != core_content(classroom):
            raise ApiError("textbook_preview_changed", "保存后的课件内容不一致", 409)
        checks = {**(service.repository.parse(row["result_json"]) or {}), **preview_checks(saved)}
        checks.pop("frozenPreview", None)
        checks.update(audioSeconds=round(sum(r.get("durationSeconds", 0) for r in receipts), 3),
                      audioReceipts=receipts, audioStopCode=stopped)
        with service.repository.transaction() as conn:
            conn.execute("UPDATE learning_textbook_course_previews SET status=?,classroom_json=?,classroom_sha256=?,result_json=?,updated_at=? WHERE preview_key=?",
                         ("review_required" if checks["issues"] or stopped else "preview_ready", canonical(saved), digest(saved), canonical(checks), now_ms(), key))
        return service.summary(service.get(key))
