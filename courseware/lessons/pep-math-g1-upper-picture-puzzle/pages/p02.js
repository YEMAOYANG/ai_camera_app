(() => {
const cfg = {
  "title": "把积木送到同形展台",
  "invite": "看展台，点一个同形的积木",
  "caption": "展台样品",
  "doneCaption": "积木已经入展",
  "hints": [
    "先看看有没有平面。",
    "再比平面的形状和长短。"
  ],
  "success": "换了颜色或方向，形状还能认出来。",
  "finish": "积木都进展台了",
  "summary": "认立体图形，先看看它的面。",
  "drag": false,
  "rounds": [
    {
      "target": {
        "url": "__IMG:match-cube__",
        "label": "红色小正方体"
      },
      "result": {
        "url": "__IMG:single-cube__",
        "label": "一个小正方体"
      },
      "choices": [
        {
          "url": "__IMG:single-bar__",
          "label": "长方体积木"
        },
        {
          "url": "__IMG:single-cube__",
          "label": "一个小正方体"
        },
        {
          "url": "__IMG:cylinder__",
          "label": "有圆面的圆柱"
        }
      ],
      "answer": 1
    },
    {
      "target": {
        "url": "__IMG:match-cylinder__",
        "label": "较粗的圆柱"
      },
      "result": {
        "url": "__IMG:cylinder__",
        "label": "有圆面的圆柱"
      },
      "choices": [
        {
          "url": "__IMG:cylinder__",
          "label": "有圆面的圆柱"
        },
        {
          "url": "__IMG:ball__",
          "label": "没有平面的球"
        },
        {
          "url": "__IMG:single-bar__",
          "label": "长方体积木"
        }
      ],
      "answer": 0
    },
    {
      "target": {
        "url": "__IMG:match-bar__",
        "label": "转了方向的长方体"
      },
      "result": {
        "url": "__IMG:single-bar__",
        "label": "长方体积木"
      },
      "choices": [
        {
          "url": "__IMG:ball__",
          "label": "没有平面的球"
        },
        {
          "url": "__IMG:single-cube__",
          "label": "一个小正方体"
        },
        {
          "url": "__IMG:single-bar__",
          "label": "长方体积木"
        }
      ],
      "answer": 2
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
