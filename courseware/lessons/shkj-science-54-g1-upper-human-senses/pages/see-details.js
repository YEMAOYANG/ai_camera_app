const zones=K.$$('.search');
const field=K.$('#compare-table');
const words={color:'颜色变了。',shape:'形状变了。',size:'大小变了。'};
let found=0;
let attempts=0;
function paint(zone,name){
  K.$('[data-zone="'+zone+'"]').classList.add(name);
  K.$('[data-ring="'+zone+'"]').classList.add(name);
}
function reset(){
  found=0;attempts=0;field.disabled=false;
  K.$$('.search,.diagram i').forEach(el=>{el.classList.remove('found','demo');if(el.tagName==='BUTTON')el.disabled=false;});
  K.stars=0;K.$('#star-n').textContent='0';K.levels(3,0);
  K.say('看看两张图，点右边图里变了的地方。');
}
zones.forEach(zone=>zone.addEventListener('click',()=>{
  K.$$('.demo').forEach(el=>el.classList.remove('demo'));
  zone.disabled=true;paint(zone.dataset.zone,'found');attempts=0;
  K.sfx.ok();K.star(1,zone);K.levels(3,++found);K.say(words[zone.dataset.zone],'ok');
  if(found===3){field.disabled=true;setTimeout(()=>K.finish({title:'三处变化都找到了',sub:'眼睛能看出颜色、形状和大小。',again:reset}),430);}
}));
field.addEventListener('click',()=>{
  K.sfx.no();K.say('托盘没有变，试着比较两个图里的小片。','no');
  attempts+=1;
  if(attempts>1){const next=zones.find(zone=>!zone.disabled);if(next)K.highlight('#'+next.id);}
});
K.onState=function(state){
  K.$$('.demo').forEach(el=>el.classList.remove('demo'));
  if(words[state.demo]){paint(state.demo,'demo');K.say(words[state.demo]);}
  if(state.demo==='clear')K.say('点右边图里变了的小片。');
};
K.hud({title:'眼睛找不同',icon:'',levels:3});K.owl();
K.onStart=reset;K.ready({title:'眼睛找不同',sub:'左右对着看',emoji:'●'});
