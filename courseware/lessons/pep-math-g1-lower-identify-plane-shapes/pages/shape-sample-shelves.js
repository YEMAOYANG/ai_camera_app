const cue = (steps) => ({
  goal: steps[0], steps, hint: "sort-hint", hint2: "sort-help", praise: "sort-praise"
});
const hints = ["转一转，看边和角。", "绕到卡片背后再推。"];

K.ready({title: "给形状卡找托盘", sub: "用箭头从后面推卡，送到同类样例。回转键可以撤回。"});

const levels = [
  {
    map: ["########", "#......#", "#S.....#", "#......#", "########"],
    step: 0.34,
    items: [
      {x: 2, y: 2, token: "circle-amber", group: "circle"},
      {x: 5, y: 3, token: "triangle-left", group: "triangle"}
    ],
    docks: [
      {x: 3, y: 2, sample: "circle-ref", group: "circle"},
      {x: 2, y: 3, sample: "triangle-ref", group: "triangle"}
    ], hints
  },
  {
    map: ["#########", "#.......#", "#..#....#", "#.S.....#", "#.......#", "#########"],
    step: 0.26,
    items: [
      {x: 4, y: 2, token: "slant-lilac", group: "slant"},
      {x: 4, y: 4, token: "rect-turned", group: "rect"},
      {x: 3, y: 3, token: "square-turned", group: "square"}
    ],
    docks: [
      {x: 6, y: 2, sample: "slant-ref", group: "slant"},
      {x: 7, y: 4, sample: "rect-ref", group: "rect"},
      {x: 6, y: 3, sample: "square-ref", group: "square"}
    ], hints
  },
  {
    map: ["##########", "#........#", "#..#.....#", "#.S......#", "#....#...#", "#........#", "##########"],
    step: 0.21,
    items: [
      {x: 4, y: 3, token: "rect-coral", group: "rect"},
      {x: 7, y: 4, token: "square-lime", group: "square"},
      {x: 4, y: 2, token: "circle-lilac", group: "circle"},
      {x: 4, y: 5, token: "triangle-down", group: "triangle"}
    ],
    docks: [
      {x: 7, y: 3, sample: "rect-ref", group: "rect"},
      {x: 8, y: 4, sample: "square-ref", group: "square"},
      {x: 8, y: 2, sample: "circle-ref", group: "circle"},
      {x: 7, y: 5, sample: "triangle-ref", group: "triangle"}
    ], hints
  }
];

const options = K.gameTemplates.sortingDepot({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    cue(["sort-round-one", "sort-next"]),
    cue(["sort-round-two", "sort-next", "sort-next"]),
    cue(["sort-round-three", "sort-next", "sort-next", "sort-next"])
  ],
  art: {
    backdrop: "__IMG:sorting-floor__", sticker: "__IMG:stamp-badge__",
    frames: ["__IMG:rabbit-idle__", "__IMG:rabbit-push__"],
    icons: {
      "circle-ref": "__IMG:circle-ref__", "triangle-ref": "__IMG:triangle-ref__",
      "square-ref": "__IMG:square-ref__", "rect-ref": "__IMG:rect-ref__", "slant-ref": "__IMG:slant-ref__",
      "circle-amber": "__IMG:circle-amber__", "triangle-left": "__IMG:triangle-left__",
      "slant-lilac": "__IMG:slant-lilac__", "rect-turned": "__IMG:rect-turned__",
      "square-turned": "__IMG:square-turned__", "rect-coral": "__IMG:rect-coral__",
      "square-lime": "__IMG:square-lime__", "circle-lilac": "__IMG:circle-lilac__",
      "triangle-down": "__IMG:triangle-down__"
    }
  },
  doneText: "看边和角，把同类样片送到一起了！",
  levels
});
options.bubbleAt = () => ({x: 456, y: 613});
const depot = K.game(options);
function firstCell(game, point) {
  const board = game.data.w;
  if (!board || game.level !== 0) return null;
  const half = board.s * .45;
  return {x: board.ox + (point.x + .5) * board.s - half,
          y: board.oy + (point.y + .5) * board.s - half,
          w: half * 2, h: half * 2};
}
depot.follow("#sample-first-tile", game => firstCell(game, levels[0].items[0]));
depot.follow("#sample-first-dock", game => firstCell(game, levels[0].docks[0]));
