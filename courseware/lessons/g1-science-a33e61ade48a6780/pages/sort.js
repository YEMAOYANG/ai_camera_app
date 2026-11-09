(function(){
  'use strict';
  var cards=K.$$('.plant-photo'),tray=K.$('#photo-tray'),land=K.$('#land-zone'),water=K.$('#water-zone');
  var images=K.$$('img');
  function picturesReady(){return images.every(function(im){return im.complete&&im.naturalWidth>0;});}
  var zones=[land,water],expect=['land','water','land'],selected=null,misses={},done=0,loaded=picturesReady();
  K.hud({icon:'🌱',title:'植物环境观察台',levels:3});K.owl();
  var retry=K.el('button','btn image-retry hide','↻',K.$('#play'));retry.setAttribute('aria-label','重新打开图片');
  retry.addEventListener('click',function(){loaded=false;retry.classList.add('hide');images.forEach(function(im){im.src=im.src;});K.say('正在重新打开图片，请等一等。');});
  images.forEach(function(im){im.addEventListener('load',function(){loaded=picturesReady();if(loaded)retry.classList.add('hide');});im.addEventListener('error',function(){loaded=false;retry.classList.remove('hide');K.say('图片没打开，点转圈箭头重试。','no');});});
  function reset(){selected=null;misses={};done=0;K.stars=0;K.$('#star-n').textContent='0';cards.forEach(function(c){c.classList.remove('placed','selected');tray.appendChild(c);c.style.transform='';});K.levels(3,0);K.say('先看植物周围，再把照片放进观察栏。');}
  function select(c){if(!loaded||c.classList.contains('placed'))return;cards.forEach(function(x){x.classList.remove('selected');});selected=c;c.classList.add('selected');K.sfx.pick();}
  function place(c,target){
    if(!K.started||!loaded||!c||c.classList.contains('placed'))return;
    var index=cards.indexOf(c),kind=target===land?'land':target===water?'water':null;
    if(kind!==expect[index]){misses[c.id]=(misses[c.id]||0)+1;K.shake(c);K.sfx.no();K.say(misses[c.id]===1?'看看照片里，植物周围是什么。':misses[c.id]===2?'把照片和观察栏上方的环境比一比。':'老师示范后，你再把这张放进去。','no');if(misses[c.id]>=3)K.highlight(expect[index]==='land'?'#land-zone':'#water-zone');return;}
    c.classList.remove('selected');c.classList.add('placed');K.$(kind==='land'?'#land-slots':'#water-slots').appendChild(c);selected=null;done++;K.levels(3,done);K.star(1,target);K.sfx.ok();K.say('照片留在观察栏，可以并排比较。','ok');
    if(cards.every(function(x){return x.classList.contains('placed');}))K.finish({title:'观察板排好了',sub:'比较的是照片中的环境，不是所有植物。',again:reset});
  }
  cards.forEach(function(c){K.drag(c,{enabled:function(){return K.started&&loaded&&!c.classList.contains('placed');},targets:function(){return zones;},onTap:select,onDrop:place});});
  zones.forEach(function(z){z.addEventListener('click',function(){if(selected)place(selected,z);});z.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();if(selected)place(selected,z);}});});
  K.onStart=reset;K.onState=function(state){if(state.demo){select(cards[0]);place(cards[0],land);K.say('示范：看照片里的土，把它放到土地栏。');}if(state.practice)reset();};
  K.ready({emoji:'🌱',title:'植物环境观察台',sub:'拖动照片，或者先点照片再点观察栏。'});
})();
