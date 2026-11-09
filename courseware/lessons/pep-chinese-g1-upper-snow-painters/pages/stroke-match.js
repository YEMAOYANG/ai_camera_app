(function(){
var paths={vertical:'M75 35 L75 170 L270 170',double:'M65 30 L65 108 L248 108 L248 182 Q248 207 215 184',hook:'M55 35 L255 35 L255 180 Q255 207 223 183'},kinds=['vertical','double','hook'],level=0,miss=0,busy=false,timer,source=K.$('#stroke-sample'),targets=K.$$('.stroke-choice');
function picture(k){return '<svg viewBox="0 0 320 230" aria-hidden="true"><path d="'+paths[k]+'"/></svg>'}
targets.forEach(function(t){t.innerHTML=picture(t.dataset.kind)});
K.hud({icon:'笔',title:'三个转折笔形',levels:3});K.owl();K.ready({emoji:'◌',title:'三个转折笔形',sub:'看清转弯，找相同笔形'});
function show(){clearTimeout(timer);busy=false;miss=0;source.innerHTML=picture(kinds[level]);source.style.left='24px';source.style.top='94px';source.style.width='350px';source.style.height='350px';targets.forEach(function(t){t.classList.remove('correct','hint')});K.levels(3,level);K.say('比较完整笔形，不只看起笔。')}
function reset(){level=0;K.stars=0;K.$('#star-n').textContent='0';show()}
function move(t){var a=t.getBoundingClientRect(),b=K.$('#play').getBoundingClientRect(),k=K.scale||1;source.style.left=((a.left-b.left)/k+10)+'px';source.style.top=((a.top-b.top)/k+80)+'px';source.style.width='105px';source.style.height='150px'}
function choose(t){if(!K.started||busy)return;if(t.dataset.kind!==kinds[level]){miss++;K.sfx.no();K.shake(t);K.say(miss===1?'从开始到末端，完整比一比。':miss===2?'留意转了几次、末尾有没有钩。':'看看相同笔形的提示，再试一次。','no');if(miss>=3)targets.find(function(x){return x.dataset.kind===kinds[level]}).classList.add('hint');return}busy=true;t.classList.add('correct');move(t);K.star(1,t);K.sfx.ok();K.say('两种画法表示相同的单笔笔形。','ok');timer=setTimeout(function(){level++;if(level===3){K.levels(3,3);K.finish({title:'笔形比清楚了',sub:'纸上的整字还要请大人看',again:reset})}else show()},1100)}
targets.forEach(function(t){t.addEventListener('click',function(){choose(t)})});K.drag(source,{enabled:function(){return K.started&&!busy},targets:function(){return targets},onTap:function(){K.say('点相同轮廓，或把笔形拖过去。')},onDrop:function(el,t){if(t)choose(t)}});
K.onStart=reset;K.onState=function(s){if(s.demo==='vertical'){reset();busy=true;var t=K.$('#stroke-choice-vertical');t.classList.add('correct');move(t);K.say('竖折的两个笔形靠在一起比较。')}if(s.phase==='play')reset()};
})();
