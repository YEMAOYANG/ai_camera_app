import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from courseware.tools.audit import VIEWPORTS, audit_body, build_harness, parse_result
from courseware.tools.check import body_hash, check_classroom


BODY = {'scenes': [
    {'type': 'slide'},
    {'type': 'interactive', 'content': {'html': '<html><body><img src="/api/classroom-media/abc/media/a%20b.png"><div id="one"></div></body></html>'}, 'actions': [
        {'type': 'speech', 'text': 'hello'},
        {'type': 'widget_highlight', 'target': '#one'},
        {'type': 'widget_setState', 'state': {'step': 1}},
        {'type': 'widget_annotation', 'target': '#one', 'content': 'note'},
        {'type': 'widget_reveal', 'target': '#one'},
    ]},
    {'type': 'quiz'},
]}


def dump(result):
    return '<html><pre id="audit-result" hidden>' + html.escape(json.dumps(result)) + '</pre></html>'


class AuditTests(unittest.TestCase):
    def test_harness(self):
        with tempfile.TemporaryDirectory() as directory:
            harness = build_harness(BODY['scenes'][1], directory, '640x360')
            self.assertNotIn('sandbox=', re.search(r'<iframe\b[^>]*>', harness).group())
            srcdoc = html.unescape(re.search(r'srcdoc="([^"]*)"', harness).group(1))
            self.assertIn((Path(directory).resolve() / 'a b.png').as_uri(), srcdoc)
            self.assertLess(srcdoc.index('MIRA_AUDIT_RESULT'), srcdoc.lower().index('</body>'))
            messages = json.loads(re.search(r'const messages = (.*);', harness).group(1))
            self.assertEqual([m['type'] for m in messages], ['HIGHLIGHT_ELEMENT', 'SET_WIDGET_STATE', 'ANNOTATE_ELEMENT', 'REVEAL_ELEMENT'])
            self.assertEqual(messages[1]['state'], {'step': 1})

    def test_results_and_receipt(self):
        good = {'errors': [], 'problems': [], 'missingTargets': []}
        cases = [good, dict(good, errors=['oops']), dict(good, problems=['overlap']), dict(good, missingTargets=['#missing']), None]
        for expected in cases:
            with self.subTest(expected=expected):
                calls = []
                def fake(args, timeout):
                    calls.append(args)
                    if '--version' in args:
                        return 0, 'Chrome 123\n', ''
                    return 0, dump(expected) if expected is not None else '<html></html>', ''
                with tempfile.TemporaryDirectory() as directory:
                    receipt = audit_body(BODY, directory, run_chrome=fake, work_dir=directory)
                self.assertEqual(receipt['bodySha256'], body_hash(BODY))
                self.assertEqual(receipt['viewports'], list(VIEWPORTS))
                self.assertEqual(len(receipt['pages']), 3)
                self.assertEqual(receipt['ok'], expected == good)
                self.assertTrue(all(page['scene'] == 2 for page in receipt['pages']))
                self.assertEqual(receipt['tool']['chrome'], 'Chrome 123')
                self.assertIn("page scripts run in a same-origin frame during the audit, so the player's sandbox is not reproduced", receipt['scope'])
                self.assertEqual(len(calls), 4)
                if expected == good:
                    self.assertFalse([issue for issue in check_classroom(BODY, receipt=receipt) if issue['gate'] == 'G6'])
                if expected is None:
                    self.assertIn('No valid result', receipt['pages'][0]['errors'][0])

    def test_parse_invalid_and_custom_viewport(self):
        self.assertTrue(parse_result('<pre id="audit-result">{}</pre>')['errors'])
        def fake(args, timeout):
            return (0, 'Chrome' if '--version' in args else dump({'errors': [], 'problems': [], 'missingTargets': []}), '')
        with tempfile.TemporaryDirectory() as directory:
            receipt = audit_body(BODY, directory, viewports=['640x360'], run_chrome=fake, work_dir=directory)
        self.assertEqual(receipt['viewports'], ['640x360'])
        self.assertTrue(any(issue['code'] == 'audit_receipt_missing_viewport' for issue in check_classroom(BODY, receipt=receipt)))

    def test_overlay_and_visibility_checks(self):
        tools = Path(__file__).resolve().parents[1]
        script = (tools / 'audit_inject.js').read_text(encoding='utf-8')
        self.assertIn('document.elementFromPoint(originX + 640 * sx, originY + 360 * sy)', script)
        self.assertIn('el = el.parentElement', script)
        self.assertIn('width * height >= 1280 * 720 * 0.85', script)
        self.assertGreaterEqual(script.count('overlay && !overlay.contains(el)'), 2)
        self.assertIn('!el.contains(top) && !top.contains(el)', script)
        self.assertIn("pointerEvents === 'none'", script)
        fixtures = tools / 'tests' / 'fixtures'
        overlay = (fixtures / 'audit_overlay.html').read_text(encoding='utf-8')
        no_overlay = (fixtures / 'audit_no_overlay.html').read_text(encoding='utf-8')
        self.assertIn('inset:0', overlay)
        self.assertIn('Hidden text', overlay)
        self.assertIn('>Behind</button>', overlay)
        self.assertIn('>Start</button>', overlay)
        self.assertNotIn('inset:0', no_overlay)
        self.assertIn('Visible text', no_overlay)
        with tempfile.TemporaryDirectory() as directory:
            for name in ('audit_overlay.html', 'audit_no_overlay.html'):
                page = (tools / 'tests' / 'fixtures' / name).read_text(encoding='utf-8')
                harness = build_harness({'content': {'html': page}}, directory, '1280x720')
                self.assertIn('0.85', html.unescape(harness))
            harness = build_harness(BODY['scenes'][1], directory, '1280x720')
            self.assertIn('e.target.currentSrc||e.target.src', html.unescape(harness))

    def test_outermost_clickable_checks(self):
        tools = Path(__file__).resolve().parents[1]
        fixtures = tools / 'tests' / 'fixtures'
        script = (tools / 'audit_inject.js').read_text(encoding='utf-8')
        patterns = json.loads((fixtures / 'audit_clickable_assertions.json').read_text(encoding='utf-8'))
        self.assertTrue(patterns)
        for pattern in patterns:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, script)
        page = (fixtures / 'audit_clickable.html').read_text(encoding='utf-8')
        self.assertRegex(page, r'<button\b[^>]*>\s*<svg\b[^>]*>\s*<path\b[^>]*>.*?</path>\s*<ellipse\b[^>]*>.*?</ellipse>\s*</svg>\s*</button>')
        self.assertRegex(page, r'<button\s+style="width:20px;height:20px">x</button>')

    @unittest.skipUnless(shutil.which('node'), 'node is not on PATH')
    def test_injected_script_syntax(self):
        script = Path(__file__).resolve().parents[1] / 'audit_inject.js'
        result = subprocess.run(['node', '--check', str(script)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
