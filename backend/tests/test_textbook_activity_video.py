"""Semantic component motion, held target frames and immutable local media."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import contextlib
import io

from content.textbook_batch import build_plan
from content.textbook_catalog import canonical, digest
from content.textbook_activity_ir import byte_sha
from services.textbook_activity_video import frame_svg, preflight_video, render_video

ROOT = Path(__file__).resolve().parents[2]


class OriginalActivityVideo(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("MIRA_TASK_TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        catalog = self.root / "catalog"
        catalog.mkdir()
        source = ROOT / "backend/content/textbooks/official-directories-v1/bnu-math-g1-lower-2022-standard.directory-c4be26f1b4e105927cc4b5a0.json"
        (catalog / "source.json").write_bytes(source.read_bytes())
        _, tasks = build_plan(catalog, superseded_ids=set())
        self.lesson = next(t for t in tasks if t["kind"] == "lesson_courseware")
        self.task = next(t for t in tasks if t["kind"] == "unit_guide")
        self.task_path = self.root / "task.json"
        self.design_path = self.root / "design.json"
        assets = []
        for number in (1, 3, 5):
            markup = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 128"><rect width="160" height="128" rx="24" fill="#f7f3e8"/>'
            markup += ''.join(f'<g id="seed-{i}"><ellipse cx="{20+25*i}" cy="72" rx="8" ry="12" fill="#867458"/></g>' for i in range(number)) + '</svg>'
            assets.append({"assetId": "seeds"+str(number), "sha256": byte_sha(markup.encode()), "svgMarkup": markup})
        self.design = {"schemaVersion": "mira.textbook.activity-design.v1", "taskId": self.task["taskId"],
            "kind": self.task["kind"], "binding": self.task["scope"], "manifestSha256": self.task["manifestSha256"],
            "status": "draft", "publicationAllowed": False, "assetPlan": assets,
            "scenes": [{"type": "interactive", "widgetType": "game", "finiteCues": [
                {"cueId": "count"+str(n), "teacherText": "看看这些种子。"} for n in (1, 3, 5)],
                "observations": [{"assetId": "seeds"+str(n), "cueId": "count"+str(n), "seekSeconds": 1.5+4*i} for i, n in enumerate((1, 3, 5))]}],
            "localVideoPlan": {"schemaVersion": "mira.textbook.original-video-plan.v1", "animationFamily": "counted_arrival",
                "shots": [{"sourceAssetId": "seeds"+str(n), "tracks": [
                    {"groupId": "seed-"+str(i), "role": "counted_object", "operation": "translate", "from": [0, -45], "to": [0, 0],
                     "startSeconds": .05+i*.1, "endSeconds": .5+i*.1} for i in range(n)]} for n in (1, 3, 5)]}}
        self.write()

    def write(self):
        self.task_path.write_text(canonical(self.task)+"\n")
        self.design_path.write_text(canonical(self.design)+"\n")

    def preflight(self):
        self.write()
        return preflight_video(self.task_path, self.design_path, task_sha256=digest(self.task), design_sha256=digest(self.design))

    def test_component_motion_finishes_at_exact_target_before_all_seek_frames(self):
        contract = self.preflight()
        for i, ob in enumerate(self.design["scenes"][0]["observations"]):
            asset = contract["assets"][ob["assetId"]]
            self.assertEqual(frame_svg(contract, i, ob["seekSeconds"]-4*i), asset)
            initial = ET.fromstring(frame_svg(contract, i, 0))
            self.assertEqual(len([n for n in initial.iter() if n.get("transform") == "translate(0 -45)"]), (1, 3, 5)[i])
            self.assertNotEqual(frame_svg(contract, i, 0), frame_svg(contract, i, .4))
            self.assertEqual(frame_svg(contract, i, 1), asset)

    def test_wrong_hash_binding_source_or_lesson_scope_rejected(self):
        contract = self.preflight()
        for hashes in (("0"*64, digest(self.design)), (digest(self.task), "0"*64)):
            with self.subTest(hashes=hashes), self.assertRaises(ValueError):
                preflight_video(self.task_path, self.design_path, task_sha256=hashes[0], design_sha256=hashes[1])
        self.design["binding"] = {**self.design["binding"], "gradeCode": "primary_6"}
        with self.assertRaisesRegex(ValueError, "binding"):
            self.preflight()
        self.design["binding"] = self.task["scope"]
        Path(self.task["sourcePaths"][0]).write_text("{}")
        with self.assertRaises(ValueError):
            self.preflight()

    def test_unknown_family_free_code_early_seek_bad_group_no_motion_and_whole_card_blocked(self):
        original = deepcopy(self.design)
        variants = []
        bad = deepcopy(original); bad["localVideoPlan"]["animationFamily"] = "generic_static_slideshow"; variants.append(bad)
        bad = deepcopy(original); bad["localVideoPlan"]["javascript"] = "eval(x)"; variants.append(bad)
        bad = deepcopy(original); bad["scenes"][0]["observations"][0]["seekSeconds"] = .5; variants.append(bad)
        bad = deepcopy(original); bad["localVideoPlan"]["shots"][0]["tracks"][0]["groupId"] = "unknown"; variants.append(bad)
        bad = deepcopy(original); bad["localVideoPlan"]["shots"][0]["tracks"][0]["from"] = [0, 0]; variants.append(bad)
        bad = deepcopy(original); bad["localVideoPlan"]["shots"][0]["tracks"][0]["role"] = "decoration"; variants.append(bad)
        bad = deepcopy(original); bad["localVideoPlan"]["shots"][0]["tracks"][0]["endSeconds"] = 2; variants.append(bad)
        for bad in variants:
            self.design = bad
            with self.subTest(plan=bad["localVideoPlan"]), self.assertRaises(ValueError):
                self.preflight()
        self.design = deepcopy(original)
        a = self.design["assetPlan"][0]
        a["svgMarkup"] = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 128"><g id="seed-0"><rect width="160" height="128"/><circle cx="40" cy="40" r="10"/></g></svg>'
        a["sha256"] = byte_sha(a["svgMarkup"].encode())
        with self.assertRaisesRegex(ValueError, "whole_card"):
            self.preflight()

    def test_hinge_uses_same_pivot_and_exact_final_svg(self):
        self.design["localVideoPlan"]["animationFamily"] = "hinged_component"
        for shot in self.design["localVideoPlan"]["shots"]:
            shot["tracks"] = [{"groupId": "seed-0", "role": "hinged_part", "operation": "rotate",
                "from": [-45, 20, 72], "to": [0, 20, 72], "startSeconds": .05, "endSeconds": .9}]
        contract = self.preflight()
        self.assertIn("rotate(-45 20 72)", frame_svg(contract, 0, 0))
        self.assertEqual(frame_svg(contract, 0, 1.5), contract["assets"]["seeds1"])
        self.design["localVideoPlan"]["shots"][0]["tracks"][0]["to"][1] += 1
        with self.assertRaisesRegex(ValueError, "hinge"):
            self.preflight()

    def test_lesson_requires_exact_approved_scope_and_preserved_page_bytes(self):
        self.task = self.lesson
        self.design.update(taskId=self.task['taskId'], kind=self.task['kind'], binding=self.task['scope'])
        with self.assertRaisesRegex(ValueError, 'reviewed_lesson_scope_required'):
            self.preflight()
        page = self.root / 'reviewed-page.image'
        page.write_bytes(b'original page fixture')
        scope = {'schemaVersion': 'mira.textbook.reviewed-lesson-scope.v1',
                 'taskId': self.task['taskId'], 'binding': self.task['scope'],
                 'manifestSha256': self.task['manifestSha256'], 'reviewStatus': 'approved',
                 'reviewer': 'test reviewer', 'basis': 'exact page review', 'assessmentMode': 'ungraded',
                 'objectives': ['观察数量'], 'knowledgePoints': ['数量比较'], 'priorKnowledge': [], 'excludedTopics': [],
                 'evidence': {'pages': [{'path': str(page), 'sha256': byte_sha(page.read_bytes())}]}}
        scope_path = self.root / 'scope.json'
        scope_path.write_text(canonical(scope))
        self.design.update(reviewedLessonScopePath=str(scope_path), reviewedLessonScopeByteSha256=byte_sha(scope_path.read_bytes()))
        contract = self.preflight()
        self.assertEqual(contract['sourceFiles'][str(page)], byte_sha(page.read_bytes()))
        self.assertIn(str(scope_path), contract['sourceFiles'])
        page.write_bytes(b'changed page')
        with self.assertRaisesRegex(ValueError, 'lesson_page_changed'):
            self.preflight()
        scope['binding'] = {**scope['binding'], 'gradeCode': 'primary_6'}
        scope_path.write_text(canonical(scope))
        self.design['reviewedLessonScopeByteSha256'] = byte_sha(scope_path.read_bytes())
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.preflight()

    def test_actual_twelve_second_h264_decode_and_create_only_reuse(self):
        if not shutil.which("node") or not shutil.which("ffmpeg") or not shutil.which("ffprobe") or not (ROOT / "openmaic-runtime/.runtime/OpenMAIC/node_modules/sharp").exists():
            self.skipTest("Local sharp/ffmpeg toolchain unavailable")
        self.write()
        source_bytes = {p: p.read_bytes() for p in (self.task_path, self.design_path, Path(self.task["sourcePaths"][0]))}
        kwargs = {"task_sha256": digest(self.task), "design_sha256": digest(self.design)}
        with patch("services.textbook_activity_video.OWNED", self.root):
            receipt = render_video(self.task_path, self.design_path, self.root / "video", **kwargs)
            self.assertEqual(receipt["video"]["durationSeconds"], 12)
            self.assertEqual(receipt["video"]["audioStreams"], 0)
            self.assertEqual(len(receipt["observationFrames"]), 3)
            with patch("services.textbook_activity_video._tools", side_effect=AssertionError("repeat tried encoding")):
                self.assertEqual(render_video(self.task_path, self.design_path, self.root / "video", **kwargs), receipt)
            target = Path(receipt["video"]["path"])
            initial = self.root / "initial.png"
            subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-i", str(target), "-frames:v", "1", str(initial)], check=True)
            self.assertNotEqual(byte_sha(initial.read_bytes()), receipt["observationFrames"][0]["sha256"])
            corner = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-loglevel", "error", "-i",
                receipt["observationFrames"][0]["path"], "-vf", "crop=1:1:148:5,format=rgb24",
                "-frames:v", "1", "-f", "rawvideo", "pipe:1"], capture_output=True, check=True).stdout
            self.assertEqual(len(corner), 3)
            self.assertGreater(min(corner), 220, "Transparent SVG corner became a black YUV artifact")
            self.assertEqual(receipt["status"], "rendered_pending_visual_review")
            target.write_bytes(b"different")
            with self.assertRaisesRegex(ValueError, "saved_bytes_changed"):
                render_video(self.task_path, self.design_path, self.root / "video", **kwargs)
        self.assertTrue(all(p.read_bytes() == raw for p, raw in source_bytes.items()))

    def test_incomplete_output_and_symlink_not_overwritten(self):
        self.write()
        kwargs = {"task_sha256": digest(self.task), "design_sha256": digest(self.design)}
        output = self.root / "video"
        folder = output / self.task["taskId"]
        folder.mkdir(parents=True)
        (folder / "observation.mp4").write_bytes(b"original-incomplete")
        with patch("services.textbook_activity_video.OWNED", self.root):
            with self.assertRaisesRegex(ValueError, "incomplete_output"):
                render_video(self.task_path, self.design_path, output, **kwargs)
            link = self.root / "link"
            link.symlink_to(output, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "owned_output"):
                render_video(self.task_path, self.design_path, link, **kwargs)
        self.assertEqual((folder / "observation.mp4").read_bytes(), b"original-incomplete")

    def test_cli_batch_preflights_every_contract_before_output_or_renderer(self):
        from scripts.render_textbook_activity_video import main
        entry = {"taskPath": str(self.task_path), "taskSha256": digest(self.task),
                 "designPath": str(self.design_path), "designSha256": digest(self.design)}
        path = self.root / "index.json"
        path.write_text(canonical({"schemaVersion": "mira.textbook.original-video-batch.v1", "entries": [entry, {**entry, "designSha256": "0"*64}]}))
        with patch("scripts.render_textbook_activity_video.render_video", side_effect=AssertionError("bad batch rendered")):
            with self.assertRaises(ValueError):
                main(["--index", str(path), "--limit", "2", "--output-directory", str(self.root / "never-written")])
        self.assertFalse((self.root / "never-written").exists())
        path.write_text(canonical({"schemaVersion": "mira.textbook.original-video-batch.v1", "entries": [entry]}))
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main(["--index", str(path), "--check"]), 0)
        self.assertTrue(json.loads(stdout.getvalue())[0]["contractValid"])


if __name__ == "__main__":
    unittest.main()
