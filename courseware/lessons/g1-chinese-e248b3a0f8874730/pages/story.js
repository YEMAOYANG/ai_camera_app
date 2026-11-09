(function(){
'use strict';
var cards=K.$$('.story-choice'),target=K.$('#story-target'),scene=K.$('#story-result');
var round=0,miss=0,busy=false,selected=null,timer=null,clip=null;
var urls={craft:'__IMG:craft__',help:'__IMG:help__',grab:'__IMG:grab__',ignore:'__IMG:ignore__',welcome:'__IMG:welcome__',leftout:'__IMG:leftout__'};
var rounds=[{before:'ignore',good:'help',choices:['help','grab','ignore'],text:'第一段故事，伙伴的画笔掉在地上了。',voice:'/api/classroom-media/__STAGE__/media/tts-p09-11-8f54417582c11ba0294fe43398c6342ac8a0abb76ad72cc0373c8916179831f2.wav'},{before:'leftout',good:'welcome',choices:['leftout','ignore','welcome'],text:'第二段故事，新朋友还站在游戏圈外。',voice:'/api/classroom-media/__STAGE__/media/tts-p09-12-df45f79f118e2be13ca21b98f6b1d5060c6ba5eab179fd125861901ac488b7fb.wav'}];
K.hud({icon:'▤',title:'把故事变友好',levels:2});K.owl();K.ready({emoji:'▤',title:'把故事变友好',sub:'想想怎样关心伙伴'});
function stopAudio(){if(clip){clip.pause();clip=null}}
function speak(){stopAudio();clip=new Audio(rounds[round].voice);clip.play().catch(function(){K.say('声音暂时没打开，可以点喇叭再听。')})}
function clearSelection(){selected=null;cards.forEach(function(c){c.classList.remove('selected');c.disabled=false})}
function showRound(){busy=false;miss=0;clearSelection();scene.src=urls[rounds[round].before];cards.forEach(function(c,i){c.dataset.key=rounds[round].choices[i];K.$('img',c).src=urls[c.dataset.key]});K.levels(2,round);K.say(rounds[round].text)}
function reset(){clearTimeout(timer);stopAudio();round=0;K.stars=0;K.$('#star-n').textContent='0';var f=K.$('#finish');if(f)f.classList.add('gone');showRound()}
function select(c){if(!K.started||busy||c.disabled)return;clearSelection();selected=c;c.classList.add('selected');K.sfx.pick()}
function drop(c){if(!K.started||busy||!c||c.disabled)return;if(c.dataset.key!==rounds[round].good){miss++;K.shake(c);K.sfx.no();clearSelection();K.say(miss===1?'再看看，这样做让伙伴舒服吗？':miss===2?'先想谁需要关心，再看大家的动作。':'老师用边框示范友好的做法。','no');if(miss===1)speak();if(miss>=3)cards.filter(function(x){return x.dataset.key===rounds[round].good}).forEach(function(x){K.highlight('#'+x.id)});return}
 busy=true;stopAudio();scene.src=urls[c.dataset.key];cards.forEach(function(x){x.disabled=true});K.sfx.ok();K.star(1,scene);K.say(round===0?'伙伴得到了帮助。':'新伙伴也参加了活动。','ok');K.levels(2,round+1);timer=setTimeout(function(){if(round===1){K.finish({title:'故事变友好了',sub:'尊重伙伴，关心需要',again:reset})}else{round++;showRound();speak()}},1000)}
cards.forEach(function(c){c.addEventListener('click',function(){select(c)});K.drag(c,{enabled:function(){return K.started&&!busy&&!c.disabled},targets:function(){return[target]},onTap:function(){select(c)},onDrop:function(el,to){if(to===target)drop(el);else{K.say('图片回到原处，可以再放。');K.sfx.drop()}}})});target.addEventListener('click',function(){drop(selected)});K.$('#story-listen').addEventListener('click',function(){if(!busy)speak()});
K.onStart=reset;K.onState=function(s){if(s.mode==='demo'){reset();busy=true;scene.src=urls.craft;K.say('老师示范：留出位置，一起创作。')}if(s.mode==='play')reset()};
var error=K.$('#story-image-error');K.$$('img').forEach(function(im){im.addEventListener('error',function(){error.classList.remove('hide')})});K.$('button',error).addEventListener('click',function(){error.classList.add('hide');K.$$('img').forEach(function(im){var old=im.src;im.src='';im.src=old})});
window.addEventListener('pagehide',function(){clearTimeout(timer);stopAudio()});
})();
