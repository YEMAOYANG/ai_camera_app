const config = {
  title: '泡泡车送故事回家',
  sub: '听下一幕的线索，按故事顺序收图，接齐后去小旗。',
  doneText: '小蚂蚁的故事接到家啦。',
  voiceLead: true,
  stepVoiceLead: true,
  art: {
    backdrop: '__IMG:story-backdrop__',
    sticker: '__IMG:firefly-sticker__',
    frames: ['__IMG:garden-rover__', '__IMG:garden-rover-pop__'],
    icons: {
      A: '__IMG:maze-grass-icon__', B: '__IMG:lily-lowers__', C: '__IMG:maze-dragonfly-icon__',
      D: '__IMG:maze-firefly-icon__', R: '__IMG:rockery__', G: '__IMG:lawn__', F: '__IMG:flowerbed__'
    }
  },
  levels: [
    {
      map: ['#########', '#S.A...E#', '#..##...#', '#..B....#', '#########'],
      route: ['A', 'B'], step: .32,
      hints: ['先想小蚂蚁趴在哪里。', '试着去亮起来的下一幕。']
    },
    {
      map: ['##########', '#S...C..E#', '#...#.+..#', '#D.....B.#', '#........#', '##########'],
      route: ['B', 'C', 'D'], step: .29, patrols: [{y: 4, from: 2, to: 6, speed: 1.03}],
      hints: ['先想哪个朋友先伸出手。', '看看亮起的朋友，再往前开。']
    },
    {
      map: ['###########', '#S.G.+...E#', '#.#.###.#.#', '#R.......F#', '#.........#', '###########'],
      route: ['R', 'G', 'F'], step: .25, patrols: [{y: 3, from: 2, to: 7, speed: 1.32}],
      hints: ['照故事想想，飞过哪儿，再到哪儿？', '接亮图，遇到软挡板就吹泡泡。']
    }
  ].map(level => ({...level, listenOnly: true})),
  cues: [
    ['maze-grass', 'maze-lily', 'maze-exit'],
    ['maze-lily', 'maze-dragonfly', 'maze-firefly', 'maze-exit'],
    ['maze-rock', 'maze-lawn', 'maze-flowers', 'maze-exit']
  ].map(steps => ({steps, goal: steps[0], hint: 'maze-hint', hint2: 'maze-help', praise: 'maze-praise'}))
};

K.ready({title: config.title, sub: config.sub});
K.stage().append(K.$('#ant-listen-mark'), K.$('#ant-first-grass'));
const activity = K.gameTemplates.bubbleMaze(config);
activity.onState = (_, state) => {
  if (state.demo === false) {
    K.$$('.teach-hl', K.stage()).forEach(anchor => anchor.classList.remove('teach-hl'));
  }
};
K.game(activity);
