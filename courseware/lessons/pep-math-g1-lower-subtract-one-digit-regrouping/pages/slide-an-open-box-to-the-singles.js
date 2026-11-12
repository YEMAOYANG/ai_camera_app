K.ready({title:'拆一盒，让散杯碰到一起', sub:'一盒换十个，把它和原有散杯拼在同一格。'});

const orders={
  42:'__IMG:slide-order-42__',31:'__IMG:slide-order-31__',46:'__IMG:slide-order-46__',
  60:'__IMG:slide-order-60__',54:'__IMG:slide-order-54__',77:'__IMG:slide-order-77__',
};
const icons={
  ten:'__IMG:closed-ten__',
  u0:'__IMG:loose-0__',u1:'__IMG:loose-1__',u2:'__IMG:loose-2__',u4:'__IMG:loose-4__',
  u6:'__IMG:loose-6__',u7:'__IMG:loose-7__',
  r10:'__IMG:loose-10__',r11:'__IMG:loose-11__',r12:'__IMG:loose-12__',
  r14:'__IMG:loose-14__',r16:'__IMG:loose-16__',r17:'__IMG:loose-17__',
};
const hints=['只拿一盒来换，旁边整盒留着。','把要拆的一盒与原有散杯滑到同一路，让它们碰到一起。'];
const cues={hint:'slide-hint',hint2:'slide-help',praise:'slide-praise'};
function room(wholes,board,seconds,walls=[]) {
  const singles=wholes.map(value=>value%10);
  const targets=singles.map(count=>'r'+(count+10));
  return {wholes,board,seconds,walls,targets,hints,
    pairs:singles.map((count,index)=>['ten','u'+count,targets[index]])};
}
const levels=[
  room([42],[[null,null,null,null],['ten',null,'u2',null],[null,null,null,null],[null,null,null,null]],.35),
  room([31,46],[['ten',null,'ten',null],[null,null,'u1',null],['u6',null,null,null],[null,null,null,null]],.29,[5]),
  room([60,54,77],[[null,null,'ten','u0'],[null,null,null,null],['ten','ten','u4','u7'],[null,null,null,null]],.24,[6,7]),
];
const game=K.game(K.gameTemplates.slideMerge({
  voiceLead:true,
  doneText:'盒里的十个杯换成了散杯，原来的总量没有变。',
  art:{backdrop:'__IMG:slide-backdrop__',frames:['__IMG:cup-helper__','__IMG:cup-hop__'],
    sticker:'__IMG:cup-slide-award__',icons},
  cues:[{...cues,goal:'slide-first'},{...cues,goal:'slide-two'},{...cues,goal:'slide-zero'}],
  levels,
}));
const guide=K.$('#exchange-order-guide');
const previews=[...guide.querySelectorAll('img')];
game.follow(guide,current=>{
  const level=levels[current.level];
  previews.forEach((image,index)=>{
    const src=orders[level.wholes[index]];
    image.hidden=!src;
    if(src&&image.getAttribute('src')!==src)image.setAttribute('src',src);
  });
  return {x:21,y:132,w:237,h:16+level.wholes.length*89};
});
game.follow('#first-box',()=>({x:318,y:236,w:88,h:80}));
game.follow('#first-singles',()=>({x:526,y:236,w:88,h:80}));
game.follow('#first-shelf',()=>({x:824,y:191,w:96,h:78}));
