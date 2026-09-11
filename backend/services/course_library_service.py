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
from repositories.course_supply_inventory import inherited_scope_requests, published_supply
from services.learning_curriculum_preparation_contract import (
    TARGET_SCHEMA_V2, build_preparation_target, preparation_target_fingerprint,
)


POLICY_PATH = Path(__file__).resolve().parents[1] / 'content/course_supply_policy.json'


class CourseLibraryNotOpen(ValueError):
    """The requested grade has no approved formal production target yet."""


def formal_supply_target(grade_code: str) -> dict:
    if not isinstance(grade_code, str) or not grade_code:
        raise CourseLibraryNotOpen('course library grade is not open')
    try:
        target = build_preparation_target(grade_code)
    except (KeyError, ValueError) as exc:
        raise CourseLibraryNotOpen('course library grade is not open') from exc
    if (target.get('gradeCode') != grade_code
            or target.get('schemaVersion') != TARGET_SCHEMA_V2
            or not target.get('courseTargets')
            or not isinstance(target.get('canaryManifest'), Mapping)):
        raise CourseLibraryNotOpen('course library grade has no formal target')
    return target


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

    def __init__(self, database_url: str, *, grade_code: str = 'primary_1',
                 preparation_repository=None, clock=now_ms):
        # Existing single-grade operator entry points retain their explicit
        # primary-one default. A supplied grade never falls back to that grade.
        self.target = formal_supply_target(grade_code)
        self.fingerprint = preparation_target_fingerprint(self.target)
        self.database = Database(database_url)
        self.preparations = preparation_repository or LearningCurriculumPreparationRepository(self.database)
        self.clock = clock
        self.policy = json.loads(POLICY_PATH.read_text())
        self.policy = {**self.policy, 'gradeCode': grade_code}

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

    def request_slot(self, *, subject: str, skill_id: str, variant_ordinal: int) -> dict:
        """Explicit operator ceiling: exactly one existing curriculum slot, no paid work."""
        if type(variant_ordinal) is not int:
            raise ValueError('variant ordinal must be an integer')
        matches = [item for item in self.target['courseTargets'] if item['subject'] == subject
                   and item['skillId'] == skill_id and item['variantOrdinal'] == variant_ordinal]
        if len(matches) != 1:
            raise ValueError('single course slot is absent from the current frozen curriculum')
        plan = self.ensure_owner()
        timestamp = self.clock()
        with self.database.transaction() as conn:
            locked = conn.execute('SELECT id FROM learning_curriculum_preparation_plans '
                'WHERE id = ? AND library_target_fingerprint = ? AND grade_code = ? FOR UPDATE',
                (plan['id'], self.fingerprint, self.target['gradeCode'])).fetchone()
            if locked is None:
                raise RuntimeError('course library ownership changed')
            conn.execute('UPDATE learning_course_supply_requests SET enabled = FALSE WHERE target_fingerprint = ?', (self.fingerprint,))
            conn.execute("""INSERT INTO learning_course_supply_requests(
                target_fingerprint, subject, skill_id, variant_ordinal, priority, purpose, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, 'core', TRUE, ?, ?)
                ON DUPLICATE KEY UPDATE priority=0, enabled=TRUE, updated_at=VALUES(updated_at)""",
                (self.fingerprint, subject, skill_id, variant_ordinal, timestamp, timestamp))
        invalidate_supply_cache(str(self.database.database_url), self.target['gradeCode'])
        return {'planId': plan['id'], 'scope': 'single_slot', 'gradeCode': self.target['gradeCode'],
                'targetFingerprint': self.fingerprint, 'requestedCount': 1,
                'slot': {'subject': subject, 'skillId': skill_id, 'variantOrdinal': variant_ordinal}}

    def request_scope(self, scope: str, *, preserve_existing_scope: bool = False) -> dict:
        desired = supply_targets(self.target, self.policy, scope)
        plan = self.ensure_owner()
        timestamp = self.clock()
        with self.database.transaction() as conn:
            # Serialize replacing the requested set for this exact owner. The
            # primary key deduplicates slots; the owner lock prevents two scope
            # updates from leaving the union of a narrow and a wider request.
            locked = conn.execute(
                'SELECT id FROM learning_curriculum_preparation_plans '
                'WHERE id = ? AND library_target_fingerprint = ? AND grade_code = ? FOR UPDATE',
                (plan['id'], self.fingerprint, self.target['gradeCode']),
            ).fetchone()
            if locked is None:
                raise RuntimeError('course library ownership changed')
            if preserve_existing_scope:
                existing = conn.execute(
                    'SELECT subject, skill_id, variant_ordinal, enabled '
                    'FROM learning_course_supply_requests WHERE target_fingerprint = ?',
                    (self.fingerprint,),
                ).fetchall()
                if not existing:
                    from repositories.course_supply_inventory import inherited_scope_request_state
                    inherited = inherited_scope_request_state(conn, self.target)
                    if inherited is not None:
                        # A policy fingerprint upgrade inherits the latest
                        # explicit ceiling; it is not a new spending approval.
                        existing = [{**row, 'enabled': True} for row in inherited]
                        if not inherited:
                            desired = []
                if existing:
                    # Automatic maintenance must never reactivate disabled
                    # requests or overwrite an explicitly narrowed scope.
                    enabled = {(row['subject'], row['skill_id'], int(row['variant_ordinal']))
                               for row in existing if row['enabled']}
                    desired = [item for item in supply_targets(self.target, self.policy, 'catalog')
                               if (item['subject'], item['skillId'], item['variantOrdinal']) in enabled]
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
        invalidate_supply_cache(str(self.database.database_url), self.target['gradeCode'])
        return {'planId': plan['id'], 'scope': scope, 'gradeCode': self.target['gradeCode'],
                'requestedCount': len(desired),
                'targetFingerprint': self.fingerprint}

    def status(self) -> dict:
        timestamp = self.clock()
        with self.database.transaction() as conn:
            plan = conn.execute(
                'SELECT * FROM learning_curriculum_preparation_plans WHERE library_target_fingerprint = ? AND grade_code = ?',
                (self.fingerprint, self.target['gradeCode']),
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
                  FALSE AS ready
                FROM learning_course_supply_requests AS request
                JOIN learning_curriculum_preparation_plans AS owner
                  ON owner.library_target_fingerprint = request.target_fingerprint
                LEFT JOIN learning_catalog_build_items AS item
                  ON item.build_job_id = owner.catalog_build_id
                  AND item.grade_code = owner.grade_code
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
                LEFT JOIN learning_course_supply_incidents AS incident
                  ON incident.build_item_id = item.id AND incident.resolved_at IS NULL
                WHERE request.target_fingerprint = ? AND owner.grade_code = ? AND request.enabled = TRUE
                ORDER BY request.priority, request.subject, request.skill_id, request.variant_ordinal""",
                (self.fingerprint, self.target['gradeCode']),
            ).fetchall()
            # Only inherit before a new owner has any explicit scope. An
            # existing owner's deliberately empty/narrow scope is authoritative.
            if not rows and plan is None:
                rows = inherited_scope_requests(conn, self.target)
            inventory = published_supply(conn, self.target)
            circuit = conn.execute("SELECT status, reason_code FROM learning_openmaic_provider_circuits WHERE circuit_key = 'formal-generation:deepseek:deepseek-v4-pro'").fetchone()
        rows = apply_published_inventory(rows, inventory, self.fingerprint)
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
        scope_ready = bool(rows) and missing_count == 0
        terminal = actual.get('status') in {'failed', 'superseded'}
        blocked = missing_count > 0 and (terminal or any(r['reason_code'] for r in rows if not r['ready']) or (circuit or {}).get('status') == 'open')
        stalled = bool(missing_count > 0 and actual.get('status') == 'running' and last_progress and timestamp - last_progress >= self.policy['stalledAfterMs'])
        durations = sorted(r['published_at'] - r['queued_at'] for r in rows
                           if r['ready'] and not r.get('reused') and r.get('published_at')
                           and r.get('queued_at') and r['published_at'] >= r['queued_at'])
        result = {
            'schemaVersion': 'learning.course-supply.v1', 'gradeCode': self.target['gradeCode'],
            'targetFingerprint': self.fingerprint, 'planId': actual.get('id'),
            'inheritedScope': bool(rows and rows[0].get('source_plan_id')),
            'state': 'ready' if scope_ready else actual.get('status', 'not_started'),
            'stage': 'completed' if scope_ready else actual.get('stage'),
            'productionState': actual.get('status', 'not_started'),
            'productionStage': actual.get('stage'), 'scopeReady': scope_ready,
            'lastProgressAt': last_progress, 'lastActivityAt': actual.get('updated_at'),
            'stalled': stalled, 'blocked': bool(blocked),
            'waitReason': ((circuit or {}).get('reason_code') if (circuit or {}).get('status') == 'open' else ('course_preparation_stopped' if terminal else ('course_review_required' if blocked else None))) if missing_count else None,
            'requestedCount': len(rows), 'readyCount': sum(bool(r['ready']) for r in rows),
            'missingCount': sum(not r['ready'] for r in rows),
            'scopeSkills': [{'subject': subject, 'skillId': skill}
                            for subject, skill in sorted({(r['subject'], r['skill_id']) for r in rows})],
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
        result['availabilityStatus'] = supply_availability_status(result)
        version_fields = {key: result[key] for key in ('gradeCode', 'targetFingerprint', 'availabilityStatus', 'scopeReady', 'state', 'stage', 'lastProgressAt', 'blocked', 'stalled', 'waitReason', 'readyCount', 'items')}
        result['version'] = hashlib.sha256(json.dumps(version_fields, sort_keys=True, default=str).encode()).hexdigest()
        return result


_cache_lock = threading.Lock()
_status_cache = {}


def invalidate_supply_cache(database_url: str, grade_code: str) -> None:
    with _cache_lock:
        for key in list(_status_cache):
            if key[:2] == (database_url, grade_code):
                del _status_cache[key]


def apply_published_inventory(rows, inventory, fingerprint: str) -> list[dict]:
    """Attach playable evidence without changing a target or production row."""
    result = []
    for row in rows:
        item = {**dict(row), 'ready': False}
        available = inventory.get((item['subject'], item['skill_id'], int(item['variant_ordinal'])))
        if available:
            item.update(ready=True, course_id=available['course_id'],
                        course_version=available['course_version'],
                        published_at=available['published_at'], runtime_status='ready',
                        source_build_item_id=available['build_item_id'],
                        source_target_fingerprint=available['target_fingerprint'],
                        reused=available['target_fingerprint'] != fingerprint,
                        reason_code=None, blocked_stage=None, blocked_at=None)
        elif item.get('publication_status') == 'published':
            item.update(reason_code='published_course_unavailable', blocked_stage='availability')
        result.append(item)
    return result


def supply_is_paused(status: Mapping) -> bool:
    if status.get('scopeReady') or status.get('requestedCount', 0) == 0:
        return False
    missing = [item for item in status.get('items', []) if not item.get('ready')]
    global_stop = status.get('waitReason') not in {None, 'course_review_required'}
    return bool(status.get('blocked') and (global_stop or not missing or all(
        item.get('reason_code') and item.get('runtime_status') != 'generating'
        for item in missing
    )))


def supply_availability_status(status: Mapping) -> str:
    # A shared library cannot decide whether a particular child has completed
    # the opened scope. The learning service adds that personal status.
    if status.get('readyCount', 0) > 0:
        return 'ready'
    if not status.get('requestedCount'):
        return 'empty'
    if supply_is_paused(status):
        return 'paused'
    return 'preparing'


def cached_supply_summary(database_url: str, *, grade_code: str) -> dict | None:
    try:
        library = CourseLibraryService(database_url, grade_code=grade_code)
    except CourseLibraryNotOpen:
        version = hashlib.sha256(f'not_open:{grade_code}'.encode()).hexdigest()
        return {'schemaVersion': 'learning.course-supply-summary.v1', 'version': version,
                'gradeCode': grade_code, 'targetFingerprint': None, 'availabilityStatus': 'not_open',
                'scopeReady': False, 'requestedCount': 0, 'readyCount': 0, 'missingCount': 0,
                'scopeSkills': [],
                'paused': False, 'delayed': False, 'lastProgressAt': None,
                'retryAfterMs': 30000, 'message': '这个年级的课程还没有开放。'}
    key = (database_url, grade_code, library.fingerprint)
    with _cache_lock:
        cached = _status_cache.get(key)
        if cached is None or cached[0] <= time.monotonic():
            status = library.status()
            _status_cache[key] = (time.monotonic() + 5, status)
        else:
            status = cached[1]
        # Registered grades are accessible even without produced courses.
        # Empty inventory never means that the grade itself is closed.
        # One rejected subject does not stop its healthy siblings. Preserve
        # the diagnostic `blocked` flag without telling both clients that all
        # production is paused while a remaining course can still advance.
        scope_ready = status.get('scopeReady', status['requestedCount'] > 0 and status['readyCount'] == status['requestedCount'])
        paused = supply_is_paused({**status, 'scopeReady': scope_ready})
        delayed = status['stalled'] and not paused and not scope_ready
        return {'schemaVersion': 'learning.course-supply-summary.v1', 'version': status['version'],
                'gradeCode': grade_code, 'targetFingerprint': library.fingerprint,
                'availabilityStatus': supply_availability_status(status), 'scopeReady': scope_ready,
                'requestedCount': status['requestedCount'], 'readyCount': status['readyCount'],
                'missingCount': status['requestedCount'] - status['readyCount'],
                'scopeSkills': status.get('scopeSkills', []),
                'paused': paused, 'delayed': delayed, 'lastProgressAt': status['lastProgressAt'],
                'retryAfterMs': 30000 if paused or delayed else 10000,
                'message': '这里还没有课程，课程准备好后就会出现。' if not status['requestedCount'] else ('已开放的课程都准备好了，可以开始学习。' if scope_ready else (('新课还需要一点调整，准备好会自动出现。' + ('可以先学习已有课程。' if status['readyCount'] else '不用一直等在这里。')) if paused else (('新课准备时间较长，进度暂未更新。' + ('已有课程可以继续学习。' if status['readyCount'] else '可以先休息一下，准备好会自动出现。')) if delayed else '每完成一节就能先学，新课准备好会自动出现。')))}
