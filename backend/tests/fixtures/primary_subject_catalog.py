from __future__ import annotations

import copy
import hashlib

from tests.fixtures.primary_math_courses import PRIMARY_MATH_COURSES


COURSE_SCHEMA_VERSION = "mira.learning.course.v1"
PRIMARY_SUBJECT_CODES = frozenset({"chinese", "math", "english"})
SOURCE_AUTHORITY = {
    "basis": "national_curriculum_standard_2022",
    "contentOrigin": "mira_original",
    "textbookDependency": "none",
}


def _choice(
    question_id: str,
    prompt: str,
    *,
    skill: str,
    choices: tuple[tuple[str, str], ...],
    answer: str,
    hint: str,
    explanation: str,
) -> dict:
    # Do not train any internal consumer to assume the first option is right.
    # The public API performs a second, session-stable shuffle and replaces
    # these private IDs with opaque tokens.
    source_choices = list(choices)
    offset = int.from_bytes(
        hashlib.sha256(question_id.encode("utf-8")).digest()[:2],
        "big",
    ) % len(source_choices)
    source_choices = source_choices[offset:] + source_choices[:offset]
    return {
        "id": question_id,
        "type": "single_choice",
        "prompt": prompt,
        "answer": answer,
        "skill": skill,
        "hint": hint,
        "explanation": explanation,
        "choices": [
            {"id": item_id, "label": label}
            for item_id, label in source_choices
        ],
        "evaluation": {
            "expectedOptionId": answer,
            "normalization": ["trim", "casefold"],
        },
    }


def _exact(
    question_id: str,
    prompt: str,
    answer: str,
    *,
    skill: str,
    hint: str,
    explanation: str,
    english: bool = False,
    case_sensitive: bool = False,
) -> dict:
    normalization = ["trim", "collapse_whitespace"]
    if english:
        if not case_sensitive:
            normalization.append("casefold")
        normalization.append("strip_terminal_punctuation")
    else:
        normalization.append("remove_whitespace")
    return {
        "id": question_id,
        "type": "exact_text",
        "prompt": prompt,
        "answer": answer,
        "skill": skill,
        "hint": hint,
        "explanation": explanation,
        "evaluation": {
            "expected": answer,
            "normalization": normalization,
        },
    }


def _accepted(
    question_id: str,
    prompt: str,
    answers: tuple[str, ...],
    *,
    skill: str,
    hint: str,
    explanation: str,
    english: bool = False,
) -> dict:
    normalization = ["trim", "collapse_whitespace"]
    if english:
        normalization.extend(["casefold", "strip_terminal_punctuation"])
    else:
        normalization.append("remove_whitespace")
    accepted = list(answers)
    return {
        "id": question_id,
        "type": "accepted_text",
        "prompt": prompt,
        "answer": accepted,
        "acceptedAnswers": accepted,
        "skill": skill,
        "hint": hint,
        "explanation": explanation,
        "evaluation": {
            "acceptedAnswers": accepted,
            "normalization": normalization,
        },
    }


def _sequence(
    question_id: str,
    prompt: str,
    *,
    skill: str,
    choices: tuple[tuple[str, str], ...],
    answer: tuple[str, ...],
    hint: str,
    explanation: str,
) -> dict:
    expected = list(answer)
    display_choices = list(reversed(choices))
    return {
        "id": question_id,
        "type": "sequence",
        "prompt": prompt,
        "answer": expected,
        "skill": skill,
        "hint": hint,
        "explanation": explanation,
        "choices": [
            {"id": item_id, "label": label}
            for item_id, label in display_choices
        ],
        "evaluation": {
            "expectedSequence": expected,
            "normalization": ["trim", "casefold"],
        },
    }


def _course(
    grade: int,
    subject: str,
    node_code: str,
    title: str,
    objective: str,
    intro: str,
    questions: list[dict],
    *,
    estimated_minutes: int,
) -> dict:
    source_authority = copy.deepcopy(SOURCE_AUTHORITY)
    if subject == "english" and grade <= 2:
        source_authority["basis"] = "mira_primary_english_enrichment_v1"
    return {
        "id": f"primary_{subject}_g{grade}_{node_code}_v1",
        "version": "1.0.0",
        "gradeCode": f"primary_{grade}",
        "subject": subject,
        "nodeCode": node_code,
        "title": title,
        "objective": objective,
        "status": "published",
        "content": {
            "schemaVersion": COURSE_SCHEMA_VERSION,
            "sessionKind": "lesson",
            "outcomeMode": "scored_deterministic",
            "sourceAuthority": source_authority,
            "reviewPolicy": "programmatic_guarded",
            "intro": intro,
            "estimatedMinutes": estimated_minutes,
            "questions": questions,
        },
    }


def _math_course_with_contract(course: dict) -> dict:
    enriched = copy.deepcopy(course)
    content = enriched["content"]
    content["schemaVersion"] = COURSE_SCHEMA_VERSION
    content["sessionKind"] = "lesson"
    content["outcomeMode"] = "scored_deterministic"
    content["sourceAuthority"] = copy.deepcopy(SOURCE_AUTHORITY)
    content["reviewPolicy"] = "programmatic_guarded"
    return enriched


