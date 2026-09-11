"""Trusted, version-bound spending contexts derived from stored learning data."""
from __future__ import annotations

import hashlib
import json
from typing import Mapping

from core.errors import ApiError


def scope_digest(scope: Mapping[str, object]) -> str:
    return hashlib.sha256(json.dumps(dict(scope), ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def upgraded_manifest(manifest: Mapping[str, object]) -> bool:
    generation = manifest.get("generationContract")
    policy = generation.get("professionalCreationPolicy") if isinstance(generation, Mapping) else None
    return isinstance(policy, Mapping) and "interactionDesignPolicy" in policy


def teaching_budget_scope(row: Mapping[str, object], manifest: Mapping[str, object], purpose: str) -> dict[str, object]:
    generation = manifest["generationContract"]
    course = generation["teachingBrief"]["course"]
    return {"purpose": purpose, "gradeCode": course["gradeCode"], "subject": course["subject"],
            "courseId": row["course_id"], "courseVersion": row["course_version"],
            "userId": row["child_id"], "sessionId": row["learning_session_id"],
            "productionJobId": None, "approvalReference": generation["targetFingerprint"]}


def teaching_budget_bindings(service, row: Mapping[str, object], manifest: Mapping[str, object], *, admit: bool):
    if not upgraded_manifest(manifest):
        return None
    evidence = manifest.get("formalEvidence")
    required = isinstance(evidence, Mapping) and int(evidence.get("discussionActionCount") or 0) > 0
    bindings = {"required_teaching": None, "optional_interaction": None}
    for purpose in bindings:
        if purpose == "required_teaching" and not required:
            continue
        scope = teaching_budget_scope(row, manifest, purpose)
        identity = scope_digest(scope)
        try:
            binding = None
            if service is not None:
                renewable = purpose == "required_teaching" and service.policy.renew_teaching_authorizations
                if renewable and (row.get("learning_session_status") != "in_progress"
                                  or row.get("learning_session_completed_at") is not None):
                    raise ApiError("learning_budget_learning_session_inactive", "学习会话已结束，请从课程列表重新进入。", 409)
                if admit:
                    binding = service.issue_course_authorization(authorization_id=identity, scope=scope)
                else:
                    try:
                        context = service.authorization_context(authorization_id=identity)
                    except ApiError as exc:
                        if not renewable or exc.code != "learning_budget_authorization_expired":
                            raise
                        service.issue_course_authorization(authorization_id=identity, scope=scope,
                                                           existing_only=True)
                        context = service.authorization_context(authorization_id=identity)
                    if context["purpose"] == purpose:
                        binding = {"schemaVersion": "mira.learning.paid-budget-binding.v1",
                                   "authorizationId": identity, "required": True}
            bindings[purpose] = binding
        except ApiError:
            # An unavailable optional round cannot discard an existing lesson.
            if admit and purpose == "required_teaching":
                raise
        if admit and purpose == "required_teaching" and bindings[purpose] is None:
            raise ApiError("learning_required_teaching_unavailable", "本课必要的实时指导暂不可用，学习进度已保留，请稍后继续。", 503)
    return bindings
