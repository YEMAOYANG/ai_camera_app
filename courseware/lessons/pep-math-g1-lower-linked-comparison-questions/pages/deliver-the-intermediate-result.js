K.ready({title:'把第一问的数送去接第二问',sub:'拿第一问的数 → 送到第二问的站'});
K.$('#ready .pic').style.objectFit='contain';

const clueBox={x:409,y:4,w:462,h:128};
const firstParcel={x:602,y:497,w:76,h:78};
const loadBox={x:1082,y:219,w:116,h:116};
const clues=['__IMG:delivery-clue-1__','__IMG:delivery-clue-2__','__IMG:delivery-clue-3__'].map(source=>{
  const image=new Image();
  image.src=source;
  return image;
});
const icons={
  'parcel-2':'__IMG:parcel-2__','parcel-7':'__IMG:parcel-7__','parcel-9':'__IMG:parcel-9__',
  'parcel-10':'__IMG:parcel-10__','parcel-12':'__IMG:parcel-12__','parcel-16':'__IMG:parcel-16__',
  'parcel-19':'__IMG:parcel-19__','parcel-23':'__IMG:parcel-23__','parcel-25':'__IMG:parcel-25__',
  'parcel-29':'__IMG:parcel-29__','parcel-34':'__IMG:parcel-34__',
  'station-12':'__IMG:station-12__','station-16':'__IMG:station-16__','station-19':'__IMG:station-19__',
  'station-22':'__IMG:station-22__','station-23':'__IMG:station-23__','station-25':'__IMG:station-25__',
  'station-34':'__IMG:station-34__','station-39':'__IMG:station-39__',
};
function stops(kind,entries){return entries.map(([number,col])=>[kind+'-'+number,col]);}
function lessonLevel(pickup,drop,[first,second],lanes,step){
  return {pickup:stops('parcel',pickup),drop:stops('station',drop),
    orders:[['parcel-'+first,'station-'+second]],lanes,step,
    hints:['先听清这一步求什么，再找对应的数。','停在亮着的一格，再按包裹键。']};
}
const levels=[
  lessonLevel([[2,1],[10,4],[12,7]],[[12,1],[22,4],[16,7]],[10,22],
    [{row:2,speed:.9,spacing:5.7,phase:0}],.33),
  lessonLevel([[7,1],[16,3],[23,6],[29,8]],[[23,1],[16,3],[39,5],[34,7]],[23,39],
    [{row:1,speed:-1.15,spacing:4.8,phase:2},{row:3,speed:1.2,spacing:5.2,phase:1}],.29),
  lessonLevel([[9,1],[19,3],[34,5],[25,7]],[[25,1],[19,3],[34,7]],[25,19],
    [{row:1,speed:-1.55,spacing:4.3,phase:.7},{row:2,speed:1.45,spacing:4.5,phase:2.2},
      {row:3,speed:-1.4,spacing:4.4,phase:1.4}],.24),
];
const cueSteps=[['pick-one','drop-one'],['pick-two','drop-two'],['pick-three','drop-three']];
const options=K.gameTemplates.listenDelivery({
  levels,
  art:{backdrop:'__IMG:patrol-delivery-landscape__',sticker:'__IMG:patrol-sticker__',
    frames:['__IMG:cart-ready__','__IMG:cart-loaded__','__IMG:maintenance-truck__'],icons},
  cues:cueSteps.map(steps=>({steps,hint:'delivery-hint',hint2:'delivery-help',praise:'delivery-praise'})),
  voiceLead:true,
  stepVoiceLead:true,
  doneText:'第一问的数已送到第二问！',
});
const drawGame=options.draw;
options.draw=(game,context)=>{
  drawGame(game,context);
  const image=clues[game.level];
  const {x,y,w,h}=clueBox;
  if(image?.complete&&image.naturalWidth)context.drawImage(image,x,y,w,h);
};
const game=K.game(options);
game.follow('#delivery-problem',()=>clueBox);
game.follow('#delivery-first',()=>firstParcel);
game.follow('#delivery-load',()=>loadBox);
