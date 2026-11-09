(function(){
  'use strict';
  function createModel(){
    var rounds=['under','on','in'];
    return {level:0,misses:0,stars:0,done:false,attempt:function(place){
      if(this.done)return 'done';
      if(place!==rounds[this.level]){this.misses++;return this.misses>=3?'demo':'hint';}
      this.level++;this.stars++;this.misses=0;this.done=this.level===rounds.length;return 'correct';
    },target:function(){return rounds[this.level]||null;},reset:function(){this.level=0;this.misses=0;this.stars=0;this.done=false;}};
  }
  if(typeof module!=='undefined'&&module.exports){module.exports={createModel:createModel};return;}
  var K=window.K,model=createModel(),busy=false,timer=null,audio=null;
  var car=K.$('#position-car'),word=K.$('#position-word');
  var locations={on:[435,183],under:[435,304],in:[925,265]};
  var cues={under:'__CUE:p02-under__',on:'__CUE:p02-on__',in:'__CUE:p02-in__',hint:'__CUE:p02-hint__'};
  function stop(){if(audio){audio.pause();audio.currentTime=0;audio=null;}}
  function speak(key){stop();var url=cues[key];if(!url||url.indexOf('__CUE:')===0)return;audio=new Audio(url);audio.play().catch(function(){K.say('点小喇叭，可以再听一次。');});}
  function move(place){var p=locations[place]||[52,290];car.style.left=p[0]+'px';car.style.top=p[1]+'px';car.style.width=place?"130px":"180px";car.style.height=place?"130px":"160px";car.style.background=place?'transparent':'#fff9e9';car.classList.toggle('placed',!!place);}
  function clear(){clearTimeout(timer);K.$$('.zone').forEach(function(x){x.classList.remove('hint');});}
  function render(){move(null);word.textContent=model.target()||'';K.levels(3,model.level);}
  function reset(quiet){clear();stop();model.reset();busy=false;K.stars=0;K.$('#star-n').textContent='0';render();K.say('听一听，再把小车摆好。');if(!quiet)speak(model.target());}
  function attempt(place){if(busy||model.done)return;var goal=model.target(),result=model.attempt(place);
    if(result==='correct'){busy=true;move(goal);K.star(1,car);K.sfx.ok();K.say('摆好了，位置和听到的一样。','ok');timer=setTimeout(function(){busy=false;if(model.done){stop();K.finish({title:'位置摆对了',sub:'再听，再摆，记住三个位置。',again:reset});}else{render();speak(model.target());}},1000);}
    else{K.sfx.no();K.shake(car);K.say('再听一遍，先找参照物。','no');speak('hint');if(result==='demo'){busy=true;timer=setTimeout(function(){move(goal);speak(goal);K.$('#position-'+goal).classList.add('hint');timer=setTimeout(function(){clear();busy=false;move(null);},1800);},500);}}
  }
  K.hud({icon:'',title:'听一听，摆一摆',levels:3});K.owl();
  K.ready({emoji:'',title:'听一听，摆一摆',sub:'听老师说，帮小车搬家。'});
  K.onStart=function(){reset(true);busy=true;};K.$('#start-btn').addEventListener('click',function(){busy=false;speak(model.target());});
  K.$$('.zone').forEach(function(x){x.addEventListener('click',function(){attempt(x.dataset.place);});});
  K.drag(car,{enabled:function(){return !busy&&!model.done;},targets:function(){return K.$$('.zone');},onDrop:function(_,target){if(target)attempt(target.dataset.place);else move(null);},onTap:function(){speak(model.target());}});
  K.$('#position-listen').addEventListener('click',function(){if(!busy)speak(model.target());});
  K.onState=function(state){clear();stop();if(state.mode==='demo'){busy=true;move(state.relation);word.textContent=state.relation;K.say('先看老师摆一摆。');}
    else if(state.mode==='play'){reset();}};
  var fail=K.$('#position-media-error'),images=K.$$('#position-room img');
  images.forEach(function(im){im.addEventListener('error',function(){busy=true;stop();fail.classList.remove('hide');});});
  K.$('button',fail).addEventListener('click',function(){var left=images.length;images.forEach(function(im){im.onload=function(){if(--left===0){fail.classList.add('hide');reset();}};im.src=im.getAttribute('src');});});
})();
