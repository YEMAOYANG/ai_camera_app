"""Validate the goldfish lesson's authored stages without making media requests."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from courseware.tools import autoplay, build, check

LESSON = Path(__file__).resolve().parents[1]


class GoldfishGamesTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.media = Path(work.name) / "media"
        self.draft = build.prepare(LESSON, work.name, stage_id="goldfish-games-test", now_ms=1)

    def test_only_registered_art_and_current_editorial_checks(self):
        notes = json.loads((LESSON / "official-notes.json").read_text(encoding="utf-8"))
        art = json.loads((LESSON / "asset-sources.json").read_text(encoding="utf-8"))
        for source in art["assets"]:
            with self.subTest(asset=source["id"]):
                rendered = self.media / ("pic-" + source["sha256"] + ".png")
                self.assertEqual(hashlib.sha256(rendered.read_bytes()).hexdigest(), source["sha256"])

        issues = check.check_classroom(
            self.draft["body"], self.media, notes=notes, roster=self.draft["roster"],
            grade=1, teaching=True,
        )
        editorial_issues = [
            issue for issue in issues
            if issue["gate"] in {"G0", "G2", "G3", "G4"}
            and issue["code"] != "quiz_questionAudioUrl_missing"
        ]
        self.assertEqual(editorial_issues, [])

    @unittest.skipUnless(Path(autoplay.CHROME).exists(), "local Chrome required")
    def test_both_observation_games_play_three_levels_and_reset(self):
        receipt = autoplay.play_body(self.draft["body"], self.media)
        self.assertEqual([result["scene"] for result in receipt["pages"]], [3, 8])
        for result in receipt["pages"]:
            with self.subTest(scene=result["scene"]):
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["method"], "game-autopilot")
                self.assertTrue(result["finishedAgain"])


if __name__ == "__main__":
    unittest.main()
