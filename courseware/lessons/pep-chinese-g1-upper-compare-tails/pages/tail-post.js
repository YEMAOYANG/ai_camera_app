const instruction = (steps) => ({
  goal: steps[0], steps, hint: "photo-hint", hint2: "photo-help", praise: "photo-praise"
});

K.ready({title: "尾巴照片邮车", sub: "听清尾巴的样子，取全身照，送到合适的局部窗。"});

const vanConfig = K.gameTemplates.listenDelivery({
  voiceLead: true,
  stepVoiceLead: true,
  cues: [
    instruction(["get-rabbit", "send-rabbit"]),
    instruction(["get-monkey", "send-monkey", "get-squirrel", "send-squirrel"]),
    instruction(["get-rooster", "send-rooster", "get-duck", "send-duck", "get-peacock", "send-peacock"])
  ],
  art: {
    backdrop: "__IMG:courtyard__", sticker: "__IMG:photo-badge__",
    frames: ["__IMG:van__", "__IMG:van__", "__IMG:van__"],
    icons: {
      monkey: "__IMG:monkey__", rabbit: "__IMG:rabbit__", squirrel: "__IMG:squirrel__",
      rooster: "__IMG:rooster__", duck: "__IMG:duck__", peacock: "__IMG:peacock__",
      "tail-monkey": "__IMG:tail-monkey__", "tail-rabbit": "__IMG:tail-rabbit__",
      "tail-squirrel": "__IMG:tail-squirrel__", "tail-rooster": "__IMG:tail-rooster__",
      "tail-duck": "__IMG:tail-duck__", "tail-peacock": "__IMG:tail-peacock__"
    }
  },
  doneText: "每张全身照都送到了相配的尾巴窗！",
  levels: [
    {
      pickup: [["rabbit", 4], ["monkey", 6]],
      drop: [["tail-monkey", 4], ["tail-rabbit", 6]],
      orders: [["rabbit", "tail-rabbit"]],
      lanes: [{row: 2, speed: 0.82, spacing: 5.8, phase: 1.4}],
      step: 0.34,
      hints: ["重听这一步，注意说的是尾巴哪一点。", "看看发亮的地方，等车过去再走。"]
    },
    {
      pickup: [["squirrel", 2], ["monkey", 5], ["rabbit", 8]],
      drop: [["tail-monkey", 1], ["tail-rabbit", 4], ["tail-squirrel", 7]],
      orders: [["monkey", "tail-monkey"], ["squirrel", "tail-squirrel"]],
      lanes: [{row: 1, speed: -1.13, spacing: 4.8, phase: 2.1},
              {row: 3, speed: 1.25, spacing: 5.0, phase: 1.1}],
      step: 0.27,
      hints: ["重听这一步，注意说的是尾巴哪一点。", "看看发亮的地方，等车过去再走。"]
    },
    {
      pickup: [["rooster", 1], ["peacock", 4], ["duck", 7]],
      drop: [["tail-duck", 2], ["tail-rooster", 5], ["tail-peacock", 8]],
      orders: [["rooster", "tail-rooster"], ["duck", "tail-duck"], ["peacock", "tail-peacock"]],
      lanes: [{row: 1, speed: -1.7, spacing: 4.3, phase: 0.9},
              {row: 2, speed: 1.54, spacing: 4.5, phase: 2.2},
              {row: 3, speed: -1.54, spacing: 4.3, phase: 1.5}],
      step: 0.23,
      hints: ["重听这一步，注意说的是尾巴哪一点。", "看看发亮的地方，等车过去再走。"]
    }
  ]
});

vanConfig.onState = (_game, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl').forEach(element => element.classList.remove('teach-hl'));
  }
};
const van = K.game(vanConfig);

van.follow("#tail-first-photo", () => ({x: 602, y: 497, w: 76, h: 78}));
van.follow("#tail-photo-windows", () => ({x: 590, y: 151, w: 276, h: 78}));
