K.ready({title:'沿摆片顺序走',sub:'看左边盘面。每次只挪一枚，找到下一张。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:two-disc-record__';},{once:true});
const values={A:11,B:20,C:13,D:22,F:31,G:40,H:41,I:32,J:23,K:14,L:5};
const icons={
  A:'__IMG:game-mat-11__',B:'__IMG:game-mat-20__',C:'__IMG:game-mat-13__',D:'__IMG:game-mat-22__',
  F:'__IMG:game-mat-31__',G:'__IMG:game-mat-40__',H:'__IMG:game-mat-41__',I:'__IMG:game-mat-32__',
  J:'__IMG:game-mat-23__',K:'__IMG:game-mat-14__',L:'__IMG:game-mat-5__',
};
function pictures(sources){
  return Object.fromEntries(Object.entries(sources).map(([key,src])=>{
    const image=new Image();image.src=src;return [key,image];
  }));
}
const boards=pictures({
  2:'__IMG:large-mat-2__',11:'__IMG:large-mat-11__',20:'__IMG:large-mat-20__',
  4:'__IMG:large-mat-4__',13:'__IMG:large-mat-13__',22:'__IMG:large-mat-22__',
  31:'__IMG:large-mat-31__',40:'__IMG:large-mat-40__',
  50:'__IMG:large-mat-50__',41:'__IMG:large-mat-41__',32:'__IMG:large-mat-32__',
  23:'__IMG:large-mat-23__',14:'__IMG:large-mat-14__',5:'__IMG:large-mat-5__',
});
const arrows=pictures({left:'__IMG:move-left__',right:'__IMG:move-right__',exit:'__IMG:maze-exit__'});
const hints=['想一想，只挪一枚以后两格各有几枚。','一边多一枚，另一边少一枚，总数不变。'];
const cue={hint:'maze-hint',hint2:'maze-help',praise:'maze-praise'};
function level(start,shift,map,route,step){
  return {start,shift,map,route,step,hints,listenOnly:true};
}
const options=K.gameTemplates.bubbleMaze({
  art:{icons},voiceLead:true,stepVoiceLead:true,
  cues:[
    {...cue,steps:['maze-two-left','maze-left-again','maze-exit']},
    {...cue,steps:['maze-four-left','maze-left-again','maze-left-again','maze-left-again','maze-exit']},
    {...cue,steps:['maze-five-right','maze-right-again','maze-right-again','maze-right-again','maze-right-again','maze-exit']},
  ],
  levels:[
    level(2,'left',['#########','#BSA...E#','##.#.##.#','#.......#','#########'],['A','B'],.31),
    level(4,'left',['###########','#DSCF....E#','#..##.##..#','#....G....#','#.........#','###########'],
      ['C','D','F','G'],.27),
    level(50,'right',['###########','#IS.H....E#','#.#.#.#.#.#','#J..K....L#','#.........#','###########'],
      ['H','I','J','K','L'],.25),
  ],doneText:'每次挪一枚，按顺序找齐了！',
});
function draw(context,image,x,y,w,h){
  if(image?.complete&&image.naturalWidth)context.drawImage(image,x,y,w,h);
}
options.drawTop=(game,context)=>{
  const {level,w}=game.data;
  if(!w)return;
  const progress=Math.min(w.i,level.route.length);
  const current=progress?values[level.route[progress-1]]:level.start;
  const previous=progress>1?values[level.route[progress-2]]:level.start;
  draw(context,boards[current],35,194,187,150);
  draw(context,arrows[level.shift],67,357,118,69);
  if(progress)draw(context,boards[previous],1048,194,188,150);
  const y=w.map.findIndex(row=>row.includes('E')),x=w.map[y].indexOf('E');
  const tile=(1280-2*w.ox)/w.map[0].length;
  draw(context,arrows.exit,w.ox+x*tile+9,w.oy+y*tile+6,49,54);
};
K.game(options);
K.$('[data-arc-input=right]').id='move-to-next-mat';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
