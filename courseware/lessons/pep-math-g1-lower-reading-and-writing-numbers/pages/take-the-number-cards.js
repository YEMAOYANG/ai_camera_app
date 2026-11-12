K.ready({title:'取两张数卡',sub:'看计数器，先拿十位，再拿个位。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:board-42__';},{once:true});

const digits={
  0:'__IMG:digit-0__',2:'__IMG:digit-2__',3:'__IMG:digit-3__',
  4:'__IMG:digit-4__',6:'__IMG:digit-6__',7:'__IMG:digit-7__',
};
const tokenDigits={'3':3,'4':4,A:7,B:0,C:7,D:2,F:4,G:6,H:6,I:4};
const icons=Object.fromEntries(Object.entries(tokenDigits).map(([symbol,digit])=>[symbol,digits[digit]]));
const numbers={
  34:'__IMG:maze-34__',70:'__IMG:maze-70__',72:'__IMG:maze-72__',
  46:'__IMG:maze-46__',64:'__IMG:maze-64__',
};
const slot='__IMG:two-empty-places__';
function loadPictures(sources){
  return Object.fromEntries(Object.entries(sources).map(([key,src])=>{
    const img=new Image();
    img.src=src;
    return [key,img];
  }));
}
const rodPictures=loadPictures(numbers),digitPictures=loadPictures(digits),{slotPicture}=loadPictures({slotPicture:slot});
const gate=new Image();
gate.src='__IMG:postal-arch__';
const hints=['先看该取哪一位，再数那一边。','十位在左，个位在右；没有散卡就取零。'];
const cue={hint:'maze-hint',hint2:'maze-help',praise:'maze-praise'};
function level(map,route,amounts,step){
  return {map,route,amounts,step,hints,listenOnly:true,labels:tokenDigits};
}
const options=K.gameTemplates.bubbleMaze({
  art:{backdrop:'__IMG:maze-garden__',frames:['__IMG:maze-car__','__IMG:carrier-lift__'],
    sticker:'__IMG:postal-rosette__',icons},
  voiceLead:true,stepVoiceLead:true,
  cues:[
    {...cue,steps:['maze-34-tens','maze-34-ones','maze-exit']},
    {...cue,steps:['maze-70-tens','maze-70-ones','maze-72-tens','maze-72-ones','maze-exit']},
    {...cue,steps:['maze-46-tens','maze-46-ones','maze-64-tens','maze-64-ones','maze-exit']},
  ],
  levels:[
    level(['#########','#4S3...E#','##.#.##.#','#.......#','#########'],['3','4'],[34],.31),
    level(['###########','#BSAC....E#','#..##.##..#','#....D....#','#.........#','###########'],
      ['A','B','C','D'],[70,72],.27),
    level(['###########','#GS.F.#..E#','#.#.#.#.#.#','#I..H.....#','#..##..#..#','###########'],
      ['F','G','H','I'],[46,64],.24),
  ],doneText:'十位、个位按顺序写好了！',
});
function picture(context,img,x,y,width,height){
  if(img?.complete&&img.naturalWidth)context.drawImage(img,x,y,width,height);
}
options.drawTop=(game,context)=>{
  const {level,w}=game.data;
  if(!w)return;
  const y=w.map.findIndex(row=>row.includes('E'));
  const x=w.map[y].indexOf('E');
  const tile=(1280-2*w.ox)/w.map[0].length;
  picture(context,gate,w.ox+x*tile+9,w.oy+y*tile+5,49,55);
  const finished=w.i>=level.route.length;
  const pair=Math.min(Math.floor(w.i/2),level.amounts.length-1);
  const count=finished?2:w.i%2;
  picture(context,rodPictures[level.amounts[pair]],44,198,162,190);
  picture(context,slotPicture,1056,237,174,103);
  if(pair>0){
    picture(context,slotPicture,1056,365,174,103);
    for(let place=0;place<2;place++){
      const previous=tokenDigits[level.route[2*(pair-1)+place]];
      picture(context,digitPictures[previous],1069+82*place,399,61,61);
    }
  }
  for(let place=0;place<count;place++){
    const digit=tokenDigits[level.route[2*pair+place]];
    picture(context,digitPictures[digit],1069+82*place,271,61,61);
  }
  if(!finished){
    context.save();
    context.strokeStyle='#b24626';
    context.lineWidth=5;
    K.draw.rr(context,1059+82*count,244,83,89,9);
    context.stroke();
    context.restore();
  }
};
K.game(options);
K.$('[data-arc-input=right]').id='move-to-tens';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
