"""Normalize returned homework transcription without inventing an answer.

The caller persists the response before parsing it. Fatal envelope errors carry
only fixed reason codes; a malformed question never removes reliable siblings.
This module neither grades answers nor dispatches provider requests.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
import json
import math

from core.errors import ApiError
from services.homework_assets import crop_region


PARSER_VERSION = "mira.homework-recognition-parser.v2"
MAX_RESPONSE_CHARACTERS = 2 * 1024 * 1024
MAX_PROMPT_CHARACTERS = 1000
MAX_ANSWER_CHARACTERS = 160
SUPPORTED_TYPES = {"arithmetic", "word_problem", "choice", "fill_blank", "geometry", "reading", "writing", "language", "science", "other", "unsupported"}
ANSWER_STATES = {"written", "blank", "unclear", "drawing"}


class RecognitionParseError(ValueError):
    """A fixed, non-content-bearing diagnostic for a received response."""

    REASONS = frozenset({"invalid_json", "invalid_schema", "truncated", "over_limit"})

    def __init__(self, reason: str):
        if reason not in self.REASONS:
            raise ValueError("unsupported recognition diagnostic")
        self.reason = reason
        super().__init__(reason)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            # Two contradictory answers must not become a last-write-wins answer.
            raise RecognitionParseError("invalid_json")
        value[key] = item
    return value


def _answer(value, maximum=MAX_ANSWER_CHARACTERS):
    if isinstance(value, str):
        return (value.strip(), False) if len(value) <= maximum else ("", None)
    if type(value) is int:
        result = str(value)
    elif isinstance(value, Decimal) and value.is_finite():
        # json.loads(parse_float=Decimal) retains the full numeric token. A
        # float round-trip could change a child's decimal answer before grading.
        result = str(value)
    else:
        # null is not evidence that the child left the original answer blank.
        # bool, lists and objects are not answers either.
        return "", None
    return (result, True) if len(result) <= maximum else ("", None)


def _confidence(value):
    if type(value) is int or isinstance(value, Decimal):
        if isinstance(value, Decimal) and not value.is_finite():
            return None
        if 0 <= value <= 1:
            return float(value)
    elif type(value) is float and math.isfinite(value) and 0 <= value <= 1:
        return value
    return None


def _region(value):
    if isinstance(value, dict):
        value = {
            key: float(number) if isinstance(number, Decimal) and number.is_finite() else number
            for key, number in value.items()
        }
    return crop_region(value)


def _contains(outer, inner):
    return (outer is not None and inner["x"] >= outer["x"] - 1e-6
            and inner["y"] >= outer["y"] - 1e-6
            and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + 1e-6
            and inner["y"] + inner["height"] <= outer["y"] + outer["height"] + 1e-6)


def _same_position(left, right):
    """Near-identical physical positions, not every overlapping shared stem."""
    x = max(left["x"], right["x"])
    y = max(left["y"], right["y"])
    w = max(0, min(left["x"] + left["width"], right["x"] + right["width"]) - x)
    h = max(0, min(left["y"] + left["height"], right["y"] + right["height"]) - y)
    intersection = w * h
    union = left["width"] * left["height"] + right["width"] * right["height"] - intersection
    return bool(union > 0 and intersection / union >= .9)


def _same_answer_positions(left, right):
    # Several independent children answers may share one large source stem.
    # Use their answer slots when both have them; never collapse those units.
    a, b = left.get("answerRegions"), right.get("answerRegions")
    if a and b:
        if len(a) != len(b):
            return False
        unused = list(b)
        for region in a:
            match = next((index for index, other in enumerate(unused) if _same_position(region, other)), None)
            if match is None:
                return False
            unused.pop(match)
        return True
    return _same_position(left["region"], right["region"])


def _source_fields(raw, *, version, answer, region, strict, issues):
    """Keep source observations separate from a solution inferred by a model."""
    present = strict or version == "v3" or any(key in raw for key in (
        "transcriptVersion", "sourceQuestionLabel", "answerState", "answerRegions", "visualEvidence"))
    if not present:
        return {}
    proof = raw.get("transcriptVersion", version)
    if proof != "v3":
        issues.add("source_version_invalid")
    label = raw.get("sourceQuestionLabel")
    if "sourceQuestionLabel" not in raw or not (label is None or isinstance(label, str) and len(label) <= 80 and label.strip()):
        label = None
        issues.add("source_label_invalid")
    elif isinstance(label, str):
        label = label.strip()
    state = raw.get("answerState")
    if not isinstance(state, str) or state not in ANSWER_STATES:
        state = "unclear"
        issues.add("answer_state_invalid")
    positions = raw.get("answerRegions")
    answer_regions = []
    if not isinstance(positions, list) or len(positions) > 16:
        issues.add("answer_regions_invalid")
    else:
        for position in positions:
            try:
                clean = _region(position)
                if clean is None or not _contains(region, clean):
                    raise ValueError("answer outside original question")
                answer_regions.append(clean)
            except (ApiError, ValueError, OverflowError, ArithmeticError):
                issues.add("answer_regions_invalid")
    if state != "unclear" and not answer_regions:
        issues.add("answer_regions_missing")
    if region is None:
        issues.add("source_region_missing")
    evidence = raw.get("visualEvidence")
    if evidence is not None and (not isinstance(evidence, str) or len(evidence) > 500):
        evidence = None
        issues.add("visual_evidence_invalid")
    elif isinstance(evidence, str):
        evidence = evidence.strip() or None
    if (state == "drawing" or raw.get("type") == "geometry") and evidence is None:
        issues.add("visual_evidence_missing")
    if state == "unclear":
        issues.add("answer_unclear")
    # □ is the observed empty slot, never an invitation to complete it. A
    # wholly blank arithmetic answer remains empty; partial answers retain □.
    if state == "blank" and any(char not in "□?？_（）() ,，、;；\t\r\n" for char in answer):
        issues.add("answer_state_conflict")
    if state == "written" and (not answer or "□" in answer):
        issues.add("answer_state_conflict")
    return {"transcriptVersion": "v3" if proof == "v3" else None,
            "sourceQuestionLabel": label, "answerState": state,
            "answerRegions": answer_regions, "visualEvidence": evidence}


def parse_recognition_response(text: str, *, maximum_items: int, maximum_answer_characters: int = MAX_ANSWER_CHARACTERS,
                               require_source_evidence: bool = False):
    """Return normalized transcription and counters that contain no source text.

    ``recognitionNeedsConfirmation`` must survive into ``check_item`` and saved
    item revisions. In particular an invalid or absent answer becomes pending,
    never a fabricated blank, wrong answer, or correct answer.
    """
    if type(maximum_answer_characters) is not int or not 1<=maximum_answer_characters<=2000:
        raise ValueError("invalid recognition answer bound")
    if type(maximum_items) is not int or not 1 <= maximum_items <= 256:
        raise ValueError("invalid recognition item bound")
    if type(require_source_evidence) is not bool:
        raise ValueError("invalid source evidence requirement")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_RESPONSE_CHARACTERS:
        raise RecognitionParseError("invalid_json")
    try:
        value = json.loads(
            text,
            parse_float=Decimal,
            parse_constant=Decimal,
            object_pairs_hook=_unique_object,
        )
    except RecognitionParseError:
        raise
    except (ValueError, TypeError, RecursionError, ArithmeticError):
        raise RecognitionParseError("invalid_json") from None
    if (
        not isinstance(value, dict)
        or type(value.get("pageReadable")) is not bool
        or not isinstance(value.get("items"), list)
    ):
        raise RecognitionParseError("invalid_schema")
    items = value["items"]
    if len(items) > maximum_items:
        # A 41st item is not silently discarded. The persisted response can be
        # inspected or reconciled without charging for another provider call.
        raise RecognitionParseError("over_limit")

    issues = Counter()
    normalized_answers = 0
    untrusted_items = 0
    cleaned = []
    duplicate_eligible = set()
    if value["pageReadable"]:
        for raw in items:
            item_issues = set()
            if not isinstance(raw, dict):
                raw = {}
                item_issues.add("item_invalid")
            prompt = raw.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARACTERS:
                prompt = ""
                item_issues.add("prompt_invalid")
            else:
                prompt = prompt.strip()
            answer, numeric_answer = _answer(raw.get("studentAnswer"), maximum_answer_characters)
            if numeric_answer is None:
                item_issues.add("answer_invalid")
            elif numeric_answer:
                normalized_answers += 1
            confidence = _confidence(raw.get("confidence"))
            if confidence is None:
                confidence = 0.0
                item_issues.add("confidence_invalid")
            annotation = raw.get("annotationAmbiguous")
            if type(annotation) is not bool:
                annotation = True
                item_issues.add("annotation_invalid")
            item_type = raw.get("type")
            if not isinstance(item_type, str) or item_type not in SUPPORTED_TYPES:
                item_type = "unsupported"
                item_issues.add("type_invalid")
            try:
                region = _region(raw.get("region"))
            except (ApiError, ValueError, OverflowError, ArithmeticError):
                region = None
                item_issues.add("region_invalid")
            source = _source_fields(raw, version=value.get("transcriptVersion"),
                answer=answer, region=region, strict=require_source_evidence, issues=item_issues)
            # A malformed transcription is preserved at its original ordinal,
            # but it cannot contribute to a child's performance assessment.
            needs_confirmation = bool(item_issues)
            if needs_confirmation:
                annotation = True
                untrusted_items += 1
                issues.update(item_issues)
            if not item_issues.intersection({"answer_invalid", "prompt_invalid", "item_invalid"}):
                duplicate_eligible.add(len(cleaned))
            cleaned.append({
                "prompt": prompt,
                "studentAnswer": answer,
                "type": item_type,
                "confidence": confidence,
                "region": region,
                "annotationAmbiguous": annotation,
                "recognitionNeedsConfirmation": needs_confirmation,
                **source,
            })
    else:
        # A provider explicitly declaring the page unreadable is not a license
        # to use a contradictory list of purported answers for assessment.
        if items:
            issues["unreadable_items_present"] = len(items)

    overlapping = {}
    for index, item in enumerate(cleaned):
        region = item["region"]
        if region is None or index not in duplicate_eligible:
            # Repeated arithmetic is legitimate; without positions there is
            # no evidence these are duplicated readings of one physical item.
            # A null answer normalized to "" is also not evidence that it is
            # identical to a separately and explicitly recognized blank.
            continue
        key = "".join(item["prompt"].split())
        overlapping.setdefault(key, []).append(index)
    for indices in overlapping.values():
        if len(indices) < 2:
            continue
        affected = {}
        for position, index in enumerate(indices):
            for other_index in indices[position + 1:]:
                item, other = cleaned[index], cleaned[other_index]
                if not _same_answer_positions(item, other):
                    continue
                issue = "overlapping_duplicate" if item["studentAnswer"] == other["studentAnswer"] else "overlapping_conflict"
                affected.setdefault(index, set()).add(issue)
                affected.setdefault(other_index, set()).add(issue)
        for index, item_issues in affected.items():
            item = cleaned[index]
            if not item["recognitionNeedsConfirmation"]:
                untrusted_items += 1
            item["recognitionNeedsConfirmation"] = True
            item["annotationAmbiguous"] = True
            issues.update(item_issues)

    diagnostics = {
        "parserVersion": PARSER_VERSION,
        "inputItems": len(items),
        "normalizedItems": len(cleaned),
        "confirmationRequiredItems": untrusted_items,
        "numericAnswersNormalized": normalized_answers,
        "issueCounts": dict(sorted(issues.items())),
    }
    return {"pageReadable": value["pageReadable"], "items": cleaned}, diagnostics
