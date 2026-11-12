const cuesFor = (goal, steps) => ({
  goal, steps, hint: "catch-hint", hint2: "catch-help", praise: "catch-praise"
});
const hints = [
  "数数空格。整串不能拆。",
  "先到亮线下，再选篮。"
];

K.ready({title: "接灯片，补满十格", sub: "把补十的灯片放左篮，其余放右篮。用双箭头换篮。"});

const artwork = new Image();
artwork.src = "__IMG:tile-amber__";
const paintBox = (context, x, y, width, height, radius, color) => {
  context.fillStyle = color;
  K.draw.rr(context, x, y, width, height, radius);
  context.fill();
};
const options = K.gameTemplates.orchardCatch({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    cuesFor("box-eight", ["box-eight", "catch-rest"]),
    cuesFor("box-seven", ["box-seven", "catch-next", "catch-rest"]),
    cuesFor("box-six", ["box-six", "catch-next", "catch-next", "catch-rest"])
  ],
  art: {
    backdrop: "__IMG:catch-pier__", sticker: "__IMG:lantern-badge__",
    frames: ["__IMG:catch-cart__"], icons: {fruit: "__IMG:tile-amber__"}
  },
  doneText: "两个篮子都装得刚刚好，灯片分好啦！",
  levels: [
    {baseCount: 8, capacity: [2, 3], batches: [[2, 1], [3, 2]],
      seconds: 3.4, catchRadius: 142, wind: 0, hints},
    {baseCount: 7, capacity: [3, 4], batches: [[1, 0], [2, 2], [4, 1]],
      seconds: 3.0, catchRadius: 119, wind: 36, hints},
    {baseCount: 6, capacity: [4, 5], batches: [[3, 2], [2, 0], [1, 1], [3, 0]],
      seconds: 2.55, catchRadius: 99, wind: 70, hints}
  ]
});

const drawGame = options.draw;
options.draw = (game, context) => {
  drawGame(game, context);
  if (!game.data.w) return;
  const {baseCount} = game.data.level;
  const added = game.data.w.fill[0];
  paintBox(context, 24, 267, 186, 91, 13, "#275541");
  paintBox(context, 28, 271, 178, 83, 10, "#f7e8c5");
  for (let i = 0; i < 10; i += 1) {
    const x = 48 + (i % 5) * 34;
    const y = 294 + Math.floor(i / 5) * 34;
    const filled = i < baseCount + added;
    paintBox(context, x - 15, y - 15, 30, 30, 5, i >= baseCount ? "#c8e6c9" : "#fff7df");
    if (filled) {
      if (artwork.complete && artwork.naturalWidth) context.drawImage(artwork, x - 12, y - 12, 24, 24);
      else paintBox(context, x - 10, y - 10, 20, 20, 5, "#b96225");
    }
  }
};

const cart = K.game(options);
cart.follow("#gap-proof", () => ({x: 24, y: 267, w: 186, h: 91}));
cart.follow("#catch-fill-basket", () => ({x: 44, y: 96, w: 310, h: 132}));
cart.follow("#catch-first-batch", (game) => {
  const world = game.data.w;
  const y = world?.index > 0 ? 491 : 259 + (world?.fall ?? 0) * 232;
  return {x: 585, y: y - 37, w: 110, h: 74};
});
