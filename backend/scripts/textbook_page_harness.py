"""Build a local play-test page for the interactive pages of one saved classroom.

Usage: textbook_page_harness.py <classroom.json | prepared-release.json> <output-dir> [--store DIR]

Serve the output directory (for example `python3 -m http.server 8765`) and open
  index.html?auto=1   plays every interactive page in a plain frame and reports
                      its natural size, script errors and the teacher cues each
                      click asks for (window.__report);
  index.html?page=N   shows page N in the opaque sandbox the student player uses,
                      with a bar naming each cue the page asks for.
Pictures and narration are inlined, because the sandbox cannot fetch runtime
media. Given a prepared release (`publish_textbook_preview.py prepare`), each
page is embedded the way the student gateway embeds it, the frame is told it is
visible, and the bar shows each teacher line as it starts and ends, so the
recorded narration can be heard and checked. Nothing is generated or published.
"""
import base64
import json
from pathlib import Path
import re
import sys
from base64 import b64encode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content.textbook_interactive_narration import interactive_cues  # noqa: E402  (the same parser narration uses)

MIME = {'.png': 'image/png', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
        '.wav': 'audio/wav', '.mp3': 'audio/mpeg'}
MEDIA = re.compile(r'(?:https?://[0-9a-z.:]+)?/api/classroom-media/([\w-]+)/(media|audio)/([\w.-]+)')

PAGE = r'''<!doctype html><meta charset="utf-8"><title>page harness</title>
<style>body{margin:0;font:14px/1.5 system-ui;background:#eee}#bar{padding:6px 10px;background:#222;color:#fff;min-height:44px}
#bar b{color:#ffd166}#stage{width:1000px;height:563px;background:#fff;border:0;display:block}pre{white-space:pre-wrap;padding:10px}</style>
<div id="bar">loading</div><div id="host"></div><pre id="out"></pre>
<script>
const params = new URLSearchParams(location.search);
const stub = (index, sandboxed) => `<script>(function(){var send=function(kind,value){${sandboxed
  ? "parent.postMessage({harness:true,kind:kind,value:String(value)},'*')"
  : `parent.__log(${index},kind,String(value))`}};
window.miraNarrate=function(id){send('cue',id)};
window.addEventListener('error',function(e){send('error',e.message+' @'+e.lineno)});
window.addEventListener('unhandledrejection',function(e){send('error','promise '+(e.reason&&e.reason.message||e.reason))});})();<\/script>`;
const withStub = (page, sandboxed) => /<head[^>]*>/i.test(page.html)
  ? page.html.replace(/<head[^>]*>/i, m => m + stub(page.index, sandboxed)) : stub(page.index, sandboxed) + page.html;
const sleep = ms => new Promise(done => setTimeout(done, ms));
const visible = (win, el) => { const r = el.getBoundingClientRect(), s = win.getComputedStyle(el);
  return r.width > 20 && r.height > 20 && s.visibility !== 'hidden' && s.display !== 'none' && s.pointerEvents !== 'none'
    && !el.disabled && r.top < 563 && r.left < 1000 && r.bottom > 0 && r.right > 0; };
const clickables = win => [...win.document.querySelectorAll('button,[onclick],[role=button],[data-id],[data-value],[data-key],.card,.option,.choice')]
  .filter(el => visible(win, el) && (el.tagName === 'BUTTON' || win.getComputedStyle(el).cursor === 'pointer'));
// The generator appends a KaTeX auto-render block that the student player
// supplies; its missing global is not a page fault.
const known = message => /renderMathInElement is not defined/.test(message);
async function auto(pages) {
  const report = []; window.__report = report;
  for (const page of pages.filter(p => p.type === 'interactive')) {
    const entry = { page: page.index, title: page.title, cues: Object.keys(page.cues).length, events: [], errors: [], fired: [] };
    window.__log = (index, kind, value) => { if (index !== page.index) return;
      if (kind === 'cue') { entry.fired.push(value); if (!(value in page.cues)) entry.errors.push('unknown cue ' + value); }
      else if (!known(value)) entry.errors.push(value); };
    const frame = document.createElement('iframe'); frame.id = 'stage'; frame.srcdoc = withStub(page, false);
    document.getElementById('host').replaceChildren(frame);
    await new Promise(done => { frame.onload = done; setTimeout(done, 5000); }); await sleep(1500);
    const win = frame.contentWindow, doc = win.document, root = doc.getElementById('fit-root');
    const saved = root && root.style.transform; if (root) root.style.transform = 'none';
    entry.natural = root ? [root.scrollWidth, root.scrollHeight] : [doc.documentElement.scrollWidth, doc.documentElement.scrollHeight];
    if (root) root.style.transform = saved;
    entry.scale = root ? saved : 'no fit-root';
    entry.offCanvas = [...doc.body.querySelectorAll('*')].filter(el => { const r = el.getBoundingClientRect();
      return r.width > 30 && r.height > 20 && (r.bottom > 566 || r.right > 1003 || r.left < -3) && visible(win, el); }).length;
    entry.images = [...doc.images].filter(img => img.complete && img.naturalWidth > 0).length + '/' + doc.images.length;
    entry.smallTargets = clickables(win).filter(el => { const r = el.getBoundingClientRect(); return Math.min(r.width, r.height) < 44; }).length;
    entry.onLoad = entry.fired.splice(0);
    const seen = new Set();
    for (let step = 0; step < 16; step++) {
      const next = clickables(win).find(el => !seen.has(el));
      if (!next) break;
      seen.add(next);
      const label = (next.getAttribute('aria-label') || next.textContent || next.id || next.className || next.tagName)
        .trim().replace(/\s+/g, ' ').slice(0, 14);
      try { next.click(); } catch (error) { entry.errors.push('click ' + error.message); }
      await sleep(450);
      entry.events.push(label + ' -> ' + (entry.fired.splice(0).join(',') || '-'));
    }
    report.push(entry);
    document.getElementById('bar').textContent = 'checked page ' + page.index;
  }
  document.getElementById('bar').textContent = 'AUTO DONE';
  document.getElementById('out').textContent = JSON.stringify(report, null, 1);
}
function view(pages, number) {
  const page = pages.find(p => p.index === number), bar = document.getElementById('bar');
  bar.innerHTML = `<b>${page.index} ${page.type}</b> ${page.title} · cues ${Object.keys(page.cues).length}<br><span id="cue">no cue yet</span> <span id="err" style="color:#ff8a8a"></span>`;
  addEventListener('message', event => { if (!event.data || !event.data.harness) return;
    if (event.data.kind === 'state') { document.getElementById('cue').textContent = event.data.value + ' ' + (page.cues[event.data.value.split(':')[0]] || ''); return; }
    if (event.data.kind === 'cue') document.getElementById('cue').textContent = event.data.value + ': ' + (page.cues[event.data.value] || '[not in the cue list]');
    else if (!known(event.data.value)) document.getElementById('err').textContent += ' x ' + event.data.value; });
  const frame = document.createElement('iframe'); frame.id = 'stage';
  frame.setAttribute('sandbox', 'allow-scripts allow-forms allow-popups');
  // A released page carries its own recorded-voice helper; tell it the page is shown.
  frame.srcdoc = page.released ? page.html : withStub(page, true);
  frame.onload = () => frame.contentWindow.postMessage({ type: 'MIRA_NARRATION_VISIBILITY', visible: true }, '*');
  document.getElementById('host').replaceChildren(frame);
}
fetch('pages.json').then(r => r.json()).then(pages => params.get('auto') ? auto(pages) : view(pages, Number(params.get('page') || 2)));
</script>'''


