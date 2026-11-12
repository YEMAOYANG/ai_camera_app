const cuesFor = (steps) => ({
  goal: steps[0], steps, hint: "colour-hint", hint2: "colour-help", praise: "colour-praise"
});
const firstDrift = 9, firstPace = 0.52;
const hints = ["再听颜色和动物。", "把船移到发亮的图卡下。"];

K.ready({title: "听颜色和动物", sub: "听两条线索，挪到图卡下面，再吹泡泡。"});

const boat = K.game(K.gameTemplates.wordBubbles({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    cuesFor(["point-blue-dog", "point-green-cat"]),
    cuesFor(["find-blue-bird", "find-yellow-bird", "find-green-dog"]),
    cuesFor(["find-red-cat", "look-blue-dog", "look-green-cat", "look-yellow-bird"])
  ],
  art: {
    backdrop: "__IMG:bubble-pond__", frames: ["__IMG:toy-boat__", "__IMG:toy-boat__"],
    sticker: "__IMG:badge-sun__",
    icons: {
      "red-cat": "__IMG:red-cat__", "green-cat": "__IMG:green-cat__", "green-dog": "__IMG:green-dog__",
      "blue-dog": "__IMG:blue-dog__", "blue-bird": "__IMG:blue-bird__", "yellow-bird": "__IMG:yellow-bird__"
    }
  },
  doneText: "颜色和动物都听对了！",
  levels: [
    {
      rounds: [
        {target: "blue-dog", cards: ["blue-dog", "blue-bird"]},
        {target: "green-cat", cards: ["green-dog", "green-cat"]}
      ], drift: firstDrift, pace: firstPace, tolerance: 62, hints
    },
    {
      rounds: [
        {target: "blue-bird", cards: ["blue-dog", "yellow-bird", "blue-bird"]},
        {target: "yellow-bird", cards: ["yellow-bird", "blue-bird", "green-cat"]},
        {target: "green-dog", cards: ["blue-dog", "green-dog", "green-cat"]}
      ], drift: 20, pace: 0.77, tolerance: 57, hints
    },
    {
      rounds: [
        {target: "red-cat", cards: ["green-cat", "red-cat", "green-dog"]},
        {target: "blue-dog", cards: ["blue-bird", "green-dog", "blue-dog"]},
        {target: "green-cat", cards: ["green-cat", "red-cat", "green-dog"]},
        {target: "yellow-bird", cards: ["blue-dog", "yellow-bird", "blue-bird"]}
      ], drift: 32, pace: 1.02, tolerance: 52, hints
    }
  ]
}));

boat.follow("#first-colour-card", (game) => {
  const time = game.data.w?.t ?? 0;
  const x = 485 + Math.sin(time * firstPace) * firstDrift;
  return {x: x - 56, y: 191, w: 112, h: 118};
});
