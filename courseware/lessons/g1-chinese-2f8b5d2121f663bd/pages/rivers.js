(function(){
 'use strict';
 var K=window.K,phase=0,opened=0,busy=false,demo=false,clip=null;
 var pictures=['__IMG:yangtze-gorge__','__IMG:yellow-falls__'];
 var names=['长江','黄河'];var clips=['/api/classroom-media/__STAGE__/media/tts-p07-10-51fadb12144bf56cb6e72949a9b8899fcbb1dd581dc6bffd2956927a447589d1.wav','/api/classroom-media/__STAGE__/media/tts-p07-11-880ff2fe923569444cefbabaf9c94a25ebf98c828e106061e1212fb103e1d584.wav'];
 K.hud({icon:'▧',title:'山河观察窗',levels:2});K.owl();
 function stop(){if(clip){clip.pause();clip.currentTime=0;clip=null;}}
 function speak(){stop();if(clips[phase].indexOf('__CLIP:')===0)return;clip=new Audio(clips[phase]);clip.play().catch(function(){K.say('声音暂时打不开，请大人帮助。');});}
 function render(){
  busy=false;opened=0;K.$('#river-picture').src=pictures[phase];K.$('#river-picture').alt=names[phase]+'代表性景色';K.$('#river-name').textContent=names[phase];
  K.levels(2,phase);K.$('#river-retry').classList.add('hide');var box=K.$('#river-windows');box.innerHTML='';
  for(var i=1;i<=6;i++){
   var b=K.el('button','river-window',null,box);b.id='river-window-'+i;b.setAttribute('aria-label','打开第'+i+'块观察窗');
   b.onclick=function(){uncover(this);};
  }
  K.say('把每一块窗打开，仔细观察整幅河流图。');
 }
 function uncover(button){
  if(busy||demo||button.classList.contains('opened'))return;
  button.classList.add('opened');opened++;K.sfx.pick();
  if(opened===6){busy=true;stop();K.star(1,K.$('#river-frame'));K.sfx.ok();K.say('整幅图画看清楚了，名字说给大人听。','ok');
   setTimeout(function(){if(phase===0){phase=1;render();}else{phase=2;K.levels(2,2);K.finish({title:'山河观察完成',sub:'朗读表现请大人听一听',again:reset});}},1000);
  }
 }
 function reset(){stop();phase=0;demo=false;K.stars=0;K.$('#star-n').textContent='0';render();}
 K.onStart=reset;
 K.onState=function(s){
  if(s.demo===true){demo=true;busy=true;K.$('#river-window-1').classList.add('opened');K.say('老师先打开一块，示范怎样观察。');}
  if(s.demo===false){reset();}
 };
 K.$('#river-listen').onclick=function(){if(!demo&&phase<2)speak();};
 K.$('#river-picture').onerror=function(){busy=true;K.$('#river-retry').classList.remove('hide');K.say('图片暂时打不开，请点圆箭头重试。','no');};
 K.$('#river-retry').onclick=reset;
 K.ready({title:'揭开山河画面',sub:'动手看清完整的河流图'});
 window.addEventListener('pagehide',stop);
})();
