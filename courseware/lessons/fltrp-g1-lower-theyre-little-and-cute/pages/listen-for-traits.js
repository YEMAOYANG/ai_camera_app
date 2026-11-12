const cards = {
  "horses-little": "__IMG:horses-little__",
  "horses-big": "__IMG:horses-big__",
  "horses-big-lift": "__IMG:horses-big-lift__",
  "horses-big-ground": "__IMG:horses-big-ground__",
  "horses-small-lift": "__IMG:horses-small-lift__",
  "pandas-little-lift": "__IMG:pandas-little-lift__",
  "pandas-big-lift": "__IMG:pandas-big-lift__",
  "pandas-low-ground": "__IMG:pandas-little-ground__"
};
const pictures = Object.fromEntries(Object.entries(cards).map(([id, url]) => {
  const image = new Image();
  image.src = url;
  return [id, image];
}));
const hints = ["再听线索，再看看图。", "找亮起来的图，移到它下面。"];
const firstDrift = 0;
const firstPace = .50;
const makeCues = (steps) => ({goal: steps[0], steps, hint: "trait-hint", hint2: "trait-help", praise: "trait-praise"});

K.ready({title: "听线索，吹泡泡", sub: "听完再瞄准图卡。用箭头移小艇，点圆圈吹泡泡。"});

const options = K.gameTemplates.wordBubbles({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    makeCues(["little-horses", "big-horses"]),
    makeCues(["big-and-strong", "little-and-strong", "box-down-big"]),
    makeCues(["little-and-strong", "big-and-strong", "box-down-little"])
  ],
  art: {
    backdrop: "__IMG:exhibit-pond__", sticker: "__IMG:exhibit-sticker__",
    frames: ["__IMG:bubble-boat__", "__IMG:bubble-boat-action__"], icons: cards
  },
  doneText: "图卡找齐，展览开门啦！",
  levels: [
    {rounds: [
      {cards: ["horses-little", "horses-big"], target: "horses-little"},
      {cards: ["horses-little", "horses-big"], target: "horses-big"}
    ], drift: firstDrift, pace: firstPace, tolerance: 62, hints},
    {rounds: [
      {cards: ["horses-big-ground", "horses-big-lift", "horses-small-lift"], target: "horses-big-lift"},
      {cards: ["horses-small-lift", "horses-big-lift", "horses-big-ground"], target: "horses-small-lift"},
      {cards: ["horses-big-lift", "horses-small-lift", "horses-big-ground"], target: "horses-big-ground"}
    ], drift: 22, pace: .79, tolerance: 57, hints},
    {rounds: [
      {cards: ["pandas-low-ground", "pandas-big-lift", "pandas-little-lift"], target: "pandas-little-lift"},
      {cards: ["pandas-little-lift", "pandas-big-lift", "pandas-low-ground"], target: "pandas-big-lift"},
      {cards: ["pandas-little-lift", "pandas-low-ground", "pandas-big-lift"], target: "pandas-low-ground"}
    ], drift: 38, pace: 1.05, tolerance: 51, hints}
  ]
});

const targetX = (level, world, count, index) => {
  const gap = count === 2 ? 310 : 238;
  return 640 + (index - (count - 1) / 2) * gap
    + Math.sin(world.t * level.pace + index * 1.48 + world.round * .9) * level.drift;
};
const paint = (context, x, y, width, height, radius, fill) => {
  context.fillStyle = fill;
  K.draw.rr(context, x, y, width, height, radius);
  context.fill();
};

function miniature(context, id, x, y) {
  const small = id.includes("little") || id.includes("small") || id.includes("low");
  const width = small ? 26 : 41;
  const height = small ? 31 : 47;
  const floor = y + 31;
  for (const dx of [-42, 42]) {
    const body = id.startsWith("pandas") ? "#51504c" : "#ac633b";
    paint(context, x + dx - width / 2, floor - height, width, height, 9, body);
    context.fillStyle = "#fff0c9";
    K.draw.circle(context, x + dx, floor - height + 12, 7);
  }
  if (id.endsWith("lift") || id.endsWith("ground")) {
    const blockY = id.endsWith("lift") ? floor - 39 : floor - 14;
    paint(context, x - 20, blockY, 40, 14, 4, "#bb7945");
  }
}

const draw = options.draw;
options.draw = (frame, context) => {
  draw(frame, context);
  const {w: world, level} = frame.data;
  const round = level?.rounds[world?.round];
  if (!round) return;
  round.cards.forEach((id, index) => {
    const x = targetX(level, world, round.cards.length, index);
    const guided = world.help && id === round.target;
    paint(context, x - 88, 185, 176, 130, 24, guided ? "#ffd276" : "#91c5b8");
    paint(context, x - 80, 193, 160, 114, 18, "#fff1d1");
    const image = pictures[id];
    if (image.naturalWidth) context.drawImage(image, x - 77, 201, 154, 98);
    else miniature(context, id, x, 250);
    context.strokeStyle = guided ? "#5b7359" : "#385e5a";
    context.lineWidth = 3;
    context.beginPath();
    context.arc(x, 317, 9, 0, Math.PI * 2);
    context.stroke();
  });
  if (world.shot && world.shot.y < 328) {
    context.fillStyle = "#cbfffaad";
    K.draw.circle(context, world.shot.x, world.shot.y, 15);
    context.strokeStyle = "#f5fff9";
    context.lineWidth = 3;
    context.stroke();
  }
};
options.bubbleAt = () => ({x: 640, y: 369});
options.onState = (_frame, state) => {
  if (state.demo === false) K.$$(".teach-hl").forEach((element) => element.classList.remove("teach-hl"));
};

const game = K.game(options);
game.follow("#first-toy-picture", () => ({x: 397, y: 185, w: 176, h: 130}));
game.follow("#bubble-replay-anchor", () => {
  const replay = K.$(".arc-voice");
  return replay && replay.offsetWidth ? K.pos(replay) : null;
});
