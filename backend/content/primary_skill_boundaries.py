from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping


SUPPORTED_PRIMARY_SUBJECTS = ("chinese", "math", "english")
PRIMARY_CURRICULUM_VERSION = "mira.primary.2026-fall.v1"
CONTENT_VALIDATION_CONTRACT_VERSION = (
    "mira.learning.primary-1-content-validation.v1"
)
PRIMARY_ONE_CONTENT_DATASET_SHA256 = (
    "1ca7707b75f9d55c775201676dfc234c496e1655b048494517ac2aea8736b63d"
)
SUBJECT_LANGUAGE_POLICY_VERSION = "mira.learning.subject-language-policy.v1"
PRIMARY_ONE_CANARY_MANIFEST_VERSION = "mira.learning.primary-1-canary.v1"

_PRIMARY_ONE_CONTENT_CONTRACT_PATH = Path(__file__).with_name(
    "primary_1_content_validation.v1.json"
)
_PRIMARY_ONE_SUBJECT_LANGUAGES = (
    ("chinese", 1, "zh-CN", "zh-CN"),
    ("math", 2, "zh-CN", "zh-CN"),
    ("english", 3, "zh-CN", "en-US"),
)
_PRIMARY_ONE_BOUNDARY_INVENTORY_KEYS = {
    "pinyin_syllables": (
        "chinese.pinyin_vowels_aoe.v1",
        "chinese.guidance_characters.v1",
    ),
    "pinyin_initials_syllables": (
        "chinese.initials.v1",
        "chinese.pinyin_vowels_aoe.v1",
        "chinese.simple_syllables.v1",
    ),
    "characters_words": ("chinese.common_characters_radicals_words.v1",),
    "simple_sentences": ("chinese.simple_sentence_punctuation.v1",),
    "number_sense_20": ("math.number_sense_20_ranges.v1",),
    "addition_subtraction_20": ("math.addition_subtraction_20_ast.v1",),
    "shapes_position": ("math.shapes_position_relations.v1",),
    "letters_sounds": ("english.letter_case_initial_sound.v1",),
    "greetings": ("english.greeting_patterns.v1",),
    "numbers_colors": ("english.numbers_1_20_colors.v1",),
}
_PRIMARY_ONE_INVENTORY_KINDS = {
    "chinese.pinyin_vowels_aoe.v1": "pinyin_vowel_rules",
    "chinese.guidance_characters.v1": "character_allowlist",
    "chinese.initials.v1": "pinyin_initial_rules",
    "chinese.simple_syllables.v1": "pinyin_syllable_rules",
    "chinese.common_characters_radicals_words.v1": (
        "character_radical_word_relation_rules"
    ),
    "chinese.simple_sentence_punctuation.v1": "sentence_language_rules",
    "math.number_sense_20_ranges.v1": "number_sense_rules",
    "math.addition_subtraction_20_ast.v1": "arithmetic_ast_rules",
    "math.shapes_position_relations.v1": "shape_position_rules",
    "english.letter_case_initial_sound.v1": "letter_initial_sound_rules",
    "english.greeting_patterns.v1": "greeting_phrase_rules",
    "english.numbers_1_20_colors.v1": "number_color_rules",
}


@dataclass(frozen=True)
class PrimarySkillBoundary:
    grade_code: str
    subject: str
    skill_id: str
    skill_title: str
    learning_objectives: tuple[str, ...]
    allowed_content: tuple[str, ...]
    excluded_content: tuple[str, ...]
    prerequisite_skills: tuple[str, ...] = ()

    @property
    def curriculum_version(self) -> str:
        return PRIMARY_CURRICULUM_VERSION

    @property
    def boundary_version(self) -> str:
        """Content-addressed boundary version persisted with generated courses.

        A curriculum edit therefore creates a new version even when the stable
        progression node id stays unchanged. Historical mastery can keep using
        ``skill_id`` while catalog publication can reject stale course content.
        """

        payload = {
            "gradeCode": self.grade_code,
            "subject": self.subject,
            "skillId": self.skill_id,
            "skillTitle": self.skill_title,
            "learningObjectives": list(self.learning_objectives),
            "allowedContent": list(self.allowed_content),
            "excludedContent": list(self.excluded_content),
            "prerequisiteSkills": list(self.prerequisite_skills),
        }
        digest = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        return f"{PRIMARY_CURRICULUM_VERSION}:{self.skill_id}:{digest}"

    def to_catalog_payload(self) -> dict[str, object]:
        return {
            "gradeCode": self.grade_code,
            "subject": self.subject,
            "curriculumVersion": self.curriculum_version,
            "boundaryVersion": self.boundary_version,
            **self.to_openmaic_payload(),
        }

    def to_openmaic_payload(self) -> dict[str, object]:
        return {
            "skillId": self.skill_id,
            "skillTitle": self.skill_title,
            "learningObjectives": list(self.learning_objectives),
            "allowedContent": list(self.allowed_content),
            "excludedContent": list(self.excluded_content),
            "prerequisiteSkills": list(self.prerequisite_skills),
            "language": "zh-CN",
            "estimatedMinutes": 10,
        }

    def to_validation_payload(self) -> dict[str, object]:
        return {
            "gradeCode": self.grade_code,
            "subject": self.subject,
            **self.to_openmaic_payload(),
            "outcomeMode": "scored_deterministic",
            "sessionKind": "lesson",
            "questionCount": 5,
        }


def _skill(
    grade: int,
    subject: str,
    skill_id: str,
    title: str,
    objectives: tuple[str, ...],
    allowed: tuple[str, ...],
    excluded: tuple[str, ...],
    prerequisites: tuple[str, ...] = (),
) -> PrimarySkillBoundary:
    return PrimarySkillBoundary(
        grade_code=f"primary_{grade}",
        subject=subject,
        skill_id=skill_id,
        skill_title=title,
        learning_objectives=objectives,
        allowed_content=allowed,
        excluded_content=excluded,
        prerequisite_skills=prerequisites,
    )


