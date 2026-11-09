(function(){
var busy=false,demonstrating=false,mediaBroken=false,miss=0,timer,taskAudio;
var taskAudioUrl='/api/classroom-media/g1-math-e1463f357599ba1e-release-v1/media/tts-p02-13-403bb7a0458a0d9e324afc4c4e1b569842f39d15da3addcdcc3a1a20ab8fb982.wav';
var pictures={room:'__IMG:room__',book:'__IMG:book__',sand:'__IMG:sand__',paint:'__IMG:paint__'};
var descriptions={room:'幼儿园分享角',book:'孩子在读书角看绘本',sand:'孩子在沙池堆小山',paint:'孩子在桌边画画'};
K.hud({icon:'听',title:'听懂伙伴说的事',levels:1});K.owl();K.ready({emoji:'听',title:'听懂伙伴说的事',sub:'先听一听，再选图片'});
function stopAudio(){
 var previous=taskAudio;
 taskAudio=null;
 if(previous)previous.pause();
}
function replayTask(){
 stopAudio();
 var clip=new Audio(taskAudioUrl);
 taskAudio=clip;
 function clear(){if(taskAudio===clip)taskAudio=null}
 function playbackFailed(){
  if(taskAudio!==clip)return;
  clear();
  K.say('声音暂时不能播放，请重开本页。','no');
 }
 clip.addEventListener('ended',clear,{once:true});
 clip.addEventListener('error',playbackFailed,{once:true});
 clip.play().catch(playbackFailed);
}
function show(key){var picture=K.$('#window-picture');picture.src=pictures[key];picture.alt=descriptions[key]}
function reset(){clearTimeout(timer);stopAudio();busy=false;demonstrating=false;miss=0;K.stars=0;K.$('#star-n').textContent='0';K.levels(1,0);K.$$('.picture-choice').forEach(function(b){b.classList.remove('selected')});show('room');K.say('先听老师的讲述，再把对应的图放进分享窗。')}
function choose(key){if(busy||demonstrating||mediaBroken)return;if(key!=='sand'){miss++;K.sfx.no();K.shake(K.$('#choice-'+key));K.say(miss===1?'先想想，老师说的是哪件事。':miss===2?'再听一次任务，比较每幅图里的活动。':'把沙池里的活动和老师的话对照。','no');if(miss>2)K.highlight('#choice-sand');return}
busy=true;stopAudio();show(key);K.$('#choice-'+key).classList.add('selected');K.levels(1,1);K.star(1,K.$('#share-window'));K.sfx.ok();K.say('这幅图和听到的内容相同。','ok');timer=setTimeout(function(){K.finish({title:'听懂了这次的讲述',sub:'再把你的小事说给大人听',again:reset})},1000)}
['book','sand','paint'].forEach(function(key){K.$('#choice-'+key).onclick=function(){choose(key)}});
K.$('#replay-task').onclick=replayTask;
K.$$('img').forEach(function(img){img.onerror=function(){mediaBroken=true;K.$('#media-problem').classList.remove('hide');K.$$('.picture-choice').forEach(function(b){b.disabled=true})}});
K.onStart=reset;K.onState=function(state){if(state.demo){clearTimeout(timer);stopAudio();demonstrating=true;busy=false;show('book');K.$('#choice-book').classList.add('selected');K.say('老师示范：听到看绘本，分享窗出现读书角。')}if(state.play)reset()};
window.addEventListener('pagehide',stopAudio);show('room');
})();
