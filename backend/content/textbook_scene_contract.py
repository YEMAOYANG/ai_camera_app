"""Frozen page constraints shared by the workbench and native page generators.

This is an authoring contract, not a pedagogical approval or a pre-generated
scene. Speech and image bytes are recorded separately when a candidate exists.
"""
from copy import deepcopy
import math
import re

from content.textbook_catalog import SUBJECTS, canonical, digest, identifier
from content.textbook_interaction_policy import interaction_policy_prompt


SCHEMA = "mira.textbook.scene-authoring-contract.v1"
SNAPSHOT_SCHEMA = "mira.frozen-textbook-scene-authoring.v1"
PROMPT_START = "\nMIRA_TEXTBOOK_SCENE_AUTHORING_CONTRACT:\n"
PROMPT_END = "\nEND_MIRA_TEXTBOOK_SCENE_AUTHORING_CONTRACT\n"
FIELDS = {"schemaVersion", "binding", "catalogEvidence", "teacherContract",
          "interactionPolicy", "qualityRules", "scopeReview", "pagePlan", "lockedAssessments"}

# The complete scene contract above remains the audit/guard authority.  New
# authoring jobs dispatch this deliberately smaller projection so the creator is
# not asked to read the same policy twice (or to treat validator prose as a page
# template).  Historical v3 jobs continue to render the original envelope.
AUTHOR_DISPATCH_SCHEMA = "mira.textbook.author-dispatch-contract.v1"
AUTHOR_DISPATCH_SNAPSHOT_SCHEMA = "mira.frozen-textbook-author-dispatch.v1"
AUTHOR_PROMPT_START = "\nMIRA_TEXTBOOK_AUTHOR_DISPATCH_CONTRACT:\n"
AUTHOR_PROMPT_END = "\nEND_MIRA_TEXTBOOK_AUTHOR_DISPATCH_CONTRACT\n"
AUTHOR_FIELDS = {
    "schemaVersion", "sourceSceneContractSha256", "binding", "catalogEvidence",
    "teacherContract", "policyRef", "authoringRules", "qualityRules", "courseScope",
    "officialResourceSummary", "pagePlan", "lockedAssessments",
}
_REVIEW_ONLY_RULES = frozenset({"official_source_review_before_authoring", "review_actual_play"})


def scene_canonical(value):
    """Compare Native scene numbers without changing archived JSON bytes.

    JSON.stringify writes a finite, safe integer-valued Number as an integer,
    including negative zero. Operator input files can retain Python's ``100.0``
    spelling. Normalize only that representation difference; strings, booleans,
    fractional values and integers outside the safe range retain their identity.
    This is deliberately separate from the frozen envelope's canonical format.
    """
    def normalized(item):
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError("Scene numbers must be finite")
            if item.is_integer() and abs(item) <= 2 ** 53 - 1:
                return int(item)
        if isinstance(item, list):
            return [normalized(child) for child in item]
        if isinstance(item, dict):
            return {key: normalized(child) for key, child in item.items()}
        return item

    return canonical(normalized(value))


