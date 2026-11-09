(function(){
var entries=[{kind:'eat',src:'__IMG:hen-eat__'},{kind:'move',src:'__IMG:hen-move__'},{kind:'grow',src:'__IMG:hen-grow__'},{kind:'family',src:'__IMG:hen-family__'}],order=[],index=0,tries=0,phase='play',busy=false,epoch=0,selected=false,missing=false;
var source=K.$('#match-source'),photo=K.$('#match-photo'),targets=K.$$('#match-table button');
K.hud({icon:'◉',title:'把两本相册对起来',levels:4});K.owl();K.ready({emoji:'◉',title:'把两本相册对起来',sub:'同一方面，两种动物一起看',btn:'start-btn'});
K.$$('#match-board img').forEach(function(im){im.onerror=function(){missing=true;im.style.visibility='hidden';K.say('图片暂未载入，请重新打开本页')}});
function show(item){photo.style.visibility='visible';photo.src=item.src;photo.alt='鸡的'+({eat:'进食',move:'运动',grow:'长大示意',family:'下一代相伴'}[item.kind])+'线索';selected=false;source.classList.remove('selected')}
function clear(){targets.forEach(function(t){t.classList.remove('match-filled');K.$('.match-slot',t).innerHTML=''})}
function reset(){epoch++;phase='play';index=0;tries=0;busy=false;order=K.shuffle(entries);clear();K.stars=0;K.$('#star-n').textContent='0';K.levels(4,0);show(order[0]);K.say('把鸡的照片放到狗的同一方面旁边')}
function put(item,target){var im=K.el('img','',null,K.$('.match-slot',target));im.src=item.src;im.alt='对应的鸡生活线索';target.classList.add('match-filled')}
function match(target){if(!K.started||busy||phase!=='play'||!target||missing)return;var item=order[index];if(target.dataset.kind!==item.kind){tries++;K.sfx.no();K.shake(source);if(tries===1)K.say('再看看两张图，是否在比较同一方面','no');else if(tries===2)K.say('先分清进食、运动、长大和下一代','no');else{K.highlight('#match-'+item.kind);K.say('老师提示对应格，再由你放入','no')}return}
busy=true;put(item,target);K.star(1,target);K.sfx.ok();K.say('两边都有线索，这个方面可以一起比较','ok');var token=epoch;setTimeout(function(){if(token!==epoch)return;index++;if(index===4){K.levels(4,4);K.finish({title:'两本相册对好了',sub:'方式不同，也能有共同生活特征',again:reset});return}busy=false;tries=0;K.levels(4,index);show(order[index])},900)}
K.drag(source,{enabled:function(){return K.started&&!busy&&phase==='play'&&!missing},targets:function(){return targets},onTap:function(){selected=true;source.classList.add('selected');K.sfx.pick()},onDrop:function(el,target){match(target)}});targets.forEach(function(t){t.addEventListener('click',function(){if(selected)match(t)})});source.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();selected=true;source.classList.add('selected')}});K.$('#match-reset').addEventListener('click',reset);
K.onState=function(s){if(s.demo){phase='demo';var item=entries.filter(function(x){return x.kind===s.demo})[0];if(item){show(item);clear();put(item,K.$('#match-'+item.kind))}}if(s.phase==='play')reset()};K.onStart=reset;reset();
})();
