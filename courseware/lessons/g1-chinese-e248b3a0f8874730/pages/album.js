(function(){
'use strict';
var cards=K.$$('.album-photo'),target=K.$('#album-target'),result=K.$('#album-result'),task=K.$('#album-task');
var round=0,miss=0,busy=false,selected=null,timer=null,clip=null;
var rounds=[{key:'family',title:'小家',text:'先把一家人在家里的照片放进家庭页。',voice:'/api/classroom-media/__STAGE__/media/tts-p04-9-83dbc5e331df60e6c2c030a0848d0e47d15b0e06d944a874212f6bfbd3e791ac.wav'},{key:'beijing',title:'北京',text:'下一页，再找首都北京的照片。',voice:'/api/classroom-media/__STAGE__/media/tts-p04-10-c818ab931235598d96ffda0500ece0788a22b19641f46137f9074e4f55ff08af.wav'}];
K.hud({icon:'▣',title:'整理旅行相册',levels:2});K.owl();K.ready({emoji:'▣',title:'整理旅行相册',sub:'听任务，移动照片'});
function stopAudio(){if(clip){clip.pause();clip=null}}
function speak(){stopAudio();clip=new Audio(rounds[round].voice);clip.play().catch(function(){K.say('声音暂时没打开，可以点喇叭再听。')})}
function clearSelection(){selected=null;cards.forEach(function(c){c.classList.remove('selected','hint');c.disabled=false})}
function showRound(){miss=0;busy=false;clearSelection();result.classList.add('hide');task.textContent=rounds[round].title;K.levels(2,round);K.say(rounds[round].text)}
function reset(){clearTimeout(timer);stopAudio();round=0;K.stars=0;K.$('#star-n').textContent='0';var f=K.$('#finish');if(f)f.classList.add('gone');showRound()}
function choose(card){if(!K.started||busy||card.disabled)return;clearSelection();selected=card;card.classList.add('selected');K.sfx.pick()}
function drop(card){
 if(!K.started||busy||!card)return;
 if(card.dataset.key!==rounds[round].key){miss++;K.sfx.no();K.shake(card);card.classList.remove('selected');selected=null;K.say(miss===1?'再想想，这一页记录谁或哪里。':miss===2?'听听任务，再看看照片里的环境。':'老师用边框示范一张，再请你放入。','no');if(miss===1)speak();if(miss>=3)K.highlight('#album-photo-'+rounds[round].key);return}
 busy=true;stopAudio();clearSelection();result.src=K.$('img',card).src;result.classList.remove('hide');cards.forEach(function(c){c.disabled=true});K.sfx.ok();K.star(1,target);K.say('照片放进相册了。','ok');K.levels(2,round+1);
 timer=setTimeout(function(){if(round===1){K.finish({title:'相册整理好了',sub:'家人与首都，记录得清楚',again:reset})}else{round++;showRound();speak()}},950)
}
cards.forEach(function(card){card.addEventListener('click',function(){choose(card)});K.drag(card,{enabled:function(){return K.started&&!busy&&!card.disabled},targets:function(){return [target]},onTap:function(){choose(card)},onDrop:function(el,to){if(to===target)drop(el);else{K.say('照片回到原处，可以再放。');K.sfx.drop()}}})});
target.addEventListener('click',function(){drop(selected)});K.$('#album-listen').addEventListener('click',function(){if(!busy)speak()});
K.onStart=reset;K.onState=function(s){if(s.mode==='demo'){reset();busy=true;task.textContent='一起创作';result.src=K.$('#album-photo-craft img').src;result.classList.remove('hide');K.say('老师示范：把共同创作记录进相册。')}if(s.mode==='play')reset()};
var error=K.$('#album-image-error');K.$$('img').forEach(function(im){im.addEventListener('error',function(){error.classList.remove('hide')})});K.$('button',error).addEventListener('click',function(){error.classList.add('hide');K.$$('img').forEach(function(im){var old=im.src;im.src='';im.src=old})});
window.addEventListener('pagehide',function(){clearTimeout(timer);stopAudio()});
})();
