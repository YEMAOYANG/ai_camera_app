(function(){
  'use strict';
  var photos=['__IMG:garden__','__IMG:pot__','__IMG:hill__'];
  var alts=['花坛植株周围的土壤','陶盆口里的土壤','山坡树干旁的土壤'];
  var soilPositions=[[70,80],[72,78],[50,70]];
  var pic=K.$('#observation-picture'), choices=K.$$('.look-circle'), ring=K.$('#soil-evidence');
  var level=0, misses=0, locked=false, loaded=true, epoch=0;
  K.hud({icon:'🔎',title:'把土壤找出来',levels:3});K.owl();
  var retry=K.el('button','btn image-retry hide','↻',K.$('#play'));retry.setAttribute('aria-label','重新打开图片');
  retry.addEventListener('click',function(){loaded=false;locked=false;retry.classList.add('hide');pic.src=pic.src;K.say('正在重新打开图片，请等一等。');});
  function show(){
    loaded=false;pic.src=photos[level];pic.alt=alts[level];loaded=pic.complete&&pic.naturalWidth>0;misses=0;locked=false;
    choices.forEach(function(b){b.classList.remove('miss','done');b.disabled=false;});
    choices[1].style.left=soilPositions[level][0]+'%';choices[1].style.top=soilPositions[level][1]+'%';
    ring.style.display='none';K.levels(3,level);K.say('看看植物周围，土在哪里？');
  }
  function reset(){epoch++;level=0;K.stars=0;K.$('#star-n').textContent='0';show();}
  function evidence(){ring.style.left=soilPositions[level][0]+'%';ring.style.top=soilPositions[level][1]+'%';ring.style.display='block';}
  pic.addEventListener('load',function(){loaded=true;retry.classList.add('hide');});
  pic.addEventListener('error',function(){loaded=false;locked=true;retry.classList.remove('hide');K.say('图片没打开，点转圈箭头重试。','no');});
  choices.forEach(function(button,index){button.addEventListener('click',function(){
    if(!K.started||locked||!loaded)return;
    if(index!==1){misses++;button.classList.add('miss');K.sfx.no();K.shake(button);
      K.say(misses===1?'沿着植物往下，找它接触周围的地方。':misses===2?['看清植物旁边露出的棕土。','把盆壁和盆口里的土分开。','看看树干旁边露出的土。'][level]:'老师示范：观察镜停在这片土上。','no');
      if(misses>=3)evidence();return;}
    locked=true;button.classList.add('done');evidence();K.sfx.ok();K.star(1,button);K.say('留下土的位置，再观察下一个地方。','ok');
    var stamp=epoch;setTimeout(function(){if(stamp!==epoch)return;level++;if(level===3){K.levels(3,3);K.finish({title:'留下了观察证据',sub:'图片观察完成，现实发现还请大人听一听。',again:reset});}else show();},650);
  });});
  K.onStart=reset;
  K.onState=function(state){if(state.demo){evidence();K.say('示范：沿着植株，找到旁边的土。');}if(state.practice)reset();};
  K.ready({emoji:'🔎',title:'把土壤找出来',sub:'听老师说，点图里的观察圈。'});
})();
