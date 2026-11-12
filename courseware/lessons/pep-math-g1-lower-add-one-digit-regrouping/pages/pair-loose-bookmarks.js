K.startPictureFallback=()=>{
  const image=K.el('img','pic');
  image.alt='五张和六张书签合成十一张';
  image.src='__IMG:tiles-ready__';
  image.style.objectFit='contain';
  return image;
};
K.ready({title:'给落下的散书签找搭档',sub:'先数两堆散书签，合到目标数量再落下。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
const icons={
  'old-5':'__IMG:tile-old-5__','old-7':'__IMG:tile-old-7__','old-8':'__IMG:tile-old-8__','old-9':'__IMG:tile-old-9__',
  'new-3':'__IMG:tile-new-3__','new-4':'__IMG:tile-new-4__','new-5':'__IMG:tile-new-5__',
  'new-6':'__IMG:tile-new-6__','new-7':'__IMG:tile-new-7__','new-8':'__IMG:tile-new-8__','new-9':'__IMG:tile-new-9__',
};
const proofSources={
  '5-6':'__IMG:tile-proof-5-6__','8-3':'__IMG:tile-proof-8-3__','7-6':'__IMG:tile-proof-7-6__','9-4':'__IMG:tile-proof-9-4__',
  '8-5':'__IMG:tile-proof-8-5__','9-7':'__IMG:tile-proof-9-7__','8-8':'__IMG:tile-proof-8-8__','7-9':'__IMG:tile-proof-7-9__',
};
const proof=Object.fromEntries(Object.entries(proofSources).map(([key,src])=>{
  const image=new Image();
  image.src=src;
  return [key,image];
}));
const resultBox={x:1010,y:402,w:239,h:110};
const count=token=>Number(token.split('-')[1]);
const hints=['看清落下的一堆，再数旁边的旧散张。','两堆合到目标数量，才挨着落下。'];
const cue={hint:'tiles-hint',hint2:'tiles-help',praise:'tiles-praise'};
function level(bottom,pieces,total,interval){
  return {
    bottom:bottom.map(n=>n===null?null:'old-'+n),pieces:pieces.map(n=>'new-'+n),
    total,interval,hints,
    matches:(next,old)=>next.startsWith('new-')&&old.startsWith('old-')&&count(next)+count(old)===total,
  };
}
const options=K.gameTemplates.fallingTiles({
  art:{backdrop:'__IMG:bookmark-worktable__',sticker:'__IMG:bookmark-award__',icons},voiceLead:true,
  cues:[{...cue,goal:'tiles-eleven'},{...cue,goal:'tiles-thirteen'},{...cue,goal:'tiles-sixteen'}],
  levels:[
    level([5,null,8,null,7,null],[6,3],11,2.4),
    level([null,7,null,9,null,8],[6,4,5],13,2.08),
    level([9,null,8,null,7,null],[7,8,9],16,1.78),
  ],
  doneText:'配好的散件每次换出一套，余张也留好了。',
});
options.drawTop=(game,context)=>{
  const {level,progress}=game.data;
  if(!level||!progress)return;
  const added=count(level.pieces[progress-1]);
  const image=proof[(level.total-added)+'-'+added];
  if(image?.complete&&image.naturalWidth)context.drawImage(image,resultBox.x,resultBox.y,resultBox.w,resultBox.h);
};
const game=K.game(options);
game.follow('#first-old-loose',()=>({x:430,y:526,w:70,h:70}));
game.follow('#loose-target-total',()=>({x:906,y:166,w:168,h:140}));
game.follow('#tile-result',()=>resultBox);
K.$('[data-arc-input=action]').id='drop-bookmark-tile';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false){
    for(const element of K.$$('.teach-hl'))element.classList.remove('teach-hl');
  }
};

