K.ready({title:'瞄准拿走以后留下的杯', sub:'先拆一盒，确认拿走多少，再瞄准真正留下的数量。'});

const orders={
  first:{whole:51,take:6,art:'__IMG:order-51-minus6__'},
  'fifty-two':{whole:52,take:6,art:'__IMG:order-52-minus6__'},
  'sixty-five':{whole:65,take:9,art:'__IMG:order-65-minus9__'},
  seventy:{whole:70,take:4,art:'__IMG:order-70-minus4__'},
  'eighty-four':{whole:84,take:8,art:'__IMG:order-84-minus8__'},
};
const numbers={
  5:'__IMG:answer-5__',6:'__IMG:answer-6__',45:'__IMG:answer-45__',46:'__IMG:answer-46__',
  50:'__IMG:answer-50__',55:'__IMG:answer-55__',56:'__IMG:answer-56__',66:'__IMG:answer-66__',
  76:'__IMG:answer-76__',86:'__IMG:answer-86__',
};
const hints=['先找真正拿走的散杯，再看剩下多少。','核对拆了一盒以后，整盒还有几盒，散杯还剩几个。'];
const cues={hint:'aim-hint',hint2:'aim-help',praise:'aim-praise'};
const room=(queue,targets,speed,drift,targetWidth)=>({
  queue,targets:targets.map(([value,x])=>({value,x})),speed,drift,targetWidth,targetHeight:113,
  matches(key,value){
    const order=orders[key];
    return order!==undefined&&order.whole-order.take===value;
  },
  symbol:'cup',hints,
});
const game=K.game(K.gameTemplates.magnetMarbles({
  voiceLead:true,
  stepVoiceLead:true,
  doneText:'拆盒时杯子总量不变，借走以后才少了。',
  art:{backdrop:'__IMG:aim-backdrop__',frames:['__IMG:cup-marble__'],sticker:'__IMG:cup-aim-award__',
    icons:{...numbers,cup:'__IMG:cup-aim-award__',first:'__IMG:cup-aim-award__',
      'fifty-two':'__IMG:cup-aim-award__','sixty-five':'__IMG:cup-aim-award__',
      seventy:'__IMG:cup-aim-award__','eighty-four':'__IMG:cup-aim-award__'}},
  cues:[
    {...cues,steps:['aim-first']},
    {...cues,steps:['aim-fifty-two','aim-sixty-five']},
    {...cues,steps:['aim-seventy','aim-eighty-four']},
  ],
  levels:[
    room(['first'],[[5,490],[55,640],[45,785]],450,0,142),
    room(['fifty-two','sixty-five'],[[46,460],[56,588],[6,709],[50,833]],466,3,118),
    room(['seventy','eighty-four'],[[66,460],[76,588],[6,709],[86,833]],478,5,118),
  ],
}));

function followArt(selector,box,lookup) {
  const img=K.$(selector);
  game.follow(img,current=>{
    const {w,level}=current.data;
    const src=w&&lookup(w,level);
    img.style.visibility=src?'visible':'hidden';
    if(!src)return null;
    if(img.getAttribute('src')!==src)img.setAttribute('src',src);
    return box;
  });
}
followArt('#active-removal',{x:21,y:326,w:395,h:171},(w,l)=>orders[l.queue[Math.min(w.i,l.queue.length-1)]].art);
followArt('#accepted-remainder',{x:1003,y:345,w:219,h:151},w=>numbers[w.locked?.value]);
