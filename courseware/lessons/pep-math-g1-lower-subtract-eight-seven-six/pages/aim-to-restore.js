K.ready({title:'瞄准能凑回总数的一组',sub:'看订单图。先瞄准，再发射，飞行中可以调方向。'});

const orders = {
  'order-a':{given:8,whole:14,picture:'__IMG:order-14-8__'},
  'order-b':{given:7,whole:12,picture:'__IMG:order-12-7__'},
  'order-c':{given:8,whole:15,picture:'__IMG:order-15-8__'},
  'order-d':{given:7,whole:15,picture:'__IMG:order-15-7__'},
  'order-e':{given:6,whole:11,picture:'__IMG:order-11-6__'},
  'order-f':{given:7,whole:14,picture:'__IMG:order-14-7__'},
  'order-g':{given:8,whole:16,picture:'__IMG:order-16-8__'},
  'order-h':{given:6,whole:15,picture:'__IMG:order-15-6__'}
};
const amounts = {5:'__IMG:target-5__',6:'__IMG:target-6__',7:'__IMG:target-7__',8:'__IMG:target-8__',9:'__IMG:target-9__'};
const orderIcons = Object.fromEntries(Object.entries(orders).map(([id,order])=>[id,amounts[order.given]]));
const target = (x,value) => ({x,value});
const levels = [
  {
    queue:['order-a','order-b'],
    targets:[target(350,5),target(640,6),target(910,7)],
    drift:0,speed:455,targetWidth:144,targetHeight:104,
    hints:['合起来和上面的总量一样吗？','对照已经知道的一组，再数目标图。']
  },
  {
    queue:['order-c','order-d','order-e'],
    targets:[target(365,5),target(540,7),target(720,8),target(900,6)],
    drift:11,speed:505,targetWidth:138,targetHeight:102,
    hints:['再看看已知的是哪一组。','先算合起来的数，再调弹珠方向。']
  },
  {
    queue:['order-f','order-g','order-h','order-b'],
    targets:[target(350,8),target(495,5),target(640,6),target(785,9),target(930,7)],
    drift:15,speed:560,targetWidth:128,targetHeight:100,
    hints:['这一单的总数可能变了。','重新对照这张订单，找能凑回总数的图。']
  }
].map(level=>({...level,matches:(id,value)=>orders[id].given+value===orders[id].whole}));

const marble = K.game(K.gameTemplates.magnetMarbles({
  voiceLead:true,
  doneText:'知道一部分，找到了能凑回总数的另一部分。',
  art:{
    backdrop:'__IMG:aim-backdrop__',
    frames:['__IMG:game-marble__'],
    sticker:'__IMG:lantern-sticker__',
    icons:{...amounts,...orderIcons}
  },
  cues:[
    {goal:'aim-whole',hint:'aim-hint',hint2:'aim-help',praise:'aim-praise'},
    {goal:'aim-two-parts',hint:'aim-hint',hint2:'aim-help',praise:'aim-praise'},
    {goal:'aim-new-whole',hint:'aim-hint',hint2:'aim-help',praise:'aim-praise'}
  ],
  levels
}));

const card = K.$('#order-card');
let shownLevel = -1;
let shownIndex = 0;
marble.follow(card, game => {
  const queue = levels[game.level].queue;
  const world = game.data.w;
  if (shownLevel !== game.level || !world) {
    shownLevel = game.level;
    shownIndex = 0;
  } else if (world.delay <= 0) {
    shownIndex = Math.min(world.i,queue.length-1);
  }
  const id = queue[shownIndex];
  if (card.getAttribute('src') !== orders[id].picture) card.setAttribute('src',orders[id].picture);
  return {x:18,y:194,w:230,h:184};
});
marble.follow('#known-group', () => ({x:34,y:294,w:122,h:65}));
marble.follow('#first-remainder-target', () => ({x:568,y:177,w:144,h:104}));
