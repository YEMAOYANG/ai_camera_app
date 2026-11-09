const shape=K.$('#shape-clue');const texture=K.$('#texture-clue');const box=K.$('#box-open');const photo=box.querySelector('img');
const senses=K.$('#sense-choices');const objects=K.$('#object-choices');
const senseButtons=K.$$('[data-sense]');const objectButtons=K.$$('[data-object]');
const closed='__IMG:closed-box__';const foam='__IMG:open-box-sponge__';
let phase=0;let misses=0;let chosen=null;
function reset(){
  phase=0;misses=0;chosen=null;photo.src=closed;photo.alt='有盖的观察盒';box.disabled=true;
  shape.classList.remove('visible');texture.classList.remove('visible');senses.classList.remove('hide');objects.classList.add('hide');
  objectButtons.forEach(button=>{button.disabled=false;button.classList.remove('picked');});
  K.stars=0;K.$('#star-n').textContent='0';K.levels(4,0);
  K.say('要知道形状，挑哪个感官？');
}
function wrong(target,message,help){
  K.sfx.no();K.say(message,'no');K.shake(target);
  if(++misses>1)K.highlight(help);
}
senseButtons.forEach(button=>button.addEventListener('click',()=>{
  if(phase>1)return;
  const need=phase===0?'eye':'skin';
  if(button.dataset.sense!==need){wrong(button,'想想要知道的是哪一种线索。','[data-sense="'+need+'"]');return;}
  (phase===0?shape:texture).classList.add('visible');
  K.sfx.ok();K.star(1,button);K.levels(4,++phase);misses=0;
  if(phase===1)K.say('它有平平的面。想知道软硬，要用什么？','ok');
  else {senses.classList.add('hide');objects.classList.remove('hide');K.say('它能按出浅坑。哪一件合上两条线索？','ok');}
}));
objectButtons.forEach(button=>button.addEventListener('click',()=>{
  if(phase!==2)return;
  if(button.dataset.object!=='foam'){wrong(button,'形状和软硬，两条都对得上吗？','[data-object=foam]');return;}
  chosen=button;button.classList.add('picked');box.disabled=false;
  objectButtons.forEach(item=>item.disabled=true);
  K.sfx.ok();K.star(1,button);K.levels(4,++phase);K.say('点一下盒子，看看猜得对不对。','ok');
}));
box.addEventListener('click',()=>{
  if(phase!==3||!chosen)return;
  photo.src=foam;photo.alt='盒子里是方形海绵';box.disabled=true;
  K.sfx.ok();K.star(1,box);K.levels(4,++phase);K.say('打开后看见了海绵，猜想对上了。','ok');
  setTimeout(()=>K.finish({title:'盒子打开了',sub:'把不同的线索合起来，再检查。',again:reset}),880);
});
K.onState=function(state){
  if(state.demo==='clear'){reset();return;}
  if(state.demo==='shape'){
    shape.classList.add('visible');texture.classList.remove('visible');K.highlight('#shape-clue');K.say('第一条线索是形状。');
  }else if(state.demo==='texture'){
    shape.classList.add('visible');texture.classList.add('visible');K.highlight('#texture-clue');K.say('第二条线索是软硬。');
  }else if(state.demo==='choices'){
    shape.classList.add('visible');texture.classList.add('visible');senses.classList.add('hide');objects.classList.remove('hide');K.say('一起比较两条线索。');
  }
};
K.hud({title:'猜一猜盒里有什么',icon:'',levels:4});K.owl();K.onStart=reset;
K.ready({title:'听线索，开盒子',sub:'猜完再打开看',emoji:'●'});
