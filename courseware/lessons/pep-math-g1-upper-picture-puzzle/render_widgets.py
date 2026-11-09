"""Compile the five editable exhibition activities into the courseware kit pages."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
HTML = '''<section id="board-target" aria-label="积木展台"><img id="board-image" draggable="false" alt="当前展台图"></section>
<div id="direction-mark" aria-hidden="true"></div>
<div id="piece-tray" role="group" aria-label="可选的积木图"></div>
<p id="board-caption" aria-live="polite"></p>'''
CSS = '''
html,body{background:#f4ecd9}
#cv{background:linear-gradient(146deg,#f9f4e6,#f0e4cc)}
#ready .pic{object-fit:contain;background:#f7f1df}
#board-target{position:absolute;left:72px;top:55px;width:496px;height:360px;display:grid;place-items:center;border:4px dashed #a18762;border-radius:28px;background:#fbf5e8}
#board-target.filled{border:4px solid #2f857a;background:#f5f8e8}
#board-image{width:432px;height:298px;object-fit:contain;border-radius:16px;pointer-events:none}
#direction-mark{position:absolute;left:586px;top:218px;width:64px;height:42px;background:#ae6432;clip-path:polygon(0 50%,38% 0,38% 28%,100% 28%,100% 72%,38% 72%,38% 100%)}
#piece-tray{position:absolute;left:666px;top:20px;width:485px;height:486px;display:grid;grid-template-rows:repeat(3,146px);gap:16px}
.piece-card{height:146px;display:grid;place-items:center;border:3px solid #a58b67;border-radius:24px;background:#fffaf0;color:#24464a;cursor:pointer;position:relative}
.piece-card img{display:block;width:196px;height:135px;object-fit:contain;border-radius:14px;pointer-events:none}
.piece-card:focus-visible{outline:5px solid #235b59;outline-offset:3px}
.piece-card.placed{border-color:#287568;background:#e1f1e2}
.piece-card:disabled{cursor:default}
.piece-card.fallback-picture img,#board-target.fallback-picture img{display:none}
.fallback-picture:after{content:attr(data-fallback);max-width:330px;font-size:28px;font-weight:700;line-height:1.2;text-align:center;color:#28484a}
#board-caption{position:absolute;left:72px;top:436px;width:496px;margin:0;text-align:center;font-size:28px;font-weight:750;color:#24464a}
'''
JS = '''(() => {
const cfg = __CONFIG__;
const board = K.$('#board-target');
const image = K.$('#board-image');
const tray = K.$('#piece-tray');
let level = 0, misses = 0, busy = false, demonstration = false, advance;
K.hud({icon:'◇',title:cfg.title,levels:cfg.rounds.length});
K.owl();
K.ready({emoji:'◇',title:cfg.title,sub:cfg.invite});

function show(parent, img, picture) {
    parent.classList.remove('fallback-picture');
    parent.dataset.fallback = picture.label;
    img.alt = picture.label;
    img.onerror = () => parent.classList.add('fallback-picture');
    img.src = picture.url;
}

function paint(result) {
    const round = cfg.rounds[level];
    show(board, image, result ? round.result : round.target);
    board.classList.toggle('filled', Boolean(result));
    K.$('#board-caption').textContent = result ? cfg.doneCaption : cfg.caption;
}

function load() {
    misses = 0;
    busy = false;
    paint(false);
    K.levels(cfg.rounds.length, level);
    K.say(cfg.invite);
    K.drags = [];
    tray.replaceChildren();
    const round = cfg.rounds[level];
    round.choices.forEach((picture, index) => {
        const button = K.el('button','piece-card','',tray);
        button.type = 'button';
        button.setAttribute('aria-label', picture.label);
        show(button, K.el('img','','',button), picture);
        button.firstChild.draggable = false;
        button.addEventListener('click', event => {
            if (!cfg.drag || event.detail === 0) choose(index, button);
        });
        if (cfg.drag) K.drag(button, {
            enabled: () => !demonstration && !busy,
            targets: () => [board],
            onTap: element => choose(index, element),
            onDrop: (element, target) => { if (target) choose(index, element); },
        });
    });
}

function choose(index, button) {
    if (demonstration || busy) return;
    const round = cfg.rounds[level];
    if (index !== round.answer) {
        misses += 1;
        K.sfx.no();
        K.shake(button);
        K.say(cfg.hints[Math.min(misses, cfg.hints.length)-1], 'no');
        if (misses >= 2) K.highlight('#board-target');
        return;
    }
    busy = true;
    button.style.transition = 'none';
    paint(true);
    button.classList.add('placed');
    for (const choice of tray.children) choice.disabled = true;
    K.star(1,button);
    K.sfx.ok();
    K.say(cfg.success, 'ok');
    advance = setTimeout(() => {
        if (level + 1 === cfg.rounds.length) {
            K.levels(cfg.rounds.length, cfg.rounds.length);
            K.finish({title:cfg.finish,sub:cfg.summary,again:reset});
            return;
        }
        level += 1;
        load();
    }, 1150);
}

function reset() {
    clearTimeout(advance);
    level = 0;
    demonstration = false;
    K.stars = 0;
    K.$('#star-n').textContent = '0';
    load();
}

K.onStart = reset;
K.onState = state => {
    if (state.demo) { reset(); demonstration = true; }
    if (state.demoResult) { demonstration = true; paint(true); }
    if (state.play) reset();
};
load();
})();
'''


def picture(key, label):
    return {'url': f'__IMG:{key}__', 'label': label}


def round_spec(target, result, choices, answer):
    return {'target': picture(*target), 'result': picture(*result),
            'choices': [picture(*item) for item in choices], 'answer': answer}


CUBE = ('single-cube', '一个小正方体')
HORIZONTAL = ('row-two', '横排的两块小正方体')
VERTICAL = ('tower-two', '竖叠的两块小正方体')
LAYER = ('layer-four', '两排各两块的小正方体')
LONG = ('single-bar', '长方体积木')
BALL = ('ball', '没有平面的球')
CYLINDER = ('cylinder', '有圆面的圆柱')
PAIR = ('piece-pair', '横着连在一起的两块')
UPRIGHT = ('piece-upright', '竖着连在一起的两块')
ELBOW = ('piece-elbow', '转角相连的三块')
LINE = ('piece-line', '横着连在一起的三块')


def widget(title, invite, caption, done_caption, hints, success, finish, summary, drag, rounds):
    return dict(title=title, invite=invite, caption=caption, doneCaption=done_caption,
                hints=hints, success=success, finish=finish, summary=summary, drag=drag, rounds=rounds)


WIDGETS = {
    'p02': widget('把积木送到同形展台', '看展台，点一个同形的积木', '展台样品', '积木已经入展',
        ['先看看有没有平面。','再比平面的形状和长短。'], '换了颜色或方向，形状还能认出来。',
        '积木都进展台了', '认立体图形，先看看它的面。', False, [
        round_spec(('match-cube','红色小正方体'), CUBE, [LONG,CUBE,CYLINDER], 1),
        round_spec(('match-cylinder','较粗的圆柱'), CYLINDER, [CYLINDER,BALL,LONG], 0),
        round_spec(('match-bar','转了方向的长方体'), LONG, [BALL,CUBE,LONG], 2),
    ]),
    'p04': widget('沿着接缝拼', '看浅色空位，把合适的积木放过去', '浅色地方还空着', '平面贴好了',
        ['先比空位朝哪边伸。','数一数空位，再对着它的方向比。'], '积木贴住接缝，轮廓就完整了。',
        '三种摆法都拼好了', '积木可以排成直线，也可以转个弯。', True, [
        round_spec(('join-x','右边连着两个浅色空位'),('row-three','横排的三块小正方体'),[CUBE,VERTICAL,HORIZONTAL],2),
        round_spec(('join-z','上面连着两个浅色空位'),('tower-three','竖叠的三块小正方体'),[VERTICAL,HORIZONTAL,CUBE],0),
        round_spec(('join-bend','右边积木上方有一个浅色空位'),('step-three','三块小正方体拼成的台阶'),[VERTICAL,CUBE,HORIZONTAL],1),
    ]),
    'p06': widget('叠出大正方体', '看缺了哪里，点能填满空位的一组', '积木的空位', '这一层补齐了',
        ['先看缺的是一块、一排，还是一层。','从左到右，再从前往后比空位。'], '这一组积木填满了空位。',
        '大正方体拼好了', '底下四块，上面四块。', False, [
        round_spec(('cube-base-corner','底层四格里有一格空位'),LAYER,[VERTICAL,CUBE,HORIZONTAL],1),
        round_spec(('cube-upper-pair','底层四块，上层后排两块，前排两格空着'),('big-cube','两层各四块的大正方体'),[LAYER,VERTICAL,HORIZONTAL],2),
        round_spec(('cube-upper-layer','上层四格都空着'),('big-cube','两层各四块的大正方体'),[LAYER,('tower-three','竖叠的三块'),('row-three','横排的三块')],0),
    ]),
    'p08': widget('把圆面对齐', '看两边的轮廓，点能让圆面齐齐叠好的图', '对齐前', '圆面对齐了',
        ['看看侧边有没有错开。','从底下往上比，圆面要一样大。'], '边缘接齐，拼成一个更高的圆柱。',
        '圆柱接齐了', '让一样大的圆面贴在一起。', False, [
        round_spec(('cylinder-shifted','上段往右偏的两段圆柱'),('cylinder-two','两段一样粗的圆柱对齐'),[('cylinder-shift-left','上段往左偏的两段圆柱'),('cylinder-two','圆面对齐的两段圆柱'),('cylinder-shifted','上段往右偏的两段圆柱')],1),
        round_spec(('cylinder-three-shift','上段错位的三段圆柱'),('cylinder-three','三段圆面对齐的圆柱'),[('cylinder-three','三段圆面对齐的圆柱'),('cylinder-three-thin','最上段比底下两段细'),('cylinder-three-shift','最上段往右偏')],0),
    ]),
    'p10': widget('补齐展台的空位', '看浅色缺口，拖入同样大小和形状的补块', '从上往下看', '空位全填满了',
        ['先看看补块和空位是不是一样多。','格数一样，还要看哪边长、哪里转弯。'], '格数和轮廓都一样，正好补进去。',
        '展台全补齐了', '先数有几格，再比形状。', True, [
        round_spec(('gap-demo','右下有两个横排空位'),('gap-demo-filled','两块横排补好'),[UPRIGHT,ELBOW,PAIR],2),
        round_spec(('gap-column','左侧有两个竖排空位'),('gap-column-filled','两块竖排补好'),[UPRIGHT,PAIR,LINE],0),
        round_spec(('gap-elbow','左下有三个拐角空位'),('gap-elbow-filled','三块转角补好'),[LINE,ELBOW,('piece-square','四块拼成的正方形')],1),
    ]),
}


def main():
    out = ROOT / 'pages'
    out.mkdir(exist_ok=True)
    for key, config in WIDGETS.items():
        files = {'html': HTML, 'css': CSS,
                 'js': JS.replace('__CONFIG__', json.dumps(config, ensure_ascii=False, indent=2))}
        for extension, text in files.items():
            (out / f'{key}.{extension}').write_text(text.rstrip() + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
