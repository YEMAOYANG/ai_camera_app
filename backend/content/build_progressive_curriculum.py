"""Build the reviewed lesson registry from the two versioned curriculum maps.

Run with --check to verify reproducibility. This is an offline authoring tool;
the application only reads the checked-in JSON, never parses Markdown at runtime.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re

from content.progressive_curriculum import CURRICULUM_PATH, CURRICULUM_VERSION, SCHEMA_VERSION, validate_curriculum

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ("docs/curriculum/primary-language-sequence-v1.md", "docs/curriculum/primary-math-sequence-v1.md")
POLICIES: dict[str, tuple[str, list[str]]] = {}


def register(strand: str, rows: str) -> None:
    for row in rows.split(";"):
        parts = row.strip().split()
        if parts:
            if parts[0] in POLICIES:
                raise ValueError(f"duplicate unit policy: {parts[0]}")
            POLICIES[parts[0]] = (strand, parts[1:])


# Required conceptual links, not a total ordering of unrelated units.
register("number_sense", "M1A01; M1A02 M1A01; M1A03 M1A02; M1B01 M1A03; M1B03 M1B01; M2B03 M1B03; M4A01 M2B03; M6B01 M4A01")
register("integer_addition_subtraction", "M1A04 M1A03; M1B02 M1A04 M1B01; M1B04 M1B03 M1B02; M2A01 M1B04; M2A02 M2A01; M2B04 M2A02 M2B03; M4A04 M4A02 M4A03 M2B04")
register("multiplication", "M2A03 M1A04; M2A04 M2A03; M3A01 M2A04 M2A01; M3A02 M3A01 M2B03; M3B01 M3A01; M4A02 M3B01 M3A02")
register("division", "M2B01 M2A04; M2B02 M2B01; M3A03 M2B02 M1B03; M3B02 M3A03 M2B03; M4A03 M3B02 M3B01")
register("geometry", "M1A05; M4A05 M1A05 M2A05; M4B03 M4A05; M4B04 M1A05 M1A01; M5B06 M4B04 M1B03")
register("length_perimeter_area", "M1B05; M2A05 M1B05 M1B03; M3A04 M2A05 M2A04 M2B04; M3B05 M3A04 M2A04; M5A05 M3B05 M4B03 M3B02; M6A05 M3B05 M5A01")
register("time", "M1B06 M1B01; M2B05 M1B06 M2A02; M3A06 M2B05 M2B04")
register("money", "M2A06 M2A02 M1B03")
register("mass", "M3A05 M2B03")
register("data", "M2B06 M1A01 M1A05; M4B05 M2B06 M2B04; M5B05 M4B05 M4A03; M6B05 M4B05 M6A04")
register("fractions", "M3B03 M2B01; M5A04 M3B03 M5A03; M5B01 M5A04; M5B02 M5A04 M5A02; M6A01 M5A04 M5B01; M6A02 M6A01")
register("decimals", "M3B04 M3B03 M2A05 M2A06; M4B01 M3B04 M4A01; M4B02 M4B01 M2B04; M5A01 M4B02 M3B05 M4A02; M5A02 M5A01 M4A03")
register("factors_multiples", "M5A03 M4A03 M2A04")
register("equations", "M5B03 M4A04")
register("volume", "M5B04 M3B05 M3B01; M6B04 M5B04 M6A05 M6A01")
register("ratio_percentage", "M6A03 M6A02; M6A04 M5B02 M6A01 M6A03; M6B02 M6A03 M5B03; M6B03 M6B02 M6A04 M2B05 M2A05")
register("mathematical_application", "M6B06 M6B03 M6B04 M6B05")

register("pinyin", "ZH1A01; ZH1A02 ZH1A01; ZH1A03 ZH1A02; ZH1A04 ZH1A03; ZH1A05 ZH1A04; ZH1A06 ZH1A05; ZH1B01 ZH1A06")
register("characters_vocabulary", "ZH1B02; ZH1B03 ZH1B02; ZH2A01 ZH1B03; ZH2A02 ZH2A01; ZH2B01 ZH2A02 ZH2A05; ZH3A01 ZH2B01")
register("sentence_structure", "ZH1B04 ZH1B03; ZH2A03 ZH1B04; ZH3A02 ZH2A03 ZH2B02; ZH3B01 ZH3A01 ZH3A02; ZH4A02 ZH3B01; ZH5A01 ZH4A02")
register("reading_information", "ZH1B05 ZH1B04 ZH1A06; ZH2A04 ZH1B05; ZH2A05 ZH1B05; ZH2B03 ZH2A04 ZH2A05; ZH2B04 ZH2A05; ZH3A03 ZH2A05 ZH2B02; ZH3A04 ZH2B03; ZH3B02 ZH2B04 ZH3A03; ZH4A01 ZH3A03 ZH3A04; ZH4A03 ZH3A04 ZH3B01; ZH4A04 ZH3A03 ZH2B03; ZH4B01 ZH3B02; ZH4B02 ZH2B04 ZH2A05; ZH5A02 ZH4A03 ZH4A04; ZH5A03 ZH4B01 ZH4A01; ZH5B01 ZH5A03 ZH4B02; ZH5B02 ZH5A02 ZH4A01; ZH5B03 ZH4A04 ZH5A01; ZH6A01 ZH5B03; ZH6A02 ZH6A01; ZH6A03 ZH5B01 ZH6A01; ZH6B01 ZH6A02 ZH6A03; ZH6B02 ZH5A03 ZH6A03")
register("writing_expression", "ZH2B02 ZH1B04 ZH2A03; ZH2B05 ZH2B02; ZH3A05 ZH2B05 ZH3A04; ZH3B04 ZH2B04 ZH2B02; ZH3B05 ZH3A05 ZH3A03; ZH4A05 ZH3B05 ZH4A03; ZH4B04 ZH3B04; ZH4B05 ZH3B05 ZH3B01; ZH5A05 ZH4A05 ZH4B05; ZH5B04 ZH4B04 ZH5B03; ZH5B05 ZH4B01 ZH5A05; ZH6A05 ZH5A05 ZH5B02; ZH6B03 ZH5B04 ZH6A01; ZH6B04 ZH6A05 ZH5B05; ZH6B05 ZH6B01 ZH6B02 ZH6B03 ZH6B04")
register("poetry_classical_reading", "ZH3B03 ZH1B05 ZH3A01; ZH4B03 ZH3B03; ZH5A04 ZH4B03; ZH6A04 ZH5A04 ZH4A04")

register("alphabet_phonics", "EN1A01; EN1A02 EN1A01; EN1A03 EN1A02; EN1A04 EN1A03; EN1A05 EN1A04; EN1B01 EN1A05; EN2A01 EN1B01; EN2A02 EN2A01; EN3A01 EN2A02; EN3A02 EN3A01; EN4A01 EN3A02")
register("vocabulary_fixed_language", "EN1B02; EN1B03; EN1B04 EN1B02; EN2A03 EN1B04 EN1B03; EN2A04 EN2A03; EN2A05 EN1B02; EN2B01 EN2A03; EN2B02 EN2A04; EN2B03 EN2A04; EN2B04 EN2B02 EN2B03; EN3A04 EN1B03 EN3A03; EN4B03 EN2B03 EN3B04; EN5B04 EN2A03 EN4B01")
register("english_reading_expression", "EN1B05 EN1A05 EN1B02 EN1B04; EN2B05 EN1B05 EN2B02 EN2B04; EN3B04 EN2B05 EN3A03; EN3B05 EN3B01 EN3B02 EN3A04 EN3B04; EN4A05 EN4A04 EN3B05; EN4B04 EN3B01 EN3B04 EN4B01; EN4B05 EN3A04 EN2A05 EN2B05; EN5A05 EN5A04 EN3B04; EN5B05 EN5B03 EN3A04; EN6A04 EN5A05 EN6A03; EN6A05 EN4B04 EN6A03; EN6B02 EN5B05 EN6A01 EN6A03; EN6B03 EN6A04 EN6A05 EN6B01; EN6B04 EN3B05 EN5A05 EN5B05 EN6A01 EN6B01; EN6B05 EN6B02 EN6B03 EN6B04")
register("english_grammar", "EN3A03 EN2B01 EN2B02; EN3A05 EN3A03; EN3B01 EN3A03 EN2B02; EN3B02 EN3B01 EN3A05; EN3B03 EN3B02 EN2B04; EN4A02 EN3B01 EN1B02; EN4A03 EN4A02; EN4A04 EN4A03 EN3B02; EN4B01 EN2B02; EN4B02 EN4B01; EN5A01 EN3B01 EN1B02; EN5A02 EN5A01 EN3B01; EN5A03 EN5A02; EN5A04 EN5A03 EN3B02; EN5B01 EN3A05; EN5B02 EN5B01 EN4A02; EN5B03 EN5A04 EN5B02 EN4A04; EN6A01 EN2B02 EN3B02; EN6A02 EN3A03; EN6A03 EN2B05 EN3B03; EN6B01 EN5B03 EN6A02")

GRAMMAR_BY_STEP = {
    "EN1B02": {1: ["fixed_greeting"], 3: ["fixed_identity"]},
    "EN1B04": {3: ["fixed_this_is"]}, "EN1B05": {1: ["sight_words_basic"]},
    "EN2A03": {2: ["noun_article"], 3: ["noun_plural"], 4: ["have_possession"]},
    "EN2A04": {1: ["demonstratives_singular"], 2: ["demonstratives_plural"], 3: ["possessive_adjectives_my_your"]},
    "EN2A05": {2: ["can_ability"], 3: ["can_negative"], 4: ["can_question"]},
    "EN2B01": {2: ["fixed_like"], 3: ["fixed_dont_like"], 4: ["fixed_do_you_like"]},
    "EN2B02": {1: ["subject_pronouns"], 3: ["possessive_adjectives_his_her"]},
    "EN2B03": {1: ["prepositions_in_on_under"], 3: ["where_is"]},
    "EN2B04": {1: ["wh_what"], 2: ["wh_who"], 3: ["wh_where"]},
    "EN2B05": {3: ["conjunction_and_but"]},
    "EN3A03": {2: ["simple_present"], 3: ["time_every_day"]},
    "EN3A04": {4: ["time_at"]}, "EN3A05": {1: ["present_do_question"], 3: ["present_dont"]},
    "EN3B01": {2: ["present_third_person_s"], 3: ["present_third_person_es"], 4: ["have_has"]},
    "EN3B02": {1: ["present_does_question"], 3: ["present_doesnt"]},
    "EN3B03": {1: ["wh_when"], 3: ["why_because"]},
    "EN3B04": {1: ["sequence_connectors"]},
    "EN4A02": {2: ["present_continuous"]}, "EN4A03": {2: ["ing_spelling"], 3: ["continuous_question"], 4: ["continuous_negative"]},
    "EN4B01": {1: ["gradable_adjectives"], 2: ["comparative_er"], 3: ["comparative_more"], 4: ["comparative_than"]},
    "EN4B02": {2: ["superlative"]}, "EN4B03": {1: ["prepositions_next_to_between"], 2: ["directions_left_right"], 3: ["before_after"]},
    "EN5A01": {1: ["past_time_markers"], 2: ["past_be"]},
    "EN5A02": {2: ["simple_past", "past_regular_ed"]}, "EN5A03": {1: ["past_irregular"]},
    "EN5A04": {1: ["past_did_question"], 3: ["past_didnt"]},
    "EN5B01": {1: ["future_time_markers"], 2: ["future_will"], 3: ["future_wont"]},
    "EN5B02": {2: ["future_going_to"]}, "EN5B04": {1: ["countability"], 2: ["many_much"], 3: ["some_any"]},
    "EN6A01": {1: ["object_pronouns"]}, "EN6A02": {1: ["frequency_adverbs"]}, "EN6A03": {4: ["conjunction_so"]},
}
TEMPORAL_CODES = {"simple_present", "present_continuous", "simple_past", "past_be", "past_regular_ed", "past_irregular", "past_did_question", "past_didnt", "future_will", "future_wont", "future_going_to", "present_perfect", "passive_voice", "complex_clause"}
OPERATIONS_BY_STEP = {"M1A04": {1: ["add"], 2: ["subtract"]},
                      "M2A03": {2: ["multiply"]}, "M2B01": {3: ["divide"]}}
PINYIN = {
    "ZH1A01": {2: ["a", "o", "e"], 3: ["i", "u", "ü"], 4: ["一声", "二声", "三声", "四声"]},
    "ZH1A02": {1: ["b", "p"], 2: ["m", "f"], 3: ["d", "t", "n", "l"]},
    "ZH1A03": {1: ["g", "k", "h"], 2: ["j", "q", "x"], 3: ["y", "w"]},
    "ZH1A04": {1: ["z", "c", "s"], 2: ["zh", "ch", "sh", "r"]},
    "ZH1A05": {1: ["ai", "ei", "ui"], 2: ["ao", "ou", "iu"], 3: ["ie", "üe", "er"]},
    "ZH1A06": {1: ["an", "en", "in", "un", "ün"], 2: ["ang", "eng", "ing", "ong"], 3: ["zhi", "chi", "shi", "ri", "zi", "ci", "si", "yi", "wu", "yu", "ye", "yue", "yuan", "yin", "yun", "ying"]},
}
MATH_BOUNDS = {
    "M1A01": (0, 5), "M1A02": (0, 10), "M1A03": (0, 10), "M1A04": (0, 10),
    "M1A05": (0, 5), "M1B01": (0, 20), "M1B02": (0, 20), "M1B03": (0, 100),
    "M1B04": (0, 100), "M1B05": (0, 5), "M1B06": (0, 12),
    "M2A01": (0, 100), "M2A02": (0, 100), "M2A03": (0, 25), "M2A04": (0, 81),
    "M2A05": (0, 100), "M2A06": (0, 100), "M2B01": (0, 81), "M2B02": (0, 100),
    "M2B03": (0, 10000), "M2B04": (0, 999), "M2B05": (0, 60), "M2B06": (0, 100),
}


def split_step(uid: str, step: int, title: str) -> list[dict]:
    """Explicitly split alphabet/phonics and entry numeracy into small targets."""
    def rows(tokens: list[str], label: str, **extra) -> list[dict]:
        return [{"title": f"{label}：{token}", "tokens": [token], **extra} for token in tokens]
    if uid in PINYIN and step in PINYIN[uid]:
        label = "声调辨听" if uid == "ZH1A01" and step == 4 else "整体认读" if uid == "ZH1A06" and step == 3 else "认读与辨听"
        return rows(PINYIN[uid][step], label, kind="pinyin")
    if uid.startswith("EN1A"):
        unit = int(uid[-2:]); start = (unit - 1) * 5; end = 26 if unit == 5 else start + 5
        letters = [chr(65 + n) for n in range(start, end)]
        label = {1: "辨认字母形", 2: "大小写对应", 3: "字母名与已学字母辨认", 4: "字母在已示范词中的声音"}[step]
        return rows(letters, label, kind="letter")
    if uid == "M1A01":
        if step == 1: return rows([str(i) for i in range(1, 6)], "逐物对应数数", kind="number", bound_by_token=True)
        if step == 2: return rows([str(i) for i in range(2, 6)], "从1顺序数到", kind="number", bound_by_token=True)
        if step in (3, 4, 5):
            return rows([str(i) for i in range(1, 6)], {3: "最后一个数表示总数", 4: "认读数字与匹配数量", 5: "按数量要求取物"}[step], kind="number", bound_by_token=True)
    if uid == "M1A02":
        if step == 1: return rows(["0"], "一个也没有", kind="number", bound_by_token=True)
        if step in (2, 3): return rows([str(i) for i in range(6, 11)], "逐物数数" if step == 2 else "数字与数量对应", kind="number", bound_by_token=True)
        return [{"title": text, "tokens": [], "kind": "number"} for text in ("0到10正数", "10到0倒数", "0到10的相邻数")]
    if uid == "M1A03" and step in (3, 4):
        return rows([str(i) for i in (range(2, 6) if step == 3 else range(6, 11))], "分成两部分并合成", kind="number", bound_by_token=True)
    if uid == "M1B01" and step in (2, 3):
        return rows([str(i) for i in range(11, 21)], "一个十和几个一" if step == 2 else "数量数字与数位对应", kind="number", bound_by_token=True)
    if uid == "M1B03" and step == 1:
        return rows([str(i) for i in range(10, 101, 10)], "整十数数", kind="number", bound_by_token=True)
    if uid == "M2A03" and step == 4:
        return rows(["2", "3", "4", "5"], "用阵列建立乘法事实", kind="number")
    if uid == "M2A04" and step in (1, 2):
        return rows(["6", "7"] if step == 1 else ["8", "9"], "用已学乘法推出乘法事实", kind="number")
    if uid == "EN1B01" and step in (2, 3):
        return rows(["a", "o"] if step == 2 else ["i", "e", "u"], "短元音规则词拼读", kind="phonics")
    if uid == "EN1B03" and step == 1:
        return rows(["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"], "数量词辨认", kind="vocabulary")
    if uid == "EN3A04" and step == 1:
        return rows(["eleven/twelve", "thirteen/fourteen", "fifteen/sixteen", "seventeen/eighteen", "nineteen/twenty", "twenty-one to twenty-nine", "thirty/forty/fifty/sixty"], "钟表所需数字词", kind="vocabulary")
    if uid == "EN2A02" and step == 3:
        return rows(["th", "wh"], "选定词中的辅音组合", kind="phonics")
    if uid == "EN3A01" and step == 3:
        return rows(["i_e", "o_e"], "词尾e拼读", kind="phonics")
    return [{"title": title, "tokens": [], "kind": "general"}]


def assessment_mode(subject: str, title: str, strand: str) -> str:
    # A generated explanation/recitation/composition cannot be scored as two
    # closed questions. Recognition and factual comparison remain objective.
    observed = r"书写|笔顺|听写|口述|复述|朗读|跟读|对话|交流|表达|写作|写一|短观察记录|口头|初稿|修改理由|作品|项目|调查|测量线段|按说明行动|按说明定位|按指令找物|根据描述摆放|说明依据|说明理由|读者检验|反馈澄清"
    if re.search(observed, title): return "observed"
    if subject == "chinese" and strand == "writing_expression" and not re.search(r"删除|错字|标点|比较|区别|判断|完整|遗漏|检查", title): return "observed"
    return "objective"


def build() -> dict:
    source_units = []
    source_hashes = {}
    for source in SOURCES:
        text = (ROOT / source).read_text(encoding="utf-8")
        source_hashes[source] = hashlib.sha256(text.encode()).hexdigest()
        for match in re.finditer(r"^\| ((?:ZH|EN|M)[1-6][AB]\d{2}) ([^|]+)\| ([^|]+)\|$", text, re.M):
            uid, title, steps = match.groups()
            source_units.append((uid, title.strip(), [part.strip() for part in steps.split("→")], source))
    if len(source_units) != 187 or {row[0] for row in source_units} != set(POLICIES):
        raise ValueError(f"unit map/policy mismatch: {len(source_units)}, missing={set(row[0] for row in source_units)-set(POLICIES)}, extra={set(POLICIES)-set(row[0] for row in source_units)}")
    def ordering(row):
        prefix, grade, phase = re.match(r"(ZH|EN|M)([1-6])([AB])", row[0]).groups()
        return int(grade), {"ZH": 0, "M": 1, "EN": 2}[prefix], phase, row[0][-2:]
    source_units.sort(key=ordering)
    units = []; lookup = {}; unit_count = defaultdict(int)
    for uid, title, steps, source in source_units:
        prefix, grade, phase = re.match(r"(ZH|EN|M)([1-6])([AB])", uid).groups()
        subject = {"ZH": "chinese", "EN": "english", "M": "math"}[prefix]
        strand, unit_priors = POLICIES[uid]
        unit_count[(grade, subject)] += 1
        unit = {"unitId": uid, "gradeCode": f"primary_{grade}", "subject": subject,
                "phase": "upper" if phase == "A" else "lower", "strand": strand,
                "title": title, "sequence": unit_count[(grade, subject)],
                "sourceDocument": source, "sourceStepCount": len(steps), "lessons": []}
        for step_index, step_title in enumerate(steps, 1):
            for piece in split_step(uid, step_index, step_title):
                lid = f"{uid}.{len(unit['lessons'])+1:02d}"
                mode = assessment_mode(subject, piece["title"], strand)
                # Read/write skills are separate: an observed handwriting or
                # oral-production item must not gate the next recognition item.
                prior_in_unit = [row for row in unit["lessons"] if row["assessmentMode"] == "objective"]
                priors = [prior_in_unit[-1]["lessonId"]] if prior_in_unit else []
                if mode == "observed" and unit["lessons"] and unit["lessons"][-1]["assessmentMode"] == "observed":
                    priors.append(unit["lessons"][-1]["lessonId"])
                for prior_unit in unit_priors:
                    previous = lookup[prior_unit]["lessons"]
                    closed = [row for row in previous if row["assessmentMode"] == "objective"]
                    anchor = closed[-1] if closed else previous[-1]
                    priors.append(anchor["lessonId"])
                priors = list(dict.fromkeys(priors))
                low, high = MATH_BOUNDS.get(uid, (None, None))
                if piece.get("bound_by_token"):
                    low, high = 0, int(piece["tokens"][0])
                grammar = GRAMMAR_BY_STEP.get(uid, {}).get(step_index, [])
                row = {"lessonId": lid, "title": piece["title"], "sourceStepSequence": step_index,
                    "sourceStepTitle": step_title,
                    "learningObjectives": [f"围绕{'一二三四五六'[int(unit['gradeCode'][-1]) - 1]}年级《{unit['title']}》的本课目标，{'通过实际表现完成' if mode == 'observed' else '通过独立辨认、匹配、选择、排序或计算验证'}：{piece['title']}"],
                    "prerequisiteLessonIds": priors, "introducedKnowledgeIds": [lid], "reviewKnowledgeIds": list(priors),
                    "assessmentMode": mode,
                    "assessmentCriteria": {"minimumIndependentAttempts": 5, "minimumDistinctTasks": 5,
                        "minimumAccuracy": 0.8, "requiresObservedConfirmation": mode == "observed",
                        "claimScope": "this_lesson_only", "promptedAnswersCountAsIndependent": False},
                    "constraints": {"introducedTokens": piece["tokens"], "tokenKind": piece["kind"],
                        "allowedLetters": [], "allowedPinyin": [], "minimumNumber": low, "maximumNumber": high,
                        "introducedGrammarCodes": list(grammar), "allowedGrammarCodes": [], "excludedGrammarCodes": [],
                        "introducedOperations": OPERATIONS_BY_STEP.get(uid, {}).get(step_index, []),
                        "allowedOperations": [], "assessmentEvidenceKinds": [],
                        "neutralDistractorTokens": ["○", "△", "□"] if piece["kind"] in ("letter", "pinyin", "phonics") else [],
                        "teachBeforeAssessment": True, "newVocabularyMustBeIntroducedBeforeUse": True,
                        "noUnintroducedKnowledgeInInstructions": True,
                        "assessmentEvidenceScope": "observed_performance" if mode == "observed" else "declared_objective_only",
                        "writtenNumberRecognitionRequired": not(uid == "M1A01" and step_index < 4),
                        "audioInstructionsAllowed": True,
                        "maxCoreNewTargets": 1,
                        "challengeMayOnlyCombineDeclaredKnowledge": True}}
                unit["lessons"].append(row)
        units.append(unit); lookup[uid] = unit
    rows = {row["lessonId"]: row for unit in units for row in unit["lessons"]}
    # Scope is inherited through prerequisites, never enabled simply by grade.
    for row in rows.values():
        ancestors = set(); pending = list(row["prerequisiteLessonIds"])
        while pending:
            prior = pending.pop()
            if prior not in ancestors:
                ancestors.add(prior); pending.extend(rows[prior]["prerequisiteLessonIds"])
        scope = [rows[lid] for lid in rows if lid in ancestors] + [row]
        constraints = row["constraints"]
        for key, kind in (("allowedLetters", "letter"), ("allowedPinyin", "pinyin")):
            constraints[key] = list(dict.fromkeys(token for parent in scope if parent["constraints"]["tokenKind"] == kind for token in parent["constraints"]["introducedTokens"]))
        constraints["allowedGrammarCodes"] = sorted({code for parent in scope for code in parent["constraints"]["introducedGrammarCodes"]})
        constraints["excludedGrammarCodes"] = sorted(TEMPORAL_CODES - set(constraints["allowedGrammarCodes"])) if row["lessonId"].startswith("EN") else []
        constraints["allowedOperations"] = sorted({code for parent in scope for code in parent["constraints"]["introducedOperations"]})
        if row["assessmentMode"] == "objective":
            if not constraints["writtenNumberRecognitionRequired"]:
                constraints["assessmentEvidenceKinds"] = ["count_objects"]
            elif constraints["introducedTokens"] and constraints["tokenKind"] in ("letter", "pinyin", "number", "vocabulary", "phonics"):
                constraints["assessmentEvidenceKinds"] = ["token_match"]
            elif row["lessonId"].startswith("M") and constraints["allowedOperations"] and re.search(r"加减|进位|退位|进退位|相加|相减|相乘|竖式|估算|计算|求商|验算|部分积|分配律|通分|约分|乘整数|除整数", row["title"]):
                constraints["assessmentEvidenceKinds"] = ["numeric_expression", "independent_choice"]
            else:
                constraints["assessmentEvidenceKinds"] = ["independent_choice"]
    payload = {"schemaVersion": SCHEMA_VERSION, "curriculumVersion": CURRICULUM_VERSION,
               "scope": "mira_self_authored_primary_1_to_6", "sourceDocumentSha256": source_hashes,
               "publicationIsSeparate": True, "units": units}
    validate_curriculum(payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not CURRICULUM_PATH.exists() or CURRICULUM_PATH.read_text(encoding="utf-8") != output:
            raise SystemExit("progressive curriculum JSON differs from its authoring sources")
    else:
        CURRICULUM_PATH.write_text(output, encoding="utf-8")
    payload = json.loads(output)
    print(f"{len(payload['units'])} units, {sum(len(u['lessons']) for u in payload['units'])} lessons; {'verified' if args.check else 'written'}")


if __name__ == "__main__":
    main()
