(function(){
  'use strict';
  var buttons=K.$$('.part-circle'), ring=K.$('#part-evidence'), positions=[[50,72],[43,34],[80,72]];
  var tasks=['请找地面下面分枝的根。','请找地面上面的绿色叶子。','请找根旁边的棕色土壤。'];
  var partPic=K.$('#observation-picture');
  var level=0,misses=0,locked=false,loaded=partPic.complete&&partPic.naturalWidth>0,epoch=0;
  K.hud({icon:'🔎',title:'沿着同一株寻找',levels:3});K.owl();
  var retry=K.el('button','btn image-retry hide','↻',K.$('#play'));retry.setAttribute('aria-label','重新打开图片');
  retry.addEventListener('click',function(){loaded=false;locked=false;retry.classList.add('hide');partPic.src=partPic.src;K.say('正在重新打开图片，请等一等。');});
  function mark(index){ring.style.left=positions[index][0]+'%';ring.style.top=positions[index][1]+'%';ring.style.display='block';}
  function show(){misses=0;locked=false;ring.style.display='none';buttons.forEach(function(b){b.classList.remove('done','miss');});K.levels(3,level);K.say(tasks[level]);}
  function reset(){epoch++;level=0;K.stars=0;K.$('#star-n').textContent='0';show();}
  partPic.addEventListener('load',function(){loaded=true;retry.classList.add('hide');});
  partPic.addEventListener('error',function(){loaded=false;locked=true;retry.classList.remove('hide');K.say('图片没打开，点转圈箭头重试。','no');});
  buttons.forEach(function(button,index){button.addEventListener('click',function(){
    if(!K.started||locked||!loaded)return;
    if(index!==level){misses++;button.classList.add('miss');K.shake(button);K.sfx.no();K.say(misses===1?'先看地面线，再比较上面和下面。':misses===2?'只找这株植物，不把周围全叫根。':'看老师的观察镜，再自己找一次。','no');if(misses>=3)mark(level);return;}
    locked=true;mark(index);button.classList.add('done');K.star(1,button);K.sfx.ok();K.say('这个位置已留下，接着观察。','ok');
    var stamp=epoch;setTimeout(function(){if(stamp!==epoch)return;level++;if(level===3){K.levels(3,3);K.finish({title:'位置分清楚了',sub:'只记录图片定位，真实观察仍待完成。',again:reset});}else show();},650);
  });});
  K.onStart=reset;K.onState=function(state){if(state.demo){mark(0);K.say('示范：从地上沿着同一株看到地下。');}if(state.practice)reset();};
  K.ready({emoji:'🔎',title:'沿着同一株寻找',sub:'听问题，用观察圈留下位置。'});
})();
