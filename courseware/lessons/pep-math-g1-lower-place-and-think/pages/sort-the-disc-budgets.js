K.ready({title:'把盘面推回材料盒',sub:'数两格用的圆片。把盘面送到用片总数一样的盒。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:three-complete__';},{once:true});
const icons={
  12:'__IMG:game-mat-12__',22:'__IMG:game-mat-22__',31:'__IMG:game-mat-31__',32:'__IMG:game-mat-32__',
  33:'__IMG:game-mat-33__',21:'__IMG:game-mat-21__',41:'__IMG:game-mat-41__',42:'__IMG:game-mat-42__',51:'__IMG:game-mat-51__',
  'budget-3':'__IMG:budget-3__','budget-4':'__IMG:budget-4__','budget-5':'__IMG:budget-5__','budget-6':'__IMG:budget-6__',
};
const photos=Object.fromEntries(Object.entries({
  12:'__IMG:large-mat-12__',22:'__IMG:large-mat-22__',31:'__IMG:large-mat-31__',32:'__IMG:large-mat-32__',
  33:'__IMG:large-mat-33__',21:'__IMG:large-mat-21__',41:'__IMG:large-mat-41__',42:'__IMG:large-mat-42__',51:'__IMG:large-mat-51__',
}).map(([n,src])=>{
  const image=new Image();image.src=src;return [n,image];
}));
const trays=Object.fromEntries([3,4,5,6].map(n=>{
  const image=new Image();image.src=icons['budget-'+n];return [n,image];
}));
const parked=new WeakMap();
const hints=['两格一共用了几枚？再数一遍。','每个圆片都数一次，数完两格再选盒。'];
const cue={hint:'sort-hint',hint2:'sort-help',praise:'sort-praise'};
function item(x,y,tens,ones){return {x,y,tens,ones,token:10*tens+ones,group:tens+ones};}
function dock(x,y,group){return {x,y,group,sample:'budget-'+group};}
const options=K.gameTemplates.sortingDepot({
  art:{icons},voiceLead:true,
  cues:[{...cue,goal:'sort-first'},{...cue,goal:'sort-three'},{...cue,goal:'sort-repeat'}],
  levels:[
    {map:['########','#......#','#.S....#','#......#','#......#','########'],step:.34,hints,
      items:[item(3,2,1,2),item(5,3,2,2)],docks:[dock(3,4,3),dock(4,2,4)]},
    {map:['#########','#.......#','#..#....#','#.S.....#','#.......#','#########'],step:.29,hints,
      items:[item(4,2,3,1),item(4,4,3,2),item(3,3,3,3)],docks:[dock(6,2,4),dock(7,4,5),dock(6,3,6)]},
    {map:['##########','#........#','#..#.....#','#.S......#','#....#...#','#........#','##########'],step:.25,hints,
      items:[item(4,3,2,1),item(7,4,4,1),item(4,2,4,2),item(4,5,5,1)],
      docks:[dock(7,3,3),dock(8,4,5),dock(8,2,6),dock(7,5,6)]},
  ],doneText:'盘面上的圆片都送回对的盒了！',
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
  if(nearest!==undefined)draw(context,photos[level.items[nearest].token],19,164,226,181);
  const landed=items.findIndex((cell,i)=>cell<0&&w.old.items[i]>=0);
  if(landed>=0)parked.set(w,landed);
  const completed=parked.get(w);
  if(completed!==undefined&&items[completed]<0){
    const item=level.items[completed];
    draw(context,photos[item.token],1012,298,240,192);
    draw(context,trays[item.group],1066,496,130,92);
  }
};
K.game(options);
K.$('[data-arc-input=down]').id='push-disc-mat';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
