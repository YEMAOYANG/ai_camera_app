"""Versioned authoring guidance; no claim of automated pedagogical acceptance.

Freeze the whole policy at preparation. Dispatch/recovery must read that snapshot,
not today's policy file, so an update never changes an existing request identity.
"""
from copy import deepcopy
import json
from pathlib import Path

from content.textbook_catalog import digest


POLICY_PATH = Path(__file__).with_name("textbook_interaction_policy.v1.json")
POLICY_SCHEMA = "mira.textbook.interaction-policy.v1"
SNAPSHOT_SCHEMA = "mira.frozen-interaction-policy.v1"


def _validate_policy(policy):
    if (not isinstance(policy, dict) or policy.get("schemaVersion") != POLICY_SCHEMA
            or not isinstance(policy.get("policyId"), str) or not policy["policyId"].strip()
            or type(policy.get("version")) is not int or policy["version"] < 1
            or not isinstance(policy.get("precedence"), list) or not policy["precedence"]
            or any(not isinstance(rule, str) or not rule.strip() for rule in policy["precedence"])
            or not isinstance(policy.get("activityContract"), dict)
            or not isinstance(policy["activityContract"].get("requiredFields"), dict)
            or not policy["activityContract"]["requiredFields"]
            or not isinstance(policy.get("executionBoundary"), dict)
            or not isinstance(policy.get("rules"), list) or not policy["rules"]):
        raise ValueError("Invalid frozen interaction policy structure")
    ids = set()
    for rule in policy["rules"]:
        if (not isinstance(rule, dict) or not isinstance(rule.get("id"), str)
                or not rule["id"].strip() or rule["id"] in ids
                or not isinstance(rule.get("requirement"), str) or not rule["requirement"].strip()):
            raise ValueError("Invalid or duplicate interaction policy rule")
        ids.add(rule["id"])
    return policy


def freeze_interaction_policy():
    policy = _validate_policy(json.loads(POLICY_PATH.read_text(encoding="utf-8")))
    return {"schemaVersion": SNAPSHOT_SCHEMA, "policy": deepcopy(policy), "sha256": digest(policy)}


def interaction_policy_prompt(snapshot):
    """Validate and render only the pinned bytes, independent of the live registry."""
    if (not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != SNAPSHOT_SCHEMA
            or not isinstance(snapshot.get("policy"), dict)
            or snapshot.get("sha256") != digest(snapshot["policy"])):
        raise ValueError("Frozen interaction policy digest or schema mismatch")
    policy = _validate_policy(snapshot["policy"])
    return (
        "【已冻结的互动教学与游戏规则】\n"
        "以下是本次任务的权威互动设计规则，按 precedence 处理旧技能/草稿的冲突要求。"
        "保留原请求的教材、目标、教师、锁定测评、音频与安全合同；不将规则注入当作课程验收通过。\n"
        f"policyId={policy['policyId']}; version={policy['version']}; sha256={snapshot['sha256']}\n"
        + json.dumps(policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n【原始已审课程请求】\n"
    )
