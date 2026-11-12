const hints = ["看篮子还空几格。这一盘蛋一起接。", "把车移到亮线，空格不够就换篮。"];
const cueBook = (goal) => ({goal, hint: "egg-hint", hint2: "egg-help", praise: "egg-praise"});

K.ready({title: "接住鸡蛋，把篮子装满", sub: "左右移小车。看空格，用双箭头换篮。"});

const options = K.gameTemplates.orchardCatch({
  voiceLead: true,
  cues: [cueBook("hear-ten"), cueBook("hear-eleven"), cueBook("hear-twelve")],
  art: {
    backdrop: "__IMG:farm-shed__", sticker: "__IMG:farm-badge__",
    frames: ["__IMG:egg-cart__"], icons: {fruit: "__IMG:egg__"}
  },
  doneText: "两篮正好装满，最后一关有十二枚蛋！",
  levels: [
    {capacity: [5, 5], batches: [[4, 1], [4, 2], [1, 0], [1, 1]],
      seconds: 3.9, catchRadius: 144, wind: 0, hints},
    {capacity: [5, 6], batches: [[3, 1], [4, 0], [2, 2], [1, 1], [1, 2]],
      seconds: 3.4, catchRadius: 123, wind: 36, hints},
    {capacity: [6, 6], batches: [[4, 2], [3, 0], [2, 1], [2, 2], [1, 0]],
      seconds: 2.8, catchRadius: 102, wind: 76, hints}
  ]
});
options.bubbleAt = () => ({x: 600, y: 413});
options.onState = (_game, state) => {
  if (state.demo === false) K.$$(".teach-hl").forEach((anchor) => anchor.classList.remove("teach-hl"));
};

const draw = options.draw;
options.draw = (game, context) => {
  draw(game, context);
  if (!game.data.w) return;
  const total = game.data.w.fill[0] + game.data.w.fill[1];
  const goal = game.data.level.capacity[0] + game.data.level.capacity[1];
  context.fillStyle = "#285c51";
  K.draw.rr(context, 38, 285, 157, 83, 18);
  context.fill();
  context.fillStyle = "#fff0c7";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.font = "bold 36px sans-serif";
  context.fillText(total + " / " + goal, 116, 328);
};

const game = K.game(options);
game.follow("#egg-baskets", () => ({x: 44, y: 96, w: 310, h: 132}));
game.follow("#egg-total", () => ({x: 38, y: 285, w: 157, h: 83}));
game.follow("#first-egg-batch", (frame) => {
  const world = frame.data.w;
  const y = world?.index > 0 ? 491 : 259 + (world?.fall ?? 0) * 232;
  return {x: 585, y: y - 37, w: 110, h: 74};
});
