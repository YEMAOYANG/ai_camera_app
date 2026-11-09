(function(){
  'use strict';
  function createModel(){var goals=[{toy:'bear',place:'on'},{toy:'hat',place:'under'},{toy:'car',place:'in'}];return {level:0,misses:0,stars:0,placed:{},done:false,
    target:function(){return goals[this.level]||null;},attempt:function(toy,place){if(this.done)return'done';if(this.placed[toy])return'already';var g=this.target();if(g.toy!==toy||g.place!==place){this.misses++;return this.misses>=3?'demo':'hint';}this.placed[toy]=place;this.level++;this.stars++;this.misses=0;this.done=this.level===3;return'correct';},
    reset:function(){this.level=0;this.misses=0;this.stars=0;this.placed={};this.done=false;}};}
  if(typeof module!=='undefined'&&module.exports){module.exports={createModel:createModel};return;}
  var K=window.K,model=createModel(),busy=false,timer=null,audio=null,selected=null;
  var toys={bear:K.$('#arrange-bear'),hat:K.$('#arrange-hat'),car:K.$('#arrange-car')};
  var origins={bear:[325,412],hat:[535,412],car:[745,412]},spots={on:[185,140],under:[555,250],in:[945,215]};
  var cues={bear:'__CUE:p09-bear__',hat:'__CUE:p09-hat__',car:'__CUE:p09-car__',hint:'__CUE:p09-hint__'};
  function stop(){if(audio){audio.pause();audio.currentTime=0;audio=null;}}
  function speak(key){stop();var url=cues[key];if(!url||url.indexOf('__CUE:')===0)return;audio=new Audio(url);audio.play().catch(function(){K.say('点小喇叭，再听一次。');});}
  function move(toy,place){var pos=spots[place]||origins[toy],el=toys[toy];el.style.left=pos[0]+'px';el.style.top=pos[1]+'px';el.classList.toggle('placed',!!place);}
  function query(){K.levels(3,model.level);}
  function unselect(){selected=null;Object.keys(toys).forEach(function(k){toys[k].classList.remove('selected');});}
  function reset(quiet){clearTimeout(timer);stop();model.reset();busy=false;unselect();K.$('#arrange-target').hidden=true;K.$$('.zone').forEach(function(e){e.classList.remove('hint');});Object.keys(toys).forEach(function(k){move(k,null);});K.stars=0;K.$('#star-n').textContent='0';query();K.say('先听一句，再摆好一件物品。');if(!quiet)speak(model.target().toy);}
  function attempt(toy,place){if(busy||model.done)return;var goal=model.target(),r=model.attempt(toy,place);if(r==='already')return;
    if(r==='correct'){busy=true;move(toy,place);unselect();K.star(1,toys[toy]);K.sfx.ok();K.say('摆放和句子一样，物品安顿好了。','ok');timer=setTimeout(function(){busy=false;if(model.done){stop();K.finish({title:'玩具角整理好了',sub:'三件物品，都有自己的位置。',again:reset});}else{query();speak(model.target().toy);}},1000);}
    else{K.sfx.no();K.shake(toys[toy]);K.say('不对就再听，先认准物品和位置。','no');speak('hint');if(r==='demo'){busy=true;unselect();timer=setTimeout(function(){move(goal.toy,goal.place);K.$('#arrange-'+goal.place).classList.add('hint');speak(goal.toy);timer=setTimeout(function(){move(goal.toy,null);K.$('#arrange-'+goal.place).classList.remove('hint');busy=false;},1800);},500);}}
  }
  K.hud({icon:'',title:'整理我们的玩具角',levels:3});K.owl();K.ready({emoji:'',title:'整理玩具角',sub:'听一句，选一件，放到它的位置。'});K.onStart=function(){reset(true);busy=true;};K.$('#start-btn').addEventListener('click',function(){busy=false;speak(model.target().toy);});
  Object.keys(toys).forEach(function(key){var el=toys[key];K.drag(el,{enabled:function(){return !busy&&!model.done&&!model.placed[key];},targets:function(){return K.$$('.zone');},onDrop:function(_,target){if(target)attempt(key,target.dataset.place);},onTap:function(){if(busy||model.placed[key])return;unselect();selected=key;el.classList.add('selected');K.sfx.pick();}});});
  K.$$('.zone').forEach(function(z){z.addEventListener('click',function(){if(selected)attempt(selected,z.dataset.place);else K.say('先选一件物品，再点它的位置。');});});K.$('#arrange-listen').addEventListener('click',function(){if(!busy&&!model.done)speak(model.target().toy);});
  K.onState = function (state) {
    clearTimeout(timer);
    stop();
    if (state.mode === 'demo') {
      const demonstratedToy = state.toy || 'car';
      busy = true;
      Object.keys(toys).forEach(function (key) { move(key, null); });
      move(demonstratedToy, state.relation);
      K.$('#arrange-target').src = K.$('img', toys[demonstratedToy]).src;
      K.$('#arrange-target').hidden = false;
      K.say('先看老师摆一摆。');
    } else if (state.mode === 'play') {
      reset();
    }
  };
  var fail=K.$('#arrange-media-error'),images=K.$$('#arrange-room img');images.forEach(function(im){im.addEventListener('error',function(){busy=true;stop();fail.classList.remove('hide');});});K.$('button',fail).addEventListener('click',function(){var left=images.length;images.forEach(function(im){im.onload=function(){if(--left===0){fail.classList.add('hide');reset();}};im.src=im.getAttribute('src');});});
})();
