K.ready({title:'把形卡送到合适的托盘', sub:'听这一关按什么分，再开推车。'});

const straight = 'straight';
const curve = 'curve';
const three = 'three';
const four = 'four';
const depot = K.game(K.gameTemplates.sortingDepot({
  voiceLead: true,
  doneText: '先选清楚一种分类标准，形卡就各有位置。',
  art: {
    backdrop: '__IMG:depot-backdrop__',
    frames: ['__IMG:sort-cart__', '__IMG:sort-cart-push__'],
    sticker: '__IMG:museum-sticker__',
    icons: {
      straight: '__IMG:token-straight__',
      curve: '__IMG:token-curve__',
      rect: '__IMG:token-rect__',
      upright: '__IMG:token-tall-rect__',
      square: '__IMG:token-square__',
      tilted: '__IMG:token-tilt-square__',
      round: '__IMG:token-round__',
      tri: '__IMG:token-tri__',
      turned: '__IMG:token-turn-tri__',
      slant: '__IMG:token-slant__'
    }
  },
  cues: [
    {goal:'depot-edge', hint:'depot-hint', hint2:'depot-help', praise:'depot-praise'},
    {goal:'depot-count', hint:'depot-hint', hint2:'depot-help', praise:'depot-praise'},
    {goal:'depot-turn', hint:'depot-hint', hint2:'depot-help', praise:'depot-praise'}
  ],
  levels: [
    {
      map: ['#########','#.......#','#.S.....#','#.......#','#.......#','#########'],
      step: .31,
      items: [
        {x:3,y:2,token:'rect',group:straight},
        {x:3,y:4,token:'round',group:curve}
      ],
      docks: [
        {x:6,y:2,sample:'straight',group:straight},
        {x:6,y:4,sample:'curve',group:curve}
      ],
      hints: ['沿形卡外圈看一看。','对照托盘的边线，再找合适的方向。']
    },
    {
      map: ['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],
      step: .26,
      items: [
        {x:4,y:2,token:'tilted',group:four},
        {x:4,y:4,token:'upright',group:four},
        {x:3,y:3,token:'tri',group:three}
      ],
      docks: [
        {x:6,y:2,sample:'rect',group:four},
        {x:7,y:4,sample:'rect',group:four},
        {x:6,y:3,sample:'tri',group:three}
      ],
      hints: ['从一个角开始，一条边数一次。','再数一遍卡片和托盘的直边。']
    },
    {
      map: ['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],
      step: .22,
      items: [
        {x:4,y:3,token:'slant',group:four},
        {x:7,y:4,token:'turned',group:three},
        {x:4,y:2,token:'square',group:four},
        {x:4,y:5,token:'tri',group:three}
      ],
      docks: [
        {x:7,y:3,sample:'rect',group:four},
        {x:8,y:4,sample:'tri',group:three},
        {x:8,y:2,sample:'rect',group:four},
        {x:7,y:5,sample:'tri',group:three}
      ],
      hints: ['斜着放也可以沿边数。','先认准组，再绕到形卡的另一边推。']
    }
  ]
}));

const rulePicture = K.$('#sort-rule');
depot.follow(rulePicture, game => {
  const image = game.level === 0 ? '__IMG:rule-edge__' : '__IMG:rule-count__';
  if (rulePicture.getAttribute('src') !== image) rulePicture.setAttribute('src', image);
  return {x:27,y:162,w:194,h:82};
});
depot.follow('#first-straight-card', () => ({x:527,y:268,w:70,h:70}));
depot.follow('#first-straight-dock', () => ({x:761,y:268,w:70,h:70}));
