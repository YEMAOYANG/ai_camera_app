const cardKinds = {
  "cow-group": ["cow", 3], "cow-one": ["cow", 1],
  "pig-group": ["pig", 3], "duck-group": ["duck", 3], "duck-one": ["duck", 1],
  "hen-group": ["hen", 3], "dog-group": ["dog", 3],
  "cat-group": ["cat", 3], "bird-group": ["bird", 3]
};
const icons = {
  "cow-group": "__IMG:cow-group__", "cow-one": "__IMG:cow-one__",
  "pig-group": "__IMG:pig-group__", "duck-group": "__IMG:duck-group__",
  "duck-one": "__IMG:duck-one__", "hen-group": "__IMG:hen-group__",
  "dog-group": "__IMG:dog-group__",
  "cat-group": "__IMG:cat-group__", "bird-group": "__IMG:bird-group__"
};
const artStatus = Object.fromEntries(Object.entries(icons).map(([key, url]) => {
  const image = new Image();
  image.src = url;
  return [key, image];
}));
const hints = ["再听一遍，留心是一只还是一群。", "看闪亮的图，再把弹珠送过去。"];
const cueBook = (steps) => ({
  goal: steps[0], steps, hint: "marble-hint", hint2: "marble-help", praise: "marble-praise"
});
const level = (cards, x, queue, speed, drift, targetWidth) => ({
  targets: cards.map((value, index) => ({x: x[index], value})),
  queue, pairs: queue.map((cue) => [cue, cue]),
  speed, drift, targetWidth, targetHeight: 122, listenOnly: true, hints
});

K.ready({title: "听线索，送弹珠", sub: "点喇叭听。用左右箭头瞄准，再发射。"});

const options = K.gameTemplates.magnetMarbles({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    cueBook(["hear-cows", "hear-one-cow"]),
    cueBook(["hear-one-duck", "hear-ducks", "hear-chickens"]),
    cueBook(["hear-dog-call", "hear-cats", "hear-birds"])
  ],
  art: {
    backdrop: "__IMG:farm-pond__", sticker: "__IMG:farm-badge__",
    frames: ["__IMG:marble__"], icons
  },
  doneText: "听清一只和一群，农场图卡都找对啦！",
  levels: [
    level(["pig-group", "cow-group", "cow-one"], [415, 640, 865],
      ["cow-group", "cow-one"], 365, 0, 196),
    level(["duck-one", "duck-group", "hen-group"], [415, 640, 865],
      ["duck-one", "duck-group", "hen-group"], 440, 15, 183),
    level(["dog-group", "cat-group", "bird-group", "hen-group"], [340, 540, 740, 940],
      ["dog-group", "cat-group", "bird-group"], 510, 28, 147)
  ]
});
options.bubbleAt = () => ({x: 645, y: 382});
options.onState = (_game, state) => {
  if (state.demo === false) K.$$(".teach-hl").forEach((anchor) => anchor.classList.remove("teach-hl"));
};

function oval(context, x, y, rx, ry, color) {
  context.fillStyle = color;
  context.beginPath();
  context.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2);
  context.fill();
}

function fallbackAnimal(context, species, x, y, scale) {
  context.save();
  context.translate(x, y);
  context.scale(scale, scale);
  if (["duck", "hen", "bird"].includes(species)) {
    const body = {duck: "#fbf0c9", hen: "#d6753b", bird: "#547b8c"}[species];
    oval(context, -3, 5, 19, 13, body);
    oval(context, 10, -10, 11, 11, body);
    oval(context, 20, -7, species === "duck" ? 11 : 6, 4, "#d38328");
    if (species === "hen") {
      for (const dx of [4, 10, 16]) oval(context, dx, -22, 4, 6, "#a8493e");
    }
    oval(context, 13, -12, 2, 2, "#382c29");
  } else {
    const fur = {cow: "#f9f1dc", pig: "#e99b94", dog: "#b07a50", cat: "#d48548"}[species];
    const ear = species === "dog" ? "#7d4a33" : fur;
    oval(context, -12, -13, 7, species === "dog" ? 15 : 8, ear);
    oval(context, 12, -13, 7, species === "dog" ? 15 : 8, ear);
    if (species === "cow") {
      oval(context, -8, -21, 3, 8, "#69452c");
      oval(context, 8, -21, 3, 8, "#69452c");
    }
    if (species === "cat") {
      context.fillStyle = fur;
      context.beginPath();
      context.moveTo(-20, -9);
      context.lineTo(-17, -24);
      context.lineTo(-7, -14);
      context.lineTo(8, -14);
      context.lineTo(17, -24);
      context.lineTo(20, -9);
      context.closePath();
      context.fill();
    }
    oval(context, 0, 1, 18, 16, fur);
    oval(context, -7, -2, 2, 2, "#382c29");
    oval(context, 7, -2, 2, 2, "#382c29");
    oval(context, 0, 9, species === "pig" ? 10 : 7, 5,
      species === "cow" || species === "pig" ? "#ca786b" : "#382c29");
  }
  context.restore();
}

const draw = options.draw;
options.draw = (game, context) => {
  draw(game, context);
  const world = game.data.w;
  if (!world) return;
  for (const target of world.targets) {
    const image = artStatus[target.value];
    if (target.used || image.naturalWidth) continue;
    const [species, count] = cardKinds[target.value];
    const x = target.x + Math.sin(world.time * 2.4 + target.x * .019) * game.data.level.drift;
    const spacing = game.data.level.targetWidth / 3.45;
    for (let i = 0; i < count; i += 1) {
      fallbackAnimal(context, species, x + (i - (count - 1) / 2) * spacing, 229, count === 1 ? 1.35 : .79);
    }
  }
};

const game = K.game(options);
game.follow("#farm-speaker", () => ({x: 580, y: 98, w: 120, h: 58}));
game.follow("#first-cow-group", () => ({x: 542, y: 168, w: 196, h: 122}));
