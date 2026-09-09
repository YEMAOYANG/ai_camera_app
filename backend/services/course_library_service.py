from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Mapping

from core.database import Database
from core.security import now_ms
from repositories.learning_curriculum_preparation_repository import LearningCurriculumPreparationRepository
from repositories.formal_student_runtime_gate import current_formal_runtime_sql, current_formal_validation_authority_sql
from services.learning_curriculum_preparation_contract import (
    build_preparation_target, preparation_target_fingerprint,
)


POLICY_PATH = Path(__file__).resolve().parents[1] / 'content/course_supply_policy.json'


def supply_targets(target: Mapping, policy: Mapping, scope: str) -> list[dict]:
    """Use curriculum order, never a total-course-count proxy for coverage."""
    if scope not in {'canary', 'first_unit', 'catalog'}:
        raise ValueError('unsupported course supply scope')
    canaries = {(t['subject'], t['skillId'], t['variantOrdinal'])
                for t in target['canaryManifest']['targets']}
    selected = []
    for item in target['courseTargets']:
        key = (item['subject'], item['skillId'], item['variantOrdinal'])
        is_canary = key in canaries
        in_unit = (
            item['boundaryOrdinal'] <= policy['firstUnitBoundaryCountPerSubject']
            and item['variantOrdinal'] <= policy['coreVariantsPerBoundary'] + policy['reviewVariantsPerBoundary']
        )
        if not (is_canary or scope == 'catalog' or scope == 'first_unit' and in_unit):
            continue
        purpose = 'canary' if is_canary else ('core' if item['variantOrdinal'] == 1 else 'review')
        selected.append({**item, 'purpose': purpose,
                         'priority': (0 if is_canary else 100 * item['boundaryOrdinal'] + 10 * item['variantOrdinal'])})
    return sorted(selected, key=lambda t: (t['priority'], t['subjectOrdinal']))


def prioritize_demand(desired, mastery_rows, *, forward_boundaries):
    """Match the student's first-unmastered rule within the opened scope."""
    prioritized = [dict(item) for item in desired]
    profiles = {}
    for row in mastery_rows:
        profiles.setdefault((row['child_id'], row['subject']), {})[row['node_code']] = row['mastery_level']
    for (_, subject), mastery in profiles.items():
        progression = sorted({(r['boundaryOrdinal'], r['skillId']) for r in desired if r['subject'] == subject})
        next_index = next((i for i, (_, skill) in enumerate(progression) if mastery.get(skill) != 'mastered'), None)
        if next_index is None:
            continue
        for index, (_, skill) in enumerate(progression):
            if not next_index <= index <= next_index + forward_boundaries:
                continue
            for item in prioritized:
                if item['subject'] == subject and item['skillId'] == skill:
                    item['priority'] = min(item['priority'], 1 if index == next_index else 10)
    return prioritized


