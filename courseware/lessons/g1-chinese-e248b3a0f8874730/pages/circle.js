(function(){
'use strict';
var cards=K.$$('.circle-child'),tray=K.$('#circle-tray'),zone=K.$('#circle-zone'),seats=K.$('#circle-seats'),line=K.$('#circle-connection');
var round=0,miss=0,busy=false,selected=null,timer=null,clip=null,counts=[3,4];
K.hud({icon:'○',title:'让每位伙伴都加入',levels:2});K.owl();K.ready({emoji:'○',title:'让每位伙伴都加入',sub:'把邀请做出来'});
function stopAudio(){if(clip){clip.pause();clip=null}}
function speak(){stopAudio();clip=new Audio('/api/classroom-media/__STAGE__/media/tts-p07-10-9f01d9ee411c8314f3dc5c1749116574e93223c8eca7ace836444052f78e61e9.wav');clip.play().catch(function(){K.say('声音暂时没打开，可以点喇叭再听。')})}
function clearSelection(){selected=null;cards.forEach(function(c){c.classList.remove('selected')})}
function showRound(){clearSelection();miss=0;busy=false;line.style.opacity='0';cards.forEach(function(c,i){tray.appendChild(c);c.classList.remove('placed');c.classList.toggle('hide',i>=counts[round]);c.disabled=false;c.style.transform=''});K.levels(2,round);K.say('给每位伙伴留位置，一起参与。')}
function reset(){clearTimeout(timer);stopAudio();round=0;K.stars=0;K.$('#star-n').textContent='0';var f=K.$('#finish');if(f)f.classList.add('gone');showRound()}
function select(c){if(!K.started||busy||c.disabled)return;clearSelection();selected=c;c.classList.add('selected');K.sfx.pick()}
function place(c){if(!K.started||busy||!c||c.disabled)return;clearSelection();seats.appendChild(c);c.classList.add('placed');c.disabled=true;K.sfx.drop();K.pop(c);var left=cards.filter(function(x,i){return i<counts[round]&&!x.classList.contains('placed')});line.style.opacity=String((counts[round]-left.length)/counts[round]);
 if(left.length){K.say('还有伙伴在圈外，想想怎样邀请。');return}busy=true;K.star(1,zone);K.sfx.ok();K.say('每位伙伴都加入了。','ok');K.levels(2,round+1);timer=setTimeout(function(){if(round===1){K.finish({title:'伙伴都加入了',sub:'共同参与，彼此尊重',again:reset})}else{round++;showRound();speak()}},950)}
cards.forEach(function(c){c.addEventListener('click',function(){select(c)});K.drag(c,{enabled:function(){return K.started&&!busy&&!c.disabled&&!c.classList.contains('hide')},targets:function(){return[zone]},onTap:function(){select(c)},onDrop:function(el,to){if(to===zone)place(el);else{miss++;K.sfx.drop();K.say(miss===1?'伙伴回到原处，可以再邀请。':miss===2?'看看伙伴还没有加入哪里。':'老师示范活动圈的位置。','no');if(miss>=3)K.highlight('#circle-zone')}}})});
zone.addEventListener('click',function(){place(selected)});K.$('#circle-listen').addEventListener('click',speak);
K.onStart=reset;K.onState=function(s){if(s.mode==='demo'){reset();seats.appendChild(cards[0]);cards[0].classList.add('placed');cards[0].disabled=true;line.style.opacity='.25';busy=true;K.say('老师示范：邀请一位伙伴进入共同活动圈。')}if(s.mode==='play')reset()};
var error=K.$('#circle-image-error'),source=K.$('#circle-source');source.addEventListener('error',function(){error.classList.remove('hide')});K.$('button',error).addEventListener('click',function(){error.classList.add('hide');var old=source.src;source.src='';source.src=old});
window.addEventListener('pagehide',function(){clearTimeout(timer);stopAudio()});
})();
