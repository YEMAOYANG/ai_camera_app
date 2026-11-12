const roll = "can-roll";
const hold = "supported";
const cues = {goal: "depot-goal", hint: "depot-hint", hint2: "depot-help", praise: "depot-praise"};

K.ready({
  title: "小球支架分拣",
  sub: "看小球还有没有路滚，把摆法图推到合适的托盘。"
});

const depotConfig = {
  art: {
    backdrop: "__IMG:hop-workbench__",
    sticker: "__IMG:hop-sticker__",
    frames: ["__IMG:hop-rabbit-ready__", "__IMG:hop-rabbit-run__"],
    icons: {
      "depot-flat": "__IMG:depot-flat__",
      "depot-rails": "__IMG:depot-rails__",
      "depot-row": "__IMG:depot-row__",
      "depot-cradle": "__IMG:depot-cradle__",
      "depot-cradle-turn": "__IMG:depot-cradle-turn__",
      "depot-roll-mark": "__IMG:depot-roll-mark__",
      "depot-hold-mark": "__IMG:depot-hold-mark__"
    }
  },
  doneText: "你分清了会滚出的摆法和能托球的摆法！",
  voiceLead: true,
  cues: [cues, cues, cues],
  levels: [
    {
      map: ["########", "#......#", "#.S....#", "#......#", "########"],
      step: 0.33,
      items: [
        {x: 3, y: 2, token: "depot-rails", group: roll},
        {x: 2, y: 3, token: "depot-cradle", group: hold}
      ],
      docks: [
        {x: 5, y: 2, sample: "depot-roll-mark", group: roll},
        {x: 5, y: 3, sample: "depot-hold-mark", group: hold}
      ],
      hints: ["顺着球的前后和两边找空路。", "看看长条有没有分开托住球。"]
    },
    {
      map: ["#########", "#.......#", "#..#....#", "#.S.....#", "#.......#", "#########"],
      step: 0.25,
      items: [
        {x: 4, y: 2, token: "depot-cradle-turn", group: hold},
        {x: 4, y: 4, token: "depot-flat", group: roll},
        {x: 3, y: 3, token: "depot-rails", group: roll}
      ],
      docks: [
        {x: 6, y: 2, sample: "depot-hold-mark", group: hold},
        {x: 7, y: 4, sample: "depot-roll-mark", group: roll},
        {x: 6, y: 3, sample: "depot-roll-mark", group: roll}
      ],
      hints: ["球在平板上，往外看还有路吗？", "小兔可以绕过墙，再从卡片背后推。"]
    },
    {
      map: ["##########", "#........#", "#..#.....#", "#.S......#", "#....#...#", "#........#", "##########"],
      step: 0.20,
      items: [
        {x: 4, y: 3, token: "depot-cradle", group: hold},
        {x: 7, y: 4, token: "depot-cradle-turn", group: hold},
        {x: 4, y: 2, token: "depot-rails", group: roll},
        {x: 4, y: 5, token: "depot-row", group: roll}
      ],
      docks: [
        {x: 7, y: 3, sample: "depot-hold-mark", group: hold},
        {x: 8, y: 4, sample: "depot-hold-mark", group: hold},
        {x: 8, y: 2, sample: "depot-roll-mark", group: roll},
        {x: 7, y: 5, sample: "depot-roll-mark", group: roll}
      ],
      hints: ["三个长条排成一线，也要找两旁的空路。", "先给别的卡片留路，再从背后推。"]
    }
  ]
};

const depot = K.game(K.gameTemplates.sortingDepot(depotConfig));
depot.follow("#depot-demo-dock", () => {
  const board = depot.data.w;
  if (!board || depot.level !== 0) return null;
  const [dock] = depotConfig.levels[0].docks;
  const side = board.s * .9;
  return {
    x: board.ox + (dock.x + .5) * board.s - side / 2,
    y: board.oy + (dock.y + .5) * board.s - side / 2,
    w: side,
    h: side
  };
});