class CourseLibraryService:
    """The production owner and desired coverage; contains no Provider calls."""

    def __init__(self, database_url: str, *, preparation_repository=None, clock=now_ms):
        self.database = Database(database_url)
        self.preparations = preparation_repository or LearningCurriculumPreparationRepository(self.database)
        self.clock = clock
        self.policy = json.loads(POLICY_PATH.read_text())
        self.target = build_preparation_target(self.policy['gradeCode'])
        self.fingerprint = preparation_target_fingerprint(self.target)

    def ensure_owner(self) -> Mapping:
        timestamp = self.clock()
        with self.database.transaction() as conn:
            plan, _ = self.preparations.reserve_plan(
                conn, family_id=None, child_id=None, grade_code=self.target['gradeCode'],
                school_year_start_year=0, grade_selection_revision=0,
                target=self.target, target_fingerprint=self.fingerprint,
                request_id=f'library:{self.fingerprint}',
                shared_build_request_id=f'grade-build:{self.fingerprint}',
                now=timestamp, library_owned=True,
            )
            digest = hashlib.sha256(f'grade-build:{self.fingerprint}'.encode()).hexdigest()[:24]
            # Adopt persisted candidates/checkpoints without rewriting their
            # target or reopening a terminal build. Child plans remain followers.
            # Adoption is only needed before this owner is linked. Repeating
            # reconciliation on every operator tick resets next_run_at and can
            # indefinitely postpone an otherwise eligible production task.
            if not plan.get('catalog_build_id') and self.preparations.content_proof_auditor is not None:
                self.preparations.reconcile_shared_build(
                    conn, build_id=f'catalog_build_{digest}',
                    target_fingerprint=self.fingerprint, now=timestamp,
                )
            return dict(self.preparations.get_plan(conn, str(plan['id'])) or plan)

    def request_scope(self, scope: str) -> dict:
        desired = supply_targets(self.target, self.policy, scope)
        plan = self.ensure_owner()
        timestamp = self.clock()
        with self.database.transaction() as conn:
            mastery = conn.execute(
                """SELECT mastery.child_id, mastery.subject, mastery.node_code, mastery.mastery_level
                FROM learning_mastery_states AS mastery
                JOIN children AS child ON child.id = mastery.child_id AND child.family_id = mastery.family_id
                WHERE child.grade_code = ? AND mastery.grade_code = child.grade_code
                  AND mastery.updated_at >= ?""",
                (self.target['gradeCode'], timestamp - 30 * 86400000),
            ).fetchall()
            desired = prioritize_demand(desired, mastery, forward_boundaries=self.policy['forwardBoundaryCount'])
            # A scope is an explicit production ceiling. Keep disabled requests
            # for audit, but never let an older, wider scope silently expand it.
            conn.execute('UPDATE learning_course_supply_requests SET enabled = FALSE WHERE target_fingerprint = ?', (self.fingerprint,))
            for item in desired:
                conn.execute(
                    """INSERT INTO learning_course_supply_requests(
                      target_fingerprint, subject, skill_id, variant_ordinal,
                      priority, purpose, enabled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, TRUE, ?, ?)
                    ON DUPLICATE KEY UPDATE priority = VALUES(priority),
                      enabled = TRUE, updated_at = VALUES(updated_at)""",
                    (self.fingerprint, item['subject'], item['skillId'], item['variantOrdinal'],
                     item['priority'], item['purpose'], timestamp, timestamp),
                )
        return {'planId': plan['id'], 'scope': scope, 'requestedCount': len(desired),
                'targetFingerprint': self.fingerprint}

    def status(self) -> dict:
        timestamp = self.clock()
        with self.database.transaction() as conn:
            plan = conn.execute(
                'SELECT * FROM learning_curriculum_preparation_plans WHERE library_target_fingerprint = ?',
                (self.fingerprint,),
            ).fetchone()
            rows = conn.execute(
                f"""SELECT request.subject, request.skill_id, request.variant_ordinal,
                  request.priority, request.purpose, item.id AS build_item_id,
                  item.status AS content_status,
                  COALESCE(runtime.status, production_runtime.status) AS runtime_status,
                  production_runtime.created_at AS runtime_started_at,
                  production_runtime.ready_at AS runtime_ready_at,
                  item.content_gate_passed_at AS content_completed_at,
                  CASE WHEN receipt.classroom_status = 'passed' THEN receipt.classroom_completed_at END AS classroom_completed_at,
                  CASE WHEN receipt.tts_status = 'passed' THEN receipt.tts_completed_at END AS tts_completed_at,
                  CASE WHEN receipt.asr_roundtrip_status = 'passed' THEN receipt.asr_roundtrip_completed_at END AS asr_completed_at,
                  CASE WHEN receipt.auto_validated = 1 THEN receipt.auto_validated_at END AS validated_at,
                  receipt.classroom_status, receipt.tts_status, receipt.asr_roundtrip_status,
                  receipt.publication_status,
                  receipt.course_id, receipt.course_version, receipt.published_at,
                  item.created_at AS queued_at,
                  COALESCE(incident.reason_code, CASE WHEN
                    (production_runtime.status = 'failed' OR production_runtime.quality_status = 'quarantined')
                    AND NOT EXISTS (
                      SELECT 1 FROM learning_course_supply_incidents AS resolved_failure
                      WHERE resolved_failure.build_item_id = item.id
                        AND resolved_failure.failure_runtime_id = production_runtime.id
                        AND resolved_failure.resolved_at IS NOT NULL
                    ) THEN COALESCE(production_runtime.error_code, 'classroom_failed') END) AS reason_code,
                  incident.stage AS blocked_stage, incident.blocked_at,
                  CASE WHEN receipt.publication_status = 'published'
                    AND receipt.classroom_status = 'passed' AND receipt.tts_status = 'passed'
                    AND receipt.asr_roundtrip_status = 'passed' AND receipt.auto_validated = 1
                    AND runtime.status = 'ready' AND runtime.retired_at IS NULL
                    AND course.status = 'published' AND course.quality_status = 'released' AND course.retired_at IS NULL
                    AND runtime.candidate_build_item_id = item.id AND runtime.candidate_target_fingerprint = request.target_fingerprint
                    AND receipt.publication_receipt_hash REGEXP '^[0-9a-f]{{64}}$'
                    {current_formal_runtime_sql(runtime_alias='runtime')}
                    {current_formal_validation_authority_sql(receipt_alias='receipt', provider_alias='provider')}
                    THEN TRUE ELSE FALSE END AS ready
                FROM learning_course_supply_requests AS request
                JOIN learning_curriculum_preparation_plans AS owner
                  ON owner.library_target_fingerprint = request.target_fingerprint
                LEFT JOIN learning_catalog_build_items AS item
                  ON item.build_job_id = owner.catalog_build_id
                  AND item.subject = request.subject AND item.skill_id = request.skill_id
                  AND item.variant_ordinal = request.variant_ordinal
                LEFT JOIN learning_curriculum_classroom_item_receipts AS receipt
                  ON receipt.build_item_id = item.id AND receipt.target_fingerprint = request.target_fingerprint
                LEFT JOIN learning_openmaic_runtime_classrooms AS runtime ON runtime.id = receipt.runtime_classroom_id
                LEFT JOIN learning_openmaic_runtime_classrooms AS production_runtime
                  ON production_runtime.id = (
                    SELECT latest.id FROM learning_openmaic_runtime_classrooms AS latest
                    WHERE latest.candidate_build_item_id = item.id
                      AND latest.candidate_target_fingerprint = request.target_fingerprint
                    ORDER BY latest.created_at DESC, latest.id DESC LIMIT 1
                  )
                LEFT JOIN learning_courses AS course ON course.id = receipt.course_id AND course.version = receipt.course_version
                LEFT JOIN learning_openmaic_provider_readiness_jobs AS provider
                  ON provider.release_id = item.release_id AND provider.grade_code = item.grade_code
                  AND provider.target_fingerprint = request.target_fingerprint
                LEFT JOIN learning_course_supply_incidents AS incident
                  ON incident.build_item_id = item.id AND incident.resolved_at IS NULL
                WHERE request.target_fingerprint = ? AND request.enabled = TRUE
                ORDER BY request.priority, request.subject, request.skill_id, request.variant_ordinal""",
                (self.fingerprint,),
            ).fetchall()
            circuit = conn.execute("SELECT status, reason_code FROM learning_openmaic_provider_circuits WHERE circuit_key = 'formal-generation:deepseek:deepseek-v4-pro'").fetchone()
        actual = {**dict(plan or {})}
        # Dispatch and durable completion are real progress. A repeated poll,
        # lease heartbeat or coordinator reconciliation is only activity.
        milestone_fields = ('runtime_started_at', 'runtime_ready_at', 'content_completed_at',
                            'classroom_completed_at', 'tts_completed_at', 'asr_completed_at',
                            'validated_at', 'published_at')
        milestones = [actual.get('last_progress_at')]
        milestones.extend(row.get(field) for row in rows for field in milestone_fields)
        last_progress = max((value for value in milestones if value is not None), default=None)
        ready_count = sum(bool(r['ready']) for r in rows)
        missing_count = len(rows) - ready_count
        blocked = missing_count > 0 and (any(r['reason_code'] for r in rows) or (circuit or {}).get('status') == 'open')
        stalled = bool(missing_count > 0 and actual.get('status') == 'running' and last_progress and timestamp - last_progress >= self.policy['stalledAfterMs'])
        durations = sorted(r['published_at'] - r['queued_at'] for r in rows if r['ready'] and r['published_at'] and r['queued_at'])
        result = {
            'schemaVersion': 'learning.course-supply.v1', 'gradeCode': self.target['gradeCode'],
            'targetFingerprint': self.fingerprint, 'planId': actual.get('id'),
            'state': actual.get('status', 'not_started'), 'stage': actual.get('stage'),
            'lastProgressAt': last_progress, 'lastActivityAt': actual.get('updated_at'),
            'stalled': stalled, 'blocked': bool(blocked),
            'waitReason': (circuit or {}).get('reason_code') if (circuit or {}).get('status') == 'open' else ('course_review_required' if blocked else None),
            'requestedCount': len(rows), 'readyCount': sum(bool(r['ready']) for r in rows),
            'missingCount': sum(not r['ready'] for r in rows),
            'items': [dict(r) for r in rows],
            'coverage': [{ 'subject': subject,
                'requestedCount': sum(r['subject'] == subject for r in rows),
                'readyCount': sum(r['subject'] == subject and bool(r['ready']) for r in rows),
                'missingSkills': sorted({r['skill_id'] for r in rows if r['subject'] == subject and not r['ready']}),
            } for subject in ('chinese', 'math', 'english')],
            'queueToPublish': {'sampleCount': len(durations),
                'p50Ms': durations[(len(durations)-1)//2] if durations else None,
                'p95Ms': durations[max(0, (95*len(durations)+99)//100-1)] if len(durations) >= 20 else None},
        }

        version_fields = {key: result[key] for key in ('state', 'stage', 'lastProgressAt', 'blocked', 'stalled', 'waitReason', 'readyCount', 'items')}
        result['version'] = hashlib.sha256(json.dumps(version_fields, sort_keys=True, default=str).encode()).hexdigest()
        return result


_cache_lock = threading.Lock()
_status_cache = {}


def cached_supply_summary(database_url: str, *, grade_code: str) -> dict | None:
    if grade_code != 'primary_1':
        return None
    with _cache_lock:
        cached = _status_cache.get(database_url)
        if cached is None or cached[0] <= time.monotonic():
            status = CourseLibraryService(database_url).status()
            _status_cache.clear()
            _status_cache[database_url] = (time.monotonic() + 5, status)
        else:
            status = cached[1]
        if not status['planId']:
            return None
        # One rejected subject does not stop its healthy siblings. Preserve
        # the diagnostic `blocked` flag without telling both clients that all
        # production is paused while a remaining course can still advance.
        missing = [item for item in status.get('items', []) if not item.get('ready')]
        global_stop = status.get('waitReason') not in {None, 'course_review_required'}
        paused = bool(status['blocked'] and (global_stop or not missing or all(
            item.get('reason_code') and item.get('runtime_status') != 'generating'
            for item in missing
        )))
        delayed = status['stalled'] and not paused
        return {'schemaVersion': 'learning.course-supply-summary.v1', 'version': status['version'],
                'requestedCount': status['requestedCount'], 'readyCount': status['readyCount'],
                'paused': paused, 'delayed': delayed, 'lastProgressAt': status['lastProgressAt'],
                'retryAfterMs': 30000 if paused or delayed else 10000,
                'message': ('新课还需要一点调整，准备好会自动出现。' + ('可以先学习已有课程。' if status['readyCount'] else '不用一直等在这里。')) if paused else (('新课准备时间较长，进度暂未更新。' + ('已有课程可以继续学习。' if status['readyCount'] else '可以先休息一下，准备好会自动出现。')) if delayed else '每完成一节就能先学，新课准备好会自动出现。')}
