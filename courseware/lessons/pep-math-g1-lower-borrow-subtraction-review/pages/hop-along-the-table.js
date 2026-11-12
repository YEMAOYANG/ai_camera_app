K.ready({title:'按减法表的规律跳',sub:'看方向和起点，只踩下一张符合规律的算式。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:table-all-45__';},{once:true});

const icons={
  '12-8':'__IMG:hop-12-8__','13-8':'__IMG:hop-13-8__','14-8':'__IMG:hop-14-8__','15-8':'__IMG:hop-15-8__',
  '13-7':'__IMG:hop-13-7__','14-9':'__IMG:hop-14-9__','15-9':'__IMG:hop-15-9__','15-7':'__IMG:hop-15-7__',
  '15-6':'__IMG:hop-15-6__','16-7':'__IMG:hop-16-7__','11-2':'__IMG:hop-11-2__','12-3':'__IMG:hop-12-3__',
  '13-4':'__IMG:hop-13-4__','14-5':'__IMG:hop-14-5__','12-4':'__IMG:hop-12-4__','14-7':'__IMG:hop-14-7__',
};
const symbols={column:'__IMG:rule-column__',row:'__IMG:rule-row__','same-difference':'__IMG:rule-same-difference__'};
const outcomes={
  '13-8':'__IMG:hop-proof-13-8__','14-8':'__IMG:hop-proof-14-8__','15-8':'__IMG:hop-proof-15-8__',
  '15-7':'__IMG:hop-proof-15-7__','15-6':'__IMG:hop-proof-15-6__','12-3':'__IMG:hop-proof-12-3__',
  '13-4':'__IMG:hop-proof-13-4__','14-5':'__IMG:hop-proof-14-5__',
};
function pictures(sources){
  return Object.fromEntries(Object.entries(sources).map(([key,src])=>{
    const image=new Image();image.src=src;return [key,image];
  }));
}
const directions=pictures(symbols),done=pictures(outcomes);
const hints=['先想这条路的规律。','沿小图的箭头走，看两个数怎样变。'];
const cue={hint:'hop-hint',hint2:'hop-help',praise:'hop-praise'};
function level(mode,startLabel,route,decoys,speed){
  return {mode,startLabel,route,speed,prompt:null,hints,
    platforms:[[71,490,129,'start'],[185,370,85,decoys[0]],[257,474,111,route[0]],
      [448,462,111,route[1]],[544,358,86,decoys[1]],[643,485,111,route[2]]],
  };
}
const options=K.gameTemplates.platformHop({
  art:{backdrop:'__IMG:garden-hops__',frames:['__IMG:explorer-stand__','__IMG:explorer-walk__','__IMG:explorer-jump__'],
    sticker:'__IMG:exhibit-rosette__',icons},voiceLead:true,
  cues:[{...cue,goal:'hop-column'},{...cue,goal:'hop-row'},{...cue,goal:'hop-diagonal'}],
  levels:[
    level('column','12-8',['13-8','14-8','15-8'],['13-7','14-9'],280),
    level('row','15-9',['15-8','15-7','15-6'],['14-8','16-7'],288),
    level('same-difference','11-2',['12-3','13-4','14-5'],['12-4','14-7'],296),
  ],doneText:'横、纵、斜三条算式路都走通了！',
});
function panel(context,image,x,y,width,height){
  if(!image?.complete||!image.naturalWidth)return;
  context.fillStyle='#2c5140';
  K.draw.rr(context,x,y,width,height,14);context.fill();
  const scale=Math.min((width-12)/image.naturalWidth,(height-12)/image.naturalHeight);
  const w=image.naturalWidth*scale,h=image.naturalHeight*scale;
  context.drawImage(image,x+(width-w)/2,y+(height-h)/2,w,h);
}
options.drawTop=(game,context)=>{
  const {level,progress}=game.data;
  if(!level)return;
  panel(context,directions[level.mode],54,145,160,150);
  if(progress)panel(context,done[level.route[progress-1]],1047,355,180,154);
};
K.game(options);
K.$('[data-arc-input=action]').id='jump-to-card';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
