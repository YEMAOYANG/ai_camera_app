K.ready({title:'送补灯，验总数',sub:'看总量，选能与九合起来的那包灯，再过车道送到对应货台。'});
const opening=K.$('#ready .pic');
opening.style.objectFit='contain';
opening.addEventListener('error',()=>{opening.src='__IMG:join-fourteen__';},{once:true});

const goods={
  'r-2':'__IMG:tile-left-2__','r-3':'__IMG:tile-left-3__','r-4':'__IMG:tile-left-4__',
  'r-5':'__IMG:tile-left-5__','r-6':'__IMG:tile-left-6__',
};
const totals={
  't-11':'__IMG:delivery-total-11__','t-12':'__IMG:delivery-total-12__','t-13':'__IMG:delivery-total-13__',
  't-14':'__IMG:delivery-total-14__','t-15':'__IMG:delivery-total-15__',
};
const jobSources={
  't-11':'__IMG:delivery-job-11__','t-12':'__IMG:delivery-job-12__','t-13':'__IMG:delivery-job-13__',
  't-14':'__IMG:delivery-job-14__','t-15':'__IMG:delivery-job-15__',
};
const proofSources={
  't-11':'__IMG:delivery-proof-11__','t-12':'__IMG:delivery-proof-12__','t-13':'__IMG:delivery-proof-13__',
  't-14':'__IMG:delivery-proof-14__','t-15':'__IMG:delivery-proof-15__',
};
function pictures(sources){
  return Object.fromEntries(Object.entries(sources).map(([key,src])=>{
    const image=new Image();image.src=src;return [key,image];
  }));
}
const jobs=pictures(jobSources),proof=pictures(proofSources);
const hints=['先对一对这次的总量。','看看已有的九盏，再数要补的位置。'];
const cue={hint:'cart-hint',hint2:'cart-help',praise:'cart-praise'};
function level(step,pickup,drop,orderTotals,lanes){
  return {step,pickup,drop,lanes,hints,orders:orderTotals.map(total=>['r-'+(total-9),'t-'+total])};
}
const options=K.gameTemplates.listenDelivery({
  art:{backdrop:'__IMG:delivery-lane__',frames:['__IMG:delivery-empty__','__IMG:delivery-loaded__','__IMG:passing-cart__'],
    sticker:'__IMG:festival-rosette__',icons:{...goods,...totals}},
  voiceLead:true,cues:[{...cue,goal:'cart-first'},{...cue,goal:'cart-second'},{...cue,goal:'cart-third'}],
  levels:[
    level(.34,[['r-2',5],['r-3',4],['r-4',2]],[['t-11',5],['t-12',3],['t-13',7]],[11],
      [{row:2,speed:.85,phase:1.8,spacing:5.2}]),
    level(.30,[['r-5',2],['r-3',6],['r-4',4]],[['t-14',6],['t-12',2],['t-13',4]],[14,12],
      [{row:2,speed:1.1,phase:1.1,spacing:4.8},{row:3,speed:-.78,phase:2.8,spacing:5.5}]),
    level(.27,[['r-4',3],['r-6',6],['r-2',2],['r-5',4]],
      [['t-13',7],['t-15',3],['t-11',1],['t-14',5]],[13,15,11],
      [{row:1,speed:1.14,phase:2.1,spacing:5.1},{row:3,speed:-1.22,phase:3.3,spacing:5.4}]),
  ],doneText:'每次都用九盏和余量复原总数！',
});
function panel(context,image,x,y,width,height){
  if(!image?.complete||!image.naturalWidth)return;
  context.fillStyle='#2e5343';
  K.draw.rr(context,x,y,width,height,14);context.fill();
  const scale=Math.min((width-12)/image.naturalWidth,(height-12)/image.naturalHeight);
  const w=image.naturalWidth*scale,h=image.naturalHeight*scale;
  context.drawImage(image,x+(width-w)/2,y+(height-h)/2,w,h);
}
options.drawTop=(game,context)=>{
  const {w,level}=game.data;
  if(!w)return;
  const order=level.orders[w.order];
  const delivered=level.orders[w.order-1];
  if(order)panel(context,jobs[order[1]],43,218,169,164);
  if(delivered&&w.delivered.get(delivered[1])===delivered[0])panel(context,proof[delivered[1]],1058,372,167,149);
};
K.game(options);
K.$('[data-arc-input=action]').id='load-lamps';
const setState=K.onState;
K.onState=(state,content)=>{
  setState(state,content);
  if(state.pause===false||state.demo===false)for(const el of K.$$('.teach-hl'))el.classList.remove('teach-hl');
};
