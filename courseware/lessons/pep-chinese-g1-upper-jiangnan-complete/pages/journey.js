(function(){
var cards=K.$$('.journey-card'),slots=K.$$('.journey-slot'),tray=K.$('#journey-tray'),next=0,miss=0,busy=false,timer;
K.hud({icon:'图',title:'排好小鱼的游程',levels:6});K.owl();K.ready({emoji:'◌',title:'排好小鱼的游程',sub:'按诗里的顺序移动图卡'});
function marks(){slots.forEach(function(s,i){s.classList.toggle('current',i===next);s.classList.toggle('filled',!!K.$('.journey-card',s))})}
function reset(){clearTimeout(timer);next=0;miss=0;busy=false;K.stars=0;K.$('#star-n').textContent='0';cards.forEach(function(c){c.disabled=false;c.classList.remove('hint');c.style.transform='';tray.appendChild(c)});K.shuffle(cards).forEach(function(c){tray.appendChild(c)});marks();K.levels(6,0);K.say('从莲叶想到小鱼，再想到四方。')}
function choose(card,target){if(!K.started||busy||card.disabled)return;if(target&&Number(target.dataset.index)!==next){K.say('先把图卡放进亮边框的下一格。');return}if(Number(card.dataset.index)!==next){miss++;K.sfx.no();K.shake(card);K.say(miss===1?'想一想古诗接下来写什么。':miss===2?'先莲叶，再小鱼，再按四方想。':'看看图卡的提示，再放一次。','no');if(miss>=3)cards[next].classList.add('hint');return}
busy=true;card.classList.remove('hint');slots[next].appendChild(card);card.disabled=true;K.sfx.ok();K.star(1,card);K.say('把这一幅画面接到心里。','ok');next++;marks();K.levels(6,next);timer=setTimeout(function(){busy=false;miss=0;if(next===6){K.finish({title:'画面连起来了',sub:'请大人听一次完整背诵',again:reset})}},850)}
cards.forEach(function(c){c.addEventListener('click',function(){choose(c,null)});K.drag(c,{enabled:function(){return K.started&&!busy&&!c.disabled},targets:function(){return slots},onDrop:function(el,t){if(t)choose(el,t)}})});
K.onStart=reset;K.onState=function(s){if(s.demo==='opening'){reset();busy=true;slots[0].appendChild(cards[0]);cards[0].disabled=true;marks();K.say('莲叶图帮助回想开始两句。')}if(s.phase==='play')reset()};
})();
