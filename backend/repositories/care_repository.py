from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow


_REMINDER_EVENT_SELECT = """
SELECT r.*,
  c.status AS command_status,
  c.message AS command_message,
  c.response_payload AS command_response_payload,
  c.updated_at AS command_updated_at,
  c.completed_at AS command_completed_at
FROM reminder_events r
LEFT JOIN camera_commands c
  ON c.family_id = r.family_id AND c.id = r.command_id
"""


class CareRepository:
    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def list_children(self, conn: DatabaseConnection, *, family_id: str) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT *
                FROM children
                WHERE family_id = ?
                ORDER BY created_at, id
                """,
                (family_id,),
            ).fetchall()
        )

    def child_exists(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
    ) -> bool:
        row = conn.execute(
            "SELECT id FROM children WHERE family_id = ? AND id = ?",
            (family_id, child_id),
        ).fetchone()
        return row is not None

    def list_capability_configs(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str | None = None,
        device_id: str | None = None,
    ) -> list[DatabaseRow]:
        clauses = ["family_id = ?"]
        values: list[object] = [family_id]
        if child_id:
            clauses.append("child_id = ?")
            values.append(child_id)
        if device_id is not None:
            clauses.append("device_id = ?")
            values.append(device_id or "")
        return list(
            conn.execute(
                f"""
                SELECT *
                FROM care_capability_configs
                WHERE {' AND '.join(clauses)}
                ORDER BY child_id, device_id, scenario
                """,
                values,
            ).fetchall()
        )

    def get_capability_config(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        scenario: str,
        device_id: str | None = None,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM care_capability_configs
            WHERE family_id = ? AND child_id = ? AND device_id = ? AND scenario = ?
            LIMIT 1
            """,
            (family_id, child_id, device_id or "", scenario),
        ).fetchone()

    def get_capability_config_with_fallback(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        scenario: str,
        device_id: str | None = None,
    ) -> DatabaseRow | None:
        if device_id:
            exact = self.get_capability_config(
                conn,
                family_id=family_id,
                child_id=child_id,
                scenario=scenario,
                device_id=device_id,
            )
            if exact is not None:
                return exact
        return self.get_capability_config(
            conn,
            family_id=family_id,
            child_id=child_id,
            scenario=scenario,
            device_id=None,
        )

    def upsert_capability_config(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        scenario: str,
        device_id: str | None,
        enabled: bool,
        day_types: str,
        time_windows: str,
        min_observation_seconds: int,
        confidence_threshold: float,
        cooldown_seconds: int,
        daily_limit: int,
        parent_notify_threshold: int,
        allow_speaker: bool,
        record_only: bool,
        prompt_id: str,
        prompt_version: str,
        fallback_templates: str,
        now: int,
    ) -> DatabaseRow:
        existing = self.get_capability_config(
            conn,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            scenario=scenario,
        )
        if existing:
            conn.execute(
                """
                UPDATE care_capability_configs
                SET enabled = ?, day_types = ?, time_windows = ?,
                    min_observation_seconds = ?, confidence_threshold = ?,
                    cooldown_seconds = ?, daily_limit = ?,
                    parent_notify_threshold = ?, allow_speaker = ?, record_only = ?,
                    prompt_id = ?, prompt_version = ?, fallback_templates = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    int(enabled),
                    day_types,
                    time_windows,
                    min_observation_seconds,
                    confidence_threshold,
                    cooldown_seconds,
                    daily_limit,
                    parent_notify_threshold,
                    int(allow_speaker),
                    int(record_only),
                    prompt_id,
                    prompt_version,
                    fallback_templates,
                    now,
                    existing["id"],
                ),
            )
            return self.get_capability_config(
                conn,
                family_id=family_id,
                child_id=child_id,
                device_id=device_id,
                scenario=scenario,
            )

        config_id = f"carecap_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO care_capability_configs(
              id, family_id, child_id, device_id, scenario, enabled, day_types,
              time_windows, min_observation_seconds, confidence_threshold,
              cooldown_seconds, daily_limit, parent_notify_threshold,
              allow_speaker, record_only, prompt_id, prompt_version,
              fallback_templates, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                config_id,
                family_id,
                child_id,
                device_id or "",
                scenario,
                int(enabled),
                day_types,
                time_windows,
                min_observation_seconds,
                confidence_threshold,
                cooldown_seconds,
                daily_limit,
                parent_notify_threshold,
                int(allow_speaker),
                int(record_only),
                prompt_id,
                prompt_version,
                fallback_templates,
                now,
                now,
            ),
        )
        return self.get_capability_config(
            conn,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
            scenario=scenario,
        )

    def list_routine_windows(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str | None = None,
        day_type: str | None = None,
    ) -> list[DatabaseRow]:
        clauses = ["family_id = ?"]
        values: list[object] = [family_id]
        if child_id:
            clauses.append("child_id = ?")
            values.append(child_id)
        if day_type:
            clauses.append("day_type = ?")
            values.append(day_type)
        return list(
            conn.execute(
                f"""
                SELECT *
                FROM care_routine_windows
                WHERE {' AND '.join(clauses)}
                ORDER BY child_id, day_type, start_time, window_type
                """,
                values,
            ).fetchall()
        )

    def delete_routine_windows_for_child(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        day_type: str | None = None,
    ) -> None:
        if day_type:
            conn.execute(
                "DELETE FROM care_routine_windows WHERE family_id = ? AND child_id = ? AND day_type = ?",
                (family_id, child_id, day_type),
            )
            return
        conn.execute(
            "DELETE FROM care_routine_windows WHERE family_id = ? AND child_id = ?",
            (family_id, child_id),
        )

    def upsert_routine_window(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        day_type: str,
        window_type: str,
        start_time: str,
        end_time: str,
        enabled: bool,
        timezone: str,
        now: int,
    ) -> DatabaseRow:
        existing = conn.execute(
            """
            SELECT *
            FROM care_routine_windows
            WHERE family_id = ? AND child_id = ? AND day_type = ? AND window_type = ?
            LIMIT 1
            """,
            (family_id, child_id, day_type, window_type),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE care_routine_windows
                SET start_time = ?, end_time = ?, enabled = ?, timezone = ?, updated_at = ?
                WHERE id = ?
                """,
                (start_time, end_time, int(enabled), timezone, now, existing["id"]),
            )
            return conn.execute(
                "SELECT * FROM care_routine_windows WHERE id = ?",
                (existing["id"],),
            ).fetchone()
        window_id = f"careroutine_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO care_routine_windows(
              id, family_id, child_id, day_type, window_type, start_time,
              end_time, enabled, timezone, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                window_id,
                family_id,
                child_id,
                day_type,
                window_type,
                start_time,
                end_time,
                int(enabled),
                timezone,
                now,
                now,
            ),
        )
        return conn.execute("SELECT * FROM care_routine_windows WHERE id = ?", (window_id,)).fetchone()

    def create_observation_event(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        device_id: str | None,
        scenario: str,
        observed_at: int,
        confidence: float,
        evidence_type: str,
        parent_summary: str | None,
        raw_detail_json: str | None,
        source: str,
        source_event_id: str | None,
        source_type: str | None,
        source_id: str | None,
        task_id: str | None,
        now: int,
    ) -> DatabaseRow:
        event_id = f"obs_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO camera_observation_events(
              id, family_id, child_id, device_id, scenario, observed_at,
              confidence, evidence_type, parent_summary, raw_detail_json,
              source, source_event_id, source_type, source_id, task_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                family_id,
                child_id,
                device_id or "",
                scenario,
                observed_at,
                confidence,
                evidence_type,
                parent_summary,
                raw_detail_json,
                source,
                source_event_id,
                source_type,
                source_id,
                task_id,
                now,
            ),
        )
        return conn.execute("SELECT * FROM camera_observation_events WHERE id = ?", (event_id,)).fetchone()

    def get_observation_by_source_event(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        source: str,
        source_event_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM camera_observation_events
            WHERE family_id = ? AND source = ? AND source_event_id = ?
            LIMIT 1
            """,
            (family_id, source, source_event_id),
        ).fetchone()

    def latest_camera_observation_for_device(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        device_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM camera_observation_events
            WHERE family_id = ? AND device_id = ?
              AND evidence_type <> 'routine_window'
            ORDER BY observed_at DESC, created_at DESC
            LIMIT 1
            """,
            (family_id, device_id),
        ).fetchone()

    def create_behavior_signal(
        self,
        conn: DatabaseConnection,
        *,
        observation_event_id: str,
        family_id: str,
        child_id: str,
        device_id: str | None,
        scenario: str,
        signal_type: str,
        signal_value: str,
        confidence: float,
        duration_seconds: int,
        metadata_json: str | None,
        now: int,
    ) -> DatabaseRow:
        signal_id = f"signal_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO behavior_signals(
              id, observation_event_id, family_id, child_id, device_id,
              scenario, signal_type, signal_value, confidence,
              duration_seconds, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                signal_id,
                observation_event_id,
                family_id,
                child_id,
                device_id or "",
                scenario,
                signal_type,
                signal_value,
                confidence,
                duration_seconds,
                metadata_json,
                now,
            ),
        )
        return conn.execute("SELECT * FROM behavior_signals WHERE id = ?", (signal_id,)).fetchone()

    def upsert_behavior_state(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        device_id: str | None,
        scenario: str,
        state: str,
        status: str,
        started_at: int,
        last_observed_at: int,
        confidence: float,
        consecutive_seconds: int,
        parent_summary: str | None,
        raw_detail_json: str | None,
        now: int,
    ) -> DatabaseRow:
        existing = conn.execute(
            """
            SELECT *
            FROM current_behavior_states
            WHERE family_id = ? AND child_id = ? AND device_id = ?
              AND scenario = ? AND state = ?
            LIMIT 1
            """,
            (family_id, child_id, device_id or "", scenario, state),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE current_behavior_states
                SET status = ?, updated_at = ?, last_observed_at = ?,
                    confidence = ?, consecutive_seconds = ?,
                    parent_summary = ?, raw_detail_json = ?
                WHERE id = ?
                """,
                (
                    status,
                    now,
                    last_observed_at,
                    confidence,
                    consecutive_seconds,
                    parent_summary,
                    raw_detail_json,
                    existing["id"],
                ),
            )
            return conn.execute("SELECT * FROM current_behavior_states WHERE id = ?", (existing["id"],)).fetchone()
        state_id = f"state_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO current_behavior_states(
              id, family_id, child_id, device_id, scenario, state, status,
              started_at, updated_at, last_observed_at, confidence,
              consecutive_seconds, parent_summary, raw_detail_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state_id,
                family_id,
                child_id,
                device_id or "",
                scenario,
                state,
                status,
                started_at,
                now,
                last_observed_at,
                confidence,
                consecutive_seconds,
                parent_summary,
                raw_detail_json,
            ),
        )
        return conn.execute("SELECT * FROM current_behavior_states WHERE id = ?", (state_id,)).fetchone()

    def get_current_behavior_state(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        device_id: str | None,
        scenario: str,
        state: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM current_behavior_states
            WHERE family_id = ? AND child_id = ? AND device_id = ?
              AND scenario = ? AND state = ?
            LIMIT 1
            """,
            (family_id, child_id, device_id or "", scenario, state),
        ).fetchone()

    def create_reminder_decision(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        device_id: str | None,
        scenario: str,
        observation_event_id: str | None,
        behavior_state_id: str | None,
        source_type: str | None,
        source_id: str | None,
        task_id: str | None,
        decision: str,
        reason: str,
        reminder_level: str,
        cooldown_until: int | None,
        should_speak: bool,
        should_notify_parent: bool,
        policy_snapshot_json: str | None,
        now: int,
    ) -> DatabaseRow:
        decision_id = f"decision_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO reminder_decisions(
              id, family_id, child_id, device_id, scenario, observation_event_id,
              behavior_state_id, source_type, source_id, task_id, decision, reason,
              reminder_level, cooldown_until, should_speak, should_notify_parent,
              policy_snapshot_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                family_id,
                child_id,
                device_id or "",
                scenario,
                observation_event_id,
                behavior_state_id,
                source_type,
                source_id,
                task_id,
                decision,
                reason,
                reminder_level,
                cooldown_until,
                int(should_speak),
                int(should_notify_parent),
                policy_snapshot_json,
                now,
            ),
        )
        return conn.execute("SELECT * FROM reminder_decisions WHERE id = ?", (decision_id,)).fetchone()

    def get_reminder_decision(
        self,
        conn: DatabaseConnection,
        *,
        decision_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM reminder_decisions WHERE id = ? LIMIT 1",
            (decision_id,),
        ).fetchone()

    def latest_decision_for_observation(
        self,
        conn: DatabaseConnection,
        *,
        observation_event_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM reminder_decisions
            WHERE observation_event_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (observation_event_id,),
        ).fetchone()

    def create_reminder_event(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        device_id: str | None,
        scenario: str,
        reminder_decision_id: str | None,
        event_source: str,
        is_test: bool,
        source_type: str | None,
        source_id: str | None,
        task_id: str | None,
        prompt_id: str | None,
        prompt_version: str | None,
        text: str,
        tone: str,
        text_source: str,
        delivery_status: str,
        command_id: str | None,
        fallback_used: bool,
        generated_at: int,
        delivered_at: int | None,
        failure_reason: str | None,
        now: int,
    ) -> DatabaseRow:
        event_id = f"reminder_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO reminder_events(
              id, family_id, child_id, device_id, scenario, reminder_decision_id,
              event_source, is_test, source_type, source_id, task_id, prompt_id,
              prompt_version, text, tone, text_source, delivery_status, command_id,
              fallback_used, generated_at, delivered_at, failure_reason, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                family_id,
                child_id,
                device_id or "",
                scenario,
                reminder_decision_id,
                event_source,
                int(is_test),
                source_type,
                source_id,
                task_id,
                prompt_id,
                prompt_version,
                text,
                tone,
                text_source,
                delivery_status,
                command_id,
                int(fallback_used),
                generated_at,
                delivered_at,
                failure_reason,
                now,
            ),
        )
        return conn.execute("SELECT * FROM reminder_events WHERE id = ?", (event_id,)).fetchone()

    def get_reminder_event(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        event_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            f"""
            {_REMINDER_EVENT_SELECT}
            WHERE r.family_id = ? AND r.id = ?
            """,
            (family_id, event_id),
        ).fetchone()

    def update_reminder_event_delivery(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        event_id: str,
        delivery_status: str,
        command_id: str | None,
        delivered_at: int | None,
        failure_reason: str | None,
    ) -> DatabaseRow | None:
        conn.execute(
            """
            UPDATE reminder_events
            SET delivery_status = ?,
              command_id = COALESCE(?, command_id),
              delivered_at = ?,
              failure_reason = ?
            WHERE family_id = ? AND id = ?
            """,
            (
                delivery_status,
                command_id,
                delivered_at,
                failure_reason,
                family_id,
                event_id,
            ),
        )
        return self.get_reminder_event(conn, family_id=family_id, event_id=event_id)

    def list_reminder_events(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str | None = None,
        scenario: str | None = None,
        limit: int = 50,
        include_test: bool = False,
    ) -> list[DatabaseRow]:
        clauses = ["r.family_id = ?"]
        values: list[object] = [family_id]
        if child_id:
            clauses.append("r.child_id = ?")
            values.append(child_id)
        if scenario:
            clauses.append("r.scenario = ?")
            values.append(scenario)
        if not include_test:
            clauses.append("r.is_test = 0")
        values.append(max(1, min(int(limit), 100)))
        return list(
            conn.execute(
                f"""
                {_REMINDER_EVENT_SELECT}
                WHERE {' AND '.join(clauses)}
                ORDER BY r.created_at DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
        )

    def list_recent_real_reminder_events(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        scenario: str,
        since: int | None = None,
        limit: int = 50,
    ) -> list[DatabaseRow]:
        clauses = [
            "family_id = ?",
            "child_id = ?",
            "scenario = ?",
            "is_test = 0",
            "event_source NOT IN ('test', 'dry_run')",
        ]
        values: list[object] = [family_id, child_id, scenario]
        if since is not None:
            clauses.append("created_at >= ?")
            values.append(since)
        values.append(max(1, min(int(limit), 100)))
        return list(
            conn.execute(
                f"""
                SELECT *
                FROM reminder_events
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
        )

    def list_recent_allowed_decisions(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        scenario: str,
        since: int,
        limit: int = 20,
    ) -> list[DatabaseRow]:
        return list(
            conn.execute(
                """
                SELECT *
                FROM reminder_decisions
                WHERE family_id = ? AND child_id = ? AND scenario = ?
                  AND decision = 'allowed' AND created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (family_id, child_id, scenario, since, max(1, min(int(limit), 50))),
            ).fetchall()
        )

    def latest_reminder_event(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        scenario: str,
        include_test: bool = False,
    ) -> DatabaseRow | None:
        clauses = ["family_id = ?", "child_id = ?", "scenario = ?"]
        values: list[object] = [family_id, child_id, scenario]
        if not include_test:
            clauses.append("is_test = 0")
        return conn.execute(
            f"""
            SELECT *
            FROM reminder_events
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC
            LIMIT 1
            """,
            values,
        ).fetchone()

    def latest_real_reminder_event(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        scenario: str,
    ) -> DatabaseRow | None:
        rows = self.list_recent_real_reminder_events(
            conn,
            family_id=family_id,
            child_id=child_id,
            scenario=scenario,
            limit=1,
        )
        return rows[0] if rows else None

    def get_internal_reminder_event_for_decision(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        scenario: str,
        decision_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT r.*,
              c.status AS command_status,
              c.message AS command_message,
              c.response_payload AS command_response_payload,
              c.updated_at AS command_updated_at,
              c.completed_at AS command_completed_at
            FROM reminder_events r
            LEFT JOIN camera_commands c
              ON c.family_id = r.family_id AND c.id = r.command_id
            WHERE r.family_id = ? AND r.child_id = ? AND r.scenario = ?
              AND r.event_source = 'internal' AND r.is_test = 0
              AND r.source_type = 'reminder_decision' AND r.source_id = ?
            ORDER BY r.created_at ASC
            LIMIT 1
            """,
            (family_id, child_id, scenario, decision_id),
        ).fetchone()

    def list_pending_parent_review_events(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str | None = None,
        limit: int = 20,
    ) -> list[DatabaseRow]:
        clauses = ["family_id = ?", "status = 'pending'"]
        values: list[object] = [family_id]
        if child_id:
            clauses.append("child_id = ?")
            values.append(child_id)
        values.append(max(1, min(int(limit), 50)))
        return list(
            conn.execute(
                f"""
                SELECT *
                FROM review_items
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
        )

    def create_parent_review_event(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str | None,
        device_id: str | None,
        domain: str,
        scenario: str,
        item_type: str,
        source_type: str | None,
        source_id: str | None,
        priority: str,
        status: str,
        summary: str,
        related_observation_id: str | None,
        related_reminder_id: str | None,
        task_id: str | None,
        due_at: int | None,
        now: int,
    ) -> DatabaseRow:
        event_id = f"review_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO review_items(
              id, family_id, child_id, device_id, domain, scenario, item_type,
              source_type, source_id, priority, status, summary,
              related_observation_id, related_reminder_id, task_id, due_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                family_id,
                child_id,
                device_id or "",
                domain,
                scenario,
                item_type,
                source_type,
                source_id,
                priority,
                status,
                summary,
                related_observation_id,
                related_reminder_id,
                task_id,
                due_at,
                now,
            ),
        )
        return conn.execute("SELECT * FROM review_items WHERE id = ?", (event_id,)).fetchone()

    def find_recent_pending_review_item(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        domain: str,
        scenario: str,
        item_type: str,
        since: int,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT *
            FROM review_items
            WHERE family_id = ? AND child_id = ? AND domain = ? AND scenario = ?
              AND item_type = ? AND status = 'pending' AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (family_id, child_id, domain, scenario, item_type, since),
        ).fetchone()

    def create_internal_audit_event(
        self,
        conn: DatabaseConnection,
        *,
        audit_domain: str,
        actor_type: str,
        actor_id: str | None,
        route: str,
        source_ip: str | None,
        source_name: str | None,
        accepted: bool,
        reason: str,
        payload_ref: str | None,
        now: int,
    ) -> DatabaseRow:
        event_id = f"internalaudit_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO audit_events(
              id, audit_domain, actor_type, actor_id, route, source_ip, source_name,
              accepted, reason, payload_ref, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                audit_domain,
                actor_type,
                actor_id,
                route,
                source_ip,
                source_name,
                int(accepted),
                reason,
                payload_ref,
                now,
            ),
        )
        return conn.execute("SELECT * FROM audit_events WHERE id = ?", (event_id,)).fetchone()