PRIMARY_CHINESE_COURSES = (
    _course(1, "chinese", "pinyin_syllables", "拼音与音节", "分辨常见声母、韵母和完整音节。", "先听清字音，再找出组成音节的字母。", [
        _choice("cn_g1_py_q1", "“妈”的正确拼音是哪一个？", skill="字音辨认", choices=(("ma1", "mā"), ("ba1", "bā"), ("na1", "nā")), answer="ma1", hint="先听声母 m。", explanation="“妈”读 mā。"),
        _choice("cn_g1_py_q2", "下面哪个音节以声母 b 开头？", skill="声母辨认", choices=(("ba", "bā"), ("pa", "pā"), ("ma", "mā")), answer="ba", hint="看每个音节的第一个字母。", explanation="bā 以声母 b 开头。"),
        _sequence("cn_g1_py_q3", "按顺序组成音节“dā”。", skill="音节拼合", choices=(("d", "声母 d"), ("a", "韵母 ā")), answer=("d", "a"), hint="声母在前，韵母在后。", explanation="d 和 ā 拼成 dā。"),
        _choice("cn_g1_py_q4", "“鱼”的拼音是哪一个？", skill="字音辨认", choices=(("yu", "yú"), ("wu", "wú"), ("yi", "yí")), answer="yu", hint="这个音节整体读作 yú。", explanation="“鱼”读 yú。"),
        _choice("cn_g1_py_q5", "声母 b 和韵母 a 拼成哪个音节？", skill="音节拼合", choices=(("ba", "ba"), ("pa", "pa"), ("ma", "ma")), answer="ba", hint="声母 b 要保留在最前面。", explanation="b 和 a 拼成 ba。"),
    ], estimated_minutes=8),
    _course(1, "chinese", "characters_words", "汉字与词语", "辨认常见汉字的结构、偏旁和恰当搭配。", "观察字形，再把字放进合适的词语里。", [
        _choice("cn_g1_cw_q1", "“河”字的偏旁是哪一个？", skill="偏旁辨认", choices=(("water", "三点水"), ("person", "单人旁"), ("mouth", "口字旁")), answer="water", hint="“河”与水有关。", explanation="“河”的偏旁是三点水。"),
        _choice("cn_g1_cw_q2", "哪个词语搭配正确？", skill="词语搭配", choices=(("red_flower", "红花"), ("red_sound", "红声音"), ("red_run", "红跑步")), answer="red_flower", hint="“红”通常描写颜色。", explanation="“红花”是正确搭配。"),
        _exact("cn_g1_cw_q3", "“上”的反义词是什么？只写一个字。", "下", skill="反义词", hint="想一想相反的方向。", explanation="“上”和“下”意思相反。"),
        _choice("cn_g1_cw_q4", "“明”字由哪两个字组成？", skill="字形结构", choices=(("sun_moon", "日和月"), ("wood_wood", "木和木"), ("person_tree", "人和木")), answer="sun_moon", hint="观察“明”的左右两边。", explanation="“明”由“日”和“月”组成。"),
        _accepted("cn_g1_cw_q5", "填词：一（ ）小鸟。", ("只",), skill="量词", hint="数小鸟常用这个量词。", explanation="应说“一只小鸟”。"),
    ], estimated_minutes=8),
    _course(1, "chinese", "simple_sentences", "完整句子", "识别完整句子，掌握基本语序和句末标点。", "把谁、做什么说清楚，就是一个完整句子。", [
        _sequence("cn_g1_ss_q1", "把词语排成一句话。", skill="基本语序", choices=(("bird", "小鸟"), ("sky", "在天空中"), ("fly", "飞")), answer=("bird", "sky", "fly"), hint="先说谁，再说在哪里做什么。", explanation="小鸟在天空中飞。"),
        _choice("cn_g1_ss_q2", "“你叫什么名字___”句末应使用什么标点？", skill="问号使用", choices=(("question", "？"), ("period", "。"), ("comma", "，")), answer="question", hint="这句话在提问。", explanation="疑问句末用问号。"),
        _choice("cn_g1_ss_q3", "下面哪一句话完整？", skill="完整句", choices=(("complete", "小猫喝水。"), ("fragment1", "一只可爱的"), ("fragment2", "在桌子下面")), answer="complete", hint="完整句要说明谁在做什么。", explanation="“小猫喝水。”意思完整。"),
        _accepted("cn_g1_ss_q4", "补全句子：我爱我的（ ）。写“家”或“家人”。", ("家", "家人"), skill="句子补充", hint="填入句意通顺的对象。", explanation="“我爱我的家”和“我爱我的家人”都通顺。"),
        _sequence("cn_g1_ss_q5", "按事情发生顺序排列。", skill="顺序表达", choices=(("wash", "先洗手"), ("eat", "再吃饭"), ("clean", "最后收拾餐桌")), answer=("wash", "eat", "clean"), hint="饭前先洗手。", explanation="洗手、吃饭、收拾餐桌是合理顺序。"),
    ], estimated_minutes=8),
    _course(2, "chinese", "word_relations", "词语关系", "掌握近义词、反义词和常见词语搭配。", "通过词语之间的关系，把意思说得更准确。", [
        _choice("cn_g2_wr_q1", "“高兴”的近义词是哪一个？", skill="近义词", choices=(("happy", "快乐"), ("sad", "难过"), ("quiet", "安静")), answer="happy", hint="找意思相近的词。", explanation="“快乐”和“高兴”意思相近。"),
        _choice("cn_g2_wr_q2", "“温暖”的反义词是哪一个？", skill="反义词", choices=(("cold", "寒冷"), ("bright", "明亮"), ("soft", "柔软")), answer="cold", hint="想一想温度相反的感受。", explanation="“温暖”和“寒冷”意思相反。"),
        _choice("cn_g2_wr_q3", "选择合适的词：小树在春风中（ ）。", skill="动词搭配", choices=(("sway", "摇摆"), ("taste", "品尝"), ("read", "阅读")), answer="sway", hint="春风吹动小树。", explanation="“小树在春风中摇摆”搭配恰当。"),
        _exact("cn_g2_wr_q4", "“急急忙忙”属于表示快还是慢？只写一个字。", "快", skill="词义判断", hint="想象赶时间的样子。", explanation="“急急忙忙”表示动作很快。"),
        _accepted("cn_g2_wr_q5", "填入合适量词：一（ ）雨伞。", ("把",), skill="量词", hint="雨伞有伞柄，可以拿在手里。", explanation="应说“一把雨伞”。"),
    ], estimated_minutes=9),
    _course(2, "chinese", "sentence_order", "句子顺序与标点", "按时间和因果关系排列句子并正确使用标点。", "先找提示顺序的词，再把句子连起来。", [
        _sequence("cn_g2_so_q1", "按早晨做事的顺序排列。", skill="时间顺序", choices=(("wake", "起床"), ("wash", "洗漱"), ("school", "去上学")), answer=("wake", "wash", "school"), hint="先离开床，再整理自己。", explanation="起床、洗漱、去上学符合时间顺序。"),
        _choice("cn_g2_so_q2", "“这里的花真美___”句末最适合哪个标点？", skill="感叹号使用", choices=(("exclamation", "！"), ("question", "？"), ("comma", "，")), answer="exclamation", hint="句子表达赞叹。", explanation="强烈赞叹时句末可用感叹号。"),
        _choice("cn_g2_so_q3", "哪一句表示原因？", skill="因果关系", choices=(("because", "因为下雨，比赛推迟了。"), ("time", "放学以后，我回家。"), ("parallel", "小明读书，小红画画。")), answer="because", hint="寻找“因为”。", explanation="“因为下雨”说明比赛推迟的原因。"),
        _sequence("cn_g2_so_q4", "把句子排成通顺的一句话。", skill="句子重组", choices=(("we", "我们"), ("library", "在图书馆"), ("read", "安静地读书")), answer=("we", "library", "read"), hint="先说谁，再说地点和动作。", explanation="我们在图书馆安静地读书。"),
        _choice("cn_g2_so_q5", "哪句话的标点使用正确？", skill="标点辨析", choices=(("correct", "你吃过早饭了吗？"), ("wrong1", "今天，天气很好？"), ("wrong2", "我喜欢跑步，")), answer="correct", hint="疑问句末用问号。", explanation="“你吃过早饭了吗？”标点正确。"),
    ], estimated_minutes=9),
    _course(2, "chinese", "short_reading", "短文信息提取", "从原创短文中找到人物、时间、地点和结果。", "阅读短文：周六早晨，安安和爸爸到社区花园浇花。他们先装水，再给小树慢慢浇水。忙完后，安安把水桶放回原处。", [
        _choice("cn_g2_sr_q1", "安安什么时候去花园？", skill="时间提取", choices=(("sat_morning", "周六早晨"), ("fri_evening", "周五晚上"), ("sun_noon", "周日中午")), answer="sat_morning", hint="看短文第一句话。", explanation="短文写的是“周六早晨”。"),
        _choice("cn_g2_sr_q2", "安安和谁一起去？", skill="人物提取", choices=(("father", "爸爸"), ("teacher", "老师"), ("friend", "同学")), answer="father", hint="看“和”字后面的人物。", explanation="安安和爸爸一起去。"),
        _choice("cn_g2_sr_q3", "他们去哪里浇花？", skill="地点提取", choices=(("garden", "社区花园"), ("school", "学校操场"), ("home", "家里阳台")), answer="garden", hint="地点在第一句话中。", explanation="他们到社区花园浇花。"),
        _sequence("cn_g2_sr_q4", "按短文顺序排列。", skill="事件顺序", choices=(("fill", "装水"), ("water", "浇树"), ("return", "放回水桶")), answer=("fill", "water", "return"), hint="依次查找“先”“再”“忙完后”。", explanation="先装水，再浇树，最后放回水桶。"),
        _choice("cn_g2_sr_q5", "安安最后做了什么？", skill="结果提取", choices=(("return", "把水桶放回原处"), ("play", "在花园玩耍"), ("buy", "买了一棵树")), answer="return", hint="看短文最后一句。", explanation="安安最后把水桶放回原处。"),
    ], estimated_minutes=9),
    _course(3, "chinese", "context_words", "联系语境理解词语", "根据句子语境判断词义和词语感情色彩。", "词语放进句子里，意思会更清楚。", [
        _choice("cn_g3_cw_q1", "“雨后，叶子显得格外鲜亮。”这里“格外”最接近什么？", skill="语境释义", choices=(("especially", "特别"), ("usually", "平常"), ("slowly", "慢慢")), answer="especially", hint="删去“格外”再比较程度。", explanation="“格外”在这里表示“特别”。"),
        _choice("cn_g3_cw_q2", "“他一丝不苟地检查作业。”说明他怎样？", skill="词义理解", choices=(("careful", "认真细致"), ("careless", "粗心大意"), ("hurried", "十分着急")), answer="careful", hint="“一丝不苟”强调不马虎。", explanation="这个词表示做事认真细致。"),
        _choice("cn_g3_cw_q3", "下面哪个词含有赞扬的意思？", skill="感情色彩", choices=(("brave", "勇敢"), ("arrogant", "傲慢"), ("lazy", "懒惰")), answer="brave", hint="找表示好品质的词。", explanation="“勇敢”通常含赞扬意味。"),
        _accepted("cn_g3_cw_q4", "“迅速”可以换成哪个意思相近的词？写“快速”或“飞快”。", ("快速", "飞快"), skill="近义替换", hint="找表示速度快的词。", explanation="“快速”和“飞快”在该意义上都与“迅速”相近。"),
        _choice("cn_g3_cw_q5", "“教室里鸦雀无声”表示什么？", skill="成语理解", choices=(("quiet", "非常安静"), ("noisy", "十分热闹"), ("dark", "光线很暗")), answer="quiet", hint="想象连鸟叫声都听不到。", explanation="“鸦雀无声”形容非常安静。"),
    ], estimated_minutes=10),
    _course(3, "chinese", "connect_sentences", "连接句子", "运用转折、因果和条件关联词组织句子。", "先判断两部分的关系，再选择关联词。", [
        _choice("cn_g3_cs_q1", "（ ）今天下雨，（ ）运动会延期了。", skill="因果关联", choices=(("because_so", "因为……所以……"), ("although_but", "虽然……但是……"), ("if_then", "如果……就……")), answer="because_so", hint="下雨是延期的原因。", explanation="两部分是因果关系。"),
        _choice("cn_g3_cs_q2", "（ ）天气很冷，（ ）同学们仍然按时到校。", skill="转折关联", choices=(("although_but", "虽然……但是……"), ("because_so", "因为……所以……"), ("not_only_but", "不但……而且……")), answer="although_but", hint="后半句与通常预想不同。", explanation="两部分是转折关系。"),
        _choice("cn_g3_cs_q3", "（ ）认真观察，（ ）能发现更多细节。", skill="条件关联", choices=(("if_then", "如果……就……"), ("because_so", "因为……所以……"), ("either_or", "不是……就是……")), answer="if_then", hint="前半句是实现后半句的条件。", explanation="这里适合使用“如果……就……”。"),
        _sequence("cn_g3_cs_q4", "把三句话排成有因果的段落。", skill="段落连贯", choices=(("cloud", "天空乌云密布。"), ("rain", "不久，大雨落了下来。"), ("shelter", "行人纷纷到屋檐下避雨。")), answer=("cloud", "rain", "shelter"), hint="先有天气变化，再下雨，最后写人的反应。", explanation="乌云、下雨、避雨构成连贯顺序。"),
        _choice("cn_g3_cs_q5", "哪句话表达了并列关系？", skill="句间关系", choices=(("parallel", "弟弟在搭积木，姐姐在画画。"), ("cause", "因为停电，所以灯灭了。"), ("turn", "虽然累，但是他没停下。")), answer="parallel", hint="两件事同时分别发生。", explanation="搭积木和画画是并列叙述。"),
    ], estimated_minutes=10),
    _course(3, "chinese", "reading_evidence", "阅读与证据", "从原创短文中提取事实，并用文本证据作出简单判断。", "阅读短文：学校的小菜园里种着番茄。三月，大家播下种子；四月，小苗长高；五月，枝头开出黄花。值日小组每天下午记录高度，还会在泥土干燥时浇水。", [
        _choice("cn_g3_re_q1", "大家在几月播种？", skill="事实提取", choices=(("march", "三月"), ("april", "四月"), ("may", "五月")), answer="march", hint="看第一件事。", explanation="短文写三月播下种子。"),
        _choice("cn_g3_re_q2", "五月出现了什么变化？", skill="事实提取", choices=(("flowers", "开出黄花"), ("seeds", "播下种子"), ("harvest", "收获果实")), answer="flowers", hint="按月份定位。", explanation="五月枝头开出黄花。"),
        _choice("cn_g3_re_q3", "值日小组什么时候记录高度？", skill="时间提取", choices=(("afternoon", "每天下午"), ("morning", "每天早晨"), ("weekly", "每周一")), answer="afternoon", hint="看最后一句。", explanation="他们每天下午记录高度。"),
        _choice("cn_g3_re_q4", "什么时候需要浇水？", skill="条件提取", choices=(("dry", "泥土干燥时"), ("flower", "开花时"), ("daily", "每次记录后")), answer="dry", hint="寻找“时”前面的条件。", explanation="泥土干燥时才浇水。"),
        _sequence("cn_g3_re_q5", "按短文中的生长顺序排列。", skill="信息排序", choices=(("seed", "播种"), ("seedling", "小苗长高"), ("flower", "开花")), answer=("seed", "seedling", "flower"), hint="按照三月、四月、五月排序。", explanation="先播种，再长苗，随后开花。"),
    ], estimated_minutes=10),
    _course(4, "chinese", "sentence_clarity", "把句子说清楚", "识别重复、搭配不当和指代不清等表达问题。", "读一遍句子，检查意思是否完整、准确、不重复。", [
        _choice("cn_g4_sc_q1", "哪句话没有语病？", skill="病句辨析", choices=(("correct", "同学们认真完成了实验记录。"), ("wrong1", "同学们完成了认真实验记录。"), ("wrong2", "同学们基本全部完成了记录。")), answer="correct", hint="检查词序和前后是否矛盾。", explanation="第一句词序恰当、意思明确。"),
        _choice("cn_g4_sc_q2", "“读了这篇故事，使我很受感动”主要问题是什么？", skill="成分残缺", choices=(("missing_subject", "句子缺少明确的主语"), ("wrong_order", "词语顺序颠倒"), ("repeat", "重复使用标点")), answer="missing_subject", hint="想一想是谁读了故事。", explanation="“读了……”和“使……”连用后没有明确主语，可删去“使”或补出主语。"),
        _choice("cn_g4_sc_q3", "哪一句指代最清楚？", skill="指代清楚", choices=(("clear", "小林把书还给小周后，小周向他道谢。"), ("unclear", "小林告诉小周，他获奖了。"), ("missing", "看到以后非常高兴。")), answer="clear", hint="读者应能判断每个动作是谁做的。", explanation="第一句人物与动作关系最清楚。"),
        _choice("cn_g4_sc_q4", "“我忍不住不笑了”若想表达笑了，应改成哪一句？", skill="否定表达", choices=(("laugh", "我忍不住笑了。"), ("not_laugh", "我没有笑。"), ("might", "我也许会笑。")), answer="laugh", hint="去掉多余的否定词。", explanation="应改为“我忍不住笑了”。"),
        _sequence("cn_g4_sc_q5", "把词语排成准确的句子。", skill="语序", choices=(("scientists", "科学家们"), ("carefully", "仔细地"), ("observe", "观察实验现象")), answer=("scientists", "carefully", "observe"), hint="主语在前，修饰动作的词放在动作前。", explanation="科学家们仔细地观察实验现象。"),
    ], estimated_minutes=10),
    _course(4, "chinese", "paragraph_structure", "段落结构", "识别总分结构、中心句和合理的说明顺序。", "先找概括全段的句子，再看其他句子怎样展开。", [
        _choice("cn_g4_ps_q1", "“校园的秋天色彩丰富。银杏叶金黄，枫叶火红，松树仍然翠绿。”中心句是哪一句？", skill="中心句", choices=(("first", "校园的秋天色彩丰富。"), ("second", "银杏叶金黄。"), ("third", "松树仍然翠绿。")), answer="first", hint="找能概括其他句子的句子。", explanation="第一句概括了后面的多种颜色。"),
        _choice("cn_g4_ps_q2", "上题中的段落是什么结构？", skill="段落结构", choices=(("general_detail", "总—分"), ("time", "时间顺序"), ("cause", "因果结构")), answer="general_detail", hint="先概括，后举例。", explanation="段落先总写色彩丰富，再分别说明。"),
        _sequence("cn_g4_ps_q3", "按制作纸风车的顺序排列。", skill="说明顺序", choices=(("cut", "剪出正方形纸"), ("fold", "沿对角线折出痕迹"), ("fix", "把叶片固定在小棒上")), answer=("cut", "fold", "fix"), hint="先准备形状，再折叠，最后组装。", explanation="剪纸、折痕、固定是合理制作顺序。"),
        _choice("cn_g4_ps_q4", "哪一句最适合作为“节约用水”段落的中心句？", skill="概括表达", choices=(("save", "我们可以从生活小事做起，节约每一滴水。"), ("tap", "水龙头是金属做的。"), ("rain", "昨天傍晚下雨了。")), answer="save", hint="中心句要统领整个主题。", explanation="第一句直接概括“节约用水”的主题。"),
        _choice("cn_g4_ps_q5", "介绍教室从门口到窗边的布置，最适合使用什么顺序？", skill="空间顺序", choices=(("space", "空间顺序"), ("cause", "因果顺序"), ("emotion", "感情顺序")), answer="space", hint="题目给出了位置变化。", explanation="介绍不同位置的布置适合使用空间顺序。"),
    ], estimated_minutes=10),
    _course(4, "chinese", "reading_inference", "阅读判断", "区分短文中的明确事实与有证据的简单推断。", "阅读短文：清晨，路面还有水迹，树叶上挂着水珠。小宇出门时带了一把收起的雨伞，天空已经露出蓝色。他走到路口，看见清洁工正在清理被风吹落的树枝。", [
        _choice("cn_g4_ri_q1", "清晨路面有什么？", skill="事实提取", choices=(("water", "水迹"), ("snow", "积雪"), ("sand", "沙土")), answer="water", hint="看第一句话。", explanation="短文明确写着路面还有水迹。"),
        _choice("cn_g4_ri_q2", "小宇带了什么？", skill="事实提取", choices=(("umbrella", "收起的雨伞"), ("coat", "雨衣"), ("bag", "旅行包")), answer="umbrella", hint="看第二句话。", explanation="小宇带了一把收起的雨伞。"),
        _choice("cn_g4_ri_q3", "可以合理推断此前可能发生了什么？", skill="证据推断", choices=(("rain", "下过雨"), ("snow", "下过雪"), ("heat", "天气炎热")), answer="rain", hint="结合水迹和水珠判断。", explanation="水迹和叶上水珠支持“此前下过雨”的推断。"),
        _choice("cn_g4_ri_q4", "此时天空怎样？", skill="事实提取", choices=(("blue", "已经露出蓝色"), ("dark", "完全漆黑"), ("red", "布满晚霞")), answer="blue", hint="定位“天空”一词。", explanation="短文说天空已经露出蓝色。"),
        _choice("cn_g4_ri_q5", "清洁工在做什么？", skill="事实提取", choices=(("branches", "清理落下的树枝"), ("water", "给树浇水"), ("paint", "粉刷路口")), answer="branches", hint="看最后一句。", explanation="清洁工正在清理被风吹落的树枝。"),
    ], estimated_minutes=10),
    _course(5, "chinese", "idioms_context", "成语与语境", "根据具体语境准确选择常用成语。", "理解情境后再选成语，不只看其中一个字。", [
        _choice("cn_g5_ic_q1", "大家想了很多办法，终于解决难题。最适合哪个词？", skill="成语运用", choices=(("brainstorm", "集思广益"), ("hasty", "草草了事"), ("alone", "孤掌难鸣")), answer="brainstorm", hint="大家共同贡献想法。", explanation="“集思广益”指集中众人智慧。"),
        _choice("cn_g5_ic_q2", "他读书时连一个小细节也不放过，可以用哪个词？", skill="成语运用", choices=(("meticulous", "一丝不苟"), ("distracted", "心不在焉"), ("superficial", "走马观花")), answer="meticulous", hint="强调认真细致。", explanation="“一丝不苟”最符合语境。"),
        _choice("cn_g5_ic_q3", "比赛前我们已经做好充分准备，可以说什么？", skill="成语运用", choices=(("ready", "胸有成竹"), ("panic", "手忙脚乱"), ("late", "亡羊补牢")), answer="ready", hint="强调事先已有把握。", explanation="“胸有成竹”表示做事前已有完整打算。"),
        _choice("cn_g5_ic_q4", "看到壮丽山河，大家不停赞叹。最合适的是？", skill="成语运用", choices=(("admire", "赞不绝口"), ("silent", "默不作声"), ("angry", "怒气冲冲")), answer="admire", hint="“不停赞叹”是关键词。", explanation="“赞不绝口”表示连声称赞。"),
        _choice("cn_g5_ic_q5", "面对失败，他没有放弃，而是再次尝试。最能概括的是？", skill="品质概括", choices=(("persevere", "坚持不懈"), ("give_up", "半途而废"), ("hesitate", "犹豫不决")), answer="persevere", hint="关注“没有放弃”。", explanation="“坚持不懈”符合不断尝试的行为。"),
    ], estimated_minutes=11),
    _course(5, "chinese", "logic_cohesion", "表达的逻辑与衔接", "利用过渡语、指代和顺序词组织连贯表达。", "每句话都要与前后内容接得上。", [
        _choice("cn_g5_lc_q1", "前文介绍纸张浪费，后文提出节约方法，中间最适合哪句？", skill="过渡句", choices=(("transition", "那么，我们怎样才能减少纸张浪费呢？"), ("unrelated", "天空中的云形态各异。"), ("repeat", "纸张就是纸张。")), answer="transition", hint="过渡句要承接问题并引出办法。", explanation="第一句既承接浪费问题，又引出解决方法。"),
        _sequence("cn_g5_lc_q2", "按“提出问题—分析原因—给出建议”排列。", skill="论述顺序", choices=(("problem", "有些同学忘记分类垃圾。"), ("reason", "主要原因是分类标识不够醒目。"), ("advice", "可以在桶盖上增加大图标。")), answer=("problem", "reason", "advice"), hint="先说现象，再找原因，最后解决。", explanation="问题、原因、建议构成完整逻辑链。"),
        _choice("cn_g5_lc_q3", "“小河水质改善了。___，近岸水域又出现了小鱼。”横线处最合适的是？", skill="结果衔接", choices=(("therefore", "因此"), ("however", "然而"), ("for_example", "例如")), answer="therefore", hint="后句是前句带来的结果。", explanation="这里是因果关系，应使用“因此”。"),
        _choice("cn_g5_lc_q4", "哪句话中的“它”指代清楚？", skill="指代衔接", choices=(("clear", "充电座旁只有一台机器人，它开始自动充电。"), ("unclear", "小猫追着小狗，它跑得很快。"), ("missing", "看见后，它很开心。")), answer="clear", hint="判断“它”之前是否只有一个可以指代的对象。", explanation="第一句中只有机器人可被“它”指代。"),
        _sequence("cn_g5_lc_q5", "按实验报告的基本顺序排列。", skill="应用文结构", choices=(("purpose", "实验目的"), ("process", "实验过程"), ("result", "实验结果")), answer=("purpose", "process", "result"), hint="先说明为什么做，再写怎么做和得到什么。", explanation="目的、过程、结果是清楚的报告顺序。"),
    ], estimated_minutes=11),
    _course(5, "chinese", "information_reading", "说明性文本阅读", "提取说明对象、方法、条件和结论。", "阅读短文：学校在两间相同的教室放置温度计。中午十二点，拉上遮光帘的教室是二十六摄氏度，未拉遮光帘的教室是二十九摄氏度。连续三天的记录都显示，拉帘教室温度较低。", [
        _choice("cn_g5_ir_q1", "比较的是哪两个条件？", skill="实验条件", choices=(("curtain", "拉帘与未拉帘"), ("large_small", "大教室与小教室"), ("morning_night", "早晨与夜晚")), answer="curtain", hint="两间教室的主要不同是什么？", explanation="实验比较是否拉遮光帘。"),
        _choice("cn_g5_ir_q2", "未拉帘教室中午多少摄氏度？", skill="数据提取", choices=(("29", "29℃"), ("26", "26℃"), ("3", "3℃")), answer="29", hint="定位“未拉遮光帘”。", explanation="未拉帘教室是29℃。"),
        _choice("cn_g5_ir_q3", "两间教室相差多少摄氏度？", skill="数据比较", choices=(("3", "3℃"), ("26", "26℃"), ("55", "55℃")), answer="3", hint="用29减26。", explanation="29-26=3℃。"),
        _choice("cn_g5_ir_q4", "记录持续了多久？", skill="时间提取", choices=(("three_days", "三天"), ("one_day", "一天"), ("week", "一周")), answer="three_days", hint="看最后一句。", explanation="记录连续进行了三天。"),
        _choice("cn_g5_ir_q5", "文本支持哪一结论？", skill="结论判断", choices=(("lower", "同样条件下拉遮光帘的教室温度较低"), ("higher", "拉帘一定使温度更高"), ("unrelated", "教室面积决定全部温度")), answer="lower", hint="结论要与三天数据一致。", explanation="三天记录都支持拉帘教室温度较低。"),
    ], estimated_minutes=11),
    _course(6, "chinese", "language_effects", "语言表达方法", "识别比喻、拟人、排比和常见说明方法。", "先观察句子的结构和关键词，再判断使用了哪种表达方法。", [
        _choice("cn_g6_le_q1", "“弯弯的月亮像一只小船”使用了什么修辞？", skill="比喻", choices=(("simile", "比喻"), ("personification", "拟人"), ("parallelism", "排比")), answer="simile", hint="句中用“像”连接两个事物。", explanation="把月亮比作小船，是比喻。"),
        _choice("cn_g6_le_q2", "“风跑过田野，叫醒了麦苗”使用了什么修辞？", skill="拟人", choices=(("personification", "拟人"), ("simile", "比喻"), ("question", "反问")), answer="personification", hint="风被写得像人一样会跑、会叫醒。", explanation="赋予风人的动作，是拟人。"),
        _choice("cn_g6_le_q3", "连续三个结构相近的分句最可能构成什么？", skill="排比", choices=(("parallelism", "排比"), ("quote", "引用"), ("contrast", "对比")), answer="parallelism", hint="关注“结构相近、连续三个”。", explanation="这样的表达通常构成排比。"),
        _choice("cn_g6_le_q4", "“这座桥长120米”主要使用什么说明方法？", skill="列数字", choices=(("numbers", "列数字"), ("example", "举例子"), ("metaphor", "打比方")), answer="numbers", hint="句中出现了精确数字。", explanation="用120米具体说明长度，属于列数字。"),
        _choice("cn_g6_le_q5", "“旧灯耗电较多，新灯更节能”主要使用什么说明方法？", skill="作比较", choices=(("compare", "作比较"), ("define", "下定义"), ("classify", "分类别")), answer="compare", hint="句中对照了旧灯和新灯。", explanation="把两种灯放在一起比较。"),
    ], estimated_minutes=11),
    _course(6, "chinese", "argument_evidence", "观点与证据", "区分观点、事实证据和无关材料，形成基础论证意识。", "先找作者想证明什么，再看材料能否支持它。", [
        _choice("cn_g6_ae_q1", "观点“学校应增加午间阅读时间”，哪个证据最有力？", skill="证据选择", choices=(("survey", "调查显示多数学生午间愿意阅读，试行班级的借阅量明显增加。"), ("weather", "本周天气晴朗。"), ("color", "图书馆墙壁是白色的。")), answer="survey", hint="证据要直接关联阅读时间和实际效果。", explanation="调查与试行数据能直接支持观点。"),
        _choice("cn_g6_ae_q2", "“我认为步行上学有助于锻炼身体”属于什么？", skill="观点辨认", choices=(("opinion", "观点"), ("number", "数据"), ("definition", "定义")), answer="opinion", hint="“我认为”表示判断和主张。", explanation="这是作者提出的观点。"),
        _choice("cn_g6_ae_q3", "“本月班级共回收废纸18千克”属于什么？", skill="事实证据", choices=(("fact", "可核查事实"), ("opinion", "个人愿望"), ("question", "疑问")), answer="fact", hint="它包含可以记录核对的数据。", explanation="该数据属于可核查事实。"),
        _sequence("cn_g6_ae_q4", "按简单论证顺序排列。", skill="论证结构", choices=(("claim", "提出观点"), ("evidence", "列出证据"), ("conclusion", "得出结论")), answer=("claim", "evidence", "conclusion"), hint="先让读者知道主张，再说明理由。", explanation="观点、证据、结论构成基本论证。"),
        _choice("cn_g6_ae_q5", "要证明“规律作息有助于保持课堂专注”，哪项材料无关？", skill="相关性判断", choices=(("unrelated", "校园花坛种了三种花。"), ("sleep", "连续记录显示早睡组上课走神次数较少。"), ("schedule", "作息表记录了每日入睡与起床时间。")), answer="unrelated", hint="材料必须与作息或专注有关。", explanation="花坛植物种类与观点无关。"),
    ], estimated_minutes=11),
    _course(6, "chinese", "practical_language", "实用表达", "根据对象和场合选择清楚、礼貌、简洁的表达。", "同一件事对不同的人说，语气和信息要合适。", [
        _choice("cn_g6_pl_q1", "向老师请假，哪种表达最合适？", skill="礼貌表达", choices=(("polite", "老师您好，我明天上午要去医院，想请半天假。"), ("rude", "我明天不来了。"), ("unclear", "那个事情就这样吧。")), answer="polite", hint="说明称呼、时间、原因和请求。", explanation="第一句信息完整且语气礼貌。"),
        _choice("cn_g6_pl_q2", "失物招领中最需要写清什么？", skill="信息完整", choices=(("details", "物品特征、拾取地点和联系方式"), ("weather", "当天的天气"), ("story", "一段想象故事")), answer="details", hint="让失主能确认并联系。", explanation="这些信息便于核验和领取物品。"),
        _sequence("cn_g6_pl_q3", "把活动通知的要素按便于阅读的顺序排列。", skill="通知结构", choices=(("event", "活动名称"), ("time_place", "时间和地点"), ("requirements", "参加要求")), answer=("event", "time_place", "requirements"), hint="先告诉大家是什么活动。", explanation="活动、时间地点、要求是清楚的通知顺序。"),
        _choice("cn_g6_pl_q4", "提醒同学保持安静，哪句话更得体？", skill="得体表达", choices=(("gentle", "这里有人阅读，请大家轻声交流。"), ("command", "都别说话！"), ("mock", "怎么连安静都做不到？")), answer="gentle", hint="既说明原因，又尊重对方。", explanation="第一句清楚、礼貌且有具体要求。"),
        _choice("cn_g6_pl_q5", "向社区提交建议，结尾最合适的是？", skill="应用文语气", choices=(("thanks", "感谢您阅读以上建议，期待您的回复。"), ("threat", "不同意就算了。"), ("casual", "就说到这里吧。")), answer="thanks", hint="正式建议应礼貌收束。", explanation="感谢并期待回复符合正式沟通语境。"),
    ], estimated_minutes=11),
)


