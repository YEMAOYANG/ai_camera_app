(function(){
'use strict';
var QUESTION_AUDIO = {}; // AUDIO_REFS
var rounds=[
{prompt:'第一关，材料应该留在哪里？',initial:'__IMG:goal-flag__',initialAlt:'等待使用和收纳的工作台材料',options:[{image:'__IMG:unsafe-taste__',alt:'把手工珠子举到嘴边'},{image:'__IMG:safe-store__',alt:'把材料放进桌上盘子'}],answer:1,hint:'看看手里的材料，嘴巴和盘子哪里更合适？'},
{prompt:'第二关，活动后该先做什么？',initial:'__IMG:test-flag__',initialAlt:'完成纸旗后的工作台',options:[{image:'__IMG:wash-hands__',alt:'在洗手池用水和泡沫洗手'},{image:'__IMG:unsafe-snack__',alt:'手上还有胶泥就去拿饼干'}],answer:0,hint:'想想刚做过活动的双手，准备好拿食物了吗？'}];
var level=0,mode='play',busy=false,wrong=0,records=[],audio=null;
var cards=[K.$('#safety-option-0'),K.$('#safety-option-1')];
function stopAudio(){if(audio){audio.pause();audio=null}}
function speak(){stopAudio();var src=QUESTION_AUDIO[rounds[level].prompt];if(!src){K.say('原声暂时未到，请稍后重听。');return}audio=new Audio(src);audio.addEventListener('error',function(){K.say('声音暂时没到，请点重听目标。')});audio.play().catch(function(){K.say('点重听目标，就能再听一次。')})}
function setImage(el,src,alt){el.alt=alt;el.src=src;el.onerror=function(){K.$('#safety-error').hidden=false}}
function draw(){var r=rounds[level];K.$('#play').dataset.mode=mode;K.$('#play').dataset.level=String(level);setImage(K.$('#safety-scene'),r.initial,r.initialAlt);cards.forEach(function(c,i){setImage(c.querySelector('img'),r.options[i].image,r.options[i].alt);c.setAttribute('aria-label',r.options[i].alt);c.disabled=mode==='demo';c.classList.remove('chosen')});K.$('#safety-next').disabled=true;K.$('#safety-stamps').innerHTML=records.map(function(o){return '<img src="'+o.image+'" alt="'+o.alt+'">'}).join('');K.levels(rounds.length,level);busy=false;wrong=0;K.say(mode==='demo'?'看老师留意动作和材料。':r.prompt)}
function choose(card,index){if(mode!=='play'||busy||!K.$('#safety-error').hidden)return;var r=rounds[level];if(index!==r.answer){wrong++;K.sfx.no();K.shake(card);K.say(wrong===1?'先看清手和嘴正在做什么。':r.hint,'no');return}busy=true;stopAudio();card.classList.add('chosen');var selected=r.options[index];setImage(K.$('#safety-scene'),selected.image,selected.alt);records.push(selected);K.star(1,card);K.sfx.ok();K.$('#safety-next').disabled=false;K.say('安全的行动已经送到工作区。','ok')}
cards.forEach(function(card,i){K.drag(card,{enabled:function(){return mode==='play'&&!busy},targets:function(){return [K.$('#safety-zone')]},onTap:function(){choose(card,i)},onDrop:function(el,target){if(target)choose(card,i)}});card.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(card,i)}})});
K.$('#safety-listen').addEventListener('click',function(){if(mode==='play')speak()});
K.$('#safety-next').addEventListener('click',function(){if(!busy)return;level++;if(level>=rounds.length){stopAudio();K.levels(rounds.length,rounds.length);K.finish({title:'工作区整理好了',sub:'屏幕里的安全选择完成了，生活中还要坚持。',again:reset});return}draw();speak()});
K.$('#safety-retry').addEventListener('click',function(){K.$('#safety-error').hidden=true;draw()});
function reset(){stopAudio();level=0;mode='play';records=[];K.stars=0;K.$('#star-n').textContent='0';draw()}
K.onStart=function(){draw()};
K.onState=function(state){stopAudio();if(state.mode==='demo'){mode='demo';level=Math.max(0,Math.min(1,Number(state.level)||0));records=[];draw()}else if(state.mode==='play'){reset();speak()}};
window.addEventListener('pagehide',stopAudio);
K.hud({icon:'◎',title:'安全收好',levels:rounds.length});K.owl();K.ready({title:'安全收好，干净结束',sub:'把安全的行动图片送到工作区。',img:'__IMG:safe-store__',emoji:'◎'});draw();
})();

