const part = (token, group, x, y) => ({token, group, x, y});
const dock = (group, x, y) => ({group, x, y, sample: 'use-'+group});
const hints = ['再看这个部件。它是用来围住、托住，还是隔开？', '比一比亮起来的用途图，再把部件推过去。'];
const levels = [
  {
    map: ['########', '#......#', '#.S....#', '#......#', '########'],
    step: .31,
    items: [part('part-tall','tall',3,2), part('part-base','base',3,3)],
    docks: [dock('tall',5,2), dock('base',5,3)],
  },
  {
    map: ['#########', '#.......#', '#..#....#', '#.S.....#', '#.......#', '#########'],
    step: .26,
    items: [part('part-divider','divider',4,2), part('part-tray','tray',4,4), part('part-low','low',3,3)],
    docks: [dock('divider',6,2), dock('tray',7,4), dock('low',6,3)],
  },
  {
    map: ['##########', '#........#', '#..#.....#', '#.S......#', '#....#...#', '#........#', '##########'],
    step: .22,
    items: [part('part-low','low',4,3), part('part-base','base',7,4),
      part('part-divider','divider',4,2), part('part-tray','tray',4,5)],
    docks: [dock('low',7,3), dock('base',8,4), dock('divider',8,2), dock('tray',7,5)],
  },
];
const title = '把部件送到用途图';
K.ready({title, sub:'认出部件的用途，再把它推到那张图。'});
const game = K.game(K.gameTemplates.sortingDepot({
  title, doneText:'每个部件都找到了能帮忙的地方。', voiceLead:true,
  art:{
    backdrop:'__IMG:sort-workbench__', sticker:'__IMG:green-mark__',
    frames:['__IMG:parts-cart__'],
    icons:{
      'part-tall':'__IMG:part-tall__', 'use-tall':'__IMG:use-tall__',
      'part-base':'__IMG:part-base__', 'use-base':'__IMG:use-base__',
      'part-divider':'__IMG:part-divider__', 'use-divider':'__IMG:use-divider__',
      'part-tray':'__IMG:part-tray__', 'use-tray':'__IMG:use-tray__',
      'part-low':'__IMG:part-low__', 'use-low':'__IMG:use-low__',
    },
  },
  levels:levels.map(level=>({...level,hints})),
  cues:['sort-first','sort-next','sort-mixed'].map(goal=>({goal,hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'})),
}));
game.follow('#parts-first-dock', () => {
  const w=game.data.w;
  if(!w||game.level!==0)return null;
  const {x,y}=levels[0].docks[0];
  return {x:w.ox+x*w.s,y:w.oy+y*w.s,w:w.s,h:w.s};
});
