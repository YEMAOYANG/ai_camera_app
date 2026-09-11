"""Versioned, answer-blind objective rules for the bounded grades 2–6 pilot.

These are grammars and finite language inventories, never model answer keys.
The same public policy guides creation; the Host derives answers separately.
Unregistered formats (including subjective writing/appreciation) fail closed.
"""
from __future__ import annotations

import ast
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Mapping


OBJECTIVE_RULE_VERSION = "mira.learning.primary-2-6-objective-rules.v2"
CLOSED_ASSESSMENT_TYPES = (
    "open_ended_composition", "subjective_literary_appreciation",
    "unbounded_reading_inference", "speech_pronunciation_scoring",
    "unregistered_textbook_reproduction",
)

WORD_RELATIONS = {
    "近义词": {"开心": "快乐", "美丽": "漂亮", "立刻": "马上", "仔细": "认真", "安静": "宁静", "喜欢": "喜爱", "帮助": "协助", "明白": "清楚", "暖和": "温暖", "寻找": "寻觅", "忽然": "突然", "保护": "爱护", "勇敢": "勇猛", "宽广": "辽阔", "迅速": "快速", "整洁": "干净"},
    "反义词": {"高": "低", "长": "短", "大": "小", "多": "少", "远": "近", "快": "慢", "早": "晚", "冷": "热", "开": "关", "轻": "重", "明": "暗", "新": "旧", "宽": "窄", "深": "浅", "进": "退", "强": "弱", "粗": "细", "干": "湿"},
}
ENGLISH_VOCABULARY = {
    "family_people": {"爸爸": "father", "妈妈": "mother", "姐姐": "sister", "妹妹": "sister", "哥哥": "brother", "弟弟": "brother", "爷爷": "grandfather", "奶奶": "grandmother", "他": "he", "她": "she", "叔叔": "uncle", "阿姨": "aunt", "婴儿": "baby", "男孩": "boy", "女孩": "girl", "朋友": "friend", "老师": "teacher", "学生": "student"},
    "school_objects": {"书": "book", "尺子": "ruler", "铅笔": "pencil", "书包": "schoolbag", "书桌": "desk", "钢笔": "pen", "橡皮": "eraser", "椅子": "chair", "黑板": "blackboard", "笔记本": "notebook", "纸": "paper", "胶水": "glue", "剪刀": "scissors", "蜡笔": "crayon", "铅笔盒": "pencil box", "字典": "dictionary", "粉笔": "chalk", "地图": "map"},
}
VERBS = {
    "run": ("runs", "running", "ran"), "read": ("reads", "reading", "read"),
    "sing": ("sings", "singing", "sang"), "swim": ("swims", "swimming", "swam"),
    "fly": ("flies", "flying", "flew"), "walk": ("walks", "walking", "walked"),
    "play": ("plays", "playing", "played"), "jump": ("jumps", "jumping", "jumped"),
    "look": ("looks", "looking", "looked"), "cook": ("cooks", "cooking", "cooked"),
    "work": ("works", "working", "worked"), "talk": ("talks", "talking", "talked"),
    "eat": ("eats", "eating", "ate"), "drink": ("drinks", "drinking", "drank"),
    "go": ("goes", "going", "went"), "write": ("writes", "writing", "wrote"),
}
REVISIONS = {
    "一只铅笔": "一支铅笔", "一本树": "一棵树", "一条花": "一朵花", "一棵书": "一本书",
    "一支鱼": "一条鱼", "一朵山": "一座山", "一把雨": "一场雨", "一头鸟": "一只鸟",
    "十分非常开心": "十分开心", "大约十人左右": "大约十人", "先首先出发": "首先出发",
    "又再次回来": "再次回来", "忍不住不禁笑了": "忍不住笑了", "亲眼目睹看见": "亲眼目睹",
    "提高数量": "增加数量", "增加水平": "提高水平", "改善错误": "改正错误", "改正生活": "改善生活",
}
POLITE_RESPONSES = {
    "请求借笔": "请问，可以借我一支笔吗？", "收到帮助": "谢谢你的帮助！",
    "碰到别人": "对不起，碰到你了。", "归还图书": "谢谢，这本书还给你。",
    "请求让路": "请让一下，谢谢。", "打断谈话": "不好意思，可以打扰一下吗？",
    "邀请同学": "你愿意和我们一起玩吗？", "安慰朋友": "别着急，我们一起想办法。",
    "请求讲解": "请再讲一遍，好吗？", "拒绝邀请": "谢谢邀请，这次我不能参加。",
    "提醒安静": "请轻声说话，谢谢。", "向人问路": "请问，图书馆怎么走？",
    "提醒排队": "请在队伍后面排队。", "接待来客": "欢迎，请坐。",
    "告别同学": "再见，明天见！", "道歉迟到": "对不起，我迟到了。",
}

