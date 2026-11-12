const gallery = {
  A: "__IMG:rabbits-little__", B: "__IMG:giraffes-tall__", D: "__IMG:pandas-little__",
  F: "__IMG:elephants-big__", G: "__IMG:horses-little__", H: "__IMG:snakes-long__",
  I: "__IMG:rabbits-little__", J: "__IMG:elephants-big__"
};
const pictures = Object.fromEntries(Object.entries(gallery).map(([key, url]) => {
  const image = new Image();
  image.src = url;
  return [key, image];
}));
const hints = ["再听一遍。", "看亮图，开车。"];
const makeCues = (goals) => ({
  goal: goals[0], steps: [...goals, "maze-exit"], hint: "maze-hint", hint2: "maze-help", praise: "maze-praise"
});

K.ready({title: "听问答，开车去展位", sub: "先听，再开车到对应图标。图标找齐才去小旗。"});

const options = K.gameTemplates.bubbleMaze({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    makeCues(["maze-not-big", "maze-yes-tall"]),
    makeCues(["maze-not-horses", "maze-yes-elephants", "maze-not-pandas"]),
    makeCues(["maze-long-ears", "maze-yes-long", "maze-yes-big"])
  ],
  art: {
    backdrop: "__IMG:exhibit-map__", sticker: "__IMG:exhibit-sticker__",
    frames: ["__IMG:exhibit-car__", "__IMG:exhibit-car-action__"], icons: gallery
  },
  doneText: "听清问答，玩具展位都到了！",
  levels: [
    {map: ["#######", "#S.A.E#", "#..B..#", "#######"],
      route: ["A", "B"], cards: ["B", "A"], listenOnly: true, step: .36, hints},
    {map: ["#########", "#S.D..E.#", "#.#.+.#.#", "#.F...G.#", "#########"],
      route: ["D", "F", "G"], cards: ["G", "D", "F"], listenOnly: true, step: .29, hints},
    {map: ["#########", "#S..+I.E#", "#.#.#.#.#", "#.H...J.#", "#.......#", "#########"],
      route: ["I", "H", "J"], cards: ["J", "H", "I"], listenOnly: true, step: .24,
      patrols: [{y: 4, from: 2, to: 6, speed: .87}], hints}
  ]
});

const paint = (context, x, y, width, height, radius, fill) => {
  context.fillStyle = fill;
  K.draw.rr(context, x, y, width, height, radius);
  context.fill();
};
const cardTop = (index) => 122 + index * 144;

function fallback(context, id, x, y, width, height) {
  const color = {A:"#b29079", B:"#dd9b4b", D:"#48413d", F:"#6b8c9a", G:"#b37249", H:"#b68437", I:"#b29079", J:"#6b8c9a"}[id];
  for (const dx of [-width * .22, width * .22]) {
    const center = x + dx;
    const head = id === "B" ? y - height * .28 : y - height * .04;
    const body = id === "F" || id === "J" ? height * .39 : height * .24;
    paint(context, center - body / 2, y + height * .25 - body, body, body, 5, color);
    context.fillStyle = color;
    K.draw.circle(context, center, head, Math.max(4, height * .095));
    if (id === "A" || id === "I") {
      paint(context, center - height * .085, head - height * .22, height * .06, height * .21, 3, color);
      paint(context, center + height * .018, head - height * .22, height * .06, height * .21, 3, color);
    }
    if (id === "B") paint(context, center - height * .05, head, height * .10, height * .31, 3, color);
    if (id === "H") paint(context, center - width * .17, y + height * .11, width * .35, height * .1, 4, color);
  }
}

const draw = options.draw;
options.draw = (frame, context) => {
  draw(frame, context);
  const {w: world, level} = frame.data;
  if (!world) return;
  level.cards.forEach((id, index) => {
    const top = cardTop(index);
    const complete = level.route.indexOf(id) < world.i;
    paint(context, 25, top, 223, 128, 18, complete ? "#d4dfcb" : "#477568");
    paint(context, 31, top + 6, 211, 116, 13, "#f9ecd1");
    const image = pictures[id];
    if (image.naturalWidth) context.drawImage(image, 43, top + 9, 188, 108);
    else fallback(context, id, 137, top + 64, 188, 108);
    if (complete) {
      context.fillStyle = "#3a6854";
      K.draw.circle(context, 228, top + 17, 13);
      context.strokeStyle = "#fff1c7";
      context.lineWidth = 4;
      context.beginPath();
      context.moveTo(222, top + 17);
      context.lineTo(227, top + 22);
      context.lineTo(234, top + 12);
      context.stroke();
    }
  });
  for (let row = 0; row < world.map.length; row += 1) {
    for (let col = 0; col < world.map[row].length; col += 1) {
      const id = world.map[row][col];
      if (!(id in pictures) || (world.x === col && world.y === row)) continue;
      const x = world.ox + (col + .5) * 67;
      const y = world.oy + (row + .5) * 67;
      const selected = world.help && id === level.route[world.i];
      paint(context, x - 31, y - 27, 62, 54, 10, selected ? "#ffcc60" : "#f8e1ad");
      const image = pictures[id];
      if (image.naturalWidth) context.drawImage(image, x - 29, y - 19, 58, 38);
      else fallback(context, id, x, y, 54, 38);
    }
  }
};
options.bubbleAt = () => ({x: 1098, y: 480});
options.onState = (_frame, state) => {
  if (state.demo === false) K.$$(".teach-hl").forEach((element) => element.classList.remove("teach-hl"));
};

const game = K.game(options);
game.follow("#maze-sound", () => ({x: 605, y: 18, w: 70, h: 58}));
game.follow("#maze-first-tile", () => ({x: 606.5, y: 280.5, w: 67, h: 67}));
game.follow("#maze-first-card", () => ({x: 25, y: cardTop(1), w: 223, h: 128}));
