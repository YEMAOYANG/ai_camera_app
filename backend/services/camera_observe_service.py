from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from core.database import Database
from core.security import now_ms
from integrations.camera_runtime.local_vision_prefilter import LocalVisionPrefilter
from integrations.camera_runtime.python_open_cv_yolo_prefilter import default_local_vision_prefilter
from services.observation_semantic_dedupe import semantic_dedupe_key
from services.observation_payload_builder import build_primary_payload
from repositories.care_repository import CareRepository
from schemas.vision import with_observation_reliability
from services.camera_ai_observation_service import CameraAiObservationService
from models.care import CARE_SCENARIO_MEAL_HABIT
from services.care_defaults import ensure_default_capability_configs, ensure_default_routine_windows
from services.observation_absence_mode import (
    absence_needs_kimi,
    absence_prefilter_skip,
    mark_absent_recorded,
    should_write_absent_record,
    update_absence_after_analysis,
    update_absence_after_prefilter,
)
from services.observation_cloud_gate import evaluate_cloud_gate, sync_care_behavior_from_analysis
from services.observation_runtime_state import (
    ObservationRuntimeStateStore,
    display_freshness_from_runtime,
)
from services.observation_session_state import (
    risk_escalated,
    session_snapshot_from_observation,
    should_force_screen_use_resample,
    should_post_observation,
    update_session_after_post,
)
from services.vision_child_context import load_child_vision_context
from services.vision_frame_gate import compute_dhash, frame_is_stable, next_frame_state
from services.vision_observation_enrich import enrich_observation
from services.vision_prefilter_service import prefilter_runtime_from_result

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ObserveTickResult:
    skipped: bool
    skip_reason: str
    analysis: dict[str, Any] | None
    posted: bool
    observation_count: int
    response: dict[str, Any] | None


