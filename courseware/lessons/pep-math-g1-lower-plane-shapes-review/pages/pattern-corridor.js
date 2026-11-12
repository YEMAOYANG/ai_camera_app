K.ready({title:'开小车补齐展馆饰带', sub:'看已经重复的图案，先补亮起的空位。'});

const picture = {
  square: '__IMG:token-square__',
  tri: '__IMG:token-tri__',
  round: '__IMG:token-round__',
  slant: '__IMG:token-slant__',
  blank: '__IMG:token-blank__'
};
const symbols = {A:'square', B:'tri', C:'round', D:'slant', F:'tri', G:'tri', H:'round', J:'square'};
const levels = [
  {
    map: ['#########','#.......#','#S.BA.E.#','#.......#','#########'],
    prefix: ['square','tri','square','tri'],
    route: ['A','B'], listenOnly: true, step: .29,
    hints: ['看亮着的空位，它在小段的哪里？','从左边读一小段，再对照现在的空位。']
  },
  {
    map: ['##########','#...C....#','#S...+..E#','#..D...F.#','##########'],
    prefix: ['round','slant','tri','round','slant','tri'],
    route: ['C','D','F'], listenOnly: true, step: .24,
    hints: ['先找完全一样的小段。','接着看空位，按小段原来的顺序补。']
  },
  {
    map: ['###########','#..G......#','#S...#..H.#','#..J..+...#','#........E#','###########'],
    prefix: ['square','square','tri','round','square','square'],
    route: ['G','H','J'], listenOnly: true, step: .21,
    hints: ['两个相同的形也可以都在一小段里。','看看上一小段，两个正方形后面接什么。']
  }
];

const strip = K.$('#pattern-strip');
const cells = [...strip.querySelectorAll('img')];
const game = K.gameTemplates.bubbleMaze({
  voiceLead: true,
  doneText: '找准重复的小段，沿着顺序补齐图形。',
  art: {
    backdrop: '__IMG:hall-backdrop__',
    frames: ['__IMG:maze-rover__','__IMG:maze-rover-pop__'],
    sticker: '__IMG:ribbon-sticker__',
    icons: Object.fromEntries(Object.entries(symbols).map(([key,shape]) => [key,picture[shape]]))
  },
  cues: [
    {goal:'maze-two', hint:'maze-hint', hint2:'maze-help', praise:'maze-praise'},
    {goal:'maze-three', hint:'maze-hint', hint2:'maze-help', praise:'maze-praise'},
    {goal:'maze-repeated-card', hint:'maze-hint', hint2:'maze-help', praise:'maze-praise'}
  ],
  levels
});
const maze = K.game({...game, bubbleAt: () => ({x:640,y:580})});

maze.follow(strip, game => {
  const {prefix,route} = levels[game.level];
  const found = Math.min(game.data.w?.i ?? 0,route.length);
  cells.forEach((cell,i) => {
    const step = i-prefix.length;
    const shape = prefix[i] ?? (step < found ? symbols[route[step]] : 'blank');
    cell.hidden = i >= prefix.length+route.length;
    if (cell.getAttribute('src') !== picture[shape]) cell.setAttribute('src',picture[shape]);
    cell.dataset.current = String(step===found && step<route.length);
  });
  return {x:27,y:70,w:20+(prefix.length+route.length)*60,h:69};
});
maze.follow('#first-pattern-blank', () => ({x:277,y:76,w:55,h:55}));
