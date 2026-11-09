(function(){
var busy=false,demonstrating=false,mediaBroken=false,miss=0,timer,taskAudio;
var taskAudioUrl='/api/classroom-media/g1-math-e1463f357599ba1e-release-v1/media/tts-p04-11-7f117ce2890db5dd5126123fbd77e55911ccb3f1298d3c98d8f9fb05e5f9eb8c.wav';
K.hud({icon:'听',title:'把倾听伙伴请回来',levels:1});K.owl();K.ready({emoji:'听',title:'把倾听伙伴请回来',sub:'拖到倾听席，也可以点一下'});
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
function show(key){var scene=K.$('#seat-scene'),listening=key==='listen';scene.src=listening?'__IMG:listen__':'__IMG:distract__';scene.alt=listening?'男孩面向正在讲话的女孩安静倾听':'女孩还在说话，男孩转头玩小车'}
function reset(){clearTimeout(timer);stopAudio();busy=false;demonstrating=false;miss=0;K.stars=0;K.$('#star-n').textContent='0';K.levels(1,0);K.$$('.listener-card').forEach(function(b){b.classList.remove('placed')});show('distract');K.say('把认真听的伙伴请到倾听席。')}
function choose(key){if(busy||demonstrating||mediaBroken)return;if(key!=='listen'){miss++;K.sfx.no();K.shake(K.$('#candidate-'+key));K.say(miss===1?'看一看，伙伴还在说话。':miss===2?'想想怎样不漏听他讲的事情。':'看看谁朝向说话的人，没有玩别的。','no');if(miss>2)K.highlight('#candidate-listen');return}
busy=true;stopAudio();show('listen');K.$('#candidate-listen').classList.add('placed');K.levels(1,1);K.star(1,K.$('#listening-seat'));K.sfx.ok();K.say('伙伴回来了，可以继续认真听。','ok');timer=setTimeout(function(){K.finish({title:'分享可以继续了',sub:'真实倾听还要在生活中练习',again:reset})},1000)}
['listen','distract'].forEach(function(key){var button=K.$('#candidate-'+key);K.drag(button,{enabled:function(){return !busy&&!demonstrating&&!mediaBroken},targets:function(){return [K.$('#listening-seat')]},onDrop:function(el,target){if(target)choose(key)},onTap:function(){choose(key)}});button.addEventListener('keydown',function(event){if(event.key==='Enter'||event.key===' '){event.preventDefault();choose(key)}})});
K.$('#replay-listener').onclick=replayTask;
K.$$('img').forEach(function(img){img.onerror=function(){mediaBroken=true;K.$('#listener-media-problem').classList.remove('hide');K.$$('.listener-card').forEach(function(b){b.disabled=true})}});
K.onStart=reset;K.onState=function(state){if(state.demo){clearTimeout(timer);stopAudio();busy=false;demonstrating=true;show('listen');K.$('#candidate-listen').classList.add('placed');K.say('老师示范：面向伙伴，等他说完。')}if(state.play)reset()};window.addEventListener('pagehide',stopAudio);show('distract');
})();
