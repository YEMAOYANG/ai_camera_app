from copy import deepcopy
import json
import shutil
import subprocess
import unittest

from content.textbook_deepseek_activity import pages_scene, role_scene
from content.textbook_interactive_narration import interactive_cues
from services.textbook_batch_queue_audio_service import _Markup, _reviewed_deepseek_picture_pages


def fixture():
    assets = {key: {"src": "/api/classroom-media/test/media/atlas.png", "width": 1200, "height": 800,
                   "crop": [i / 3, 0, 1 / 3, 1], "sha256": "a" * 64, "description": key}
              for i, key in enumerate(("coral", "teal", "yellow"))}
    page = {"pageId": "p1", "activityId": "a1", "kind": "choose_picture", "assetKey": "coral",
            "targetCharacters": ["我"], "teacherCueId": "teacher", "promptCueId": "question",
            "retryCueId": None, "modelCueId": None, "completeCueId": None,
            "correctChoiceIds": ["coral"], "choices": [
                {"choiceId": key, "assetKey": key, "buttonId": "p1_" + key, "feedbackCueId": key}
                for key in assets]}
    scene = {"sceneId": "s1", "title": "合成测试场景", "renderer": "deepseek_picture_pages",
             "pages": [page], "finiteCues": [{"cueId": key, "teacherText": "合成测试台词" + key}
                                             for key in ("teacher", "question", *assets)]}
    frozen = {"activityDesign": {"lessonFamily": "deepseek_picture_book_v1", "scenes": [scene],
                                "compiledImageAssets": assets}}
    return frozen, scene, assets


class DeepSeekPicturePageTests(unittest.TestCase):
    def test_saved_design_key_order_preserves_exact_renderer_admission(self):
        frozen, scene, assets = fixture()
        html = pages_scene(scene, assets)
        persisted = json.loads(json.dumps(frozen, sort_keys=True))
        self.assertTrue(_reviewed_deepseek_picture_pages(persisted, {"id": "s1"}, html))
        self.assertFalse(_reviewed_deepseek_picture_pages(persisted, {"id": "s1"}, html + "<p>unreviewed</p>"))

    def test_repeated_portraits_across_questions_are_allowed_but_duplicate_choices_are_not(self):
        frozen, scene, assets = fixture()
        second = deepcopy(scene["pages"][0])
        second["pageId"] = "p2"
        for choice in second["choices"]:
            choice["buttonId"] = "p2_" + choice["choiceId"]
        scene["pages"].append(second)
        html = pages_scene(scene, assets)
        self.assertTrue(_reviewed_deepseek_picture_pages(frozen, {"id": "s1"}, html))
        self.assertFalse(_reviewed_deepseek_picture_pages(frozen, {"id": "s1"}, html + "<p>unreviewed</p>"))
        assets["teal"]["crop"] = assets["coral"]["crop"]
        self.assertFalse(_reviewed_deepseek_picture_pages(frozen, {"id": "s1"}, pages_scene(scene, assets)))

    def test_single_picture_oral_page_is_exact_template_only(self):
        frozen, scene, assets = fixture()
        page = scene["pages"][0]
        page.update(kind="oral_response", choices=[], correctChoiceIds=[], modelCueId="teacher")
        self.assertTrue(_reviewed_deepseek_picture_pages(frozen, {"id": "s1"}, pages_scene(scene, assets)))
        page["kind"] = "unsupported"
        self.assertFalse(_reviewed_deepseek_picture_pages(frozen, {"id": "s1"}, pages_scene(scene, assets)))

    def test_model_identifiers_cannot_inject_markup(self):
        _, scene, assets = fixture()
        injected = 'x" onclick="window.unreviewedCode()'
        page = scene["pages"][0]
        page["pageId"] = injected
        page["choices"][0].update(buttonId=injected, choiceId=injected)
        markup = _Markup(pages_scene(scene, assets))
        self.assertFalse(any(key.startswith("on") for _, attrs in markup.tags for key in attrs))
        self.assertEqual(interactive_cues(pages_scene(scene, assets)), [
            {"id": c["cueId"], "text": c["teacherText"]} for c in scene["finiteCues"]])

    @unittest.skipUnless(shutil.which("node"), "Node required for generated browser script syntax")
    def test_both_renderers_produce_valid_browser_javascript(self):
        _, scene, assets = fixture()
        model = {**scene, "roleModel": {"teacherCueId": "teacher", "promptCueId": "question",
            "configurations": [{"speakerCharacterId": "coral", "listenerCharacterId": "teal",
                                "thirdCharacterId": "yellow", "portraitAssetKey": "coral",
                                "teacherCueId": "teacher", "questionCueId": "question", "modelCueId": "coral"}]}}
        for html in (pages_scene(scene, assets), role_scene(model, assets)):
            for script in _Markup(html).scripts:
                if script["attrs"].get("type") != "application/json":
                    completed = subprocess.run([shutil.which("node"), "--check", "--input-type=module"],
                        input=script["code"], text=True, capture_output=True)
                    self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
