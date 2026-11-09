(function(){
'use strict';
var C={"kind": "work", "title": "nurse · driver", "targets": {"clinic": "#clinic-place", "bus": "#bus-place"}, "tasks": [{"image": "nurse", "correct": "clinic"}, {"image": "driver", "correct": "bus"}], "hint1": "再看看照片里的人正在做什么。", "hint2": "留意照护场景，或驾驶座和方向盘。"};
var pictures={nurse:'__IMG:nurse__',driver:'__IMG:driver__',policeman:'__IMG:policeman__',policewoman:'__IMG:policewoman__',pupil:'__IMG:pupil__'};
var level=0,wrong=0,busy=false,mode='play',pending=null;
var board=K.$('#activity-board'),card=K.$('#job-card');
K.hud({icon:'',title:C.title,levels:C.tasks.length});K.owl();
function task(){return C.tasks[Math.min(level,C.tasks.length-1)]}
function clearPhotos(){board.classList.remove('self-solved');K.$$('.placed-photos').forEach(function(el){el.innerHTML=''})}
function place(key,image){var dest=K.$(C.targets[key]);if(!dest)return;var frame=dest.querySelector('.placed-photos');var img=K.el('img','token-result','',frame);img.src=pictures[image];img.alt='放好的职业人物照片';if(C.kind==='sort'){img.style.left=(18+frame.children.length*74)+'px';img.style.width='104px'}bindFailure(img);if(C.kind==='self')board.classList.add('self-solved')}
function bindFailure(img){img.addEventListener('error',function(){var host=img.parentElement;if(!host)return;host.classList.add('image-failed');if(host.querySelector('.reload-picture'))return;var b=K.el('button','reload-picture','↻',host);b.setAttribute('aria-label','重试加载图片');b.addEventListener('click',function(e){e.stopPropagation();host.classList.remove('image-failed');b.remove();img.src=img.getAttribute('src')})})}
K.$$('img').forEach(bindFailure);
function render(){board.dataset.level=String(level);board.dataset.mode=mode;board.classList.toggle('demo',mode==='demo');K.levels(C.tasks.length,level);
 if(card){card.classList.remove('picked');K.$('#active-photo').src=pictures[task().image]}
 if(C.kind==='self'){var order=level%2?['driver','pupil','nurse']:['pupil','nurse','driver'];order.forEach(function(key,i){K.$('#pick-'+key).style.left=(i*210)+'px'})}
}
function reset(next){if(pending!==null)clearTimeout(pending);pending=null;level=0;wrong=0;busy=false;mode=next||'play';K.stars=0;var sn=K.$('#star-n');if(sn)sn.textContent='0';clearPhotos();render();K.say('看人物和工作，把照片放到合适的位置。')}
function choose(key){if(mode!=='play'||busy||level>=C.tasks.length)return;var current=task();if(key!==current.correct){wrong++;K.sfx.no();K.shake(C.kind==='self'?K.$('#pick-'+key):card);K.say(wrong===1?C.hint1:C.hint2,'no');if(wrong===2)K.highlight(C.kind==='self'?'#picture-choices':'#job-card');if(wrong>=3){K.highlight(C.kind==='self'?'#pick-pupil':C.targets[current.correct]);K.say('老师指一指，再请你自己放一次。')}return}
 busy=true;wrong=0;place(current.correct,current.image);K.sfx.ok();K.star(1,C.kind==='self'?K.$('#pick-pupil'):card);K.say('人物和这页相册对应上了。','ok');
 pending=setTimeout(function(){pending=null;level++;busy=false;if(level>=C.tasks.length){board.dataset.level=String(level);K.levels(C.tasks.length,level);K.finish({title:'相册整理好了',sub:'你完成了图片对应任务',again:function(){reset('play')}})}else{if(C.kind==='self')clearPhotos();render()}},650)
}
Object.keys(C.targets).forEach(function(key){var dest=K.$(C.targets[key]);if(C.kind!=='self')dest.addEventListener('click',function(){choose(key)})});
if(card){K.drag(card,{enabled:function(){return mode==='play'&&!busy},targets:function(){return Object.values(C.targets).map(function(s){return K.$(s)})},onDrop:function(el,target){if(!target)return;var key=Object.keys(C.targets).find(function(k){return K.$(C.targets[k])===target});choose(key)},onTap:function(){card.classList.add('picked');K.sfx.pick()}})}
if(C.kind==='self')['pupil','nurse','driver'].forEach(function(key){K.$('#pick-'+key).addEventListener('click',function(){choose(key)})});
K.onState=function(state){if(state.mode==='demo'){reset('demo');place(task().correct,task().image);K.say('先看老师示范，接着由你独立尝试。')}else if(state.mode==='play'){reset('play')}};
K.onStart=function(){reset('play')};
K.ready({emoji:'图片暂未加载',title:C.title,sub:'看图片，听老师，再动手',btn:'start-btn'});
render();
})();
