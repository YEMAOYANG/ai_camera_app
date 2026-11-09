const pictures={wash:'__IMG:wash-setup__',outside:'__IMG:orange-outside__',inside:'__IMG:orange-inside__'};
const descriptions={wash:'大人清洗橘子',outside:'完整橘子外皮',inside:'橘子里面的果肉'};
const cards=K.$$('.record-card');const photo=K.$('#observed-photo');const target=K.$('#observation-slot');
const order=['outside','inside'];let next=0;let misses=0;
function showPicture(key){photo.src=pictures[key];photo.alt=descriptions[key];}
function reset(){
  next=0;misses=0;showPicture('outside');photo.classList.remove('demo');
  K.$$('.posted-record').forEach(node=>node.replaceChildren());cards.forEach(card=>card.disabled=false);
  K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);
  K.say('先记外面，再记里面。拖图卡到观察册。');
}
function record(card){
  if(card.disabled||next>=order.length)return;
  if(card.dataset.observation!==order[next]){
    K.sfx.no();K.say('再想想观察顺序，哪一张应该先记？','no');K.shake(card);
    if(++misses>1)K.highlight('.record-card[data-observation="'+order[next]+'"]');
    return;
  }
  const type=order[next];showPicture(type);photo.classList.remove('demo');
  K.$('#record-'+(next+1)).append(card.querySelector('img').cloneNode(true));
  card.disabled=true;misses=0;K.sfx.ok();K.star(1,card);K.levels(2,++next);
  K.say(next===1?'记下外皮，再请大人剥开。':'橘瓣也记下来了。','ok');
  if(next===2)setTimeout(()=>K.finish({title:'观察册记好了',sub:'先看外面，再看里面。',again:reset}),430);
}
cards.forEach(card=>K.drag(card,{enabled:()=>!card.disabled,targets:()=>[target],onDrop:(item,where)=>{if(where)record(item);else K.say('把图卡放到观察册上。');},onTap:record}));
K.onState=function(state){
  photo.classList.remove('demo');
  if(pictures[state.demo]){showPicture(state.demo);photo.classList.add('demo');}
  if(state.demo==='evidence'){showPicture('inside');K.highlight('#observation-slot');K.say('记下这一次真的发现了什么。');}
  if(state.demo==='clear')reset();
};
K.hud({title:'观察橘子',icon:'',levels:2});K.owl();K.onStart=reset;
K.ready({title:'给橘子做记录',sub:'先外面，后里面',emoji:'●'});
