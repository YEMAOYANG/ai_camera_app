K.ready({title:'把题图推到答案格',sub:'先找相关的量，算出结果，再推入同样数量的格。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:bookmark-missing__';},{once:true});

const problems={
  'part-5':'__IMG:crate-part-5__','part-7':'__IMG:crate-part-7__','plus-6':'__IMG:crate-plus-6__',
  'minus-14':'__IMG:crate-minus-14__','needed-9':'__IMG:crate-needed-9__','compare-7':'__IMG:crate-compare-7__',
  'steps-5':'__IMG:crate-steps-5__',
};
const amounts={5:'__IMG:depot-amount-5__',6:'__IMG:depot-amount-6__',7:'__IMG:depot-amount-7__',
  9:'__IMG:depot-amount-9__',14:'__IMG:depot-amount-14__'};
function pictures(sources){
  return Object.fromEntries(Object.entries(sources).map(([key,src])=>{
    const image=new Image();image.src=src;return [key,image];
  }));
}
const cards=pictures(problems),results=pictures(amounts);
const hints=['先找问题要的是哪一份量。','再看图里有用的两个量，或者用加法检查。'];
const cue={hint:'push-hint',hint2:'push-help',praise:'push-praise'};
function item(x,y,token,group){return {x,y,token,group};}
function dock(x,y,group){return {x,y,group,sample:group};}
const options=K.gameTemplates.sortingDepot({
  art:{backdrop:'__IMG:depot-desk__',frames:['__IMG:trolley-idle__','__IMG:trolley-push__'],sticker:'__IMG:exhibit-rosette__',
    icons:{...problems,...amounts}},voiceLead:true,
  cues:[{...cue,goal:'push-part'},{...cue,goal:'push-hidden'},{...cue,goal:'push-relevant'}],
  levels:[
    {map:['########','#......#','#.S....#','#......#','#......#','########'],step:.34,hints,
      items:[item(3,2,'part-5',5),item(5,3,'part-7',7)],docks:[dock(3,4,5),dock(4,2,7)]},
    {map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.29,hints,
      items:[item(4,2,'minus-14',14),item(3,3,'plus-6',6)],docks:[dock(6,2,14),dock(6,3,6)]},
    {map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.25,hints,
      items:[item(4,3,'needed-9',9),item(7,4,'compare-7',7),item(4,5,'steps-5',5)],
      docks:[dock(7,3,9),dock(8,4,7),dock(7,5,5)]},
  ],doneText:'每张图的所求量都找对了！',
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
  const {w,level}=game.data;
  if(!w)return;
  const {p,items}=w.state;
  const cols=level.map[0].length;
  const distance=index=>Math.abs(items[index]%cols-p%cols)+Math.abs(Math.floor(items[index]/cols)-Math.floor(p/cols));
  const unparked=items.flatMap((cell,i)=>cell>=0?[i]:[]).sort((a,b)=>distance(a)-distance(b));
  const parked=items.findLastIndex(cell=>cell<0);
  if((!game.auto||game.state==='play')&&unparked.length)panel(context,cards[level.items[unparked[0]].token],40,163,190,150);
  if(parked>=0)panel(context,results[level.items[parked].group],1054,355,176,151);
};
K.game(options);
K.$('[data-arc-input=down]').id='push-down-to-result';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
