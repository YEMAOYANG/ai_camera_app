(function(){
var cards=K.$$('.radical-card'),bank=K.$('#roof-bank'),slot=K.$('#roof-slot'),level=0,miss=0,busy=false,timer;
K.hud({icon:'字',title:'给家找回宝盖头',levels:2});K.owl();K.ready({emoji:'◌',title:'给家找回宝盖头',sub:'看字形，把偏旁放到上面'});
function show(){clearTimeout(timer);busy=false;miss=0;slot.classList.remove('filled');cards.forEach(function(c){bank.appendChild(c);c.disabled=false;c.classList.remove('hint')});K.shuffle(cards).forEach(function(c){bank.appendChild(c)});K.levels(2,level);K.say('对照家字，找到上面的宝盖头。')}
function reset(){level=0;K.stars=0;K.$('#star-n').textContent='0';show()}
function choose(c){if(!K.started||busy||c.disabled)return;if(c.dataset.radical!=='roof'){miss++;K.shake(c);K.sfx.no();K.say(miss===1?'先看家字上面的形状。':miss===2?'从上到下比较这个偏旁。':'看宝盖头的提示，再放一次。','no');if(miss>=3)K.$('#roof-card').classList.add('hint');return}busy=true;slot.appendChild(c);c.disabled=true;c.classList.remove('hint');slot.classList.add('filled');K.star(1,slot);K.sfx.ok();K.say('宝盖头放在家字上面。','ok');timer=setTimeout(function(){level++;if(level===2){K.levels(2,2);K.finish({title:'宝盖头找到了',sub:'再看看完整的家字',again:reset})}else show()},1100)}
cards.forEach(function(c){c.addEventListener('click',function(){choose(c)});K.drag(c,{enabled:function(){return K.started&&!busy&&!c.disabled},targets:function(){return [slot]},onDrop:function(el,t){if(t)choose(el)}})});
K.onStart=reset;K.onState=function(s){if(s.demo==='roof'){reset();busy=true;slot.appendChild(cards[0]);cards[0].disabled=true;slot.classList.add('filled');K.say('家的上方是宝盖头。')}if(s.phase==='play')reset()};
})();
