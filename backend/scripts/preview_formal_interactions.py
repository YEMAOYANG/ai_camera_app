#!/usr/bin/env python3
"""Extract frozen interactive HTML for manual operation; no services or QA receipts."""
from __future__ import annotations
import argparse
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / 'openmaic-runtime/.runtime/OpenMAIC/data/formal-quality-reviews'


def build(source: Path, output: Path | None = None):
    source = source.resolve(strict=True)
    if not source.is_relative_to(SOURCE_ROOT.resolve()) or not source.name.endswith('-input.json'):
        raise ValueError('use a saved formal-quality-reviews/*/*-input.json')
    payload = json.loads(source.read_text(encoding='utf-8'))
    snapshot = payload['snapshot']
    canonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    if source.name[:64] != digest:
        raise ValueError('snapshot hash does not match the saved review filename')
    pages = []
    for scene in snapshot['scenes']:
        if scene.get('type') != 'interactive':
            continue
        original = scene.get('content', {}).get('html')
        if not isinstance(original, str) or not original.strip():
            raise ValueError('interactive scene has no original HTML')
        pages.append({'id': scene['id'], 'title': scene['title'], 'html': original})
    if not pages:
        raise ValueError('snapshot contains no interactive scenes')
    output = (output or ROOT / 'output' / f'formal-interactions-{digest}.html').resolve()
    if not output.is_relative_to((ROOT / 'output').resolve()) or output.suffix != '.html':
        raise ValueError('preview must be an HTML file under repository output/')
    output.parent.mkdir(parents=True, exist_ok=True)
    # Escaping only the outer JSON transport preserves every inner HTML character.
    data = json.dumps(pages, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    document = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>正式课件人工交互预览</title><style>body{margin:16px;font:14px sans-serif;background:#eee}header{margin-bottom:12px}select{margin-right:12px}iframe{display:block;border:1px solid #aaa;background:white}</style>
<header><strong>人工交互预览（非学生入口）</strong><p>仅展示冻结 HTML；不生成或替代任何 QA 通过回执。</p>
<p>快照 SHA256：<code>__SHA__</code></p><label>页面 <select id="page"></select></label>
<label>尺寸 <select id="size"><option value="1280,720">1280 × 720</option><option value="1024,768">1024 × 768</option></select></label><span id="identity"></span></header>
<iframe id="preview" title="原始互动课件" sandbox="allow-scripts" width="1280" height="720"></iframe>
<script>const pages=__PAGES__;const choose=document.getElementById('page'),frame=document.getElementById('preview'),size=document.getElementById('size');
for(const [i,p] of pages.entries()){const o=document.createElement('option');o.value=i;o.textContent=p.title;choose.append(o)}
function show(){const p=pages[Number(choose.value)];frame.srcdoc=p.html;document.getElementById('identity').textContent=p.id}
choose.addEventListener('change',show);size.addEventListener('change',()=>{const[w,h]=size.value.split(',');frame.width=w;frame.height=h});show();</script></html>'''
    output.write_text(document.replace('__SHA__', html.escape(digest)).replace('__PAGES__', data), encoding='utf-8')
    return {'previewFile': str(output), 'snapshotSha256': digest, 'interactiveSceneCount': len(pages)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), ensure_ascii=False))
