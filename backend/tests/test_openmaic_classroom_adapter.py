from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from content.primary_skill_boundaries import boundaries_for
from integrations.openmaic_classroom_adapter import OpenMaicClassroomAdapter


def _course(grade_code: str, subject: str) -> dict:
    questions = [
        {
            "id": "q1",
            "type": "numeric",
            "prompt": "例题：7+5=?",
            "explanation": "把5分成3和2，7加3等于10，再加2等于12。",
        }
    ]
    return {
        "grade_code": grade_code,
        "subject": subject,
        "content_json": json.dumps(
            {
                "questions": questions,
                "teachingFlow": {
                    "teach": {
                        "title": "先学方法",
                        "sayText": "先看清题意，再学习本节课的方法。",
                        "keyPoints": ["看清题意", "按步骤思考"],
                    },
                    "demoQuestionId": "q1",
                    "guidedQuestionIds": ["q2", "q3"],
                    "independentQuestionIds": ["q4", "q5"],
                    "recap": {"sayText": "回顾本节课的方法。"},
                },
            },
            ensure_ascii=False,
        ),
    }


class OpenMaicClassroomAdapterTest(unittest.TestCase):
    def test_contract_requests_only_native_scenes_and_sidecar_safe_limits(self):
        calls = []

        def runner(command, **kwargs):
            payload = json.loads(kwargs["input"])
            calls.append(payload)
            response = {
                "schemaVersion": "mira.openmaic.classroom_intent.v2",
                "dslVersion": "0.1.0",
                "generator": "openmaic",
                "requestId": payload["requestId"],
                "status": "unverified",
                "publicationEligible": False,
                "authoritativeAnswersProvided": False,
                "classroom": {"scenes": []},
            }
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(response),
                stderr="",
            )

        adapter = OpenMaicClassroomAdapter(
            sidecar_root=Path(__file__).resolve().parents[1] / "openmaic-sidecar",
            fake_mode=True,
            process_runner=runner,
        )
        adapter.generate(
            request_id="classroom-adapter-contract",
            course=_course("primary_3", "math"),
            skill_boundary={"skillId": "multi_digit_operations"},
            public_questions=[
                {"id": f"q{index}", "type": "numeric", "prompt": "计算"}
                for index in range(2, 6)
            ],
        )

        self.assertEqual(len(calls), 1)
        request = calls[0]
        options = request["classroomOptions"]
        self.assertEqual(options["allowedSceneTypes"], ["slide", "interactive", "quiz"])
        self.assertEqual(options["requiredSceneTypes"], ["slide", "interactive", "quiz"])
        self.assertEqual(options["quizMode"], "independent")
        self.assertEqual(options["maxScenes"], 5)
        self.assertEqual(options["maxHtmlChars"], 1_000)
        self.assertEqual(request["questionRefs"], ["q2", "q3", "q4", "q5"])
        self.assertEqual(request["assets"], [])
        self.assertEqual(request["courseTeaching"]["workedExample"]["questionId"], "q1")
        self.assertNotIn("answer", json.dumps(request["courseTeaching"]).lower())

    def test_real_node_sidecar_compiles_generic_outlines_before_review(self):
        outlines = [
            {
                "phaseRole": "teach",
                "type": "slide",
                "title": "先认识数量",
                "description": "把物体一个一个对应起来，观察多少。",
                "keyPoints": ["一个对应一个", "数到哪里就停在哪里"],
                "layoutTemplate": "concept_focus.v1",
                "misconceptions": ["漏数一个物体", "重复数同一个物体"],
                "assetBrief": [],
            },
            {
                "phaseRole": "demo",
                "type": "slide",
                "title": "老师示范",
                "description": "老师示范怎样按顺序数一组物体。",
                "keyPoints": ["按顺序数", "最后一个数表示总数"],
            },
            {
                "phaseRole": "guided",
                "type": "interactive",
                "title": "一起数一数",
                "description": "跟着提示完成两次选择。",
                "keyPoints": [],
                "widgetTemplate": "listen_tap_choice.v1",
                "gameRules": {
                    "goal": "完成两道数量辨认",
                    "instructions": ["先观察", "再选择", "听反馈后继续"],
                    "successCriterion": "完成两道服务器判定的练习",
                    "maxAttempts": 2,
                    "feedbackMode": "encouraging_retry",
                },
            },
            {
                "phaseRole": "independent",
                "type": "quiz",
                "title": "我自己试一试",
                "description": "独立完成最后两道练习。",
                "keyPoints": [],
            },
            {
                "phaseRole": "recap",
                "type": "slide",
                "title": "回顾方法",
                "description": "回顾按顺序数和一一对应的方法。",
                "keyPoints": ["按顺序", "一一对应"],
            },
        ]
        generic = json.dumps({"courseTitle": "20 以内数感", "outlines": outlines})
        compiled = json.dumps({"outlines": outlines})
        review = json.dumps({"passed": True, "issues": []})
        boundary = boundaries_for("primary_1", "math")[0].to_openmaic_payload()
        public_questions = [
            {
                "id": f"q{index}",
                "type": "single_choice",
                "prompt": f"观察第 {index - 1} 组物体，选择数量。",
                "choices": [
                    {"id": "a", "label": "较少"},
                    {"id": "b", "label": "较多"},
                ],
            }
            for index in range(2, 6)
        ]
        adapter = OpenMaicClassroomAdapter(
            sidecar_root=Path(__file__).resolve().parents[1] / "openmaic-sidecar",
            provider_name="kimi",
            model_name="kimi-k2.6",
            base_url="https://api.moonshot.cn/v1",
            fake_mode=True,
            fake_responses=[generic, compiled, review],
        )

        result = adapter.generate(
            request_id="classroom-real-node-intent-compiler",
            course=_course("primary_1", "math"),
            skill_boundary=boundary,
            public_questions=public_questions,
        )

        self.assertFalse(result.source["publicationEligible"])
        self.assertFalse(result.source["authoritativeAnswersProvided"])
        intent = result.source["classroom"]["intent"]
        self.assertEqual(intent["layoutTemplate"], "concept_focus.v1")
        self.assertEqual(intent["widgetTemplate"], "listen_tap_choice.v1")
        self.assertEqual(intent["guided"]["questionRefs"], ["q2", "q3"])
        self.assertEqual(intent["independent"]["questionRefs"], ["q4", "q5"])
        serialized = json.dumps(result.source).lower()
        for forbidden in ("correctanswer", "expectedanswer", "authoritativeanswersprovided\": true"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
