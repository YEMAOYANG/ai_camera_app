(function(){
var words=['东','西','南','北'],round=0,miss=0,busy=false,timer;
var fish=K.$('#moving-fish'),word=K.$('#direction-word'),labels=K.$('#direction-labels'),zones=K.$$('.water-zone');
K.hud({icon:'字',title:'小鱼游向哪里',levels:4});K.owl();K.ready({emoji:'◌',title:'小鱼游向哪里',sub:'听方位字，移动小鱼'});
function center(){fish.style.left='432px';fish.style.top='220px'}
function place(zone){fish.style.left=(zone.offsetLeft+22)+'px';fish.style.top=(zone.offsetTop+22)+'px'}
function clearMarks(){zones.forEach(function(z){z.classList.remove('correct','hint')})}
function showRound(){clearTimeout(timer);busy=false;miss=0;clearMarks();center();fish.disabled=false;zones.forEach(function(z){z.disabled=false});word.textContent=words[round];K.levels(4,round);K.say('想想这个方向，把小鱼送过去。')}
function reset(){round=0;K.stars=0;K.$('#star-n').textContent='0';labels.classList.add('faded');showRound()}
function choose(z){if(!K.started||busy)return;if(z.dataset.direction!==words[round]){miss++;K.sfx.no();K.shake(z);K.say(miss===1?'先想字的意思，再想位置。':miss===2?'回想老师讲的这张方位板。':'看水面边框的提示，再送一次。','no');if(miss>=3){zones.forEach(function(a){a.classList.toggle('hint',a.dataset.direction===words[round])})}return}
 busy=true;fish.disabled=true;zones.forEach(function(a){a.disabled=true});place(z);z.classList.add('correct');K.sfx.ok();K.star(1,z);K.say('小鱼游到了这个方向。','ok');timer=setTimeout(function(){round++;if(round===4){K.levels(4,4);K.finish({title:'四方都游到了',sub:'字和位置连起来了',again:reset})}else showRound()},1150)}
zones.forEach(function(z){z.addEventListener('click',function(){choose(z)})});
K.drag(fish,{enabled:function(){return K.started&&!busy},targets:function(){return zones},onTap:function(){K.say('点一片水面，送小鱼过去。');K.sfx.pick()},onDrop:function(el,z){if(z)choose(z);else K.say('送到一片水面上，再松手。')}});
K.onStart=reset;K.onState=function(s){if(s.demo==='center'){clearTimeout(timer);busy=true;fish.disabled=true;zones.forEach(function(z){z.disabled=true});clearMarks();center();labels.classList.remove('faded');K.say('间：想象小鱼在莲叶之间。')}if(s.phase==='play')reset()};
})();
