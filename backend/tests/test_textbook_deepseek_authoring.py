from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from content.textbook_catalog import digest
from services.textbook_batch_generation_service import atomic_json
from services.textbook_deepseek_authoring import (BLUEPRINT_SCHEMA, PATCH_SCHEMA, DeepSeekTextbookAuthoring,
                                                STAGES, apply_reviewed_patch, check_blueprint, patch_targets,
                                                resolve_blueprint, sha)


def fixture():
    source = {"taskId": "a" * 64, "binding": {"subject": "chinese"}, "activityGoalIds": ["meaning"],
              "outstandingGoalIds": ["full_text"]}
    blueprint = {"schemaVersion": BLUEPRINT_SCHEMA, **source,
        "activities": [{"activityId": "a1", "teacherText": "看图，比较两种不同的动作。", "goalIds": ["meaning"],
            "visual": {"newPictureDescription": "一人在说话，另一人在听。"},
            "interaction": {"type": "oral_response", "choices": [], "spokenPrompt": "谁在听？",
                "waitForStudentBeforeModel": True, "modelAnswer": "面对说话人，安静听话的孩子。"}}],
        "goalEvidence": [{"goalId": "meaning", **{stage: ["a1"] for stage in STAGES},
                          "coverageExplanation": "测试引用有效，不代表真实教学充分。"}],
        "lessonPlan": {"sessions": [{"activityIds": ["a1"]}]},
        "mediaDesign": {"video": [{}], "threeD": [{}]}, "unresolved": []}
    return source, blueprint


