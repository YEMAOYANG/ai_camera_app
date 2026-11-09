(() => {
const cfg = {
  "title": "补齐展台的空位",
  "invite": "看浅色缺口，拖入同样大小和形状的补块",
  "caption": "从上往下看",
  "doneCaption": "空位全填满了",
  "hints": [
    "先看看补块和空位是不是一样多。",
    "格数一样，还要看哪边长、哪里转弯。"
  ],
  "success": "格数和轮廓都一样，正好补进去。",
  "finish": "展台全补齐了",
  "summary": "先数有几格，再比形状。",
  "drag": true,
  "rounds": [
    {
      "target": {
        "url": "__IMG:gap-demo__",
        "label": "右下有两个横排空位"
      },
      "result": {
        "url": "__IMG:gap-demo-filled__",
        "label": "两块横排补好"
      },
      "choices": [
        {
          "url": "__IMG:piece-upright__",
          "label": "竖着连在一起的两块"
        },
        {
          "url": "__IMG:piece-elbow__",
          "label": "转角相连的三块"
        },
        {
          "url": "__IMG:piece-pair__",
          "label": "横着连在一起的两块"
        }
      ],
      "answer": 2
    },
    {
      "target": {
        "url": "__IMG:gap-column__",
        "label": "左侧有两个竖排空位"
      },
      "result": {
        "url": "__IMG:gap-column-filled__",
        "label": "两块竖排补好"
      },
      "choices": [
        {
          "url": "__IMG:piece-upright__",
          "label": "竖着连在一起的两块"
        },
        {
          "url": "__IMG:piece-pair__",
          "label": "横着连在一起的两块"
        },
        {
          "url": "__IMG:piece-line__",
          "label": "横着连在一起的三块"
        }
      ],
      "answer": 0
    },
    {
      "target": {
        "url": "__IMG:gap-elbow__",
        "label": "左下有三个拐角空位"
      },
      "result": {
        "url": "__IMG:gap-elbow-filled__",
        "label": "三块转角补好"
      },
      "choices": [
        {
          "url": "__IMG:piece-line__",
          "label": "横着连在一起的三块"
        },
        {
          "url": "__IMG:piece-elbow__",
          "label": "转角相连的三块"
        },
        {
          "url": "__IMG:piece-square__",
          "label": "四块拼成的正方形"
        }
      ],
      "answer": 1
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
