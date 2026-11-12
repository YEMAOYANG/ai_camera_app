const groups = (id) => id.split("-").slice(1).map(Number);
const sum = (id) => groups(id).reduce((total, count) => total + count, 0);
const sameTotal = (launch, target) => sum(launch) === sum(target);
const labels = Object.fromEntries(
  ["a-8-6", "a-8-3", "a-6-7", "a-4-7", "a-7-8", "a-6-8", "a-6-9", "a-8-8"]
    .map(id => [id, groups(id).join("+")])
);
const cuesFor = (steps) => ({
  goal: steps[0], steps, hint: "target-hint", hint2: "target-help", praise: "target-praise"
});
const targets = (positions, values) => positions.map((x, i) => ({x, value: values[i]}));
const hints = [
  "先凑十，再看还剩几片。找到同样多的靶。",
  "往亮起来的靶瞄准，弹珠飞出去也能再转一点。"
];
const levels = [
  {queue: ["a-8-6", "a-8-3"], targets: targets([430, 650, 870], ["total-14", "total-13", "total-11"]),
    speed: 405, drift: 4, targetWidth: 174, targetHeight: 101, symbol: "↔"},
  {queue: ["a-6-7", "a-4-7", "a-7-8"],
    targets: targets([354, 545, 735, 927], ["pair-8-7", "pair-7-6", "pair-8-8", "pair-7-4"]),
    speed: 492, drift: 11, targetWidth: 154, targetHeight: 99, symbol: "↔"},
  {queue: ["a-6-8", "a-6-9", "a-8-8"],
    targets: targets([354, 545, 735, 927], ["total-17", "total-15", "total-14", "total-16"]),
    speed: 570, drift: 16, targetWidth: 153, targetHeight: 96, symbol: "↔"}
].map(level => ({...level, labels, hints, matches: sameTotal}));

K.ready({title: "瞄准同样多的灯片", sub: "先看两组有几片，找同样多的靶。左右瞄准，点箭头发射。"});

const amber = new Image(), mint = new Image();
amber.src = "__IMG:tile-amber__";
mint.src = "__IMG:tile-mint__";
const paintBox = (context, x, y, width, height, radius, color) => {
  context.fillStyle = color;
  K.draw.rr(context, x, y, width, height, radius);
  context.fill();
};
const options = K.gameTemplates.magnetMarbles({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    cuesFor(["shot-eight-six", "shot-eight-three"]),
    cuesFor(["shot-six-seven", "shot-four-seven", "shot-seven-eight"]),
    cuesFor(["shot-six-eight", "shot-six-nine", "shot-eight-eight"])
  ],
  art: {
    backdrop: "__IMG:marble-pier__", sticker: "__IMG:lantern-badge__", frames: ["__IMG:launch-orb__"],
    icons: {
      "total-11": "__IMG:total-11__", "total-13": "__IMG:total-13__", "total-14": "__IMG:total-14__",
      "total-15": "__IMG:total-15__", "total-16": "__IMG:total-16__", "total-17": "__IMG:total-17__",
      "pair-8-7": "__IMG:pair-8-7__", "pair-7-6": "__IMG:pair-7-6__",
      "pair-8-8": "__IMG:pair-8-8__", "pair-7-4": "__IMG:pair-7-4__"
    }
  },
  doneText: "每颗弹珠都找到了同样多的灯片！",
  levels
});

const drawGame = options.draw;
options.draw = (game, context) => {
  drawGame(game, context);
  const world = game.data.w;
  const current = world && game.data.level.queue[world.i];
  if (!current) return;
  const [a, b] = groups(current);
  paintBox(context, 19, 257, 181, 196, 17, "#275541");
  paintBox(context, 24, 262, 171, 186, 14, "#fff4db");
  [a, b].forEach((count, group) => {
    const art = group ? mint : amber;
    const shade = group ? "#39795e" : "#b96225";
    for (let i = 0; i < count; i += 1) {
      const x = 49 + (i % 5) * 30;
      const y = 289 + Math.floor(i / 5) * 27 + group * 69;
      if (art.complete && art.naturalWidth) context.drawImage(art, x - 11, y - 11, 22, 22);
      else paintBox(context, x - 9, y - 9, 18, 18, 4, shade);
    }
  });
  K.draw.text(context, labels[current], 109, 429, 29, "#264d3c");
};

const marble = K.game(options);
marble.follow("#count-preview", () => ({x: 19, y: 257, w: 181, h: 196}));
marble.follow("#same-first-target", (game) => {
  const time = game.data.w?.time ?? 0;
  const first = levels[0].targets[0];
  const x = first.x + Math.sin(time * 2.4 + first.x * .019) * levels[0].drift;
  return {x: x - 87, y: 178.5, w: 174, h: 101};
});
