(function(){
var steps=['normal','hand','paper'],photos={normal:'__IMG:listen-bare__',hand:'__IMG:listen-cup__',paper:'__IMG:listen-cone__'},step=0,tries=0,phase='play',epoch=0,busy=false,shown='normal',missing=false;
var photo=K.$('#listen-photo'),strip=K.$('#listen-strip');
K.hud({icon:'◉',title:'排好三次听法',levels:3});K.owl();K.ready({emoji:'◉',title:'排好三次听法',sub:'动作先排好，实际感受再记录',btn:'start-btn'});
K.$$('#listen-board img').forEach(function(im){im.onerror=function(){missing=true;im.style.visibility='hidden';K.say('图片暂未载入，请重新打开本页')}});
function view(kind){shown=kind;photo.style.visibility='visible';photo.src=photos[kind];photo.alt=kind==='normal'?'双手放下直接听':kind==='hand'?'弯手放耳旁听':'纸卷靠耳外听'}
function reset(){epoch++;step=0;tries=0;phase='play';busy=false;strip.innerHTML='';view('normal');K.stars=0;K.$('#star-n').textContent='0';K.levels(3,0);K.say('先选直接听的动作，再安排另外两次')}
function choose(kind,button){if(!K.started||busy||phase!=='play'||missing)return;if(kind!==steps[step]){tries++;K.sfx.no();K.shake(button);if(tries===1)K.say('想想比较从哪一种基本听法开始','no');else if(tries===2)K.say('先直接听，再弯手，最后用纸卷','no');else{view(steps[step]);K.highlight('#listen-'+steps[step]);K.say('老师示范这一步，再由你留下动作记录','no')}return}
tries=0;view(kind);var im=K.el('img','',null,strip);im.src=photos[kind];im.alt='已安排的听法动作';K.star(1,button);K.sfx.ok();step++;K.levels(3,step);K.say('动作留下了，真实感受要在实物比较后记录','ok');if(step===3){busy=true;var token=epoch;setTimeout(function(){if(token!==epoch)return;K.finish({title:'三次听法安排好了',sub:'同一段声音，比较自己的真实感受',again:reset})},900)}}
K.$$('#listen-choices button').forEach(function(b){b.addEventListener('click',function(){choose(b.dataset.method,b)})});K.$('#listen-replay').addEventListener('click',function(){if(K.started&&!missing){K.pop(photo);view(shown);K.say('动作再看一次，实际听法请大人陪你试')}});K.$('#listen-reset').addEventListener('click',reset);K.onState=function(s){if(s.demo){phase='demo';view(s.demo)}if(s.phase==='play')reset()};K.onStart=reset;reset();
})();
