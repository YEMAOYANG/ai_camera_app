(function(){
  'use strict';
  var tray=K.$('#seed-tray'),soil=K.$('#soil-box'),paper=K.$('#paper-box'),ghost=K.$('#demo-seed'),seeds=[],selected=null;
  var setupPic=K.$('#observation-picture');
  var counts={soil:0,paper:0},misses=0,loaded=setupPic.complete&&setupPic.naturalWidth>0,finished=false;
  var seedSvg='<svg viewBox="0 0 90 60" aria-hidden="true"><path d="M12 38C8 14 37 4 60 9C87 15 85 45 61 52C39 61 17 55 12 38Z" fill="#669347" stroke="#3B6432" stroke-width="4"/><path d="M31 17Q52 31 64 42" fill="none" stroke="#BDD890" stroke-width="5"/></svg>';
  K.hud({icon:'🌱',title:'准备两组观察',levels:2});K.owl();
  var retry=K.el('button','btn image-retry hide','↻',K.$('#play'));retry.setAttribute('aria-label','重新打开图片');
  retry.addEventListener('click',function(){loaded=false;retry.classList.add('hide');setupPic.src=setupPic.src;K.say('正在重新打开图片，请等一等。');});
  setupPic.addEventListener('load',function(){loaded=true;retry.classList.add('hide');});
  setupPic.addEventListener('error',function(){loaded=false;retry.classList.remove('hide');K.say('图片没打开，点转圈箭头重试。','no');});
  function select(seed){if(!loaded||finished||seed.classList.contains('placed'))return;seeds.forEach(function(s){s.classList.remove('selected');});selected=seed;seed.classList.add('selected');K.sfx.pick();}
  function place(seed,target){
    if(!K.started||!loaded||finished||!seed||seed.classList.contains('placed'))return;
    var key=target===soil?'soil':target===paper?'paper':null;
    if(!key||counts[key]>=4){misses++;K.shake(seed);K.sfx.no();K.say(misses===1?'先看看两个盒子里的种子数量。':misses===2?'每盒四颗，已经满的盒子先停一停。':'数一数，另一个盒子还需要准备。','no');if(misses>=3)K.highlight(counts.soil<4?'#soil-box':'#paper-box');return;}
    var n=counts[key]++;target.appendChild(seed);seed.style.left=(30+(n%2)*150)+'px';seed.style.top=(Math.floor(n/2)*92)+'px';seed.classList.remove('selected');seed.classList.add('placed');selected=null;K.sfx.drop();
    if(counts[key]===4){target.classList.add('full');K.star(1,target);K.sfx.ok();}
    K.levels(2,(counts.soil===4?1:0)+(counts.paper===4?1:0));
    K.say('种子放好了，比较两盒是否同样多。');
    if(seeds.every(function(s){return s.classList.contains('placed');})){finished=true;K.finish({title:'观察计划准备好了',sub:'这只是模型，真实种植和多日变化还待观察。',again:reset});}
  }
  function reset(){counts={soil:0,paper:0};misses=0;selected=null;finished=false;ghost.style.opacity='0';soil.classList.remove('full');paper.classList.remove('full');K.stars=0;K.$('#star-n').textContent='0';seeds.forEach(function(seed,i){tray.appendChild(seed);seed.classList.remove('placed','selected');seed.style.left=(18+i*110)+'px';seed.style.top='6px';seed.style.transform='';});K.levels(2,0);K.say('把种子分进两盒，每盒四颗。');}
  for(var i=0;i<8;i++){var seed=K.el('button','count-seed',seedSvg,tray);seed.id='count-seed-'+(i+1);seed.setAttribute('aria-label','一颗待放的绿豆');seeds.push(seed);K.drag(seed,{enabled:function(el){return K.started&&loaded&&!finished&&!el.classList.contains('placed');},targets:function(){return [soil,paper];},onTap:select,onDrop:place});}
  [soil,paper].forEach(function(z){z.addEventListener('click',function(){if(selected)place(selected,z);});z.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();if(selected)place(selected,z);}});});
  K.onStart=reset;K.onState=function(state){if(state.demo){ghost.style.opacity='.85';K.say('示范：放一颗，数量就多一颗。');}if(state.practice)reset();};
  K.ready({emoji:'🌱',title:'准备两组观察',sub:'土和纸分别准备，数量同样多。'});
})();
