K.startPictureFallback=()=>{
  const image=K.el('img','pic');
  image.alt='三十八张书签添上五张';
  image.src='__IMG:depot-ready__';
  image.style.objectFit='contain';
  return image;
};
K.ready({title:'把书签送到总数柜',sub:'先合散件，再数整套和余张。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
const crate={
  '38-5':'__IMG:crate-38-5__',
  '47-6':'__IMG:crate-47-6__',
  '63-7':'__IMG:crate-63-7__',
  '35-8':'__IMG:crate-35-8__',
  '9-45':'__IMG:crate-9-45__',
  '7-58':'__IMG:crate-7-58__',
  '76-6':'__IMG:crate-76-6__',
  '84-7':'__IMG:crate-84-7__',
  '26-9':'__IMG:crate-26-9__',
};
const order={
  '38-5':'__IMG:order-38-5__',
  '47-6':'__IMG:order-47-6__',
  '63-7':'__IMG:order-63-7__',
  '35-8':'__IMG:order-35-8__',
  '9-45':'__IMG:order-9-45__',
  '7-58':'__IMG:order-7-58__',
  '76-6':'__IMG:order-76-6__',
  '84-7':'__IMG:order-84-7__',
  '26-9':'__IMG:order-26-9__',
};
const packed={
  '38-5':'__IMG:packed-38-5__',
  '47-6':'__IMG:packed-47-6__',
  '63-7':'__IMG:packed-63-7__',
  '35-8':'__IMG:packed-35-8__',
  '9-45':'__IMG:packed-9-45__',
  '7-58':'__IMG:packed-7-58__',
  '76-6':'__IMG:packed-76-6__',
  '84-7':'__IMG:packed-84-7__',
  '26-9':'__IMG:packed-26-9__',
};
const docks={
  35:'__IMG:dock-35__',43:'__IMG:dock-43__',53:'__IMG:dock-53__',54:'__IMG:dock-54__',
  65:'__IMG:dock-65__',70:'__IMG:dock-70__',82:'__IMG:dock-82__',91:'__IMG:dock-91__',
};
function pictures(sources){
  return Object.fromEntries(Object.entries(sources).map(([key,src])=>{
    const image=new Image();
    image.src=src;
    return [key,image];
  }));
}
const views=pictures(order),results=pictures(packed);
const parkedPreview=new WeakMap();
const orderBox={x:24,y:166,w:226,h:130};
const resultBox={x:1027,y:365,w:226,h:130};
const hints=['看一看，刚装的新套算进去了吗？','原套和新套各数一次，再数外面的余张。'];
const cue={hint:'docks-hint',hint2:'docks-help',praise:'docks-praise'};
const item=(x,y,a,b)=>({x,y,token:a+'-'+b,group:'dock-'+(a+b)});
const dock=(x,y,total)=>({x,y,group:'dock-'+total,sample:'dock-'+total});
const dockIcons=Object.fromEntries(Object.entries(docks).map(([total,src])=>['dock-'+total,src]));
const options=K.gameTemplates.sortingDepot({
  art:{backdrop:'__IMG:bookmark-workroom__',frames:['__IMG:bookmark-cart__','__IMG:bookmark-cart-push__'],
    sticker:'__IMG:bookmark-parcel-award__',icons:{...crate,...dockIcons}},voiceLead:true,
  cues:[{...cue,goal:'docks-two'},{...cue,goal:'docks-three'},{...cue,goal:'docks-four'}],
  levels:[
    {map:['########','#......#','#.S....#','#......#','#......#','########'],step:.34,hints,
      items:[item(3,2,38,5),item(5,3,47,6)],docks:[dock(3,4,43),dock(4,2,53)]},
    {map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.29,hints,
      items:[item(4,2,63,7),item(4,4,35,8),item(3,3,9,45)],docks:[dock(6,2,70),dock(7,4,43),dock(6,3,54)]},
    {map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.25,hints,
      items:[item(4,3,7,58),item(7,4,76,6),item(4,2,84,7),item(4,5,26,9)],
      docks:[dock(7,3,65),dock(8,4,82),dock(8,2,91),dock(7,5,35)]},
  ],
  doneText:'每箱书签都按实际总数送到了。',
});
function picture(context,image,box){
  if(image?.complete&&image.naturalWidth)context.drawImage(image,box.x,box.y,box.w,box.h);
}
options.drawTop=(game,context)=>{
  const {w,level}=game.data;
  if(!w)return;
  const {p,items}=w.state;
  const cols=level.map[0].length;
  const distance=i=>Math.abs(items[i]%cols-p%cols)+Math.abs(Math.floor(items[i]/cols)-Math.floor(p/cols));
  const nearest=items.flatMap((cell,i)=>cell>=0?[i]:[]).sort((a,b)=>distance(a)-distance(b))[0];
  // During the teacher's first delivery, keep its original order beside the result.
  const orderIndex=game.autoLoop?0:nearest;
  if(orderIndex!==undefined)picture(context,views[level.items[orderIndex].token],orderBox);
  const last=items.findIndex((cell,i)=>cell<0&&w.old.items[i]>=0);
  if(last>=0)parkedPreview.set(w,last);
  const completed=parkedPreview.get(w);
  if(completed!==undefined){
    if(items[completed]<0)picture(context,results[level.items[completed].token],resultBox);
    else parkedPreview.delete(w);
  }
};
const game=K.game(options);
game.follow('#depot-order',()=>orderBox);
game.follow('#first-total-dock',()=>({x:565,y:421,w:72,h:72}));
game.follow('#depot-result',()=>resultBox);
K.$('[data-arc-input=down]').id='push-bookmark-crate';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false){
    for(const element of K.$$('.teach-hl'))element.classList.remove('teach-hl');
  }
};