FORWARD = ("<script>window.addEventListener('mira-narration-state',function(e){parent.postMessage("
           "{harness:true,kind:'state',value:String(e.detail.cueId)+':'+e.detail.status},'*')});</script>")


def released_page(html, media, store):
    """Embed one page like the student gateway (inline up to 2 MB, else blob URLs)."""
    assets = [{'path': item['path'], 'mimeType': item['mimeType'],
               'base64': b64encode((store / item['path'].split('/api/classroom-media/', 1)[1]).read_bytes()).decode()}
              for item in media if item['path'] in html]
    html = html.replace('</body>', FORWARD + '</body>') if '</body>' in html else html + FORWARD
    size = len(html) + sum(html.count(a['path']) * (len(a['base64']) + len(a['mimeType']) + 13) for a in assets)
    if size <= 2 * 1024 * 1024:
        for asset in assets:
            html = html.replace(asset['path'], f"data:{asset['mimeType']};base64,{asset['base64']}")
        return html
    page = json.dumps(html).replace('<', '\\u003c')
    listed = json.dumps(assets).replace('<', '\\u003c')
    return ('<!doctype html><html><head><meta charset="utf-8"></head><body><script>(function(){const assets=' + listed
            + ';let page=' + page + ';for(const asset of assets){const binary=atob(asset.base64);'
            'const bytes=new Uint8Array(binary.length);for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);'
            'const url=URL.createObjectURL(new Blob([bytes],{type:asset.mimeType}));page=page.split(asset.path).join(url);}'
            'document.open();document.write(page);document.close();})();</script></body></html>')


def build(source, target, store=None):
    saved = json.loads(source.read_text(encoding='utf-8'))
    release = saved.get('release', saved) if isinstance(saved.get('release', saved), dict) else saved
    if 'media' in release and 'classroom' in release:
        store = store or source.parent
        pages = []
        for index, scene in enumerate(release['classroom']['scenes'], 1):
            html = (scene.get('content') or {}).get('html') or ''
            cues = {cue['id']: cue['text'] for cue in interactive_cues(html)} if html else {}
            pages.append({'index': index, 'type': scene['type'], 'title': scene.get('title'), 'cues': cues,
                          'released': True, 'html': released_page(html, release['media'], store) if html else ''})
        target.mkdir(parents=True, exist_ok=True)
        (target / 'pages.json').write_text(json.dumps(pages, ensure_ascii=False), encoding='utf-8')
        (target / 'index.html').write_text(PAGE, encoding='utf-8')
        return len(pages)
    store = store or source.parent
    classroom = saved.get('classroom', saved)

    def inline(match):
        path = store / match.group(1) / match.group(2) / match.group(3)
        if not path.is_file() or path.suffix.lower() not in MIME:
            return match.group(0)
        return f'data:{MIME[path.suffix.lower()]};base64,' + base64.b64encode(path.read_bytes()).decode()

    pages = []
    for index, scene in enumerate(classroom['scenes'], 1):
        html = (scene.get('content') or {}).get('html') or ''
        cues = {cue['id']: cue['text'] for cue in interactive_cues(html)} if html else {}
        pages.append({'index': index, 'type': scene['type'], 'title': scene.get('title'),
                      'html': MEDIA.sub(inline, html), 'cues': cues})
    target.mkdir(parents=True, exist_ok=True)
    (target / 'pages.json').write_text(json.dumps(pages, ensure_ascii=False), encoding='utf-8')
    (target / 'index.html').write_text(PAGE, encoding='utf-8')
    return len(pages)


if __name__ == '__main__':
    arguments = sys.argv[1:]
    store = None
    if len(arguments) == 4 and arguments[2] == '--store':
        store = Path(arguments[3])
        arguments = arguments[:2]
    if len(arguments) != 2:
        sys.exit(__doc__)
    print(build(Path(arguments[0]), Path(arguments[1]), store), 'pages ->', arguments[1])
