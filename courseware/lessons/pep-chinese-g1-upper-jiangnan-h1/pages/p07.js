(function(){
var lines=[['莲叶','何','田田'],['鱼戏','莲','叶间']],level=0,miss=0,busy=false,timer,slots=[K.$('#pause-slot-1'),K.$('#pause-slot-2')],beat=K.$('#beat'),pond=K.$('.pond');
K.hud({icon:'🌿',title:'给诗句安上节拍',levels:2});K.owl();K.ready({img:'__IMG:pond__',emoji:'🌿',title:'给诗句安上节拍',sub:'听一听，放停顿'});
function show(parts){K.$('#part-a').textContent=parts[0];K.$('#part-b').textContent=parts[1];K.$('#part-c').textContent=parts[2];slots.forEach(function(s){s.classList.remove('placed','hint')});pond.classList.remove('wave')}
function round(){busy=false;miss=0;beat.classList.remove('selected');show(lines[level]);K.levels(2,level);K.say('听一听，在哪里停一下？')}
function reset(){clearTimeout(timer);level=0;K.stars=0;K.$('#star-n').textContent='0';round()}
function choose(slot){if(busy)return;if(slot!==slots[0]){miss++;K.sfx.no();K.shake(beat);K.say(miss===1?'再听，哪里声音停了一下？':miss===2?'跟着老师慢读，留意两段之间。':'看，停顿放在两段之间。','no');if(miss>=3){slots[0].classList.add('hint');timer=setTimeout(function(){slots[0].classList.remove('hint')},1800)}return}busy=true;slot.classList.add('placed');pond.classList.add('wave');K.sfx.ok();K.star(1,slot);K.say('两段之间歇一歇。','ok');timer=setTimeout(function(){level++;if(level===2){K.levels(2,2);K.finish({title:'听到了停顿',sub:'跟老师再读读',again:reset})}else round()},1800)}
beat.addEventListener('click',function(){beat.classList.toggle('selected')});K.drag(beat,{targets:function(){return slots},onDrop:function(el,target){if(target)choose(target)}});slots.forEach(function(s){s.addEventListener('click',function(){choose(s)})});
K.onState=function(state){if(state.demo==='pause'){clearTimeout(timer);busy=true;show(['江南','可','采莲']);slots[0].classList.add('placed');pond.classList.add('wave');K.sfx.tick(0);setTimeout(function(){K.sfx.tick(2)},500);timer=setTimeout(round,6500)}};K.onStart=function(){show(['江南','可','采莲']);K.say('听老师慢慢读。');timer=setTimeout(round,10000)};
})();
