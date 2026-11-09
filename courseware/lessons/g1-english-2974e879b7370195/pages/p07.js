(function(){
  function makePlacement(answer){return {answer:answer,done:false,wrongs:0,place:function(id){if(this.done)return 'ignored';if(id===this.answer){this.done=true;return 'correct';}this.wrongs++;return 'wrong';},reset:function(){this.done=false;this.wrongs=0;}};}
  if(typeof module==='object'&&module.exports)module.exports={makePlacement:makePlacement};
  if(typeof document==='undefined')return;
  var model=makePlacement('place-under'),selected=false,timer,cat=K.$('#cat-mover'),bed=K.$('#bed-picture'),emptyBedSrc=K.$('#bed-picture').src;
  K.hud({icon:'',title:'把小猫安置在床下',levels:1});K.owl();
  function reset(){clearTimeout(timer);model.reset();selected=false;cat.classList.remove('selected','placed','hide');bed.src=emptyBedSrc;K.$$('.place-target').forEach(function(t){t.classList.remove('hide');});K.$('#tip').style.display='none';cat.style.left='60px';cat.style.top='245px';K.stars=0;K.$('#star-n').textContent='0';K.levels(1,0);K.say('听清位置，拖动小猫；也能先点再点。');}
  function place(target){if(model.done||!target)return;var result=model.place(target.id);if(result==='wrong'){selected=false;cat.classList.remove('selected');K.sfx.no();K.shake(cat);if(model.wrongs===2)K.highlight('#bed-picture');if(model.wrongs>=3)K.highlight('#place-under');K.say(model.wrongs===1?'先停一停，看清床面和床底。':'再听位置词，对着床找一找。','no');return;}cat.style.left=(target.offsetLeft-10)+'px';cat.style.top=(target.offsetTop-25)+'px';cat.classList.remove('selected');cat.classList.add('placed');K.star(1,cat);bed.src='__IMG:under-bed__';cat.classList.add('hide');K.$$('.place-target').forEach(function(t){t.classList.add('hide');});K.$('#tip').style.display='none';bed.classList.remove('teach-hl');K.sfx.ok();K.levels(1,1);K.say('小猫的位置和老师说的一样。','ok');timer=setTimeout(function(){K.finish({title:'小猫安置好了',sub:'看清相对位置再回答',again:reset});},1200);}
  K.$$('.place-target').forEach(function(target){target.addEventListener('click',function(){if(selected)place(target);else K.say('先点一下小猫，再点你选的位置。');});});
  function select(){if(model.done)return;selected=true;cat.classList.add('selected');K.say('现在点一个落点，让小猫过去。');}
  K.drag(cat,{enabled:function(){return !model.done;},targets:function(){return K.$$('.place-target');},onTap:select,onDrop:function(_,target){place(target);}});
  cat.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}});
  K.onState=function(state){if(state.reset)reset();};
  K.$$('#play img').forEach(function(img){img.addEventListener('error',function(){K.$('#image-recovery').classList.remove('hide');});});
  K.$('#retry-pictures').addEventListener('click',function(){K.$('#image-recovery').classList.add('hide');K.$$('#play img').forEach(function(img){img.src=img.src;});});
  K.onStart=reset;K.ready({title:'把小猫安置在床下',sub:'听位置，再摆放',emoji:''});
})();
