K.ready({
  title: '观察镜走哪边',
  sub: '按住镜面，从动物的头慢慢看到尾，记下看过的部位。',
  img: '__IMG:station__'
});

const imageBox = [640, 450, 752, 423];

function round(animal, head, points, {mirror = false} = {}) {
  const [cx, cy, w, h] = imageBox;
  const routePoints = points.map(([x, y]) => [
    cx + (mirror ? 512 - x : x - 512) * w / 1024,
    cy + (y - 288) * h / 576
  ]);
  return {
    goal: {image: head, fallback: {image: animal, fallback: '先找头'}},
    background: {image: animal, fallback: {image: head, fallback: '先找头'}},
    imageBox,
    mirrorImage: mirror,
    strokes: [routePoints],
    vehicle: 'lens',
    hint: '慢一点，把观察镜放回刚才看过的地方。',
    hint2: '从头往后看，经过身子和脚，最后找尾巴。',
    success: '从头往后看，脚和尾巴都找到了。'
  };
}

const orange = [[286,162], [378,224], [520,251], [421,345], [366,490], [640,489], [709,347], [891,420]];
const white = [[329,227], [432,268], [552,300], [442,370], [409,493], [646,493], [702,391], [785,383]];
const brown = [[325,230], [432,269], [547,298], [428,374], [390,493], [638,496], [712,390], [804,376]];

K.game(K.gameTemplates.trace({
  goalHeight: 111,
  doneText: '两只动物方向会变，观察次序一样。把真的看到的画下来。',
  levels: [
    {
      name: '沿观察路线看猫',
      rounds: [round('__IMG:cat-orange__', '__IMG:cat-ear__', orange)]
    },
    {
      name: '兔换朝向，再从头看起',
      rounds: [
        round('__IMG:rabbit-white__', '__IMG:rabbit-ear__', white),
        round('__IMG:rabbit-brown__', '__IMG:rabbit-ear__', brown, {mirror: true})
      ]
    }
  ]
}));
