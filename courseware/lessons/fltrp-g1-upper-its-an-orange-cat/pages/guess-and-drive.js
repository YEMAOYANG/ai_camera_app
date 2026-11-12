K.ready({title: '听问答开泡泡车', sub: '开向回答确认的图，最后开到旗子旁。'});

const pictures = {
  A: '__IMG:orange-cat__', B: '__IMG:yellow-box__',
  C: '__IMG:red-ball__', D: '__IMG:green-book__', F: '__IMG:red-book__',
  G: '__IMG:black-bird__', H: '__IMG:blue-bird__', I: '__IMG:blue-book__',
};
const tips = ['想想回答里的颜色和物名，再开。', '朝亮起来的图开过去。'];
const round = (map, route, step, patrols = []) =>
  ({map, route, step, patrols, hints: tips, listenOnly: true});

K.game(K.gameTemplates.bubbleMaze({
  art: {
    backdrop: '__IMG:maze-backdrop__',
    sticker: '__IMG:gallery-sticker__',
    frames: ['__IMG:paper-rover__', '__IMG:paper-rover-bubble__'],
    icons: pictures,
  },
  doneText: '小车找到所有展品！',
  voiceLead: true,
  stepVoiceLead: true,
  cues: [
    {steps: ['maze-orange-cat', 'maze-yellow-box'], goal: 'maze-exit', hint: 'maze-hint', hint2: 'maze-help', praise: 'maze-praise'},
    {steps: ['maze-red-ball', 'maze-green-book', 'maze-red-book'], goal: 'maze-exit', hint: 'maze-hint', hint2: 'maze-help', praise: 'maze-praise'},
    {steps: ['maze-blue-book', 'maze-black-bird', 'maze-green-book', 'maze-blue-bird'], goal: 'maze-exit', hint: 'maze-hint', hint2: 'maze-help', praise: 'maze-praise'},
  ],
  levels: [
    round(['#########', '#S..B.E.#', '#.#.#.#.#', '#..A....#', '#.......#', '#########'], ['A', 'B'], .37),
    round(['###########', '#S..D....E#', '#.#.###.#.#', '#.C..F....#', '#.#.###.#.#', '#.........#', '###########'],
      ['C', 'D', 'F'], .32),
    round(['#############', '#S..G+.....E#', '#.##.#####.##', '#..H..I..D..#', '#.....##.#..#', '#...........#', '#############'],
      ['I', 'G', 'D', 'H'], .27, [{y: 5, from: 3, to: 9, speed: 1.25}]),
  ],
}));
