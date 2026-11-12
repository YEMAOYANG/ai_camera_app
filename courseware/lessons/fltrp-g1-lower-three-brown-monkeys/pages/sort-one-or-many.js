const hints = ["再数一次，是一只还是多只？", "看发亮的图架，从卡片后面推。"];
const makeCues = (steps) => ({goal: steps[0], steps, hint: "sort-hint", hint2: "sort-help", praise: "sort-praise"});

K.ready({title: "一只、多只，送对图架", sub: "用箭头从图卡后面推。看图架是一只的标记，还是多只的标记。"});

const levels = [
  {
    map: ["########","#......#","#S.....#","#......#","########"], step: .34, hints,
    items: [{x:2,y:2,token:"one-monkey",group:"one"},{x:5,y:3,token:"two-white-horses",group:"many"}],
    docks: [{x:3,y:2,sample:"marker-one",group:"one"},{x:2,y:3,sample:"marker-many",group:"many"}]
  },
  {
    map: ["#########","#.......#","#..#....#","#.S.....#","#.......#","#########"], step: .28, hints,
    items: [{x:4,y:2,token:"one-green-bird",group:"one"},
      {x:4,y:4,token:"three-green-birds",group:"many"},{x:3,y:3,token:"one-tiger",group:"one"}],
    docks: [{x:6,y:2,sample:"marker-one",group:"one"},{x:7,y:4,sample:"marker-many",group:"many"},
      {x:6,y:3,sample:"marker-one",group:"one"}]
  },
  {
    map: ["##########","#........#","#..#.....#","#.S......#","#....#...#","#........#","##########"], step: .23, hints,
    items: [{x:4,y:3,token:"one-elephant",group:"one"},{x:7,y:4,token:"three-elephants",group:"many"},
      {x:4,y:2,token:"three-tigers",group:"many"},{x:4,y:5,token:"one-yellow-bird",group:"one"}],
    docks: [{x:7,y:3,sample:"marker-one",group:"one"},{x:8,y:4,sample:"marker-many",group:"many"},
      {x:8,y:2,sample:"marker-many",group:"many"},{x:7,y:5,sample:"marker-one",group:"one"}]
  }
];

const options = K.gameTemplates.sortingDepot({
  voiceLead: true, stepVoiceLead: true,
  cues: [
    makeCues(["sort-start", "sort-next"]),
    makeCues(["sort-same-colour", "sort-next", "sort-next"]),
    makeCues(["sort-more-pictures", "sort-next", "sort-next", "sort-next"])
  ],
  art: {
    backdrop: "__IMG:printing-workshop__", sticker: "__IMG:monkey-badge__",
    frames: ["__IMG:print-cart__", "__IMG:print-cart__"],
    icons: {
      "marker-one": "__IMG:marker-one__", "marker-many": "__IMG:marker-many__",
      "one-monkey": "__IMG:one-monkey__", "two-white-horses": "__IMG:two-white-horses__",
      "one-green-bird": "__IMG:one-green-bird__", "three-green-birds": "__IMG:three-green-birds__",
      "one-tiger": "__IMG:one-tiger__", "one-elephant": "__IMG:one-elephant__",
      "three-elephants": "__IMG:three-elephants__", "three-tigers": "__IMG:three-tigers__",
      "one-yellow-bird": "__IMG:one-yellow-bird__"
    }
  },
  doneText: "一只和多只的图都分好了！",
  levels
});
options.bubbleAt = () => ({x: 640, y: 98});
options.onState = (_frame, state) => {
  if (state.demo === false) K.$$(".teach-hl").forEach((anchor) => anchor.classList.remove("teach-hl"));
};

const game = K.game(options);
function firstCell(frame, point) {
  const board = frame.data.w;
  if (!board || frame.level !== 0) return null;
  const half = board.s * .45;
  return {
    x: board.ox + (point.x + .5) * board.s - half,
    y: board.oy + (point.y + .5) * board.s - half,
    w: half * 2, h: half * 2
  };
}
game.follow("#first-picture-to-sort", (frame) => firstCell(frame,levels[0].items[0]));
game.follow("#first-sorting-slot", (frame) => firstCell(frame,levels[0].docks[0]));
