(() => {
const cfg = {
  "title": "把圆面对齐",
  "invite": "看两边的轮廓，点能让圆面齐齐叠好的图",
  "caption": "对齐前",
  "doneCaption": "圆面对齐了",
  "hints": [
    "看看侧边有没有错开。",
    "从底下往上比，圆面要一样大。"
  ],
  "success": "边缘接齐，拼成一个更高的圆柱。",
  "finish": "圆柱接齐了",
  "summary": "让一样大的圆面贴在一起。",
  "drag": false,
  "rounds": [
    {
      "target": {
        "url": "__IMG:cylinder-shifted__",
        "label": "上段往右偏的两段圆柱"
      },
      "result": {
        "url": "__IMG:cylinder-two__",
        "label": "两段一样粗的圆柱对齐"
      },
      "choices": [
        {
          "url": "__IMG:cylinder-shift-left__",
          "label": "上段往左偏的两段圆柱"
        },
        {
          "url": "__IMG:cylinder-two__",
          "label": "圆面对齐的两段圆柱"
        },
        {
          "url": "__IMG:cylinder-shifted__",
          "label": "上段往右偏的两段圆柱"
        }
      ],
      "answer": 1
    },
    {
      "target": {
        "url": "__IMG:cylinder-three-shift__",
        "label": "上段错位的三段圆柱"
      },
      "result": {
        "url": "__IMG:cylinder-three__",
        "label": "三段圆面对齐的圆柱"
      },
      "choices": [
        {
          "url": "__IMG:cylinder-three__",
          "label": "三段圆面对齐的圆柱"
        },
        {
          "url": "__IMG:cylinder-three-thin__",
          "label": "最上段比底下两段细"
        },
        {
          "url": "__IMG:cylinder-three-shift__",
          "label": "最上段往右偏"
        }
      ],
      "answer": 0
    }
  ]
};
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
