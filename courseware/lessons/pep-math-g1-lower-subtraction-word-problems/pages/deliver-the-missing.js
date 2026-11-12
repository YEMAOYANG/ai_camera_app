K.ready({title:'取正确数量，送到所问的盘',sub:'看图算一组，开车取货，走到这一单要找的盘。'});

const queueArt = [
  ['__IMG:order-14-8-wave__'],
  ['__IMG:order-14-6-leaf__','__IMG:order-16-7-loan__'],
  ['__IMG:order-13-5-wave__','__IMG:order-15-6-leaf__','__IMG:order-12-8-loan__']
];
const delivery = K.game(K.gameTemplates.listenDelivery({
  voiceLead:true,stepVoiceLead:true,
  doneText:'你找对了这道题要的另一组，还把它送到了。',
  art:{
    backdrop:'__IMG:delivery-backdrop__',sticker:'__IMG:leaf-sticker__',
    frames:['__IMG:delivery-cart__','__IMG:delivery-action__','__IMG:lane-trolley__'],
    icons:{
      'cargo-4':'__IMG:cargo-4__','cargo-5':'__IMG:cargo-5__','cargo-6':'__IMG:cargo-6__','cargo-7':'__IMG:cargo-7__',
      'cargo-8':'__IMG:cargo-8__','cargo-9':'__IMG:cargo-9__',
      wave:'__IMG:drop-wave__',leaf:'__IMG:drop-leaf__',loan:'__IMG:drop-loan__'
    }
  },
  cues:[
    {goal:'ask-wave',steps:['ask-wave','send-wave'],hint:'deliver-hint',hint2:'deliver-help',praise:'deliver-praise'},
    {goal:'ask-leaf',steps:['ask-leaf','send-leaf','ask-loan','send-loan'],hint:'deliver-hint',hint2:'deliver-help',praise:'deliver-praise'},
    {goal:'ask-wave',steps:['ask-wave','send-wave','ask-leaf','send-leaf','ask-loan','send-loan'],hint:'deliver-hint',hint2:'deliver-help',praise:'deliver-praise'}
  ],
  levels:[
    {
      pickup:[['cargo-6',2],['cargo-5',4],['cargo-8',7]], drop:[['wave',2],['leaf',6]],
      orders:[['cargo-6','wave']], lanes:[{row:2,speed:.8,spacing:4.6,phase:.2}],step:.33,
      hints:['拿的是已经知道的，还是要找的？','看左边两条线索，用总数减已知。']
    },
    {
      pickup:[['cargo-6',2],['cargo-8',4],['cargo-9',6],['cargo-7',7]], drop:[['leaf',2],['loan',6]],
      orders:[['cargo-8','leaf'],['cargo-9','loan']],
      lanes:[{row:2,speed:1.05,spacing:4.8,phase:1.2},{row:3,speed:-.75,spacing:5.3,phase:2.2}],step:.27,
      hints:['这一单问的是什么？','看清留在原处的那一组，再算借出的。']
    },
    {
      pickup:[['cargo-6',1],['cargo-8',3],['cargo-4',5],['cargo-9',7]], drop:[['wave',2],['leaf',4],['loan',6]],
      orders:[['cargo-8','wave'],['cargo-9','leaf'],['cargo-4','loan']],
      lanes:[{row:1,speed:-1.15,spacing:4.9,phase:2.1},{row:3,speed:.95,spacing:4.5,phase:1.1}],step:.23,
      hints:['停一停，先看这一单。','对一对总数和已知部分。拿好后去下方图示的盘。']
    }
  ]
}));
const order = K.$('#delivery-order');
delivery.follow(order, game => {
  const cards = queueArt[game.level];
  const image = cards[Math.min(game.data.w?.order ?? 0,cards.length-1)];
  if (order.getAttribute('src') !== image) order.setAttribute('src',image);
  return {x:21,y:184,w:198,h:265};
});
delivery.follow('#first-cargo', () => ({x:430,y:496,w:76,h:78}));
delivery.follow('#first-drop', () => ({x:430,y:153,w:76,h:78}));
