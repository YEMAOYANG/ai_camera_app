const headings = {north: [0,-1], east: [1,0], south: [0,1], west: [-1,0]};
const centerColumn = 4;
const stationPlan = [
  {
    green: ['north', [[3,'purple-drum'],[6,'blue-lantern']]],
    star: ['north', [[3,'green-flag'],[6,'orange-crate']]],
    orders: [['left','right']], lanes: [{row:2,speed:.9,spacing:5.7,phase:0}], step:.33,
  },
  {
    green: ['south', [[2,'orange-crate'],[6,'blue-lantern']]],
    star: ['north', [[2,'triangle-shaker'],[6,'green-flag']]],
    orders: [['left','left'],['right','right']],
    lanes: [{row:1,speed:-1.18,spacing:4.7,phase:2},{row:3,speed:1.32,spacing:4.8,phase:1}], step:.26,
  },
  {
    green: ['east', [[2,'blue-lantern'],[7,'purple-drum']]],
    star: ['west', [[1,'triangle-shaker'],[7,'orange-crate']]],
    orders: [['front','back'],['back','front']],
    lanes: [{row:1,speed:-1.42,spacing:4.3,phase:.7},{row:2,speed:1.56,spacing:4.5,phase:2},{row:3,speed:-1.36,spacing:4.6,phase:1.4}], step:.23,
  },
];
function select([heading, props], direction) {
  const [fx,fy] = headings[heading];
  const lateral = -fy;
  const horizontal = {front:fx, back:-fx, right:lateral, left:-lateral};
  const target = props.find(([col]) => Math.sign(col-centerColumn) === horizontal[direction]);
  if (!target) throw new Error('direction must resolve to one prop at this station');
  return target[1];
}
function stations([face, props], who) {
  return [[who+'-ref-'+face,centerColumn], ...props.map(([col, prop]) => [prop,col])];
}
const hints = ['听听是谁的方向，再找那顶帽子和脚下箭头。','车慢一点，可以先在路边停一停。'];
const levels = stationPlan.map(({green, star, orders, lanes, step}) => ({
  pickup: stations(green,'green'),
  drop: stations(star,'star'),
  orders: orders.map(([pick,drop]) => [select(green,pick),select(star,drop)]),
  lanes, step, hints,
}));
const title = '给小演员送道具';
K.ready({title,sub:'听方位，找到参照的人，再开车取和送。'});
K.game(K.gameTemplates.listenDelivery({
  title, doneText:'每次先找人和朝向，给两岸送对了道具。',
  voiceLead:true, stepVoiceLead:true,
  art:{
    backdrop:'__IMG:delivery-background__', sticker:'__IMG:camera-badge__',
    frames:['__IMG:truck-still__','__IMG:truck-moving__','__IMG:lane-cart__'],
    icons:{
      'purple-drum':'__IMG:purple-drum__','blue-lantern':'__IMG:blue-lantern__',
      'green-flag':'__IMG:green-flag__','orange-crate':'__IMG:orange-crate__','triangle-shaker':'__IMG:triangle-shaker__',
      'green-ref-north':'__IMG:green-ref-north__','green-ref-south':'__IMG:green-ref-south__',
      'green-ref-east':'__IMG:green-ref-east__','star-ref-north':'__IMG:star-ref-north__',
      'star-ref-west':'__IMG:star-ref-west__',
    },
  },
  levels,
  cues:stationPlan.map(({orders}) => ({
    goal:'green-'+orders[0][0],
    hint:'delivery-hint',hint2:'delivery-help',praise:'delivery-praise',
    steps:orders.flatMap(([pick,drop])=>['green-'+pick,'star-'+drop]),
  })),
}));
