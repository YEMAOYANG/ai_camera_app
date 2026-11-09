(function(){
'use strict';
var QUESTION_AUDIO = {}; // AUDIO_REFS
var prompt='轮到你，按这次纸旗活动的过程摆图。';
var actions=[{key:'plan',image:'__IMG:plan-flag__',alt:'先想样子和准备材料'},{key:'make',image:'__IMG:make-flag__',alt:'给木棒涂胶，准备贴纸片'},{key:'test',image:'__IMG:test-flag__',alt:'做完后检查作品'}];
var step=0,mode='play',wrong=0,audio=null,finishTimer=null;
var cards=actions.map(function(a){return K.$('#process-'+a.key)});
function stopAudio(){if(audio){audio.pause();audio=null}}
function speak(){stopAudio();var src=QUESTION_AUDIO[prompt];if(!src){K.say('原声暂时未到，请稍后重听。');return}audio=new Audio(src);audio.addEventListener('error',function(){K.say('声音暂时没到，请点重听目标。')});audio.play().catch(function(){K.say('点重听目标，就能再听一次。')})}
function checkImages(){K.$$('img',K.$('#play')).forEach(function(im){im.onerror=function(){K.$('#process-error').hidden=false}})}
function showStage(index){var a=actions[Math.max(0,Math.min(2,index))],im=K.$('#process-stage-image');im.src=a.image;im.alt=a.alt}
function refresh(){K.$('#play').dataset.mode=mode;K.$('#play').dataset.step=String(step);K.levels(3,step);cards.forEach(function(c){c.disabled=mode==='demo'});checkImages()}
function choose(card,target){
if(mode!=='play'||step>=3||!K.$('#process-error').hidden)return;
var expected=actions[step],key=card.dataset.key;
if(key!==expected.key||(target&&target.id!=='process-slot-'+step)){wrong++;K.sfx.no();K.shake(card);K.say(wrong===1?'先看图里的动作，想想前一步准备好了吗？':'先准备材料，再看正在动手还是已经做完。','no');return}
stopAudio();var slot=K.$('#process-slot-'+step+' .slot-image');slot.innerHTML='<img src="'+expected.image+'" alt="'+expected.alt+'">';
card.classList.add('placed');showStage(step);K.star(1,card);K.sfx.ok();step++;wrong=0;refresh();K.say('这一张已经放到过程轨道里。','ok');
if(step===3)finishTimer=setTimeout(function(){K.finish({title:'过程接起来了',sub:'准备、动手和检查都留下了图片记录。',again:reset})},900);
}
cards.forEach(function(card){K.drag(card,{enabled:function(){return mode==='play'&&!card.classList.contains('placed')},targets:function(){return [0,1,2].map(function(i){return K.$('#process-slot-'+i)})},onTap:function(){choose(card)},onDrop:function(el,target){if(target)choose(card,target)}});card.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(card)}})});
function reset(){clearTimeout(finishTimer);stopAudio();mode='play';step=0;wrong=0;K.stars=0;K.$('#star-n').textContent='0';cards.forEach(function(c){c.classList.remove('placed','chosen');c.disabled=false});K.$$('.slot-image').forEach(function(s){s.innerHTML=''});showStage(0);refresh();K.say(prompt)}
K.$('#process-listen').addEventListener('click',function(){if(mode==='play')speak()});
K.$('#process-retry').addEventListener('click',function(){K.$('#process-error').hidden=true;reset()});
K.onStart=function(){refresh()};
K.onState=function(state){clearTimeout(finishTimer);stopAudio();if(state.mode==='demo'){reset();mode='demo';var i=Math.max(0,Math.min(2,Number(state.step)||0));showStage(i);refresh();K.say('看老师怎样回顾这次制作过程。')}else if(state.mode==='play'){reset();speak()}};
window.addEventListener('pagehide',function(){clearTimeout(finishTimer);stopAudio()});
K.hud({icon:'◎',title:'把过程接起来',levels:3});K.owl();K.ready({title:'把过程接起来',sub:'看图里的动作，按这次活动的过程摆好。',img:'__IMG:plan-flag__',emoji:'◎'});refresh();
})();

