(function(){
var level=0,miss=0,busy=false,selected=false,timer;
K.hud({icon:'🌿',title:'找出水字旁',levels:2});K.owl();
K.ready({img:'__IMG:water-town__',emoji:'🌿',title:'找出水字旁',sub:'听一听，看一看'});
var card=K.$('#jiang'),river=K.$('#river'),rad=K.$('#water-radical'),choices=K.$('#choices');
function reset(){clearTimeout(timer);level=0;miss=0;busy=false;selected=false;K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);rad.classList.remove('shown');river.classList.remove('success','hint');choices.append(river,K.$('#mountain'),K.$('#tree'));K.say('把江送到水边。')}
function choose(el){if(busy)return;if(el!==river){miss++;K.sfx.no();K.shake(card);K.say(miss===1?'看看哪里有流动的水。':miss===2?'找蓝色水纹。':'看，江来到河边。','no');if(miss===2)choices.classList.add('look');if(miss>=3){river.classList.add('hint');timer=setTimeout(function(){river.classList.remove('hint')},1800)}return}busy=true;selected=false;card.classList.remove('selected');river.classList.add('success');rad.classList.add('shown');K.sfx.ok();K.star(1,river);K.say('江来到河边，看看三点水。','ok');timer=setTimeout(function(){level++;if(level===2){K.levels(2,2);K.finish({title:'找到水边',sub:'江的三点水提示水义',again:reset});return}miss=0;busy=false;rad.classList.remove('shown');river.classList.remove('success');choices.append(K.$('#tree'),river,K.$('#mountain'));K.levels(2,level);K.say('再找一次水边。')},1700)}
card.addEventListener('click',function(){selected=!selected;card.classList.toggle('selected',selected)});K.drag(card,{onDrop:function(el,target){if(target)choose(target)},targets:function(){return K.$$('.place')}});K.$$('.place').forEach(function(el){el.addEventListener('click',function(){choose(el)})});
K.onState=function(state){if(state.demo==='river'){clearTimeout(timer);busy=true;rad.classList.add('shown');river.classList.add('success');K.say('江来到河边。');timer=setTimeout(function(){rad.classList.remove('shown');river.classList.remove('success');busy=false;K.say('你来试试。')},6500)}};K.onStart=function(){K.say('把江送到水边。')};
})();
