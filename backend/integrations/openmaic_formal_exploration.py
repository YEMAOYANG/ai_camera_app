"""Registered independent mechanisms; generated JavaScript is never an oracle."""
from __future__ import annotations
import math
import re
from integrations.openmaic_formal_quality import quality_sha

SCHEMA = "mira.openmaic.multistate-exploration.v1"
EXPLORATION_POLICY = {"schemaVersion": SCHEMA, "minimumStates": 3, "maximumStates": 5,
    "resetRequired": True, "inputModes": ["pointer", "touch"],
    "mechanismRegistry": ["fraction-ratio-percentage.v1", "semantic-state-model.v1"]}


def validate_exploration(value, *, skill_id=None):
    def exact(v, fields): return isinstance(v, dict) and set(v) == set(fields)
    def selector(v): return isinstance(v, str) and re.fullmatch(r"#[A-Za-z][A-Za-z0-9_-]{0,98}", v)
    def text(v): return isinstance(v, str) and 3 <= len(v.strip()) and len(v) <= 500
    if (not exact(value, ("schemaVersion", "mechanism", "diagramSelector", "feedbackSelector", "states", "reset"))
        or value["schemaVersion"] != SCHEMA or not selector(value["diagramSelector"]) or not selector(value["feedbackSelector"])
        or value["diagramSelector"] == value["feedbackSelector"] or not exact(value["reset"], ("selector", "stateId"))
        or not selector(value["reset"]["selector"])):
        raise ValueError("invalid exploration identity")
    m, states = value["mechanism"], value["states"]
    numeric = isinstance(m, dict) and m.get("kind") == "fraction-ratio-percentage.v1"
    if numeric:
        if not exact(m, ("kind", "numeratorSelector", "denominatorSelector", "decimalSelector", "percentSelector", "wholeSelector", "partSelector")) or any(not selector(v) for k, v in m.items() if k != "kind"):
            raise ValueError("invalid numeric mechanism")
    elif not exact(m, ("kind",)) or m["kind"] != "semantic-state-model.v1":
        raise ValueError("unregistered exploration mechanism")
    if skill_id == "fraction_ratio_percentage" and not numeric:
        raise ValueError("numeric fraction mechanism cannot downgrade to semantic evidence")
    if not isinstance(states, list) or not 3 <= len(states) <= 5:
        raise ValueError("exploration requires three to five states")
    for s in states:
        if (not exact(s, {"id", "operations", "resultText", "explanationText"} | ({"numerator", "denominator"} if numeric else set()))
            or not isinstance(s["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", s["id"])
            or not text(s["resultText"]) or not text(s["explanationText"])
            or not isinstance(s["operations"], list) or not 1 <= len(s["operations"]) <= 3):
            raise ValueError("invalid exploration state")
        for op in s["operations"]:
            if (not isinstance(op, dict) or op.get("action") not in ("click", "fill", "select")
                or not exact(op, {"selector", "action"} | ({"value"} if op["action"] != "click" else set()))
                or not selector(op["selector"]) or (op["action"] != "click" and (not isinstance(op["value"], str) or not 1 <= len(op["value"]) <= 100))):
                raise ValueError("invalid exploration operation")
        if numeric and (type(s["numerator"]) is not int or type(s["denominator"]) is not int or not 0 < s["numerator"] <= s["denominator"] <= 1000):
            raise ValueError("invalid independent numeric inputs")
    if (len({s["id"] for s in states}) != len(states) or len({s["resultText"] for s in states}) != len(states)
        or value["reset"]["stateId"] not in {s["id"] for s in states}
        or numeric and len({s["numerator"] / s["denominator"] for s in states}) != len(states)):
        raise ValueError("exploration states or reset are not distinct")


def validate_exploration_checks(receipt, viewports):
    checks = receipt["explorationChecks"]
    if not isinstance(checks, list) or len(checks) != len(receipt["objectives"]) * len(viewports):
        raise ValueError("exploration device coverage missing")
    for goal in receipt["objectives"]:
        model = goal["exploration"]
        for index, viewport in enumerate(viewports):
            found = [c for c in checks if isinstance(c, dict) and c.get("objectiveIndex") == goal["objectiveIndex"] and quality_sha(c.get("viewport")) == quality_sha(viewport)]
            if len(found) != 1 or set(found[0]) != {"objectiveIndex", "viewport", "evidence"}:
                raise ValueError("exploration observation is missing or repeated")
            evidence = found[0]["evidence"]
            numeric = model["mechanism"]["kind"] == "fraction-ratio-percentage.v1"
            if (not isinstance(evidence, dict) or set(evidence) != {"mechanism", "verification", "inputMode", "resetPassed", "states"}
                or evidence["mechanism"] != model["mechanism"]["kind"] or evidence["resetPassed"] is not True
                or evidence["inputMode"] != ("pointer" if index == 0 else "touch")
                or evidence["verification"] != ("independent_numeric_svg" if numeric else "structural_then_semantic_visual_review")
                or not isinstance(evidence["states"], list) or len(evidence["states"]) != len(model["states"])):
                raise ValueError("exploration observation contract mismatch")
            for actual, state in zip(evidence["states"], model["states"]):
                if (set(actual) != {"stateId", "diagramSha256", "feedbackSha256"} | ({"numeric"} if numeric else set())
                    or actual["stateId"] != state["id"] or any(not re.fullmatch("[a-f0-9]{64}", str(actual[k])) for k in ("diagramSha256", "feedbackSha256"))):
                    raise ValueError("state image or result identity invalid")
                if numeric:
                    n = actual["numeric"]
                    ratio = state["numerator"] / state["denominator"]
                    if (not isinstance(n, dict) or set(n) != {"numerator", "denominator", "decimal", "percent", "diagramRatio"}
                        or n["numerator"] != state["numerator"] or n["denominator"] != state["denominator"]
                        or any(type(v) not in (int, float) or not math.isfinite(v) for v in n.values())
                        or abs(n["decimal"] - ratio) > 0.0001 or abs(n["percent"] - ratio * 100) > 0.01
                        or abs(n["diagramRatio"] - ratio) > 0.015):
                        raise ValueError("numeric observation disagrees with independent mechanism")
            if any(len({s[key] for s in evidence["states"]}) != len(model["states"]) for key in ("diagramSha256", "feedbackSha256")):
                raise ValueError("states do not change diagram and explanation")
