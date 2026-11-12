K.ready({title:'把余下的灯配到一起',sub:'看从十格里送走九盏后还剩多少，再移动落块。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:fourteen-before__';},{once:true});

const sources={
  'n-11':'__IMG:tile-state-11__','n-12':'__IMG:tile-state-12__','n-13':'__IMG:tile-state-13__',
  'n-14':'__IMG:tile-state-14__','n-15':'__IMG:tile-state-15__',
  'r-2':'__IMG:tile-left-2__','r-3':'__IMG:tile-left-3__','r-4':'__IMG:tile-left-4__',
  'r-5':'__IMG:tile-left-5__','r-6':'__IMG:tile-left-6__',
};
const views=Object.fromEntries(Object.entries(sources).map(([key,src])=>{
  const image=new Image();image.src=src;return [key,image];
}));
const remainder=key=>'r-'+(Number(key.slice(2))-9);
const pairs=Object.keys(sources).filter(key=>key.startsWith('n-')).map(key=>[key,remainder(key)]);
const hints=['先看十格里还剩几盏。','把十格里留下的和散灯合在一起。'];
const cue={hint:'tiles-hint',hint2:'tiles-help',praise:'tiles-praise'};
const options=K.gameTemplates.fallingTiles({
  art:{backdrop:'__IMG:lantern-workbench__',sticker:'__IMG:paper-spark__',icons:sources},
  voiceLead:true,cues:[{...cue,goal:'tiles-first'},{...cue,goal:'tiles-second'},{...cue,goal:'tiles-third'}],
  levels:[
    {bottom:['r-2',null,null,'r-4',null,null],pieces:['n-11','n-13'],interval:2.4,pairs,hints,symbol:'−9'},
    {bottom:[null,'r-6',null,'r-3',null,null],pieces:['n-12','n-15'],interval:2.1,pairs,hints,symbol:'−9'},
    {bottom:['r-5',null,'r-2',null,'r-6',null],pieces:['n-15','n-14','n-11'],interval:1.78,pairs,hints,symbol:'−9'},
  ],doneText:'每张余量图都和送走九盏后的图配对了！',
});
function panel(context,key,x,y,width,height){
  const image=views[key];
  if(!image?.complete||!image.naturalWidth)return;
  context.fillStyle='#2e5343';
  K.draw.rr(context,x,y,width,height,14);context.fill();
  const scale=Math.min((width-12)/image.naturalWidth,(height-12)/image.naturalHeight);
  const w=image.naturalWidth*scale,h=image.naturalHeight*scale;
  context.drawImage(image,x+(width-w)/2,y+(height-h)/2,w,h);
}
options.drawTop=(game,context)=>{
  const {level,progress}=game.data;
  if(!level)return;
  if(!game.auto||game.state==='play')panel(context,level.pieces[progress],45,222,169,156);
  if(progress)panel(context,remainder(level.pieces[progress-1]),1078,419,157,142);
};
K.game(options);
K.$('[data-arc-input=action]').id='drop-lamp-tile';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
