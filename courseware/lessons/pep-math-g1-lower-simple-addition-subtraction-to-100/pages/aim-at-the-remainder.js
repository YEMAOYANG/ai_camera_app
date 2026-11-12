K.ready({title:'发射到取走后剩下的数量', sub:'看虚线盘要取走多少，再瞄准留下的。'});

const orders={
  first:{whole:80,take:30,picture:'__IMG:order-first__'},
  'take-four':{whole:64,take:4,picture:'__IMG:order-take-four__'},
  'take-sixty':{whole:64,take:60,picture:'__IMG:order-take-sixty__'},
  'take-three':{whole:73,take:3,picture:'__IMG:order-take-three__'},
  'take-eighty':{whole:87,take:80,picture:'__IMG:order-take-eighty__'},
};
const icons={
  3:'__IMG:tile-3__',4:'__IMG:tile-4__',7:'__IMG:tile-7__',10:'__IMG:tile-10__',
  20:'__IMG:tile-20__',30:'__IMG:tile-30__',50:'__IMG:tile-50__',
  60:'__IMG:tile-60__',64:'__IMG:tile-64__',70:'__IMG:tile-70__',80:'__IMG:tile-80__',
};
const hints=['看虚线盘，那些旗已经被取走。','数留下的整条和散旗，再找同样多的牌。'];
const cues={hint:'aim-hint',hint2:'aim-help',praise:'aim-praise'};
const level=(queue,targets,speed,drift,targetWidth)=>({
  queue,targets:targets.map(([value,x])=>({value,x})),speed,drift,targetWidth,targetHeight:113,hints,
  matches(key,value){
    const order=orders[key];
    return order != null && order.whole-order.take===value;
  },
  symbol:'flag',
});
const aim=K.game(K.gameTemplates.magnetMarbles({
  voiceLead:true,
  stepVoiceLead:true,
  doneText:'看清拿走的部分，每张取货单都算对了。',
  art:{
    backdrop:'__IMG:aim-backdrop__',frames:['__IMG:amber-marble__'],sticker:'__IMG:delivery-sticker__',
    icons:{...icons,flag:'__IMG:delivery-sticker__',
      first:'__IMG:delivery-sticker__','take-four':'__IMG:delivery-sticker__','take-sixty':'__IMG:delivery-sticker__',
      'take-three':'__IMG:delivery-sticker__','take-eighty':'__IMG:delivery-sticker__'},
  },
  cues:[
    {...cues,goal:'aim-first',steps:['aim-first']},
    {...cues,goal:'aim-take-four',steps:['aim-take-four','aim-take-sixty']},
    {...cues,goal:'aim-take-three',steps:['aim-take-three','aim-take-eighty']},
  ],
  levels:[
    level(['first'],[[20,490],[30,640],[50,785]],449,0,141),
    level(['take-four','take-sixty'],[[4,460],[60,588],[64,709],[10,833]],462,3,119),
    level(['take-three','take-eighty'],[[70,460],[3,580],[7,699],[80,829]],477,5,119),
  ],
}));

function guide(id,box,pictureFor){
  const image=K.$(id);
  aim.follow(image,game=>{
    const {w,level}=game.data;
    const src=w&&pictureFor(w,level);
    image.style.visibility=src?'visible':'hidden';
    if (!src) return null;
    if (image.getAttribute('src')!==src) image.setAttribute('src',src);
    return box;
  });
}
guide('#current-order',{x:20,y:327,w:392,h:174},(w,l)=>orders[l.queue[Math.min(w.i,l.queue.length-1)]].picture);
guide('#confirmed-remainder',{x:1005,y:347,w:220,h:152},w=>icons[w.locked?.value]);