# Each policy deliberately covers a measurable subset of its registered skill.
# No entry represents a complete textbook unit or a whole school year.
_MODES = {
    "number_operations_100": ("integer_add_sub_100", "计算：23+48。"),
    "multiplication_division_intro": ("table_multiply_divide", "计算：7*8。"),
    "measurement_time": ("length_conversion", "换算：3米=多少厘米？"),
    "multi_digit_operations": ("integer_operations_1000", "计算：321+456。"),
    "fractions_intro": ("fraction_representation", "把一个整体平均分成8份，取其中3份，用分数表示是多少？"),
    "perimeter_measurement": ("rectangle_perimeter", "长方形长8厘米，宽3厘米，周长是多少厘米？"),
    "large_numbers_operations": ("large_integer_operations", "计算：321*24。"),
    "decimals_intro": ("decimal_add_sub", "计算：3.25+1.6。"),
    "area_geometry": ("rectangle_area", "长方形长8厘米，宽3厘米，面积是多少平方厘米？"),
    "fractions_operations": ("fraction_add_sub", "计算分数：1/3+1/6。"),
    "decimals_equations": ("decimal_multiply_divide", "计算：3.2*1.5。"),
    "volume_statistics": ("cuboid_volume", "长方体长8厘米，宽3厘米，高2厘米，体积是多少立方厘米？"),
    "fraction_ratio_percentage": ("fraction_percentage", "把分数3/4化成百分数是多少？"),
    "proportional_reasoning": ("ratio_distribution", "把60个物品按2:3分给甲和乙，甲得到多少个？"),
    "circle_solid_geometry": ("circle_measure", "圆的半径是3厘米，圆周率取3.14，面积是多少平方厘米？"),
    "word_relations": ("word_relation", "“开心”的近义词是什么？"),
    "sentence_order_punctuation": ("sentence_punctuation", "给句子选择句末标点：你要去哪里"),
    "short_reading": ("explicit_fact", "短文：小林在周一去了公园。问题：小林在什么时候去了公园？"),
    "context_words": ("word_relation", "“立刻”的近义词是什么？"),
    "connect_sentences": ("connective", "选择关联词：____下雨了，所以我们带伞。"),
    "reading_evidence": ("explicit_fact", "短文：小林在周一去了公园。问题：小林在什么时候去了公园？"),
    "paragraph_structure": ("paragraph_structure", "判断段落结构：总的来说，校园很美。花坛有花，草地很绿。"),
    "sentence_revision": ("sentence_revision", "修改不恰当的表达：一只铅笔"),
    "reading_inference": ("conditional_inference", "短文：如果下雨，小林就带伞。今天下雨。问题：小林会做什么？"),
    "meaning_expression": ("simile", "判断修辞：月亮像小船。"),
    "nonfiction_reading": ("explanation_method", "判断说明方法：这棵树高12米。"),
    "narrative_logic": ("explicit_cause", "短文：因为下雨了，所以小林带了伞。问题：小林为什么带了伞？"),
    "argument_evidence": ("quantified_evidence", "观点：所有种子都发芽了。事实：一共20粒种子，有18粒发芽。事实是否支持观点？"),
    "integrated_reading": ("combined_facts", "短文：小林读了8页书，小雨读了6页书。问题：两人一共读了多少页书？"),
    "language_application": ("polite_response", "选择得体表达，情境：请求借笔"),
    "family_people": ("english_vocabulary", "选择英语词语：爸爸"),
    "school_objects": ("english_vocabulary", "选择英语词语：铅笔"),
    "actions_abilities": ("can_verb", "填空：She can ____ (swim)."),
    "self_introduction": ("self_information", "My name is Lily. What is my name?"),
    "daily_routines": ("present_simple", "填空：He ____ (walk) every day."),
    "time_schedules": ("clock_order", "Tom starts at 08:30. Lily starts at 09:00. Who starts earlier?"),
    "questions_answers": ("wh_word", "填空：____ is Tom? He is at home."),
    "descriptions": ("there_be", "填空：There ____ 3 books on the desk."),
    "present_tenses": ("present_tense", "填空：He ____ (run) now."),
    "comparisons": ("height_comparison", "Tom is 120 cm tall. Lily is 130 cm tall. Who is taller?"),
    "informational_reading": ("english_cause", "Tom stays home because it is raining. Why does Tom stay home?"),
    "past_future": ("past_future", "填空：She ____ (walk) yesterday."),
    "grammar_in_context": ("present_simple", "填空：He ____ (walk) every day."),
}


