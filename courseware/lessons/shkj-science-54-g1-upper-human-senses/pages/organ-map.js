const parts = K.$$('.part');
const targets = K.$$('.target');
const names = {eye:'眼睛', ear:'耳朵', nose:'鼻子', tongue:'舌头', skin:'皮肤'};
let selected = null;
let attempts = 0;
let done = 0;
function clearSelection(){
  selected = null;
  attempts = 0;
  parts.forEach(part=>part.classList.remove('selected'));
}
function reset(){
  clearSelection();
  done = 0;
  parts.concat(targets).forEach(part=>{part.disabled=false;part.classList.remove('done','bad','demo');});
  K.stars=0; K.$('#star-n').textContent='0'; K.levels(5,0);
  K.say('先挑图卡，再点身体上的位置。');
}
parts.forEach(part=>part.addEventListener('click',()=>{
  clearSelection();
  selected=part.dataset.part;
  part.classList.add('selected');
  K.sfx.pick();
  K.say('找一找它的位置。');
}));
targets.forEach(target=>target.addEventListener('click',()=>{
  if(!selected){K.say('先挑一张图卡。');return;}
  if(selected!==target.dataset.part){
    attempts+=1;K.sfx.no();K.say('再看看图卡画的是哪里。','no');
    target.classList.add('bad');setTimeout(()=>target.classList.remove('bad'),400);
    if(attempts>1)K.highlight('#point-'+selected);
    return;
  }
  const part=parts.find(card=>card.dataset.part===selected);
  part.disabled=true;target.disabled=true;target.classList.add('done');
  K.sfx.ok();K.star(1,target);K.levels(5,++done);
  K.say(names[selected]+'找到位置了。','ok');clearSelection();
  if(done===5)setTimeout(()=>K.finish({title:'感官都找到了',sub:'每一种都帮我们认识周围。',again:reset}),440);
}));
K.onState=function(state){
  parts.concat(targets).forEach(part=>part.classList.remove('demo','selected'));
  if(state.demo==='clear'){clearSelection();K.say('先挑一张图卡，再点对应的位置。');return;}
  const demo=targets.find(target=>target.dataset.part===state.demo);
  if(!demo)return;
  demo.classList.add('demo');parts.find(part=>part.dataset.part===state.demo).classList.add('selected');
  K.say(names[state.demo]+'的位置。');
};
K.hud({title:'认一认感官',icon:'',levels:5});K.owl();
K.onStart=reset;K.ready({title:'感官在哪里',sub:'跟着老师找一找',emoji:'●'});
