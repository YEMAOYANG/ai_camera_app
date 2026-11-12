const cue = (steps) => ({
  goal: steps[0], steps, hint: "swing-hint", hint2: "swing-help", praise: "swing-praise"
});
const hints = ["再看上方形状和落点。", "虚线朝向亮灯时松手。"];
const leg = (goal, x, y, a, otherX, otherY, b) => ({
  goal, targets: [{x, y, value: a}, {x: otherX, y: otherY, value: b}]
});
const levels = [
  {omega: 1.75, legs: [
    leg("circle-amber", 409, 244, "circle-amber", 409, 432, "triangle-left"),
    leg("triangle-lean", 678, 248, "circle-lilac", 678, 440, "triangle-lean")
  ], hints},
  {omega: 2.33, legs: [
    leg("square-turned", 385, 225, "square-turned", 406, 445, "rect-turned"),
    leg("slant-lilac", 642, 235, "slant-lilac", 642, 463, "square-lime"),
    leg("rect-coral", 914, 249, "slant-green", 906, 449, "rect-coral")
  ], hints},
  {omega: 2.95, legs: [
    leg("triangle-down", 371, 232, "square-turned", 372, 467, "triangle-down"),
    leg("circle-lilac", 604, 222, "circle-lilac", 623, 465, "triangle-left"),
    leg("slant-blue", 855, 239, "rect-turned", 839, 433, "slant-blue"),
    leg("square-lime", 1080, 225, "square-lime", 1103, 451, "slant-green")
  ], hints}
];

K.ready({title: "荡到同类的灯牌", sub: "比一比上面的轮廓，虚线指向同类灯牌时松手。"});

const options = K.gameTemplates.fireflySwing({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    cue(["swing-circle", "swing-triangle"]),
    cue(["swing-square", "swing-slant", "swing-rect"]),
    cue(["swing-triangle", "swing-circle", "swing-slant", "swing-square"])
  ],
  art: {
    backdrop: "__IMG:night-court__", sticker: "__IMG:stamp-badge__",
    frames: ["__IMG:firefly-rest__", "__IMG:firefly-wing__"],
    icons: {
      "circle-amber": "__IMG:circle-amber__", "circle-lilac": "__IMG:circle-lilac__",
      "triangle-left": "__IMG:triangle-left__", "triangle-lean": "__IMG:triangle-lean__",
      "triangle-down": "__IMG:triangle-down__", "square-turned": "__IMG:square-turned__",
      "square-lime": "__IMG:square-lime__", "rect-turned": "__IMG:rect-turned__",
      "rect-coral": "__IMG:rect-coral__", "slant-lilac": "__IMG:slant-lilac__",
      "slant-green": "__IMG:slant-green__", "slant-blue": "__IMG:slant-blue__"
    }
  },
  doneText: "图形转了方向，也都找到同类了！",
  levels
});

const refs = {
  circle: "__IMG:circle-ref__", triangle: "__IMG:triangle-ref__", square: "__IMG:square-ref__",
  rect: "__IMG:rect-ref__", slant: "__IMG:slant-ref__"
};
const symbols = Object.fromEntries(Object.entries(refs).map(([kind, path]) => {
  const image = new Image();
  image.src = path;
  return [kind, image];
}));
const draw = options.draw;
options.draw = (game, context) => {
  draw(game, context);
  const world = game.data.w;
  if (!world) return;
  const current = game.data.level.legs[world.i] || game.data.level.legs.at(-1);
  const kind = current.goal.split("-")[0];
  const image = symbols[kind];
  if (!image?.complete || !image.naturalWidth) return;
  context.fillStyle = "#eae9d5";
  K.draw.rr(context, 577, 93, 126, 62, 18);
  context.fill();
  const iconSize = kind === "circle" ? 88 : 64;
  context.drawImage(image, 640 - iconSize / 2, 124 - iconSize / 2, iconSize, iconSize);
};
options.bubbleAt = () => ({x: 605, y: 612});
const swing = K.game(options);
swing.follow("#swing-goal", () => ({x: 577, y: 93, w: 126, h: 62}));
swing.follow("#swing-first-lamp", () => ({x: 357, y: 192, w: 104, h: 104}));
