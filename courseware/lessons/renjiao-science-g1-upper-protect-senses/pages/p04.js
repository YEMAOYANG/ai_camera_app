(function(){
var dirs=['left','right'],level=0,tries=0,locked=false,phase='play',demo=false;
K.hud({icon:'🐦',title:'听声音找位置',levels:2});K.owl();K.say('听一听，再让小鸟转向');
K.ready({emoji:'🐦',title:'听声音找位置',sub:'听一听，转一转',btn:'start-btn'});
var bird=K.$('#listener'),left=K.$('#direction-left'),right=K.$('#direction-right'),turn=K.$('#turn-indicator');
function direction(d){return d==='left'?left:right}
function cue(d){left.classList.remove('heard');right.classList.remove('heard');K.sfx.tick(d==='left'?0:5)}
function pointBird(d){bird.classList.remove('turn-left','turn-right');bird.classList.add(d==='left'?'turn-left':'turn-right')}
function setLevel(i){level=i;phase='play';tries=0;locked=false;demo=false;bird.classList.remove('turn-left','turn-right');left.classList.remove('active','correct','heard');right.classList.remove('active','correct','heard');turn.classList.remove('on');K.levels(2,i);cue(dirs[i]);K.say(i===0?'听左边的声音':'听右边的声音')}
function answer(d,el){if(!K.started||locked||phase!=='play')return;K.sfx.pick();var want=dirs[level];if(d===want){locked=true;phase='done';pointBird(d);direction(d).classList.add('correct');turn.classList.add('on');K.sfx.ok();K.star(tries===0?2:1,el);K.say(d==='left'?'小鸟转向左边声源':'小鸟转向右边声源','ok');setTimeout(function(){if(level===0)setLevel(1);else{K.levels(2,2);K.finish({title:'找到了声音',sub:'耳朵帮助我们听',again:function(){setLevel(0)}})}},1200);return}
 tries++;K.sfx.no();K.shake(el);if(tries===1){K.say('再听一次，留意声音从哪边来','no');cue(want)}else if(tries===2){K.say('看一看，哪边的声波在动','no');direction(want).classList.add('active','heard')}else{K.say('老师示范方向，再轮到你','no');pointBird(want);direction(want).classList.add('active');setTimeout(function(){bird.classList.remove('turn-left','turn-right');direction(want).classList.remove('active')},900)}}
[left,right].forEach(function(el){el.addEventListener('click',function(){answer(el.dataset.direction,el)})});
K.$('#sound-replay').addEventListener('click',function(){if(!K.started||phase!=='play')return;K.sfx.pick();cue(dirs[level]);K.say('再听一次声音线索')});
K.drag(bird,{enabled:function(){return K.started&&phase==='play'&&!locked},targets:function(){return [left,right]},onTap:function(){},onDrop:function(el,target){if(target)answer(target.dataset.direction,target)}});
K.onState=function(state){if(state.demo==='left'){demo=true;phase='demo';locked=true;cue('left');pointBird('left');left.classList.add('correct');turn.classList.add('on');K.say('老师示范：小鸟转向左边声源','ok')}if(state.phase==='play'){demo=false;setLevel(0)}};
K.highlight('#listener');
})();
