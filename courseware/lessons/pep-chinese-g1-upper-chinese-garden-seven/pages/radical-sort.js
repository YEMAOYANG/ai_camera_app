const labels = {nai:'奶', ma:'妈', jie:'姐', mei:'妹', ming:'明', wan:'晚', zuo:'昨', chun:'春', woman:'女', sun:'日'};
const config = {
  title: '给字卡送到家',
  sub: '看清字卡里的部件，按箭头推到相应托盘。',
  doneText: '借书字卡都归好啦。',
  voiceLead: true,
  art: {
    sticker: '__IMG:rover__',
    frames: ['__IMG:rover__', '__IMG:rover-boost__'],
    icons: {
      nai: '__IMG:nai__', ma: '__IMG:ma__', jie: '__IMG:jie__', mei: '__IMG:mei__',
      ming: '__IMG:ming__', wan: '__IMG:wan__', zuo: '__IMG:zuo__', chun: '__IMG:chun__',
      woman: '__IMG:woman__', sun: '__IMG:sun__'
    }
  },
  levels: [
    {
      labels,
      map: ['########', '#......#', '#.S....#', '#......#', '########'],
      items: [{x:3,y:2,token:'nai',group:'woman'}, {x:3,y:3,token:'ming',group:'sun'}],
      docks: [{x:5,y:2,sample:'woman',group:'woman'}, {x:5,y:3,sample:'sun',group:'sun'}],
      step: 0.30,
      hints: ['找一找卡片里的熟悉部件。','看亮起来的托盘，再推过去。']
    },
    {
      labels,
      map: ['#########', '#.......#', '#..#....#', '#.S.....#', '#.......#', '#########'],
      items: [{x:4,y:2,token:'ma',group:'woman'}, {x:4,y:4,token:'chun',group:'sun'},
        {x:3,y:3,token:'wan',group:'sun'}],
      docks: [{x:6,y:2,sample:'woman',group:'woman'}, {x:6,y:3,sample:'sun',group:'sun'},
        {x:7,y:4,sample:'sun',group:'sun'}],
      step: 0.25,
      hints: ['看看字的左边，也看看下面。','把发亮的托盘当作找路的提示。']
    },
    {
      labels,
      map: ['##########', '#........#', '#..#.....#', '#.S......#', '#....#...#', '#........#', '##########'],
      items: [{x:4,y:3,token:'mei',group:'woman'}, {x:7,y:4,token:'zuo',group:'sun'},
        {x:5,y:2,token:'jie',group:'woman'}, {x:4,y:5,token:'chun',group:'sun'}],
      docks: [{x:8,y:4,sample:'sun',group:'sun'}, {x:5,y:1,sample:'woman',group:'woman'},
        {x:8,y:2,sample:'woman',group:'woman'}, {x:7,y:5,sample:'sun',group:'sun'}],
      step: 0.21,
      hints: ['慢一点，先找部件，再找空托盘。','可以按回转钮退一步，看看亮处。']
    }
  ],
  cues: Array.from({length:3}, () => ({
    goal:'sort-goal', hint:'sort-hint', hint2:'sort-goal', praise:'sort-praise'
  }))
};

K.ready({title:config.title, sub:config.sub});
K.stage().append(K.$('#garden-first-dock'));
K.game(K.gameTemplates.sortingDepot(config));
