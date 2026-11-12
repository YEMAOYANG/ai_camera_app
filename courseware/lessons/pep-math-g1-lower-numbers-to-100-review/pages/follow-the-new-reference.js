K.ready({title:'小蛇跟着新参照走', sub:'看右边参照，吃到满足大小条件的数牌。'});

const values={
  27:'__IMG:snake-27__',36:'__IMG:snake-36__',37:'__IMG:snake-37__',55:'__IMG:snake-55__',
  58:'__IMG:snake-58__',69:'__IMG:snake-69__',71:'__IMG:snake-71__',73:'__IMG:snake-73__',
  74:'__IMG:snake-74__',78:'__IMG:snake-78__',79:'__IMG:snake-79__',82:'__IMG:snake-82__',
  85:'__IMG:snake-85__',86:'__IMG:snake-86__',89:'__IMG:snake-89__',90:'__IMG:snake-90__',
  92:'__IMG:snake-92__',93:'__IMG:snake-93__',100:'__IMG:snake-100__',
};
const signs={gt:'__IMG:rule-gt__',lt:'__IMG:rule-lt__'};
const proofs={
  85:'__IMG:proof-58-85__',73:'__IMG:proof-37-73__',69:'__IMG:proof-73-69__',
  79:'__IMG:proof-82-79__',90:'__IMG:proof-79-90__',100:'__IMG:proof-90-100__',
};
const hints=['看看右边当前的参照，再听是找更大还是更小。','两位数先看十位；十位相同，再比较个位。'];
const cue={hint:'snake-hint',hint2:'snake-help',praise:'snake-praise'};
const level=(start,seconds,walls,rounds)=>({start,seconds,walls,rounds,hints});
const snake=K.game(K.gameTemplates.compareSnake({
  voiceLead:true,
  stepVoiceLead:true,
  doneText:'每次换参照，你都能再比一遍。',
  art:{
    backdrop:'__IMG:snake-backdrop__',
    frames:['__IMG:snake-head__','__IMG:snake-body__','__IMG:snake-tail__'],
    sticker:'__IMG:exhibit-sticker__',
    icons:values,
  },
  cues:[
    {...cue,steps:['snake-start']},
    {...cue,steps:['snake-up-from-37','snake-down-from-73']},
    {...cue,steps:['snake-down-from-82','snake-up-from-79','snake-up-from-90']},
  ],
  levels:[
    level(58,.79,[],[{relation:'gt',foods:[[5,4,85],[6,4,55]]}]),
    level(37,.70,[],[
      {relation:'gt',foods:[[7,3,73],[5,4,36],[3,3,27]]},
      {relation:'lt',foods:[[4,2,69],[7,2,74],[6,4,92]]},
    ]),
    level(82,.64,[[4,2],[7,2]],[
      {relation:'lt',foods:[[5,3,79],[5,4,86],[2,1,93]]},
      {relation:'gt',foods:[[3,3,90],[4,3,71],[6,3,78]]},
      {relation:'gt',foods:[[8,1,100],[8,3,89],[5,2,90]]},
    ]),
  ],
}));

const sign=K.$('#relation-rule');
const ref=K.$('#reference-amount');
const card=K.$('#current-reference-guide');
const proof=K.$('#last-accepted-number');
function updateImage(image,src) {
  if(src&&image.getAttribute('src')!==src)image.setAttribute('src',src);
}
snake.follow(card,current=>{
  const {w,level}=current.data;
  card.style.visibility=w?'visible':'hidden';
  if(!w)return null;
  const round=level.rounds[w.round];
  sign.hidden=!round;
  if(round)updateImage(sign,signs[round.relation]);
  updateImage(ref,values[w.ref]);
  return {x:1021,y:171,w:236,h:172};
});
snake.follow(proof,current=>{
  const w=current.data.w;
  const src=w&&w.round>0&&proofs[w.ref];
  proof.style.visibility=src?'visible':'hidden';
  if(!src)return null;
  updateImage(proof,src);
  return {x:1024,y:370,w:229,h:108};
});
snake.follow('#first-good-card',()=>({x:599,y:429,w:70,h:54}));
