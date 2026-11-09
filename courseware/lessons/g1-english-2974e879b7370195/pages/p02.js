(function(){
  function makeChoice(){return {done:false,wrongs:0,choose:function(colour){if(this.done)return 'ignored';if(colour==='orange'){this.done=true;return 'correct';}this.wrongs++;return 'wrong';},reset:function(){this.done=false;this.wrongs=0;}};}
  if(typeof module==='object'&&module.exports)module.exports={makeChoice:makeChoice};
  if(typeof document==='undefined')return;
  var model=makeChoice(),timer;
  K.hud({icon:'',title:'听颜色，找小猫',levels:1});K.owl();
  function reset(){clearTimeout(timer);model.reset();K.stars=0;K.$('#star-n').textContent='0';K.levels(1,0);K.$$('.cat-choice').forEach(function(b){b.classList.remove('selected');b.disabled=false;});K.$('#demo-cat').classList.remove('settled');K.say('听老师的声音，点对应的小猫。');}
  K.$$('.cat-choice').forEach(function(button){button.addEventListener('click',function(){var result=model.choose(button.dataset.colour);if(result==='ignored')return;if(result==='wrong'){K.sfx.no();K.shake(button);K.say(model.wrongs===1?'先听清颜色，再比较毛的颜色。':'再想想 orange 的意思，慢慢找。','no');return;}button.classList.add('selected');K.$$('.cat-choice').forEach(function(b){b.disabled=true;});K.star(1,button);K.sfx.ok();K.levels(1,1);K.say('你按声音找到了这只小猫。','ok');timer=setTimeout(function(){K.finish({title:'找到小猫了',sub:'听颜色，再认图',again:reset});},1000);});});
  K.onState=function(state){if('demo'in state){var cat=K.$('#demo-cat');cat.classList.toggle('settled',!!state.demo);if(!state.demo){cat.classList.remove('teach-hl');K.$('#tip').style.display='none';}};};
  K.$$ ('#play img').forEach(function(img){img.addEventListener('error',function(){K.$('#image-recovery').classList.remove('hide');});});
  K.$('#retry-pictures').addEventListener('click',function(){K.$('#image-recovery').classList.add('hide');K.$$('#play img').forEach(function(img){img.src=img.src;});});
  K.onStart=reset;K.ready({title:'听颜色，找小猫',sub:'听老师读一句，再点图片',emoji:''});
})();