class CameraObserveService:
    def __init__(
        self,
        database_url: str,
        *,
        vision_service=None,
        observation_service: CameraAiObservationService | None = None,
        vision_prefilter: LocalVisionPrefilter | None = None,
    ):
        repository = CareRepository(Database(database_url))
        self.repository = repository
        self.database_url = database_url
        self.runtime_store = ObservationRuntimeStateStore(repository)
        self.vision_service = vision_service
        self.observation_service = observation_service or CameraAiObservationService(database_url)
        self.vision_prefilter = vision_prefilter or default_local_vision_prefilter()

    def run_tick(
        self,
        *,
        family_id: str,
        child_id: str,
        device_id: str,
        image_bytes: bytes,
        content_type: str = "image/jpeg",
        source: str = "ai_camera_test",
        force_analyze: bool = False,
        force_post: bool = False,
        window_start_ms: int | None = None,
        window_end_ms: int | None = None,
        post_observation: Callable[[dict], dict] | None = None,
    ) -> ObserveTickResult:
        now = now_ms()
        start = window_start_ms if window_start_ms is not None else now
        end = window_end_ms if window_end_ms is not None else now
        if end <= start:
            end = start + 60_000

        frame_hash = compute_dhash(image_bytes)
        context = self._load_observe_context(
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            frame_hash=frame_hash,
            now=now,
        )

        prefilter = self.vision_prefilter.analyze_frame(
            image_bytes,
            previous=context.prefilter_previous,
            now_ms=now,
        )
        gate_decision = evaluate_cloud_gate(
            prefilter=prefilter,
            prefilter_previous=context.prefilter_previous,
            cloud_gate=context.runtime.get("cloud_gate"),
            care_behavior=context.runtime.get("care_behavior"),
            now_ms=now,
            force_analyze=force_analyze,
            child_id=child_id,
            family_id=family_id,
            device_id=device_id,
            enabled_capabilities=context.enabled_capabilities,
            routine_windows=context.routine_windows,
            meal_capability_config=context.meal_capability_config,
        )

        if gate_decision.observation_context_invalid:
            logger.warning(
                "observation tick skipped: invalid observation context",
                extra={
                    "family_id": family_id,
                    "device_id": device_id,
                    "skip_reason": gate_decision.reason,
                    "observation_context_invalid": True,
                },
            )
            return ObserveTickResult(
                skipped=True,
                skip_reason=gate_decision.reason,
                analysis=None,
                posted=False,
                observation_count=0,
                response=None,
            )

        call_kimi = gate_decision.call_kimi or absence_needs_kimi(
            context.absence_snapshot,
            person_detected=prefilter.person_detected,
            now_ms=now,
        )

        if not call_kimi:
            skip_before, skip_reason = absence_prefilter_skip(
                context.absence_snapshot,
                now_ms=now,
                person_detected=prefilter.person_detected,
            )
            if not skip_before:
                skip_reason = gate_decision.reason or "cloud_gate_skip"
            absence = update_absence_after_prefilter(
                dict(context.absence_snapshot),
                person_detected=prefilter.person_detected,
                now_ms=now,
                frame_stable=context.frame_stable,
            )
            runtime = self._apply_gate_runtime(
                context.runtime,
                prefilter=prefilter,
                gate_decision=gate_decision,
                frame_hash=frame_hash,
                now=now,
                display=_prefilter_skip_display(now_ms=now, gate_reason=skip_reason),
                absence=absence,
            )
            self._save_runtime(
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                payload=runtime,
                now=now,
            )
            return ObserveTickResult(
                skipped=True,
                skip_reason=skip_reason,
                analysis=None,
                posted=False,
                observation_count=0,
                response=None,
            )

        analysis = self._analyze_image(
            image_bytes=image_bytes,
            content_type=content_type,
            device_id=device_id,
            family_id=family_id,
            child_id=child_id,
            force_analyze=force_analyze,
        )
        analysis = enrich_observation(dict(analysis))
        current_session = session_snapshot_from_observation(analysis)
        has_person = analysis.get("has_person")

        care_behavior = sync_care_behavior_from_analysis(
            dict(gate_decision.next_care_behavior or context.runtime.get("care_behavior") or {}),
            analysis,
        )
        pending_runtime: dict[str, Any] | None = None
        post_reason = ""
        with self.repository.transaction() as conn:
            runtime = self.runtime_store.load(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
            )
            absence = update_absence_after_analysis(
                dict(runtime.get("absence") or context.absence_snapshot),
                has_person=has_person,
                now_ms=now,
                frame_stable=context.frame_stable,
            )
            runtime["absence"] = absence
            runtime["frame"] = next_frame_state(
                previous=runtime.get("frame"),
                current_hash=frame_hash,
                now_ms=now,
            )
            runtime["prefilter"] = prefilter_runtime_from_result(prefilter)
            runtime["cloud_gate"] = dict(gate_decision.next_cloud_gate)
            runtime["care_behavior"] = care_behavior
            runtime["session"]["last_cloud_at"] = now
            runtime["session"]["bucket"] = current_session["bucket"]
            runtime["session"]["risk"] = current_session["risk"]
            runtime["display"] = _runtime_display_from_analysis(analysis, now_ms=now)
            pending_runtime = runtime

            should_post, post_reason = should_post_observation(
                previous_session=context.previous_session,
                current_session=current_session,
                has_person=has_person,
                absence_mode=str(absence.get("mode") or "active"),
                recorded_absent=bool(absence.get("recorded_absent")),
            )
            screen_use_resample = should_force_screen_use_resample(
                previous_session=context.previous_session,
                current_session=current_session,
                now_ms=now,
            )
            post_force = (
                force_post
                or risk_escalated(context.previous_session, current_session)
                or screen_use_resample
            )
            if screen_use_resample and not should_post:
                post_reason = "screen_use_resample"
            if not should_post and not post_force:
                self._save_runtime_state(
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                    device_id=device_id,
                    payload=runtime,
                    now=now,
                )
                return ObserveTickResult(
                    skipped=True,
                    skip_reason=post_reason,
                    analysis=analysis,
                    posted=False,
                    observation_count=0,
                    response=None,
                )

        payload = build_primary_payload(
            analysis,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            source=source,
            window_start_ms=start,
            window_end_ms=end,
            observed_at=end,
        )
        if payload is None:
            if pending_runtime is not None:
                pending_runtime["display"] = _runtime_display_from_analysis(analysis, now_ms=now)
                self._save_runtime(
                    family_id=family_id,
                    child_id=child_id,
                    device_id=device_id,
                    payload=pending_runtime,
                    now=now,
                )
            return ObserveTickResult(
                skipped=True,
                skip_reason="no_actionable_signal",
                analysis=analysis,
                posted=False,
                observation_count=0,
                response=None,
            )

        if post_reason == "screen_use_resample":
            raw_detail = dict(payload.get("rawDetail") or {})
            raw_detail["observation_resample"] = True
            payload["rawDetail"] = raw_detail

        if (
            post_reason != "screen_use_resample"
            and self._semantic_duplicate(
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                payload=payload,
            )
        ):
            if pending_runtime is not None:
                self._save_runtime(
                    family_id=family_id,
                    child_id=child_id,
                    device_id=device_id,
                    payload=pending_runtime,
                    now=now,
                )
            return ObserveTickResult(
                skipped=True,
                skip_reason="semantic_duplicate",
                analysis=analysis,
                posted=False,
                observation_count=0,
                response=None,
            )

        poster = post_observation or self.observation_service.record_observation
        response = poster(payload)
        duplicate = bool(response.get("duplicate") or response.get("duplicateCareEvent"))
        posted = not duplicate and bool(response.get("ok"))

        runtime = dict(pending_runtime or {})
        if should_write_absent_record(runtime.get("absence") or {}, has_person=has_person) and posted:
            runtime["absence"] = mark_absent_recorded(dict(runtime.get("absence") or {}))
        if posted:
            runtime["session"] = update_session_after_post(
                dict(runtime.get("session") or {}),
                current_session,
                now_ms=now,
            )
        self._save_runtime(
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            payload=runtime,
            now=now,
        )

        return ObserveTickResult(
            skipped=False,
            skip_reason="",
            analysis=analysis,
            posted=posted,
            observation_count=1,
            response=response,
        )

    def _load_observe_context(
        self,
        *,
        family_id: str,
        child_id: str,
        device_id: str,
        frame_hash: str,
        now: int,
    ) -> "_ObserveContext":
        with self.repository.transaction() as conn:
            if str(child_id or "").strip():
                ensure_default_capability_configs(
                    self.repository,
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                    device_id=None,
                )
                ensure_default_routine_windows(
                    self.repository,
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                )
            capability_rows = (
                self.repository.list_capability_configs(
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                    device_id=device_id,
                )
                if str(child_id or "").strip()
                else []
            )
            routine_rows = (
                self.repository.list_routine_windows(
                    conn,
                    family_id=family_id,
                    child_id=child_id,
                )
                if str(child_id or "").strip()
                else []
            )
            runtime = self.runtime_store.load(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
            )
        meal_capability_config = next(
            (dict(row) for row in capability_rows if str(row.get("scenario") or "") == CARE_SCENARIO_MEAL_HABIT),
            None,
        )
        enabled_capabilities = [
            {
                "scenario": str(row.get("scenario") or ""),
                "enabled": bool(row.get("enabled")),
            }
            for row in capability_rows
        ]
        return _ObserveContext(
            runtime=runtime,
            previous_session=dict(runtime.get("session") or {}),
            frame_stable=frame_is_stable(
                previous=runtime.get("frame"),
                current_hash=frame_hash,
                now_ms=now,
            ),
            prefilter_previous=runtime.get("prefilter"),
            absence_snapshot=dict(runtime.get("absence") or {}),
            enabled_capabilities=enabled_capabilities,
            routine_windows=[dict(row) for row in routine_rows],
            meal_capability_config=meal_capability_config,
        )

    def _apply_gate_runtime(
        self,
        runtime: Mapping[str, Any],
        *,
        prefilter,
        gate_decision,
        frame_hash: str,
        now: int,
        display: dict[str, object],
        absence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        next_runtime = dict(runtime)
        next_runtime["prefilter"] = prefilter_runtime_from_result(prefilter)
        next_runtime["cloud_gate"] = dict(gate_decision.next_cloud_gate)
        if gate_decision.next_care_behavior is not None:
            next_runtime["care_behavior"] = dict(gate_decision.next_care_behavior)
        next_runtime["frame"] = next_frame_state(
            previous=runtime.get("frame"),
            current_hash=frame_hash,
            now_ms=now,
        )
        if absence is not None:
            next_runtime["absence"] = absence
        next_runtime["display"] = display
        return next_runtime

    def _save_runtime_state(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        device_id: str,
        payload: Mapping[str, Any],
        now: int,
    ) -> None:
        self.runtime_store.save(
            conn,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            payload=payload,
            now=now,
        )

    def _save_runtime(
        self,
        *,
        family_id: str,
        child_id: str,
        device_id: str,
        payload: Mapping[str, Any],
        now: int,
    ) -> None:
        with self.repository.transaction() as conn:
            self._save_runtime_state(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                payload=payload,
                now=now,
            )

    def _analyze_image(
        self,
        *,
        image_bytes: bytes,
        content_type: str,
        device_id: str,
        family_id: str,
        child_id: str,
        force_analyze: bool,
    ) -> dict[str, Any]:
        if self.vision_service is None:
            raise RuntimeError("Vision 服务未配置，无法分析画面。")
        vision_context = load_child_vision_context(
            self.database_url,
            family_id=family_id,
            child_id=child_id,
        )
        return with_observation_reliability(
            self.vision_service.analyze_snapshot(
                image_bytes=image_bytes,
                content_type=content_type,
                device_key=device_id,
                context=vision_context,
                force_analyze=force_analyze,
            )
        )

    def _semantic_duplicate(
        self,
        *,
        family_id: str,
        child_id: str,
        device_id: str,
        payload: Mapping[str, object],
    ) -> bool:
        signals = payload.get("signals")
        if not isinstance(signals, list) or not signals:
            return False
        signal_type = str(signals[0].get("signalType") or "")
        dedupe_key = semantic_dedupe_key(payload)
        since = now_ms() - 120_000
        with self.repository.transaction() as conn:
            row = self.repository.find_recent_duplicate_observation(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                scenario=str(payload.get("scenario") or ""),
                signal_type=signal_type,
                parent_summary=str(payload.get("parentSummary") or ""),
                raw_detail_json=dedupe_key,
                since=since,
            )
        return row is not None


@dataclass(frozen=True)
class _ObserveContext:
    runtime: dict[str, Any]
    previous_session: dict[str, Any]
    frame_stable: bool
    prefilter_previous: dict[str, Any] | None
    absence_snapshot: dict[str, Any]
    enabled_capabilities: list[dict[str, Any]]
    routine_windows: list[dict[str, Any]]
    meal_capability_config: dict[str, Any] | None


def _prefilter_skip_display(*, now_ms: int, gate_reason: str) -> dict[str, object]:
    return {
        "observed_at": now_ms,
        "freshness": "prefilter_only",
        "has_person": None,
        "activity": "",
        "raw_activity": "",
        "confidence": 0.0,
        "description": "",
        "decision_reason": gate_reason,
        "isReliable": False,
        "is_meal_scene": False,
    }


def _absent_runtime_display(now_ms: int) -> dict[str, object]:
    return {
        "observed_at": now_ms,
        "has_person": False,
        "activity": "离开",
        "raw_activity": "离开",
        "confidence": 0.0,
        "description": "刚才的画面里没有看到孩子。",
        "decision_reason": "",
        "isReliable": True,
        "is_meal_scene": False,
    }


def _runtime_display_from_analysis(analysis: Mapping[str, object], *, now_ms: int) -> dict[str, object]:
    enriched = enrich_observation(dict(analysis))
    display = {
        "observed_at": now_ms,
        "has_person": enriched.get("has_person"),
        "activity": enriched.get("activity") or enriched.get("raw_activity"),
        "raw_activity": enriched.get("raw_activity"),
        "confidence": enriched.get("confidence"),
        "description": enriched.get("description"),
        "decision_reason": enriched.get("decision_reason"),
        "isReliable": enriched.get("isReliable"),
        "is_meal_scene": enriched.get("is_meal_scene"),
    }
    display["freshness"] = display_freshness_from_runtime(
        now_ms=now_ms,
        display=display,
        last_kimi_at_ms=now_ms,
    )
    return display


def build_observe_service_from_env(environ: Mapping[str, str] | None = None) -> CameraObserveService:
    from services.service_factory import build_vision_observation_service_from_config
    from services.vision_worker_config import vision_worker_config

    env = dict(environ or os.environ)
    database_url = _database_url_from_env(env)
    vision_service = build_vision_observation_service_from_config(vision_worker_config(env))
    return CameraObserveService(
        database_url,
        vision_service=vision_service,
        vision_prefilter=default_local_vision_prefilter(),
    )


def _database_url_from_env(environ: Mapping[str, str]) -> str:
    url = str(environ.get("DATABASE_URL") or environ.get("APP_DATABASE_URL") or "").strip()
    if url:
        return url
    from core.config import AppConfig

    return AppConfig.from_env().DATABASE_URL