def _legacy_question_policy(grade_code: str, subject: str, skill_id: str) -> dict:
    if grade_code not in {f"primary_{n}" for n in range(2, 7)}:
        raise ValueError("objective grammar grade is not registered")
    # Same stable skill id may occur in different subjects/grades.
    mode, example = _MODES[skill_id] if skill_id in _MODES else (None, None)
    if subject == "english" and skill_id in {"short_reading", "reading_evidence"}:
        mode, example = "english_fact", "Tom is at the park. Where is Tom?"
    if mode is None:
        raise ValueError("objective grammar skill is not registered")
    from content.primary_skill_boundaries import boundaries_for
    if not any(b.skill_id == skill_id for b in boundaries_for(grade_code, subject)):
        raise ValueError("objective grammar grade/subject/skill mismatch")
    policy = {
        "version": OBJECTIVE_RULE_VERSION, "gradeCode": grade_code,
        "subject": subject, "skillId": skill_id, "mode": mode,
        # Numeric independent proofs bind every operand to the public prompt.
        # Geometry/conversion constants and rational answers use text/choice
        # until their own dimensional proof contract is registered.
        "allowedQuestionTypes": (["numeric"] if mode in {
            "integer_add_sub_100", "table_multiply_divide", "integer_operations_1000",
            "large_integer_operations", "decimal_add_sub", "decimal_multiply_divide",
        } else []) + ["exact_text", "single_choice"],
        "publicPromptExample": example,
        "promptPolicy": "Use this exact public grammar with fresh bounded operands or inventory members; do not copy the example five times. Host derives the answer without the model key.",
        "coverage": "registered_objective_subset", "closedAssessmentTypes": list(CLOSED_ASSESSMENT_TYPES),
    }
    if mode == "word_relation": policy["inventory"] = WORD_RELATIONS
    if mode == "english_vocabulary": policy["inventory"] = ENGLISH_VOCABULARY[skill_id]
    if mode in {"can_verb", "present_simple", "present_tense", "past_future"}: policy["verbs"] = VERBS
    if mode == "sentence_revision": policy["inventory"] = REVISIONS
    if mode == "polite_response": policy["inventory"] = POLITE_RESPONSES
    return policy


