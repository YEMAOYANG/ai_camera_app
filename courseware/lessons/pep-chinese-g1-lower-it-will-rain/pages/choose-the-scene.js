const config = {
  title: '泡泡车串起故事',
  sub: '听下一幕的线索，按先后接图，最后开到小旗。',
  doneText: '故事的画面接起来啦。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:maze-backdrop__',
    sticker: '__IMG:game-sticker__',
    frames: ['__IMG:maze-rover__', '__IMG:maze-rover-pop__'],
    icons: {A: '__IMG:bird-icon__', B: '__IMG:fish-icon__', C: '__IMG:ant-icon__', D: '__IMG:rain-icon__'}
  },
  levels: [
    {
      map: ['#########', '#S..A..E#', '#..#.#..#', '#..B....#', '#########'],
      route: ['A', 'B'], step: .32,
      hints: ['先想想故事开头遇见谁。', '看看亮起来的下一幕。']
    },
    {
      map: ['#########', '#S.C...E#', '#...#+..#', '#B....A.#', '#.......#', '#########'],
      route: ['A', 'B', 'C'], step: .29, patrols: [{y: 4, from: 2, to: 6, speed: 1.05}],
      hints: ['想想离开池边后又遇到谁。', '先接亮起来的图，再往前开。']
    },
    {
      map: ['###########', '#S.C..+..E#', '#.#.###.#.#', '#A.......D#', '#...B.....#', '###########'],
      route: ['A', 'B', 'C', 'D'], step: .24, patrols: [{y: 3, from: 2, to: 7, speed: 1.35}],
      hints: ['听清下一幕，接好再去小旗。', '照着亮图开，挡板前可以吹泡泡。']
    }
  ].map(level => ({...level, listenOnly: true})),
  cues: [
    ['maze-begin', 'maze-after-bird', 'maze-exit'],
    ['maze-begin', 'maze-after-bird', 'maze-after-fish', 'maze-exit'],
    ['maze-begin', 'maze-after-bird', 'maze-after-fish', 'maze-after-ant', 'maze-exit']
  ].map(steps => ({steps, goal: steps[0], hint: 'maze-hint', hint2: 'maze-hint-again', praise: 'maze-praise'}))
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#maze-listen-mark'), K.$('#maze-first-swallow'));
const activity = K.gameTemplates.bubbleMaze(config);
activity.onState = (_, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
