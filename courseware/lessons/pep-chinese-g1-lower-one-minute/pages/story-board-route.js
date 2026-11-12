const config = {
  title: '泡泡车排故事图',
  sub: '听下一幕的线索，按先后接图，再去小旗。',
  doneText: '元元的故事排好了。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:route-backdrop__',
    sticker: '__IMG:minute-sticker__',
    frames: ['__IMG:route-rover__', '__IMG:route-rover-pop__'],
    icons: {
      A: '__IMG:route-alarm-icon__', B: '__IMG:route-rise-icon__', C: '__IMG:route-bag-icon__',
      D: '__IMG:route-curb-icon__', G: '__IMG:route-cross-icon__', F: '__IMG:route-bus-icon__',
      H: '__IMG:route-wait-icon__', I: '__IMG:route-walk-icon__', J: '__IMG:route-class-icon__'
    }
  },
  levels: [
    {
      map: ['#########', '#S..A..E#', '#..#.#..#', '#B..C...#', '#########'],
      route: ['A', 'B', 'C'], step: .32,
      hints: ['先想故事是从哪儿开始的。', '去亮起来的那一幕。']
    },
    {
      map: ['##########', '#S..F...E#', '#..##+...#', '#G.....D.#', '#........#', '##########'],
      route: ['D', 'G', 'F'], step: .28, patrols: [{y: 4, from: 2, to: 6, speed: 1.06}],
      hints: ['先想等灯和到车站哪个早。', '接亮起来的画，再听下一幕。']
    },
    {
      map: ['###########', '#S..H+...E#', '#.#.###.#.#', '#F.......J#', '#...I.....#', '###########'],
      route: ['F', 'H', 'I', 'J'], step: .25, patrols: [{y: 3, from: 2, to: 7, speed: 1.3}],
      hints: ['想想错过公交以后元元做了什么。', '看亮图。碰到软挡板可以吹泡泡。']
    }
  ].map(level => ({...level, listenOnly: true})),
  cues: [
    ['route-alarm', 'route-rise', 'route-bag', 'route-exit'],
    ['route-curb', 'route-cross', 'route-miss-bus', 'route-exit'],
    ['route-miss-bus', 'route-wait-bus', 'route-walk', 'route-class', 'route-exit']
  ].map(steps => ({steps, goal: steps[0], hint: 'route-hint', hint2: 'route-help', praise: 'route-praise'}))
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#minute-route-listen'), K.$('#minute-first-alarm'));
const activity = K.gameTemplates.bubbleMaze(config);
activity.onState = (_, state) => {
  if (state.demo === false) K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
};
K.game(activity);