def _text(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _decimal(value: object) -> str:
    number = Decimal(str(value))
    if not number.is_finite(): raise ValueError("nonfinite result")
    return format(number.normalize(), "f")


def bounded_numeric_ast(expression: str, *, mode: str) -> tuple[Fraction, dict]:
    """Small Fraction AST; rejects boolean, power, names and unbounded work."""
    normalized = _text(expression).replace("×", "*").replace("÷", "/")
    if len(normalized) > 100 or re.fullmatch(r"[0-9. +*/()\-]+", normalized) is None:
        raise ValueError("unregistered arithmetic expression")
    tree = ast.parse(normalized, mode="eval")
    nodes = list(ast.walk(tree))
    if len(nodes) > 30: raise ValueError("arithmetic expression too complex")
    operations = []
    operands = []
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            raw = ast.get_source_segment(normalized, node)
            value = Fraction(raw)
            if value < 0 or value > 100_000_000 or value.denominator > 100:
                raise ValueError("arithmetic operand outside bound")
            operands.append(value)
            return value, {"kind": "number", "value": _fraction_text(value)}
        if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub, ast.Mult, ast.Div):
            left, ltree = visit(node.left); right, rtree = visit(node.right)
            op = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}[type(node.op)]
            operations.append(op)
            if op == "/" and right == 0: raise ValueError("zero divisor")
            result = {"+": lambda: left + right, "-": lambda: left - right, "*": lambda: left * right, "/": lambda: left / right}[op]()
            if result < 0 or result > 100_000_000: raise ValueError("arithmetic result outside bound")
            return result, {"kind": "binary", "operator": op, "left": ltree, "right": rtree}
        raise ValueError("unregistered arithmetic AST")
    result, payload = visit(tree.body)
    if not operations: raise ValueError("constant is not an arithmetic problem")
    limits = {
        "integer_add_sub_100": (100, {"+", "-"}, 2, True),
        "table_multiply_divide": (81, {"*", "/"}, 1, True),
        "integer_operations_1000": (1000, {"+", "-", "*", "/"}, 2, True),
        "large_integer_operations": (100_000_000, {"+", "-", "*", "/"}, 3, True),
        "decimal_add_sub": (1000, {"+", "-"}, 2, False),
        "decimal_multiply_divide": (1000, {"*", "/"}, 2, False),
        "fraction_add_sub": (100, {"+", "-", "/"}, 5, True),
        "derived_measurement": (100_000_000, {"+", "-", "*", "/"}, 5, False),
    }
    maximum, allowed, count, integers = limits[mode]
    if len(operations) > count or not set(operations) <= allowed or max(operands) > maximum or result > maximum:
        raise ValueError("arithmetic outside skill")
    if integers and any(n.denominator != 1 for n in operands): raise ValueError("noninteger operand")
    if mode == "table_multiply_divide":
        if len(operands) != 2 or result.denominator != 1 or min(operands) < 2:
            raise ValueError("table arithmetic must be exact")
        if operations == ["*"] and max(operands) > 9: raise ValueError("multiplication table bound")
        if operations == ["/"] and not (2 <= operands[1] <= 9 and 2 <= result <= 9): raise ValueError("division table bound")
    if mode == "integer_operations_1000" and any(op in {"*", "/"} for op in operations) and (len(operands) != 2 or operands[1] > 9 or result.denominator != 1):
        raise ValueError("one-digit operation bound")
    if mode not in {"fraction_add_sub", "derived_measurement"} and result.denominator not in {1, 2, 4, 5, 10, 20, 25, 50, 100}:
        raise ValueError("nonterminating or overprecision answer")
    return result, payload


