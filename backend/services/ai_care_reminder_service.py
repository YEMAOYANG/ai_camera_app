from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Mapping

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from models.care import (
    CARE_SCENARIOS,
    DEFAULT_FALLBACK_TEMPLATES,
    REMINDER_DECISION_ALLOWED,
    REMINDER_EVENT_SOURCE_CARE_POLICY,
    REMINDER_EVENT_SOURCE_DRY_RUN,
    REMINDER_EVENT_SOURCE_INTERNAL,
    REMINDER_EVENT_SOURCE_TEST,
    REMINDER_STATUS_COMMAND_SENT,
    REMINDER_STATUS_FALLBACK_USED,
    REMINDER_STATUS_FAILED,
    REMINDER_STATUS_GENERATED,
    REMINDER_STATUS_TEST_GENERATED,
)
from repositories.care_repository import CareRepository
from schemas.care import reminder_event_payload
from services.ai_text_provider import AiTextProvider
from services.auth_service import AuthService
from services.camera_bridge_service import CameraBridgeError
from services.camera_command_service import CameraCommandService
from services.prompt_registry import PromptRegistry
from services.reminder_text_validator import ReminderTextValidator
from services.task_event_stream import (
    CAMERA_COMMAND_CREATED,
    REMINDER_EVENT_CREATED,
    publish_family_event,
)


REMINDER_DECISION_TRIGGER_TTL_MS = 2 * 60 * 1000


