(function(){
var targets=['南','北','西','东'],positions={'东':[480,190],'西':[100,190],'南':[290,310],'北':[290,65]},level=0,miss=0,busy=false,timer;
var fish=K.$('#sentence-fish'),slot=K.$('#word-slot'),cards=K.$$('.word-card');
K.hud({icon:'字',title:'给诗句接上方向',levels:4});K.owl();K.ready({emoji:'◌',title:'给诗句接上方向',sub:'看小鱼，选方位字'});
function at(w){var p=positions[w];fish.style.left=p[0]+'px';fish.style.top=p[1]+'px';fish.classList.remove('swim')}
function show(){clearTimeout(timer);busy=false;miss=0;slot.textContent='?';slot.classList.remove('filled');cards.forEach(function(c){c.classList.remove('success','hint')});K.shuffle(cards).forEach(function(c){K.$('#word-bank').appendChild(c)});at(targets[level]);K.levels(4,level);K.say('先看小鱼在哪里，再给诗句接上方位。')}
function reset(){level=0;K.stars=0;K.$('#star-n').textContent='0';show()}
function choose(c){if(!K.started||busy)return;if(c.dataset.word!==targets[level]){miss++;K.sfx.no();K.shake(c);K.say(miss===1?'先比较小鱼与荷叶的位置。':miss===2?'回想这张方位板，别只看字卡。':'看方位字的提示，再试一次。','no');if(miss>=3)cards.forEach(function(a){a.classList.toggle('hint',a.dataset.word===targets[level])});return}
busy=true;slot.textContent=c.dataset.word;slot.classList.add('filled');c.classList.add('success');fish.classList.add('swim');K.sfx.ok();K.star(1,slot);K.say('这个字把小鱼的位置说清楚了。','ok');timer=setTimeout(function(){level++;if(level===4){K.levels(4,4);K.finish({title:'诗句接好了',sub:'相同开头，方向会变',again:reset})}else show()},1150)}
cards.forEach(function(c){c.addEventListener('click',function(){choose(c)});K.drag(c,{enabled:function(){return K.started&&!busy},targets:function(){return [slot]},onDrop:function(el,t){if(t)choose(el)}})});
K.onStart=reset;K.onState=function(s){if(s.demo==='east'){clearTimeout(timer);busy=true;at('东');slot.textContent='东';slot.classList.add('filled');fish.classList.add('swim');K.say('鱼戏莲叶东，图与字连起来。')}if(s.phase==='play')reset()};
})();
