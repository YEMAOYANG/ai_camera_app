K.ready({title:'按这一关的标准送盆牌', sub:'先听看哪一种标记，再推盆牌。'});

const rackRule = '__IMG:rule-rack__';
const shapeRule = '__IMG:rule-tag__';
const rulePicture = K.$('#rule-picture');
const depot = K.game(K.gameTemplates.sortingDepot({
  voiceLead: true,
  doneText: '每张盆牌都只送到一个托盘。',
  art: {
    backdrop: '__IMG:sort-backdrop__',
    frames: ['__IMG:plant-cart__', '__IMG:plant-cart-push__'],
    sticker: '__IMG:exhibit-sticker__',
    icons: {
      top: '__IMG:dock-top__', bottom: '__IMG:dock-bottom__',
      leaf: '__IMG:tag-leaf__', drop: '__IMG:tag-drop__',
      us: '__IMG:token-us__', ur: '__IMG:token-ur__',
      uf: '__IMG:token-uf__', ug: '__IMG:token-ug__',
      lr: '__IMG:token-lr__', lf: '__IMG:token-lf__', lg: '__IMG:token-lg__'
    }
  },
  cues: [
    {goal:'sort-rack-one',hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'},
    {goal:'sort-by-tag',hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'},
    {goal:'sort-rack-again',hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'}
  ],
  levels: [
    {
      map: ['########', '#......#', '#.S....#', '#......#', '########'],
      step: .31,
      items: [
        {x:3,y:2,token:'us',group:'top'}, {x:3,y:3,token:'lr',group:'bottom'}
      ],
      docks: [
        {x:5,y:2,sample:'top',group:'top'}, {x:5,y:3,sample:'bottom',group:'bottom'}
      ],
      hints: ['看看小架子亮在哪一层。', '先找亮起的托盘，再从盆牌后面推。']
    },
    {
      map: ['#########', '#.......#', '#..#....#', '#.S.....#', '#.......#', '#########'],
      step: .25,
      items: [
        {x:4,y:2,token:'uf',group:'leaf'},
        {x:4,y:4,token:'ug',group:'drop'},
        {x:3,y:3,token:'lr',group:'drop'}
      ],
      docks: [
        {x:6,y:2,sample:'leaf',group:'leaf'},
        {x:7,y:4,sample:'drop',group:'drop'},
        {x:6,y:3,sample:'drop',group:'drop'}
      ],
      hints: ['这关看叶形和水滴形。', '先对一对牌的形状，再从后面推。']
    },
    {
      map: ['##########', '#........#', '#..#.....#', '#.S......#', '#....#...#', '#........#', '##########'],
      step: .21,
      items: [
        {x:4,y:3,token:'us',group:'top'}, {x:7,y:4,token:'ur',group:'top'},
        {x:4,y:2,token:'lf',group:'bottom'}, {x:4,y:5,token:'lg',group:'bottom'}
      ],
      docks: [
        {x:7,y:3,sample:'top',group:'top'}, {x:8,y:4,sample:'top',group:'top'},
        {x:8,y:2,sample:'bottom',group:'bottom'}, {x:7,y:5,sample:'bottom',group:'bottom'}
      ],
      hints: ['这一关又按架层分。', '要留一条绕过去的路，也可以撤回。']
    }
  ]
}));
depot.follow('#rule-picture', game => {
  const picture = game.level === 1 ? shapeRule : rackRule;
  if (rulePicture.getAttribute('src') !== picture) rulePicture.setAttribute('src', picture);
  return {x:16,y:147,w:220,h:80};
});
depot.follow('#first-dock', () => ({x:739,y:300,w:84,h:84}));
