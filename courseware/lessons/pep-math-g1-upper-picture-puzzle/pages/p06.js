(() => {
const cfg = {
  "title": "叠出大正方体",
  "invite": "看缺了哪里，点能填满空位的一组",
  "caption": "积木的空位",
  "doneCaption": "这一层补齐了",
  "hints": [
    "先看缺的是一块、一排，还是一层。",
    "从左到右，再从前往后比空位。"
  ],
  "success": "这一组积木填满了空位。",
  "finish": "大正方体拼好了",
  "summary": "底下四块，上面四块。",
  "drag": false,
  "rounds": [
    {
      "target": {
        "url": "__IMG:cube-base-corner__",
        "label": "底层四格里有一格空位"
      },
      "result": {
        "url": "__IMG:layer-four__",
        "label": "两排各两块的小正方体"
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
    },
    {
      "target": {
        "url": "__IMG:cube-upper-pair__",
        "label": "底层四块，上层后排两块，前排两格空着"
      },
      "result": {
        "url": "__IMG:big-cube__",
        "label": "两层各四块的大正方体"
      },
      "choices": [
        {
          "url": "__IMG:layer-four__",
          "label": "两排各两块的小正方体"
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
        "url": "__IMG:cube-upper-layer__",
        "label": "上层四格都空着"
      },
      "result": {
        "url": "__IMG:big-cube__",
        "label": "两层各四块的大正方体"
      },
      "choices": [
        {
          "url": "__IMG:layer-four__",
          "label": "两排各两块的小正方体"
        },
        {
          "url": "__IMG:tower-three__",
          "label": "竖叠的三块"
        },
        {
          "url": "__IMG:row-three__",
          "label": "横排的三块"
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
