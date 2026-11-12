const sent = (n) => 'sent-'+n;
const left = (n) => 'left-'+n;
const order = (a,b) => [sent(a),left(b)];
const pick = (n,col) => [sent(n),col];
const dock = (n,col) => [left(n),col];
const lane = (row,speed,spacing,phase) => ({row,speed,spacing,phase});
const levels = [
  {pickup:[pick(4,3),pick(6,6)],drop:[dock(7,3),dock(8,6)],orders:[order(4,7)],
   lanes:[lane(2,.9,5.7,0)],step:.33},
  {pickup:[pick(4,2),pick(6,6),pick(8,8)],drop:[dock(5,1),dock(7,5),dock(8,7)],
   orders:[order(6,7),order(8,5)],lanes:[lane(1,-1.25,4.6,2),lane(3,1.36,4.6,1)],step:.26},
  {pickup:[pick(4,1),pick(6,4),pick(8,7),pick(7,3)],drop:[dock(8,6),dock(7,2),dock(5,4),dock(6,8)],
   orders:[order(4,8),order(6,7),order(8,5)],
   lanes:[lane(1,-1.8,3.9,.7),lane(2,1.65,4,2.2),lane(3,-1.6,4,1.4)],step:.20},
];
const hints = ['再听一次。现在要领回送走的，还是要找剩下的托盘？','慢慢开，路上能停一停。'];
const feedback = {hint:'return-hint',hint2:'return-help',praise:'return-praise'};
const cue = (id) => 'return-'+id;
const summary = {
  'sent-4/left-7': {src:'__IMG:returned-4-7__',alt:'送走四盆，剩七盆，原有十一盆'},
  'sent-6/left-7': {src:'__IMG:returned-6-7__',alt:'送走六盆，剩七盆，原有十三盆'},
  'sent-8/left-5': {src:'__IMG:returned-8-5__',alt:'送走八盆，剩五盆，原有十三盆'},
  'sent-4/left-8': {src:'__IMG:returned-4-8__',alt:'送走四盆，剩八盆，原有十二盆'},
};
const empty = {src:'__IMG:return-empty__',alt:'还没有合并两组盆苗'};
const title = '把送走的盆苗领回来';
K.ready({title,sub:'听清数量，先领回一组，再送到对应托盘。'});
const arcade = K.gameTemplates.listenDelivery({
  title,doneText:'两部分合回去，就是送走前的总数。',
  voiceLead:true,stepVoiceLead:true,
  art:{
    backdrop:'__IMG:yard-backdrop__',sticker:'__IMG:nursery-sticker__',
    frames:['__IMG:cart-open__','__IMG:cart-covered__','__IMG:utility-trolley__'],
    icons:{
      'sent-4':'__IMG:sent-4__','sent-6':'__IMG:sent-6__','sent-7':'__IMG:sent-7__','sent-8':'__IMG:sent-8__',
      'left-5':'__IMG:left-5__','left-6':'__IMG:left-6__','left-7':'__IMG:left-7__','left-8':'__IMG:left-8__',
    },
  },
  levels:levels.map(level=>({...level,hints})),
  cues:levels.map(level=>({...feedback,goal:cue(level.orders[0][0]),steps:level.orders.flat().map(cue)})),
});
const proof = K.$('#return-proof');
const picture = K.$('#return-proof-picture');
K.stage().appendChild(proof);
const draw = arcade.draw;
arcade.draw = (g,canvas) => {
  draw(g,canvas);
  const completed = g.data.w ? [...g.data.w.delivered].at(-1) : null;
  const current = completed ? summary[completed[1]+'/'+completed[0]] : empty;
  proof.hidden = g.state==='ready' || g.state==='done';
  if (g.state==='done' && completed) {
    const replay = K.$('#btn-again');
    if (replay && !K.$('.return-finish-proof')) {
      const photo = K.el('img','return-finish-proof');
      photo.src = current.src;
      photo.alt = current.alt;
      replay.parentElement.insertBefore(photo,replay);
    }
  }
  if (proof.hidden) return;
  if (picture.getAttribute('src')!==current.src) {
    picture.src = current.src;
    picture.alt = current.alt;
  }
};
K.game(arcade);
