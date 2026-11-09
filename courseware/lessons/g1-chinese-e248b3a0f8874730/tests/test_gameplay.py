"""Regression checks for this lesson's wrong answers, teacher reset and replay.

The pixel fixture deliberately isolates interaction behavior. Formal-picture,
audio and three-size acceptance still run through the courseware release gates.
Run from the repository root through tools/task_tmp.py.
"""
import base64
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from courseware.kit.page import page


SOURCE = Path(__file__).resolve().parents[1]
ROOT = SOURCE.parents[2]
PIXEL = "data:image/png;base64," + base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
)).decode("ascii")

SCRIPT = r"""
const assert = require('node:assert/strict');
const { chromium } = require(process.argv[1] + '/student-web/node_modules/playwright-core');
const { pathToFileURL } = require('node:url');
(async () => {
  const browser = await chromium.launch({executablePath: process.env.MIRA_CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: true});
  try {
    const p = await browser.newPage({viewport: {width: 1280, height: 720}});
    const errors = [];
    p.on('pageerror', e => errors.push(e.message));
    await p.addInitScript(() => {window.Audio = class {play(){return Promise.resolve()} pause(){}}});
    const open = async name => {await p.goto(pathToFileURL(process.argv[2] + '/' + name + '.html').href); await p.locator('#start-btn').click()};
    const stars = () => p.evaluate(() => K.stars);
    const teacher = mode => p.evaluate(m => K.onState({mode:m}), mode);
    const done = async () => {await p.locator('#finish:not(.gone)').waitFor(); assert.equal(await stars(), 2)};
    const replay = async () => {await p.locator('#btn-again').click(); assert.equal(await stars(), 0); assert.equal(await p.locator('#finish:not(.gone)').count(),0)};

    await open('album');
    await teacher('demo');
    assert.equal(await p.locator('#album-result').evaluate(e => e.classList.contains('hide')),false);
    await teacher('play');
    await p.locator('#album-photo-beijing').click(); await p.locator('#album-target').click();
    assert.equal(await stars(),0,'first wrong album photo cannot advance');
    assert.equal(await p.locator('.album-photo.teach-hl').count(),0,'first miss cannot reveal answer');
    assert.equal(await p.locator('#album-result').evaluate(e=>e.classList.contains('hide')),true);
    await p.locator('#album-photo-family').dragTo(p.locator('#album-target'));
    assert.equal(await stars(),1);
    assert.equal(await p.locator('.album-photo.selected').count(),0,'correct drop clears any prior selection outline');
    await p.waitForTimeout(1100);
    await p.locator('#album-photo-beijing').dragTo(p.locator('#album-target'));
    await done(); await replay();
    assert.equal(await p.locator('#album-task').innerText(),'小家');
    assert.equal(await p.locator('#album-result').evaluate(e=>e.classList.contains('hide')),true);
    console.log('album: first miss, real drag, teacher reset, replay OK');

    await open('circle');
    await teacher('demo');
    assert.equal(await p.locator('.circle-child.placed').count(),1);
    await teacher('play');
    assert.equal(await p.locator('.circle-child.placed').count(),0);
    await p.locator('#circle-child-1').dragTo(p.locator('#circle-listen'));
    assert.equal(await stars(),0,'outside drop cannot complete the circle');
    assert.equal(await p.locator('#circle-zone.teach-hl').count(),0,'first miss cannot demonstrate answer');
    for(let i=1;i<=3;i++) await p.locator('#circle-child-'+i).dragTo(p.locator('#circle-zone'));
    assert.equal(await stars(),1);
    await p.waitForTimeout(1100);
    for(let i=1;i<=4;i++) await p.locator('#circle-child-'+i).dragTo(p.locator('#circle-zone'));
    await done(); await replay();
    assert.equal(await p.locator('.circle-child.placed').count(),0);
    assert.equal(await p.locator('#circle-tray .circle-child:not(.hide)').count(),3);
    console.log('circle: all-members condition, real drag, teacher reset, replay OK');

    await open('story');
    await teacher('demo'); await teacher('play');
    const initial = await p.locator('#story-result').getAttribute('src');
    await p.locator('#story-choice-2').click(); await p.locator('#story-target').click();
    assert.equal(await stars(),0,'unkind choice cannot advance');
    assert.equal(await p.locator('#story-result').getAttribute('src'),initial,'first wrong choice must not change conclusion');
    assert.equal(await p.locator('.story-choice.teach-hl').count(),0,'first miss cannot reveal answer');
    await p.locator('#story-choice-1').dragTo(p.locator('#story-target'));
    assert.equal(await stars(),1);
    assert.notEqual(await p.locator('#story-result').getAttribute('src'),initial,'friendly action must visibly replace the scene');
    await p.waitForTimeout(1100);
    await p.locator('#story-choice-3').dragTo(p.locator('#story-target'));
    await done(); await replay();
    assert.equal(await p.locator('#story-choice-1').getAttribute('data-key'),'help');
    assert.equal(await p.locator('#story-result').getAttribute('src'),initial);
    console.log('story: first miss, changed conclusion, teacher reset, replay OK');
    assert.deepEqual(errors,[],'no script errors');
  } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
"""


class GameplayTests(unittest.TestCase):
    def test_wrong_answers_teacher_reset_and_replay(self):
        with tempfile.TemporaryDirectory(dir=os.environ.get("MIRA_TASK_TMPDIR")) as folder:
            temporary = Path(folder)
            for name in ("album", "circle", "story"):
                html = (SOURCE / "pages" / (name + ".html")).read_text()
                css = (SOURCE / "pages" / (name + ".css")).read_text()
                js = (SOURCE / "pages" / (name + ".js")).read_text()
                built = page(name, html, css, js)
                built = re.sub(
                    r"__IMG:([^_]+)__",
                    lambda match: PIXEL + "#" + match.group(1), built,
                )
                (temporary / (name + ".html")).write_text(built)
            result = subprocess.run(
                ["node", "-e", SCRIPT, str(ROOT), str(temporary)],
                capture_output=True, text=True, timeout=120,
            )
            print(result.stdout, end="")
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
