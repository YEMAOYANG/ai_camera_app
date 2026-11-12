K.ready({title:'滑一滑，把旗子拼成订单量', sub:'看订单，往能让两张卡碰头的方向滑。'});

const tiles={
  6:'__IMG:tile-6__',8:'__IMG:tile-8__',9:'__IMG:tile-9__',10:'__IMG:tile-10__',
  19:'__IMG:tile-19__',20:'__IMG:tile-20__',28:'__IMG:tile-28__',30:'__IMG:tile-30__',
  37:'__IMG:tile-37__',40:'__IMG:tile-40__',46:'__IMG:tile-46__',50:'__IMG:tile-50__',
  54:'__IMG:tile-54__',60:'__IMG:tile-60__',7:'__IMG:tile-7__',
};
const hints=['看订单有多少整条、几面散旗。','让能合成订单的两张卡滑到同一条路，再让它们碰头。'];
const cues={hint:'slide-hint',hint2:'slide-help',praise:'slide-praise'};

function level(board,targets,seconds,walls=[]) {
  const values=board.flat().filter(value=>value!==null);
  const pairs=values.flatMap((a,i)=>values.slice(i+1)
    .filter(b=>targets.includes(a+b)).map(b=>[a,b,a+b]));
  return {board,targets,seconds,walls,pairs,hints};
}
const levels=[
  level([[null,null,null,null],[20,null,null,40],[null,null,null,null],[null,null,null,null]],[60],.35),
  level([[40,null,20,null],[null,null,6,null],[8,null,null,null],[null,null,null,null]],[46,28],.29,[5]),
  level([[null,null,10,9],[null,null,null,null],[30,50,4,7],[null,null,null,null]],[37,54,19],.24,[6,7]),
];
const slide=K.game(K.gameTemplates.slideMerge({
  voiceLead:true,
  doneText:'整条与散旗合起来，这些订单都配好了。',
  art:{
    backdrop:'__IMG:slide-backdrop__',
    frames:['__IMG:chipmunk-ready__','__IMG:chipmunk-hop__'],
    sticker:'__IMG:rosette-sticker__',
    icons:tiles,
  },
  cues:[
    {...cues,goal:'slide-tens'},
    {...cues,goal:'slide-mixed'},
    {...cues,goal:'slide-three'},
  ],
  levels,
}));

const guide=K.$('#slide-order-guide');
const orderImages=[...guide.querySelectorAll('img')];
slide.follow(guide,game=>{
  const targets=levels[game.level].targets;
  orderImages.forEach((image,index)=>{
    image.hidden=index>=targets.length;
    const src=tiles[targets[index]];
    if (src && image.getAttribute('src')!==src) image.setAttribute('src',src);
  });
  return {x:19,y:135,w:237,h:16+targets.length*82};
});
slide.follow('#first-twenty',()=>({x:318,y:236,w:88,h:80}));
slide.follow('#first-forty',()=>({x:630,y:236,w:88,h:80}));
slide.follow('#first-shelf-tray',()=>({x:824,y:191,w:96,h:78}));
