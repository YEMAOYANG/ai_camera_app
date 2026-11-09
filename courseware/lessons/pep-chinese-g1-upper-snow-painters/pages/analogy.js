(function(){
var kinds=['chick','dog','duck','horse'],pics={chick:'__IMG:track-chick__',dog:'__IMG:track-dog__',duck:'__IMG:track-duck__',horse:'__IMG:track-horse__'},level=0,miss=0,busy=false,timer;
var source=K.$('#analogy-track'),picture=K.$('#analogy-picture'),targets=K.$$('.likeness');
K.hud({icon:'图',title:'脚印像什么',levels:4});K.owl();K.ready({emoji:'◌',title:'脚印像什么',sub:'看轮廓，找形状相像的图'});
function move(t){var a=t.getBoundingClientRect(),b=K.$('#play').getBoundingClientRect(),k=K.scale||1;source.style.left=((a.left-b.left)/k+10)+'px';source.style.top=((a.top-b.top)/k+48)+'px';source.style.width='145px';source.style.height='145px'}
function show(){clearTimeout(timer);busy=false;miss=0;picture.src=pics[kinds[level]];source.style.left='45px';source.style.top='145px';source.style.width='300px';source.style.height='280px';targets.forEach(function(t){t.classList.remove('correct','hint')});K.levels(4,level);K.say('观察足印轮廓，再想它像什么。')}
function reset(){level=0;K.stars=0;K.$('#star-n').textContent='0';show()}
function choose(t){if(!K.started||busy)return;if(t.dataset.kind!==kinds[level]){miss++;K.sfx.no();K.shake(t);K.say(miss===1?'先看轮廓，不只看颜色。':miss===2?'比较尖长、圆润、宽阔和弯弯的形状。':'看看相似形状的提示，再试一次。','no');if(miss>=3)targets.find(function(x){return x.dataset.kind===kinds[level]}).classList.add('hint');return}busy=true;t.classList.add('correct');move(t);K.star(1,t);K.sfx.ok();K.say('形状相像，足印就能引起联想。','ok');timer=setTimeout(function(){level++;if(level===4){K.levels(4,4);K.finish({title:'足印里的画找到了',sub:'想想为什么形状相像',again:reset})}else show()},1100)}
targets.forEach(function(t){t.addEventListener('click',function(){choose(t)})});K.drag(source,{enabled:function(){return K.started&&!busy},targets:function(){return targets},onTap:function(){K.say('点一幅形状相像的图，也能拖足印过去。')},onDrop:function(el,t){if(t)choose(t)}});
K.onStart=reset;K.onState=function(s){if(s.demo==='bamboo'){reset();busy=true;picture.src=pics.chick;var t=K.$('#likeness-bamboo');move(t);t.classList.add('correct');K.say('细长的印和细长的竹叶，轮廓有相似。')}if(s.phase==='play')reset()};
})();
