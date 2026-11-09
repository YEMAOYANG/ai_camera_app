(function(){
var chars=['江','南','可','采','莲','戏','间','东','北'];
var level=0,miss=0,busy=false,timer,answer=0;
var buttons=K.$$('.picture'),card=K.$('#character'),target=K.$('#target-char'),grass=K.$('#grass-radical'),fish=K.$('#fish');
K.hud({icon:'字',title:'莲叶上找同一个字',levels:9});K.owl();K.ready({emoji:'◌',title:'莲叶上找同一个字',sub:'看大字，逐笔比一比'});
function positionFish(index){var b=buttons[index],r=b.getBoundingClientRect(),p=K.$('#play').getBoundingClientRect();fish.style.left=((r.left-p.left+r.width/2)/(K.scale||1)-110)+'px';fish.style.top=((r.top-p.top+r.height*.70)/(K.scale||1))+'px';fish.classList.add('swim')}
function setChoices(values){buttons.forEach(function(b,i){K.$('span',b).textContent=values[i];b.dataset.char=values[i];b.classList.remove('success','hint')})}
function round(){clearTimeout(timer);busy=false;miss=0;target.textContent=chars[level];grass.classList.remove('shown');answer=(level*2)%3;var others=[chars[(level+3)%9],chars[(level+6)%9]],values=others.slice();values.splice(answer,0,chars[level]);setChoices(values);fish.style.left='520px';fish.style.top='365px';fish.classList.remove('swim');K.levels(9,level);K.say('看大字，逐笔比较莲叶上的字')}
function reset(){level=0;K.stars=0;K.$('#star-n').textContent='0';round()}
function choose(b){if(!K.started||busy)return;if(b.dataset.char!==chars[level]){miss++;K.sfx.no();K.shake(b);K.say(miss===1?'先看大字的第一笔':'从上到下逐笔比较','no');if(miss>=3)buttons[answer].classList.add('hint');return}busy=true;b.classList.add('success');positionFish(buttons.indexOf(b));if(chars[level]==='莲')grass.classList.add('shown');K.sfx.ok();K.star(1,b);K.say('两个字完全相同','ok');timer=setTimeout(function(){level++;if(level===chars.length){K.levels(9,9);K.finish({title:'九组字都配好了',sub:'再玩一次',again:reset})}else round()},1250)}
buttons.forEach(function(b){b.addEventListener('click',function(){choose(b)})});
K.drag(fish,{enabled:function(){return K.started&&!busy},targets:function(){return buttons},onTap:function(){K.sfx.pick();K.say('把小鱼送到相同的字旁')},onDrop:function(el,b){if(b)choose(b)}});
fish.addEventListener('keydown',function(e){if((e.key==='Enter'||e.key===' ')&&!busy){e.preventDefault();K.say('点一片莲叶来选择')}});card.addEventListener('click',function(){card.classList.toggle('selected')});
K.onState=function(state){if(state.demo==='lotus'){clearTimeout(timer);busy=true;target.textContent='莲';answer=0;setChoices(['莲','江','可']);grass.classList.add('shown');positionFish(0);buttons[0].classList.add('success');K.say('大字和莲叶上的莲完全相同');}if(state.phase==='play')reset()};
K.onStart=reset;round();
})();
