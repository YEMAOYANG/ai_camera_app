(function(){
 'use strict';
 var K=window.K, phase=0, misses=0, busy=false, demo=false, clip=null;
 var photos={flag:'__IMG:flag-stadium__',gate:'__IMG:gate-sunset__',kite:'__IMG:kite__',castle:'__IMG:castle__'};
 var models=['__IMG:flag-school__','__IMG:gate-front__'];
 var names=['五星红旗','北京天安门'];
 var clips={flag:'/api/classroom-media/__STAGE__/media/tts-p04-14-2e6b8000758311fcd53d762f90860058d3b37ff0ed3b00c8f01b24651609461d.wav',gate:'/api/classroom-media/__STAGE__/media/tts-p04-15-f4311eed46237aff2996c268b82e5e1bf40df0d150e755562b5850c039b98388.wav',hint:'/api/classroom-media/__STAGE__/media/tts-p04-13-5e4cfb84a6d03fda521992750ee67f2193c33492baa786143cfbeaada3d0da55.wav',hint2:'/api/classroom-media/__STAGE__/media/tts-p04-7-b7727fb1c0c115538d9768ed64009a9d71f906d8e434c079396e8ca6d2d2b732.wav'};
 K.hud({icon:'▧',title:'照片展框',levels:2});K.owl();
 function stop(){if(clip){clip.pause();clip.currentTime=0;clip=null;}}
 function speak(key){stop();if(clips[key].indexOf('__CLIP:')===0)return;clip=new Audio(clips[key]);clip.play().catch(function(){K.say('声音暂时打不开，请大人帮助。');});}
 function resetScore(){K.stars=0;K.$('#star-n').textContent='0';}
 function imageFailure(){busy=true;K.$('#gallery-retry').classList.remove('hide');K.say('图片暂时打不开，请点圆箭头重试。','no');}
 function watchImages(){K.$$('img').forEach(function(img){img.onerror=imageFailure;});}
 function show(){
  busy=false;misses=0;K.$('#gallery-chosen').classList.add('hide');K.$('#gallery-feature').classList.remove('hide');
  K.$('#gallery-model').src=models[phase];K.$('#gallery-name').textContent=names[phase];
  K.$('#gallery-model').alt=names[phase]+'参考图';K.$('#gallery-retry').classList.add('hide');
  K.levels(2,phase);var box=K.$('#gallery-choices');box.innerHTML='';
  var correct=phase===0?'flag':'gate';
  K.shuffle([correct,'kite','castle']).forEach(function(key){
   var b=K.el('button','gallery-photo',null,box);b.setAttribute('aria-label',key===correct?names[phase]:key==='kite'?'风筝照片':'城堡照片');
   var img=K.el('img','',null,b);img.src=photos[key];img.alt=b.getAttribute('aria-label');
   b.onclick=function(){choose(key,b);};
   K.drag(b,{enabled:function(){return !busy&&!demo;},targets:function(){return [K.$('#gallery-target')];},onDrop:function(el,target){if(target)choose(key,b);}});
  });watchImages();K.say('看看参考图，移动同一种东西的照片。');
 }
 function choose(key,button){
  if(busy||demo||phase>1)return;
  if(key!==(phase===0?'flag':'gate')){
   misses++;K.sfx.no();K.shake(button);
   K.say(misses===1?'再看一眼，找同一种东西。':misses===2?'听一次名字，看看颜色和外形。':'再比较主体，背景不一样也可以。','no');
   speak(misses===1?'hint':'hint2');
   if(misses>=3)K.pop(K.$('#gallery-example'));
   return;
  }
  busy=true;stop();button.classList.add('selected');K.$('#gallery-chosen').src=photos[key];K.$('#gallery-chosen').classList.remove('hide');K.$('#gallery-feature').classList.add('hide');
  K.sfx.ok();K.star(1);K.say('照片已经进入展框。','ok');
  setTimeout(function(){if(phase===0){phase=1;show();}else{phase=2;K.levels(2,2);K.finish({title:'照片入展了',sub:'你完成了两次图片选择',again:reset});}},850);
 }
 function reset(){stop();phase=0;demo=false;resetScore();show();}
 K.onStart=reset;
 K.onState=function(s){
  if(s.mode==='demo'){stop();demo=true;busy=true;K.$('#gallery-chosen').src='__IMG:flag-school__';K.$('#gallery-chosen').classList.remove('hide');K.$('#gallery-feature').classList.add('hide');K.say('老师正在示范比较照片。');}
  if(s.mode==='play'){reset();}
 };
 K.$('#gallery-listen').onclick=function(){if(!demo&&phase<2)speak(phase===0?'flag':'gate');};
 K.$('#gallery-retry').onclick=function(){reset();};
 K.ready({title:'把照片送进展框',sub:'先看参考图，再听要求'});watchImages();
 window.addEventListener('pagehide',stop);
})();