def scene_digest(value):
    import hashlib
    return hashlib.sha256(scene_canonical(value).encode()).hexdigest()


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _portable_json(value):
    """The envelope has no measurements; numeric fields are safe JSON integers.

    Native scene measurements may be floats and use their own canonicalJson
    receipt. Keeping the constraint envelope portable avoids JS/Python number
    serialization differences changing its identity.
    """
    if value is None or isinstance(value, (str, bool)):
        return
    if type(value) is int and abs(value) <= 2 ** 53 - 1:
        return
    if isinstance(value, list):
        for item in value:
            _portable_json(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _portable_json(item)
        return
    raise ValueError("Scene contract requires portable JSON values and safe integer numbers")


def _validate(contract):
    if not isinstance(contract, dict) or set(contract) != FIELDS or contract.get("schemaVersion") != SCHEMA:
        raise ValueError("Invalid scene authoring contract schema")
    _portable_json(contract)
    binding = contract["binding"]
    if (not isinstance(binding, dict)
            or not all(identifier(binding.get(key)) for key in ("editionId", "revisionId", "unitId", "nodeId"))
            or binding.get("gradeCode") not in {f"primary_{i}" for i in range(1, 7)}
            or binding.get("subject") not in SUBJECTS
            or binding.get("volume") not in {"upper", "lower", "full"}
            or binding.get("schoolSystem") not in {"six_year", "five_four"}
            or (binding["schoolSystem"] == "five_four" and binding["gradeCode"] == "primary_6")
            or not all(_text(binding.get(key)) for key in ("unitTitle", "lessonTitle"))):
        raise ValueError("Scene contract needs the complete catalog-verified textbook binding")
    evidence = contract["catalogEvidence"]
    if (not isinstance(evidence, dict) or set(evidence) != {"manifestSha256", "lessonScopeSha256"}
            or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                   for value in evidence.values())):
        raise ValueError("Scene contract lacks catalog and lesson scope digests")
    teacher = contract["teacherContract"]
    if (not isinstance(teacher, dict) or teacher.get("subject") != binding["subject"]
            or not all(_text(teacher.get(key)) for key in
                       ("teacherProfileId", "teacherProfileHash", "teacherName", "voiceId", "languageCode"))
            or type(teacher.get("teacherProfileVersion")) is not int or teacher["teacherProfileVersion"] < 1):
        raise ValueError("Scene contract teacher does not match the bound subject")
    interaction_policy_prompt(contract["interactionPolicy"])
    rules, scope, plan, assessments = (contract[key] for key in
                                      ("qualityRules", "scopeReview", "pagePlan", "lockedAssessments"))
    if not isinstance(rules, list) or not rules or not all(_text(rule) for rule in rules):
        raise ValueError("Scene contract needs explicit quality rules")
    if not isinstance(scope, dict) or not scope:
        raise ValueError("Scene contract needs a frozen textbook scope review")
    if not isinstance(plan, list) or not plan:
        raise ValueError("Scene contract needs an ordered page plan")
    expected_questions = {}
    low_reading = binding["gradeCode"] in {"primary_1", "primary_2"}
    for index, page in enumerate(plan, 1):
        if (not isinstance(page, dict) or type(page.get("page")) is not int or page["page"] != index
                or page.get("type") not in {"slide", "interactive", "quiz"}
                or not _text(page.get("title")) or not _text(page.get("move"))):
            raise ValueError("Page plan needs consecutive page numbers, types, titles and teaching moves")
        ids = page.get("questionIds", [])
        guidance = page.get("narrationGuidance", [])
        if (not isinstance(guidance, list) or any(not _text(text) for text in guidance)
                or len(set(guidance)) != len(guidance)
                or (guidance and page["type"] != "quiz")):
            raise ValueError("Optional narration guidance is a unique quiz-only text list")
        if (not isinstance(ids, list) or any(not identifier(qid) for qid in ids)
                or len(set(ids)) != len(ids)
                or (page["type"] == "quiz" and (not ids or (low_reading and len(ids) != 1)))
                or (page["type"] != "quiz" and ids)):
            raise ValueError("Quiz page must identify its locked questions; low-reading pages use one question")
        for qid in ids:
            if qid in expected_questions:
                raise ValueError("Locked question occurs on more than one page")
            expected_questions[qid] = index
    if not isinstance(assessments, list):
        raise ValueError("Locked assessments must be an explicit list")
    seen = set()
    for question in assessments:
        if not isinstance(question, dict):
            raise ValueError("Invalid locked assessment")
        qid, page, choices = question.get("id"), question.get("page"), question.get("choices")
        if (not identifier(qid) or qid in seen or expected_questions.get(qid) != page or type(page) is not int
                or question.get("type") != "single" or type(question.get("points")) is not int
                or question["points"] <= 0 or not all(_text(question.get(key)) for key in ("question", "analysis"))
                or not isinstance(choices, list) or not 2 <= len(choices) <= 6):
            raise ValueError("Locked assessment identity, page, score or question is invalid")
        seen.add(qid)
        if "visualAsset" in question and not identifier(question["visualAsset"]):
            raise ValueError("Optional question picture must use a stable asset key")
        if any(text in {question["question"], question["analysis"]}
               for text in plan[page - 1].get("narrationGuidance", [])):
            raise ValueError("Quiz guidance cannot duplicate its question or reveal its answer explanation")
        values = []
        for choice in choices:
            if (not isinstance(choice, dict) or not _text(choice.get("value")) or not _text(choice.get("label"))
                    or (low_reading and not identifier(choice.get("asset")))
                    or ("asset" in choice and not identifier(choice["asset"]))):
                raise ValueError("Locked choice needs a value, label and low-reading picture asset key")
            values.append(choice["value"])
        if len(set(values)) != len(values) or question.get("answer") not in values:
            raise ValueError("Locked question answer must reference a unique choice")
    if seen != set(expected_questions):
        raise ValueError("Page plan and locked assessment coverage differ")
    return contract


