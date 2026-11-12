K.ready({title:'给数量找车位', sub:'看货有多少，再看托盘的珠子在哪一杆。'});

const hints = ['比较货件的数量和托盘珠子的位置。', '从右起，第一杆是一，第二杆是十，第三杆是一百。'];
const cues = {hint:'depot-hint', hint2:'depot-help', praise:'depot-praise'};
const depot = K.game(K.gameTemplates.sortingDepot({
  voiceLead: true,
  doneText: '看珠子在哪根杆，就能认出一、十和一百。',
  art: {
    backdrop:'__IMG:depot-backdrop__',
    frames:['__IMG:cart-ready__','__IMG:cart-push__'],
    sticker:'__IMG:leaf-award__',
    icons: {
      one:'__IMG:item-one__', otherOne:'__IMG:item-one-alt__',
      ten:'__IMG:item-ten__', otherTen:'__IMG:item-ten-alt__', hundred:'__IMG:item-hundred__',
      onesDock:'__IMG:dock-1__', tensDock:'__IMG:dock-10__', hundredsDock:'__IMG:dock-100__',
    },
  },
  cues: [
    {...cues, goal:'depot-first'},
    {...cues, goal:'depot-second'},
    {...cues, goal:'depot-third'},
  ],
  levels: [
    {
      map:['#########','#.......#','#.S.....#','#.......#','#.......#','#########'],
      step:.31, hints,
      items:[
        {x:3,y:2,token:'one',group:1},
        {x:3,y:4,token:'ten',group:10},
      ],
      docks:[
        {x:6,y:2,sample:'onesDock',group:1},
        {x:6,y:4,sample:'tensDock',group:10},
      ],
    },
    {
      map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],
      step:.26, hints,
      items:[
        {x:4,y:2,token:'otherOne',group:1},
        {x:4,y:4,token:'hundred',group:100},
        {x:3,y:3,token:'ten',group:10},
      ],
      docks:[
        {x:6,y:2,sample:'onesDock',group:1},
        {x:7,y:4,sample:'hundredsDock',group:100},
        {x:6,y:3,sample:'tensDock',group:10},
      ],
    },
    {
      map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],
      step:.23, hints,
      items:[
        {x:4,y:3,token:'ten',group:10},
        {x:7,y:4,token:'otherTen',group:10},
        {x:4,y:2,token:'one',group:1},
        {x:4,y:5,token:'hundred',group:100},
      ],
      docks:[
        {x:7,y:3,sample:'tensDock',group:10},
        {x:8,y:4,sample:'tensDock',group:10},
        {x:8,y:2,sample:'onesDock',group:1},
        {x:7,y:5,sample:'hundredsDock',group:100},
      ],
    },
  ],
}));

depot.follow('#unit-legend', () => ({x:17,y:151,w:221,h:334}));
depot.follow('#first-unit-item', () => ({x:527,y:268,w:70,h:70}));
depot.follow('#first-ones-dock', () => ({x:761,y:268,w:70,h:70}));
