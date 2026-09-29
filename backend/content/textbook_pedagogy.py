"""Grade-specific teaching constraints frozen into new textbook course briefs."""
from copy import deepcopy
import json
from pathlib import Path

LOW_READING_POLICY = json.loads((Path(__file__).parent / 'low_reading_policy.v1.json').read_text())

PROFILES = {
    "primary_1": {
        "readingMode": "pre_reader", "maxVisibleCharactersPerScene": 24, "maxInstructionCharacters": 16,
        "minVisualSceneRatio": 0.8, "maxTasksPerScene": 1, "maxNarrationSegmentSeconds": 30,
        "responseModes": ["point", "picture_choice", "speak", "act"],
        "rules": ["默认学生尚不识字、未学拼音，不能依赖阅读题干、选项或按钮长文完成操作。",
                  "每屏一个任务、一句短提示；目标汉字可以单独放大，其余主要用有教学作用的原创插画、示范动画或短视频。",
                  "指令、问题和选后反馈都必须有提前合成的语音；看图选择、指一指、跟读或动手为主要回应方式。",
                  "先给具体生活情境，再观察和模仿；留出回答时间，不自动跳过孩子的操作。",
                  "画面必须对应当前讲解，不能用背景装饰代替教学图。视频如使用，须有可暂停重播的配音和字幕。"]},
    "primary_2": {
        "readingMode": "picture_supported_reader", "maxVisibleCharactersPerScene": 24, "maxInstructionCharacters": 16,
        "minVisualSceneRatio": 0.8, "maxTasksPerScene": 1, "maxNarrationSegmentSeconds": 35,
        "responseModes": ["point", "picture_choice", "speak", "act"],
        "rules": ["默认仍不能独立读题，问题和选项必须有可理解的图像与语音，文字只作辅助。", "一屏一个任务，用具体事物帮助识字、复述和简单比较。"]},
    "primary_3": {
        "readingMode": "guided_reader", "maxVisibleCharactersPerScene": 90, "maxInstructionCharacters": 36,
        "minVisualSceneRatio": 0.5, "maxTasksPerScene": 2, "maxNarrationSegmentSeconds": 40,
        "responseModes": ["short_reading", "compare", "explain"],
        "rules": ["逐步增加短段阅读，用图示帮助抓住关键信息。", "先示范如何寻找依据，再让学生解释一个简单原因。"]},
    "primary_4": {
        "readingMode": "independent_reader", "maxVisibleCharactersPerScene": 120, "maxInstructionCharacters": 40,
        "minVisualSceneRatio": 0.45, "maxTasksPerScene": 2, "maxNarrationSegmentSeconds": 45,
        "responseModes": ["read", "compare", "explain", "organize"],
        "rules": ["以阅读、图示和归纳结合，支持用自己的话说明依据。", "增加比较、整理和迁移任务，避免套用一年级的幼儿情境。"]},
    "primary_5": {
        "readingMode": "analytical_reader", "maxVisibleCharactersPerScene": 160, "maxInstructionCharacters": 48,
        "minVisualSceneRatio": 0.35, "maxTasksPerScene": 2, "maxNarrationSegmentSeconds": 50,
        "responseModes": ["read", "analyze", "justify", "apply"],
        "rules": ["使用结构图、证据比较和方法示范，让学生解释推理过程。", "内容更深入但每屏重点明确；插画服务知识关系，不使用幼儿化奖励和口吻。"]},
    "primary_6": {
        "readingMode": "critical_reader", "maxVisibleCharactersPerScene": 180, "maxInstructionCharacters": 56,
        "minVisualSceneRatio": 0.3, "maxTasksPerScene": 2, "maxNarrationSegmentSeconds": 50,
        "responseModes": ["read", "analyze", "justify", "transfer"],
        "rules": ["增加证据、观点比较、归纳与迁移；图表和示范服务抽象思考。", "允许自主阅读和回看讲解，追问为什么，不套用低年级识字前的交互和语气。"]},
}


LEGACY_PROFILES = deepcopy(PROFILES)
LEGACY_PROFILES['primary_2'] = {
    "readingMode": "emerging_reader", "maxVisibleCharactersPerScene": 48, "maxInstructionCharacters": 24,
    "minVisualSceneRatio": 0.65, "maxTasksPerScene": 1, "maxNarrationSegmentSeconds": 35,
    "responseModes": ["picture_choice", "short_reading", "speak", "act"],
    "rules": ["图画和语音支撑短句阅读，不假设已掌握未教生字。", "一屏一个任务，用具体事物帮助识字、复述和简单比较。"]}


def teaching_profile(grade_code, *, version=2):
    if version not in (1, 2):
        raise ValueError('Unknown teaching profile version')
    if grade_code not in LOW_READING_POLICY['grades']:
        version = 1
    profiles = LEGACY_PROFILES if version == 1 else PROFILES
    profile = {"schemaVersion": f"mira.textbook.grade-pedagogy.v{version}", "gradeCode": grade_code, **deepcopy(profiles[grade_code])}
    if version == 2 and grade_code in LOW_READING_POLICY['grades']:
        profile['lowReadingPolicy'] = deepcopy(LOW_READING_POLICY)
        profile['rules'].extend(LOW_READING_POLICY['rules'])
    return profile