def _solve_legacy_objective_question(grade_code: str, subject: str, skill_id: str, prompt: str) -> str:
    policy = _legacy_question_policy(grade_code, subject, skill_id)
    mode = policy["mode"]
    p = _text(prompt)
    n = r"(\d+(?:\.\d+)?)"
    name = r"([A-Za-z]+)"
    han = r"([\u3400-\u9fff]{1,16})"
    match = lambda pattern: re.fullmatch(_text(pattern), p)
    m = match(r"计算[:：]([0-9. +*/()×÷\-]+)[。?？]?")
    if mode in {"integer_add_sub_100", "table_multiply_divide", "integer_operations_1000", "large_integer_operations", "decimal_add_sub", "decimal_multiply_divide"} and m:
        value, _ = bounded_numeric_ast(m[1], mode=mode)
        return _decimal(Decimal(value.numerator) / Decimal(value.denominator))
    if mode == "fraction_add_sub":
        m = match(r"计算分数[:：](\d+/\d+[+\-]\d+/\d+)[。?？]?")
        if m: return _fraction_text(bounded_numeric_ast(m[1], mode=mode)[0])
    if mode == "length_conversion":
        m = match(r"换算[:：](\d+)米=多少厘米[?？]")
        if m and 1 <= int(m[1]) <= 99: return str(int(m[1])*100)
        m = match(r"换算[:：](\d+)厘米=多少米[?？]")
        if m and 100 <= int(m[1]) <= 9900 and int(m[1]) % 100 == 0: return str(int(m[1])//100)
    if mode == "fraction_representation":
        m = match(r"把一个整体平均分成(\d+)份，取其中(\d+)份，用分数表示是多少[?？]")
        if m and 2 <= int(m[1]) <= 12 and 1 <= int(m[2]) <= int(m[1]): return f"{int(m[2])}/{int(m[1])}"
    if mode in {"rectangle_perimeter", "rectangle_area"}:
        m = match(r"长方形长"+n+r"厘米，宽"+n+r"厘米，"+(r"周长是多少厘米" if mode == "rectangle_perimeter" else r"面积是多少平方厘米")+r"[?？]")
        if m and all(0 < Decimal(x) <= 100 for x in m.groups()):
            a,b = map(Decimal,m.groups()); return _decimal(2*(a+b) if mode == "rectangle_perimeter" else a*b)
    if mode == "cuboid_volume":
        m = match(r"长方体长"+n+r"厘米，宽"+n+r"厘米，高"+n+r"厘米，体积是多少立方厘米[?？]")
        if m and all(0 < Decimal(x) <= 100 for x in m.groups()):
            a,b,c = map(Decimal,m.groups()); return _decimal(a*b*c)
    if mode == "fraction_percentage":
        m = match(r"把分数(\+?\d+)/(\d+)化成百分数是多少[?？]")
        if m and 1 <= int(m[2]) <= 100 and 0 <= int(m[1]) <= int(m[2]):
            v = Fraction(int(m[1]),int(m[2]))*100
            if v.denominator in {1,2,4,5,10,20,25,50,100}: return _decimal(Decimal(v.numerator)/Decimal(v.denominator))+"%"
    if mode == "ratio_distribution":
        m = match(r"把(\d+)个物品按(\d+)[:：](\d+)分给甲和乙，甲得到多少个[?？]")
        if m:
            total,a,b = map(int,m.groups())
            if 1 <= a <= 20 and 1 <= b <= 20 and 1 <= total <= 1000 and total*a%(a+b)==0: return str(total*a//(a+b))
    if mode == "circle_measure":
        m = match(r"圆的半径是"+n+r"厘米，圆周率取3.14，(面积是多少平方厘米|周长是多少厘米)[?？]")
        if m and 0 < Decimal(m[1]) <= 100:
            radius=Decimal(m[1]); return _decimal(Decimal('3.14')*(radius*radius if m[2].startswith('面积') else 2*radius))
    if mode == "word_relation":
        m = match(r"[“\"](.{1,8})[”\"]的(近义词|反义词)是什么[?？]")
        if m and m[1] in WORD_RELATIONS[m[2]]: return WORD_RELATIONS[m[2]][m[1]]
    if mode == "sentence_punctuation":
        m = match(r"给句子选择句末标点[:：]([\u3400-\u9fff]{3,30})")
        if m:
            s=m[1]
            if s.endswith(("吗","呢")) or any(q in s for q in ("哪里","什么","几时","多少","为什么")): return "？"
            if s.startswith("多么") or s.endswith(("真美啊","真好啊")): return "！"
            if re.fullmatch(r"[\u3400-\u9fff]{1,6}(?:在|正在|喜欢|看见|有)[\u3400-\u9fff]{1,20}",s): return "。"
    if mode == "explicit_fact":
        m = match(r"短文[:：]"+han+r"在"+han+r"去了"+han+r"。问题[:：]"+han+r"在什么时候去了"+han+r"[?？]")
        if m and m[1]==m[4] and m[3]==m[5]: return m[2]
        m = match(r"短文[:：]"+han+r"在"+han+r"去了"+han+r"。问题[:：]"+han+r"在"+han+r"去了哪里[?？]")
        if m and m[1]==m[4] and m[2]==m[5]: return m[3]
    if mode == "connective":
        m = match(r"选择关联词[:：]____"+han+r"，(所以|但是|就)"+han+r"。")
        if m: return {"所以":"因为","但是":"虽然","就":"如果"}[m[2]]
    if mode == "paragraph_structure":
        m = match(r"判断段落结构[:：](.{6,150})")
        if m:
            sentences=[s for s in m[1].split('。') if s]
            if len(sentences)>=2 and sentences[0].startswith('总的来说,') and all('总的来说' not in x for x in sentences[1:]): return '总分'
            if len(sentences)>=2 and sentences[-1].startswith('总的来说,') and all('总的来说' not in x for x in sentences[:-1]): return '分总'
    if mode == "sentence_revision":
        m = match(r"修改不恰当的表达[:：](.{2,20})")
        if m and m[1] in REVISIONS: return REVISIONS[m[1]]
    if mode == "conditional_inference":
        m = match(r"短文[:：]如果"+han+r"，"+han+r"就"+han+r"。今天"+han+r"。问题[:：]"+han+r"会做什么[?？]")
        if m and m[1]==m[4] and m[2]==m[5]: return m[3]
    if mode == "simile":
        m=match(r"判断修辞[:：]"+han+r"像"+han+r"。")
        literal={"月亮","太阳","星星","云朵","雪花","雨丝","湖面","露珠","树叶","花朵","小河","瀑布","彩虹","草地","麦田","灯光","眼睛"}
        figures={"小船","火球","宝石","棉花","蝴蝶","银线","镜子","珍珠","手掌","笑脸","丝带","白布","彩桥","地毯","海洋","星星"}
        if m and m[1] in literal and m[2] in figures and m[1]!=m[2]: return "比喻"
    if mode == "explanation_method":
        m=match(r"判断说明方法[:：](.{4,150})")
        if m:
            s=m[1]
            if s.startswith("例如,") and not re.search(r"\d",s): return '举例子'
            if re.fullmatch(r"[\u3400-\u9fff]{2,12}(?:高|长|重|有|宽)\d+(?:\.\d+)?(?:米|厘米|千克|个|片|只)。(?:)?",s): return '列数字'
    if mode == "explicit_cause":
        m=match(r"短文[:：]因为"+han+r"，所以"+han+r"。问题[:：]"+han+r"为什么"+han+r"[?？]")
        if m and m[2]==m[3]+m[4]: return m[1]
    if mode == "quantified_evidence":
        m=match(r"观点[:：]所有种子都发芽了。事实[:：]一共(\d+)粒种子，有(\d+)粒发芽。事实是否支持观点[?？]")
        if m and 1<=int(m[1])<=1000 and 0<=int(m[2])<=int(m[1]): return '支持' if m[1]==m[2] else '不支持'
    if mode == "combined_facts":
        m=match(r"短文[:：]"+han+r"读了(\d+)页书，"+han+r"读了(\d+)页书。问题[:：]两人一共读了多少页书[?？]")
        if m and m[1]!=m[3] and 1<=int(m[2])<=100 and 1<=int(m[4])<=100: return str(int(m[2])+int(m[4]))
    if mode == "polite_response":
        m=match(r"选择得体表达，情境[:：](.{2,12})")
        if m and m[1] in POLITE_RESPONSES: return POLITE_RESPONSES[m[1]]
    if mode == "english_vocabulary":
        m=match(r"选择英语词语[:：]([\u3400-\u9fff]{1,8})")
        if m and m[1] in ENGLISH_VOCABULARY[skill_id]: return ENGLISH_VOCABULARY[skill_id][m[1]]
    if mode == "can_verb":
        m=match(r"填空[:：](I|You|He|She|We|They) can(?:'t)? ____ \(([a-z]+)\)\.")
        if m and m[2] in VERBS: return m[2]
    if mode in {"present_simple","present_tense","past_future"}:
        m=match(r"填空[:：](I|You|He|She|We|They) ____ \(([a-z]+)\) (every day|now|yesterday|tomorrow)\.")
        if m and m[2] in VERBS:
            who,verb,time=m.groups(); singular=who in {'He','She'}
            if mode in {'present_simple','present_tense'} and time=='every day': return VERBS[verb][0] if singular else verb
            if mode=='present_tense' and time=='now': return ('am' if who=='I' else 'is' if singular else 'are')+' '+VERBS[verb][1]
            if mode=='past_future' and time=='yesterday': return VERBS[verb][2]
            if mode=='past_future' and time=='tomorrow': return 'will '+verb
    if mode == 'self_information':
        m=match(r"My name is "+name+r"\. What is my name\?")
        if m: return m[1]
        m=match(r"I am (\d+) years old\. How old am I\?")
        if m and 1<=int(m[1])<=18: return m[1]
    if mode == 'english_fact':
        m=match(name+r" is at (the [a-z]+)\. Where is "+name+r"\?")
        if m and m[1]==m[3] and m[2] in {'the park','the school','the library','the shop','the zoo','the farm','the beach','the station','the playground','the museum','the hospital','the cinema','the market','the pool','the garden','the lake'}: return m[2]
    if mode == 'clock_order':
        m=match(name+r" starts at (\d{2}):(\d{2})\. "+name+r" starts at (\d{2}):(\d{2})\. Who starts earlier\?")
        if m and m[1]!=m[4]:
            a,b=int(m[2])*60+int(m[3]),int(m[5])*60+int(m[6])
            if all(0<=int(m[i])<24 for i in (2,5)) and all(0<=int(m[i])<60 for i in (3,6)) and a!=b: return m[1] if a<b else m[4]
    if mode == 'wh_word':
        m=match(r"填空[:：]____ is "+name+r"\? (He|She) is (at [a-z ]+|a teacher|a student)\.")
        if m: return 'Where' if m[3].startswith('at ') else 'Who'
    if mode == 'there_be':
        m=match(r"填空[:：]There ____ (\d+) (books|rulers|pencils|chairs|desks|pens) on the desk\.")
        if m and 2<=int(m[1])<=100: return 'are'
        m=match(r"填空[:：]There ____ 1 (book|ruler|pencil|chair|desk|pen) on the desk\.")
        if m: return 'is'
    if mode == 'height_comparison':
        m=match(name+r" is (\d+) cm tall\. "+name+r" is (\d+) cm tall\. Who is taller\?")
        if m and m[1]!=m[3] and 50<=int(m[2])<=200 and 50<=int(m[4])<=200 and m[2]!=m[4]: return m[1] if int(m[2])>int(m[4]) else m[3]
    if mode == 'english_cause':
        m=match(name+r" stays home because (it is raining|it is snowing|it is windy|it is cold|it is hot)\. Why does "+name+r" stay home\?")
        if m and m[1]==m[3]: return m[2]
    raise ValueError("public question is outside the sealed objective grammar")


def validate_objective_question(grade_code: str, subject: str, skill_id: str, question: Mapping, difficulty_code: str = "standard") -> str:
    policy = objective_question_policy(grade_code, subject, skill_id, difficulty_code)
    expected = solve_objective_question(grade_code, subject, skill_id, str(question.get("prompt") or ""), difficulty_code)
    question_type = question.get('type')
    if question_type not in policy['allowedQuestionTypes']:
        raise ValueError('assessment type is closed for this skill authority')
    normalize = lambda value: _text(value).casefold().replace(' ', '')
    if question_type == 'single_choice':
        matches = [c.get('id') for c in question.get('choices', []) if isinstance(c,Mapping) and normalize(c.get('label'))==normalize(expected)]
        if len(matches)!=1 or question.get('answer')!=matches[0]: raise ValueError('model choice disagrees with Host solution')
    elif question_type == 'exact_text':
        if normalize(question.get('answer'))!=normalize(expected): raise ValueError('model text disagrees with Host solution')
    elif question_type == 'numeric':
        try:
            if Decimal(str(question.get('answer')))!=Decimal(expected): raise ValueError('model numeric answer disagrees with Host solution')
            value,_=bounded_numeric_ast(str(question.get('verificationExpression') or ''),mode='derived_measurement')
            if value!=Fraction(expected): raise ValueError('numeric expression disagrees with Host solution')
        except (InvalidOperation,TypeError,ZeroDivisionError) as exc: raise ValueError('invalid numeric solution') from exc
    else:
        raise ValueError('assessment type is closed for this authority')
    return expected


def objective_question_policy(grade_code: str, subject: str, skill_id: str, difficulty_code: str = "standard") -> dict:
    from content.formal_difficulty_policy import difficulty_spec
    policy = _legacy_question_policy(grade_code, subject, skill_id)
    mode, example, complexity = difficulty_spec(grade_code, subject, skill_id, difficulty_code, policy['mode'], policy['publicPromptExample'])
    policy.update(mode=mode, publicPromptExample=example, difficultyCode=difficulty_code, complexity=complexity)
    if example.startswith('辨析任务'):
        policy['allowedQuestionTypes'] = ['exact_text', 'single_choice']
    if mode == 'zh_context_relation':
        from content.formal_difficulty_policy import CONTEXT_WORDS, DIFFICULTY_CODES
        level = DIFFICULTY_CODES.index(difficulty_code)
        policy['contextInventory'] = [list(row) for row in CONTEXT_WORDS[level*6:(level+1)*6]]
    policy['promptPolicy'] = ('Use the exact public grammar with fresh bounded operands, names and evidence. '
        'Every question must satisfy this explicit difficulty band; variant ordinal never determines difficulty. '
        'For chains preserve each link and the exact evidence count. For sources use a unique joint answer and distractors in every source. '
        'Do not simplify multi-step tasks to direct recall. Preserve the literal answer-format instruction. Host independently solves each prompt.')
    return policy


def solve_objective_question(grade_code: str, subject: str, skill_id: str, prompt: str, difficulty_code: str = "standard") -> str:
    from content.formal_difficulty_policy import solve_banded_question
    legacy = _legacy_question_policy(grade_code, subject, skill_id)
    return solve_banded_question(grade_code, subject, skill_id, difficulty_code, prompt, _solve_legacy_objective_question, legacy['mode'])
