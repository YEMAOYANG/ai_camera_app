const levels = [
  {
    map: ['#########', '#S.A+..E#', '#.####.##', '#..C.B..#', '#.......#', '#########'],
    route: ['A', 'B', 'C'],
    start: 10, step: 0.29, listenOnly: true,
    labels: {A: '13−2', B: '10+2', C: '16−3'},
    hints: ['算一算，哪块站牌的得数比左边多一？', '先看十位，再算散开的几个一。'],
  },
  {
    map: ['###########', '#S.D+....E#', '#.#.###.#.#', '#.N..F..G.#', '#.#.###.#.#', '#.........#', '###########'],
    route: ['D', 'N', 'F', 'G'],
    start: 11, step: 0.23, listenOnly: true,
    labels: {D: '14−2', N: '10+3', F: '16−2', G: '17−2'},
    hints: ['先算得数，再找多一的那站。', '遇到橙色障碍，面朝它喷泡泡。'],
  },
  {
    map: ['#############', '#S..H+.....E#', '#.##.#####.##', '#..I..J..K..#', '###.##.##.#.#', '#......M....#', '#############'],
    route: ['H', 'I', 'J', 'K', 'M'],
    start: 15, step: 0.17, listenOnly: true,
    labels: {H: '10+6', I: '19−2', J: '16+2', K: '15+4', M: '10+10'},
    patrols: [{y:1,from:6,to:10,speed:1.3}],
    hints: ['两个站的得数很近，哪一个只多一？', '可以停一停，让巡游的小车先过去。'],
  },
];

const cues = ['route-goal-a','route-goal-b','route-goal-c'].map(goal => ({
  goal, hint: 'route-hint', hint2: 'route-help', praise: 'route-praise',
}));

const config = {
  title: '得数巡游路线',
  sub: '每站的得数多一。把路线接好，再开到小旗。',
  doneText: '路线接好了，每次多一。',
  voiceLead: true,
  levels,
  cues,
  art: {
    backdrop: '__IMG:route-room__',
    sticker: '__IMG:exhibit-flag__',
    frames: ['__IMG:rover-idle__', '__IMG:rover-moving__'],
    icons: {
      A: '__IMG:route-a__', B: '__IMG:route-b__', C: '__IMG:route-c__',
      D: '__IMG:route-d__', N: '__IMG:route-e__', F: '__IMG:route-f__', G: '__IMG:route-g__',
      H: '__IMG:route-h__', I: '__IMG:route-i__', J: '__IMG:route-j__',
      K: '__IMG:route-k__', M: '__IMG:route-m__',
    },
  },
};

K.ready({title: config.title, sub: config.sub});
const arcade = K.gameTemplates.bubbleMaze(config);
const current = K.$('#route-current');
K.stage().appendChild(current);
const currentNumber = K.$('#route-number');
const drawArcade = arcade.draw;
arcade.draw = (g, canvas) => {
  drawArcade(g, canvas);
  const level = g.data.level;
  current.hidden = !level || g.state === 'ready' || g.state === 'done';
  if (!current.hidden) {
    const result = String(level.start + Math.min(g.data.progress, level.route.length));
    if (currentNumber.textContent !== result) currentNumber.textContent = result;
  }
};
K.game(arcade);
