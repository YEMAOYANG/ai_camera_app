const tileCues = {goal: "tile-goal", hint: "tile-hint", hint2: "tile-help", praise: "tile-praise"};

K.ready({
  title: "余量配对工坊",
  sub: "算出底卡还剩几，让相同余量的落块在旁边停下。"
});

const workbench = K.game(K.gameTemplates.fallingTiles({
  voiceLead: true,
  cues: [tileCues, tileCues, tileCues],
  art: {
    backdrop: "__IMG:tile-workbench__",
    sticker: "__IMG:festival-sticker__",
    icons: {
      "take-14-04": "__IMG:take-14-04__", "take-16-06": "__IMG:take-16-06__",
      "take-12-10": "__IMG:take-12-10__", "take-17-07": "__IMG:take-17-07__",
      "take-16-10": "__IMG:take-16-10__", "take-15-03": "__IMG:take-15-03__",
      "take-19-10": "__IMG:take-19-10__", "take-14-01": "__IMG:take-14-01__",
      "take-17-02": "__IMG:take-17-02__", "rem-02": "__IMG:rem-02__",
      "rem-06": "__IMG:rem-06__", "rem-09": "__IMG:rem-09__",
      "rem-10": "__IMG:rem-10__", "rem-12": "__IMG:rem-12__",
      "rem-13": "__IMG:rem-13__", "rem-15": "__IMG:rem-15__"
    }
  },
  doneText: "每张落块都找到了正确的余量！",
  levels: [
    {
      bottom: [null, "take-14-04", null, "take-16-06", null, "take-12-10"],
      pieces: ["rem-10", "rem-10"],
      pairs: [["rem-10", "take-14-04"], ["rem-10", "take-16-06"]],
      interval: 1.48,
      hints: ["先看原数，再看拿走了几个。", "要落在同一行，紧挨着那张卡。"]
    },
    {
      bottom: [null, "take-12-10", null, "take-17-07", null, "take-16-10"],
      pieces: ["rem-02", "rem-10", "rem-06"],
      pairs: [["rem-02", "take-12-10"], ["rem-10", "take-17-07"], ["rem-06", "take-16-10"]],
      interval: 1.04,
      hints: ["这次去掉的是一盒还是散件？", "看浅浅的影子，把落块放到隔壁。"]
    },
    {
      bottom: ["take-15-03", null, "take-19-10", "take-14-01", null, "take-17-02"],
      pieces: ["rem-12", "rem-09", "rem-13", "rem-15"],
      pairs: [["rem-12", "take-15-03"], ["rem-09", "take-19-10"],
              ["rem-13", "take-14-01"], ["rem-15", "take-17-02"]],
      interval: 0.72,
      hints: ["散件拿走一部分，整盒还在吗？", "先算余量，再看这一格能不能落到底。"]
    }
  ]
}));

workbench.follow("#tile-demo-first-card", () => ({x: 500, y: 526, w: 70, h: 70}));
