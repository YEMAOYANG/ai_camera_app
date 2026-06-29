from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from core.database import Database
from core.security import now_ms
from services.observation_semantic_dedupe import semantic_dedupe_key
from services.observation_payload_builder import build_primary_payload
from repositories.care_repository import CareRepository
from schemas.vision import with_observation_reliability
from services.camera_ai_observation_service import CameraAiObservationService
from services.observation_absence_mode import (
    mark_absent_recorded,
    should_skip_vision_before_analyze,
    should_write_absent_record,
    update_absence_after_analysis,
)
from services.observation_runtime_state import ObservationRuntimeStateStore
from services.observation_session_state import (
    risk_escalated,
    session_snapshot_from_observation,
    should_post_observation,
    update_session_after_post,
)
from services.vision_child_context import load_child_vision_context
from services.vision_frame_gate import compute_dhash, frame_is_stable, next_frame_state
from services.vision_observation_enrich import enrich_observation


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
    ):
        repository = CareRepository(Database(database_url))
        self.repository = repository
        self.database_url = database_url
        self.runtime_store = ObservationRuntimeStateStore(repository)
        self.vision_service = vision_service
        self.observation_service = observation_service or CameraAiObservationService(database_url)

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
        with self.repository.transaction() as conn:
            runtime = self.runtime_store.load(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
            )
            previous_session = dict(runtime.get("session") or {})
            frame_stable = frame_is_stable(
                previous=runtime.get("frame"),
                current_hash=frame_hash,
                now_ms=now,
            )
            skip_before, skip_reason = should_skip_vision_before_analyze(
                runtime.get("absence") or {},
                now_ms=now,
                frame_stable=frame_stable,
                force_analyze=force_analyze,
            )
            if skip_before:
                runtime["frame"] = next_frame_state(
                    previous=runtime.get("frame"),
                    current_hash=frame_hash,
                    now_ms=now,
                )
                runtime["display"] = _absent_runtime_display(now_ms=now)
                self.runtime_store.save(
                    conn,
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
            force_analyze=force_analyze or not frame_stable,
        )
        analysis = enrich_observation(dict(analysis))
        current_session = session_snapshot_from_observation(analysis)
        has_person = analysis.get("has_person")

        pending_runtime: dict[str, Any] | None = None
        with self.repository.transaction() as conn:
            runtime = self.runtime_store.load(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
            )
            absence = update_absence_after_analysis(
                dict(runtime.get("absence") or {}),
                has_person=has_person,
                now_ms=now,
                frame_stable=frame_stable,
            )
            runtime["absence"] = absence
            runtime["frame"] = next_frame_state(
                previous=runtime.get("frame"),
                current_hash=frame_hash,
                now_ms=now,
            )
            runtime["session"]["last_cloud_at"] = now
            runtime["session"]["bucket"] = current_session["bucket"]
            runtime["session"]["risk"] = current_session["risk"]
            runtime["display"] = _runtime_display_from_analysis(analysis, now_ms=now)
            pending_runtime = runtime

            post_force = force_post or risk_escalated(previous_session, current_session)
            should_post, post_reason = should_post_observation(
                previous_session=previous_session,
                current_session=current_session,
                has_person=has_person,
                absence_mode=str(absence.get("mode") or "active"),
                recorded_absent=bool(absence.get("recorded_absent")),
            )
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

        if not str(child_id or "").strip():
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
                skip_reason="missing_child_id",
                analysis=analysis,
                posted=False,
                observation_count=0,
                response=None,
            )

        if self._semantic_duplicate(
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            payload=payload,
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
    return {
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


def build_observe_service_from_env(environ: Mapping[str, str] | None = None) -> CameraObserveService:
    from services.service_factory import build_vision_observation_service_from_config
    from services.vision_worker_config import vision_worker_config

    env = dict(environ or os.environ)
    database_url = _database_url_from_env(env)
    vision_service = build_vision_observation_service_from_config(vision_worker_config(env))
    return CameraObserveService(database_url, vision_service=vision_service)


def _database_url_from_env(environ: Mapping[str, str]) -> str:
    url = str(environ.get("DATABASE_URL") or environ.get("APP_DATABASE_URL") or "").strip()
    if url:
        return url
    from core.config import AppConfig

    return AppConfig.from_env().DATABASE_URL