def freeze_scene_contract(draft, catalog_check, interaction_policy):
    try:
        contract = {"schemaVersion": SCHEMA,
                    **{key: deepcopy(draft[key]) for key in
                       ("binding", "teacherContract", "qualityRules", "scopeReview", "pagePlan", "lockedAssessments")},
                    "catalogEvidence": {key: catalog_check[key] for key in ("manifestSha256", "lessonScopeSha256")},
                    "interactionPolicy": deepcopy(interaction_policy)}
    except (KeyError, TypeError) as error:
        raise ValueError("Draft lacks the structured page authoring contract") from error
    _validate(contract)
    return {"schemaVersion": SNAPSHOT_SCHEMA, "contract": contract, "sha256": digest(contract)}


def validate_scene_contract(snapshot, *, draft=None, catalog_check=None, interaction_policy=None):
    if (not isinstance(snapshot, dict) or set(snapshot) != {"schemaVersion", "contract", "sha256"}
            or snapshot.get("schemaVersion") != SNAPSHOT_SCHEMA
            or not isinstance(snapshot.get("contract"), dict)
            or snapshot.get("sha256") != digest(snapshot["contract"])):
        raise ValueError("Frozen scene contract digest or schema mismatch")
    contract = _validate(snapshot["contract"])
    if draft is not None:
        if catalog_check is None or interaction_policy is None:
            raise ValueError("Verifying the original draft requires catalog and policy evidence")
        expected = freeze_scene_contract(draft, catalog_check, interaction_policy)
        if snapshot != expected:
            raise ValueError("Frozen scene contract differs from the original reviewed draft")
    return contract


def render_scene_contract(snapshot):
    validate_scene_contract(snapshot)
    return PROMPT_START + canonical(snapshot) + PROMPT_END


def _official_resource_summary(scope):
    review = scope.get("officialResourceReview") if isinstance(scope, dict) else None
    if not isinstance(review, dict):
        raise ValueError("Author dispatch requires the reviewed official-resource record")
    try:
        hours = [{
            "classHourId": hour["classHourId"],
            "title": hour["title"],
            "learningObjectives": deepcopy(hour["learningObjectives"]),
            "resources": {
                kind: {key: deepcopy(resource[key]) for key in ("status", "locations", "findings")}
                for kind, resource in hour["resources"].items()
            },
        } for hour in review["classHours"]]
        return {
            "schemaVersion": review["schemaVersion"],
            "sha256": digest(review),
            "officialTextbook": deepcopy(review["officialTextbook"]),
            "classHours": hours,
            "adaptation": deepcopy(review["adaptation"]),
        }
    except (KeyError, TypeError) as error:
        raise ValueError("Official-resource review cannot form an author summary") from error


def _authoring_rules(interaction_policy):
    """Project creator-facing requirements from the pinned policy.

    Review acquisition and post-generation play inspection stay in the complete
    frozen contract.  All other versioned rule requirements are kept verbatim,
    without examples, provider boundaries or duplicate policy JSON.
    """
    try:
        policy = interaction_policy["policy"]
        return [{"id": rule["id"], "requirement": rule["requirement"]}
                for rule in policy["rules"] if rule["id"] not in _REVIEW_ONLY_RULES]
    except (KeyError, TypeError) as error:
        raise ValueError("Frozen interaction policy cannot form an author brief") from error