PRIMARY_ENGLISH_COURSES = (
    _course(1, "english", "letters_sounds", "Letters and Sounds", "Recognize common English letters and their basic order.", "Look at each letter carefully and choose or arrange it.", [
        _choice("en_g1_ls_q1", "Which word begins with the /b/ sound?", skill="initial sound", choices=(("ball", "ball"), ("cat", "cat"), ("sun", "sun")), answer="ball", hint="Listen to the first sound: /b/.", explanation="Ball begins with the /b/ sound."),
        _choice("en_g1_ls_q2", "Which letter comes after B?", skill="alphabet order", choices=(("C", "C"), ("A", "A"), ("D", "D")), answer="C", hint="Say A, B, ...", explanation="C comes after B."),
        _sequence("en_g1_ls_q3", "Put the letters in alphabet order.", skill="alphabet order", choices=(("a", "A"), ("b", "B"), ("c", "C")), answer=("a", "b", "c"), hint="Start with A.", explanation="The order is A, B, C."),
        _choice("en_g1_ls_q4", "Which word begins with the letter d?", skill="initial letter", choices=(("dog", "dog"), ("cat", "cat"), ("sun", "sun")), answer="dog", hint="Listen for /d/.", explanation="Dog begins with d."),
        _choice("en_g1_ls_q5", "Which word begins with the /g/ sound?", skill="initial sound", choices=(("goat", "goat"), ("fish", "fish"), ("moon", "moon")), answer="goat", hint="Listen to the first sound: /g/.", explanation="Goat begins with the /g/ sound."),
    ], estimated_minutes=8),
    _course(1, "english", "greetings_names", "Greetings and Names", "Use basic greetings and say a name in a fixed sentence.", "Choose the greeting that fits the situation.", [
        _choice("en_g1_gn_q1", "What do you say when you meet someone?", skill="greeting", choices=(("hello", "Hello!"), ("bye", "Goodbye!"), ("thanks", "Thank you!")), answer="hello", hint="Choose a greeting for meeting.", explanation="Hello is used when meeting someone."),
        _choice("en_g1_gn_q2", "What do you say when you leave?", skill="farewell", choices=(("goodbye", "Goodbye!"), ("hello", "Hello!"), ("morning", "Good morning!")), answer="goodbye", hint="Choose the farewell.", explanation="Goodbye is used when leaving."),
        _exact("en_g1_gn_q3", "Complete: My ___ is Amy.", "name", skill="self introduction", hint="It tells what people call you.", explanation="The sentence is “My name is Amy.”", english=True),
        _choice("en_g1_gn_q4", "Someone says “Thank you.” What is a good reply?", skill="polite reply", choices=(("welcome", "You're welcome."), ("blue", "It is blue."), ("name", "My name is Tom.")), answer="welcome", hint="Choose the polite response to thanks.", explanation="“You're welcome” replies to “Thank you.”"),
        _sequence("en_g1_gn_q5", "Make a sentence.", skill="sentence order", choices=(("my", "My"), ("name", "name is"), ("sam", "Sam.")), answer=("my", "name", "sam"), hint="Start with My.", explanation="My name is Sam."),
    ], estimated_minutes=8),
    _course(1, "english", "colors_numbers", "Colors and Numbers", "Recognize basic color words and the number words one, two, three and five.", "Match simple English words with colors and numbers.", [
        _choice("en_g1_cn_q1", "Which word means 红色?", skill="colors", choices=(("red", "red"), ("blue", "blue"), ("green", "green")), answer="red", hint="It begins with r.", explanation="Red means 红色."),
        _choice("en_g1_cn_q2", "Which word means 蓝色?", skill="colors", choices=(("blue", "blue"), ("black", "black"), ("yellow", "yellow")), answer="blue", hint="It begins with bl.", explanation="Blue means 蓝色."),
        _choice("en_g1_cn_q3", "Which word means 3?", skill="numbers", choices=(("three", "three"), ("two", "two"), ("five", "five")), answer="three", hint="Count one, two, ...", explanation="Three means 3."),
        _exact("en_g1_cn_q4", "Write the English word for 1.", "one", skill="numbers", hint="It begins with o.", explanation="The English word for 1 is one.", english=True),
        _sequence("en_g1_cn_q5", "Put the numbers in order from 1 to 3.", skill="number order", choices=(("one", "one"), ("two", "two"), ("three", "three")), answer=("one", "two", "three"), hint="Begin with one.", explanation="The order is one, two, three."),
    ], estimated_minutes=8),
    _course(2, "english", "family_people", "Family and People", "Use basic family words and simple identity sentences.", "Choose the correct word for each person.", [
        _choice("en_g2_fp_q1", "My mother's mother is my ___.", skill="family words", choices=(("grandmother", "grandmother"), ("sister", "sister"), ("aunt", "aunt")), answer="grandmother", hint="She is one generation above your mother.", explanation="Your mother's mother is your grandmother."),
        _choice("en_g2_fp_q2", "My father's other son is my ___.", skill="family words", choices=(("brother", "brother"), ("mother", "mother"), ("grandma", "grandma")), answer="brother", hint="Choose a boy in the same generation.", explanation="Your father's other son is your brother."),
        _exact("en_g2_fp_q3", "Complete: She ___ my sister.", "is", skill="be verb", hint="Use the be verb for she.", explanation="The sentence is “She is my sister.”", english=True),
        _choice("en_g2_fp_q4", "Which pronoun can replace “Tom”?", skill="pronouns", choices=(("he", "he"), ("she", "she"), ("it", "it")), answer="he", hint="Tom is a boy's name.", explanation="He can replace Tom."),
        _sequence("en_g2_fp_q5", "Make a sentence.", skill="sentence order", choices=(("this", "This"), ("is", "is"), ("dad", "my dad.")), answer=("this", "is", "dad"), hint="Start with This.", explanation="This is my dad."),
    ], estimated_minutes=9),
    _course(2, "english", "school_objects", "School Objects", "Name common classroom objects and use this/that with singular nouns.", "Look at school items and complete simple sentences.", [
        _choice("en_g2_so_q1", "Which one is used for writing?", skill="school objects", choices=(("pencil", "pencil"), ("chair", "chair"), ("door", "door")), answer="pencil", hint="You hold it in your hand.", explanation="A pencil is used for writing."),
        _choice("en_g2_so_q2", "Which word means 书包?", skill="school objects", choices=(("schoolbag", "schoolbag"), ("book", "book"), ("desk", "desk")), answer="schoolbag", hint="It holds your books.", explanation="Schoolbag means 书包."),
        _exact("en_g2_so_q3", "Complete: This ___ a ruler.", "is", skill="this is", hint="Use the be verb for one object.", explanation="The sentence is “This is a ruler.”", english=True),
        _choice("en_g2_so_q4", "Which sentence asks about an object?", skill="basic questions", choices=(("what", "What is this?"), ("who", "Who is she?"), ("how", "How are you?")), answer="what", hint="Use What for a thing.", explanation="“What is this?” asks about an object."),
        _sequence("en_g2_so_q5", "Make a sentence.", skill="sentence order", choices=(("that", "That"), ("is", "is"), ("book", "a book.")), answer=("that", "is", "book"), hint="Start with That.", explanation="That is a book."),
    ], estimated_minutes=9),
    _course(2, "english", "actions_abilities", "Actions and Abilities", "Recognize common action verbs and use can/can't in fixed patterns.", "Choose what someone can do and build a simple sentence.", [
        _choice("en_g2_aa_q1", "Which word means 跑?", skill="action verbs", choices=(("run", "run"), ("read", "read"), ("sing", "sing")), answer="run", hint="It begins with r.", explanation="Run means 跑."),
        _choice("en_g2_aa_q2", "A sparrow can ___.", skill="can plus verb", choices=(("fly", "fly"), ("write", "write"), ("cook", "cook")), answer="fly", hint="Think about what a sparrow does with its wings.", explanation="A sparrow can fly."),
        _exact("en_g2_aa_q3", "Complete: I can ___ a book.", "read", skill="action verbs", hint="What do you do with a book?", explanation="You read a book.", english=True),
        _choice("en_g2_aa_q4", "Which sentence says “我会游泳”?", skill="ability sentence", choices=(("can", "I can swim."), ("like", "I like swimming."), ("see", "I see water.")), answer="can", hint="Use can for ability.", explanation="“I can swim” states an ability."),
        _sequence("en_g2_aa_q5", "Make a sentence that says she cannot dance.", skill="negative ability sentence", choices=(("she", "She"), ("cannot", "can't"), ("dance", "dance.")), answer=("she", "cannot", "dance"), hint="Put can't before the action.", explanation="She can't dance."),
    ], estimated_minutes=9),
    _course(3, "english", "self_introduction", "Self-introduction", "Use simple sentences to state name, age and preferences.", "Read short self-introduction patterns and choose the missing words.", [
        _exact("en_g3_si_q1", "Complete: My name ___ Lily.", "is", skill="be verb", hint="Use the be verb after My name.", explanation="The sentence is “My name is Lily.”", english=True),
        _choice("en_g3_si_q2", "Which question asks someone's age?", skill="asking age", choices=(("age", "How old are you?"), ("name", "What's your name?"), ("place", "Where are you?")), answer="age", hint="Look for old.", explanation="“How old are you?” asks age."),
        _exact("en_g3_si_q3", "Complete: I ___ nine years old.", "am", skill="be verb", hint="Use the be verb for I.", explanation="The sentence is “I am nine years old.”", english=True),
        _choice("en_g3_si_q4", "Which sentence expresses a preference?", skill="preferences", choices=(("like", "I like music."), ("age", "I am nine."), ("name", "I am Ben.")), answer="like", hint="A preference tells what someone enjoys.", explanation="“I like music” expresses a preference."),
        _sequence("en_g3_si_q5", "Make a sentence.", skill="sentence order", choices=(("i", "I"), ("live", "live in"), ("city", "Beijing.")), answer=("i", "live", "city"), hint="Start with I.", explanation="I live in Beijing."),
    ], estimated_minutes=10),
    _course(3, "english", "daily_routines", "Daily Routines", "Recognize routine verbs and simple present sentence order.", "Put everyday actions in a clear sentence or time order.", [
        _choice("en_g3_dr_q1", "Which phrase means 起床?", skill="routine phrases", choices=(("get_up", "get up"), ("go_bed", "go to bed"), ("have_lunch", "have lunch")), answer="get_up", hint="It is the first action after sleeping.", explanation="Get up means 起床."),
        _choice("en_g3_dr_q2", "I ___ breakfast at 7:00.", skill="verb collocation", choices=(("have", "have"), ("do", "do"), ("play", "play")), answer="have", hint="Think of the verb usually used with meals.", explanation="“Have breakfast” is the correct phrase."),
        _sequence("en_g3_dr_q3", "Put the morning actions in order.", skill="time order", choices=(("wake", "get up"), ("breakfast", "have breakfast"), ("school", "go to school")), answer=("wake", "breakfast", "school"), hint="Think about a normal school morning.", explanation="Get up, eat breakfast, then go to school."),
        _exact("en_g3_dr_q4", "Complete: She ___ to school at eight.", "goes", skill="third person singular", hint="Add -es to go after she.", explanation="The correct form is goes.", english=True),
        _choice("en_g3_dr_q5", "Which question asks about time?", skill="asking time", choices=(("when", "When do you get up?"), ("who", "Who is he?"), ("what", "What is this?")), answer="when", hint="Choose the question whose answer could be a clock time.", explanation="“When do you get up?” asks about time."),
    ], estimated_minutes=10),
    _course(3, "english", "short_reading", "Read a Short Note", "Find explicit people, places, times and actions in a short original English note.", "Read: Mia has a green lunch box. She puts an apple and two sandwiches in it. At noon, she eats with her friend Zoe under a big tree.", [
        _choice("en_g3_sr_q1", "What color is Mia's lunch box?", skill="reading details", choices=(("green", "green"), ("red", "red"), ("blue", "blue")), answer="green", hint="Read the first sentence.", explanation="The lunch box is green."),
        _choice("en_g3_sr_q2", "How many sandwiches are in the box?", skill="reading details", choices=(("two", "two"), ("one", "one"), ("three", "three")), answer="two", hint="Read the second sentence.", explanation="There are two sandwiches."),
        _choice("en_g3_sr_q3", "When does Mia eat?", skill="reading time", choices=(("noon", "at noon"), ("morning", "in the morning"), ("night", "at night")), answer="noon", hint="Read the last sentence.", explanation="Mia eats at noon."),
        _choice("en_g3_sr_q4", "Who eats with Mia?", skill="reading people", choices=(("zoe", "Zoe"), ("tom", "Tom"), ("amy", "Amy")), answer="zoe", hint="Find the word friend.", explanation="Her friend Zoe eats with her."),
        _choice("en_g3_sr_q5", "Where do they eat?", skill="reading place", choices=(("tree", "under a big tree"), ("room", "in a classroom"), ("bus", "on a bus")), answer="tree", hint="Read the last four words.", explanation="They eat under a big tree."),
    ], estimated_minutes=10),
    _course(4, "english", "time_schedule", "Time and Schedules", "Read clock times and use before/after in daily schedules.", "Use the timetable words to understand when things happen.", [
        _choice("en_g4_ts_q1", "Which phrase means 7:30?", skill="telling time", choices=(("seven_thirty", "seven thirty"), ("three_seven", "three seven"), ("seven_fifteen", "seven fifteen")), answer="seven_thirty", hint="Say the hour, then the minutes.", explanation="7:30 is seven thirty."),
        _choice("en_g4_ts_q2", "Lunch is ___ 12:00.", skill="time prepositions", choices=(("at", "at"), ("on", "on"), ("in", "in")), answer="at", hint="Clock times use a short time preposition.", explanation="We say “at 12:00.”"),
        _choice("en_g4_ts_q3", "Art is after math. Which lesson comes first?", skill="before and after", choices=(("math", "math"), ("art", "art"), ("unknown", "We cannot know.")), answer="math", hint="After means later than.", explanation="Math comes before art."),
        _sequence("en_g4_ts_q4", "Put the school day in time order.", skill="schedule order", choices=(("start", "classes start"), ("lunch", "have lunch"), ("home", "go home")), answer=("start", "lunch", "home"), hint="Think morning, noon, afternoon.", explanation="Classes start before lunch, and students go home later."),
        _exact("en_g4_ts_q5", "Complete: I go home ___ four o'clock.", "at", skill="time prepositions", hint="Clock times use a short time preposition.", explanation="The correct preposition is at.", english=True),
    ], estimated_minutes=10),
    _course(4, "english", "questions_answers", "Questions and Answers", "Match who/what/where/when questions with suitable answers.", "Find what information each question word asks for.", [
        _choice("en_g4_qa_q1", "___ is your science teacher?", skill="question words", choices=(("who", "Who"), ("where", "Where"), ("when", "When")), answer="who", hint="The answer will be a person.", explanation="Who asks about a person."),
        _choice("en_g4_qa_q2", "___ is the library?", skill="question words", choices=(("where", "Where"), ("who", "Who"), ("why", "Why")), answer="where", hint="The answer will be a place.", explanation="Where asks about a place."),
        _choice("en_g4_qa_q3", "___ do you have music class? On Friday.", skill="question words", choices=(("when", "When"), ("what", "What"), ("how", "How")), answer="when", hint="On Friday is a time answer.", explanation="When asks about time."),
        _choice("en_g4_qa_q4", "What is your favorite sport? Which answer fits?", skill="matching answers", choices=(("basketball", "Basketball."), ("monday", "On Monday."), ("school", "At school.")), answer="basketball", hint="The question asks for a sport.", explanation="Basketball is a sport."),
        _sequence("en_g4_qa_q5", "Make a question.", skill="question order", choices=(("where", "Where"), ("is", "is"), ("lab", "the science lab?")), answer=("where", "is", "lab"), hint="Start with the question word.", explanation="Where is the science lab?"),
    ], estimated_minutes=10),
    _course(4, "english", "reading_plan", "Read a Weekend Plan", "Identify explicit plan details and sequence from an original paragraph.", "Read: On Saturday morning, Leo will visit the city museum with his aunt. They will take the subway at nine. After lunch, they will buy vegetables and then go home.", [
        _choice("en_g4_rp_q1", "When will Leo visit the museum?", skill="reading time", choices=(("sat_morning", "Saturday morning"), ("sun_morning", "Sunday morning"), ("sat_night", "Saturday night")), answer="sat_morning", hint="Read the first five words.", explanation="Leo will visit on Saturday morning."),
        _choice("en_g4_rp_q2", "Who will go with Leo?", skill="reading people", choices=(("aunt", "his aunt"), ("uncle", "his uncle"), ("friend", "his friend")), answer="aunt", hint="Read the end of the first sentence.", explanation="His aunt will go with him."),
        _choice("en_g4_rp_q3", "How will they travel?", skill="reading transport", choices=(("subway", "by subway"), ("bus", "by bus"), ("bike", "by bike")), answer="subway", hint="Read the second sentence.", explanation="They will take the subway."),
        _choice("en_g4_rp_q4", "What time will they take it?", skill="reading time", choices=(("nine", "at nine"), ("eight", "at eight"), ("ten", "at ten")), answer="nine", hint="The time follows subway.", explanation="They will take it at nine."),
        _sequence("en_g4_rp_q5", "Put the plan in order.", skill="event sequence", choices=(("museum", "visit the museum"), ("vegetables", "buy vegetables"), ("home", "go home")), answer=("museum", "vegetables", "home"), hint="Follow the paragraph from start to finish.", explanation="Museum, vegetables, then home is the stated order."),
    ], estimated_minutes=10),
    _course(5, "english", "present_tenses", "Present Simple or Continuous", "Distinguish routines from actions happening now.", "Look for time clues such as every day and now.", [
        _choice("en_g5_pt_q1", "Nina ___ to school every day.", skill="present simple", choices=(("walks", "walks"), ("walking", "walking"), ("walk", "walk")), answer="walks", hint="Every day shows a routine; Nina is third person singular.", explanation="The correct form is walks."),
        _choice("en_g5_pt_q2", "Look! The dog ___ in the garden.", skill="present continuous", choices=(("running", "is running"), ("runs", "runs"), ("run", "run")), answer="running", hint="Look shows the action is happening now.", explanation="Use is running for an action happening now."),
        _exact("en_g5_pt_q3", "Complete: We ___ reading now.", "are", skill="present continuous", hint="Use the be verb for we.", explanation="The sentence is “We are reading now.”", english=True),
        _choice("en_g5_pt_q4", "Which sentence describes a habit?", skill="tense meaning", choices=(("habit", "I clean my desk every Friday."), ("now", "I am cleaning my desk now."), ("future", "I will clean it tomorrow.")), answer="habit", hint="Look for repeated time.", explanation="Every Friday marks a habit."),
        _sequence("en_g5_pt_q5", "Make a present continuous sentence.", skill="sentence order", choices=(("they", "They"), ("are", "are"), ("play", "playing chess.")), answer=("they", "are", "play"), hint="Put are between the subject and -ing verb.", explanation="They are playing chess."),
    ], estimated_minutes=11),
    _course(5, "english", "comparison_quantity", "Comparisons and Quantity", "Use comparative adjectives and common quantity words accurately.", "Compare two things and choose the quantity word that matches the noun.", [
        _choice("en_g5_cq_q1", "A giraffe is ___ than a goat.", skill="comparatives", choices=(("taller", "taller"), ("tallest", "tallest"), ("tall", "tall")), answer="taller", hint="Than signals a comparison of two things.", explanation="Use taller with than."),
        _choice("en_g5_cq_q2", "This box is ___ than that one.", skill="comparatives", choices=(("heavier", "heavier"), ("heavy", "heavy"), ("heaviest", "heaviest")), answer="heavier", hint="Use the comparative form before than.", explanation="Heavier is the comparative form of heavy."),
        _choice("en_g5_cq_q3", "How ___ apples are there?", skill="countable quantity", choices=(("many", "many"), ("much", "much"), ("long", "long")), answer="many", hint="Apples can be counted.", explanation="Use many with countable plural nouns."),
        _choice("en_g5_cq_q4", "How ___ water is in the bottle?", skill="uncountable quantity", choices=(("much", "much"), ("many", "many"), ("old", "old")), answer="much", hint="Water is not counted as separate items here.", explanation="Use much with uncountable water."),
        _exact("en_g5_cq_q5", "Complete: My bike is faster ___ yours.", "than", skill="comparative structure", hint="Use the comparison word after faster.", explanation="The correct structure is faster than.", english=True),
    ], estimated_minutes=11),
    _course(5, "english", "reading_experiment", "Read an Experiment Record", "Find conditions, measurements and results in an original English record.", "Read: Ben put one ice cube in sunlight and another in the shade. He checked them after ten minutes. The ice cube in sunlight was smaller. Both cubes began at the same size.", [
        _choice("en_g5_re_q1", "How many ice cubes did Ben use?", skill="reading details", choices=(("two", "two"), ("one", "one"), ("three", "three")), answer="two", hint="One was in sunlight and another was in shade.", explanation="Ben used two ice cubes."),
        _choice("en_g5_re_q2", "Where did he put the cube described first?", skill="reading conditions", choices=(("sunlight", "in sunlight"), ("freezer", "in a freezer"), ("water", "in water")), answer="sunlight", hint="Read the first clause.", explanation="The cube described first was in sunlight."),
        _choice("en_g5_re_q3", "When did he check them?", skill="reading time", choices=(("ten", "after ten minutes"), ("hour", "after one hour"), ("day", "the next day")), answer="ten", hint="Read the second sentence.", explanation="He checked them after ten minutes."),
        _choice("en_g5_re_q4", "Which cube was smaller?", skill="reading results", choices=(("sun", "the cube in sunlight"), ("shade", "the cube in shade"), ("same", "neither cube")), answer="sun", hint="Read the third sentence.", explanation="The cube in sunlight was smaller."),
        _choice("en_g5_re_q5", "What was the same at the start?", skill="controlled variables", choices=(("size", "the cubes' size"), ("place", "their place"), ("result", "their final size")), answer="size", hint="Read the last sentence.", explanation="Both cubes began at the same size."),
    ], estimated_minutes=11),
    _course(6, "english", "past_events", "Past Events", "Use regular and common irregular past-tense forms in simple contexts.", "Look for yesterday or last week, then choose the past form.", [
        _choice("en_g6_pe_q1", "Yesterday, we ___ the science museum.", skill="regular past", choices=(("visited", "visited"), ("visit", "visit"), ("visiting", "visiting")), answer="visited", hint="Yesterday needs the past form.", explanation="Visited is the past form of visit."),
        _choice("en_g6_pe_q2", "Last night, Mia ___ a short story.", skill="irregular past", choices=(("wrote", "wrote"), ("writes", "writes"), ("writing", "writing")), answer="wrote", hint="Use the past form of write.", explanation="Wrote is the past form of write."),
        _choice("en_g6_pe_q3", "Tom ___ home early yesterday.", skill="irregular past", choices=(("went", "went"), ("goes", "goes"), ("go", "go")), answer="went", hint="The past form of go is irregular.", explanation="Went is the past form of go."),
        _exact("en_g6_pe_q4", "Write the past form of play.", "played", skill="regular past", hint="Add -ed.", explanation="The past form of play is played.", english=True),
        _sequence("en_g6_pe_q5", "Make a past-tense sentence.", skill="sentence order", choices=(("we", "We"), ("watched", "watched"), ("film", "a film yesterday.")), answer=("we", "watched", "film"), hint="Put the past verb after the subject.", explanation="We watched a film yesterday."),
    ], estimated_minutes=11),
    _course(6, "english", "connectors_reasons", "Connectors and Reasons", "Use because, so, but and if to express clear relationships.", "Decide whether the ideas show cause, result, contrast or condition.", [
        _choice("en_g6_cr_q1", "I stayed inside ___ it was raining.", skill="cause connector", choices=(("because", "because"), ("but", "but"), ("if", "if")), answer="because", hint="The second part gives the reason.", explanation="Because introduces a reason."),
        _choice("en_g6_cr_q2", "It was raining, ___ I took an umbrella.", skill="result connector", choices=(("so", "so"), ("because", "because"), ("or", "or")), answer="so", hint="Taking an umbrella is the result.", explanation="So introduces the result."),
        _choice("en_g6_cr_q3", "The bag is small, ___ it is strong.", skill="contrast connector", choices=(("but", "but"), ("so", "so"), ("because", "because")), answer="but", hint="The second idea contrasts with the first.", explanation="But shows contrast."),
        _choice("en_g6_cr_q4", "Which word makes finishing early a condition? ___ you finish early, you can help the group.", skill="condition connector", choices=(("if", "If"), ("because", "Because"), ("but", "But")), answer="if", hint="The sentence asks for a condition, not a reason or contrast.", explanation="If introduces a condition."),
        _sequence("en_g6_cr_q5", "Make a cause sentence.", skill="sentence order", choices=(("we", "We stayed home"), ("because", "because"), ("storm", "there was a storm.")), answer=("we", "because", "storm"), hint="Put because before the reason.", explanation="We stayed home because there was a storm."),
    ], estimated_minutes=11),
    _course(6, "english", "reading_information", "Read and Compare Information", "Compare explicit facts and draw one supported conclusion from an original text.", "Read: Green Club tested two ways to water young plants. Group A received a little water every morning. Group B received the same total amount once every three days. After two weeks, 18 of 20 plants in Group A were healthy, while 12 of 20 in Group B were healthy.", [
        _choice("en_g6_ri_q1", "How often did Group A get water?", skill="reading frequency", choices=(("daily", "every morning"), ("three_days", "once every three days"), ("weekly", "once a week")), answer="daily", hint="Read the second sentence.", explanation="Group A received water every morning."),
        _choice("en_g6_ri_q2", "How long did the test last?", skill="reading duration", choices=(("two_weeks", "two weeks"), ("two_days", "two days"), ("month", "one month")), answer="two_weeks", hint="Read the final sentence.", explanation="The test lasted two weeks."),
        _choice("en_g6_ri_q3", "How many Group A plants were healthy?", skill="reading data", choices=(("18", "18"), ("12", "12"), ("20", "20")), answer="18", hint="Find Group A in the last sentence.", explanation="18 Group A plants were healthy."),
        _choice("en_g6_ri_q4", "Which group had more healthy plants?", skill="data comparison", choices=(("A", "Group A"), ("B", "Group B"), ("same", "They were the same.")), answer="A", hint="Compare 18 and 12.", explanation="Group A had 18 healthy plants, more than Group B's 12."),
        _choice("en_g6_ri_q5", "Which conclusion is supported by this test?", skill="evidence conclusion", choices=(("supported", "For these plants and conditions, daily watering was associated with more healthy plants."), ("all", "Every plant always needs daily watering."), ("none", "Watering frequency never matters.")), answer="supported", hint="Choose the statement limited to this test without claiming proven cause.", explanation="The first conclusion reports an association limited to this test."),
    ], estimated_minutes=11),
)


PRIMARY_COURSE_CATALOG = tuple(
    _math_course_with_contract(course) for course in PRIMARY_MATH_COURSES
) + PRIMARY_CHINESE_COURSES + PRIMARY_ENGLISH_COURSES
