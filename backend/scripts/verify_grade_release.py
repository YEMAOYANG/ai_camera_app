from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.database import Database, DatabaseConnection
from core.security import now_ms as current_time_ms


GRADE_CODE = "primary_1"
FORMAL_PUBLICATION_CONTRACT_VERSION = "mira.learning.formal-publication.v1"
CANDIDATE_BINDING_CONTRACT_VERSION = (
    "mira.learning.candidate-runtime-binding.v1"
)
REPORT_SCHEMA_VERSION = "mira.learning.grade-release-verification.v1"

REQUIRED_MIGRATIONS = (
    "056_learning_curriculum_preparation_content_stage.sql",
    "057_learning_curriculum_classroom_publication.sql",
    "058_learning_formal_qwen_audio_receipts.sql",
    "059_learning_openmaic_provider_readiness.sql",
    "060_learning_student_formal_session_bindings.sql",
    "061_learning_openmaic_runtime_events.sql",
    "065_learning_openmaic_release_provider_readiness.sql",
    "066_learning_student_formal_session_binding_contract_split.sql",
    "067_learning_student_formal_session_binding_build_package_split.sql",
)

REQUIRED_TABLES = (
    "schema_migrations",
    "learning_curriculum_grade_release_pointers",
    "learning_curriculum_grade_release_history",
    "learning_catalog_releases",
    "learning_catalog_release_items",
    "learning_catalog_build_items",
    "learning_courses",
    "learning_lesson_packages",
    "learning_openmaic_runtime_classrooms",
    "learning_curriculum_classroom_item_receipts",
    "learning_formal_qwen_audio_jobs",
    "learning_openmaic_provider_readiness_jobs",
    "learning_openmaic_provider_readiness_call_receipts",
    "learning_student_formal_session_bindings",
    "learning_openmaic_runtime_event_streams",
    "learning_openmaic_runtime_events",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class VerificationInputError(ValueError):
    pass


def verify_grade_release(
    database: Any,
    *,
    phase: str,
    configured_grade_allowlist: Sequence[str],
    now_ms: int,
    max_event_lag_ms: int,
) -> dict[str, object]:
    """Verify one production grade using only a read-only transaction.

    The report deliberately contains aggregate state only. Database identities,
    hashes, prompts, credentials and child-level data never leave this function.
    """

    if phase not in {"preflight", "postflight"}:
        raise VerificationInputError("phase must be preflight or postflight")
    if list(configured_grade_allowlist) != [GRADE_CODE]:
        raise VerificationInputError(
            "production grade allowlist must be exactly primary_1"
        )
    if type(now_ms) is not int or now_ms <= 0:
        raise VerificationInputError("verification clock is invalid")
    if type(max_event_lag_ms) is not int or max_event_lag_ms < 0:
        raise VerificationInputError("event lag threshold is invalid")

    with database.transaction() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        return _verify_connection(
            conn,
            phase=phase,
            now_ms=now_ms,
            max_event_lag_ms=max_event_lag_ms,
        )


def _verify_connection(
    conn: DatabaseConnection,
    *,
    phase: str,
    now_ms: int,
    max_event_lag_ms: int,
) -> dict[str, object]:
    tables = {
        str(row.get("table_name") or row.get("TABLE_NAME") or "")
        for row in conn.execute(
            """
            SELECT /* verify_grade_release:schema */ table_name
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name IN (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
              )
            """,
            REQUIRED_TABLES,
        ).fetchall()
    }
    schema_ok = tables == set(REQUIRED_TABLES)
    migrations: set[str] = set()
    if "schema_migrations" in tables:
        migrations = {
            str(row.get("version") or "")
            for row in conn.execute(
                """
                SELECT /* verify_grade_release:migrations */ version
                FROM schema_migrations
                WHERE version IN (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                REQUIRED_MIGRATIONS,
            ).fetchall()
        }
    migrations_ok = migrations == set(REQUIRED_MIGRATIONS)

    pointer: Mapping[str, object] | None = None
    if schema_ok:
        pointer = conn.execute(
            """
            SELECT /* verify_grade_release:pointer */
              pointer.pointer_revision,
              pointer.target_fingerprint AS pointer_target_fingerprint,
              pointer.contract_version AS pointer_contract_version,
              pointer.release_id AS pointer_release_id,
              pointer.history_id AS pointer_history_id,
              pointer.activated_at AS pointer_activated_at,
              history.id AS history_id,
              history.grade_code AS history_grade_code,
              history.pointer_revision AS history_pointer_revision,
              history.target_fingerprint AS history_target_fingerprint,
              history.contract_version AS history_contract_version,
              history.release_id AS history_release_id,
              history.activation_source AS history_activation_source,
              history.publication_request_id AS history_publication_request_id,
              history.publication_receipt_hash
                AS history_publication_receipt_hash,
              history.activated_at AS history_activated_at,
              history.superseded_at AS history_superseded_at,
              release_row.status AS release_status,
              release_row.quality_status AS release_quality_status,
              release_row.ready_item_count AS release_ready_item_count,
              release_row.retired_at AS release_retired_at
            FROM learning_curriculum_grade_release_pointers AS pointer
            JOIN learning_curriculum_grade_release_history AS history
              ON history.id = pointer.history_id
            JOIN learning_catalog_releases AS release_row
              ON release_row.id = pointer.release_id
            WHERE pointer.grade_code = ? AND pointer.pointer_revision >= 1
            LIMIT 1
            """,
            (GRADE_CODE,),
        ).fetchone()

    pointer_present = pointer is not None
    pointer_exact = _pointer_is_exact(pointer)
    pointer_ok = pointer_exact or (phase == "preflight" and not pointer_present)

    evidence = _empty_evidence()
    event_lag = _empty_event_lag()
    publication_receipts_exact = False
    if pointer_exact and pointer is not None:
        release_id = str(pointer["pointer_release_id"])
        target_fingerprint = str(pointer["pointer_target_fingerprint"])
        evidence = dict(
            conn.execute(
                """
                SELECT /* verify_grade_release:evidence */
                  COUNT(*) AS item_count,
                  SUM(CASE WHEN
                    build_item.id IS NOT NULL
                    AND build_item.release_id = release_item.release_id
                    AND build_item.grade_code = release_item.grade_code
                    AND build_item.course_id = release_item.course_id
                    AND build_item.course_version = release_item.course_version
                    AND release_item.status = 'published'
                    AND release_item.quality_status = 'ready'
                    AND release_item.retired_at IS NULL
                    AND course.status = 'published'
                    AND course.quality_status = 'released'
                    AND course.retired_at IS NULL
                    AND package.status = 'published'
                    AND package.retired_at IS NULL
                    AND runtime.id IS NOT NULL
                    AND runtime.status = 'ready'
                    AND runtime.retired_at IS NULL
                    AND runtime.candidate_build_item_id = build_item.id
                    AND runtime.candidate_release_id = release_item.release_id
                    AND runtime.candidate_grade_code = release_item.grade_code
                    AND runtime.candidate_target_fingerprint = ?
                    AND runtime.candidate_binding_contract_version = ?
                    AND runtime.course_id = release_item.course_id
                    AND runtime.course_version = release_item.course_version
                    AND runtime.package_id = release_item.package_id
                    AND runtime.package_version = release_item.package_version
                    AND JSON_VALID(runtime.feature_manifest_json) = 1
                    AND JSON_TYPE(JSON_EXTRACT(
                      runtime.feature_manifest_json, '$.sceneCount'
                    )) = 'INTEGER'
                    AND JSON_TYPE(JSON_EXTRACT(
                      runtime.feature_manifest_json,
                      '$.formalEvidence.speechActionCount'
                    )) = 'INTEGER'
                    AND CAST(JSON_UNQUOTE(JSON_EXTRACT(
                      runtime.feature_manifest_json, '$.sceneCount'
                    )) AS UNSIGNED) BETWEEN 1 AND 60
                    AND CAST(JSON_UNQUOTE(JSON_EXTRACT(
                      runtime.feature_manifest_json,
                      '$.formalEvidence.speechActionCount'
                    )) AS UNSIGNED) BETWEEN
                      CAST(JSON_UNQUOTE(JSON_EXTRACT(
                        runtime.feature_manifest_json, '$.sceneCount'
                      )) AS UNSIGNED)
                      AND LEAST(
                        240,
                        CAST(JSON_UNQUOTE(JSON_EXTRACT(
                          runtime.feature_manifest_json, '$.sceneCount'
                        )) AS UNSIGNED) * 20
                      )
                    AND receipt.build_item_id = build_item.id
                    AND receipt.release_id = release_item.release_id
                    AND receipt.grade_code = release_item.grade_code
                    AND receipt.target_fingerprint = ?
                    AND receipt.binding_contract_version = ?
                    AND receipt.runtime_classroom_id = runtime.id
                    AND receipt.course_id = release_item.course_id
                    AND receipt.course_version = release_item.course_version
                    AND receipt.package_id = release_item.package_id
                    AND receipt.package_version = release_item.package_version
                    AND receipt.classroom_status = 'passed'
                    AND receipt.tts_status = 'passed'
                    AND receipt.asr_roundtrip_status = 'passed'
                    AND receipt.conversation_provider_status = 'passed'
                    AND receipt.auto_validated = 1
                    AND receipt.auto_validation_contract_version = ?
                    AND receipt.auto_validation_receipt_hash IS NOT NULL
                    AND receipt.approved = 0
                    AND receipt.publication_status = 'published'
                    AND receipt.publication_receipt_hash IS NOT NULL
                    AND audio.build_item_id = build_item.id
                    AND audio.release_id = release_item.release_id
                    AND audio.grade_code = release_item.grade_code
                    AND audio.target_fingerprint = ?
                    AND audio.runtime_classroom_id = runtime.id
                    AND audio.runtime_request_id = runtime.request_id
                    AND audio.upstream_classroom_id = runtime.upstream_classroom_id
                    AND audio.course_id = release_item.course_id
                    AND audio.course_version = release_item.course_version
                    AND audio.package_id = release_item.package_id
                    AND audio.package_version = release_item.package_version
                    AND audio.subject = release_item.subject
                    AND audio.state = 'auto_validated'
                    AND audio.audio_contract_version =
                      'mira.learning.formal-qwen-audio.v1'
                    AND audio.pcm_validation_contract_version =
                      'mira.learning.formal-pcm-validation.v1'
                    AND audio.asr_roundtrip_contract_version =
                      'mira.learning.formal-qwen-asr-roundtrip.v1'
                    AND audio.terminal_receipt_version =
                      'mira.learning.formal-qwen-audio-job.v1'
                    AND audio.expected_segment_count BETWEEN 1 AND 240
                    AND audio.expected_segment_count =
                      CAST(JSON_UNQUOTE(JSON_EXTRACT(
                        runtime.feature_manifest_json,
                        '$.formalEvidence.speechActionCount'
                      )) AS UNSIGNED)
                    AND audio.tts_attempted_count = audio.expected_segment_count
                    AND audio.tts_completed_count = audio.expected_segment_count
                    AND audio.audio_validated_count = audio.expected_segment_count
                    AND audio.asr_attempted_count = audio.expected_segment_count
                    AND audio.asr_passed_count = audio.expected_segment_count
                    AND audio.terminal_receipt_hash IS NOT NULL
                    AND audio.teacher_gender = audio.voice_gender
                    AND audio.voice_contract_version =
                      'mira.openmaic.formal-subject-qwen3-voice.v1'
                    AND audio.tts_provider_id = 'qwen-tts'
                    AND audio.tts_model_id = 'qwen3-tts-flash'
                    AND audio.tts_fallback_allowed = 0
                    AND audio.asr_provider_id = 'qwen-asr'
                    AND audio.asr_model_id = 'qwen3-asr-flash'
                    AND audio.asr_fallback_allowed = 0
                    AND provider.build_item_id = (
                      SELECT witness.id
                      FROM learning_catalog_build_items AS witness
                      WHERE witness.build_job_id = build_item.build_job_id
                        AND witness.release_id = release_item.release_id
                      ORDER BY witness.subject_ordinal,
                        witness.boundary_ordinal, witness.variant_ordinal,
                        witness.id
                      LIMIT 1
                    )
                    AND provider.release_id = release_item.release_id
                    AND provider.grade_code = release_item.grade_code
                    AND provider.target_fingerprint = ?
                    AND provider.state = 'auto_validated'
                    AND provider.provider_contract_version =
                      'mira.openmaic.formal-provider-readiness.v2'
                    AND provider.route_session_contract_version =
                      'mira.openmaic.conversation-proof.v1'
                    AND provider.expected_provider_call_count = 5
                    AND provider.provider_attempted_count = 5
                    AND provider.provider_passed_count = 5
                    AND provider.provider_receipt_hash IS NOT NULL
                    AND provider.route_session_provider_call = 0
                    AND provider.route_session_status = 'passed'
                    AND (SELECT COUNT(*)
                           FROM learning_openmaic_provider_readiness_call_receipts
                             AS provider_call
                          WHERE provider_call.readiness_id = provider.id
                            AND provider_call.state = 'passed'
                            AND provider_call.provider_call = 1) = 5
                    THEN 1 ELSE 0 END) AS exact_item_count,
                  SUM(CASE WHEN release_item.subject = 'chinese'
                    THEN 1 ELSE 0 END) AS chinese_count,
                  SUM(CASE WHEN release_item.subject = 'math'
                    THEN 1 ELSE 0 END) AS math_count,
                  SUM(CASE WHEN release_item.subject = 'english'
                    THEN 1 ELSE 0 END) AS english_count
                FROM learning_catalog_release_items AS release_item
                LEFT JOIN learning_catalog_build_items AS build_item
                  ON build_item.release_id = release_item.release_id
                 AND build_item.grade_code = release_item.grade_code
                 AND build_item.course_id = release_item.course_id
                 AND build_item.course_version = release_item.course_version
                LEFT JOIN learning_courses AS course
                  ON course.id = release_item.course_id
                 AND course.version = release_item.course_version
                LEFT JOIN learning_lesson_packages AS package
                  ON package.id = release_item.package_id
                 AND package.version = release_item.package_version
                LEFT JOIN learning_openmaic_runtime_classrooms AS runtime
                  ON runtime.candidate_build_item_id = build_item.id
                LEFT JOIN learning_curriculum_classroom_item_receipts AS receipt
                  ON receipt.build_item_id = build_item.id
                LEFT JOIN learning_formal_qwen_audio_jobs AS audio
                  ON audio.build_item_id = build_item.id
                LEFT JOIN learning_openmaic_provider_readiness_jobs AS provider
                  ON provider.release_id = release_item.release_id
                 AND provider.grade_code = release_item.grade_code
                 AND provider.target_fingerprint = ?
                WHERE release_item.release_id = ?
                  AND release_item.grade_code = ?
                """,
                (
                    target_fingerprint,
                    CANDIDATE_BINDING_CONTRACT_VERSION,
                    target_fingerprint,
                    CANDIDATE_BINDING_CONTRACT_VERSION,
                    FORMAL_PUBLICATION_CONTRACT_VERSION,
                    target_fingerprint,
                    target_fingerprint,
                    target_fingerprint,
                    release_id,
                    GRADE_CODE,
                ),
            ).fetchone()
            or _empty_evidence()
        )
        publication_rows = conn.execute(
            """
            SELECT /* verify_grade_release:publication_receipts */
              build_item.build_job_id AS build_id,
              build_item.id AS build_item_id,
              runtime.id AS runtime_classroom_id,
              release_item.course_id, release_item.course_version,
              release_item.package_id, release_item.package_version,
              audio.classroom_content_sha256,
              audio.terminal_receipt_hash AS audio_receipt_sha256,
              provider.provider_receipt_hash AS provider_receipt_sha256,
              receipt.conversation_provider_receipt_hash
                AS provider_binding_receipt_sha256,
              receipt.publication_receipt_hash
                AS publication_receipt_sha256
            FROM learning_catalog_release_items AS release_item
            JOIN learning_catalog_build_items AS build_item
              ON build_item.release_id = release_item.release_id
             AND build_item.grade_code = release_item.grade_code
             AND build_item.course_id = release_item.course_id
             AND build_item.course_version = release_item.course_version
            JOIN learning_curriculum_classroom_item_receipts AS receipt
              ON receipt.build_item_id = build_item.id
            JOIN learning_openmaic_runtime_classrooms AS runtime
              ON runtime.id = receipt.runtime_classroom_id
            JOIN learning_formal_qwen_audio_jobs AS audio
              ON audio.build_item_id = build_item.id
            JOIN learning_openmaic_provider_readiness_jobs AS provider
              ON provider.release_id = release_item.release_id
             AND provider.grade_code = release_item.grade_code
             AND provider.target_fingerprint = receipt.target_fingerprint
            WHERE release_item.release_id = ?
              AND release_item.grade_code = ?
            ORDER BY build_item.subject_ordinal,
              build_item.boundary_ordinal,
              build_item.variant_ordinal, build_item.id
            """,
            (release_id, GRADE_CODE),
        ).fetchall()
        publication_receipts_exact = _publication_receipts_are_exact(
            publication_rows,
            release_id=release_id,
            target_fingerprint=target_fingerprint,
            expected_aggregate_sha256=str(
                pointer.get("history_publication_receipt_hash") or ""
            ),
        )
        event_lag = dict(
            conn.execute(
                """
                SELECT /* verify_grade_release:event_lag */
                  (SELECT COUNT(*)
                     FROM learning_student_formal_session_bindings
                       AS bound_session
                    WHERE bound_session.release_id = ?
                      AND bound_session.grade_code = ?)
                    AS bound_session_count,
                  COUNT(DISTINCT stream.runtime_session_id) AS stream_count,
                  SUM(CASE WHEN stream.runtime_session_id IS NOT NULL
                    AND binding.learning_session_id IS NOT NULL
                    AND stream.last_sequence =
                      (SELECT COUNT(*)
                         FROM learning_openmaic_runtime_events AS event_row
                        WHERE event_row.runtime_session_id =
                          stream.runtime_session_id)
                    THEN 1 ELSE 0 END) AS exact_stream_count,
                  SUM(CASE WHEN stream.runtime_session_id IS NOT NULL
                    AND stream.completed_at IS NULL
                    THEN 1 ELSE 0 END) AS active_stream_count,
                  SUM(CASE WHEN stream.runtime_session_id IS NOT NULL
                    AND stream.completed_at IS NOT NULL
                    THEN 1 ELSE 0 END) AS completed_stream_count,
                  COALESCE(MAX(CASE WHEN stream.runtime_session_id IS NOT NULL
                    AND stream.completed_at IS NULL
                    THEN GREATEST(0, ? - stream.updated_at)
                    ELSE 0 END), 0) AS max_active_event_lag_ms
                FROM learning_openmaic_runtime_event_streams AS stream
                LEFT JOIN learning_student_formal_session_bindings AS binding
                  ON binding.learning_session_id = stream.learning_session_id
                 AND binding.runtime_classroom_id = stream.runtime_classroom_id
                 AND binding.release_id = stream.release_id
                 AND binding.target_fingerprint = stream.target_fingerprint
                WHERE stream.release_id = ? AND stream.target_fingerprint = ?
                """,
                (
                    release_id,
                    GRADE_CODE,
                    int(now_ms),
                    release_id,
                    target_fingerprint,
                ),
            ).fetchone()
            or _empty_event_lag()
        )

    item_count = int(evidence.get("item_count") or 0)
    exact_item_count = int(evidence.get("exact_item_count") or 0)
    evidence_ok = bool(
        pointer_exact
        and item_count == 30
        and exact_item_count == 30
        and int(evidence.get("chinese_count") or 0) == 12
        and int(evidence.get("math_count") or 0) == 9
        and int(evidence.get("english_count") or 0) == 9
        and publication_receipts_exact
    )
    stream_count = int(event_lag.get("stream_count") or 0)
    exact_stream_count = int(event_lag.get("exact_stream_count") or 0)
    bound_session_count = int(event_lag.get("bound_session_count") or 0)
    event_consistency_ok = bool(
        stream_count == exact_stream_count and stream_count <= bound_session_count
    )
    observed_lag_ms = int(event_lag.get("max_active_event_lag_ms") or 0)
    event_lag_ok = observed_lag_ms <= max_event_lag_ms

    no_pointer_preflight = phase == "preflight" and not pointer_present
    checks = [
        {"name": "gradeAllowlist", "ok": True},
        {"name": "schema", "ok": schema_ok},
        {"name": "migrations", "ok": migrations_ok},
        {"name": "activePointer", "ok": pointer_ok},
        {
            "name": "releaseEvidence",
            "ok": evidence_ok or no_pointer_preflight,
        },
        {
            "name": "eventConsistency",
            "ok": event_consistency_ok if pointer_exact else no_pointer_preflight,
        },
        {
            "name": "eventLag",
            "ok": event_lag_ok if pointer_exact else no_pointer_preflight,
        },
    ]
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "phase": phase,
        "gradeCode": GRADE_CODE,
        "publicationContractVersion": FORMAL_PUBLICATION_CONTRACT_VERSION,
        "ok": all(bool(check["ok"]) for check in checks),
        "checks": checks,
        "summary": {
            "activePointerPresent": pointer_present,
            "pointerRevision": (
                int(pointer.get("pointer_revision") or 0)
                if pointer_exact and pointer is not None
                else 0
            ),
            "releaseItemCount": item_count,
            "exactEvidenceItemCount": exact_item_count,
            "boundSessionCount": bound_session_count,
            "eventStreamCount": stream_count,
            "activeEventStreamCount": int(
                event_lag.get("active_stream_count") or 0
            ),
            "completedEventStreamCount": int(
                event_lag.get("completed_stream_count") or 0
            ),
            "maxActiveEventLagMs": observed_lag_ms,
            "maxAllowedEventLagMs": max_event_lag_ms,
        },
    }


def _pointer_is_exact(row: Mapping[str, object] | None) -> bool:
    if row is None:
        return False
    return bool(
        int(row.get("pointer_revision") or 0) >= 1
        and str(row.get("pointer_contract_version") or "")
        == FORMAL_PUBLICATION_CONTRACT_VERSION
        and _SHA256.fullmatch(
            str(row.get("pointer_target_fingerprint") or "")
        )
        is not None
        and str(row.get("pointer_release_id") or "")
        == str(row.get("history_release_id") or "")
        and str(row.get("pointer_history_id") or "")
        == str(row.get("history_id") or "")
        and int(row.get("pointer_revision") or 0)
        == int(row.get("history_pointer_revision") or 0)
        and str(row.get("pointer_target_fingerprint") or "")
        == str(row.get("history_target_fingerprint") or "")
        and str(row.get("pointer_contract_version") or "")
        == str(row.get("history_contract_version") or "")
        and int(row.get("pointer_activated_at") or 0)
        == int(row.get("history_activated_at") or 0)
        and str(row.get("history_grade_code") or "") == GRADE_CODE
        and str(row.get("history_activation_source") or "")
        == "formal_publication"
        and bool(str(row.get("history_publication_request_id") or ""))
        and _SHA256.fullmatch(
            str(row.get("history_publication_receipt_hash") or "")
        )
        is not None
        and str(row.get("release_status") or "") == "published"
        and str(row.get("release_quality_status") or "") == "ready"
        and int(row.get("release_ready_item_count") or 0) == 30
        and row.get("release_retired_at") is None
    )


def _publication_receipts_are_exact(
    rows: Sequence[Mapping[str, object]],
    *,
    release_id: str,
    target_fingerprint: str,
    expected_aggregate_sha256: str,
) -> bool:
    if len(rows) != 30 or _SHA256.fullmatch(expected_aggregate_sha256) is None:
        return False
    build_ids = {str(row.get("build_id") or "") for row in rows}
    if len(build_ids) != 1 or "" in build_ids:
        return False
    build_id = next(iter(build_ids))
    aggregate_items: list[dict[str, str]] = []
    for row in rows:
        sha_values = (
            str(row.get("classroom_content_sha256") or ""),
            str(row.get("audio_receipt_sha256") or ""),
            str(row.get("provider_receipt_sha256") or ""),
            str(row.get("provider_binding_receipt_sha256") or ""),
            str(row.get("publication_receipt_sha256") or ""),
        )
        if any(_SHA256.fullmatch(value) is None for value in sha_values):
            return False
        item_payload = {
            "schemaVersion": FORMAL_PUBLICATION_CONTRACT_VERSION,
            "gradeCode": GRADE_CODE,
            "buildId": build_id,
            "releaseId": release_id,
            "targetFingerprint": target_fingerprint,
            "buildItemId": str(row.get("build_item_id") or ""),
            "runtimeClassroomId": str(
                row.get("runtime_classroom_id") or ""
            ),
            "course": {
                "id": str(row.get("course_id") or ""),
                "version": str(row.get("course_version") or ""),
            },
            "package": {
                "id": str(row.get("package_id") or ""),
                "version": int(row.get("package_version") or 0),
            },
            "classroomContentSha256": sha_values[0],
            "audioReceiptSha256": sha_values[1],
            "providerReceiptSha256": sha_values[2],
            "providerBindingReceiptSha256": sha_values[3],
        }
        item_receipt = hashlib.sha256(
            _encode_json(item_payload).encode("utf-8")
        ).hexdigest()
        if item_receipt != sha_values[4]:
            return False
        aggregate_items.append(
            {
                "buildItemId": str(row.get("build_item_id") or ""),
                "receiptSha256": item_receipt,
            }
        )
    aggregate = {
        "schemaVersion": FORMAL_PUBLICATION_CONTRACT_VERSION,
        "gradeCode": GRADE_CODE,
        "buildId": build_id,
        "releaseId": release_id,
        "targetFingerprint": target_fingerprint,
        "items": aggregate_items,
    }
    return hashlib.sha256(
        _encode_json(aggregate).encode("utf-8")
    ).hexdigest() == expected_aggregate_sha256


def _encode_json(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _empty_evidence() -> dict[str, int]:
    return {
        "item_count": 0,
        "exact_item_count": 0,
        "chinese_count": 0,
        "math_count": 0,
        "english_count": 0,
    }


def _empty_event_lag() -> dict[str, int]:
    return {
        "bound_session_count": 0,
        "stream_count": 0,
        "exact_stream_count": 0,
        "active_stream_count": 0,
        "completed_stream_count": 0,
        "max_active_event_lag_ms": 0,
    }


def _configured_grade_allowlist() -> list[str]:
    raw = os.environ.get(
        "LEARNING_CURRICULUM_PREPARATION_GRADE_ALLOWLIST", GRADE_CODE
    )
    return [part.strip() for part in raw.split(",") if part.strip()]


def _safe_error_payload(code: str, *, phase: str) -> dict[str, object]:
    return {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "phase": phase,
        "gradeCode": GRADE_CODE,
        "publicationContractVersion": FORMAL_PUBLICATION_CONTRACT_VERSION,
        "ok": False,
        "errorCode": code,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only verification for the primary_1 formal release."
    )
    parser.add_argument(
        "--phase", choices=("preflight", "postflight"), default="preflight"
    )
    parser.add_argument(
        "--max-event-lag-seconds", type=int, default=300
    )
    args = parser.parse_args(argv)
    if args.max_event_lag_seconds < 0:
        print(
            json.dumps(
                _safe_error_payload("invalid_event_lag_threshold", phase=args.phase),
                sort_keys=True,
            )
        )
        return 2
    database_url = str(os.environ.get("DATABASE_URL") or "").strip()
    if not database_url:
        print(
            json.dumps(
                _safe_error_payload("database_configuration_missing", phase=args.phase),
                sort_keys=True,
            )
        )
        return 2
    try:
        report = verify_grade_release(
            Database(database_url),
            phase=args.phase,
            configured_grade_allowlist=_configured_grade_allowlist(),
            now_ms=current_time_ms(),
            max_event_lag_ms=args.max_event_lag_seconds * 1_000,
        )
    except VerificationInputError:
        report = _safe_error_payload(
            "verification_input_invalid", phase=args.phase
        )
        exit_code = 2
    except Exception:
        report = _safe_error_payload(
            "verification_unavailable", phase=args.phase
        )
        exit_code = 2
    else:
        exit_code = 0 if bool(report.get("ok")) else 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
