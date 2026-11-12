K.ready({title:'瞄准能凑满十的一组',sub:'看左边还空几格。瞄准合适的数量，再发弹珠。'});

const rods = {
  1:'__IMG:aim-rods-1__',2:'__IMG:aim-rods-2__',3:'__IMG:aim-rods-3__',
  4:'__IMG:aim-rods-4__',5:'__IMG:aim-rods-5__',6:'__IMG:aim-rods-6__',
  7:'__IMG:aim-rods-7__',8:'__IMG:aim-rods-8__',9:'__IMG:aim-rods-9__',
  10:'__IMG:ten-outline__'
};
const before = {
  4:'__IMG:ten-start-4__',5:'__IMG:ten-start-5__',6:'__IMG:ten-start-6__',
  7:'__IMG:ten-start-7__',8:'__IMG:ten-start-8__',9:'__IMG:ten-start-9__'
};
const complete = {
  4:'__IMG:ten-done-4__',5:'__IMG:ten-done-5__',6:'__IMG:ten-done-6__',
  7:'__IMG:ten-done-7__',8:'__IMG:ten-done-8__',9:'__IMG:ten-done-9__'
};
const target=(x,value)=>({x,value});
const levels=[
  {total:10,queue:[6,8],targets:[target(350,2),target(640,4),target(910,3)],drift:0,speed:455,targetWidth:146,targetHeight:107,
    hints:['看看这组放进去后，十格够不够。','数左边还空几格，再选一样多的靶。']},
  {total:10,queue:[7,5,6],targets:[target(365,5),target(540,3),target(720,4),target(900,6)],drift:9,speed:502,targetWidth:136,targetHeight:104,
    hints:['不要看颜色。比一比两边有几根。','数空着的格，再去找同样多的散杆。']},
  {total:10,queue:[9,4,7],targets:[target(350,3),target(495,1),target(640,4),target(785,6),target(930,2)],drift:15,speed:558,targetWidth:128,targetHeight:100,
    hints:['每次弹珠带来的数量可能不同。','先把当前空格数清，再看靶往哪边移。']}
];
const aim = K.game(K.gameTemplates.magnetMarbles({
  voiceLead:true,
  doneText:'每次都找到了能凑满十格的另一组。',
  art:{backdrop:'__IMG:aim-backdrop__',frames:['__IMG:amber-marble__'],sticker:'__IMG:kite-sticker__',icons:rods},
  cues:[
    {goal:'aim-ten',hint:'aim-hint',hint2:'aim-help',praise:'aim-praise'},
    {goal:'aim-fills',hint:'aim-hint',hint2:'aim-help',praise:'aim-praise'},
    {goal:'aim-mixed',hint:'aim-hint',hint2:'aim-help',praise:'aim-praise'}
  ],
  levels
}));
const current = K.$('#current-ten');
const last = K.$('#last-ten');
aim.follow(current, game => {
  const queue=levels[game.level].queue;
  const index=Math.min(game.data.w?.i ?? 0,queue.length-1);
  const image=before[queue[index]];
  if (current.getAttribute('src')!==image) current.setAttribute('src',image);
  return {x:18,y:217,w:198,h:136};
});
aim.follow(last, game => {
  const queue=levels[game.level].queue;
  const world=game.data.w;
  const given=queue[(world?.i ?? 0)-1];
  const image=given+world?.locked?.value===10 ? complete[given] : null;
  last.hidden=!image;
  if (image && last.getAttribute('src')!==image) last.setAttribute('src',image);
  return {x:1068,y:272,w:191,h:132};
});
aim.follow('#first-four-rods', () => ({x:567,y:175.5,w:146,h:107}));