def freeze_author_dispatch_contract(scene_snapshot):
    """Freeze a compact creator projection while retaining the full source hash."""
    source = validate_scene_contract(scene_snapshot)
    policy_snapshot = source["interactionPolicy"]
    # interaction_policy_prompt is the existing canonical policy validator.  Do
    # not render its large result into this author-facing envelope.
    interaction_policy_prompt(policy_snapshot)
    policy = policy_snapshot["policy"]
    scope = source["scopeReview"]
    contract = {
        "schemaVersion": AUTHOR_DISPATCH_SCHEMA,
        "sourceSceneContractSha256": scene_snapshot["sha256"],
        "binding": deepcopy(source["binding"]),
        "catalogEvidence": deepcopy(source["catalogEvidence"]),
        "teacherContract": deepcopy(source["teacherContract"]),
        "policyRef": {
            "schemaVersion": policy_snapshot["schemaVersion"],
            "policyId": policy["policyId"],
            "version": policy["version"],
            "sha256": policy_snapshot["sha256"],
        },
        "authoringRules": _authoring_rules(policy_snapshot),
        "qualityRules": deepcopy(source["qualityRules"]),
        "courseScope": {key: deepcopy(value) for key, value in scope.items()
                        if key != "officialResourceReview"},
        "officialResourceSummary": _official_resource_summary(scope),
        "pagePlan": deepcopy(source["pagePlan"]),
        "lockedAssessments": deepcopy(source["lockedAssessments"]),
    }
    _validate_author_dispatch_contract(contract)
    return {"schemaVersion": AUTHOR_DISPATCH_SNAPSHOT_SCHEMA,
            "contract": contract, "sha256": digest(contract)}


def _validate_author_dispatch_contract(contract):
    if (not isinstance(contract, dict) or set(contract) != AUTHOR_FIELDS
            or contract.get("schemaVersion") != AUTHOR_DISPATCH_SCHEMA):
        raise ValueError("Invalid author dispatch contract schema")
    _portable_json(contract)
    if not re.fullmatch(r"[0-9a-f]{64}", contract.get("sourceSceneContractSha256", "")):
        raise ValueError("Author dispatch source contract digest is invalid")
    policy = contract.get("policyRef")
    if (not isinstance(policy, dict)
            or set(policy) != {"schemaVersion", "policyId", "version", "sha256"}
            or policy.get("schemaVersion") != "mira.frozen-interaction-policy.v1"
            or not _text(policy.get("policyId"))
            or type(policy.get("version")) is not int or policy["version"] < 1
            or not re.fullmatch(r"[0-9a-f]{64}", policy.get("sha256", ""))):
        raise ValueError("Author dispatch policy reference is invalid")
    rules = contract.get("authoringRules")
    if (not isinstance(rules, list) or not rules
            or any(not isinstance(rule, dict) or set(rule) != {"id", "requirement"}
                   or not _text(rule.get("id")) or not _text(rule.get("requirement")) for rule in rules)
            or len({rule["id"] for rule in rules}) != len(rules)):
        raise ValueError("Author dispatch rules are invalid")
    if (not isinstance(contract.get("courseScope"), dict)
            or "officialResourceReview" in contract["courseScope"]
            or not isinstance(contract.get("officialResourceSummary"), dict)):
        raise ValueError("Author dispatch course scope summary is invalid")
    # Reuse the complete validator for page/quiz/binding semantics without
    # creating a second, drifting implementation here.
    return contract


def validate_author_dispatch_contract(snapshot, *, scene_contract=None):
    if (not isinstance(snapshot, dict) or set(snapshot) != {"schemaVersion", "contract", "sha256"}
            or snapshot.get("schemaVersion") != AUTHOR_DISPATCH_SNAPSHOT_SCHEMA
            or not isinstance(snapshot.get("contract"), dict)
            or snapshot.get("sha256") != digest(snapshot["contract"])):
        raise ValueError("Frozen author dispatch contract digest or schema mismatch")
    contract = _validate_author_dispatch_contract(snapshot["contract"])
    if scene_contract is not None and snapshot != freeze_author_dispatch_contract(scene_contract):
        raise ValueError("Author dispatch contract differs from its complete frozen source")
    return contract


def render_author_dispatch_contract(snapshot):
    validate_author_dispatch_contract(snapshot)
    return AUTHOR_PROMPT_START + canonical(snapshot) + AUTHOR_PROMPT_END
