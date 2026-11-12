K.ready({title:'听号码送信',sub:'听数名，选珠图。再把信送到写着这个数的投递箱。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:board-63__';},{once:true});

const goods={
  'g-31':'__IMG:goods-31__','g-13':'__IMG:goods-13__','g-80':'__IMG:goods-80__',
  'g-83':'__IMG:goods-83__','g-8':'__IMG:goods-8__',
  'g-47':'__IMG:goods-47__','g-74':'__IMG:goods-74__','g-61':'__IMG:goods-61__',
};
const boxes={
  'b-31':'__IMG:box-31__','b-13':'__IMG:box-13__','b-80':'__IMG:box-80__',
  'b-83':'__IMG:box-83__','b-8':'__IMG:box-8__',
  'b-47':'__IMG:box-47__','b-74':'__IMG:box-74__','b-61':'__IMG:box-61__',
};
const marks=Object.fromEntries(Object.entries({...goods,...boxes}).map(([key,src])=>{
  const img=new Image();
  img.src=src;
  return [key,img];
}));
const ear=new Image();
ear.src='__IMG:listen-symbol__';
const hints=['重新对一对听到的两位数。','先数左边有几个十，再数右边有几个一。'];
const cue={hint:'delivery-hint',hint2:'delivery-help',praise:'delivery-praise'};
function level(step,pickup,drop,amounts,lanes){
  return {step,hints,lanes,pickup:pickup.map(([n,col])=>['g-'+n,col]),
    drop:drop.map(([n,col])=>['b-'+n,col]),orders:amounts.map(n=>['g-'+n,'b-'+n])};
}
const options=K.gameTemplates.listenDelivery({
  art:{backdrop:'__IMG:delivery-street__',frames:['__IMG:carrier-stand__','__IMG:carrier-lift__','__IMG:passing-cart__'],
    sticker:'__IMG:postal-rosette__',icons:{...goods,...boxes}},
  voiceLead:true,stepVoiceLead:true,
  cues:[
    {...cue,steps:['delivery-31-pick','delivery-31-box']},
    {...cue,steps:['delivery-80-pick','delivery-80-box','delivery-83-pick','delivery-83-box']},
    {...cue,steps:['delivery-47-pick','delivery-47-box','delivery-74-pick','delivery-74-box','delivery-61-pick','delivery-61-box']},
  ],
  levels:[
    level(.34,[[13,4],[31,5]],[[31,5],[13,3]],[31],
      [{row:2,speed:.85,phase:1.8,spacing:5.2}]),
    level(.30,[[83,2],[80,6],[8,4]],[[80,2],[8,6],[83,4]],[80,83],
      [{row:2,speed:1.1,phase:1.1,spacing:4.8},{row:3,speed:-.78,phase:2.8,spacing:5.5}]),
    level(.27,[[74,3],[61,6],[47,2]],[[47,7],[74,3],[61,5]],[47,74,61],
      [{row:1,speed:1.14,phase:2.1,spacing:5.1},{row:3,speed:-1.22,phase:3.3,spacing:5.4}]),
  ],doneText:'听到的数、珠图和号箱都对上了！',
});
options.drawTop=(game,context)=>{
  const {w,level}=game.data;
  if(!w)return;
  if(w.order<level.orders.length&&ear.complete&&ear.naturalWidth)context.drawImage(ear,36,208,172,142);
  const station=w.row===4?w.goods:w.row===0?w.recipients:null;
  const parked=station&&[...station].find(([,col])=>col===w.col);
  const preview=parked&&marks[parked[0]];
  if(preview?.complete&&preview.naturalWidth)context.drawImage(preview,36,365,172,172);
  const previous=level.orders[w.order-1];
  if(previous&&w.delivered.get(previous[1])===previous[0]){
    const image=marks[previous[1]];
    if(image?.complete&&image.naturalWidth)context.drawImage(image,1072,362,136,136);
  }
};
K.game(options);
K.$('[data-arc-input=action]').id='pick-or-deliver';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
