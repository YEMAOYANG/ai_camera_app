const rounds = [
  {pickup:[['album',4],['eraser',5]],drop:[['main-pocket',3],['zip-pocket',6]],
    orders:[['album','main-pocket']],lanes:[{row:2,speed:.72,spacing:5.6,phase:.1}],step:.34},
  {pickup:[['album',2],['bottle',4],['tape',7]],drop:[['main-pocket',2],['zip-pocket',4],['side-pocket',7]],
    orders:[['bottle','side-pocket'],['tape','zip-pocket']],
    lanes:[{row:1,speed:.95,spacing:5.7,phase:.2},{row:3,speed:-.9,spacing:5.3,phase:2}],step:.29},
  {pickup:[['bottle',1],['foldmap',4],['tape',6],['eraser',8]],
    drop:[['main-pocket',2],['zip-pocket',4],['side-pocket',7]],
    orders:[['foldmap','main-pocket'],['tape','zip-pocket'],['bottle','side-pocket']],
    lanes:[{row:1,speed:1.05,spacing:5.6,phase:.1},{row:2,speed:-1.1,spacing:5.5,phase:2.2},
      {row:3,speed:.95,spacing:5.8,phase:1.3}],step:.24},
];
const hints = ['停一停，听听这趟要取什么，或找怎样的袋位。','大袋平放大本，小件找拉链袋，水瓶找侧网袋。'];
const title = '用品送进合适的袋位';
K.ready({title,sub:'先听要取什么，再看哪个袋位合用。'});
K.game(K.gameTemplates.listenDelivery({
  title,doneText:'用品按这只书包的袋位放好了。',voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:pocket-road-background__',sticker:'__IMG:storage-badge__',
    frames:['__IMG:storage-cart-idle__','__IMG:storage-cart-loaded__','__IMG:lane-paper-cart__'],
    icons:{
      album:'__IMG:delivery-album__',eraser:'__IMG:delivery-eraser__',bottle:'__IMG:delivery-bottle__',
      tape:'__IMG:delivery-tape__',foldmap:'__IMG:delivery-map__',
      'main-pocket':'__IMG:pocket-main__','zip-pocket':'__IMG:pocket-zip__','side-pocket':'__IMG:pocket-side__',
    },
  },
  levels:rounds.map(level=>({...level,hints})),
  cues:rounds.map(({orders})=>({
    goal:'pick-'+orders[0][0],steps:orders.flatMap(([good,pocket])=>['pick-'+good,'deliver-'+pocket]),
    hint:'delivery-hint',hint2:'delivery-help',praise:'delivery-praise',
  })),
}));
