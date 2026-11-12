K.startPictureFallback=()=>{
  const picture=K.el('img','pic');
  picture.src='__IMG:exhibit-cover__';
  picture.alt='两个小小观察员在展桌上找线索';
  return picture;
};
K.ready({title:'把线索送到风景图',sub:'听线索，瞄准相符的图靶。'});
K.$('#ready .pic').style.objectFit='contain';

const clueBox={x:401,y:10,w:478,h:150};
const firstTarget={x:548,y:172,w:184,h:114};
const artwork={
  hall:'__IMG:hall__',guilin:'__IMG:guilin__',gorges:'__IMG:gorges__',
  taishan:'__IMG:taishan__',westlake:'__IMG:westlake__',potala:'__IMG:potala__',
};
const clues={
  'hall-ticket':'__IMG:marble-100__','guilin-ticket':'__IMG:marble-20__',
  'gorges-ticket':'__IMG:marble-10__','taishan-ticket':'__IMG:marble-5__',
  'westlake-ticket':'__IMG:marble-1__',
};
const clueImages=new Map(Object.entries(clues).map(([key,url])=>{
  const image=new Image();
  image.src=url;
  return [key,image];
}));
const pairs=Object.keys(artwork).map(key=>[key+'-ticket',key]);

function exhibitLevel(drift,speed,positions,queue){
  return {drift,speed,queue:queue.map(key=>key+'-ticket'),pairs,listenOnly:true,
    targetWidth:184,targetHeight:114,targets:positions.map(([x,value])=>({x,value})),
    hints:['再听线索，看哪张图有这个样子。','瞄准亮起来的图片，再发射。']};
}
const levels=[
  exhibitLevel(0,450,[[402,'westlake'],[640,'hall'],[878,'guilin']],['hall','guilin']),
  exhibitLevel(12,478,[[393,'gorges'],[637,'taishan'],[876,'guilin']],['gorges','taishan']),
  exhibitLevel(22,505,[[343,'taishan'],[538,'westlake'],[738,'potala'],[935,'hall']],['westlake','hall']),
];
const cues=[['find-hall','find-guilin'],['find-gorges','find-taishan'],['find-westlake','find-hall-again']];
const options=K.gameTemplates.magnetMarbles({
  levels,
  art:{backdrop:'__IMG:gallery-backdrop__',sticker:'__IMG:exhibit-sticker__',frames:['__IMG:leaf-marble__'],icons:artwork},
  cues:cues.map(steps=>({steps,hint:'marble-hint',hint2:'marble-help',praise:'marble-praise'})),
  voiceLead:true,stepVoiceLead:true,
  doneText:'你用图里的线索找对了地点！',
});
const drawGame=options.draw;
options.draw=(game,context)=>{
  drawGame(game,context);
  const level=levels[game.level],world=game.data.w;
  if(!world)return;
  const index=game.autoLoop?0:Math.min(world.i,level.queue.length-1);
  const picture=clueImages.get(level.queue[index]);
  const {x,y,w,h}=clueBox;
  if(picture?.complete&&picture.naturalWidth)context.drawImage(picture,x,y,w,h);
};
options.onState=(game,state)=>{
  if(state.demo===false)for(const node of K.$$('.teach-hl'))node.classList.remove('teach-hl');
};
const game=K.game(options);
game.follow('#marble-clue',()=>clueBox);
game.follow('#marble-first',()=>firstTarget);
