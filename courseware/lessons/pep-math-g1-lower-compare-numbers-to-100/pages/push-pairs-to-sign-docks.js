K.ready({title:'把双数牌推到符号柜',sub:'先读左边，再读右边，选中间该放的符号。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:grouped-51-47__';},{once:true});
const pairs={
  '32-45':'__IMG:crate-32-45__','70-68':'__IMG:crate-70-68__','84-84':'__IMG:crate-84-84__',
  '21-12':'__IMG:crate-21-12__','55-56':'__IMG:crate-55-56__','66-66':'__IMG:crate-66-66__',
  '98-92':'__IMG:crate-98-92__','38-43':'__IMG:crate-38-43__','89-93':'__IMG:crate-89-93__',
};
const views={
  '32-45':'__IMG:depot-view-32-45__','70-68':'__IMG:depot-view-70-68__','84-84':'__IMG:depot-view-84-84__',
  '21-12':'__IMG:depot-view-21-12__','55-56':'__IMG:depot-view-55-56__','66-66':'__IMG:depot-view-66-66__',
  '98-92':'__IMG:depot-view-98-92__','38-43':'__IMG:depot-view-38-43__','89-93':'__IMG:depot-view-89-93__',
};
const proof={
  '32-45':'__IMG:depot-proof-32-45__','70-68':'__IMG:depot-proof-70-68__','84-84':'__IMG:depot-proof-84-84__',
  '21-12':'__IMG:depot-proof-21-12__','55-56':'__IMG:depot-proof-55-56__','66-66':'__IMG:depot-proof-66-66__',
  '98-92':'__IMG:depot-proof-98-92__','38-43':'__IMG:depot-proof-38-43__','89-93':'__IMG:depot-proof-89-93__',
};
function pictures(sources){
  return Object.fromEntries(Object.entries(sources).map(([key,src])=>{
    const image=new Image();image.src=src;return [key,image];
  }));
}
const enlarged=pictures(views),results=pictures(proof);
const parkedPreview=new WeakMap();
const signs={gt:'__IMG:sign-gt__',lt:'__IMG:sign-lt__',eq:'__IMG:sign-eq__'};
const hints=['读一读，左边和右边各是多少？','先比十位，再决定要不要比个位。'];
const cue={hint:'depot-hint',hint2:'depot-help',praise:'depot-praise'};
function item(x,y,left,right){
  return {x,y,left,right,token:left+'-'+right,group:left===right?'eq':left>right?'gt':'lt'};
}
function dock(x,y,group){return {x,y,group,sample:group};}
const options=K.gameTemplates.sortingDepot({
  art:{icons:{...pairs,...signs}},voiceLead:true,
  cues:[{...cue,goal:'depot-two'},{...cue,goal:'depot-three'},{...cue,goal:'depot-four'}],
  levels:[
    {map:['########','#......#','#.S....#','#......#','#......#','########'],step:.34,hints,
      items:[item(3,2,32,45),item(5,3,70,68)],docks:[dock(3,4,'lt'),dock(4,2,'gt')]},
    {map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.29,hints,
      items:[item(4,2,84,84),item(4,4,21,12),item(3,3,55,56)],
      docks:[dock(6,2,'eq'),dock(7,4,'gt'),dock(6,3,'lt')]},
    {map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.25,hints,
      items:[item(4,3,66,66),item(7,4,98,92),item(4,2,38,43),item(4,5,89,93)],
      docks:[dock(7,3,'eq'),dock(8,4,'gt'),dock(8,2,'lt'),dock(7,5,'lt')]},
  ],doneText:'每一对牌都按左右顺序找到了正确符号！',
});
function draw(context,image,x,y,w,h){
  if(image?.complete&&image.naturalWidth)context.drawImage(image,x,y,w,h);
}
options.drawTop=(game,context)=>{
  const {w,level}=game.data;
  if(!w)return;
  const {p,items}=w.state;
  const cols=level.map[0].length;
  const distance=i=>Math.abs(items[i]%cols-p%cols)+Math.abs(Math.floor(items[i]/cols)-Math.floor(p/cols));
  const nearest=items.flatMap((cell,i)=>cell>=0?[i]:[]).sort((a,b)=>distance(a)-distance(b))[0];
  if(nearest!==undefined)draw(context,enlarged[level.items[nearest].token],23,177,224,151);
  const last=items.findIndex((cell,i)=>cell<0&&w.old.items[i]>=0);
  if(last>=0)parkedPreview.set(w,last);
  const completed=parkedPreview.get(w);
  if(completed!==undefined&&items[completed]<0)draw(context,results[level.items[completed].token],1026,337,224,113);
};
K.game(options);
K.$('[data-arc-input=down]').id='push-toward-dock';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
