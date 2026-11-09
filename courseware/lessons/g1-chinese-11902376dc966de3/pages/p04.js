(function(){
 'use strict';
 function initial(){return {opened:false,misses:0,finished:false};}
 function next(state,event){if(event==='reset')return initial();if(state.finished)return state;if(event==='spread')return {opened:true,misses:state.misses,finished:false};if(event==='path'&&state.opened)return {opened:true,misses:state.misses,finished:true};if(event==='boat'||event==='path')return {opened:state.opened,misses:state.misses+1,finished:false};return state;}
 if(typeof module!=='undefined'&&module.exports)module.exports={initial:initial,next:next};
 if(typeof document==='undefined')return;
 var state=initial(),demoTimer,view=K.$('#duckweed-view'),path=K.$('#path-choice');
 K.hud({icon:'',title:'是谁留下的水道',levels:2});K.owl();
 K.ready({img:'__IMG:duckweed__',emoji:'池',title:'是谁留下的水道',sub:'看看浮萍，找找踪迹'});
 function render(){view.classList.toggle('opened',state.opened);path.classList.toggle('chosen',state.finished);K.levels(2,state.finished?2:(state.opened?1:0));}
 function reset(){clearTimeout(demoTimer);state=initial();K.stars=0;K.$('#star-n').textContent='0';render();K.say('先看看小艇经过时，水面怎样变化。');}
 function act(event){clearTimeout(demoTimer);var before=state;state=next(state,event);render();
  if(state.misses>before.misses){K.sfx.no();K.shake(K.$('#meaning-choices'));K.say(state.misses===1?'再想想，走过以后留下的是什么？':state.opened?'留意水面，不是找走过的人。':'让小艇先经过，再观察水面。','no');return;}
  if(state.finished&&!before.finished){K.star(1,path);K.say('浮萍分开一道水，留下船走过的踪迹。','ok');K.finish({title:'发现踪迹',sub:'水道留下了小娃经过的痕迹。',again:reset});return;}
  if(state.opened&&!before.opened){K.sfx.ok();K.star(1,view);K.say('小艇经过，浮萍分开一道水。','ok');}
 }
 K.$('#spread-control').addEventListener('click',function(){act('spread');});
 K.$('#boat-choice').addEventListener('click',function(){act('boat');});
 path.addEventListener('click',function(){act('path');});
 K.onStart=reset;
 K.onState=function(value){if(value.demo==='path'){clearTimeout(demoTimer);view.classList.add('opened');K.say('老师示范：中间留下了小艇经过的水道。');demoTimer=setTimeout(render,2200);}};
 K.$$('.trace-stage img').forEach(function(im){im.addEventListener('error',function(){K.$('#trace-asset-note').classList.remove('hide');});});
})();
