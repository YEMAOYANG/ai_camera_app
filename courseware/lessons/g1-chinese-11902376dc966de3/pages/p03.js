(function(){
  'use strict';
  function initial(){return {pushes:0,misses:0,finished:false};}
  function next(state,event){
    if(event==='reset')return initial();
    if(state.finished)return state;
    if(event==='push')return {pushes:Math.min(3,state.pushes+1),misses:state.misses,finished:false};
    if(event==='collect')return state.pushes===3?{pushes:3,misses:state.misses,finished:true}:{pushes:state.pushes,misses:state.misses+1,finished:false};
    return state;
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={initial:initial,next:next};
  if(typeof document==='undefined')return;
  var state=initial(),demoTimer,finishTimer;
  K.hud({icon:'',title:'小艇动起来',levels:4});K.owl();
  K.ready({img:'__IMG:boat__',emoji:'池',title:'小艇动起来',sub:'听词语，让小艇前进'});
  var boat=K.$('#boat-object'),landing=K.$('#lotus-target'),track=K.$('#journey-track');
  function render(){boat.style.transform='translateX('+(state.finished?0:state.pushes*88)+'px)';landing.classList.toggle('reached',state.pushes===3);track.classList.toggle('completed',state.finished);K.levels(4,state.finished?4:state.pushes);}
  function reset(){clearTimeout(demoTimer);clearTimeout(finishTimer);state=initial();K.stars=0;K.$('#star-n').textContent='0';render();K.say('让竹竿动起来，小艇会前进。');}
  function act(event){
    clearTimeout(demoTimer);var old=state;state=next(state,event);render();
    if(state.misses>old.misses){K.sfx.no();K.shake(boat);K.say(state.misses===1?'小艇还没靠近，看看两幅画之间的距离。':'试着让竹竿动一动，再看看小艇。','no');return;}
    if(state.finished&&!old.finished){K.star(1,landing);K.say('小娃撑小艇，偷采白莲回。','ok');finishTimer=setTimeout(function(){K.finish({title:'小艇归来',sub:'动作连上了诗句，朗读请家人听。',again:reset});},520);return;}
    if(state.pushes>old.pushes){K.sfx.tick(state.pushes);K.say(state.pushes===3?'小艇靠近了，想想采白莲的动作。':'竹竿一撑，小艇又向前了一段。','ok');}
  }
  K.$('#pole-control').addEventListener('click',function(){act('push');});
  K.$('#collect-control').addEventListener('click',function(){act('collect');});
  K.onStart=reset;
  K.onState=function(value){if(value.demo==='push'){clearTimeout(demoTimer);boat.style.transform='translateX(110px)';K.say('老师示范：竹竿一撑，小艇向前。');demoTimer=setTimeout(render,2200);}};
  K.$$('.boat-stage img').forEach(function(im){im.addEventListener('error',function(){K.$('#boat-asset-note').classList.remove('hide');});});
})();
