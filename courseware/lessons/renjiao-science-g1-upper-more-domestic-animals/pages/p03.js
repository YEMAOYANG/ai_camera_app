(function(){
var photos={eat:'__IMG:dog-eat__',move:'__IMG:dog-move__',grow:'__IMG:dog-grow__',family:'__IMG:dog-family__'},names={eat:'狗吃食物的情境',move:'狗在平地小跑',grow:'幼犬到成犬的成长示意',family:'成年犬与幼犬相伴'},seen={},count=0,phase='play',epoch=0,busy=false,missing=false;
var photo=K.$('#album-photo'),record=K.$('#album-record');
K.hud({icon:'◉',title:'打开狗的生活相册',levels:4});K.owl();K.ready({emoji:'◉',title:'打开狗的生活相册',sub:'四种生活线索，一张张打开看',btn:'start-btn'});
K.$$('#album-board img').forEach(function(im){im.onerror=function(){missing=true;im.style.visibility='hidden';K.say('图片暂未载入，请重新打开本页')}});
function view(kind){photo.style.visibility='visible';photo.src=photos[kind];photo.alt=names[kind]}
function reset(){epoch++;phase='play';seen={};count=0;busy=false;record.innerHTML='';K.$$('#album-tabs button').forEach(function(b){b.classList.remove('album-viewed')});K.stars=0;K.$('#star-n').textContent='0';K.levels(4,0);view('eat');K.say('自由打开四张生活图，看看不同的线索')}
function open(kind,button){if(!K.started||busy||phase!=='play'||missing)return;view(kind);K.pop(photo);if(seen[kind]){K.say('这一种看过了，也可以再仔细看看');return}seen[kind]=true;count++;button.classList.add('album-viewed');var im=K.el('img','',null,record);im.src=photos[kind];im.alt=names[kind];K.star(1,button);K.levels(4,count);K.say('留下一种新的生活线索，不只是记动物名字','ok');if(count===4){busy=true;var token=epoch;setTimeout(function(){if(token!==epoch)return;K.finish({title:'四种生活线索看过了',sub:'再和另一种动物比较，才好找共同点',again:reset})},1000)}}
K.$$('#album-tabs button').forEach(function(b){b.addEventListener('click',function(){open(b.dataset.kind,b)})});K.$('#album-reset').addEventListener('click',reset);K.onState=function(s){if(s.demo){phase='demo';view(s.demo)}if(s.phase==='play')reset()};K.onStart=reset;reset();
})();
