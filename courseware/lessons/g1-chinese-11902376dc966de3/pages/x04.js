(function(){
 'use strict';
 var order=['spring','shade','lotus','dragonfly'];
 function initial(){return {index:0,misses:0,finished:false};}
 function next(state,event){if(event==='reset')return initial();if(state.finished)return state;if(order.indexOf(event)<0)return state;if(order[state.index]!==event)return {index:state.index,misses:state.misses+1,finished:false};return {index:state.index+1,misses:state.misses,finished:state.index===3};}
 if(typeof module!=='undefined'&&module.exports)module.exports={initial:initial,next:next};
 if(typeof document==='undefined')return;
 var state=initial(),demoTimer,labels=['泉眼','树阴','小荷','蜻蜓'],lines=['泉眼 / 无声 / 惜细流','树阴 / 照水 / 爱晴柔','小荷 / 才露 / 尖尖角','早有 / 蜻蜓 / 立上头'];
 K.hud({icon:'',title:'发现小池里的景物',levels:4});K.owl();K.ready({img:'__IMG:small-pond__',emoji:'池',title:'发现小池里的景物',sub:'泉眼、树阴、小荷、蜻蜓'});
 function render(){order.forEach(function(name,i){K.$('#'+name+'-spot').classList.toggle('found',i<state.index);});K.$('#current-object').textContent=labels[Math.min(3,state.index)];K.$('#poem-found').textContent=lines[Math.min(3,state.index)];K.levels(4,state.index);}
 function reset(){clearTimeout(demoTimer);state=initial();K.stars=0;K.$('#star-n').textContent='0';K.$$('.scene-spot').forEach(function(e){e.classList.remove('demo');});render();K.say('先泉眼，再树阴、小荷，最后找蜻蜓。');}
 function act(name){var old=state;state=next(state,name);render();if(state.misses>old.misses){K.sfx.no();K.shake(K.$('#current-object'));K.say(state.misses===1?'再想想老师说过的顺序，看看画面。':'泉眼出水，树阴映水，小荷叶尖上有蜻蜓。','no');return;}if(state.index>old.index){K.star(1,K.$('#'+name+'-spot'));K.sfx.ok();K.say('找到'+labels[old.index]+'，请把对应诗句说给家人听。','ok');}if(state.finished&&!old.finished)K.finish({title:'小池有生机',sub:'景物和诗句连上了，背诵请家人听。',again:reset});}
 order.forEach(function(name){K.$('#'+name+'-spot').addEventListener('click',function(){act(name);});});K.$('#clear-spots').addEventListener('click',reset);K.onStart=reset;
 K.onState=function(value){if(value.demo==='spring'){clearTimeout(demoTimer);K.$('#spring-spot').classList.add('demo');K.say('老师圈出泉眼，清水从这里流出。');demoTimer=setTimeout(function(){K.$('#spring-spot').classList.remove('demo');},2200);}};
 K.$('#pond-picture img').addEventListener('error',function(){K.$('#pond-asset-note').classList.remove('hide');});
})();
