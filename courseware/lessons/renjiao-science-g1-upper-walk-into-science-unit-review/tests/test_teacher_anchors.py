"""Verify teacher highlights cover the lesson's first objects at 640×360."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from courseware.tools import autoplay, build


LESSON = Path(__file__).resolve().parents[1]
SCRIPT = r"""
const assert = require('node:assert/strict');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const [directory, playwright, executablePath] = process.argv.slice(1);
const {chromium} = require(path.join(playwright, 'node_modules/playwright-core'));
const targets = {
  'p04': {'science-depot-demo-item': [593, 342], 'science-depot-demo-dock': [781, 342]},
  'p06': {'science-shutter-goal': [640, 126]},
};

(async () => {
  const browser = await chromium.launch({executablePath});
  try {
    const page = await browser.newPage({viewport: {width: 640, height: 360}});
    for (const [scene, anchors] of Object.entries(targets)) {
      await page.goto(pathToFileURL(path.join(directory, scene + '.html')).href);
      await page.locator('#start-btn').click();
      await page.evaluate(() => window.K.onState({demo:true, level:1, pause:true}));
      for (const [id, [x,y]] of Object.entries(anchors)) {
        const center = await page.locator('#' + id).evaluate(el => {
          const stage = window.K.stage().getBoundingClientRect();
          const box = el.getBoundingClientRect();
          return [(box.x + box.width / 2 - stage.x) * 1280 / stage.width,
                  (box.y + box.height / 2 - stage.y) * 720 / stage.height];
        });
        assert.ok(Math.abs(center[0] - x) < 2 && Math.abs(center[1] - y) < 2,
                  id + ' covered [' + center + '] instead of [' + [x,y] + ']');
      }
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""


class TeacherAnchorsTest(unittest.TestCase):
    def test_first_demo_anchors_cover_the_card_dock_and_photo_target(self):
        node = shutil.which("node")
        chrome = Path(os.environ.get("MIRA_CHROME_BIN", autoplay.CHROME))
        if not node or not chrome.is_file():
            self.skipTest("Node and Chrome are required")
        with tempfile.TemporaryDirectory(dir=os.environ["MIRA_TASK_TMPDIR"]) as name:
            work = Path(name)
            draft = build.prepare(LESSON, work, stage_id="walk-science-anchor-test")
            for scene in draft["body"]["scenes"]:
                if scene["type"] == "interactive":
                    page = work / (scene["id"].removeprefix("scene-") + ".html")
                    page.write_text(autoplay.page_html(scene, work / "media"), encoding="utf-8")
            result = subprocess.run(
                [node, "-e", SCRIPT, str(work), str(autoplay._playwright_dir()), str(chrome)],
                capture_output=True, text=True, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
