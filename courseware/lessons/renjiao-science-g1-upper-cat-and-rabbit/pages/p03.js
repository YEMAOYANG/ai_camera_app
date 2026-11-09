(function(){
var steps=['whole','head','body','legs','tail'],photos=['__IMG:cat-orange__','__IMG:rabbit-white__'],level=0,step=0,tries=0,phase='play',busy=false,epoch=0,missing=false;
var photo=K.$('#scan-photo'),strip=K.$('#scan-strip');
K.hud({icon:'◉',title:'让镜头走一圈',levels:2});K.owl();K.ready({emoji:'◉',title:'让镜头走一圈',sub:'先全身，再按顺序看局部',btn:'start-btn'});
function preload(){missing=false;photos.forEach(function(src){var im=new Image();im.onerror=function(){missing=true;K.say('图片暂未载入，请点重来或重新打开本页')};im.src=src})}
function view(el,kind){var headSize=el.classList.contains('scan-record')||level===1?'auto 140%':'200% auto';el.style.backgroundImage='url("'+photos[level]+'")';el.style.backgroundSize=kind==='whole'?'contain':kind==='head'?headSize:kind==='legs'?'210% auto':kind==='body'?'230% auto':'250% auto';el.style.backgroundPosition=kind==='head'?'10% 0%':kind==='legs'?'48% 92%':kind==='tail'?'94% 55%':'53% 50%'}
function refresh(){K.$$('.scan-view').forEach(function(el){el.style.backgroundImage='url("'+photos[level]+'")'})}
function reset(){epoch++;level=0;step=0;tries=0;phase='play';busy=false;K.stars=0;K.$('#star-n').textContent='0';K.levels(2,0);strip.innerHTML='';view(photo,'whole');refresh();preload();K.say('先看全身，再从头往后观察')}
function choose(kind,button){if(!K.started||busy||phase!=='play'||missing)return;if(kind!==steps[step]){tries++;K.sfx.no();K.shake(button);if(tries===1)K.say('想想观察顺序，哪一处还没有看过','no');else if(tries===2)K.say('先整体，再头颈、躯干、四肢和尾','no');else{view(photo,steps[step]);K.highlight('#scan-'+steps[step]);K.say('老师示范这一处，再由你放入记录','no')}return}
tries=0;view(photo,kind);var record=K.el('div','scan-record',null,strip);view(record,kind);K.sfx.ok();step++;K.say('看到这一处，就留下真实的局部记录','ok');if(step<5)return;busy=true;K.star(1,button);var token=epoch;setTimeout(function(){if(token!==epoch)return;if(level===1){K.levels(2,2);K.finish({title:'一圈观察完成',sub:'先整体，再按身体顺序看',again:reset});return}level++;step=0;busy=false;strip.innerHTML='';refresh();view(photo,'whole');K.levels(2,level);K.say('换成兔，也按同样顺序看一遍')},850)}
K.$$('#scan-choices [data-view]').forEach(function(b){b.addEventListener('click',function(){choose(b.dataset.view,b)})});K.$('#scan-reset').addEventListener('click',reset);
K.onState=function(s){if(s.demo){phase='demo';view(photo,s.demo)}if(s.phase==='play')reset()};K.onStart=reset;reset();
})();
