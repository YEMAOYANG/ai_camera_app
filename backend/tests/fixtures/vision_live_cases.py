from __future__ import annotations

from dataclasses import dataclass, field

from tests.fixtures.vision_regression_cases import (
    VISION_REGRESSION_CASES,
    VisionRegressionExpectation,
)


def _expect_for(case_id: str) -> VisionRegressionExpectation:
    case = next(item for item in VISION_REGRESSION_CASES if item.case_id == case_id)
    return case.expect


@dataclass(frozen=True)
class VisionLiveCase:
    case_id: str
    title: str
    image_filename: str
    expect: VisionRegressionExpectation
    notes: str = ""
    context: dict = field(default_factory=dict)
    tags: tuple[str, ...] = field(default_factory=tuple)


VISION_IMAGES_ROOT = "tests/fixtures/vision_images"

# Live cases reuse offline expectations where possible.
# Image files are optional and gitignored; missing images skip the subtest.
VISION_LIVE_CASES: tuple[VisionLiveCase, ...] = (
    VisionLiveCase(
        case_id="homework_bad_posture",
        title="真实帧：学习低头/趴桌",
        image_filename="posture/homework_low_head.jpg",
        expect=_expect_for("homework_bad_posture"),
        notes="需绑定儿童在场、书桌/书本可见。",
        context={"child_reference": "小爱", "age_stage": "小学低年级"},
        tags=("posture", "homework"),
    ),
    VisionLiveCase(
        case_id="homework_good_posture",
        title="真实帧：正常写作业坐姿",
        image_filename="posture/homework_good_posture.jpg",
        expect=_expect_for("homework_good_posture"),
        notes="不应生成 posture reminder payload。",
        context={"child_reference": "小爱", "age_stage": "小学低年级"},
        tags=("posture", "homework", "negative"),
    ),
    VisionLiveCase(
        case_id="meal_standing_on_chair",
        title="真实帧：用餐站椅子",
        image_filename="meal/meal_standing_on_chair.jpg",
        expect=_expect_for("meal_standing_on_chair"),
        notes="需在餐窗内或明显用餐场景。",
        context={"child_reference": "小爱", "age_stage": "小学低年级"},
        tags=("meal", "etiquette"),
    ),
    VisionLiveCase(
        case_id="meal_distracted_phone",
        title="真实帧：用餐看手机/分心",
        image_filename="meal/meal_distracted_phone.jpg",
        expect=_expect_for("meal_distracted_phone"),
        notes="需手机可见且用餐上下文明确。",
        context={"child_reference": "小爱", "age_stage": "小学低年级"},
        tags=("meal", "etiquette", "screen"),
    ),
)
