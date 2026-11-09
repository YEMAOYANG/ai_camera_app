(function(){
var art={leaf:'__IMG:leaf__',cloud:'__IMG:cloud__',flower:'__IMG:flower__'},names={leaf:'叶子',cloud:'白云',flower:'花'},order=['leaf','cloud','flower'];
var level=0,misses=0,busy=false,demo=false,armed=false,timer;
K.hud({icon:'◎',title:'放大镜找发现',levels:3});K.owl();K.ready({emoji:'◎',title:'放大镜找发现',sub:'先看图片，再找相同的事物'});
function reset(){clearTimeout(timer);level=0;misses=0;busy=false;demo=false;armed=false;K.stars=0;K.$('#star-n').textContent='0';K.$('#collected-pictures').innerHTML='';K.$$('#nature-choices button').forEach(function(b){b.classList.remove('found');b.innerHTML='<img src="'+art[b.dataset.kind]+'" alt="'+names[b.dataset.kind]+'">'});render();K.say('比较颜色和外形，找相同的图。')}
function render(){var kind=order[Math.min(level,2)],im=K.$('#lens-picture');im.src=art[kind];im.alt='本关要观察的'+names[kind];K.$('#lens').classList.toggle('armed',armed);K.levels(3,level);}
function record(button){var im=button.querySelector('img');if(im){K.$('#collected-pictures').appendChild(im);im.alt='已观察的'+names[button.dataset.kind]};button.classList.add('found');}
function choose(button){if(!K.started||busy||demo)return;var kind=button.dataset.kind;if(kind!==order[level]){misses++;K.sfx.no();K.shake(button);K.say(misses===1?'再比一比图片的颜色和外形。':misses===2?'留心轮廓，不急着点下一幅。':'先看放大镜里的图，再慢慢比较。','no');if(misses>=3){K.highlight('#lens');misses=0}return}
 busy=true;misses=0;record(button);K.sfx.ok();K.star(1,button);K.say('进入观察窗了，再留心图里的细节。','ok');timer=setTimeout(function(){level++;if(level===3){K.levels(3,3);K.finish({title:'发现了三样事物',sub:'把你想知道的，说给大人听。',again:reset})}else{busy=false;render()}},950)}
K.$$('#nature-choices button').forEach(function(b){b.addEventListener('click',function(){choose(b)})});
K.$('#lens').addEventListener('click',function(){if(busy||demo)return;armed=true;render();K.sfx.pick()});
K.drag(K.$('#lens'),{enabled:function(){return K.started&&!busy&&!demo},targets:function(){return K.$$('#nature-choices button')},onTap:function(){armed=true;render()},onDrop:function(el,target){if(target)choose(target)}});
K.onStart=reset;K.onState=function(state){if(state.demo==='match'){reset();demo=true;record(K.$('#nature-0'));K.say('老师观察的图片进入观察窗。','ok')}if(state.phase==='play')reset()};
render();
K.$('#play').addEventListener('error',function(e){if(e.target&&e.target.tagName==='IMG'){e.target.alt='图片暂未加载';K.say('图片暂未加载，请重新打开这一页。','no')}},true);
})();