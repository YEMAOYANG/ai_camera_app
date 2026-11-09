(function(){
  'use strict';
  function createModel(){var goals=['under','in','on'];return {level:0,misses:0,stars:0,found:[],done:false,
    target:function(){return goals[this.level]||null;},attempt:function(place){if(this.done)return'done';if(place!==this.target()){this.misses++;return this.misses>=3?'demo':'hint';}this.found.push(place);this.level++;this.stars++;this.misses=0;this.done=this.level===3;return'correct';},
    reset:function(){this.level=0;this.misses=0;this.stars=0;this.found=[];this.done=false;}};}
  if(typeof module!=='undefined'&&module.exports){module.exports={createModel:createModel};return;}
  var K=window.K,model=createModel(),busy=false,timer=null,audio=null;
  var toys={under:K.$('#search-bear'),in:K.$('#search-hat'),on:K.$('#search-car')};
  var cues={under:'__CUE:p04-bear__',in:'__CUE:p04-hat__',on:'__CUE:p04-car__',hint:'__CUE:p04-hint__'};
  function stop(){if(audio){audio.pause();audio.currentTime=0;audio=null;}}
  function speak(key){stop();var url=cues[key];if(!url||url.indexOf('__CUE:')===0)return;audio=new Audio(url);audio.play().catch(function(){K.say('点小喇叭，再听一次。');});}
  function closeAll(){K.$$('.cover').forEach(function(c){c.classList.remove('open');});}
  function query(){var goal=model.target();if(goal)K.$('#search-target').src=toys[goal].src;K.levels(3,model.level);}
  function reset(quiet){clearTimeout(timer);stop();model.reset();busy=false;closeAll();K.$$('.cover').forEach(function(c){c.classList.remove('found');});Object.keys(toys).forEach(function(k){toys[k].style.opacity='1';});K.$('#search-tray').innerHTML='';K.stars=0;K.$('#star-n').textContent='0';query();K.say('听名字，去找正在问的物品。');if(!quiet)speak(model.target());}
  function attempt(place){if(busy||model.done||model.found.indexOf(place)>=0)return;clearTimeout(timer);closeAll();var goal=model.target(),cover=K.$('#search-cover-'+place),result=model.attempt(place);cover.classList.add('open');
    if(result==='correct'){busy=true;K.star(1,cover);K.sfx.ok();K.say('找到了，物品来到收集区。','ok');timer=setTimeout(function(){cover.classList.add('found');toys[place].style.opacity='0';var im=K.el('img','',null,K.$('#search-tray'));im.src=toys[place].src;im.alt=toys[place].alt;busy=false;if(model.done){stop();K.finish({title:'都找到了',sub:'听名字，再看它和家具的关系。',again:reset});}else{query();speak(model.target());}},900);}
    else{K.sfx.no();K.say('不是这个物品，先听清名字。','no');speak('hint');timer=setTimeout(function(){cover.classList.remove('open');if(result==='demo'){var c=K.$('#search-cover-'+goal);c.classList.add('open');timer=setTimeout(function(){c.classList.remove('open');},1700);}},700);}
  }
  K.hud({icon:'',title:'帮忙找玩具',levels:3});K.owl();K.ready({emoji:'',title:'帮忙找玩具',sub:'听清名字，掀开看看。'});K.onStart=function(){reset(true);busy=true;};K.$('#start-btn').addEventListener('click',function(){busy=false;speak(model.target());});
  K.$$('.cover').forEach(function(c){c.addEventListener('click',function(){attempt(c.dataset.place);});});K.$('#search-listen').addEventListener('click',function(){if(!busy)speak(model.target());});
  K.onState=function(state){
    clearTimeout(timer);stop();closeAll();
    if(state.mode==='play'){reset();return;}
    if((state.mode==='focus'||state.mode==='demo')&&toys[state.place]){
      busy=true;
      K.$('#search-target').src=toys[state.place].src;
      if(state.mode==='demo')K.$('#search-cover-'+state.place).classList.add('open');
      K.say('先看老师找一找。');
    }
  };
  var fail=K.$('#search-media-error'),images=K.$$('#search-room img');images.forEach(function(im){im.addEventListener('error',function(){busy=true;stop();fail.classList.remove('hide');});});K.$('button',fail).addEventListener('click',function(){var left=images.length;images.forEach(function(im){im.onload=function(){if(--left===0){fail.classList.add('hide');reset();}};im.src=im.getAttribute('src');});});
})();