def _content_contract_hash(contract: Mapping[str, object]) -> str:
    payload = dict(contract)
    payload.pop("datasetSha256", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sealed_simple_sentence_boundary_scope(
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    with _PRIMARY_ONE_CONTENT_CONTRACT_PATH.open(
        "r", encoding="utf-8"
    ) as handle:
        contract = json.load(handle)
    if (
        contract.get("datasetSha256") != PRIMARY_ONE_CONTENT_DATASET_SHA256
        or _content_contract_hash(contract)
        != PRIMARY_ONE_CONTENT_DATASET_SHA256
    ):
        raise ValueError("pinned primary-one content dataset mismatch")

    rules = contract["inventories"][
        "chinese.simple_sentence_punctuation.v1"
    ]["rules"]
    grammar_version = rules["predicateGrammarVersion"]
    inventory_names = (
        "aspectMarkers",
        "intransitivePredicates",
        "actionPhrases",
        "statePredicates",
        "identityMarkers",
        "descriptionMarkers",
        "markerBearingSubjectNouns",
        "identityComplements",
    )
    if not isinstance(grammar_version, str) or not grammar_version:
        raise ValueError("sealed predicate grammar version mismatch")
    inventories: dict[str, tuple[str, ...]] = {}
    for name in inventory_names:
        values = rules[name]
        if (
            not isinstance(values, list)
            or not values
            or any(not isinstance(item, str) or not item for item in values)
        ):
            raise ValueError(f"sealed sentence inventory {name} mismatch")
        inventories[name] = tuple(values)

    aspect_text = "、".join(inventories["aspectMarkers"])
    objectives = (
        "判断主语、谓语和补语形状是否完整",
        "仅用密封有限谓语组织陈述句和问句",
    )
    allowed = (
        f"谓语语法版本：{grammar_version}",
        "句型：主语+谓语；主语+谓语+补语",
        "不及物谓语（可接"
        f"{aspect_text}）：{'、'.join(inventories['intransitivePredicates'])}",
        "完整动作短语（可接"
        f"{aspect_text}）：{'、'.join(inventories['actionPhrases'])}",
        f"状态谓语：{'、'.join(inventories['statePredicates'])}",
        f"判断标记：{'、'.join(inventories['identityMarkers'])}",
        f"描述标记：{'、'.join(inventories['descriptionMarkers'])}",
        "含语法标记的完整主语名词："
        f"{'、'.join(inventories['markerBearingSubjectNouns'])}",
        f"身份补语：{'、'.join(inventories['identityComplements'])}",
        "陈述句用句号，问句用问号",
    )
    return objectives, allowed


(
    _PRIMARY_ONE_SIMPLE_SENTENCE_OBJECTIVES,
    _PRIMARY_ONE_SIMPLE_SENTENCE_ALLOWED_CONTENT,
) = _sealed_simple_sentence_boundary_scope()


# These are curriculum boundaries, not questions or answer keys. They tell the
# generator what may be taught while leaving every concrete lesson and item to
# the OpenMAIC generation pipeline.
PRIMARY_SKILL_BOUNDARIES = (
    _skill(1, "math", "number_sense_20", "20以内数感", ("比较20以内数的大小", "理解数的组成与顺序"), ("数数", "数位雏形", "大小比较"), ("负数", "乘除法", "分数", "小数")),
    _skill(1, "math", "addition_subtraction_20", "20以内加减法", ("正确计算20以内加减法", "用加减法解决一步问题"), ("凑十", "拆分", "一步口算", "简单生活情境"), ("连加连减超过两步", "乘除法", "未知数方程")),
    _skill(1, "math", "shapes_position", "图形与位置", ("辨认常见平面图形", "使用上下左右描述位置"), ("圆形", "三角形", "正方形", "长方形", "位置词"), ("面积公式", "周长公式", "立体展开图")),
    _skill(2, "math", "number_operations_100", "100以内数与运算", ("理解两位数的数位", "正确完成100以内加减法"), ("十位和个位", "进位加法", "退位减法", "估算"), ("三位数运算", "负数", "小数")),
    _skill(2, "math", "multiplication_division_intro", "乘除法初步", ("理解乘法是相同加数的和", "理解平均分与除法"), ("2至9的乘法", "平均分", "包含除"), ("多位数乘除", "分数除法", "小数乘除")),
    _skill(2, "math", "measurement_time", "长度、时间与生活测量", ("选择合适长度单位", "读取整时与半时", "比较简单测量结果"), ("厘米和米", "整时半时", "生活测量"), ("速度公式", "单位复合换算", "体积")),
    _skill(3, "math", "multi_digit_operations", "多位数基础运算", ("完成三位数加减", "完成一位数乘除的基础计算"), ("三位数加减", "一位数乘法", "有余数除法"), ("小数乘除", "负数运算", "代数方程")),
    _skill(3, "math", "fractions_intro", "分数初步", ("理解几分之一和几分之几", "比较同分母简单分数"), ("整体等分", "分数读写", "同分母比较"), ("异分母通分", "分数乘除", "复杂约分")),
    _skill(3, "math", "perimeter_measurement", "周长与测量", ("理解周长含义", "计算长方形和正方形周长"), ("封闭图形周长", "长度单位", "长方形正方形"), ("面积公式", "圆周率", "不规则曲线测量")),
    _skill(4, "math", "large_numbers_operations", "大数认识与整数运算", ("理解万以上数位", "运用运算顺序完成整数计算"), ("大数读写", "近似数", "三位数乘两位数", "除数两位数"), ("负数复杂运算", "小数乘除", "代数证明")),
    _skill(4, "math", "decimals_intro", "小数意义与加减", ("理解小数的数位意义", "完成简单小数加减"), ("十分位百分位", "小数比较", "小数加减"), ("循环小数", "小数乘除", "科学记数法")),
    _skill(4, "math", "area_geometry", "面积与几何关系", ("计算长方形正方形面积", "辨认平行与垂直"), ("面积单位", "长方形正方形面积", "平行垂直"), ("圆面积", "立体几何", "坐标证明")),
    _skill(5, "math", "fractions_operations", "分数意义与加减", ("理解约分通分", "完成同分母和简单异分母加减"), ("因数倍数", "约分", "通分", "分数加减"), ("分数乘除", "复杂代数分式")),
    _skill(5, "math", "decimals_equations", "小数运算与简易方程", ("完成小数乘除", "用简易方程表示数量关系"), ("小数乘除", "字母表示数", "一步两步方程"), ("二元方程", "负指数", "函数")),
    _skill(5, "math", "volume_statistics", "体积与统计", ("计算长方体正方体体积", "读懂简单统计图表"), ("体积单位", "长方体正方体", "平均数", "折线统计图"), ("圆柱圆锥", "概率推断", "标准差")),
    _skill(6, "math", "fraction_ratio_percentage", "分数、比与百分数", ("理解比和百分数", "在分数小数百分数之间转换"), ("比的意义", "百分率", "折扣", "分数小数互化"), ("复利", "三角比", "复杂比例证明")),
    _skill(6, "math", "proportional_reasoning", "比例与应用", ("判断正反比例的简单关系", "解决比例尺和按比例分配问题"), ("比例基本性质", "比例尺", "按比例分配", "简单正反比例"), ("函数图像证明", "复合比例", "微积分")),
    _skill(6, "math", "circle_solid_geometry", "圆与立体图形", ("计算圆的周长和面积", "理解圆柱的表面积与体积"), ("圆周率取3.14", "圆周长面积", "圆柱表面积体积"), ("圆锥体积证明", "球体公式", "解析几何")),

    # Grade-one Chinese must start with a deliberately narrow pinyin lesson.
    # Keep the historical ``pinyin_syllables`` node id so existing mastery and
    # generated-course rows continue to participate in progression, but do not
    # let the first lesson jump to initials, radicals, or character recognition.
    _skill(
        1,
        "chinese",
        "pinyin_syllables",
        "单韵母 a、o、e",
        ("能看口形认读单韵母 a、o、e", "能听辨 a、o、e 的基本读音"),
        ("单韵母 a、o、e", "a、o、e 的口形提示", "a、o、e 的听辨与跟读"),
        ("声母", "整体认读音节", "偏旁部首", "生字认读", "多音字", "方言知识"),
    ),
    _skill(
        1,
        "chinese",
        "pinyin_initials_syllables",
        "声母与简单音节",
        ("分辨常见声母", "用已学韵母拼合简单音节"),
        ("常见声母", "简单两拼音节", "四声初步"),
        ("偏旁部首", "生字默写", "复杂三拼音节", "多音字复杂语境"),
        ("pinyin_syllables",),
    ),
    _skill(1, "chinese", "characters_words", "汉字与词语", ("辨认常用汉字", "理解基础偏旁和词语搭配"), ("常用独体字", "基础偏旁", "反义词", "量词"), ("生僻字", "古汉语", "复杂成语辨析"), ("pinyin_initials_syllables",)),
    _skill(1, "chinese", "simple_sentences", "完整句子", _PRIMARY_ONE_SIMPLE_SENTENCE_OBJECTIVES, _PRIMARY_ONE_SIMPLE_SENTENCE_ALLOWED_CONTENT, ("复句分析", "修辞术语", "长段落写作"), ("characters_words",)),
    _skill(2, "chinese", "word_relations", "词语关系", ("辨认近义词反义词", "选择恰当动词和量词"), ("近义词", "反义词", "词语搭配", "常用量词"), ("文言实词", "生僻成语", "抽象语义学")),
    _skill(2, "chinese", "sentence_order_punctuation", "句序与标点", ("按时间因果排列句子", "正确使用常见句末标点"), ("时间顺序", "因果关系", "句号问号感叹号"), ("复杂分号用法", "病句术语", "长篇写作")),
    _skill(2, "chinese", "short_reading", "短文信息提取", ("从原创短文提取人物时间地点", "按短文顺序排列事件"), ("原创短文不超过120字", "显性事实", "事件顺序"), ("教材课文复刻", "开放式赏析", "隐晦象征")),
    _skill(3, "chinese", "context_words", "联系语境理解词语", ("根据上下文解释词义", "辨认常见感情色彩"), ("语境释义", "近义替换", "常用成语"), ("文言词义", "作者生平知识", "教材原文")),
    _skill(3, "chinese", "connect_sentences", "关联词与句段连贯", ("辨认因果转折条件关系", "排列连贯短段"), ("因为所以", "虽然但是", "如果就", "三句以内排序"), ("复杂多重复句", "语法学术语", "教材原文")),
    _skill(3, "chinese", "reading_evidence", "阅读事实与证据", ("从原创短文定位事实", "用明确证据完成客观判断"), ("原创短文不超过180字", "时间地点人物", "明确因果"), ("主观赏析", "作者意图猜测", "教材课文复刻")),
    _skill(4, "chinese", "paragraph_structure", "段落结构", ("识别总分和因果结构", "概括段落明确主旨"), ("原创段落", "中心句", "总分结构", "过渡句"), ("整篇名著", "开放式鉴赏", "教材原文")),
    _skill(4, "chinese", "sentence_revision", "句子修改", ("发现常见搭配和成分问题", "选择清楚准确的表达"), ("搭配不当", "成分残缺", "语序问题", "重复啰嗦"), ("存在争议的语病", "专业语言学分析")),
    _skill(4, "chinese", "reading_inference", "阅读推断", ("基于文中明确信息作简单推断", "区分事实与合理推断"), ("原创短文不超过220字", "单步推断", "证据定位"), ("脱离文本猜测", "主观价值评分", "教材原文")),
    _skill(5, "chinese", "meaning_expression", "词句表达效果", ("理解常见修辞的明确作用", "比较具体与笼统表达"), ("比喻拟人", "关键词作用", "明确语境"), ("唯一化主观审美", "文学流派", "教材原文")),
    _skill(5, "chinese", "nonfiction_reading", "说明性文本阅读", ("提取说明对象与关键特征", "理解顺序和简单说明方法"), ("原创说明文不超过260字", "时间空间逻辑顺序", "举例列数字"), ("专业科学细节", "开放式评价", "教材原文")),
    _skill(5, "chinese", "narrative_logic", "叙事线索与因果", ("梳理人物行动和结果", "根据证据判断直接原因"), ("原创叙事不超过260字", "行动结果", "时间线", "明确人物关系"), ("隐喻象征", "作者生平", "教材原文")),
    _skill(6, "chinese", "argument_evidence", "观点与证据", ("区分观点与事实", "判断证据是否直接支持观点"), ("短小原创议论片段", "事实证据", "理由", "明确结论"), ("政治立场评价", "复杂逻辑谬误术语", "教材原文")),
    _skill(6, "chinese", "integrated_reading", "综合阅读", ("整合多处显性信息", "概括结构和关键信息"), ("原创文本不超过320字", "跨句信息", "结构概括", "客观选择"), ("开放式文学鉴赏", "唯一化主观答案", "教材原文")),
    _skill(6, "chinese", "language_application", "语言运用", ("在具体情境选择得体表达", "修改常见病句和标点"), ("通知提示语", "简短交流", "常见病句", "标点"), ("公文专业格式", "复杂修辞创作评分")),

    _skill(1, "english", "letters_sounds", "Letters and Sounds", ("辨认常见英文字母", "匹配简单字母与单词首音"), ("26个字母", "大小写辨认", "常见首字母"), ("音标书写", "复杂自然拼读规则", "长句语法")),
    _skill(1, "english", "greetings", "Greetings", ("理解并回应常见问候", "说出简单姓名信息"), ("hello", "good morning", "how are you", "my name is"), ("过去时", "从句", "长篇阅读")),
    _skill(1, "english", "numbers_colors", "Numbers and Colors", ("辨认1至20英文数字", "理解常见颜色词"), ("one to twenty", "basic colors", "simple matching"), ("序数词复杂用法", "大数", "抽象颜色表达")),
    _skill(2, "english", "family_people", "Family and People", ("理解常见家庭成员词", "使用简单人物指代"), ("father mother sister brother", "he she", "this is"), ("复杂亲属关系", "所有格从句", "过去时")),
    _skill(2, "english", "school_objects", "School Objects", ("辨认常见学习用品", "使用this和that的固定句型"), ("book ruler pencil schoolbag desk", "this is", "that is"), ("复数所有格", "被动语态", "复杂方位")),
    _skill(2, "english", "actions_abilities", "Actions and Abilities", ("理解常见动作词", "使用can和can't表达能力"), ("run read sing swim fly", "can plus verb", "can't plus verb"), ("完成时", "情态动词细微差异", "从句")),
    _skill(3, "english", "self_introduction", "Self-introduction", ("用固定句型介绍姓名年龄喜好", "理解相应简单问句"), ("name age likes city", "I am", "I like", "How old"), ("复杂时态", "长篇写作", "从句")),
    _skill(3, "english", "daily_routines", "Daily Routines", ("理解常见作息动词", "使用一般现在时固定语序"), ("get up", "have breakfast", "go to school", "go to bed", "third person singular basics"), ("复杂频率副词", "完成时", "被动语态")),
    _skill(3, "english", "short_reading", "Short Reading", ("从原创短文提取人物时间地点", "理解简单明确事实"), ("original text under 80 words", "explicit facts", "present tense"), ("copyrighted textbook passages", "open literary analysis", "rare vocabulary")),
    _skill(4, "english", "time_schedules", "Time and Schedules", ("读懂常见时间表达", "理解before和after"), ("clock time", "school timetable", "before after", "at plus time"), ("时区换算", "复杂将来时", "长篇日程")),
    _skill(4, "english", "questions_answers", "Questions and Answers", ("区分who what where when", "匹配简单问答"), ("wh questions", "short answers", "people places time things"), ("间接疑问句", "从句", "复杂语法术语")),
    _skill(4, "english", "descriptions", "People and Places", ("理解常见外貌地点描述", "使用基础形容词和there be"), ("basic adjectives", "there is there are", "place words"), ("形容词从句", "文学描写", "生僻词")),
    _skill(5, "english", "present_tenses", "Present Tenses", ("根据时间提示区分一般现在时和现在进行时", "选择正确动词形式"), ("every day", "usually", "now", "look", "am is are plus ing"), ("完成进行时", "被动语态", "复杂从句")),
    _skill(5, "english", "comparisons", "Comparisons", ("正确使用基础比较级最高级", "在明确语境比较事物"), ("-er", "more", "the -est", "than", "three-item comparisons"), ("不规则罕见形式", "复杂倍数表达", "从句")),
    _skill(5, "english", "informational_reading", "Informational Reading", ("从原创说明短文提取事实", "理解简单因果和顺序"), ("original text under 130 words", "explicit cause and effect", "sequence words"), ("copyrighted passages", "subjective interpretation", "advanced science terms")),
    _skill(6, "english", "past_future", "Past and Future", ("根据时间词选择一般过去时或一般将来时", "辨认常见规则和不规则过去式"), ("yesterday", "last week", "tomorrow", "will", "be going to", "common past forms"), ("过去完成时", "虚拟语气", "复杂从句")),
    _skill(6, "english", "grammar_in_context", "Grammar in Context", ("在短句语境选择代词介词连词", "保持主谓一致"), ("pronouns", "common prepositions", "and but because", "subject verb agreement"), ("倒装", "虚拟语气", "复杂从句分析")),
    _skill(6, "english", "reading_evidence", "Reading with Evidence", ("整合原创短文中的明确事实", "根据文本作单步推断"), ("original text under 180 words", "explicit evidence", "single-step inference", "context vocabulary"), ("copyrighted passages", "open literary criticism", "rare idioms")),
)


def boundaries_for(grade_code: str, subject: str) -> tuple[PrimarySkillBoundary, ...]:
    grade = str(grade_code or "").strip()
    subject_code = str(subject or "").strip()
    return tuple(
        boundary
        for boundary in PRIMARY_SKILL_BOUNDARIES
        if boundary.grade_code == grade and boundary.subject == subject_code
    )


def boundary_for(
    grade_code: str,
    subject: str,
    *,
    index: int = 0,
) -> PrimarySkillBoundary:
    candidates = boundaries_for(grade_code, subject)
    if not candidates:
        raise ValueError("unsupported primary grade or subject")
    return candidates[int(index) % len(candidates)]


def _unique_strings(value: object, field: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"{field} must contain unique non-empty strings")
    return value


def _exact_mapping_keys(
    value: object,
    expected: set[str],
    field: str,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"{field} fields mismatch")
    return value


def _require_authority_ordinal(value: object, field: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{field} must be an integer")
    return value


def _authority_ordinal(value: object, field: str, expected: int) -> int:
    ordinal = _require_authority_ordinal(value, field)
    if ordinal != expected:
        raise ValueError(f"{field} mismatch")
    return ordinal


def _validate_authority_ordinal_types(contract: Mapping[str, object]) -> None:
    """Reject Python values that compare equal to integers before hash checks."""

    subjects = contract.get("subjects")
    if isinstance(subjects, list):
        for policy in subjects:
            if not isinstance(policy, Mapping):
                continue
            if "subjectOrdinal" in policy:
                _require_authority_ordinal(
                    policy["subjectOrdinal"],
                    "subjectOrdinal",
                )
            boundaries = policy.get("boundaries")
            if isinstance(boundaries, list):
                for boundary in boundaries:
                    if (
                        isinstance(boundary, Mapping)
                        and "boundaryOrdinal" in boundary
                    ):
                        _require_authority_ordinal(
                            boundary["boundaryOrdinal"],
                            "boundary ordinal",
                        )

    inventories = contract.get("inventories")
    if isinstance(inventories, Mapping):
        initials = inventories.get("chinese.initials.v1")
        if isinstance(initials, Mapping):
            rules = initials.get("rules")
            if isinstance(rules, Mapping):
                tone_ordinals = rules.get("toneOrdinals")
                if isinstance(tone_ordinals, list):
                    for tone in tone_ordinals:
                        _require_authority_ordinal(
                            tone,
                            "pinyin tone ordinal",
                        )

    canary = contract.get("canaryManifest")
    if isinstance(canary, Mapping):
        targets = canary.get("targets")
        if isinstance(targets, list):
            for target in targets:
                if not isinstance(target, Mapping):
                    continue
                for field in (
                    "subjectOrdinal",
                    "boundaryOrdinal",
                    "variantOrdinal",
                ):
                    if field in target:
                        _require_authority_ordinal(
                            target[field],
                            f"canary {field}",
                        )


def _validate_typed_inventory(key: str, inventory: object) -> None:
    value = _exact_mapping_keys(
        inventory,
        {"schemaVersion", "kind", "rules"},
        f"inventory {key}",
    )
    if value["schemaVersion"] != key:
        raise ValueError(f"inventory {key} schema version mismatch")
    if value["kind"] != _PRIMARY_ONE_INVENTORY_KINDS[key]:
        raise ValueError(f"inventory {key} kind mismatch")
    rules = value["rules"]
    if not isinstance(rules, Mapping) or not rules:
        raise ValueError(f"inventory {key} rules must be a non-empty object")

    kind = value["kind"]
    if kind == "pinyin_vowel_rules":
        typed = _exact_mapping_keys(
            rules,
            {
                "symbols",
                "allowedAssessmentModes",
                "forbiddenTeachingTargets",
            },
            f"inventory {key}.rules",
        )
        symbols = typed["symbols"]
        if not isinstance(symbols, list) or [
            item.get("symbol") for item in symbols
        ] != ["a", "o", "e"]:
            raise ValueError("pinyin vowel inventory must contain exact a/o/e rules")
        for item in symbols:
            _exact_mapping_keys(
                item,
                {"symbol", "mouthShape", "soundCue"},
                "pinyin vowel rule",
            )
        _unique_strings(typed["allowedAssessmentModes"], "allowedAssessmentModes")
        _unique_strings(typed["forbiddenTeachingTargets"], "forbiddenTeachingTargets")
    elif kind == "character_allowlist":
        typed = _exact_mapping_keys(
            rules, {"usage", "characters"}, f"inventory {key}.rules"
        )
        if typed["usage"] != "instruction_only":
            raise ValueError("guidance characters must be instruction_only")
        _unique_strings(typed["characters"], "guidance characters")
    elif kind == "pinyin_initial_rules":
        typed = _exact_mapping_keys(
            rules,
            {"initials", "learnedFinals", "toneOrdinals", "compositionRule"},
            f"inventory {key}.rules",
        )
        if typed["initials"] != [
            "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h",
            "j", "q", "x", "zh", "ch", "sh", "r", "z", "c", "s", "y", "w",
        ]:
            raise ValueError("pinyin initials inventory mismatch")
        if typed["learnedFinals"] != ["a", "o", "e"]:
            raise ValueError("learned pinyin finals mismatch")
        if (
            not isinstance(typed["toneOrdinals"], list)
            or len(typed["toneOrdinals"]) != 4
        ):
            raise ValueError("pinyin tone ordinals mismatch")
        for expected_tone, actual_tone in enumerate(typed["toneOrdinals"], start=1):
            _authority_ordinal(actual_tone, "pinyin tone ordinal", expected_tone)
        if typed["compositionRule"] != "initial_plus_learned_final":
            raise ValueError("pinyin composition rule mismatch")
    elif kind == "pinyin_syllable_rules":
        typed = _exact_mapping_keys(
            rules,
            {"syllables", "maxComponents", "prerequisiteSkill"},
            f"inventory {key}.rules",
        )
        _unique_strings(typed["syllables"], "simple syllables")
        if type(typed["maxComponents"]) is not int or typed["maxComponents"] != 2:
            raise ValueError("pinyin maxComponents must be integer 2")
        if typed["prerequisiteSkill"] != "pinyin_syllables":
            raise ValueError("pinyin syllable prerequisite mismatch")
    elif kind == "character_radical_word_relation_rules":
        typed = _exact_mapping_keys(
            rules,
            {"characters", "radicals", "wordRelations"},
            f"inventory {key}.rules",
        )
        if not isinstance(typed["characters"], list) or len(typed["characters"]) < 12:
            raise ValueError("character inventory must contain at least 12 entries")
        if not isinstance(typed["radicals"], list) or len(typed["radicals"]) < 4:
            raise ValueError("radical inventory must contain at least 4 entries")
        if (
            not isinstance(typed["wordRelations"], list)
            or len(typed["wordRelations"]) < 6
        ):
            raise ValueError("word relation inventory must contain at least 6 entries")
        for item in typed["characters"]:
            character = _exact_mapping_keys(
                item, {"character", "reading", "words"}, "character rule"
            )
            _unique_strings(character["words"], "character words")
        for item in typed["radicals"]:
            radical = _exact_mapping_keys(
                item, {"radical", "meaning", "characters"}, "radical rule"
            )
            _unique_strings(radical["characters"], "radical characters")
        for item in typed["wordRelations"]:
            if not isinstance(item, Mapping) or not item.get("relation"):
                raise ValueError("word relation rule must name its relation")
    elif kind == "sentence_language_rules":
        typed = _exact_mapping_keys(
            rules,
            {
                "sentencePatterns",
                "wordOrderRules",
                "terminalPunctuation",
                "punctuationRules",
                "requiredCompleteness",
                "predicateGrammarVersion",
                "subjectPredicateShapes",
                "aspectMarkers",
                "intransitivePredicates",
                "actionPhrases",
                "statePredicates",
                "identityMarkers",
                "descriptionMarkers",
                "markerBearingSubjectNouns",
                "identityComplements",
            },
            f"inventory {key}.rules",
        )
        if (
            not isinstance(typed["sentencePatterns"], list)
            or not typed["sentencePatterns"]
        ):
            raise ValueError("sentence patterns must be non-empty")
        _unique_strings(typed["wordOrderRules"], "word order rules")
        if typed["terminalPunctuation"] != ["。", "？"]:
            raise ValueError("terminal punctuation mismatch")
        if (
            not isinstance(typed["punctuationRules"], list)
            or not typed["punctuationRules"]
        ):
            raise ValueError("punctuation rules must be non-empty")
        _unique_strings(typed["requiredCompleteness"], "sentence completeness")
        if typed["predicateGrammarVersion"] != (
            "mira.learning.primary-1-simple-sentence-predicate-grammar.v2"
        ):
            raise ValueError("predicate grammar version mismatch")
        expected_shapes = [
            {
                "patternId": "subject_action",
                "predicateInventory": "intransitivePredicates",
                "shape": ["subject", "predicate"],
                "aspectMarkersAllowed": True,
            },
            {
                "patternId": "subject_action",
                "predicateInventory": "actionPhrases",
                "shape": ["subject", "predicate"],
                "aspectMarkersAllowed": True,
            },
            {
                "patternId": "subject_description",
                "predicateInventory": "statePredicates",
                "shape": ["subject", "predicate"],
                "aspectMarkersAllowed": True,
            },
            {
                "patternId": "subject_identity",
                "predicateInventory": "identityMarkers",
                "shape": ["subject", "predicate", "complement"],
                "aspectMarkersAllowed": False,
            },
            {
                "patternId": "subject_description",
                "predicateInventory": "descriptionMarkers",
                "shape": ["subject", "predicate", "complement"],
                "aspectMarkersAllowed": False,
            },
        ]
        if typed["subjectPredicateShapes"] != expected_shapes:
            raise ValueError("subject/predicate/complement shapes mismatch")
        if typed["aspectMarkers"] != ["了", "着", "过"]:
            raise ValueError("sentence aspect markers mismatch")
        predicate_inventory_limits = {
            "intransitivePredicates": 24,
            "actionPhrases": 32,
            "statePredicates": 24,
            "identityMarkers": 4,
            "descriptionMarkers": 8,
            "markerBearingSubjectNouns": 8,
            "identityComplements": 24,
        }
        for inventory_name, maximum_size in predicate_inventory_limits.items():
            values = _unique_strings(
                typed[inventory_name], f"sentence {inventory_name}"
            )
            if len(values) > maximum_size or any(
                re.fullmatch(r"[\u3400-\u9fff]+", value) is None
                for value in values
            ):
                raise ValueError(f"sentence {inventory_name} is not bounded Han text")
        if any(len(value) < 2 for value in typed["actionPhrases"]):
            raise ValueError("sentence action phrases must be complete phrases")
        if any(len(value) != 1 for value in typed["identityMarkers"]):
            raise ValueError("sentence identity markers must be single characters")
        if any(len(value) != 1 for value in typed["descriptionMarkers"]):
            raise ValueError("sentence description markers must be single characters")
        if any(len(value) < 2 for value in typed["markerBearingSubjectNouns"]):
            raise ValueError(
                "sentence marker-bearing subject nouns must be complete nouns"
            )
        if any(len(value) < 2 for value in typed["identityComplements"]):
            raise ValueError("sentence identity complements must be complete nouns")
        if set(typed["intransitivePredicates"]) & set(typed["actionPhrases"]):
            raise ValueError("sentence predicate inventories must be disjoint")
    elif kind == "number_sense_rules":
        typed = _exact_mapping_keys(
            rules,
            {"valueRange", "placeValue", "comparisonRelations", "requiredEvidence"},
            f"inventory {key}.rules",
        )
        if typed["valueRange"] != {"minimum": 0, "maximum": 20, "integerOnly": True}:
            raise ValueError("number-sense value range mismatch")
        place_value = typed["placeValue"]
        if (
            not isinstance(place_value, Mapping)
            or place_value.get("twentyComposition") != {"tens": 2, "ones": 0}
        ):
            raise ValueError("number-sense place-value rules mismatch")
        _unique_strings(typed["comparisonRelations"], "comparison relations")
        _unique_strings(typed["requiredEvidence"], "number-sense evidence")
    elif kind == "arithmetic_ast_rules":
        typed = _exact_mapping_keys(
            rules,
            {
                "allowedNodeTypes",
                "operandRange",
                "resultRange",
                "maximumOperatorDepth",
                "subtractionMustBeNonNegative",
                "requiredIndependentOperations",
            },
            f"inventory {key}.rules",
        )
        if typed["allowedNodeTypes"] != ["integer_literal", "add", "subtract"]:
            raise ValueError("arithmetic AST node allowlist mismatch")
        expected_range = {"minimum": 0, "maximum": 20, "integerOnly": True}
        if (
            typed["operandRange"] != expected_range
            or typed["resultRange"] != expected_range
        ):
            raise ValueError("arithmetic range mismatch")
        if (
            type(typed["maximumOperatorDepth"]) is not int
            or typed["maximumOperatorDepth"] != 1
        ):
            raise ValueError("maximumOperatorDepth must be integer 1")
        if typed["subtractionMustBeNonNegative"] is not True:
            raise ValueError("subtraction must be non-negative")
        if typed["requiredIndependentOperations"] != ["add", "subtract"]:
            raise ValueError("independent operation requirements mismatch")
    elif kind == "shape_position_rules":
        typed = _exact_mapping_keys(
            rules,
            {
                "shapes",
                "positionRelations",
                "rectangleSquareRule",
                "relationComposition",
            },
            f"inventory {key}.rules",
        )
        shapes = typed["shapes"]
        if not isinstance(shapes, list) or [item.get("name") for item in shapes] != [
            "圆形",
            "三角形",
            "正方形",
            "长方形",
        ]:
            raise ValueError("shape inventory mismatch")
        if typed["positionRelations"] != ["上", "下", "左", "右"]:
            raise ValueError("position relation inventory mismatch")
        rectangle_rule = typed["rectangleSquareRule"]
        if not isinstance(rectangle_rule, Mapping) or rectangle_rule != {
            "squareIsRectangle": True,
            "whenBothAreChoices": "must_disambiguate_particular_rectangle",
            "requiredDiscriminators": [
                "四条边不全相等",
                "相邻边长度不同",
                "长和宽不相等",
            ],
        }:
            raise ValueError("rectangle/square disambiguation rule mismatch")
        if typed["relationComposition"] != {
            "sameAxisOnly": True,
            "crossAxisRequiresSharedRowOrColumn": True,
        }:
            raise ValueError("position relation composition mismatch")
    elif kind == "letter_initial_sound_rules":
        typed = _exact_mapping_keys(
            rules,
            {"letters", "assessmentModes", "scoringNormalization"},
            f"inventory {key}.rules",
        )
        letters = typed["letters"]
        if not isinstance(letters, list) or len(letters) != 26:
            raise ValueError("English letter inventory must contain 26 entries")
        for index, item in enumerate(letters):
            letter = _exact_mapping_keys(
                item,
                {"uppercase", "lowercase", "initialSoundWords"},
                "English letter rule",
            )
            if letter["uppercase"] != chr(65 + index) or letter["lowercase"] != chr(
                97 + index
            ):
                raise ValueError("English letter case mapping mismatch")
            _unique_strings(letter["initialSoundWords"], "initial sound words")
        _unique_strings(typed["assessmentModes"], "letter assessment modes")
        _unique_strings(typed["scoringNormalization"], "letter scoring normalization")
    elif kind == "greeting_phrase_rules":
        typed = _exact_mapping_keys(
            rules,
            {"phrases", "nameExpression", "scoringNormalization", "targetLanguageCode"},
            f"inventory {key}.rules",
        )
        if not isinstance(typed["phrases"], list) or len(typed["phrases"]) < 4:
            raise ValueError("greeting phrase inventory must contain four entries")
        if typed["nameExpression"] != {
            "pattern": "My name is {name}.",
            "nameMustBeNonEmpty": True,
        }:
            raise ValueError("name expression rule mismatch")
        if typed["targetLanguageCode"] != "en-US":
            raise ValueError("greeting target language mismatch")
        _unique_strings(typed["scoringNormalization"], "greeting normalization")
    elif kind == "number_color_rules":
        typed = _exact_mapping_keys(
            rules,
            {"numbers", "colors", "assessmentModes", "scoringNormalization"},
            f"inventory {key}.rules",
        )
        expected_words = [
            "one", "two", "three", "four", "five", "six", "seven", "eight",
            "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
            "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
        ]
        numbers = typed["numbers"]
        if not isinstance(numbers, list) or [
            (item.get("value"), item.get("word")) for item in numbers
        ] != list(enumerate(expected_words, start=1)):
            raise ValueError("English number inventory must cover 1 through 20")
        _unique_strings(typed["colors"], "color inventory")
        _unique_strings(typed["assessmentModes"], "number/color assessment modes")
        _unique_strings(typed["scoringNormalization"], "number/color normalization")


def validate_primary_one_content_contract(
    contract: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(contract, Mapping):
        raise ValueError("primary-one content contract must be an object")
    expected_top_keys = {
        "schemaVersion",
        "gradeCode",
        "subjectLanguagePolicyVersion",
        "subjects",
        "prerequisiteInventory",
        "inventories",
        "canaryManifest",
        "datasetSha256",
    }
    missing = expected_top_keys - set(contract)
    extras = set(contract) - expected_top_keys
    if missing:
        raise ValueError(
            "primary-one content contract missing fields: "
            + ", ".join(sorted(missing))
        )
    if extras:
        raise ValueError(
            "primary-one content contract has unsupported fields: "
            + ", ".join(sorted(extras))
        )
    if contract["schemaVersion"] != CONTENT_VALIDATION_CONTRACT_VERSION:
        raise ValueError("content validation contract version mismatch")
    if contract["gradeCode"] != "primary_1":
        raise ValueError("content validation contract grade mismatch")
    if contract["subjectLanguagePolicyVersion"] != SUBJECT_LANGUAGE_POLICY_VERSION:
        raise ValueError("subject language policy version mismatch")

    _validate_authority_ordinal_types(contract)
    dataset_hash = contract["datasetSha256"]
    if (
        not isinstance(dataset_hash, str)
        or len(dataset_hash) != 64
        or any(character not in "0123456789abcdef" for character in dataset_hash)
    ):
        raise ValueError("datasetSha256 must be lowercase SHA-256 hex")
    actual_dataset_hash = _content_contract_hash(contract)
    if (
        dataset_hash == actual_dataset_hash
        and actual_dataset_hash != PRIMARY_ONE_CONTENT_DATASET_SHA256
    ):
        raise ValueError("pinned dataset hash mismatch")

    inventories = contract["inventories"]
    if not isinstance(inventories, Mapping) or not inventories:
        raise ValueError("inventories must be a non-empty object")
    if set(inventories) != set(_PRIMARY_ONE_INVENTORY_KINDS):
        raise ValueError("inventories must cover the exact Grade-1 rule datasets")
    for inventory_key, inventory in inventories.items():
        if not isinstance(inventory_key, str) or not inventory_key:
            raise ValueError("inventory keys must be non-empty strings")
        _validate_typed_inventory(inventory_key, inventory)

    prerequisite_inventory = contract["prerequisiteInventory"]
    if not isinstance(prerequisite_inventory, Mapping):
        raise ValueError("prerequisiteInventory must be an object")

    subjects = contract["subjects"]
    if not isinstance(subjects, list) or len(subjects) != 3:
        raise ValueError("subjects must contain the exact three subject policies")
    actual_skill_ids: list[str] = []
    for subject_index, expected_policy in enumerate(_PRIMARY_ONE_SUBJECT_LANGUAGES):
        subject, subject_ordinal, instruction_language, target_language = (
            expected_policy
        )
        policy = subjects[subject_index]
        if not isinstance(policy, Mapping):
            raise ValueError("subject policy must be an object")
        expected_subject_keys = {
            "subject",
            "subjectOrdinal",
            "instructionLanguageCode",
            "targetLanguageCode",
            "boundaries",
        }
        extras = set(policy) - expected_subject_keys
        missing = expected_subject_keys - set(policy)
        if extras:
            raise ValueError(
                "unsupported subject fields: " + ", ".join(sorted(extras))
            )
        if missing:
            raise ValueError(
                "missing subject fields: " + ", ".join(sorted(missing))
            )
        _authority_ordinal(
            policy["subjectOrdinal"], "subjectOrdinal", subject_ordinal
        )
        if policy["subject"] != subject:
            raise ValueError("subject ordinal mismatch")
        if (
            policy["instructionLanguageCode"] != instruction_language
            or policy["targetLanguageCode"] != target_language
        ):
            raise ValueError("subject language policy mismatch")

        registered_boundaries = boundaries_for("primary_1", subject)
        authority_boundaries = policy["boundaries"]
        if (
            not isinstance(authority_boundaries, list)
            or len(authority_boundaries) != len(registered_boundaries)
        ):
            raise ValueError("subject boundary inventory mismatch")
        for boundary_index, registered in enumerate(registered_boundaries, start=1):
            authority = authority_boundaries[boundary_index - 1]
            if not isinstance(authority, Mapping):
                raise ValueError("boundary authority must be an object")
            expected_boundary_keys = {
                "skillId",
                "boundaryOrdinal",
                "prerequisiteSkills",
                "validationInventoryKeys",
            }
            if set(authority) != expected_boundary_keys:
                raise ValueError("boundary authority fields mismatch")
            _authority_ordinal(
                authority["boundaryOrdinal"],
                "boundary ordinal",
                boundary_index,
            )
            if authority["skillId"] != registered.skill_id:
                raise ValueError("boundary skill mismatch")
            expected_prerequisites = list(registered.prerequisite_skills)
            if authority["prerequisiteSkills"] != expected_prerequisites:
                raise ValueError("boundary prerequisite mismatch")
            if (
                prerequisite_inventory.get(registered.skill_id)
                != expected_prerequisites
            ):
                raise ValueError("prerequisiteInventory boundary mismatch")
            inventory_keys = authority["validationInventoryKeys"]
            if (
                not isinstance(inventory_keys, list)
                or not inventory_keys
                or len(set(inventory_keys)) != len(inventory_keys)
                or any(key not in inventories for key in inventory_keys)
                or inventory_keys
                != list(_PRIMARY_ONE_BOUNDARY_INVENTORY_KEYS[registered.skill_id])
            ):
                raise ValueError("boundary validation inventory mismatch")
            actual_skill_ids.append(registered.skill_id)
    if set(prerequisite_inventory) != set(actual_skill_ids):
        raise ValueError("prerequisiteInventory must cover exactly ten boundaries")

    canary = contract["canaryManifest"]
    expected_canary = {
        "version": PRIMARY_ONE_CANARY_MANIFEST_VERSION,
        "targets": [
            {
                "subject": "chinese",
                "subjectOrdinal": 1,
                "skillId": "pinyin_syllables",
                "boundaryOrdinal": 1,
                "variantOrdinal": 1,
            },
            {
                "subject": "math",
                "subjectOrdinal": 2,
                "skillId": "number_sense_20",
                "boundaryOrdinal": 1,
                "variantOrdinal": 1,
            },
            {
                "subject": "english",
                "subjectOrdinal": 3,
                "skillId": "letters_sounds",
                "boundaryOrdinal": 1,
                "variantOrdinal": 1,
            },
        ],
    }
    if not isinstance(canary, Mapping) or set(canary) != {"version", "targets"}:
        raise ValueError("canary manifest mismatch")
    canary_targets = canary["targets"]
    if not isinstance(canary_targets, list) or len(canary_targets) != 3:
        raise ValueError("canary manifest mismatch")
    for index, target in enumerate(canary_targets):
        if not isinstance(target, Mapping):
            raise ValueError("canary target must be an object")
        _authority_ordinal(
            target.get("subjectOrdinal"),
            "canary subjectOrdinal",
            expected_canary["targets"][index]["subjectOrdinal"],
        )
        _authority_ordinal(
            target.get("boundaryOrdinal"),
            "canary boundaryOrdinal",
            expected_canary["targets"][index]["boundaryOrdinal"],
        )
        _authority_ordinal(
            target.get("variantOrdinal"),
            "canary variantOrdinal",
            expected_canary["targets"][index]["variantOrdinal"],
        )
    if canary != expected_canary:
        raise ValueError("canary manifest mismatch")

    if dataset_hash != actual_dataset_hash:
        raise ValueError("content validation dataset hash mismatch")
    if actual_dataset_hash != PRIMARY_ONE_CONTENT_DATASET_SHA256:
        raise ValueError("pinned dataset hash mismatch")
    return json.loads(json.dumps(contract, ensure_ascii=False))


def primary_one_content_contract() -> Mapping[str, object]:
    with _PRIMARY_ONE_CONTENT_CONTRACT_PATH.open("r", encoding="utf-8") as handle:
        contract = json.load(handle)
    return validate_primary_one_content_contract(contract)
