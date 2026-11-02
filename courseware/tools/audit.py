"""Run generic interactive-page audits in headless Chrome."""
import argparse
from datetime import datetime, timezone
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import unquote

from courseware.kit.contract import WIDGET_ACTION_TYPES, widget_message
from courseware.tools.check import MEDIA_URL, body_hash


VIEWPORTS = ('1280x720', '1000x563', '640x360')
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
SCOPE = 'interactive pages in headless Chrome: generic layout, size and error checks and the teacher page operations; page scripts run in a same-origin frame during the audit, so the player\'s sandbox is not reproduced; slides and quiz scenes are not rendered here'


def _run_chrome(args, timeout):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


def _viewport(value):
    match = re.fullmatch(r'([1-9]\d*)x([1-9]\d*)', value)
    if not match:
        raise ValueError('Invalid viewport: ' + str(value))
    return tuple(map(int, match.groups()))


def build_harness(scene, media_dir, viewport):
    width, height = _viewport(viewport)
    page = scene.get('content', {}).get('html', '')

    def media_url(match):
        suffix = match.group().split('/media/', 1)[1]
        filename = unquote(re.split(r'[?#]', suffix, 1)[0])
        if not filename or '/' in filename or '\\' in filename or filename in ('.', '..'):
            raise ValueError('Invalid media filename: ' + filename)
        tail = suffix[len(re.split(r'[?#]', suffix, 1)[0]):]
        return (Path(media_dir).resolve() / filename).as_uri() + tail

    page = MEDIA_URL.sub(media_url, page)
    bootstrap = '''<script>window.__miraAuditErrors=[];window.addEventListener('error',function(e){var src=e.target&&(e.target.currentSrc||e.target.src);window.__miraAuditErrors.push('error: '+(e.message||('resource error'+(src?' '+src:''))))},true);window.addEventListener('unhandledrejection',function(e){window.__miraAuditErrors.push('unhandledrejection: '+String(e.reason))});(function(){var old=console.error;console.error=function(){window.__miraAuditErrors.push('console.error: '+Array.from(arguments).map(String).join(' '));old.apply(console,arguments)}})();</script>'''
    head = re.search(r'<head(?:\s[^>]*)?>', page, flags=re.I)
    page = page[:head.end()] + bootstrap + page[head.end():] if head else bootstrap + page
    injection = '<script>' + Path(__file__).with_name('audit_inject.js').read_text(encoding='utf-8') + '</script>'
    page, count = re.subn(r'</body\s*>', lambda _: injection + '</body>', page, count=1, flags=re.I)
    if not count:
        page += injection
    messages = [widget_message(a) for a in scene.get('actions', []) if a.get('type') in WIDGET_ACTION_TYPES]
    # Escape HTML-significant characters in JSON embedded in the outer script.
    messages_json = json.dumps(messages, ensure_ascii=True).replace('<', '\\u003c')
    # Cross-process frames do not progress under Chrome's virtual time.
    return '''<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0">
<iframe id="page" style="border:0;display:block;width:%dpx;height:%dpx" srcdoc="%s"></iframe>
<pre id="audit-result" hidden></pre><script>
const frame = document.getElementById('page');
const messages = %s;
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
window.addEventListener('message', event => {
  if (event.source === frame.contentWindow && event.data && event.data.type === 'MIRA_AUDIT_RESULT')
    document.getElementById('audit-result').textContent = JSON.stringify(event.data.result);
});
frame.addEventListener('load', async () => {
  await wait(500);
  frame.contentWindow.postMessage({type:'MIRA_AUDIT_CHECK'}, '*');
  for (const message of messages) { frame.contentWindow.postMessage(message, '*'); await wait(200); frame.contentWindow.postMessage({type:'MIRA_AUDIT_CHECK'}, '*'); }
  await wait(300);
  frame.contentWindow.postMessage({type:'MIRA_AUDIT_FINISH'}, '*');
});
</script></body></html>''' % (width, height, html.escape(page, quote=True), messages_json)


class _ResultParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.inside = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'pre' and dict(attrs).get('id') == 'audit-result':
            self.inside = True

    def handle_endtag(self, tag):
        if tag == 'pre' and self.inside:
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)


def parse_result(dump):
    parser = _ResultParser()
    parser.feed(dump)
    try:
        result = json.loads(''.join(parser.parts))
        if not isinstance(result, dict) or any(not isinstance(result.get(key), list) for key in ('errors', 'problems', 'missingTargets')):
            raise ValueError('invalid result')
        return {key: result[key] for key in ('errors', 'problems', 'missingTargets')}
    except (ValueError, TypeError):
        return {'errors': ['No valid result from sandboxed page'], 'problems': [], 'missingTargets': []}


def audit_body(body, media_dir, *, viewports=VIEWPORTS, run_chrome=None, work_dir=None):
    run = run_chrome or _run_chrome
    chrome = os.environ.get('MIRA_CHROME_BIN', CHROME)
    sizes = list(viewports)
    for size in sizes:
        _viewport(size)
    try:
        code, version, _ = run([chrome, '--version'], 15)
        version = version.strip() if code == 0 and version.strip() else 'unknown'
    except (OSError, subprocess.SubprocessError):
        version = 'unknown'
    pages = []
    ran_sizes = set()
    with tempfile.TemporaryDirectory(dir=work_dir) as temporary:
        for index, scene in enumerate(body.get('scenes', []), 1):
            if scene.get('type') != 'interactive':
                continue
            for size in sizes:
                width, height = _viewport(size)
                result = {'scene': index, 'viewport': size}
                try:
                    path = Path(temporary) / 'harness.html'
                    path.write_text(build_harness(scene, media_dir, size), encoding='utf-8')
                    args = [chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--allow-file-access-from-files', '--autoplay-policy=no-user-gesture-required', f'--window-size={width},{height}', '--virtual-time-budget=30000', '--dump-dom', path.as_uri()]
                    ran_sizes.add(size)
                    code, stdout, stderr = run(args, 90)
                    result.update(parse_result(stdout))
                    if code:
                        result['errors'].append('Chrome exited %s: %s' % (code, stderr.strip()[-400:]))
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    result.update(errors=[str(exc)], problems=[], missingTargets=[])
                result['ok'] = not any(result[key] for key in ('errors', 'problems', 'missingTargets'))
                pages.append(result)
    return {'schemaVersion': 'mira.courseware.audit-receipt.v1', 'bodySha256': body_hash(body), 'ok': all(page['ok'] for page in pages), 'viewports': [size for size in sizes if size in ran_sizes], 'pages': pages, 'scope': SCOPE, 'tool': {'chrome': version, 'ranAt': datetime.now(timezone.utc).isoformat()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--body', required=True)
    parser.add_argument('--media-dir', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--viewport', action='append')
    args = parser.parse_args()
    try:
        body = json.loads(Path(args.body).read_text(encoding='utf-8'))
        receipt = audit_body(body, args.media_dir, viewports=args.viewport or VIEWPORTS)
        Path(args.out).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    for page in receipt['pages']:
        print('scene %s %s: %s' % (page['scene'], page['viewport'], 'ok' if page['ok'] else 'FAILED'))
    return int(not receipt['ok'])


if __name__ == '__main__':
    raise SystemExit(main())
