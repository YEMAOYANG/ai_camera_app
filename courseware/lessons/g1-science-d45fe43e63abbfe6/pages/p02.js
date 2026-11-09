(function(){
'use strict';
var QUESTION_AUDIO = {}; // AUDIO_REFS
var methods={
observe:{label:'观察',image:'__IMG:method-observe__',alt:'孩子仔细观察叶片'},
experiment:{label:'实验',image:'__IMG:method-experiment__',alt:'孩子动手试验不同纸片'},
make:{label:'制作',image:'__IMG:method-make__',alt:'孩子动手制作纸旗'},
measure:{label:'测量',image:'__IMG:method-measure__',alt:'孩子用尺子测量木棒'},
reference:{label:'查资料',image:'__IMG:method-reference__',alt:'孩子与成人查阅自然图鉴'}};
var rounds=[
{image:'__IMG:goal-leaf__',alt:'不同边缘的叶片',question:'叶片边缘哪里不同？先把问题说清楚。',answer:'observe',choices:['observe','make','reference'],hint:'想想怎样才能把细节看清楚。'},
{image:'__IMG:goal-paper__',alt:'等待比较的不同纸片',question:'想知道两种纸遇水后有什么变化。',answer:'experiment',choices:['measure','experiment','observe'],hint:'想想只看纸片，能看到遇水后的变化吗？'},
{image:'__IMG:goal-flag__',alt:'想做成的小纸旗和待用材料',question:'想把这些材料做成一面纸旗。',answer:'make',choices:['reference','measure','make'],hint:'目标是把材料变成作品。'},
{image:'__IMG:goal-stick__',alt:'长度不同的木棒',question:'想知道这两根木棒哪根长。',answer:'measure',choices:['measure','make','reference'],hint:'你要得到的是长度的信息。'},
{image:'__IMG:goal-flower__',alt:'还不知道名字的紫色花朵',question:'想查找这朵花的名字。',answer:'reference',choices:['experiment','reference','observe'],hint:'单靠自己看，还需要从哪里找信息？'}];
var level=0,mode='play',busy=false,wrongs=0,records=[],audio=null;
var cards=[0,1,2].map(function(i){return K.$('#method-choice-'+i)});
function stopAudio(){if(audio){audio.pause();audio=null}}
function speak(){stopAudio();var src=QUESTION_AUDIO[rounds[level].question];if(!src){K.say('原声暂时未到，请稍后重听。');return}audio=new Audio(src);audio.addEventListener('error',function(){K.say('声音暂时没到，请点重听目标。')});audio.play().catch(function(){K.say('点重听目标，就能再听一次。')})}
function image(el,src,alt){el.alt=alt;el.src=src;el.onerror=function(){K.$('#method-error').hidden=false}}
function draw(){
K.$('#play').dataset.mode=mode;K.$('#play').dataset.level=String(level);
var r=rounds[level];image(K.$('#method-goal-image'),r.image,r.alt);
K.$('#method-found').hidden=true;K.$('#method-found').innerHTML='';
cards.forEach(function(card,i){var key=r.choices[i],m=methods[key];card.dataset.key=key;card.disabled=mode==='demo';card.classList.remove('chosen');image(card.querySelector('img'),m.image,m.alt);card.querySelector('span').textContent=m.label;card.setAttribute('aria-label',m.alt)});
K.$('#method-next').disabled=true;
K.$('#method-record').innerHTML=records.map(function(key){var m=methods[key];return '<img src="'+m.image+'" alt="'+m.alt+'">'}).join('');
K.levels(rounds.length,level);K.say(mode==='demo'?'看老师怎样按问题选择方法。':r.question);busy=false;wrongs=0;
}
function choose(card){
if(mode!=='play'||busy||K.$('#method-error').hidden===false)return;
var key=card.dataset.key,r=rounds[level];
if(key!==r.answer){wrongs++;K.sfx.no();K.shake(card);K.say(wrongs===1?'先想想，你需要得到什么信息。':r.hint,'no');K.highlight('#method-goal');return}
busy=true;stopAudio();card.classList.add('chosen');K.$('#method-found').hidden=false;K.$('#method-found').innerHTML='<img src="'+methods[key].image+'" alt="'+methods[key].alt+'">';
records.push(key);K.star(1,card);K.sfx.ok();K.$('#method-next').disabled=false;K.say('方法图片已经放到调查现场。','ok');
}
cards.forEach(function(card){K.drag(card,{enabled:function(){return mode==='play'&&!busy},targets:function(){return [K.$('#method-goal')]},onTap:function(){choose(card)},onDrop:function(el,target){if(target)choose(card)}});card.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(card)}})});
K.$('#method-listen').addEventListener('click',function(){if(mode==='play')speak()});
K.$('#method-next').addEventListener('click',function(){if(!busy)return;level++;if(level>=rounds.length){stopAudio();K.levels(rounds.length,rounds.length);K.finish({title:'办法连上了问题',sub:'你完成了屏幕里的方法匹配。',again:reset});return}draw();speak()});
K.$('#method-retry').addEventListener('click',function(){K.$('#method-error').hidden=true;draw()});
function reset(){stopAudio();level=0;mode='play';records=[];K.stars=0;K.$('#star-n').textContent='0';draw()}
K.onStart=function(){draw()};
K.onState=function(state){stopAudio();if(state.mode==='demo'){mode='demo';level=Math.max(0,Math.min(rounds.length-1,Number(state.level)||0));records=[];draw()}else if(state.mode==='play'){reset();speak()}};
window.addEventListener('pagehide',stopAudio);
K.hud({icon:'◎',title:'方法工作台',levels:rounds.length});K.owl();K.ready({title:'方法工作台',sub:'听目标，把行动图片送到问题现场。',img:'__IMG:cover__',emoji:'◎'});draw();
})();

