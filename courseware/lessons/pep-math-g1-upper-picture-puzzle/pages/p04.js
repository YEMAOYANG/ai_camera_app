(() => {
const cfg = {
  "title": "沿着接缝拼",
  "invite": "看浅色空位，把合适的积木放过去",
  "caption": "浅色地方还空着",
  "doneCaption": "平面贴好了",
  "hints": [
    "先比空位朝哪边伸。",
    "数一数空位，再对着它的方向比。"
  ],
  "success": "积木贴住接缝，轮廓就完整了。",
  "finish": "三种摆法都拼好了",
  "summary": "积木可以排成直线，也可以转个弯。",
  "drag": true,
  "rounds": [
    {
      "target": {
        "url": "__IMG:join-x__",
        "label": "右边连着两个浅色空位"
      },
      "result": {
        "url": "__IMG:row-three__",
        "label": "横排的三块小正方体"
      },
      "choices": [
        {
          "url": "__IMG:single-cube__",
          "label": "一个小正方体"
        },
        {
          "url": "__IMG:tower-two__",
          "label": "竖叠的两块小正方体"
        },
        {
          "url": "__IMG:row-two__",
          "label": "横排的两块小正方体"
        }
      ],
      "answer": 2
    },
    {
      "target": {
        "url": "__IMG:join-z__",
        "label": "上面连着两个浅色空位"
      },
      "result": {
        "url": "__IMG:tower-three__",
        "label": "竖叠的三块小正方体"
      },
      "choices": [
        {
          "url": "__IMG:tower-two__",
          "label": "竖叠的两块小正方体"
        },
        {
          "url": "__IMG:row-two__",
          "label": "横排的两块小正方体"
        },
        {
          "url": "__IMG:single-cube__",
          "label": "一个小正方体"
        }
      ],
      "answer": 0
    },
    {
      "target": {
        "url": "__IMG:join-bend__",
        "label": "右边积木上方有一个浅色空位"
      },
      "result": {
        "url": "__IMG:step-three__",
        "label": "三块小正方体拼成的台阶"
      },
      "choices": [
        {
          "url": "__IMG:tower-two__",
          "label": "竖叠的两块小正方体"
        },
        {
          "url": "__IMG:single-cube__",
          "label": "一个小正方体"
        },
        {
          "url": "__IMG:row-two__",
          "label": "横排的两块小正方体"
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