class DeepSeekAuthoringTests(unittest.TestCase):
    def test_long_saved_revision_chain_keeps_early_response_integrity(self):
        source, blueprint = fixture()
        pointer = "/activities/0/teacherText"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            request = {"taskId": source["taskId"], "source": source, "sourceFiles": {}}
            request["requestSha256"] = digest(request)
            response = {"model": "deepseek-v4-pro", "choices": [{"finish_reason": "stop",
                "message": {"content": json.dumps(blueprint)}}]}
            for index in range(15):
                folder = root / str(index)
                folder.mkdir()
                review = {"taskId": source["taskId"], "allowedPaths": [pointer]}
                for name, value in (("request", request), ("response", response), ("review", review)):
                    atomic_json(folder / (name + ".json"), value)
                paths = {key + "Path": str(folder / (key + ".json"))
                         for key in ("request", "response", "review")}
                patch_value = {"schemaVersion": PATCH_SCHEMA, "parentBlueprintSha256": digest(blueprint),
                    "operations": [{"op": "replace", "path": pointer, "value": f"合成讲解第{index}次修订。"}]}
                next_request = {"purpose": "reviewed_content_patch", "taskId": source["taskId"],
                    "source": source, "parentRequestSha256": request["requestSha256"],
                    "sourceFiles": {path: sha(path) for path in paths.values()},
                    "patchParent": {**paths, "allowedPaths": [pointer]}}
                next_request["requestSha256"] = digest(next_request)
                request = next_request
                response = {"model": "deepseek-v4-pro", "choices": [{"finish_reason": "stop",
                    "message": {"content": json.dumps(patch_value)}}]}
                blueprint = apply_reviewed_patch(blueprint, patch_value, [pointer])
            self.assertEqual(resolve_blueprint(request, response), blueprint)
            bad = deepcopy(request)
            bad["taskId"] = "changed"
            with self.assertRaisesRegex(ValueError, "patch_lineage_identity_changed"):
                resolve_blueprint(bad, response)
            early = root / "0/response.json"
            early.write_text(early.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "patch_lineage_bytes_changed"):
                resolve_blueprint(request, response)

    def test_target_context_keeps_actual_activity_id_and_zero_based_path_together(self):
        _, blueprint = fixture()
        blueprint["activities"] += [{**deepcopy(blueprint["activities"][0]), "activityId": "a15", "teacherText": "我字的合成说明"}]
        result = patch_targets(blueprint, ["/activities/1/teacherText"])
        self.assertEqual(result, [{"path": "/activities/1/teacherText", "currentValue": "我字的合成说明",
                                 "activityContext": blueprint["activities"][1]}])
        result[0]["activityContext"]["teacherText"] = "changed"
        self.assertEqual(blueprint["activities"][1]["teacherText"], "我字的合成说明")
        for paths in (["/activities/15/teacherText"], ["/binding"], ["/activities/1"],
                      ["/activities/1/teacherText", "/activities/1/teacherText"]):
            with self.subTest(paths=paths), self.assertRaises(ValueError):
                patch_targets(blueprint, paths)

    def test_patch_preserves_unreviewed_text_and_rejects_scope_changes(self):
        source, blueprint = fixture()
        pointer = "/activities/0/teacherText"
        response = {"schemaVersion": PATCH_SCHEMA, "parentBlueprintSha256": digest(blueprint),
                    "operations": [{"op": "replace", "path": pointer, "value": "这是合成测试中的模型修订。"}]}
        revised = apply_reviewed_patch(blueprint, response, [pointer])
        self.assertNotEqual(revised["activities"][0]["teacherText"], blueprint["activities"][0]["teacherText"])
        self.assertEqual(revised["activities"][0]["interaction"], blueprint["activities"][0]["interaction"])
        self.assertTrue(check_blueprint(revised, source)["structurePassed"])
        for case in ("scope", "missing", "extra", "type", "source"):
            other = deepcopy(response)
            allowed = [pointer]
            if case == "scope":
                allowed = ["/binding"]
                other["operations"][0].update(path="/binding", value={})
            elif case == "missing":
                other["operations"] = []
            elif case == "extra":
                other["operations"].append(deepcopy(other["operations"][0]))
            elif case == "type":
                other["operations"][0]["value"] = []
            else:
                other["parentBlueprintSha256"] = "f" * 64
            with self.subTest(case=case), self.assertRaises(ValueError):
                apply_reviewed_patch(blueprint, other, allowed)

    def test_missing_depth_refs_and_answer_before_attempt_rejected(self):
        source, blueprint = fixture()
        self.assertTrue(check_blueprint(blueprint, source)["structurePassed"])
        self.assertFalse(check_blueprint(blueprint, source)["semanticReviewPassed"])
        for kind in ("missing", "invented", "unbound", "answer_first", "unfinished", "schedule"):
            other = deepcopy(blueprint)
            if kind == "missing":
                other["goalEvidence"][0]["transfer"] = []
            elif kind == "invented":
                other["goalEvidence"][0]["retrieval"] = ["absent"]
            elif kind == "unbound":
                other["activities"][0]["goalIds"] = ["other"]
            elif kind == "answer_first":
                other["activities"][0]["interaction"]["waitForStudentBeforeModel"] = False
            elif kind == "unfinished":
                other["outstandingGoalIds"] = []
            else:
                other["lessonPlan"]["sessions"][0]["activityIds"] = []
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                check_blueprint(other, source)

    def request(self, directory):
        source, blueprint = fixture()
        value = {"taskId": source["taskId"], "source": source, "sourceFiles": {},
            "endpoint": "https://api.deepseek.com/v1/chat/completions", "payload": {"model": "deepseek-v4-pro"}}
        value["requestSha256"] = digest(value)
        folder = Path(directory) / source["taskId"] / value["requestSha256"]
        folder.mkdir(parents=True)
        atomic_json(folder / "request.json", value)
        return folder, blueprint

    @patch("services.textbook_deepseek_authoring.provider_config",
           return_value=("https://api.deepseek.com/v1", "deepseek-v4-pro", "synthetic-test-key"))
    def test_success_preserves_raw_response_and_does_not_dispatch_twice(self, _config):
        with tempfile.TemporaryDirectory() as tmp:
            folder, blueprint = self.request(tmp)
            response = {"id": "response1", "model": "deepseek-v4-pro", "usage": {"total_tokens": 123},
                        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(blueprint)}}]}
            calls = []
            def opener(request, **kwargs):
                calls.append(request)
                self.assertTrue((folder / "dispatch.json").exists())
                return BytesIO(json.dumps(response).encode())
            service = DeepSeekTextbookAuthoring(tmp, opener=opener)
            self.assertEqual(service.run(folder)["status"], "generated_needs_semantic_review")
            self.assertEqual(service.run(folder)["usage"], {"total_tokens": 123})
            self.assertEqual(len(calls), 1)
            self.assertEqual(json.loads((folder / "response.json").read_text()), response)
            self.assertNotIn("synthetic-test-key", "".join(p.read_text() for p in folder.glob("*.json")))

    @patch("services.textbook_deepseek_authoring.provider_config",
           return_value=("https://api.deepseek.com/v1", "deepseek-v4-pro", "synthetic-test-key"))
    def test_network_unknown_and_truncated_paid_results_are_never_retried(self, _config):
        for truncated in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                folder, _ = self.request(tmp)
                calls = []
                def opener(request, **kwargs):
                    calls.append(request)
                    if not truncated:
                        raise TimeoutError("not safe to replay")
                    return BytesIO(json.dumps({"model": "deepseek-v4-pro", "id": "r2", "usage": {},
                        "choices": [{"finish_reason": "length", "message": {"content": "{"}}]}).encode())
                service = DeepSeekTextbookAuthoring(tmp, opener=opener)
                expected = "response_preserved_needs_repair" if truncated else "outcome_unknown_fenced"
                self.assertEqual(service.run(folder)["status"], expected)
                self.assertEqual(service.run(folder)["status"], expected)
                self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
