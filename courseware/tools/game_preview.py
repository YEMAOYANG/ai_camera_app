"""Build the shared game examples as local HTML, without a lesson or publishing."""
import argparse
from html import escape
import json
from pathlib import Path

from courseware.kit.page import page
from courseware.kit.game_templates import _CLASSIC

EXAMPLES = Path(__file__).resolve().parents[1] / 'kit' / 'examples' / 'classic-arcade'
ANCHORS = ''.join(f'<div id="game-{name}"></div>' for name in ('goal', 'player', 'target'))
PREVIEW_ORDER = ('magnet-marbles', 'firefly-swing', 'shutter-scout', 'shadow-stage', 'wind-courier',
                 'falling-tiles', 'bubble-maze', 'platform-hop')


def _js(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).replace('<', r'\u003c')


def build_examples(destination, *, assets='assets', audio=None, tests=False, include_drafts=False):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    cards = {}
    for preset in sorted(EXAMPLES.glob('*.json')):
        config = json.loads(preset.read_text(encoding='utf-8'))
        if config.pop('draft', False) and not include_drafts:
            continue
        template = config.pop('template')
        if template not in _CLASSIC:
            raise ValueError(f'unknown preview template: {template}')
        title = config.pop('title')
        sub = config.pop('sub')
        for key, value in config['art'].items():
            convert = lambda name: f'{assets}/{name}' if assets is not None else None
            if isinstance(value, list):
                config['art'][key] = [convert(name) for name in value]
            elif isinstance(value, dict):
                config['art'][key] = {token: convert(name) for token, name in value.items()}
            else:
                config['art'][key] = convert(value)
        voices = (audio or {}).get(preset.stem)
        narration = ''
        if voices:
            config['cues'] = voices['cues']
            # Standalone preview only. Published pages bind cues through game_audio.
            narration = '''
let clip;const recordings=RECORDINGS;
window.miraCancelNarration=()=>{if(clip){clip.pause();clip=null;}};
window.miraNarrate=id=>{
  window.miraCancelNarration();
  if(!recordings[id])return;
  const a=clip=new Audio(recordings[id]);
  const state=status=>window.dispatchEvent(new CustomEvent('mira-narration-state',{detail:{cueId:id,status}}));
  a.addEventListener('ended',()=>{if(clip===a)state('ready');},{once:true});
  a.play().then(()=>{if(clip===a)state('playing');}).catch(()=>{if(clip===a)state('ready');});
};
'''.replace('RECORDINGS', _js(voices['files']))
        js = (
            narration
            + f'K.ready({_js(dict(title=escape(title), sub=escape(sub), img=config["art"]["backdrop"]))});\n'
            + f'K.game(K.gameTemplates.{template}({_js(config)}));'
        )
        result = destination / (preset.stem + '.html')
        result.write_text(page(title, ANCHORS, '', js, tests=tests), encoding='utf-8')
        cards[preset.stem] = f'<a href="{result.name}"><strong>{escape(title)}</strong><span>{escape(sub)}</span></a>'
    index = destination / 'index.html'
    index.write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mira 游戏试玩</title><style>
body{background:#193931;color:#fff1d3;font:20px/1.55 system-ui,sans-serif;margin:7vh auto;width:min(90%,750px)}
h1{font-size:clamp(32px,8vw,62px);line-height:1.1;margin:.3em 0}h2{font-size:22px;margin:30px 0 12px}
section{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,215px),1fr));gap:13px}
a{display:block;background:#f1d39f;color:#203e34;border-radius:18px;padding:17px 19px;text-decoration:none}
a strong,a span{display:block}a span{font-size:15px;line-height:1.4;margin-top:6px}a:focus-visible{outline:4px solid white}
</style><p>MIRA · 一年级课件样品</p><h1>选一个游戏</h1>
<p>可用键盘方向键和空格，也可用鼠标或触屏点游戏里的大按钮。</p>'''
                     + '<h2>原创玩法</h2><section>' + ''.join(cards.pop(key) for key in PREVIEW_ORDER[:5] if key in cards)
                     + '</section><h2>经典玩法</h2><section>' + ''.join(cards.pop(key) for key in PREVIEW_ORDER[5:] if key in cards)
                     + '</section>' + ('<h2>内部试作</h2><section>' + ''.join(cards.values()) + '</section>' if cards else '')
                     + '</html>', encoding='utf-8')
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--audio-map', type=Path)
    parser.add_argument('--include-drafts', action='store_true')
    args = parser.parse_args(argv)
    voices = json.loads(args.audio_map.read_text(encoding='utf-8')) if args.audio_map else None
    print(build_examples(args.destination, audio=voices, include_drafts=args.include_drafts))


if __name__ == '__main__':
    main()