class AiCareReminderService:
    def __init__(
        self,
        database_url: str | Path,
        *,
        auth_service: AuthService,
        ai_text_provider: AiTextProvider,
        prompt_registry: PromptRegistry,
        validator: ReminderTextValidator | None = None,
        camera_command_service: CameraCommandService | None = None,
    ):
        self.repository = CareRepository(Database(database_url))
        self.auth_service = auth_service
        self.ai_text_provider = ai_text_provider
        self.prompt_registry = prompt_registry
        self.validator = validator or ReminderTextValidator()
        self.camera_command_service = camera_command_service
        self._speaker_locks: dict[str, threading.Lock] = {}
        self._speaker_locks_guard = threading.Lock()

    def next_reminder(self, access_token: str, args) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        child_id = _optional_text(args.get("childId") if args else None)
        with self.repository.transaction() as conn:
            resolved_child_id = self._resolve_child_id(conn, family_id, child_id)
            if not resolved_child_id:
                return {"ok": True, "nextReminder": None}
            recent = self.repository.list_reminder_events(
                conn,
                family_id=family_id,
                child_id=resolved_child_id,
                limit=1,
            )
        return {
            "ok": True,
            "childId": resolved_child_id,
            "nextReminder": None,
            "lastReminder": reminder_event_payload(recent[0]) if recent else None,
        }

    def list_events(self, access_token: str, args) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        child_id = _optional_text(args.get("childId") if args else None)
        scenario = _optional_text(args.get("scenario") if args else None)
        limit = _limit(args.get("limit") if args else None)
        include_test = _bool_flag(args.get("includeTest") if args else None)
        with self.repository.transaction() as conn:
            events = self.repository.list_reminder_events(
                conn,
                family_id=family_id,
                child_id=child_id,
                scenario=scenario,
                limit=limit,
                include_test=include_test,
            )
        return {"ok": True, "events": [reminder_event_payload(row) for row in events]}

    def test_reminder(self, access_token: str, data: dict) -> dict:
        context = self.auth_service.authenticate(access_token)
        family_id = context["family"]["id"]
        with self.repository.transaction() as conn:
            child_id = self._resolve_child_id(conn, family_id, _optional_text(data.get("childId")))
            if not child_id:
                raise ApiError("child_required", "请先完善孩子资料。")
        scenario = _scenario(data.get("scenario"))
        result = self.generate_and_record(
            family_id=family_id,
            child_id=child_id,
            device_id=_optional_text(data.get("deviceId")),
            scenario=scenario,
            event_source=REMINDER_EVENT_SOURCE_TEST,
            is_test=True,
            context={
                "dayType": data.get("dayType") or "school_day",
                "currentRoutineStage": data.get("currentRoutineStage") or "",
                "targetBehavior": data.get("targetBehavior") or "",
                "reminderLevel": data.get("reminderLevel") or "gentle",
                "tonePreference": data.get("tonePreference") or "温柔",
                "locale": "zh-CN",
                "maxLength": 40,
            },
        )
        return {"ok": True, "reminder": result["event"], "validation": result["validation"]}

    def trigger_internal(self, data: dict) -> dict:
        family_id = _required_text(data, "familyId", "familyId is required")
        child_id = _required_text(data, "childId", "childId is required")
        scenario = _scenario(data.get("scenario"))
        dry_run = _bool_flag(data.get("dryRun"))
        reminder_decision_id = _optional_text(data.get("reminderDecisionId"))
        existing_event = None
        with self.repository.transaction() as conn:
            if not self.repository.child_exists(conn, family_id=family_id, child_id=child_id):
                raise ApiError("child_not_found", "孩子资料不存在。", 404)
            decision = None
            if reminder_decision_id:
                decision = self.repository.get_reminder_decision(conn, decision_id=reminder_decision_id)
                if (
                    decision is None
                    or decision["family_id"] != family_id
                    or decision["child_id"] != child_id
                    or decision["scenario"] != scenario
                ):
                    raise ApiError("reminder_decision_not_found", "提醒决策不存在。", 404)
            elif not dry_run:
                raise ApiError("reminder_decision_required", "正式提醒需要先生成提醒决策。")
            if not dry_run and (
                decision["decision"] != REMINDER_DECISION_ALLOWED or not bool(decision.get("should_speak"))
            ):
                raise ApiError("reminder_decision_not_allowed", "当前提醒决策不允许播报。", 409)
            trigger_device_id = _device_id_for_trigger(decision, data) if not dry_run else _optional_text(data.get("deviceId"))
            if not dry_run and reminder_decision_id:
                existing_event = self.repository.get_internal_reminder_event_for_decision(
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                    scenario=scenario,
                    decision_id=reminder_decision_id,
                )
                if existing_event is None:
                    created_at = int(decision.get("created_at") or 0)
                    if created_at <= 0 or now_ms() - created_at > REMINDER_DECISION_TRIGGER_TTL_MS:
                        raise ApiError("reminder_decision_expired", "提醒决策已过期。", 409)
        if dry_run:
            result = self.generate_preview(
                family_id=family_id,
                child_id=child_id,
                device_id=_optional_text(data.get("deviceId")),
                scenario=scenario,
                reminder_decision_id=reminder_decision_id,
                context=data.get("context") if isinstance(data.get("context"), dict) else {},
            )
            return {"ok": True, "dryRun": True, "reminder": result["event"], "validation": result["validation"]}
        if existing_event is not None:
            command_result = self._ensure_speaker_command_for_event(
                family_id=family_id,
                event_id=str(existing_event["id"]),
            )
            self._publish_internal_trigger_events(
                family_id=family_id,
                event=command_result["event"],
                command=command_result["command"],
            )
            return {
                "ok": True,
                "idempotent": True,
                "reminder": command_result["event"],
                "validation": {"ok": True, "reusedExistingEvent": True},
                "command": command_result["command"],
            }
        result = self.generate_and_record(
            family_id=family_id,
            child_id=child_id,
            device_id=trigger_device_id,
            scenario=scenario,
            reminder_decision_id=reminder_decision_id,
            event_source=REMINDER_EVENT_SOURCE_INTERNAL,
            is_test=False,
            source_type="reminder_decision",
            source_id=reminder_decision_id,
            task_id=decision.get("task_id"),
            context=data.get("context") if isinstance(data.get("context"), dict) else {},
        )
        command_result = self._ensure_speaker_command_for_event(
            family_id=family_id,
            event_id=result["event"]["id"],
        )
        self._publish_internal_trigger_events(
            family_id=family_id,
            event=command_result["event"],
            command=command_result["command"],
        )
        return {
            "ok": True,
            "reminder": command_result["event"],
            "validation": result["validation"],
            "command": command_result["command"],
        }

    def generate_and_record(
        self,
        *,
        family_id: str,
        child_id: str,
        device_id: str | None,
        scenario: str,
        context: Mapping,
        reminder_decision_id: str | None = None,
        event_source: str = REMINDER_EVENT_SOURCE_CARE_POLICY,
        is_test: bool = False,
        source_type: str | None = None,
        source_id: str | None = None,
        task_id: str | None = None,
    ) -> dict:
        now = now_ms()
        generated = self._generate_text_payload(
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            scenario=scenario,
            context=context,
        )
        status = REMINDER_STATUS_TEST_GENERATED if is_test else generated["delivery_status"]
        with self.repository.transaction() as conn:
            event = self.repository.create_reminder_event(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                scenario=scenario,
                reminder_decision_id=reminder_decision_id,
                event_source=event_source,
                is_test=is_test,
                source_type=source_type,
                source_id=source_id,
                task_id=task_id,
                prompt_id=generated["prompt_id"],
                prompt_version=generated["prompt_version"],
                text=generated["text"],
                tone=generated["tone"],
                text_source=generated["text_source"],
                delivery_status=status,
                command_id=None,
                fallback_used=generated["fallback_used"],
                generated_at=now,
                delivered_at=None,
                failure_reason=generated["failure_reason"],
                now=now,
            )
        return {
            "event": reminder_event_payload(event),
            "validation": generated["validation"],
        }

    def _ensure_speaker_command_for_event(self, *, family_id: str, event_id: str) -> dict:
        with self.repository.transaction() as conn:
            event = self.repository.get_reminder_event(conn, family_id=family_id, event_id=event_id)
        if event is None:
            raise ApiError("reminder_event_not_found", "提醒事件不存在。", 404)

        existing_command_id = _optional_text(event.get("command_id"))
        if existing_command_id:
            delivery_status = str(event.get("delivery_status") or REMINDER_STATUS_COMMAND_SENT)
            camera_command_status = str(event.get("command_status") or "")
            failed = delivery_status == REMINDER_STATUS_FAILED or camera_command_status == "failed"
            return {
                "event": reminder_event_payload(event),
                "command": {
                    "ok": not failed,
                    "commandId": existing_command_id,
                    "status": REMINDER_STATUS_FAILED if failed else delivery_status,
                    "cameraCommandStatus": camera_command_status,
                    "message": str(event.get("failure_reason") or event.get("command_message") or ""),
                    "reusedExistingCommand": True,
                },
            }

        if self.camera_command_service is None:
            return self._mark_command_failed(
                family_id=family_id,
                event_id=event_id,
                command_id=None,
                failure_reason="摄像头暂时离线，提醒没有播出。",
            )

        command_id = None
        device_id = _optional_text(event.get("device_id")) or ""
        try:
            with self._speaker_lock(device_id):
                command = self.camera_command_service.internal_speak(
                    family_id=family_id,
                    text=str(event.get("text") or ""),
                    task_id=_optional_text(event.get("task_id")),
                    device_id=device_id or None,
                    source="care_reminder",
                    scenario=str(event.get("scenario") or ""),
                    prompt_id=str(event.get("prompt_id") or ""),
                )
            command_id = _optional_text(command.get("commandId"))
            if str(command.get("status") or "") == "failed":
                return self._mark_command_failed(
                    family_id=family_id,
                    event_id=event_id,
                    command_id=command_id,
                    failure_reason=str(command.get("message") or "摄像头暂时离线，提醒没有播出。"),
                )
            return self._mark_command_sent(
                family_id=family_id,
                event_id=event_id,
                command_id=command_id,
                command=command,
            )
        except ApiError as exc:
            return self._mark_command_failed(
                family_id=family_id,
                event_id=event_id,
                command_id=command_id,
                failure_reason=str(exc.message or "摄像头暂时离线，提醒没有播出。"),
            )
        except CameraBridgeError as exc:
            return self._mark_command_failed(
                family_id=family_id,
                event_id=event_id,
                command_id=command_id,
                failure_reason=str(exc.message or "摄像头暂时离线，提醒没有播出。"),
            )

    def _mark_command_sent(self, *, family_id: str, event_id: str, command_id: str | None, command: dict) -> dict:
        with self.repository.transaction() as conn:
            event = self.repository.update_reminder_event_delivery(
                conn,
                family_id=family_id,
                event_id=event_id,
                delivery_status=REMINDER_STATUS_COMMAND_SENT,
                command_id=command_id,
                delivered_at=None,
                failure_reason=None,
            )
        return {
            "event": reminder_event_payload(event),
            "command": {
                "ok": True,
                "commandId": command_id or "",
                "status": REMINDER_STATUS_COMMAND_SENT,
                "cameraCommandStatus": command.get("status") or "",
                "reusedExistingCommand": False,
            },
        }

    def _mark_command_failed(
        self,
        *,
        family_id: str,
        event_id: str,
        command_id: str | None,
        failure_reason: str,
    ) -> dict:
        with self.repository.transaction() as conn:
            event = self.repository.update_reminder_event_delivery(
                conn,
                family_id=family_id,
                event_id=event_id,
                delivery_status=REMINDER_STATUS_FAILED,
                command_id=command_id,
                delivered_at=None,
                failure_reason=failure_reason,
            )
        return {
            "event": reminder_event_payload(event),
            "command": {
                "ok": False,
                "commandId": command_id or "",
                "status": REMINDER_STATUS_FAILED,
                "message": failure_reason,
                "reusedExistingCommand": False,
            },
        }

    def _speaker_lock(self, device_id: str) -> threading.Lock:
        key = device_id or "__default__"
        with self._speaker_locks_guard:
            lock = self._speaker_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._speaker_locks[key] = lock
            return lock

    def generate_preview(
        self,
        *,
        family_id: str,
        child_id: str,
        device_id: str | None,
        scenario: str,
        context: Mapping,
        reminder_decision_id: str | None = None,
    ) -> dict:
        now = now_ms()
        generated = self._generate_text_payload(
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            scenario=scenario,
            context=context,
        )
        event = {
            "id": "",
            "family_id": family_id,
            "child_id": child_id,
            "device_id": device_id or "",
            "scenario": scenario,
            "reminder_decision_id": reminder_decision_id or "",
            "event_source": REMINDER_EVENT_SOURCE_DRY_RUN,
            "is_test": 1,
            "source_type": "reminder_decision" if reminder_decision_id else "",
            "source_id": reminder_decision_id or "",
            "task_id": "",
            "text": generated["text"],
            "tone": generated["tone"],
            "text_source": generated["text_source"],
            "delivery_status": REMINDER_STATUS_TEST_GENERATED,
            "fallback_used": int(generated["fallback_used"]),
            "generated_at": now,
            "delivered_at": None,
            "created_at": now,
        }
        return {"event": reminder_event_payload(event), "validation": generated["validation"]}

    def _publish_internal_trigger_events(
        self,
        *,
        family_id: str,
        event: dict,
        command: dict,
    ) -> None:
        event_id = str(event.get("id") or "").strip()
        command_id = str(command.get("commandId") or "").strip()
        device_id = _optional_text(event.get("deviceId"))
        task_id = _optional_text(event.get("taskId"))
        publish_family_event(
            family_id=family_id,
            event_type=REMINDER_EVENT_CREATED,
            device_id=device_id,
            task_ids=[task_id] if task_id else [],
            event_ids=[event_id] if event_id else [],
            source="care_reminder",
        )
        if command_id:
            publish_family_event(
                family_id=family_id,
                event_type=CAMERA_COMMAND_CREATED,
                device_id=device_id,
                task_ids=[task_id] if task_id else [],
                event_ids=[command_id],
                is_reliable=command.get("ok") is not False,
                source="care_reminder",
            )

    def _generate_text_payload(
        self,
        *,
        family_id: str,
        child_id: str,
        device_id: str | None,
        scenario: str,
        context: Mapping,
    ) -> dict:
        with self.repository.transaction() as conn:
            last = self.repository.latest_reminder_event(
                conn,
                family_id=family_id,
                child_id=child_id,
                scenario=scenario,
            )
            config = self.repository.get_capability_config_with_fallback(
                conn,
                family_id=family_id,
                child_id=child_id,
                scenario=scenario,
                device_id=device_id,
            )
        prompt_id = str(context.get("promptId") or (config or {}).get("prompt_id") or f"reminder.{scenario}")
        prompt_version = str((config or {}).get("prompt_version") or "v1")
        fallback_templates = _json_list(config.get("fallback_templates") if config else None)
        if not fallback_templates:
            fallback_templates = DEFAULT_FALLBACK_TEMPLATES.get(scenario, DEFAULT_FALLBACK_TEMPLATES["transition"])
        last_text = str(last.get("text") or "") if last else ""
        ai_text = self._ai_text(prompt_id, prompt_version, scenario, context, last_text)
        validation = self.validator.validate_json_text(
            ai_text,
            scenario=scenario,
            last_text=last_text,
        )
        fallback_used = not validation.ok
        text_source = "ai"
        if fallback_used:
            fallback_text = self._fallback_text(fallback_templates, last_text=last_text)
            fallback_validation = self.validator.validate_plain_text(
                fallback_text,
                last_text=last_text,
            )
            text = fallback_validation.text or fallback_templates[0]
            tone = "warm"
            text_source = "fallback"
            status = REMINDER_STATUS_FALLBACK_USED
            validation_payload = {
                "ok": False,
                "reason": validation.reason,
                "fallbackUsed": True,
            }
        else:
            text = validation.text
            tone = validation.tone
            status = REMINDER_STATUS_GENERATED
            validation_payload = {"ok": True, "fallbackUsed": False}
        return {
            "prompt_id": prompt_id,
            "prompt_version": prompt_version,
            "text": text,
            "tone": tone,
            "text_source": text_source,
            "delivery_status": status,
            "fallback_used": fallback_used,
            "failure_reason": validation.reason if fallback_used else None,
            "validation": validation_payload,
        }

    def _ai_text(
        self,
        prompt_id: str,
        prompt_version: str,
        scenario: str,
        context: Mapping,
        last_text: str,
    ) -> str | None:
        prompt = self.prompt_registry.get_prompt(prompt_id, prompt_version)
        if prompt is None:
            prompt = self.prompt_registry.get_prompt("reminder.fallback", "v1")
        if prompt is None:
            return None
        user_prompt = json.dumps(
            {
                "scenario": scenario,
                "context": dict(context),
                "lastReminderText": last_text,
                "outputFormat": {"text": "string", "tone": "string", "scenario": scenario, "safety": "ok"},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        response = self.ai_text_provider.complete(
            system_prompt=prompt.body,
            user_prompt=user_prompt,
            max_tokens=96,
            temperature=0.45,
        )
        return response.text if response is not None else None

    def _fallback_text(self, templates: list[str], *, last_text: str) -> str:
        for item in templates:
            if item != last_text:
                return item
        return templates[0]

    def _resolve_child_id(self, conn, family_id: str, child_id: str | None) -> str:
        if child_id:
            if not self.repository.child_exists(conn, family_id=family_id, child_id=child_id):
                raise ApiError("child_not_found", "孩子资料不存在。", 404)
            return child_id
        children = self.repository.list_children(conn, family_id=family_id)
        return str(children[0]["id"]) if children else ""


def _scenario(value: object) -> str:
    scenario = str(value or "").strip()
    if scenario not in CARE_SCENARIOS:
        raise ApiError("invalid_care_scenario", "看护能力暂不支持。")
    return scenario


def _required_text(data: dict, key: str, message: str) -> str:
    value = str(data.get(key) or "").strip()
    if not value:
        raise ApiError(f"missing_{key}", message)
    return value


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _device_id_for_trigger(decision: Mapping, data: dict) -> str | None:
    decision_device_id = _optional_text(decision.get("device_id"))
    request_device_id = _optional_text(data.get("deviceId"))
    if decision_device_id:
        if request_device_id and request_device_id != decision_device_id:
            raise ApiError("reminder_decision_device_mismatch", "提醒决策设备不匹配。", 409)
        return decision_device_id
    return request_device_id


def _limit(value: object) -> int:
    try:
        return max(1, min(int(value or 50), 100))
    except (TypeError, ValueError):
        return 50


def _bool_flag(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]
